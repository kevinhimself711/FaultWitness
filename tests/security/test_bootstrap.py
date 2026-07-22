from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from faultwitness_dev.bootstrap import (
    BootstrapPaths,
    SecretBundle,
    accept_host_key_candidate,
    assert_no_sensitive_capability_fields,
    canonical_capability_report,
    finalize_handoff,
    generate_server_password,
    host_key_fingerprint,
    migrate_handoff,
    parse_handoff,
    password_meets_rotation_policy,
)
from faultwitness_dev.errors import GovernanceError
from faultwitness_dev.evals import validate_capability_baseline


def handoff_text() -> str:
    opaque = "x" * 32
    return "\n".join(
        [
            "远程服务器",
            "服务器ip：192.0.2.10",
            "端口：2222",
            "用户：operator",
            "密码：" + opaque,
            "",
            "大模型api",
            "百炼key：" + opaque,
            "",
            "LANGSMITH配置",
            opaque,
        ]
    )


def bundle() -> SecretBundle:
    opaque = "y" * 32
    return SecretBundle(
        server_host="192.0.2.10",
        server_port=2222,
        server_username="operator",
        server_password=opaque,
        bailian_api_key=opaque,
        langsmith_api_key=opaque,
    )


def capability_document() -> dict:
    return {
        "architecture": "x86_64",
        "cpu_count": 32,
        "memory_bytes": 64 * 1024**3,
        "kernel_release": "5.15.0",
        "cgroup_version": 1,
        "kvm_available": True,
        "seccomp_available": True,
        "user_namespace_available": True,
        "docker_available": True,
        "docker_running_count": 2,
        "docker_unhealthy_count": 0,
        "ports_80_443_in_use": True,
        "k3s_available": False,
        "helm_available": False,
        "gvisor_available": False,
        "kata_available": False,
        "nvidia_available": True,
        "gpu_model": "RTX 4090",
        "gpu_memory_bytes": 24 * 1024**3,
        "root_filesystem": "ext4",
        "root_total_bytes": 1024**4,
        "cidr_conflict_with_10_42_10_43": False,
    }


def test_handoff_parser_extracts_required_fields_without_repr_leak() -> None:
    parsed = parse_handoff(handoff_text())
    assert parsed.server_port == 2222
    assert parsed.server_username == "operator"
    assert repr(parsed) == "SecretBundle(<redacted>)"
    assert set(parsed.to_document()) == {"schema_version", "server", "bailian", "langsmith"}


def test_handoff_parser_rejects_missing_secret_without_echoing_value() -> None:
    with pytest.raises(GovernanceError, match="langsmith.api_key") as raised:
        parse_handoff("\n".join(handoff_text().splitlines()[:-2]))
    assert "x" * 20 not in str(raised.value)


def test_legacy_password_can_be_secured_but_cannot_satisfy_rotation_policy() -> None:
    legacy = handoff_text().replace("x" * 32, "weak", 1)
    parsed = parse_handoff(legacy)
    assert not password_meets_rotation_policy(parsed.server_password)
    assert password_meets_rotation_policy("Correct-Horse-2026-Battery")
    assert password_meets_rotation_policy(generate_server_password())


def test_migration_writes_ciphertext_and_metadata_but_retains_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = BootstrapPaths.under(tmp_path / "private")
    paths.identity_file.parent.mkdir(parents=True)
    paths.identity_file.write_text("identity fixture", encoding="utf-8")
    source = tmp_path / "handoff.txt"
    source.write_text(handoff_text(), encoding="utf-8")
    monkeypatch.setattr(
        "faultwitness_dev.bootstrap.derive_age_recipient", lambda *_: "age1" + "q" * 58
    )
    monkeypatch.setattr(
        "faultwitness_dev.bootstrap.encrypt_bundle", lambda *_: "sops: encrypted fixture\n"
    )
    monkeypatch.setattr("faultwitness_dev.bootstrap.decrypt_bundle", lambda *_: bundle())
    monkeypatch.setattr("faultwitness_dev.bootstrap.parse_handoff", lambda *_: bundle())

    metadata = migrate_handoff(
        source,
        paths,
        tmp_path / "sops",
        tmp_path / "age-keygen",
        now=datetime(2026, 7, 22, tzinfo=UTC),
    )

    assert source.is_file()
    assert paths.encrypted_store.read_text(encoding="utf-8") == "sops: encrypted fixture\n"
    assert metadata["encrypted_round_trip"] == "pass"
    assert set(metadata["rotation"].values()) == {"pending"}
    assert "x" * 20 not in paths.metadata_file.read_text(encoding="utf-8")


def test_finalize_refuses_pending_rotation_and_preserves_handoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "envs.txt"
    source.write_text("opaque", encoding="utf-8")
    paths = BootstrapPaths.under(tmp_path / "private")
    metadata = {
        "rotation": {
            "server.password": "pending",
            "bailian.api_key": "verified",
            "langsmith.api_key": "verified",
        },
        "host_key_verified": True,
        "ssh_key_verified": True,
        "capability_reprobe_match": True,
    }
    monkeypatch.setattr("faultwitness_dev.bootstrap.validate_migration", lambda *_: metadata)
    with pytest.raises(GovernanceError, match="server.password"):
        finalize_handoff(source, paths, tmp_path / "sops")
    assert source.is_file()


def test_finalize_deletes_handoff_only_after_every_evidence_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "envs.txt"
    source.write_text("opaque", encoding="utf-8")
    paths = BootstrapPaths.under(tmp_path / "private")
    metadata = {
        "rotation": {
            "server.password": "verified",
            "bailian.api_key": "verified",
            "langsmith.api_key": "verified",
        },
        "host_key_verified": True,
        "ssh_key_verified": True,
        "capability_reprobe_match": True,
    }
    monkeypatch.setattr("faultwitness_dev.bootstrap.validate_migration", lambda *_: metadata)
    finalize_handoff(source, paths, tmp_path / "sops")
    assert not source.exists()
    written = json.loads(paths.metadata_file.read_text(encoding="utf-8"))
    assert written["handoff_deleted"] is True


def test_capability_report_is_deterministic_and_rejects_sensitive_fields() -> None:
    candidate = "a" * 40
    first = canonical_capability_report(capability_document(), candidate)
    second = canonical_capability_report(capability_document(), candidate)
    assert first == second
    assert_no_sensitive_capability_fields(first)

    unsafe = json.loads(json.dumps(first))
    unsafe["capabilities"]["host_fingerprint"] = "not-public"
    with pytest.raises(GovernanceError, match="forbidden field"):
        assert_no_sensitive_capability_fields(unsafe)


def test_capability_eval_enforces_frozen_server_floor() -> None:
    candidate = "a" * 40
    report = canonical_capability_report(capability_document(), candidate)
    validate_capability_baseline(report, candidate)

    failed = capability_document()
    failed["cpu_count"] = 31
    with pytest.raises(GovernanceError, match="cpu_count"):
        validate_capability_baseline(canonical_capability_report(failed, candidate), candidate)


def test_host_key_acceptance_requires_exact_out_of_band_fingerprint(tmp_path: Path) -> None:
    paths = BootstrapPaths.under(tmp_path / "private")
    candidate = paths.known_hosts_file.with_suffix(".candidate")
    candidate.parent.mkdir(parents=True)
    encoded = base64.b64encode(b"synthetic-ed25519-key-blob").decode("ascii")
    candidate.write_text(f"[example.invalid]:22 ssh-ed25519 {encoded}\n", encoding="utf-8")
    paths.metadata_file.parent.mkdir(parents=True)
    paths.metadata_file.write_text(json.dumps({"host_key_verified": False}), encoding="utf-8")
    fingerprint = host_key_fingerprint(candidate.read_text(encoding="utf-8"))

    with pytest.raises(GovernanceError, match="does not match"):
        accept_host_key_candidate(paths, "SHA256:" + "A" * 43)
    assert not paths.known_hosts_file.exists()

    accept_host_key_candidate(paths, fingerprint)
    assert paths.known_hosts_file.is_file()
    metadata = json.loads(paths.metadata_file.read_text(encoding="utf-8"))
    assert metadata["host_key_verified"] is True
    assert "fingerprint" not in json.dumps(metadata)
