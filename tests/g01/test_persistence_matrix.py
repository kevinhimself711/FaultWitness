from __future__ import annotations

import copy
import json
from contextlib import AbstractContextManager
from types import TracebackType
from typing import Any

import pytest

from faultwitness.persistence.postgres import PostgresStateStore
from faultwitness.state.kernel import TransitionDecision

TENANT = "ten_01ARZ3NDEKTSV4RRFFQ69G5FAV"


class FaultConnection:
    def __init__(self) -> None:
        self.state: dict[str, Any] = {
            "aggregates": {},
            "outbox": {},
            "idempotency": {},
            "inbox": set(),
        }
        self.fail_mutation: int | None = None
        self.mutations = 0
        self._snapshot: dict[str, Any] | None = None

    def transaction(self) -> AbstractContextManager[None]:
        connection = self

        class Transaction(AbstractContextManager[None]):
            def __enter__(self) -> None:
                connection._snapshot = (
                    copy.deepcopy(connection.state)
                    if connection.fail_mutation is not None
                    else None
                )

            def __exit__(
                self,
                exc_type: type[BaseException] | None,
                exc_value: BaseException | None,
                traceback: TracebackType | None,
            ) -> bool:
                if exc_type is not None and connection._snapshot is not None:
                    connection.state = connection._snapshot
                connection._snapshot = None
                return False

        return Transaction()

    def cursor(self) -> FaultConnection:
        return self

    def __enter__(self) -> FaultConnection:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def _mutate(self) -> None:
        self.mutations += 1
        if self.fail_mutation == self.mutations:
            raise RuntimeError("injected database failure")

    def execute(self, statement: str, parameters: tuple[Any, ...]) -> None:
        normalized = " ".join(statement.split())
        self.rowcount = 0
        self._row: tuple[Any, ...] | None = None
        if normalized.startswith("SELECT request_digest"):
            tenant_id, key = parameters
            prior = self.state["idempotency"].get((tenant_id, key))
            self._row = prior
            return
        if "aggregate_state" in normalized and normalized.startswith("INSERT"):
            self._mutate()
            tenant_id, aggregate_id, machine, state, version, previous = parameters
            slot = (tenant_id, aggregate_id)
            current = self.state["aggregates"].get(slot)
            if current is None or current[2] == previous:
                self.state["aggregates"][slot] = (machine, state, version)
                self.rowcount = 1
            return
        if ".outbox" in normalized and normalized.startswith("INSERT"):
            self._mutate()
            outbox_id, tenant_id, aggregate_id, event_id, event_type, payload = parameters
            self.state["outbox"][outbox_id] = (
                tenant_id,
                aggregate_id,
                event_id,
                event_type,
                json.loads(payload),
            )
            self.rowcount = 1
            return
        if ".idempotency" in normalized and normalized.startswith("INSERT"):
            self._mutate()
            tenant_id, key, digest, response = parameters
            self.state["idempotency"][(tenant_id, key)] = (digest, json.loads(response))
            self.rowcount = 1
            return
        if "runtime_shared.inbox" in normalized:
            self._mutate()
            slot = tuple(parameters)
            if slot not in self.state["inbox"]:
                self.state["inbox"].add(slot)
                self.rowcount = 1
            return
        raise AssertionError(f"unexpected SQL: {normalized}")

    def fetchone(self) -> tuple[Any, ...] | None:
        return self._row


def _decision(index: int) -> TransitionDecision:
    return TransitionDecision(
        machine_id="incident",
        owner_component="CMP-CONTROL-API",
        transition_id="TR-INCIDENT-CREATE",
        actor="authenticated edge",
        aggregate_id=f"inc_matrix_{index}",
        previous_state="ABSENT",
        next_state="NEW",
        previous_state_version=0,
        next_state_version=1,
        command="CMD-CREATE-INCIDENT",
        event="EVT-INCIDENT-CREATED",
        schema_version="1.1.0",
        automatic=False,
        idempotency_key=f"matrix-key-{index}",
        request_digest=f"{index:064x}",
        evaluated_predicates=("guard:TR-INCIDENT-CREATE",),
        decision_digest=f"{index + 1:064x}",
    )


def test_one_hundred_crash_injections_never_partially_commit_state_outbox() -> None:
    for index in range(100):
        connection = FaultConnection()
        connection.fail_mutation = index % 3 + 1
        store = PostgresStateStore(connection, "incident_owner")
        before = copy.deepcopy(connection.state)
        with pytest.raises(RuntimeError, match="injected database failure"):
            store.apply_transition(
                _decision(index),
                tenant_id=TENANT,
                event_id=f"evt_{index}",
                outbox_id=f"outbox_{index}",
            )
        assert connection.state == before


def test_ten_thousand_duplicate_deliveries_mutate_inbox_once_per_event() -> None:
    connection = FaultConnection()
    store = PostgresStateStore(connection, "incident_owner")
    first_delivery_count = 0
    for index in range(5_000):
        event_id = f"evt_{index:05d}"
        first_delivery_count += store.record_inbox(
            tenant_id=TENANT, consumer="matrix", event_id=event_id
        )
        first_delivery_count += store.record_inbox(
            tenant_id=TENANT, consumer="matrix", event_id=event_id
        )
    assert first_delivery_count == 5_000
    assert len(connection.state["inbox"]) == 5_000
