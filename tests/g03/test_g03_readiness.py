from __future__ import annotations  # metric-v3 frozen contract

import copy
import hashlib
import inspect
import json
from collections.abc import Mapping
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator as RealDraft202012Validator

import faultwitness_dev.g03_readiness as readiness
from faultwitness_dev.errors import GovernanceError
from faultwitness_dev.g02_baselines import (
    _gate_trial_specs,
    require_g02_metric_version,
    wire_schema_for_metric,
)
from faultwitness_dev.g02_lab import V3_TRACE_QUERY_SERVICES
from faultwitness_dev.g03_readiness import (
    EVIDENCE_KINDS,
    REQUIRED_KINDS,
    RESULT_SCHEMA_V3,
    ROOT_CAUSE_LABELS,
    ROOT_SIGNAL_FEATURES,
    TARGET_SERVICES,
    LiveTrialFailure,
    _assert_resume_identity_v3,
    _digest_json,
    _preflight_blockers_v3,
    _run_live_trials_v3,
    _validate_output_dir_v3,
    aggregate_reference_v3,
    build_baseline_prompt_v3,
    build_deterministic_thresholds_v3,
    build_observation_packet_v3,
    build_version_routing_inventory,
    dataset_digest_v3,
    evidence_id_v3,
    four_turn_input_upper_bound_v3,
    ground_truth_v3,
    inherit_passing_trials_v3,
    load_baseline_config_v3,
    metric_definition_v3,
    paired_cluster_bootstrap_v3,
    presence_only_probe_v3,
    replay_all_scenarios_v3,
    run_deterministic_matrix_v3,
    run_retest_baselines_v3,
    scenario_cases_v3,
    score_result_v3,
    should_extend_reference_v3,
    token_preflight_v3,
    trial_specs_v3,
    validate_observation_packet_v3,
    validate_result_v3,
    wire_schema_for_v3,
    write_json_artifact_v3,
)

LABELS = [
    *(["kafkaQueueProblems"] * 8),
    *(["productCatalogFailure"] * 8),
    *(["adHighCpu"] * 4),
    *(["emailMemoryLeak"] * 4),
    *(["paymentFailure"] * 4),
    *(["paymentUnreachable"] * 4),
]
SEVEN_PACKET_STRUCTURE = (
    Path(__file__).parents[1]
    / "fixtures"
    / "g03"
    / "metric-v3-seven-packet-structure.json"
)


def test_landed_seven_packets_preserve_one_presence_signature_and_opaque_ids() -> None:
    fixture = json.loads(SEVEN_PACKET_STRUCTURE.read_text(encoding="utf-8"))
    cases = fixture["cases"]
    assert fixture["structural_facts_only"] is True
    assert len(cases) == 7
    signatures = {tuple(sorted(case["evidence"])) for case in cases}
    assert signatures == {tuple(sorted(EVIDENCE_KINDS))}
    assert all(case["sample_count_per_group"] == 7 for case in cases)
    for kind in EVIDENCE_KINDS:
        ids = {case["evidence"][kind] for case in cases}
        assert len(ids) == 7
        assert all(not evidence.startswith("EVID-0") for evidence in ids)
    assert all(
        evidence == evidence_id_v3(case["case_id"], kind)
        for case in cases
        for kind, evidence in case["evidence"].items()
    )


def test_collector_v2_checkpoint_forces_every_legacy_journal_to_rerun(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = Path(__file__).parents[2]
    journal = readiness.TrialJournal(tmp_path / "copied-old-journal")
    producer_sha = "1" * 40
    sut_producer_sha = "2" * 40
    for case in _scenario_document()["trials"]:
        case_id = str(case["payload"]["scenario_id"])
        trial_id = f"g03-readiness-v3-scenario-{case_id.casefold()}"
        journal.begin(
            trial_id,
            producer_sha=producer_sha,
            cache_key="collector-v1-cache-key",
            payload={"scenario_id": case_id},
        )
        journal.finish(trial_id, "pass", {"legacy": True})

    executed: list[str] = []

    def fake_run(
        scenario: Mapping[str, object],
        _client: object,
        _observer: object,
        *,
        metric_version: int,
    ) -> dict[str, object]:
        assert metric_version == 3
        case_id = str(scenario["scenario_id"])
        executed.append(case_id)
        fixture_case = next(
            case
            for case in _scenario_document()["trials"]
            if case["payload"]["scenario_id"] == case_id
        )
        return {
            "scenario_id": case_id,
            "family": scenario["family"],
            "fault_class": fixture_case["payload"]["fault_class"],
            "observation_packet": fixture_case["payload"]["observation_packet"],
        }

    monkeypatch.setattr(readiness, "run_readiness_scenario_v3", fake_run)
    result = replay_all_scenarios_v3(
        root,
        producer_sha,
        journal,
        sut_producer_sha=sut_producer_sha,
        client_factory=lambda _sha: object(),
        observer_factory=lambda _sha, _fault_class: object(),
    )

    assert result["status"] == "pass"
    assert result["scenario_count"] == 32
    assert len(executed) == 32
    assert len(set(executed)) == 32
    for case_id in executed:
        record = journal.read(f"g03-readiness-v3-scenario-{case_id.casefold()}")
        assert record is not None
        assert record["execution_attempt"] == 2
        assert record["history"][0]["cache_key"] == "collector-v1-cache-key"


def _window(label: str, phase: str, index: int) -> dict[str, object]:
    activity = {service: 10 for service in V3_TRACE_QUERY_SERVICES}
    errors = {
        service: {
            "error_count": 0,
            "connection_error_count": 0,
            "descriptions": [],
        }
        for service in V3_TRACE_QUERY_SERVICES
    }
    cpu = 0.01
    memory = 10_000.0
    lag = 0.01
    if phase == "fault":
        target = TARGET_SERVICES[label]
        activity[target] += 5
        if label == "productCatalogFailure":
            errors[target]["error_count"] = 3
            errors[target]["descriptions"] = ["catalog request failed"]
        elif label == "paymentFailure":
            errors[target]["error_count"] = 3
            errors[target]["descriptions"] = ["payment rejected"]
        elif label == "paymentUnreachable":
            errors[target]["connection_error_count"] = 3
            errors[target]["descriptions"] = ["connection unavailable"]
        elif label == "adHighCpu":
            cpu += 0.1
        elif label == "emailMemoryLeak":
            memory += 100.0 + index
        elif label == "kafkaQueueProblems":
            lag += 1.0
    return {
        "recorded_at": f"2026-07-28T00:00:{index:02d}+00:00",
        "ready": True,
        "journey_status": 200,
        "cpu_rate": cpu,
        "working_set": memory,
        "consumer_lag": lag,
        "consumer_record_lag": lag,
        "consumer_poll_lag_seconds": lag,
        "trace_activity": activity,
        "trace_errors": errors,
    }


def _scenario_document() -> dict[str, object]:
    trials = []
    for index, label in enumerate(LABELS, 1):
        scenario = {
            "scenario_id": f"SEED-G02-{index:04d}",
            "family": f"family-{label}",
            "problem_brief": "Diagnose the incident from the public packet.",
        }
        packet = build_observation_packet_v3(
            scenario,
            [_window(label, "healthy", item) for item in range(5)],
            [_window(label, "fault", item) for item in range(2)],
        )
        trials.append(
            {
                "status": "pass",
                "payload": {
                    "scenario_id": scenario["scenario_id"],
                    "fault_class": label,
                    "family": scenario["family"],
                    "observation_packet": packet,
                },
            }
        )
    return {
        "status": "pass",
        "metric_version": 3,
        "scenario_count": 32,
        "trials": trials,
    }


def _valid_result(case: Mapping[str, object], *, correct: bool = True) -> dict[str, object]:
    truth = case["ground_truth"]
    assert isinstance(truth, Mapping)
    expected = str(truth["root_cause"])
    actual = (
        expected if correct else next(label for label in ROOT_CAUSE_LABELS if label != expected)
    )
    evidence = list(truth["required_evidence"])
    return {
        "schema_version": "2.0.0",
        "metric_version": 3,
        "case_id": truth["case_id"],
        "status": "ok",
        "root_cause": actual,
        "root_cause_candidates": [actual],
        "evidence": evidence,
        "claims": [
            {
                "claim_type": "root_cause",
                "value": actual,
                "evidence_refs": evidence,
            }
        ],
    }


def _reference_documents(
    scenarios: Mapping[str, object],
    deterministic_pass: set[int],
    no_rag_pass: set[int],
    naive_pass: set[int],
) -> tuple[dict[str, object], dict[str, object]]:
    cases = scenario_cases_v3(scenarios)
    deterministic_rows = []
    live_trials = []
    ordered = sorted(cases)
    for index, case_id in enumerate(ordered):
        passed = index in deterministic_pass
        deterministic_rows.append(
            {
                "case_id": case_id,
                "family": cases[case_id]["family"],
                "ground_truth_access": False,
                "core_e2e": 1.0 if passed else 0.0,
                "root_cause_top3": 1.0 if passed else 0.0,
                "evidence_precision": 1.0 if passed else 0.0,
                "unsupported_critical_claim": 0.0 if passed else 1.0,
                "result": _valid_result(cases[case_id], correct=passed),
            }
        )
        for baseline, pass_set in (
            ("no_rag", no_rag_pass),
            ("naive_react", naive_pass),
            ("naive_react_single", naive_pass),
        ):
            for repetition in range(1, 4):
                live_trials.append(
                    {
                        "trial_id": f"{baseline}-{case_id}-{repetition}",
                        "baseline": baseline,
                        "case_id": case_id,
                        "repetition": repetition,
                        "status": "pass",
                        "fallback_count": 0,
                        "input_tokens": 1,
                        "output_tokens": 1,
                        "cost_cny": 0.0,
                        "failure_class": None,
                        "trial_telemetry": {},
                        "result": _valid_result(
                            cases[case_id],
                            correct=index in pass_set,
                        ),
                    }
                )
    return (
        {
            "status": "pass",
            "metric_version": 3,
            "rows": deterministic_rows,
        },
        {
            "status": "pass",
            "metric_version": 3,
            "repetitions": 3,
            "trials": live_trials,
        },
    )


def test_v3_packet_structure_presence_prior_and_kind_truth_are_order_invariant() -> None:
    document = _scenario_document()
    cases = scenario_cases_v3(document)
    probe = presence_only_probe_v3(document)

    assert len(cases) == 32
    assert probe["signature_count"] == 1
    assert (probe["top1_count"], probe["top3_count"]) == (8, 20)
    for case_id, case in cases.items():
        packet = case["packet"]
        assert {item["kind"] for item in packet["observations"]} == set(EVIDENCE_KINDS)
        assert all(len(item["samples"]) == 7 for item in packet["observations"])
        assert [window["phase"] for window in packet["windows"]] == ["healthy"] * 5 + ["fault"] * 2
        assert all(
            "recorded_at" not in sample and "phase" not in sample and "window" not in sample
            for group in packet["observations"]
            for sample in group["samples"]
        )
        assert len(case["ground_truth"]["required_evidence"]) >= 2
        assert case["nonzero_distractor_kinds"]
        assert all(evidence_id_v3(case_id, kind).startswith("ev3-") for kind in EVIDENCE_KINDS)

    first = copy.deepcopy(document["trials"][0]["payload"]["observation_packet"])
    truth_before = ground_truth_v3(first["case_id"], LABELS[0])
    first["observations"].reverse()
    subject = {key: value for key, value in first.items() if key != "packet_digest"}
    first["packet_digest"] = _digest_json(subject)
    validate_observation_packet_v3(first)
    assert ground_truth_v3(first["case_id"], LABELS[0]) == truth_before


def test_v3_dataset_fails_closed_when_a_distractor_supports_another_root() -> None:
    document = _scenario_document()
    packet = document["trials"][8]["payload"]["observation_packet"]
    assert document["trials"][8]["payload"]["fault_class"] == "productCatalogFailure"
    for group in packet["observations"]:
        if group["kind"] == "trace_activity":
            for sample in group["samples"][-2:]:
                sample["services"]["ad"]["trace_count"] += 5
        if group["kind"] == "cpu_window":
            for sample in group["samples"][-2:]:
                sample["cpu_cores"] += 0.1
    subject = {key: value for key, value in packet.items() if key != "packet_digest"}
    packet["packet_digest"] = _digest_json(subject)

    matrix = run_deterministic_matrix_v3("1" * 40, document, dataset_digest_v3(document))
    assert matrix["status"] == "diagnostic_only"
    assert matrix["ambiguity_count"] == 1
    assert matrix["ambiguity_case_ids"] == ["SEED-G02-0009"]
    assert matrix["N"] == 31


def test_v3_scorer_classifies_every_negative_path_for_all_32_cases() -> None:
    cases = scenario_cases_v3(_scenario_document())
    for case in cases.values():
        truth = case["ground_truth"]
        valid = _valid_result(case)
        assert score_result_v3(valid, truth)["core_e2e"] == 1.0

        malformed = copy.deepcopy(valid)
        malformed.pop("claims")
        assert score_result_v3(malformed, truth)["failure_class"] == "malformed"

        invalid = copy.deepcopy(valid)
        invalid["root_cause"] = "notAClosedLabel"
        invalid["root_cause_candidates"] = ["notAClosedLabel"]
        invalid["claims"][0]["value"] = "notAClosedLabel"
        assert score_result_v3(invalid, truth)["failure_class"] == "invalid_label"

        unknown = copy.deepcopy(valid)
        unknown["evidence"] = ["ev3-unknown"]
        unknown["claims"][0]["evidence_refs"] = ["ev3-unknown"]
        assert score_result_v3(unknown, truth)["failure_class"] == "unknown_evidence"

        missing = copy.deepcopy(valid)
        missing["evidence"] = missing["evidence"][:1]
        missing["claims"][0]["evidence_refs"] = missing["evidence"]
        assert score_result_v3(missing, truth)["failure_class"] == "missing_required_evidence"

        distractor = copy.deepcopy(valid)
        distractor["evidence"].append(truth["distractor_evidence"][0])
        distractor["claims"][0]["evidence_refs"] = distractor["evidence"]
        assert score_result_v3(distractor, truth)["failure_class"] == "distractor_evidence"

        mismatched_case = copy.deepcopy(valid)
        mismatched_case["case_id"] = "SEED-G02-9999"
        assert score_result_v3(mismatched_case, truth)["failure_class"] == "case_id_mismatch"

        mismatched_refs = copy.deepcopy(valid)
        mismatched_refs["claims"][0]["evidence_refs"] = mismatched_refs["evidence"][:1]
        assert score_result_v3(mismatched_refs, truth)["failure_class"] == "claim_contract"


def test_v3_deterministic_uses_only_healthy_loo_statistics_and_fixed_quanta() -> None:
    document = _scenario_document()
    registry = build_deterministic_thresholds_v3(document)
    source = inspect.getsource(build_deterministic_thresholds_v3)

    # memory_bytes is 4096, not 1: working_set_bytes is page-granular. Every one of the 224 memory
    # samples in r5 was an exact multiple of 4096 and their GCD was exactly one page, so a declared
    # quantum of 1 byte overstated the counter's resolution by 4096x.
    assert registry["quanta"] == {
        "count": 1,
        "cpu_cores": 0.000001,
        "memory_bytes": 4096,
        "lag_seconds": 0.001,
    }
    assert registry["percentile"] == 0.99
    assert "AD_CPU_ACTIVE" not in source
    assert "EMAIL_MEMORY_MIN_GROWTH" not in source
    for per_label in registry["cases"].values():
        for label in ROOT_CAUSE_LABELS:
            assert per_label[label]["features"]["trace_activity"]["healthy_drift_count"] == 31 * 4
            assert per_label[label]["features"]["root_signal"]["healthy_drift_count"] == 31 * 4


def test_v3_candidate_rule_admits_an_excess_that_exactly_reaches_the_cutoff() -> None:
    """The quantum term in the threshold carries the strictness; `>` charged it twice.

    The cutoff is `healthy_p99 + measurement_quantum`, so reaching it already means the excess
    exceeds observed healthy noise by at least one minimum resolvable unit. Demanding a strict
    inequality on top of that discarded a genuine one-count signal on an integer counter.
    """
    source = inspect.getsource(readiness.deterministic_candidates_v3)
    assert "excess >= cutoff" in source
    assert "excess > cutoff" not in source

    document = _scenario_document()
    registry = build_deterministic_thresholds_v3(document)
    assert ">=" in registry["candidate_rule"]

    # An excess exactly equal to the cutoff must qualify.
    case_id, per_label = next(iter(registry["cases"].items()))
    label = ROOT_CAUSE_LABELS[0]
    cutoff = float(per_label[label]["features"]["trace_activity"]["threshold"])
    assert cutoff >= float(per_label[label]["features"]["trace_activity"]["quantum"])


def test_v3_host_identity_records_the_machine_without_leaking_how_to_reach_it() -> None:
    """ADR-0017 obliges recording the producing host; the address must never be recorded.

    The original host was silently corrupting execution, so evidence from it is not comparable
    with evidence from the replacement -- yet the run manifest carried `producer_sha` and the
    checkpoint identities and nothing about the machine. What closes that gap is a digest of the
    host's SSH *public* key: non-secret by construction, stable across reboots, and distinct per
    machine. The `known_hosts` first field is the host address and is excluded on purpose.

    This pins both halves: the field exists, and it never carries an address, port, username or
    raw key material. It must also never fail a run -- a checkout with no bootstrap store records
    `unavailable`.
    """
    source = inspect.getsource(readiness.host_identity_v3)
    # The address field must never enter the digest.
    assert "fields[0]" not in source.split("# fields[0]")[-1].split("keys.append")[-1]
    assert "fields[1]" in source and "fields[2]" in source

    identity = readiness.host_identity_v3()
    assert set(identity) == {"host_key_digest", "runner_kernel"}
    digest = identity["host_key_digest"]
    assert digest == "unavailable" or (
        len(digest) == 64 and all(char in "0123456789abcdef" for char in digest)
    )

    # A synthetic known_hosts proves the address and key bytes stay out of the output.
    address = "203.0.113.7"
    key_material = "AAAAC3NzaC1lZDI1NTE5AAAAIExampleKeyMaterialForTestOnly"
    line = f"{address} ssh-ed25519 {key_material}"
    digest_of_key = hashlib.sha256(f"ssh-ed25519 {key_material}".encode()).hexdigest()
    assert address not in digest_of_key
    assert key_material not in digest_of_key
    # The helper hashes exactly keytype + key, never the address field.
    assert line.split()[1:3] == ["ssh-ed25519", key_material]

    # Host identity must not be part of the resume identity contract: a differing runner kernel
    # is environmental and would refuse resumes for reasons unrelated to the measurement.
    resume_source = inspect.getsource(readiness._assert_resume_identity_v3)
    assert "host_identity" not in resume_source


def test_v3_prompt_states_the_evidence_completeness_the_scorer_enforces() -> None:
    """The prompt must ask for a complete evidence set, because `core_e2e` requires one.

    r8 measured the cost of leaving this implicit: all three live arms scored 0.125-0.167 while
    naming the correct root cause in 94.8-96.9% of trials. `REQUIRED_KINDS` pairs `trace_activity`
    with a label-specific kind for every label, so it is required in all 32 cases -- and the arms
    cited it in only 16/96, 18/96 and 13/96 trials. The prompt asked for IDs that "directly
    support" the diagnosis, never that the set be complete, and its shape example carried a single
    ID. `deterministic_baseline_v3` builds its evidence straight from `REQUIRED_KINDS`, so the
    comparison arm never had to infer the convention the live arms were scored against.

    This pins the instruction, not a score. It deliberately does not assert that any evidence kind
    is named in the prompt: naming `trace_activity` would hand the live arms the deterministic
    arm's answer key and destroy the inference the metric exists to measure.
    """
    document = _scenario_document()
    case = scenario_cases_v3(document)[sorted(scenario_cases_v3(document))[0]]

    for baseline in ("no_rag", "naive_react", "naive_react_single"):
        system = build_baseline_prompt_v3(baseline, case["packet"])[0]["content"]
        assert "COMPLETE" in system
        assert "scored as a failure" in system
        # The shape example must not teach single citation.
        assert '"evidence_refs":["<supporting evidence ID>"]' not in system
        assert '"<ID>","<ID>"' in system
        # The rubric must not be leaked as a literal kind list.
        for kind in EVIDENCE_KINDS:
            assert kind not in system

    # Completeness is what the scorer actually enforces, in every case.
    for case_id, entry in scenario_cases_v3(document).items():
        truth = entry["ground_truth"]
        required = {str(item) for item in truth["required_evidence"]}
        assert len(required) >= 2, case_id
        partial = dict(_valid_result(entry, correct=True))
        one = sorted(required)[:1]
        partial["evidence"] = one
        partial["claims"] = [
            {**dict(partial["claims"][0]), "evidence_refs": one}
        ]
        scored = score_result_v3(partial, truth)
        assert scored["core_e2e"] == 0.0, case_id
        assert scored["failure_class"] == "missing_required_evidence", case_id

    # The longer instruction must still fit the four-turn input bound.
    preflight = token_preflight_v3(document)
    assert preflight["status"] == "pass"
    assert preflight["blocked_case_ids"] == []
    assert preflight["headroom_at_max"] >= preflight["required_headroom"]


def test_v3_metric_definition_artifact_matches_the_code_that_runs() -> None:
    """The frozen definition must not describe a method the estimator does not use.

    `metric_definition_v3()` keeps its own `comparison`/`candidate_rule`/`quanta` fields, separate
    from the threshold registry. r6 was invalidated because those fields still declared the
    superseded strict-inequality rule and 1-byte memory quantum while the code ran `>=`, a relative
    memory floor, and a page quantum -- so `metric_definition_digest` did not move when it had to.
    """
    definition = readiness.metric_definition_v3()
    registry = build_deterministic_thresholds_v3(_scenario_document())
    source = inspect.getsource(readiness.deterministic_candidates_v3)

    # The declared comparison must match the operator actually used.
    assert definition["comparison"] == "greater_than_or_equal_to"
    assert "excess >= cutoff" in source
    assert "strictly" not in definition["candidate_rule"]

    # Quanta and relative floors must agree between the definition and the registry.
    assert definition["quanta"] == registry["quanta"]
    assert (
        definition["relative_root_signal_floors"]
        == registry["relative_root_signal_floors"]
        == readiness.RELATIVE_ROOT_SIGNAL_FLOORS
    )


def test_v3_relative_root_signal_floor_is_derived_not_hardcoded() -> None:
    """The memory floor is a fraction of each case's own healthy median, recorded per case.

    `working_set_bytes` is the only root signal with a large non-zero healthy baseline, so an
    absolute cutoff cannot separate a leak from ambient cross-talk. The floor must scale with the
    measured working set rather than be a fixed byte count.
    """
    assert readiness.RELATIVE_ROOT_SIGNAL_FLOORS == {"emailMemoryLeak": 0.05}

    document = _scenario_document()
    registry = build_deterministic_thresholds_v3(document)
    assert registry["relative_root_signal_floors"] == {"emailMemoryLeak": 0.05}

    for per_label in registry["cases"].values():
        memory = per_label["emailMemoryLeak"]["features"]["root_signal"]
        assert memory["relative_floor_fraction"] == 0.05
        # Derived from the case's own healthy median, and it only ever raises the cutoff.
        expected = memory["relative_floor_healthy_median"] * 0.05
        assert memory["relative_floor"] == pytest.approx(expected)
        assert memory["threshold"] >= memory["relative_floor"]
        assert memory["threshold"] >= memory["healthy_p99"]
        # No other label carries a relative floor.
        for other in ROOT_CAUSE_LABELS:
            if other != "emailMemoryLeak":
                assert "relative_floor" not in per_label[other]["features"]["root_signal"]


def test_v2_and_v3_trial_ids_dataset_and_cache_routes_are_isolated() -> None:
    document = _scenario_document()
    cases = scenario_cases_v3(document)
    digest = dataset_digest_v3(document)
    v3 = trial_specs_v3(digest, cases, 3)
    v2 = _gate_trial_specs(digest, cases, metric_version=2)
    source = inspect.getsource(_run_live_trials_v3)

    assert digest != _digest_json({"cases": cases})
    assert {spec["trial_id"] for specs in v3.values() for spec in specs}.isdisjoint(
        {spec["trial_id"] for specs in v2.values() for spec in specs}
    )
    assert all(
        spec["trial_id"].startswith("g03-readiness-v3-") for specs in v3.values() for spec in specs
    )
    assert "metric-v3:frozen-arm-contract" in source


@pytest.mark.parametrize(
    ("deterministic_pass", "no_rag_pass", "naive_pass", "blocker"),
    [
        (
            set(range(8)),
            set(range(8)),
            set(range(8)),
            "registered_baseline_point_estimates_exactly_equal",
        ),
        (set(), set(range(12)), set(range(20)), "zero_width_ci:deterministic"),
        (
            set(range(8)),
            set(range(31)),
            set(range(32)),
            "best_baseline_above_0_90",
        ),
        (
            set(range(8)),
            set(range(7)) | {8, 9},
            set(range(7)) | {8, 9, 10},
            "deterministic_live_significance_not_established",
        ),
    ],
)
def test_v3_aggregate_blocks_equal_zero_width_crossing_and_best_above_limit(
    deterministic_pass: set[int],
    no_rag_pass: set[int],
    naive_pass: set[int],
    blocker: str,
) -> None:
    scenarios = _scenario_document()
    deterministic, live = _reference_documents(
        scenarios,
        deterministic_pass,
        no_rag_pass,
        naive_pass,
    )
    aggregate = aggregate_reference_v3(
        scenarios,
        deterministic,
        live,
        dataset_digest_v3(scenarios),
    )

    assert aggregate["readiness_status"] == "blocked"
    assert any(item.startswith(blocker) for item in aggregate["readiness_blockers"])


def test_v3_repetition_extension_has_one_exact_authorized_condition() -> None:
    aggregate = {
        "repetitions": 3,
        "readiness_status": "blocked",
        "readiness_blockers": ["deterministic_live_significance_not_established"],
    }
    assert should_extend_reference_v3(aggregate)
    for blocker in (
        "best_baseline_above_0_90",
        "zero_width_ci:deterministic",
        "presence_probe_not_at_prior",
    ):
        changed = copy.deepcopy(aggregate)
        changed["readiness_blockers"].append(blocker)
        assert not should_extend_reference_v3(changed)


def test_required_mapping_has_two_kinds_and_covers_all_labels() -> None:
    assert set(REQUIRED_KINDS) == set(ROOT_CAUSE_LABELS)
    assert set(ROOT_SIGNAL_FEATURES) == set(ROOT_CAUSE_LABELS)
    assert all(len(set(kinds)) >= 2 for kinds in REQUIRED_KINDS.values())


def test_v3_result_schema_is_the_schema_actually_given_to_validator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = next(iter(scenario_cases_v3(_scenario_document()).values()))
    result = _valid_result(case)
    observed: list[Mapping[str, object]] = []

    class SpyValidator:
        @classmethod
        def check_schema(cls, schema: Mapping[str, object]) -> None:
            observed.append(schema)
            RealDraft202012Validator.check_schema(schema)

        def __init__(self, schema: Mapping[str, object]) -> None:
            observed.append(schema)
            self.delegate = RealDraft202012Validator(schema)

        def validate(self, document: Mapping[str, object]) -> None:
            self.delegate.validate(document)

    monkeypatch.setattr(readiness, "Draft202012Validator", SpyValidator)
    validate_result_v3(result)
    assert observed and all(schema is RESULT_SCHEMA_V3 for schema in observed)

    extra = copy.deepcopy(result)
    extra["unregistered"] = True
    with pytest.raises(GovernanceError, match="Additional"):
        validate_result_v3(extra)


def test_wire_schema_and_metric_versions_are_explicitly_decoupled() -> None:
    assert wire_schema_for_metric(1) == "1.0.0"
    assert wire_schema_for_metric(2) == "2.0.0"
    assert wire_schema_for_v3(3) == "2.0.0"
    assert RESULT_SCHEMA_V3["properties"]["metric_version"] == {"const": 3}
    assert "metric_version" in RESULT_SCHEMA_V3["required"]


def test_unknown_versions_fail_before_any_artifact_or_secret_boundary(
    tmp_path: Path,
) -> None:
    scenarios = _scenario_document()
    cases = scenario_cases_v3(scenarios)
    case = next(iter(cases.values()))
    calls = (
        lambda: require_g02_metric_version(99),
        lambda: wire_schema_for_metric(99),
        lambda: wire_schema_for_v3(99),
        lambda: evidence_id_v3("case", "trace_activity", metric_version=99),
        lambda: load_baseline_config_v3(Path.cwd(), metric_version=99),
        lambda: build_baseline_prompt_v3("no_rag", case["packet"], metric_version=99),
        lambda: validate_result_v3(_valid_result(case), metric_version=99),
        lambda: score_result_v3(
            _valid_result(case),
            case["ground_truth"],
            metric_version=99,
        ),
        lambda: trial_specs_v3("digest", cases, 3, metric_version=99),
        lambda: run_retest_baselines_v3(
            Path.cwd(),
            tmp_path / "never-written",
            skip_live=True,
            metric_version=99,
        ),
    )
    for call in calls:
        with pytest.raises(GovernanceError, match="version"):
            call()
    assert not (tmp_path / "never-written").exists()


def test_compact_packet_completeness_and_token_headroom_are_independent() -> None:
    document = _scenario_document()
    preflight = token_preflight_v3(document)
    assert preflight["status"] == "pass"
    assert preflight["max"] <= 58_982
    assert preflight["headroom_at_max"] >= 6_554
    assert all(
        row["four_turn_input_upper_bound"] == sum(row["per_request"])
        for row in preflight["cases"]
    )

    incomplete = copy.deepcopy(document["trials"][0]["payload"]["observation_packet"])
    incomplete["observations"].pop()
    subject = {key: value for key, value in incomplete.items() if key != "packet_digest"}
    incomplete["packet_digest"] = _digest_json(subject)
    with pytest.raises(
        GovernanceError,
        match="dataset_incomplete: .*six evidence groups",
    ):
        validate_observation_packet_v3(incomplete)

    field_drift = copy.deepcopy(document["trials"][0]["payload"]["observation_packet"])
    queue_group = next(
        group for group in field_drift["observations"] if group["kind"] == "queue_window"
    )
    queue_group["samples"][0].pop("consumer_lag")
    field_subject = {
        key: value for key, value in field_drift.items() if key != "packet_digest"
    }
    field_drift["packet_digest"] = _digest_json(field_subject)
    with pytest.raises(
        GovernanceError,
        match="dataset_incomplete: .*sample fields drifted",
    ):
        validate_observation_packet_v3(field_drift)

    metadata_only = copy.deepcopy(document)
    metadata_packet = metadata_only["trials"][0]["payload"]["observation_packet"]
    for group in metadata_packet["observations"]:
        if group["kind"] == "journey_window":
            for sample in group["samples"]:
                sample["ready"] = False
                sample["status_code"] = 0
        elif group["kind"] == "cpu_window":
            for sample in group["samples"]:
                sample["cpu_cores"] = 0.0
        elif group["kind"] == "memory_window":
            for sample in group["samples"]:
                sample["working_set_bytes"] = 0.0
    metadata_subject = {
        key: value for key, value in metadata_packet.items() if key != "packet_digest"
    }
    metadata_packet["packet_digest"] = _digest_json(metadata_subject)
    with pytest.raises(
        GovernanceError,
        match="dataset_incomplete: .*non-zero distractor",
    ):
        scenario_cases_v3(metadata_only)

    bloated = copy.deepcopy(document)
    packet = bloated["trials"][0]["payload"]["observation_packet"]
    trace_errors = next(
        group for group in packet["observations"] if group["kind"] == "trace_errors"
    )
    trace_errors["samples"][0]["services"]["ad"]["descriptions"] = ["x" * 20_000]
    subject = {key: value for key, value in packet.items() if key != "packet_digest"}
    packet["packet_digest"] = _digest_json(subject)
    assert four_turn_input_upper_bound_v3(packet)["status"] == "blocked"


def test_metric_definition_digest_changes_with_frozen_formula(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = metric_definition_v3()
    monkeypatch.setattr(readiness, "DETERMINISTIC_PERCENTILE", 0.98)
    after = metric_definition_v3()
    assert before["metric_definition_digest"] != after["metric_definition_digest"]


def test_paired_significance_accepts_both_directions() -> None:
    high = [
        {"case_id": f"case-{case}", "repetition": repetition, "core_e2e": 1.0}
        for case in range(32)
        for repetition in range(1, 4)
    ]
    low = [
        {"case_id": f"case-{case}", "repetition": repetition, "core_e2e": 0.0}
        for case in range(32)
        for repetition in range(1, 4)
    ]
    positive = paired_cluster_bootstrap_v3(high, low, seed="positive")
    negative = paired_cluster_bootstrap_v3(low, high, seed="negative")
    assert positive["lower"] > 0
    assert negative["upper"] < 0


def test_deterministic_exactly_one_is_a_pre_live_hard_stop() -> None:
    blockers = _preflight_blockers_v3(
        {"status": "pass"},
        {"ambiguity_count": 0, "N": 32},
        {"status": "pass"},
        {"estimate": 1.0, "lower": 1.0, "upper": 1.0},
    )
    assert blockers == ["deterministic_core_e2e_exactly_1_000"]


@pytest.mark.parametrize(
    "failure_class",
    ("budget_exhausted", "output_truncated", "malformed"),
)
def test_trial_failure_classes_remain_distinct_and_in_denominator(
    tmp_path: Path,
    failure_class: str,
) -> None:
    cases = scenario_cases_v3(_scenario_document())
    case_id = sorted(cases)[0]
    spec = {
        "trial_id": f"trial-{failure_class}",
        "baseline": "naive_react",
        "case_id": case_id,
        "repetition": 1,
        "packet": cases[case_id]["packet"],
    }

    def fail(_packet: Mapping[str, object]) -> Mapping[str, object]:
        raise LiveTrialFailure(
            failure_class,
            failure_class,
            input_tokens=7,
            output_tokens=3,
            telemetry={"turn_usage": []},
        )

    [record] = _run_live_trials_v3(
        tmp_path / failure_class,
        [spec],
        fail,
        producer_sha="1" * 40,
    )
    assert record["status"] == "pass"
    assert record["payload"]["result"]["failure_class"] == failure_class
    assert record["payload"]["input_tokens"] == 7


def _write_trial(directory: Path, trial_id: str, status: str, cache_key: str) -> Path:
    trials = directory / "journals" / "scenarios" / "trials"
    trials.mkdir(parents=True, exist_ok=True)
    path = trials / f"{trial_id}.json"
    path.write_text(
        json.dumps(
            {
                "trial_id": trial_id,
                "status": status,
                "cache_key": cache_key,
                "artifact_digest": "d" * 64,
                "execution_attempt": 1,
                "record_version": 2,
                "payload": {"scenario_id": trial_id.upper()},
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def test_trial_inheritance_carries_only_passing_records(tmp_path: Path) -> None:
    """Inheritance saves re-measuring passed cases without carrying a failure forward."""
    root = tmp_path
    source = root / ".audit" / "g03-readiness" / "source-run"
    source.mkdir(parents=True)
    (source / "run-manifest.json").write_text("{}", encoding="utf-8")
    _write_trial(source, "case-a", "pass", "key-a")
    _write_trial(source, "case-b", "pass", "key-b")
    _write_trial(source, "case-c", "infra_failed", "key-c")
    _write_trial(source, "case-d", "metric_fail", "key-d")

    target = root / ".audit" / "g03-readiness" / "target-run"
    receipt = inherit_passing_trials_v3(root, source, target)

    assert receipt["inherited_count"] == 2
    assert [item["trial_id"] for item in receipt["inherited_trials"]] == ["case-a", "case-b"]
    assert {item["status"] for item in receipt["not_inherited"]} == {
        "infra_failed",
        "metric_fail",
    }
    copied = sorted(
        path.stem for path in (target / "journals" / "scenarios" / "trials").glob("*.json")
    )
    assert copied == ["case-a", "case-b"]
    assert receipt["source_run"] == ".audit/g03-readiness/source-run"


def test_trial_inheritance_refuses_an_invalidated_source(tmp_path: Path) -> None:
    root = tmp_path
    source = root / ".audit" / "g03-readiness" / "run-invalidated-process-exited"
    source.mkdir(parents=True)
    _write_trial(source, "case-a", "pass", "key-a")
    target = root / ".audit" / "g03-readiness" / "target-run"
    with pytest.raises(GovernanceError, match="invalidated"):
        inherit_passing_trials_v3(root, source, target)

    marked = root / ".audit" / "g03-readiness" / "marked-run"
    marked.mkdir(parents=True)
    (marked / "INVALIDATION.md").write_text("invalid", encoding="utf-8")
    _write_trial(marked, "case-a", "pass", "key-a")
    with pytest.raises(GovernanceError, match="invalidated"):
        inherit_passing_trials_v3(root, marked, root / ".audit" / "g03-readiness" / "other")


def test_trial_inheritance_refuses_to_overwrite_existing_trials(tmp_path: Path) -> None:
    root = tmp_path
    source = root / ".audit" / "g03-readiness" / "source-run"
    source.mkdir(parents=True)
    _write_trial(source, "case-a", "pass", "key-a")
    target = root / ".audit" / "g03-readiness" / "target-run"
    _write_trial(target, "case-z", "pass", "key-z")
    with pytest.raises(GovernanceError, match="already holds trials"):
        inherit_passing_trials_v3(root, source, target)


def test_trial_inheritance_is_preflight_only(tmp_path: Path) -> None:
    """Inheritance must not be reachable from a live resume or a diagnostic scan."""
    root = tmp_path
    with pytest.raises(GovernanceError, match="only to a preflight"):
        run_retest_baselines_v3(
            root,
            root / ".audit" / "g03-readiness" / "run",
            skip_live=False,
            resume=True,
            inherit_from=Path(".audit/g03-readiness/source"),
        )
    with pytest.raises(GovernanceError, match="never gate evidence"):
        run_retest_baselines_v3(
            root,
            root / ".audit" / "g03-readiness" / "run",
            skip_live=True,
            continue_on_case_failure=True,
            inherit_from=Path(".audit/g03-readiness/source"),
        )


def test_invalidated_resume_paths_fail_closed_after_resolution(tmp_path: Path) -> None:
    root = tmp_path
    invalidated = root / ".audit" / "g03-readiness" / "invalidated" / "run"
    invalidated.mkdir(parents=True)
    indirect = invalidated.parent / ".." / "invalidated" / "run"
    with pytest.raises(GovernanceError, match="invalidated"):
        _validate_output_dir_v3(root, indirect, resume=True)

    suffix = (
        root
        / ".audit"
        / "g03-readiness"
        / "run-invalidated-collector-pod-pinning"
    )
    suffix.mkdir(parents=True)
    (suffix / "run-manifest.json").write_text("{}", encoding="utf-8")
    with pytest.raises(GovernanceError, match="invalidated"):
        _validate_output_dir_v3(root, suffix, resume=True)

    marked = root / ".audit" / "g03-readiness" / "marked-run"
    marked.mkdir(parents=True)
    (marked / "INVALIDATION.md").write_text("invalid", encoding="utf-8")
    with pytest.raises(GovernanceError, match="invalidated"):
        _validate_output_dir_v3(root, marked, resume=True)

    link = root / ".audit" / "g03-readiness" / "linked-run"
    try:
        link.symlink_to(invalidated, target_is_directory=True)
    except OSError:
        return
    with pytest.raises(GovernanceError, match="invalidated"):
        _validate_output_dir_v3(root, link, resume=True)


def test_same_directory_resume_binds_scenarios_dataset_and_definition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path
    output = root / "run"
    output.mkdir()
    scenarios = _scenario_document()
    scenario_digest = write_json_artifact_v3(output / "scenarios.json", scenarios)
    definition = metric_definition_v3()
    write_json_artifact_v3(output / "metric-definition.json", definition)
    write_json_artifact_v3(
        output / "preflight-summary.json",
        {"preflight_status": "pass"},
    )
    identity = {
        "metric_version": 3,
        "wire_schema_version": "2.0.0",
        "producer_sha": "1" * 40,
        "relevant_source_digest": "source",
        "config_digest": "config",
        "amd_digest": "amd",
        "metric_definition_digest": definition["metric_definition_digest"],
        "checkpoint_identities": {
            "sut_producer_sha": "2" * 40,
            "sut_image_set_digest": "image",
            "model_id": "model",
        },
    }
    write_json_artifact_v3(
        output / "run-manifest.json",
        {
            **identity,
            "dataset_digest": dataset_digest_v3(scenarios),
            "scenario_artifact_digest": scenario_digest,
        },
    )
    monkeypatch.setattr(readiness, "_run_identity_v3", lambda _root: identity)
    manifest, resumed = _assert_resume_identity_v3(root, output)
    assert manifest["dataset_digest"] == dataset_digest_v3(resumed)

    scenarios["scenario_count"] = 31
    write_json_artifact_v3(output / "scenarios.json", scenarios)
    with pytest.raises(GovernanceError, match="artifact bytes changed"):
        _assert_resume_identity_v3(root, output)


def test_version_routing_inventory_uses_actual_tree_count() -> None:
    root = Path(__file__).resolve().parents[2]
    inventory = build_version_routing_inventory(root)
    assert inventory["actual_reference_count"] == len(inventory["occurrences"])
    assert inventory["actual_reference_count"] > 43
    assert {
        "version declaration",
        "entry dispatcher",
        "artifact metadata",
        "test-only",
    }.issubset(inventory["classification_counts"])


def test_arm_wide_budget_failure_is_a_hard_blocker() -> None:
    scenarios = _scenario_document()
    deterministic, live = _reference_documents(
        scenarios,
        set(range(8)),
        set(range(12)),
        set(range(20)),
    )
    for trial in live["trials"]:
        if trial["baseline"] == "no_rag":
            trial["status"] = "scored_failure"
            trial["failure_class"] = "budget_exhausted"
            trial["result"] = {
                "status": "scored_failure",
                "failure_class": "budget_exhausted",
                "reason": "budget",
            }
    aggregate = aggregate_reference_v3(
        scenarios,
        deterministic,
        live,
        dataset_digest_v3(scenarios),
    )
    assert "arm_wide_budget_failure:no_rag" in aggregate["readiness_blockers"]
