from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pytest

from faultwitness_dev.experiment import (
    ExperimentRunner,
    ExperimentUnit,
    TrialJournal,
)
from faultwitness_dev.g02_baselines import score_result

ROOT = Path(__file__).resolve().parents[2]


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
