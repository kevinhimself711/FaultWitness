from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from faultwitness_dev.cli import parser
from faultwitness_dev.errors import GovernanceError
from faultwitness_dev.g02_eval import (
    G02_PHASES,
    PhaseContext,
    PhaseDefinition,
    PhaseEngine,
    TrialJournal,
    _owned_phase_handlers,
    inspect_reconciliation,
    run_phase_contract_suite,
    validate_candidate_binding_document,
    validate_gate_orchestration_selection,
    validate_manifest_debt_documents,
    validate_reconciliation_document,
)
from faultwitness_dev.schemas import load_data, validate_document

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "g02"


def _context(candidate: str = "1" * 40) -> PhaseContext:
    return PhaseContext(
        candidate_sha=candidate,
        runtime_image_digests=("2" * 64,),
        sut_image_set_digest="3" * 64,
        config_digest="4" * 64,
        evaluator_digest="5" * 64,
        dataset_digest="6" * 64,
        environment_fingerprint="7" * 64,
    )


def test_v_g02_001_runs_exactly_five_contract_cases(tmp_path: Path) -> None:
    cases = run_phase_contract_suite("1" * 40, tmp_path)
    assert [case["case"] for case in cases] == [
        "dag_and_cache",
        "phase_dependency",
        "resume_infra_failed",
        "from_failed",
        "destructive_once",
    ]
    assert {case["status"] for case in cases} == {"pass"}


def test_stale_cache_fixture_is_not_reused(tmp_path: Path) -> None:
    definition = PhaseDefinition("first", (), "I-0016")
    engine = PhaseEngine((definition,), _context(), tmp_path)
    path = engine.record_path("first")
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(load_data(FIXTURES / "phase_stale_cache.json")), encoding="utf-8")
    calls: list[str] = []

    def handler(_context: PhaseContext, _journal: TrialJournal) -> dict[str, str]:
        calls.append("run")
        return {"status": "pass"}

    [result] = engine.run({"first": handler})
    assert calls == ["run"]
    assert result["cache_key"] == _context().cache_key(definition)


def test_trial_journal_persists_attempts_atomically(tmp_path: Path) -> None:
    journal = TrialJournal(tmp_path)
    first = journal.write("trial-1", "infra_failed", {"reason": "transport"})
    second = journal.write("trial-1", "pass", {"score": 0})
    assert first["attempt"] == 1
    assert second["attempt"] == 2
    assert journal.read("trial-1") == second
    assert not list((tmp_path / "trials").glob("*.tmp"))


def test_owned_l2_negative_fixtures_fail_closed() -> None:
    with pytest.raises(GovernanceError, match="candidate-affecting"):
        validate_candidate_binding_document(
            load_data(FIXTURES / "candidate_non_evidence_descendant.json")
        )
    with pytest.raises(GovernanceError, match="open evidence"):
        validate_manifest_debt_documents(
            {"negative": load_data(FIXTURES / "manifest_open_evidence.json")}
        )
    with pytest.raises(GovernanceError, match="unresolved phase"):
        validate_reconciliation_document(load_data(FIXTURES / "reconciliation_pending.json"))


def test_reconciliation_accepts_only_complete_timestamped_evidence() -> None:
    complete = {
        "open_evidence": [],
        "waivers": [],
        "backlog_count": 0,
        "dlq_count": 0,
        "fallback_count": 0,
        "phases": [
            {
                "phase_id": "scenario-matrix",
                "status": "pass",
                "start_time": "2026-07-23T00:00:00+00:00",
                "end_time": "2026-07-23T00:01:00+00:00",
                "destructive": True,
                "execution_count": 1,
            }
        ],
        "trials": [{"trial_id": "trial-1", "status": "pass"}],
    }
    assert inspect_reconciliation(complete)["status"] == "pass"
    duplicate = copy.deepcopy(complete)
    duplicate["phases"][0]["execution_count"] = 2
    with pytest.raises(GovernanceError, match="execution count"):
        validate_reconciliation_document(duplicate)


def test_frozen_phase_registry_has_fail_fast_order_and_one_destructive_phase() -> None:
    assert len(G02_PHASES) == 14
    assert [phase.phase_id for phase in G02_PHASES[:4]] == [
        "preflight-manifests",
        "preflight-candidate-binding",
        "preflight-static-inheritance",
        "preflight-upstream-g01",
    ]
    assert [phase.phase_id for phase in G02_PHASES if phase.destructive] == ["scenario-matrix"]


def test_forward_orchestration_selects_e008_and_rejects_terminal_i0020() -> None:
    state = {
        "active_gate": "G02",
        "active_gate_status": "in_progress",
        "active_iteration": "I-0023",
    }
    iteration = load_data(ROOT / "governance/iterations/I-0023.yaml")
    iteration["status"] = "in_progress"
    manifest = load_data(ROOT / "docs/evals/EVAL-G02-008/manifest.json")
    plan = (ROOT / "docs/evals/EVAL-G02-008/PLAN.md").read_text(encoding="utf-8")
    assert validate_gate_orchestration_selection(state, iteration, manifest, plan) == (
        "I-0023",
        "EVAL-G02-008",
    )

    terminal = load_data(ROOT / "governance/iterations/I-0020.yaml")
    terminal_state = {**state, "active_iteration": "I-0020"}
    failed_manifest = load_data(ROOT / "docs/evals/EVAL-G02-005/manifest.json")
    failed_plan = (ROOT / "docs/evals/EVAL-G02-005/PLAN.md").read_text(encoding="utf-8")
    with pytest.raises(GovernanceError, match="active standard orchestration"):
        validate_gate_orchestration_selection(
            terminal_state, terminal, failed_manifest, failed_plan
        )


def test_forward_orchestration_rejects_an_incomplete_phase_plan() -> None:
    state = {
        "active_gate": "G02",
        "active_gate_status": "in_progress",
        "active_iteration": "I-0023",
    }
    iteration = load_data(ROOT / "governance/iterations/I-0023.yaml")
    iteration["status"] = "in_progress"
    manifest = load_data(ROOT / "docs/evals/EVAL-G02-008/manifest.json")
    with pytest.raises(GovernanceError, match="complete Gate orchestration"):
        validate_gate_orchestration_selection(state, iteration, manifest, "preflight-manifests")


def test_every_frozen_phase_has_an_owner_implemented_handler(tmp_path: Path) -> None:
    engine = PhaseEngine(G02_PHASES, _context(), tmp_path)
    handlers = _owned_phase_handlers(tmp_path, {}, engine)
    assert set(handlers) == {phase.phase_id for phase in G02_PHASES}


def test_manifest_schema_accepts_legacy_v1_and_requires_complete_v2() -> None:
    schema = load_data(ROOT / "schemas" / "governance" / "eval-manifest.schema.json")
    legacy = load_data(ROOT / "docs" / "evals" / "EVAL-G01-001" / "manifest.json")
    validate_document(legacy, schema, "legacy-v1")
    artifact = "docs/evals/EVAL-G02-001/artifacts/phase-contract.json"
    manifest_v2 = {
        "schema_version": "2.0.0",
        "eval_id": "EVAL-G02-001",
        "gate": "G02",
        "iteration": "I-0016",
        "candidate_sha": "1" * 40,
        "evaluated_revision": "1" * 40,
        "evidence_head_sha": "1" * 40,
        "status": "pass",
        "subject_digests": {"src/faultwitness_dev/g02_eval.py": "2" * 64},
        "environment_fingerprint": "3" * 64,
        "phases": [
            {
                "phase_id": "iteration-contract",
                "status": "pass",
                "start_time": "2026-07-23T00:00:00+00:00",
                "end_time": "2026-07-23T00:00:01+00:00",
                "cache_key": "4" * 64,
                "artifact_digest": "5" * 64,
                "artifact_path": artifact,
                "private_artifact_uri": None,
                "execution_count": 1,
                "inherited_from_manifest": None,
            }
        ],
        "environments": ["local-deterministic"],
        "commands": ["eval-iteration I-0016"],
        "artifacts": [artifact],
        "evidence_urls": [],
        "integrations": {},
        "open_evidence": [],
    }
    validate_document(manifest_v2, schema, "manifest-v2")
    manifest_v2["phases"][0]["end_time"] = None
    with pytest.raises(GovernanceError, match="schema validation failed"):
        validate_document(manifest_v2, schema, "invalid-v2")


def test_cli_freezes_g02_phase_and_continuation_interfaces() -> None:
    parsed = parser().parse_args(
        ["eval-g02", "--candidate-sha", "1" * 40, "--phase", "preflight-manifests"]
    )
    assert parsed.phase == "preflight-manifests"
    assert not parsed.resume
    assert not parsed.from_failed
    resumed = parser().parse_args(["eval-g02", "--candidate-sha", "1" * 40, "--resume"])
    assert resumed.resume
    with pytest.raises(SystemExit):
        parser().parse_args(["eval-g02", "--candidate-sha", "1" * 40, "--resume", "--from-failed"])
