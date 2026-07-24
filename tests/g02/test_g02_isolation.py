from __future__ import annotations

import copy
from collections import Counter
from pathlib import Path

import pytest

from faultwitness_dev.errors import GovernanceError
from faultwitness_dev.g02_collectors import MemoryProbeBackend
from faultwitness_dev.g02_eval import (
    G02_PHASES,
    PhaseContext,
    PhaseEngine,
    TrialJournal,
    _owned_phase_handlers,
)
from faultwitness_dev.g02_isolation import (
    CANARY_SURFACES,
    DIFFICULTIES,
    FAMILIES,
    G02_WRITERS,
    PRINCIPALS,
    TRACE_STAGES,
    access_cell_contract,
    build_preregistry,
    load_isolation_config,
    prove_writer_canaries,
    reject_package_fixture,
    scan_runtime_packages,
    simulate_identity_policies,
    validate_all_surface_canary,
    validate_live_access_matrix,
    validate_namespace_isolation_manifest,
    validate_policy_observation,
    validate_preregistry,
    validate_public_https_egress,
    validate_stage_matrix,
    validate_writer_payload,
)
from faultwitness_dev.schemas import load_data

ROOT = Path(__file__).resolve().parents[2]
CANDIDATE = "1" * 40
ENVIRONMENT = "2" * 64


def test_preregistry_is_exact_160_rows_without_payloads() -> None:
    rows = build_preregistry()
    validate_preregistry(rows)
    assert len(rows) == 160
    assert [row["case_id"] for row in rows] == [f"CORE-{index:04d}" for index in range(1, 161)]
    assert {row["family"] for row in rows} == set(FAMILIES)
    assert {row["difficulty"] for row in rows} == set(DIFFICULTIES)
    counts = Counter(row["split"] for row in rows)
    assert counts == {"dev": 80, "validation": 40, "locked": 40}
    assert all(
        set(row)
        == {
            "schema_version",
            "case_id",
            "family",
            "split",
            "difficulty",
            "ground_truth_placeholder",
        }
        for row in rows
    )


def test_preregistry_rejects_materialized_case_fixture() -> None:
    fixture = load_data(ROOT / "tests/fixtures/g02/prereg_materialized_case.yaml")
    with pytest.raises(GovernanceError, match="materialized"):
        validate_preregistry(build_preregistry(), fixture["materialized_objects"])


def test_three_runtime_packages_exclude_sealed_material() -> None:
    config = load_isolation_config(ROOT)
    results = scan_runtime_packages(ROOT, config)
    assert [result["role"] for result in results] == list(PRINCIPALS[:3])
    assert all(result["status"] == "pass" for result in results)


def test_package_scan_rejects_ground_truth_fixture() -> None:
    path = ROOT / "tests/fixtures/g02/image_contains_ground_truth.txt"
    with pytest.raises(GovernanceError, match="sealed material"):
        reject_package_fixture(path.name, path.read_text(encoding="utf-8"))


def test_four_identity_policies_include_named_denials() -> None:
    config = load_isolation_config(ROOT)
    results = simulate_identity_policies(config)
    assert [result["principal"] for result in results] == list(PRINCIPALS)
    controller = results[0]["checks"]
    developer = results[3]["checks"]
    assert any(
        "ground-truth" in check["resource"] and check["actual"] is False for check in controller
    )
    assert any(
        "locked-tests" in check["resource"] and check["actual"] is False for check in developer
    )
    namespace_result = validate_namespace_isolation_manifest(ROOT)
    assert namespace_result["credential_objects"] == 0
    assert namespace_result["service_accounts"] == list(PRINCIPALS[:3])
    assert namespace_result["network_policy_count"] == 7
    assert namespace_result["baseline_observability_namespaces"] == [
        "fw-observability",
        "fw-sut",
    ]
    assert namespace_result["observability_ingress"] == "exact-baseline-principal"


def test_public_https_egress_rejects_private_network_fixture() -> None:
    fixture = load_data(ROOT / "tests/fixtures/g02/isolation_broad_private_egress.yaml")
    with pytest.raises(GovernanceError, match="private range"):
        validate_public_https_egress(fixture)


def test_access_wrong_allow_fixture_is_rejected() -> None:
    config = load_isolation_config(ROOT)
    fixture = load_data(ROOT / "tests/fixtures/g02/access_wrong_allow.yaml")
    with pytest.raises(GovernanceError, match="contradicts"):
        validate_policy_observation(config, fixture)


def test_four_new_writer_paths_reject_secret_and_pii() -> None:
    results = prove_writer_canaries(load_isolation_config(ROOT))
    assert [result["writer"] for result in results] == list(G02_WRITERS)
    assert all(result["rejected_canary_classes"] == ["secret", "pii"] for result in results)
    with pytest.raises(GovernanceError, match="rejected"):
        validate_writer_payload({"value": "FW_SECRET_CANARY_must_not_persist"})


def _passing_access_matrix() -> dict[str, object]:
    return {
        "candidate_sha": CANDIDATE,
        "environment_fingerprint": ENVIRONMENT,
        "cells": [
            {
                **cell,
                "actual_allow": cell["expected_allow"],
                "artifact_ref": f"private://access/{index}",
            }
            for index, cell in enumerate(access_cell_contract(), 1)
        ],
    }


def test_access_matrix_runner_contract_is_60_candidate_bound_cells() -> None:
    document = _passing_access_matrix()
    assert validate_live_access_matrix(document, CANDIDATE, ENVIRONMENT)["cell_count"] == 60
    broken = copy.deepcopy(document)
    broken["cells"][0]["actual_allow"] = not broken["cells"][0]["actual_allow"]
    with pytest.raises(GovernanceError, match="access matrix failed"):
        validate_live_access_matrix(broken, CANDIDATE, ENVIRONMENT)
    with pytest.raises(GovernanceError, match="candidate binding"):
        validate_live_access_matrix(document, "3" * 40, ENVIRONMENT)


def _passing_stage_matrix() -> dict[str, object]:
    return {
        "candidate_sha": CANDIDATE,
        "environment_fingerprint": ENVIRONMENT,
        "stages": [
            {
                "stage": stage,
                "trace_id": "a" * 32,
                "observed": True,
                "artifact_ref": f"private://trace/{stage}",
            }
            for stage in TRACE_STAGES
        ],
    }


def test_six_stage_runner_contract_rejects_missing_stage_fixture() -> None:
    document = _passing_stage_matrix()
    assert validate_stage_matrix(document, CANDIDATE, ENVIRONMENT)["stage_count"] == 6
    fixture = load_data(ROOT / "tests/fixtures/g02/trace_missing_stage.json")
    broken = copy.deepcopy(document)
    broken["stages"] = [
        stage for stage in broken["stages"] if stage["stage"] != fixture["missing_stage"]
    ]
    with pytest.raises(GovernanceError, match="lacks"):
        validate_stage_matrix(broken, CANDIDATE, ENVIRONMENT)


def _passing_canary_matrix() -> dict[str, object]:
    return {
        "candidate_sha": CANDIDATE,
        "environment_fingerprint": ENVIRONMENT,
        "surfaces": [
            {
                "surface": surface,
                "hit_count": 0,
                "artifact_ref": f"private://canary/{surface}",
                "canary_digest": f"{index:064x}",
            }
            for index, surface in enumerate(CANARY_SURFACES, 1)
        ],
    }


def test_all_surface_runner_contract_rejects_leaked_fixture() -> None:
    document = _passing_canary_matrix()
    assert validate_all_surface_canary(document, CANDIDATE, ENVIRONMENT)["surface_count"] == 22
    fixture = load_data(ROOT / "tests/fixtures/g02/canary_leaked_artifact.json")
    broken = copy.deepcopy(document)
    index = list(CANARY_SURFACES).index(fixture["surface"])
    broken["surfaces"][index] = fixture
    with pytest.raises(GovernanceError, match="leaked"):
        validate_all_surface_canary(broken, CANDIDATE, ENVIRONMENT)


def test_three_gate_phase_interfaces_write_candidate_bound_artifacts(tmp_path: Path) -> None:
    context = PhaseContext(
        candidate_sha=CANDIDATE,
        runtime_image_digests=("3" * 64,),
        sut_image_set_digest="4" * 64,
        config_digest="5" * 64,
        evaluator_digest="6" * 64,
        dataset_digest="7" * 64,
        environment_fingerprint=ENVIRONMENT,
    )
    engine = PhaseEngine(G02_PHASES, context, tmp_path / "journal")
    handlers = _owned_phase_handlers(
        tmp_path,
        {"_eval_id": "EVAL-G02-010"},
        engine,
        MemoryProbeBackend(ROOT),
    )
    journal = TrialJournal(tmp_path / "journal")
    for phase_id in (
        "isolation-access-matrix",
        "trace-six-stage-matrix",
        "all-surface-canary",
    ):
        result = handlers[phase_id](context, journal)
        assert result["status"] == "pass"
        assert (tmp_path / result["artifact_path"]).is_file()
