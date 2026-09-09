from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

from faultwitness_dev.experiment import ExperimentRunner, ExperimentUnit, TrialJournal
from faultwitness_dev.infra import _remote_process

ROOT = Path(__file__).resolve().parents[2]


def _tracked_tree_fingerprint() -> str:
    diff = subprocess.run(
        ["git", "diff", "--binary", "HEAD", "--", "."],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout
    return hashlib.sha256(diff).hexdigest()


def _invoke(value: str) -> str:
    result = _remote_process(
        subprocess.run,
        [sys.executable, "-c"],
        "import sys; print(sys.stdin.buffer.read().hex())",
        value,
    )
    assert result.returncode == 0
    return result.stdout.strip()


def test_infra_child_process_transport_is_byte_exact() -> None:
    payload = "set -eu\nprintf '跨平台-ok'\n"
    assert _invoke(payload) == payload.encode("utf-8").hex()


def test_infra_direct_debug_campaign_is_byte_exact(tmp_path: Path) -> None:
    before = _tracked_tree_fingerprint()
    unit = ExperimentUnit("infra-bytes", ("transport",), (), "stdin-byte-contract")
    journal = TrialJournal(tmp_path)
    payload = "set -eu\nprintf 'cross-platform-ok'\n"

    def crlf_mutant(_execution):  # type: ignore[no-untyped-def]
        observed = _invoke(payload.replace("\n", "\r\n"))
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
        observed = _invoke(payload)
        assert observed == payload.encode().hex()
        return {"status": "pass", "payload": {"byte_exact": True}}

    repaired = ExperimentRunner(
        (unit,), journal, {"transport": "utf8-bytes"}, producer_sha="2" * 40
    ).run({unit.unit_id: bytes_fixed})
    assert repaired.executed_units == (unit.unit_id,)
    assert journal.read(unit.unit_id)["execution_attempt"] == 2  # type: ignore[index]
    assert _tracked_tree_fingerprint() == before
