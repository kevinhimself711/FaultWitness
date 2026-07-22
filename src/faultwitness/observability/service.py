"""Trace ingestion and per-sink drain orchestration."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from contextlib import suppress
from typing import Any

from faultwitness.contracts.models import TraceEnvelope
from faultwitness.observability.buffer import DeliverySink
from faultwitness.observability.exporters import ExportFailure, TraceExporter
from faultwitness.observability.sanitizer import SanitizedTrace, TraceSanitizer


class TraceExportService:
    def __init__(
        self,
        store: Any,
        sanitizer: TraceSanitizer,
        exporters: Mapping[DeliverySink, TraceExporter],
    ) -> None:
        expected = set(DeliverySink)
        if set(exporters) != expected:
            raise ValueError("every required trace sink must have exactly one exporter")
        self.store = store
        self.sanitizer = sanitizer
        self.exporters = dict(exporters)

    async def ingest(self, envelope: TraceEnvelope) -> tuple[SanitizedTrace, bool]:
        trace = self.sanitizer.sanitize(envelope)
        created = await self.store.enqueue(trace)
        return trace, created

    async def drain_once(self, *, per_sink_limit: int = 10) -> dict[str, int]:
        result = {"acked": 0, "retried": 0}
        for sink in DeliverySink:
            deliveries = await self.store.claim(sink, limit=per_sink_limit)
            for delivery in deliveries:
                try:
                    await self.exporters[sink].export(delivery.trace)
                except ExportFailure as error:
                    await self.store.retry(delivery.trace.trace_ref, sink, error.code)
                    result["retried"] += 1
                except Exception:
                    # Unknown details never enter the durable buffer or public output.
                    await self.store.retry(
                        delivery.trace.trace_ref, sink, "unexpected_export_error"
                    )
                    result["retried"] += 1
                else:
                    await self.store.acknowledge(delivery.trace.trace_ref, sink)
                    result["acked"] += 1
        return result

    async def drain_until_idle(
        self, *, max_rounds: int = 100, per_sink_limit: int = 10
    ) -> dict[str, int]:
        totals = {"acked": 0, "retried": 0}
        for _ in range(max_rounds):
            result = await self.drain_once(per_sink_limit=per_sink_limit)
            totals = {key: totals[key] + result[key] for key in totals}
            status = await self.store.status()
            if status["traces"] == 0 or result["acked"] + result["retried"] == 0:
                break
        return totals


async def run_drain_loop(
    service: TraceExportService, stop: asyncio.Event, *, interval_seconds: float = 1.0
) -> None:
    while not stop.is_set():
        await service.drain_once()
        with suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
