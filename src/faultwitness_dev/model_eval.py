from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter
from typing import Any

from faultwitness.contracts.models import (
    AgentBudget,
    ModelFamily,
    ModelMessage,
    ModelRequest,
    SpanRecord,
    SpanStatus,
    TraceEnvelope,
    TraceStage,
)
from faultwitness.models import (
    CapabilityCatalog,
    ChannelName,
    ModelCapability,
    ModelGateway,
)
from faultwitness.models.channel import OpenAICompatibleChannel
from faultwitness.observability.exporters import LangSmithExporter
from faultwitness.observability.sanitizer import TraceSanitizer
from faultwitness_dev.bootstrap import (
    BootstrapPaths,
    default_sops_executable,
    load_secret_bundle,
    record_live_api_verification,
)
from faultwitness_dev.errors import GovernanceError

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_BAILIAN_ENDPOINT = "https://dashscope.aliyuncs.com/compatible-mode/v1"


def _id(prefix: str) -> str:
    return prefix + "".join(secrets.choice(_ALPHABET) for _ in range(26))


def _request(
    family: ModelFamily,
    model_id: str,
    capability: str,
) -> ModelRequest:
    schema = {
        "type": "object",
        "properties": {"status": {"type": "string", "const": "ok"}},
        "required": ["status"],
        "additionalProperties": False,
    }
    tool = {
        "type": "function",
        "function": {
            "name": "report_status",
            "description": "Report a synthetic status used by a contract test.",
            "parameters": schema,
        },
    }
    prompts = {
        "complete": "Reply with exactly OK.",
        "structured": "Return one JSON object with status set to ok. JSON only.",
        "forced_tool": "Call report_status with status set to ok. Do not answer directly.",
        "stream": "Reply with exactly STREAM_OK.",
    }
    return ModelRequest(
        request_id=_id("mreq_"),
        tenant_id=_id("ten_"),
        correlation_id=_id("corr_"),
        model_family=family,
        model_id=model_id,
        messages=(ModelMessage(role="user", content=prompts[capability]),),
        target_json_schema=schema if capability == "structured" else None,
        tool_schemas=(tool,) if capability == "forced_tool" else (),
        stream=capability == "stream",
        budget=AgentBudget(
            deadline=datetime.now(UTC) + timedelta(minutes=3),
            max_steps=1,
            max_model_calls=3,
            max_tokens=256,
            max_cost_usd=1,
        ),
    )


async def _export_trial_trace(
    *,
    credential: str,
    candidate_sha: str,
    family: ModelFamily,
    model_id: str,
    route: str,
    outcome: str,
    started_at: datetime,
    ended_at: datetime,
) -> str:
    span_id = _id("span_")
    envelope = TraceEnvelope(
        trace_id=_id("trace_"),
        tenant_id=_id("ten_"),
        correlation_id=_id("corr_"),
        contracts_version="1.1.0",
        candidate_sha=candidate_sha,
        spans=(
            SpanRecord(
                span_id=span_id,
                name="model.gateway.trial",
                stage=TraceStage.MODEL,
                started_at=started_at,
                ended_at=ended_at,
                status=SpanStatus.OK if outcome == "pass" else SpanStatus.ERROR,
                attributes={
                    "model.family": family.value,
                    "model.route": route,
                    "model.snapshot": model_id,
                    "outcome": outcome,
                },
            ),
        ),
        emitted_at=ended_at,
    )
    sanitizer = TraceSanitizer(secrets.token_bytes(32))
    trace = sanitizer.sanitize(envelope)
    exporter = LangSmithExporter(
        credential,
        project=f"faultwitness-g01-models-{candidate_sha[:12]}",
    )
    result = await exporter.export(trace)
    return str(result["remote_trace_id"])


async def _run_live(root: Path, candidate_sha: str) -> dict[str, Any]:
    paths = BootstrapPaths.defaults()
    bundle = load_secret_bundle(paths, default_sops_executable())
    catalog = CapabilityCatalog.load(root / "config/models/catalog.yaml")
    channel = OpenAICompatibleChannel(
        base_url=_BAILIAN_ENDPOINT,
        credential=bundle.bailian_api_key,
        timeout_seconds=120,
    )
    gateway = ModelGateway(catalog=catalog, channels={ChannelName.BAILIAN: channel})
    trials: list[dict[str, Any]] = []
    trace_ids: list[str] = []
    for family in ModelFamily:
        primary = catalog.candidates(family, ModelCapability.COMPLETE)[0]
        for capability in ("complete", "structured", "forced_tool", "stream"):
            for repetition in range(1, 4):
                request = _request(family, primary.model_id, capability)
                start_wall = perf_counter()
                started_at = datetime.now(UTC)
                outcome = "fail"
                route_name = f"bailian:{primary.model_id}"
                usage_total: int | None = None
                try:
                    if capability == "stream":
                        chunks = [chunk async for chunk in gateway.stream(request)]
                        if not "".join(chunk.delta for chunk in chunks).strip():
                            raise GovernanceError("live stream produced no visible content")
                        usage = next(
                            (chunk.usage for chunk in reversed(chunks) if chunk.usage), None
                        )
                        if usage is None:
                            raise GovernanceError("live stream omitted attributable usage")
                        usage_total = usage.total_tokens
                        route = chunks[0].route
                    else:
                        response = await gateway.complete(request)
                        route = response.route
                        if capability == "complete" and not response.content.strip():
                            raise GovernanceError("live completion produced no content")
                        if capability == "structured" and response.structured_output != {
                            "status": "ok"
                        }:
                            raise GovernanceError("live structured result failed strict schema")
                        if capability == "forced_tool" and not response.tool_calls:
                            raise GovernanceError("live forced-tool result omitted tool call")
                        if response.usage is None:
                            raise GovernanceError("live response omitted attributable usage")
                        usage_total = response.usage.total_tokens
                    if route.fallback_count != 0 or route.model_family is not family:
                        raise GovernanceError("live primary capability used an unplanned fallback")
                    route_name = f"{route.channel.value}:{route.resolved_model}"
                    outcome = "pass"
                finally:
                    ended_at = datetime.now(UTC)
                    trace_ids.append(
                        await _export_trial_trace(
                            credential=bundle.langsmith_api_key,
                            candidate_sha=candidate_sha,
                            family=family,
                            model_id=primary.model_id,
                            route=route_name,
                            outcome=outcome,
                            started_at=started_at,
                            ended_at=ended_at,
                        )
                    )
                trials.append(
                    {
                        "family": family.value,
                        "model_id": primary.model_id,
                        "capability": capability,
                        "repetition": repetition,
                        "status": outcome,
                        "latency_ms": round((perf_counter() - start_wall) * 1000, 3),
                        "usage_total_tokens": usage_total,
                        "route": route_name,
                    }
                )
    if len(trials) != 36 or any(item["status"] != "pass" for item in trials):
        raise GovernanceError("live Bailian capability matrix did not pass 36/36")
    record_live_api_verification(paths, secret_name="bailian.api_key", iteration="I-0014")
    return {
        "trial_count": len(trials),
        "trials": trials,
        "langsmith_trace_ids": trace_ids,
        "catalog_sha256": hashlib.sha256(
            (root / "config/models/catalog.yaml").read_bytes()
        ).hexdigest(),
    }


def run_model_eval(root: Path, candidate_sha: str) -> dict[str, Any]:
    summary = asyncio.run(_run_live(root, candidate_sha))
    evidence_dir = BootstrapPaths.defaults().config_root / "evidence" / "I-0014"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    evidence = {
        "schema_version": "1.0.0",
        "eval_id": "EVAL-G01-008",
        "candidate_sha": candidate_sha,
        "status": "pass",
        **summary,
    }
    payload = json.dumps(evidence, sort_keys=True, indent=2) + "\n"
    output = evidence_dir / f"{candidate_sha}.json"
    output.write_text(payload, encoding="utf-8")
    return {
        "eval_id": "EVAL-G01-008",
        "candidate_sha": candidate_sha,
        "status": "pass",
        "checks": {
            "bailian_live_36_of_36": "pass",
            "structured_schema": "pass",
            "forced_tool_schema": "pass",
            "stream_reconstruction_usage": "pass",
            "sanitized_langsmith_per_trial": "pass",
        },
        "trial_count": summary["trial_count"],
        "catalog_sha256": summary["catalog_sha256"],
        "evidence_sha256": hashlib.sha256(payload.encode()).hexdigest(),
        "first_langsmith_trace_id": summary["langsmith_trace_ids"][0],
        "last_langsmith_trace_id": summary["langsmith_trace_ids"][-1],
    }
