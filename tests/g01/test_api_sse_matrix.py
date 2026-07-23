from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from faultwitness.api.schemas import FeedbackRequest, IncidentCreate
from faultwitness.api.store import MemoryIncidentStore, RetentionGap

TENANT = "ten_01ARZ3NDEKTSV4RRFFQ69G5FAV"


def _incident() -> IncidentCreate:
    now = datetime.now(UTC)
    return IncidentCreate.model_validate(
        {
            "source": "synthetic-matrix",
            "environment_id": "env_test",
            "service_scope": ["svc_api"],
            "time_window": {
                "start": (now - timedelta(minutes=5)).isoformat(),
                "end": now.isoformat(),
            },
            "symptom_summary": "synthetic SSE matrix",
            "mode": "diagnosis_only",
            "budget": {
                "deadline": (now + timedelta(minutes=10)).isoformat(),
                "max_steps": 10,
                "max_model_calls": 3,
                "max_tokens": 2000,
                "max_cost_usd": 1.0,
            },
        }
    )


def test_ten_thousand_events_and_one_hundred_reconnects_are_exact() -> None:
    async def scenario() -> None:
        store = MemoryIncidentStore(retention_count=10_000)
        snapshot, _ = await store.create(TENANT, "create-matrix", _incident())
        request = FeedbackRequest(rating=5, expected_state_version=0)
        for index in range(9_999):
            await store.feedback(
                TENANT,
                "usr_synthetic",
                snapshot.incident_id,
                f"feedback-{index:05d}",
                request,
            )

        all_events = await store.replay(TENANT, snapshot.incident_id, None)
        assert len(all_events) == 10_000
        assert [event.sequence for event in all_events] == list(range(1, 10_001))
        assert len({event.event_id for event in all_events}) == 10_000

        delivered: list[int] = []
        cursor = 0
        for _ in range(100):
            replay = await store.replay(TENANT, snapshot.incident_id, str(cursor))
            batch = replay[:100]
            delivered.extend(event.sequence for event in batch)
            cursor = batch[-1].sequence
        assert delivered == list(range(1, 10_001))
        assert cursor == 10_000

    asyncio.run(scenario())


def test_retention_gap_and_slow_consumer_fail_without_blocking_publisher() -> None:
    async def scenario() -> None:
        store = MemoryIncidentStore(retention_count=3)
        snapshot, _ = await store.create(TENANT, "create-retention", _incident())
        subscriber = await store.subscribe(TENANT, snapshot.incident_id, buffer_size=1)
        request = FeedbackRequest(rating=4, expected_state_version=0)
        for index in range(4):
            await store.feedback(
                TENANT,
                "usr_synthetic",
                snapshot.incident_id,
                f"retention-{index}",
                request,
            )
        assert subscriber.closed is True
        with pytest.raises(RetentionGap) as captured:
            await store.replay(TENANT, snapshot.incident_id, "0")
        assert captured.value.earliest_cursor == "3"
        retained = await store.replay(TENANT, snapshot.incident_id, "2")
        assert [event.sequence for event in retained] == [3, 4, 5]

    asyncio.run(scenario())
