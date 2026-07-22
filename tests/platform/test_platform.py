from __future__ import annotations

import json
from pathlib import Path

import pytest

from faultwitness_dev.errors import GovernanceError
from faultwitness_dev.platform import (
    PlatformPaths,
    _assert_candidate,
    _sanitize_inventory,
    deploy_platform,
    inspect_platform_readiness,
)

CANDIDATE = "a" * 40


def _inventory(*, ready: int = 1, generation: int = 4) -> str:
    return json.dumps(
        {
            "apiVersion": "v1",
            "items": [
                {
                    "kind": "StatefulSet",
                    "metadata": {
                        "name": "postgresql",
                        "namespace": "fw-data",
                        "generation": generation,
                        "annotations": {"unsafe.example/token": "must-not-survive"},
                    },
                    "spec": {
                        "replicas": 1,
                        "template": {
                            "metadata": {
                                "labels": {"app.kubernetes.io/part-of": "faultwitness-platform"}
                            },
                            "spec": {
                                "containers": [{"env": [{"name": "PASSWORD", "value": "private"}]}]
                            },
                        },
                    },
                    "status": {
                        "readyReplicas": ready,
                        "observedGeneration": generation,
                    },
                }
            ],
        }
    )


def test_sanitized_inventory_is_candidate_bound_and_allowlisted() -> None:
    result = _sanitize_inventory(_inventory(), CANDIDATE)
    encoded = json.dumps(result)
    assert result["candidate_sha"] == CANDIDATE
    assert result["workload_count"] == 1
    assert result["workloads"][0]["ready"] == 1
    assert "private" not in encoded
    assert "must-not-survive" not in encoded
    assert "annotations" not in encoded


@pytest.mark.parametrize("raw", ["{}", '{"items": []}', "not-json"])
def test_sanitized_inventory_fails_closed_on_missing_or_invalid_evidence(raw: str) -> None:
    with pytest.raises(GovernanceError):
        _sanitize_inventory(raw, CANDIDATE)


def test_sanitized_inventory_rejects_unready_or_stale_workload() -> None:
    with pytest.raises(GovernanceError, match="not Ready"):
        _sanitize_inventory(_inventory(ready=0), CANDIDATE)
    document = json.loads(_inventory())
    document["items"][0]["status"]["observedGeneration"] = 3
    with pytest.raises(GovernanceError, match="not Ready"):
        _sanitize_inventory(json.dumps(document), CANDIDATE)


def test_candidate_binding_rejects_head_mismatch(monkeypatch, tmp_path: Path) -> None:
    class Result:
        stdout = "b" * 40 + "\n"

    monkeypatch.setattr("faultwitness_dev.platform.subprocess.run", lambda *a, **k: Result())
    with pytest.raises(GovernanceError, match="does not match"):
        _assert_candidate(tmp_path, CANDIDATE, [])


def test_deploy_platform_stages_helm_bundle_and_writes_private_summary(
    monkeypatch, tmp_path: Path
) -> None:
    chart = tmp_path / "deploy" / "charts" / "faultwitness-platform"
    chart.mkdir(parents=True)
    (chart / "Chart.yaml").write_text(
        "apiVersion: v2\nname: faultwitness-platform\nversion: 0.1.0\n",
        encoding="utf-8",
    )
    templates = chart / "templates"
    templates.mkdir()
    (templates / "deployment.yaml").write_text(
        "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: example\n",
        encoding="utf-8",
    )
    values = tmp_path / "deploy" / "environments" / "private-server" / "values.yaml"
    values.parent.mkdir(parents=True)
    values.write_text("replicas: 1\n", encoding="utf-8")
    evidence = PlatformPaths(tmp_path / "private-evidence")
    captured: dict[str, object] = {}
    monkeypatch.setattr("faultwitness_dev.platform._assert_candidate", lambda *a, **k: None)

    def fake_remote(script: str, **kwargs: object) -> str:
        captured["script"] = script
        captured["kwargs"] = kwargs
        return ""

    monkeypatch.setattr("faultwitness_dev.platform.run_remote_script", fake_remote)
    result = deploy_platform(
        tmp_path,
        CANDIDATE,
        chart=chart,
        values=values,
        evidence_paths=evidence,
    )
    script = str(captured["script"])
    assert "export KUBECONFIG=/etc/rancher/k3s/k3s.yaml" in script
    assert "helm upgrade --install fw-platform" in script
    assert "--atomic --wait --timeout 15m" in script
    assert "fw-platform-candidate-binding" in script
    assert f"--from-literal=candidate_sha={CANDIDATE}" in script
    assert captured["kwargs"] == {"privileged": True, "timeout": 1200}
    assert result["candidate_sha"] == CANDIDATE
    written = json.loads((evidence.evidence_dir / "deployment-summary.json").read_text())
    assert written["deployment_bundle_sha256"] == result["deployment_bundle_sha256"]


def test_inspect_platform_rechecks_for_full_stability_window(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("faultwitness_dev.platform._assert_candidate", lambda *a, **k: None)
    calls = {"remote": 0}

    def fake_remote(*args: object, **kwargs: object) -> str:
        calls["remote"] += 1
        return _inventory()

    ticks = iter([0.0, 0.0, 5.0, 10.0])
    sleeps: list[float] = []
    monkeypatch.setattr("faultwitness_dev.platform.run_remote_script", fake_remote)
    result = inspect_platform_readiness(
        tmp_path,
        CANDIDATE,
        stability_seconds=10,
        evidence_paths=PlatformPaths(tmp_path / "evidence"),
        clock=lambda: next(ticks),
        sleeper=sleeps.append,
    )
    assert calls["remote"] == 3
    assert sleeps == [5.0, 5.0]
    assert result["stability_seconds"] == 10
