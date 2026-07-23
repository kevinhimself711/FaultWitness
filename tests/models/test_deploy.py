from pathlib import Path

from faultwitness_dev.model_deploy import _manifest, _tracked_files

ROOT = Path(__file__).resolve().parents[2]
SHA = "a" * 40


def test_model_gateway_deployment_is_private_candidate_bound_and_non_root() -> None:
    manifest = _manifest(SHA, f"docker.io/faultwitness/model-gateway:{SHA}")
    assert f'candidate_sha: "{SHA}"' in manifest
    assert "type: ClusterIP" in manifest
    assert "readOnlyRootFilesystem: true" in manifest
    assert "allowPrivilegeEscalation: false" in manifest
    assert "automountServiceAccountToken: false" in manifest
    assert "containerPort: 8002" in manifest
    assert "hostPort" not in manifest and "NodePort" not in manifest


def test_model_gateway_build_context_contains_catalog_and_runtime_dependencies() -> None:
    relative = {path.relative_to(ROOT).as_posix() for path in _tracked_files(ROOT)}
    assert "config/models/catalog.yaml" in relative
    assert "deploy/model-gateway/Dockerfile" in relative
    lock = (ROOT / "deploy/control-api/requirements.lock").read_text(encoding="utf-8")
    for package in ("jsonschema==", "pyyaml==", "referencing==", "rpds-py=="):
        assert package in lock
