from __future__ import annotations

from dataclasses import replace

import pytest
from cryptography.exceptions import InvalidTag

from faultwitness.runtime.checkpoint import CheckpointCipher


def test_checkpoint_round_trip_binds_tenant_and_task() -> None:
    cipher = CheckpointCipher("key-1", b"k" * 32)
    sealed = cipher.seal({"node": "collect", "count": 2}, tenant_id="ten_1", task_id="task_1")

    assert cipher.open(sealed, tenant_id="ten_1", task_id="task_1") == {
        "node": "collect",
        "count": 2,
    }
    with pytest.raises(InvalidTag):
        cipher.open(sealed, tenant_id="ten_2", task_id="task_1")
    with pytest.raises(InvalidTag):
        cipher.open(
            replace(sealed, ciphertext=sealed.ciphertext[:-1] + b"x"),
            tenant_id="ten_1",
            task_id="task_1",
        )


def test_checkpoint_fails_closed_for_unknown_key_or_format() -> None:
    cipher = CheckpointCipher("key-1", b"k" * 32)
    sealed = cipher.seal({}, tenant_id="ten_1", task_id="task_1")

    with pytest.raises(ValueError, match="unknown checkpoint"):
        cipher.open(replace(sealed, key_id="key-2"), tenant_id="ten_1", task_id="task_1")
    with pytest.raises(ValueError, match="unknown checkpoint"):
        cipher.open(replace(sealed, format_version=2), tenant_id="ten_1", task_id="task_1")
