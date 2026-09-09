from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import faultwitness_dev.checks as active_checks
from faultwitness.api.app import create_app
from faultwitness.identity.oidc import AuthenticatedPrincipal, AuthenticationError
from faultwitness_dev.cli import parser
from faultwitness_dev.errors import GovernanceError
from faultwitness_dev.experiment import (
    ExperimentRunner,
    ExperimentUnit,
    TrialJournal,
)
from faultwitness_dev.g02_baselines import score_result
from faultwitness_dev.infra import _remote_process
from faultwitness_dev.schemas import load_data

ROOT = Path(__file__).resolve().parents[2]


class FakeAuthenticator:
    async def authenticate(self, authorization: str | None) -> AuthenticatedPrincipal:
        if not authorization or not authorization.startswith("Bearer "):
            raise AuthenticationError("invalid token")
        tenant, role = authorization.removeprefix("Bearer ").split(":")
        return AuthenticatedPrincipal(
            tenant_id=tenant,
            user_id=f"user-{tenant}",
            roles=frozenset({role}),
            token_id=f"token-{tenant}",
            expires_at=int(time.time()),
        )


def _incident_body() -> dict[str, object]:
    now = datetime.now(UTC)
    return {
        "source": "governance-v2-proof",
        "environment_id": "env_test",
        "service_scope": ["svc_api"],
        "time_window": {
            "start": (now - timedelta(minutes=5)).isoformat(),
            "end": now.isoformat(),
        },
        "symptom_summary": "synthetic latency increase",
        "mode": "diagnosis_only",
        "budget": {
            "deadline": (now + timedelta(minutes=10)).isoformat(),
            "max_steps": 10,
            "max_model_calls": 3,
            "max_tokens": 2000,
            "max_cost_usd": 1.0,
        },
    }


def _headers() -> dict[str, str]:
    return {
        "Authorization": "Bearer tenant-a:operator",
        "Idempotency-Key": "governance-v2-idempotency",
    }


def test_application_tenant_identity_override_fails_closed() -> None:
    client = TestClient(create_app(authenticator=FakeAuthenticator()))
    body = _incident_body() | {"tenant_id": "tenant-b"}
    assert client.post("/v1/incidents", headers=_headers(), json=body).status_code == 400
    headers = _headers() | {"X-Tenant-ID": "tenant-b"}
    assert client.post("/v1/incidents", headers=headers, json=_incident_body()).status_code == 403


def test_application_idempotency_digest_conflict_fails_closed() -> None:
    client = TestClient(create_app(authenticator=FakeAuthenticator()))
    first = client.post("/v1/incidents", headers=_headers(), json=_incident_body())
    assert first.status_code == 201
    changed = _incident_body()
    changed["symptom_summary"] = "different semantic request"
    conflict = client.post("/v1/incidents", headers=_headers(), json=changed)
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "ERR-CONFLICT"


def test_infra_child_process_transport_is_byte_exact() -> None:
    payload = "set -eu\nprintf '跨平台-ok'\n"
    result = _remote_process(
        subprocess.run,
        [sys.executable, "-c"],
        "import sys; print(sys.stdin.buffer.read().hex())",
        payload,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == payload.encode("utf-8").hex()


def test_eval_scorer_malformed_and_unsupported_claim_semantics() -> None:
    malformed = score_result({"status": "ok"}, {"root_cause": "expected"})
    assert malformed["status"] == "scored_failure"
    assert malformed["failure_class"] == "malformed"
    unsupported = score_result(
        {
            "case_id": "synthetic-unsupported",
            "status": "ok",
            "root_cause": "expected",
            "root_cause_candidates": ["expected"],
            "evidence": ["evidence-1"],
            "claims": [{"claim": "invented", "supported": False}],
        },
        {"root_cause": "expected", "evidence": ["evidence-1"]},
    )
    assert unsupported["unsupported_critical_claim"] == 1.0


def _json_digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def test_journal_separates_execution_attempt_from_record_version(tmp_path: Path) -> None:
    journal = TrialJournal(tmp_path)
    running = journal.begin(
        "seed-2",
        producer_sha="1" * 40,
        cache_key="2" * 64,
    )
    failed = journal.finish("seed-2", "metric_fail", {"reason": "oracle"})
    assert running["execution_attempt"] == failed["execution_attempt"] == 1
    assert running["record_version"] == 1
    assert failed["record_version"] == 2
    resumed = journal.begin(
        "seed-2",
        producer_sha="3" * 40,
        cache_key="4" * 64,
    )
    assert resumed["execution_attempt"] == 2
    assert resumed["record_version"] == 3


def test_journal_preserves_failed_observation_across_semantic_fix(tmp_path: Path) -> None:
    journal = TrialJournal(tmp_path)
    journal.begin("side-effect", producer_sha="1" * 40, cache_key="2" * 64)
    journal.checkpoint(
        "side-effect",
        "terminal-observation",
        {"namespace": "proof", "pod": "failed", "exit_code": 7},
    )
    journal.finish("side-effect", "metric_fail", {"root_cause": "intentional exit 7"})

    resumed = journal.begin("side-effect", producer_sha="3" * 40, cache_key="4" * 64)
    assert resumed["runtime_checkpoints"] == {}
    assert resumed["execution_attempt"] == 2
    assert len(resumed["history"]) == 1
    failed = resumed["history"][0]
    assert failed["status"] == "metric_fail"
    assert failed["execution_attempt"] == 1
    assert failed["runtime_checkpoints"]["terminal-observation"]["exit_code"] == 7

    journal.checkpoint("side-effect", "cleanup", {"namespace": "not-found"})
    passed = journal.finish("side-effect", "pass", {"ready": True})
    assert passed["history"][0] == failed


def _matrix_units() -> tuple[ExperimentUnit, ...]:
    units: list[ExperimentUnit] = []
    units.extend(
        ExperimentUnit(f"access-{index:02d}", ("identity_and_storage",), (), f"a{index}")
        for index in range(1, 61)
    )
    trace_ids = tuple(f"trace-{index:02d}" for index in range(1, 7))
    units.extend(
        ExperimentUnit(unit_id, ("trace_service",), (), f"t{index}")
        for index, unit_id in enumerate(trace_ids, 1)
    )
    units.extend(
        ExperimentUnit(f"canary-{index:02d}", ("writer_surfaces",), (), f"c{index}")
        for index in range(1, 23)
    )
    scenario_ids: list[str] = []
    for seed in range(1, 33):
        unit_id = f"scenario-{seed:02d}"
        scenario_ids.append(unit_id)
        checkpoints = ("sut", "trace_service")
        if seed in {8, 12, 19}:
            checkpoints += ("email-memory",)
        units.append(ExperimentUnit(unit_id, checkpoints, trace_ids, f"s{seed}"))
    baseline_ids: list[str] = []
    for seed, scenario_id in enumerate(scenario_ids, 1):
        for baseline in ("naive", "no-rag"):
            for repetition in range(1, 4):
                unit_id = f"baseline-{seed:02d}-{baseline}-{repetition}"
                baseline_ids.append(unit_id)
                units.append(
                    ExperimentUnit(
                        unit_id,
                        ("sut", "trace_service", "model_route"),
                        (scenario_id,),
                        f"b{seed}-{baseline}-{repetition}",
                    )
                )
    units.append(ExperimentUnit("aggregate", (), tuple(baseline_ids), "bootstrap-b2000"))
    return tuple(units)


@pytest.mark.parametrize(
    ("changed", "expected_prefixes", "expected_exact"),
    [
        (None, (), set()),
        ("identity_and_storage", ("access-",), set()),
        ("trace_service", ("trace-", "scenario-", "baseline-"), {"aggregate"}),
        ("writer_surfaces", ("canary-",), set()),
        ("sut", ("scenario-", "baseline-"), {"aggregate"}),
        ("model_route", ("baseline-",), {"aggregate"}),
        (
            "email-memory",
            (),
            {
                "scenario-08",
                "scenario-12",
                "scenario-19",
                "aggregate",
                *{
                    f"baseline-{seed:02d}-{baseline}-{repetition}"
                    for seed in (8, 12, 19)
                    for baseline in ("naive", "no-rag")
                    for repetition in range(1, 4)
                },
            },
        ),
    ],
)
def test_runner_performs_exact_semantic_invalidation(
    tmp_path: Path,
    changed: str | None,
    expected_prefixes: tuple[str, ...],
    expected_exact: set[str],
) -> None:
    units = _matrix_units()
    checkpoints = {
        "identity_and_storage": "identity-v1",
        "trace_service": "trace-v1",
        "writer_surfaces": "writers-v1",
        "sut": "sut-v1",
        "model_route": "model-v1",
        "email-memory": "email-v1",
    }
    journal = TrialJournal(tmp_path)
    handlers = {
        unit.unit_id: (lambda execution: {"payload": {"unit": execution.unit.unit_id}})
        for unit in units
    }
    first = ExperimentRunner(
        units, journal, checkpoints, producer_sha="1" * 40
    ).run(handlers)
    assert len(first.executed_units) == 313
    before = {
        unit.unit_id: str(journal.read(unit.unit_id)["artifact_digest"])  # type: ignore[index]
        for unit in units
    }
    if changed is not None:
        checkpoints[changed] += "-changed"
    second = ExperimentRunner(
        units,
        journal,
        checkpoints,
        producer_sha="2" * 40,
    ).run(handlers)
    expected = {
        unit.unit_id
        for unit in units
        if any(unit.unit_id.startswith(prefix) for prefix in expected_prefixes)
    } | expected_exact
    assert set(second.executed_units) == expected
    assert len(second.reused_units) == 313 - len(expected)
    assert all(
        journal.read(unit_id)["artifact_digest"] == digest  # type: ignore[index]
        for unit_id, digest in before.items()
        if unit_id not in expected
    )


def _tracked_tree_fingerprint() -> str:
    diff = subprocess.run(
        ["git", "diff", "--binary", "HEAD", "--", "."],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout
    return hashlib.sha256(diff).hexdigest()


def test_application_direct_debug_campaign_uses_one_journal_unit(tmp_path: Path) -> None:
    before = _tracked_tree_fingerprint()
    client = TestClient(create_app(authenticator=FakeAuthenticator()))
    unit = ExperimentUnit(
        "application-request",
        ("request_builder",),
        (),
        "tenant-create-contract",
    )
    journal = TrialJournal(tmp_path)

    def broken(_execution):  # type: ignore[no-untyped-def]
        response = client.post(
            "/v1/incidents",
            headers=_headers() | {"X-Tenant-ID": "tenant-b"},
            json=_incident_body(),
        )
        assert response.status_code == 403
        return {
            "status": "metric_fail",
            "payload": {"root_cause": "cross-tenant header", "observed": 403},
        }

    failed = ExperimentRunner(
        (unit,), journal, {"request_builder": "mutant-header"}, producer_sha="1" * 40
    ).run({unit.unit_id: broken})
    assert failed.records[0]["status"] == "metric_fail"
    with pytest.raises(GovernanceError, match="cannot retry unchanged"):
        ExperimentRunner(
            (unit,),
            journal,
            {"request_builder": "mutant-header"},
            producer_sha="2" * 40,
        ).run({unit.unit_id: broken})

    def fixed(_execution):  # type: ignore[no-untyped-def]
        headers = _headers() | {"Idempotency-Key": "governance-v2-fixed"}
        created = client.post("/v1/incidents", headers=headers, json=_incident_body())
        body_override = client.post(
            "/v1/incidents",
            headers=_headers() | {"Idempotency-Key": "governance-v2-body-override"},
            json=_incident_body() | {"tenant_id": "tenant-b"},
        )
        changed = _incident_body()
        changed["symptom_summary"] = "different semantic request"
        conflict = client.post("/v1/incidents", headers=headers, json=changed)
        observed = {
            "created": created.status_code,
            "body_override": body_override.status_code,
            "idempotency_conflict": conflict.status_code,
        }
        assert observed == {
            "created": 201,
            "body_override": 400,
            "idempotency_conflict": 409,
        }
        return {"status": "pass", "payload": observed}

    repaired = ExperimentRunner(
        (unit,), journal, {"request_builder": "fixed"}, producer_sha="3" * 40
    ).run({unit.unit_id: fixed})
    assert repaired.executed_units == (unit.unit_id,)
    assert journal.read(unit.unit_id)["execution_attempt"] == 2  # type: ignore[index]
    assert _tracked_tree_fingerprint() == before


def test_infra_direct_debug_campaign_is_byte_exact(tmp_path: Path) -> None:
    before = _tracked_tree_fingerprint()
    unit = ExperimentUnit("infra-bytes", ("transport",), (), "stdin-byte-contract")
    journal = TrialJournal(tmp_path)
    payload = "set -eu\nprintf 'cross-platform-ok'\n"

    def invoke(value: str) -> str:
        result = _remote_process(
            subprocess.run,
            [sys.executable, "-c"],
            "import sys; print(sys.stdin.buffer.read().hex())",
            value,
        )
        assert result.returncode == 0
        return result.stdout.strip()

    def crlf_mutant(_execution):  # type: ignore[no-untyped-def]
        observed = invoke(payload.replace("\n", "\r\n"))
        assert observed != payload.encode().hex()
        return {
            "status": "metric_fail",
            "payload": {"root_cause": "text-mode CRLF conversion", "observed": observed},
        }

    failed = ExperimentRunner(
        (unit,), journal, {"transport": "crlf-mutant"}, producer_sha="1" * 40
    ).run({unit.unit_id: crlf_mutant})
    assert failed.records[0]["status"] == "metric_fail"

    def bytes_fixed(_execution):  # type: ignore[no-untyped-def]
        observed = invoke(payload)
        assert observed == payload.encode().hex()
        return {"status": "pass", "payload": {"byte_exact": True}}

    repaired = ExperimentRunner(
        (unit,), journal, {"transport": "utf8-bytes"}, producer_sha="2" * 40
    ).run({unit.unit_id: bytes_fixed})
    assert repaired.executed_units == (unit.unit_id,)
    assert journal.read(unit.unit_id)["execution_attempt"] == 2  # type: ignore[index]
    assert _tracked_tree_fingerprint() == before


def test_eval_direct_debug_campaign_fails_closed(tmp_path: Path) -> None:
    before = _tracked_tree_fingerprint()
    unit = ExperimentUnit("eval-adapter", ("adapter",), (), "claim-score-contract")
    journal = TrialJournal(tmp_path)
    ground_truth = {"root_cause": "expected", "evidence": ["evidence-1"]}

    def malformed(_execution):  # type: ignore[no-untyped-def]
        score = score_result({"status": "ok"}, ground_truth)
        assert score["status"] == "scored_failure"
        return {"status": "metric_fail", "payload": score}

    failed = ExperimentRunner(
        (unit,), journal, {"adapter": "malformed"}, producer_sha="1" * 40
    ).run({unit.unit_id: malformed})
    assert failed.records[0]["status"] == "metric_fail"

    def fixed(_execution):  # type: ignore[no-untyped-def]
        score = score_result(
            {
                "case_id": "proof-case",
                "status": "ok",
                "root_cause": "expected",
                "root_cause_candidates": ["expected"],
                "evidence": ["evidence-1"],
                "claims": [{"claim": "supported", "supported": True}],
            },
            ground_truth,
        )
        assert score["status"] == "scored"
        assert score["unsupported_critical_claim"] == 0.0
        return {"status": "pass", "payload": score}

    repaired = ExperimentRunner(
        (unit,), journal, {"adapter": "fixed"}, producer_sha="2" * 40
    ).run({unit.unit_id: fixed})
    assert repaired.executed_units == (unit.unit_id,)
    assert journal.read(unit.unit_id)["execution_attempt"] == 2  # type: ignore[index]
    assert _tracked_tree_fingerprint() == before


def test_active_cli_has_no_legacy_lifecycle_or_binding_entrypoint() -> None:
    command_action = next(
        action for action in parser()._actions if action.__class__.__name__ == "_SubParsersAction"
    )
    commands = set(command_action.choices)
    assert "verify-docs" in commands
    legacy_commands = {
        "eval-changed",
        "eval-iteration",
        "eval-g01",
        "eval-g01-close",
        "eval-g02",
        "eval-g02-close",
        "lab-g02",
        "inspect-g01-reconciliation",
        "rehearse-g01-postgres-restore",
        "rehearse-g01-k3s-snapshot",
        "rehearse-g01-k3s-restore",
        "rehearse-g01-platform-rollback",
        "run-g01-postgres-matrix",
        "run-g01-redis-matrix",
        "run-g01-api-load-matrix",
        "run-g01-trace-matrix",
    }
    assert commands.isdisjoint(legacy_commands)


def test_legacy_epoch_is_preserved_but_not_registered() -> None:
    registry = load_data(ROOT / "governance/ASSETS.yaml")
    patterns = {item["path"] for item in registry["assets"]}
    assert "governance/iterations/*.yaml" not in patterns
    assert "governance/gates/G*.yaml" not in patterns
    assert "docs/evals/EVAL-G*/manifest.json" not in patterns
    assert (ROOT / "governance/iterations/C-G02-012.yaml").is_file()
    assert (ROOT / "docs/evals/EVAL-G02-046/manifest.json").is_file()


FORBIDDEN_LIFECYCLE_MODULES = {
    "faultwitness_dev.changes",
    "faultwitness_dev.evals",
    "faultwitness_dev.g01_eval",
    "faultwitness_dev.g02_eval",
    "faultwitness_dev.model_eval",
}


def _local_module_path(module: str) -> Path | None:
    relative = Path(*module.split("."))
    module_file = ROOT / "src" / relative.with_suffix(".py")
    if module_file.is_file():
        return module_file
    package_file = ROOT / "src" / relative / "__init__.py"
    return package_file if package_file.is_file() else None


def _imports(module: str, path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported: set[str] = set()
    package = module if path.name == "__init__.py" else module.rpartition(".")[0]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
            continue
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level:
            target = importlib.util.resolve_name(
                "." * node.level + (node.module or ""), package
            )
        else:
            target = node.module or ""
        if target:
            imported.add(target)
            for alias in node.names:
                possible_submodule = f"{target}.{alias.name}"
                if _local_module_path(possible_submodule) is not None:
                    imported.add(possible_submodule)
    return {
        name
        for name in imported
        if name == "faultwitness"
        or name == "faultwitness_dev"
        or name.startswith(("faultwitness.", "faultwitness_dev."))
    }


def _cli_import_closure() -> dict[str, Path]:
    pending = ["faultwitness_dev.cli"]
    closure: dict[str, Path] = {}
    while pending:
        module = pending.pop()
        if module in closure:
            continue
        path = _local_module_path(module)
        if path is None:
            continue
        closure[module] = path
        pending.extend(sorted(_imports(module, path) - closure.keys()))
    return closure


def test_active_cli_and_pytest_imports_cannot_reach_legacy_lifecycle() -> None:
    closure = _cli_import_closure()
    assert "faultwitness_dev.cli" in closure
    assert FORBIDDEN_LIFECYCLE_MODULES.isdisjoint(closure)

    test_imports: set[str] = set()
    for path in sorted((ROOT / "tests").rglob("*.py")):
        test_imports.update(_imports("tests." + path.stem, path))
    assert FORBIDDEN_LIFECYCLE_MODULES.isdisjoint(test_imports)
    assert all(_local_module_path(module) is None for module in FORBIDDEN_LIFECYCLE_MODULES)


LEGACY_REFERENCE = re.compile(
    r"--candidate-sha|candidate_sha|candidate-binding|evaluated_revision|"
    r"evidence_head(?:_sha)?|active_iteration|eval-changed|"
    r"(?<![A-Z0-9])(?:I-[0-9]{4}|[AC]-G02-[0-9]{3})(?![A-Z0-9])",
    re.IGNORECASE,
)
RUNTIME_PROVENANCE_FILES = {
    "deploy/g02/gate_probe.py",
    "src/faultwitness/contracts/generated/contracts-v1.1.0.json",
    "src/faultwitness/contracts/models.py",
    "src/faultwitness/observability/buffer.py",
    "src/faultwitness/observability/exporters.py",
    "src/faultwitness/observability/sanitizer.py",
    "src/faultwitness_dev/observability_deploy.py",
}


def _active_reachability_files() -> list[Path]:
    roots = (
        ROOT / "src",
        ROOT / "deploy",
        ROOT / ".github",
        ROOT / "docs" / "contracts",
        ROOT / "docs" / "governance",
        ROOT / "docs" / "runbooks",
        ROOT / "docs" / "templates",
    )
    files = [
        path
        for directory in roots
        for path in directory.rglob("*")
        if path.is_file()
        and path.suffix.lower() in {".cmd", ".json", ".md", ".py", ".sh", ".yaml", ".yml"}
    ]
    files.extend(
        [
            ROOT / "AGENTS.md",
            ROOT / "Makefile",
            ROOT / "PROJECT_STATE.yaml",
            ROOT / "README.md",
            ROOT / "docs/roadmap/PHASES.md",
            ROOT / "tools/bin/make.cmd",
            ROOT / "governance/ASSETS.yaml",
        ]
    )
    return sorted(set(files))


def _classify_legacy_reference(relative: str, line: str, token: str) -> str:
    if relative in RUNTIME_PROVENANCE_FILES and token.lower() == "candidate_sha":
        return "necessary runtime provenance"
    if relative.startswith("docs/governance/"):
        return "historical/tag narrative"
    if relative in {"AGENTS.md", "README.md", "docs/roadmap/PHASES.md"}:
        return "historical/tag narrative"
    if relative.startswith("docs/runbooks/"):
        lowered = line.lower()
        negative_markers = ("legacy", "not ", "no ", "none ", "without", "does not")
        if any(marker in lowered for marker in negative_markers):
            return "historical/tag narrative"
    return "active redundancy"


def test_active_reachability_classifies_every_legacy_reference() -> None:
    classified: list[tuple[str, int, str, str]] = []
    for path in _active_reachability_files():
        relative = path.relative_to(ROOT).as_posix()
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for match in LEGACY_REFERENCE.finditer(line):
                if (
                    relative == "src/faultwitness/contracts/generated/contracts-v1.1.0.json"
                    and match.group(0).lower() != "candidate_sha"
                ):
                    continue
                classified.append(
                    (
                        relative,
                        line_number,
                        match.group(0),
                        _classify_legacy_reference(relative, line, match.group(0)),
                    )
                )
    assert classified
    assert {row[3] for row in classified} == {
        "historical/tag narrative",
        "necessary runtime provenance",
    }


def test_active_templates_entrypoints_and_ci_are_minimal() -> None:
    templates = {path.name for path in (ROOT / "docs/templates").iterdir() if path.is_file()}
    assert templates == {"ADR.example.yaml", "REQUIREMENT.example.yaml"}

    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    shim = (ROOT / "tools/bin/make.cmd").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/baseline.yml").read_text(encoding="utf-8")
    assert makefile.count("verify-fast") == 3
    assert "verify-docs:" in makefile
    assert "eval" not in makefile.lower()
    assert "Only verify-fast and verify-docs are active make targets" in shim
    assert "make verify-fast" in workflow
    assert "windows-latest" not in workflow
    assert "matrix.os" not in workflow
    assert not LEGACY_REFERENCE.search(makefile + shim + workflow)
    assert not (ROOT / ".github/rulesets/main.json").exists()


def test_verify_fast_invokes_only_active_local_checks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    commands: list[tuple[str, ...]] = []
    calls: list[str] = []
    monkeypatch.setattr(active_checks, "repository_files", lambda _root: [])
    monkeypatch.setattr(active_checks, "check_utf8", lambda *_args: calls.append("utf8"))
    monkeypatch.setattr(
        active_checks,
        "check_release_evidence",
        lambda _root: calls.append("evidence"),
    )
    monkeypatch.setattr(
        active_checks,
        "check_markdown_basics",
        lambda *_args: calls.append("markdown"),
    )
    monkeypatch.setattr(
        active_checks,
        "check_local_links",
        lambda *_args: calls.append("links"),
    )
    monkeypatch.setattr(
        active_checks,
        "validate_repository_schemas",
        lambda _root: calls.append("schemas"),
    )
    monkeypatch.setattr(
        active_checks,
        "validate_current_state",
        lambda _root: calls.append("state"),
    )
    monkeypatch.setattr(active_checks, "run_repository_audit", lambda _root: calls.append("audit"))
    monkeypatch.setattr(
        active_checks,
        "run",
        lambda command, _root: commands.append(tuple(command)),
    )
    active_checks.verify_fast(tmp_path)
    assert calls == ["utf8", "evidence"]
    assert commands == [
        ("ruff", "check", "src", "tests"),
        ("pytest", "-q"),
        ("git", "diff", "--check"),
    ]
    forbidden = ("git log", "rev-list", "eval-changed", "gate eval", "ssh", "kubectl")
    rendered = "\n".join(" ".join(command).lower() for command in commands)
    assert not any(value in rendered for value in forbidden)
