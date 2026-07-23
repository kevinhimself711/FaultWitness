from __future__ import annotations

from typing import Any

from faultwitness.runtime.streams import RedisEventStream


class FakeRedis:
    def __init__(self) -> None:
        self.acked: list[str] = []
        self.pending = 0

    def xgroup_create(self, *_: Any, **__: Any) -> None:
        return None

    def xadd(self, stream: str, fields: dict[str, Any]) -> str:
        assert stream == "events"
        assert fields["event_id"] == "evt_1"
        return "1-0"

    def xreadgroup(self, *_: Any, **__: Any) -> list[Any]:
        return [
            [
                b"events",
                [
                    [
                        b"1-0",
                        {b"event_id": b"evt_1", b"tenant_id": b"ten_1", b"payload": b'{"ok":true}'},
                    ]
                ],
            ]
        ]

    def xautoclaim(self, *_: Any, **__: Any) -> list[Any]:
        return [
            b"0-0",
            [[b"1-0", {b"event_id": b"evt_1", b"tenant_id": b"ten_1", b"payload": b'{"ok":true}'}]],
        ]

    def xack(self, _stream: str, _group: str, stream_id: str) -> None:
        self.acked.append(stream_id)

    def xinfo_groups(self, _stream: str) -> list[dict[str, Any]]:
        return [{"name": b"workers", "pending": self.pending}]


def test_at_least_once_receive_recover_ack_and_readiness() -> None:
    client = FakeRedis()
    stream = RedisEventStream(client, "events", "workers", "worker-1")  # type: ignore[arg-type]

    stream.ensure_group()
    assert stream.publish("evt_1", "ten_1", {"ok": True}) == "1-0"
    assert stream.receive()[0].payload == {"ok": True}
    assert stream.recover(1000)[0].event_id == "evt_1"
    stream.acknowledge("1-0")
    assert client.acked == ["1-0"]
    assert stream.ready(0)
    client.pending = 2
    assert not stream.ready(1)
