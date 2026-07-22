"""Redis Streams at-least-once delivery with explicit pending and poison semantics."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from redis import Redis


@dataclass(frozen=True, slots=True)
class StreamMessage:
    stream_id: str
    event_id: str
    tenant_id: str
    payload: dict[str, Any]


class RedisEventStream:
    def __init__(self, client: Redis, stream: str, group: str, consumer: str) -> None:
        self.client = client
        self.stream = stream
        self.group = group
        self.consumer = consumer

    def ensure_group(self) -> None:
        try:
            self.client.xgroup_create(self.stream, self.group, id="0", mkstream=True)
        except Exception as error:
            if "BUSYGROUP" not in str(error):
                raise

    def publish(self, event_id: str, tenant_id: str, payload: dict[str, Any]) -> str:
        return str(
            self.client.xadd(
                self.stream,
                {"event_id": event_id, "tenant_id": tenant_id, "payload": json.dumps(payload)},
            )
        )

    def receive(self, count: int = 10, block_ms: int = 1000) -> list[StreamMessage]:
        batches = self.client.xreadgroup(
            self.group, self.consumer, {self.stream: ">"}, count=count, block=block_ms
        )
        return self._decode(batches)

    def recover(self, minimum_idle_ms: int, count: int = 10) -> list[StreamMessage]:
        result = self.client.xautoclaim(
            self.stream, self.group, self.consumer, minimum_idle_ms, start_id="0-0", count=count
        )
        entries = result[1]
        return self._decode([(self.stream, entries)])

    def acknowledge(self, stream_id: str) -> None:
        self.client.xack(self.stream, self.group, stream_id)

    def ready(self, maximum_pending: int) -> bool:
        groups = self.client.xinfo_groups(self.stream)
        group = next((item for item in groups if _text(item.get("name")) == self.group), None)
        return group is not None and int(group.get("pending", 0)) <= maximum_pending

    @staticmethod
    def _decode(batches: list[Any]) -> list[StreamMessage]:
        messages: list[StreamMessage] = []
        for _, entries in batches:
            for stream_id, fields in entries:
                normalized = {_text(key): _text(value) for key, value in fields.items()}
                payload = json.loads(normalized["payload"])
                if not isinstance(payload, dict):
                    raise ValueError("stream payload must be an object")
                messages.append(
                    StreamMessage(
                        _text(stream_id), normalized["event_id"], normalized["tenant_id"], payload
                    )
                )
        return messages


def _text(value: Any) -> str:
    return value.decode() if isinstance(value, bytes) else str(value)
