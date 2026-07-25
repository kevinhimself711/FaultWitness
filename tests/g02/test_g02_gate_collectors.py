from __future__ import annotations

import json
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

from faultwitness_dev.errors import GovernanceError
from faultwitness_dev.g02_collectors import (
    CandidateProbeBackend,
    MemoryProbeBackend,
    ProbeBlockedError,
    ProbeInfrastructureError,
    build_provisioning_plan,
    canary_values,
    run_access_matrix,
    run_canary_matrix,
    run_trace_matrix,
    validate_provisioning_plan,
)
from faultwitness_dev.g02_eval import (
    G02_PHASES,
    PhaseContext,
    PhaseEngine,
    TrialJournal,
    _owned_phase_handlers,
)
from faultwitness_dev.g02_isolation import CANARY_SURFACES, TRACE_STAGES, access_cell_contract
from faultwitness_dev.schemas import load_data

ROOT = Path(__file__).resolve().parents[2]
CANDIDATE = "1" * 40
ENVIRONMENT = "2" * 64


def _context() -> PhaseContext:
    return PhaseContext(
        candidate_sha=CANDIDATE,
        runtime_image_digests=("3" * 64,),
        sut_image_set_digest="4" * 64,
        config_digest="5" * 64,
        evaluator_digest="6" * 64,
        dataset_digest="7" * 64,
        environment_fingerprint=ENVIRONMENT,
    )


def _remote_probe_module():  # type: ignore[no-untyped-def]
    path = ROOT / "deploy/g02/gate_probe.py"
    spec = spec_from_file_location("faultwitness_g02_gate_probe_test", path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_provisioning_plan_is_bound_pinned_and_credential_free() -> None:
    plan = build_provisioning_plan(ROOT, _context())
    assert plan["candidate_sha"] == CANDIDATE
    assert plan["environment_fingerprint"] == ENVIRONMENT
    assert len(plan["principals"]) == 4
    assert len(plan["prefixes"]) == 5
    assert len(plan["credential_refs"]) == 4
    assert plan["secret_values"] == []
    assert all("@sha256:" in image for image in plan["images"].values())

    drift = load_data(ROOT / "tests/fixtures/g02/provisioning_identity_drift.json")
    with pytest.raises(GovernanceError, match="principal registry"):
        validate_provisioning_plan({**plan, **drift})


def test_remote_provisioning_contract_matches_local_digest_and_cross_boundary_policy() -> None:
    backend = CandidateProbeBackend(ROOT, {})
    request = backend._request(_context())
    remote = _remote_probe_module()
    local_plan = build_provisioning_plan(ROOT, _context())
    assert remote.plan_resources(request) == local_plan
    assert remote.object_operation("s3:g02/scenarios/", "cross-boundary") == (
        "sealed-evaluator",
        "read",
    )
    assert remote.object_operation("s3:g02/trials/", "cross-boundary") == (
        "scenario-controller",
        "write",
    )


@pytest.mark.parametrize(
    ("cell", "returncode", "stderr", "required_command", "forbidden_commands", "outcome"),
    [
        (
            {"target": "s3:g02/scenarios/", "probe": "canonical-owner"},
            0,
            "",
            "mc cat probe/faultwitness-eval/g02/scenarios/deny-sentinel",
            ("mc stat", "mc pipe"),
            (True, "allowed"),
        ),
        (
            {"target": "s3:g02/ground-truth/", "probe": "ordinary-developer"},
            1,
            "Access Denied",
            "mc cat probe/faultwitness-eval/g02/ground-truth/deny-sentinel",
            ("mc stat", "mc pipe"),
            (False, "denied"),
        ),
        (
            {"target": "s3:g02/evidence/", "probe": "canonical-owner"},
            0,
            "",
            "mc pipe probe/faultwitness-eval/g02/evidence/probe-",
            ("mc stat", "mc cat"),
            (True, "allowed"),
        ),
    ],
)
def test_object_probe_uses_exact_getobject_and_preserves_denials_and_writes(
    monkeypatch: pytest.MonkeyPatch,
    cell: dict[str, str],
    returncode: int,
    stderr: str,
    required_command: str,
    forbidden_commands: tuple[str, ...],
    outcome: tuple[bool, str],
) -> None:
    remote = _remote_probe_module()
    scripts: list[str] = []

    monkeypatch.setattr(remote, "secret_value", lambda *_args: "test-credential")

    def fake_mc_script(script: str, *, check: bool = True):  # type: ignore[no-untyped-def]
        scripts.append(script)
        assert check is False
        return remote.subprocess.CompletedProcess(
            args=["mc"], returncode=returncode, stdout="", stderr=stderr
        )

    monkeypatch.setattr(remote, "mc_script", fake_mc_script)
    assert remote.object_access({}, cell) == outcome
    assert len(scripts) == 1
    assert required_command in scripts[0]
    assert all(command not in scripts[0] for command in forbidden_commands)


def test_remote_probe_uses_python38_compatible_utc_semantics() -> None:
    source = (ROOT / "deploy/g02/gate_probe.py").read_text(encoding="utf-8")
    assert "from datetime import UTC" not in source
    remote = _remote_probe_module()
    timestamp = remote.datetime.now(remote.UTC)
    assert remote.UTC is remote.timezone.utc
    assert timestamp.utcoffset() is not None
    assert timestamp.utcoffset().total_seconds() == 0
    assert timestamp.isoformat().endswith("+00:00")


def test_access_collector_is_exactly_60_cells_and_terminal_failure_is_not_retried(
    tmp_path: Path,
) -> None:
    backend = MemoryProbeBackend(ROOT)
    journal = TrialJournal(tmp_path)
    document = run_access_matrix(_context(), journal, backend)
    assert document["status"] == "pass"
    assert len(document["cells"]) == 60
    assert backend.calls == {"provision": 1, "access": 60}

    first = access_cell_contract()[0]
    failing = MemoryProbeBackend(
        ROOT, access_overrides={str(first["cell_id"]): not bool(first["expected_allow"])}
    )
    failing_journal = TrialJournal(tmp_path / "failure")
    assert run_access_matrix(_context(), failing_journal, failing)["status"] == "metric_fail"
    assert run_access_matrix(_context(), failing_journal, failing)["status"] == "metric_fail"
    assert failing.calls["access"] == 1


def test_trace_and_canary_collectors_fail_closed_on_named_negative_fixtures(
    tmp_path: Path,
) -> None:
    trace_fixture = load_data(ROOT / "tests/fixtures/g02/trace_missing_stage.json")
    trace_backend = MemoryProbeBackend(ROOT, missing_stage=trace_fixture["missing_stage"])
    trace = run_trace_matrix(_context(), TrialJournal(tmp_path / "trace"), trace_backend)
    assert trace["status"] == "metric_fail"
    assert len(trace["stages"]) == len(TRACE_STAGES)

    canary_fixture = load_data(ROOT / "tests/fixtures/g02/canary_leaked_artifact.json")
    canary_backend = MemoryProbeBackend(
        ROOT, canary_hit_surface=canary_fixture["surface"]
    )
    canary = run_canary_matrix(
        _context(), TrialJournal(tmp_path / "canary"), canary_backend
    )
    assert canary["status"] == "metric_fail"
    assert len(canary["surfaces"]) == len(CANARY_SURFACES)


def test_infrastructure_failure_resumes_only_the_failed_access_cell(tmp_path: Path) -> None:
    class TransientBackend(MemoryProbeBackend):
        failed = False

        def access_cell(self, context, contract):  # type: ignore[no-untyped-def]
            if contract["cell_id"] == access_cell_contract()[2]["cell_id"] and not self.failed:
                self.failed = True
                raise ProbeInfrastructureError("transport_interrupted")
            return super().access_cell(context, contract)

    backend = TransientBackend(ROOT)
    journal = TrialJournal(tmp_path)
    first = run_access_matrix(_context(), journal, backend)
    assert first["status"] == "infra_failed"
    assert len(first["cells"]) == 2
    second = run_access_matrix(_context(), journal, backend)
    assert second["status"] == "pass"
    assert len(second["cells"]) == 60
    assert backend.calls["access"] == 60


def test_phase_handlers_produce_target_artifacts_without_phase_inputs(tmp_path: Path) -> None:
    context = _context()
    engine = PhaseEngine(G02_PHASES, context, tmp_path / "journal")
    handlers = _owned_phase_handlers(
        tmp_path,
        {"_eval_id": "EVAL-G02-010"},
        engine,
        MemoryProbeBackend(ROOT),
    )
    journal = TrialJournal(tmp_path / "journal")
    expected = {
        "isolation-access-matrix": 60,
        "trace-six-stage-matrix": 6,
        "all-surface-canary": 22,
    }
    for phase_id, count in expected.items():
        result = handlers[phase_id](context, journal)
        assert result["status"] == "pass"
        assert result["artifact_path"].endswith(f"{phase_id}/matrix.json")
        assert (tmp_path / result["artifact_path"]).is_file()
        assert count in result.values()


def test_candidate_backend_classifies_transport_and_rejects_raw_canary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = CandidateProbeBackend(ROOT, {})

    def transport_failure(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise GovernanceError("ssh transport unavailable")

    monkeypatch.setattr("faultwitness_dev.g02_collectors.run_remote_script", transport_failure)
    with pytest.raises(ProbeInfrastructureError, match="remote_probe_transport"):
        backend._invoke("plan", _context())

    raw_canary = canary_values(_context())[0]
    monkeypatch.setattr(
        "faultwitness_dev.g02_collectors.run_remote_script",
        lambda *_args, **_kwargs: json.dumps(
            {"status": "pass", "unexpected": raw_canary}
        ),
    )
    with pytest.raises(ProbeBlockedError, match="raw_canary"):
        backend._invoke("plan", _context())


def test_invalid_backend_artifact_is_blocking_and_reviewable(tmp_path: Path) -> None:
    class MissingArtifactBackend(MemoryProbeBackend):
        def access_cell(self, context, contract):  # type: ignore[no-untyped-def]
            result = dict(super().access_cell(context, contract))
            result.pop("artifact_ref")
            return result

    backend = MissingArtifactBackend(ROOT)
    journal = TrialJournal(tmp_path)
    document = run_access_matrix(_context(), journal, backend)
    assert document["status"] == "blocked"
    record = journal.read("access-01")
    assert record is not None
    assert record["status"] == "blocked"
