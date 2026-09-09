from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from faultwitness_dev.bootstrap import (
    BootstrapPaths,
    SecretBundle,
    _ssh_base_arguments,
    accept_existing_credentials,
    accept_host_key_candidate,
    assert_no_sensitive_capability_fields,
    canonical_capability_report,
    finalize_handoff,
    host_key_fingerprint,
    migrate_handoff,
    parse_endpoint_handoff,
    parse_handoff,
    remote_probe_failure_category,
    rotate_server_endpoint,
    ssh_failure_category,
    validate_capability_baseline,
)
from faultwitness_dev.errors import GovernanceError
from faultwitness_dev.schemas import load_data


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


def test_ssh_connection_timeout_is_explicit(tmp_path: Path) -> None:
    arguments = _ssh_base_arguments(bundle(), BootstrapPaths.under(tmp_path / "private"))
    assert "ConnectTimeout=10" in arguments
    assert not any(argument.startswith("ConnectionAttempts=") for argument in arguments)


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


def test_existing_password_can_be_secured_without_mutating_its_value() -> None:
    legacy = handoff_text().replace("x" * 32, "weak", 1)
    parsed = parse_handoff(legacy)
    assert parsed.server_password == "weak"


def endpoint_handoff_text() -> str:
    return "\n".join(
        [
            "内网ip:192.0.2.50",
            "ssh 端口: 22",
            "frpc ip:198.51.100.7",
            "ssh 端口: 40760",
            "",
            "user: replacement",
            "pwd: " + "z" * 24,
        ]
    )


def test_endpoint_handoff_prefers_lan_and_binds_each_port_to_its_own_address() -> None:
    endpoints = parse_endpoint_handoff(endpoint_handoff_text())
    assert [item.label for item in endpoints] == ["lan", "relay"]
    assert (endpoints[0].host, endpoints[0].port) == ("192.0.2.50", 22)
    assert (endpoints[1].host, endpoints[1].port) == ("198.51.100.7", 40760)
    assert endpoints[0].username == "replacement"
    assert "z" * 20 not in repr(endpoints[0])


def test_endpoint_handoff_rejects_an_address_without_a_port() -> None:
    text = "\n".join(["内网ip:192.0.2.50", "user: replacement", "pwd: secret"])
    with pytest.raises(GovernanceError, match="no port for the lan address"):
        parse_endpoint_handoff(text)


def test_endpoint_handoff_rejects_missing_login_without_echoing_it() -> None:
    text = "\n".join(["内网ip:192.0.2.50", "ssh 端口: 22", "pwd: " + "z" * 24])
    with pytest.raises(GovernanceError, match="username or password") as raised:
        parse_endpoint_handoff(text)
    assert "z" * 20 not in str(raised.value)


def _rotation_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> BootstrapPaths:
    paths = BootstrapPaths.under(tmp_path / "private")
    paths.identity_file.parent.mkdir(parents=True)
    paths.identity_file.write_text("identity fixture", encoding="utf-8")
    paths.encrypted_store.parent.mkdir(parents=True, exist_ok=True)
    paths.encrypted_store.write_text("sops: old fixture\n", encoding="utf-8")
    paths.known_hosts_file.parent.mkdir(parents=True, exist_ok=True)
    paths.known_hosts_file.write_text("[192.0.2.10]:2222 ssh-ed25519 AAAA\n", encoding="utf-8")
    paths.metadata_file.parent.mkdir(parents=True, exist_ok=True)
    paths.metadata_file.write_text(
        json.dumps(
            {
                "encrypted_round_trip": "pass",
                "host_key_verified": True,
                "ssh_key_verified": True,
                "capability_reprobe_match": True,
                "host_key_verification_method": "operator_out_of_band",
                "credential_verification": {
                    "server.password": "verified_login",
                    "bailian.api_key": "verified_live_I-0014",
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "faultwitness_dev.bootstrap.derive_age_recipient", lambda *_: "age1" + "q" * 58
    )
    monkeypatch.setattr(
        "faultwitness_dev.bootstrap.encrypt_bundle", lambda *_: "sops: rotated fixture\n"
    )
    return paths


def test_rotation_retains_api_keys_and_clears_the_stale_host_pin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _rotation_paths(tmp_path, monkeypatch)
    captured: dict[str, SecretBundle] = {}

    def fake_encrypt(payload: SecretBundle, *_: object) -> str:
        captured["bundle"] = payload
        return "sops: rotated fixture\n"

    monkeypatch.setattr("faultwitness_dev.bootstrap.encrypt_bundle", fake_encrypt)
    monkeypatch.setattr(
        "faultwitness_dev.bootstrap.decrypt_bundle",
        lambda *_: captured.get("bundle", bundle()),
    )

    metadata = rotate_server_endpoint(
        paths,
        tmp_path / "sops",
        tmp_path / "age-keygen",
        host="192.0.2.50",
        port=22,
        username="replacement",
        password="w" * 24,
        reason="original host is physically unrecoverable",
        now=datetime(2026, 8, 11, tzinfo=UTC),
    )

    rotated = captured["bundle"]
    assert (rotated.server_host, rotated.server_port) == ("192.0.2.50", 22)
    assert rotated.server_username == "replacement"
    # Host-independent credentials survive so their live verification stays meaningful.
    assert rotated.bailian_api_key == bundle().bailian_api_key
    assert rotated.langsmith_api_key == bundle().langsmith_api_key
    # A new machine must re-earn trust rather than inherit it.
    assert metadata["host_key_verified"] is False
    assert metadata["ssh_key_verified"] is False
    assert metadata["capability_reprobe_match"] is False
    assert "host_key_verification_method" not in metadata
    assert metadata["credential_verification"]["server.password"] == "pending_login"
    assert metadata["credential_verification"]["bailian.api_key"] == "verified_live_I-0014"
    assert not paths.known_hosts_file.exists()
    assert paths.encrypted_store.read_text(encoding="utf-8") == "sops: rotated fixture\n"
    rotations = metadata["server_endpoint_rotations"]
    assert len(rotations) == 1
    assert rotations[0]["reason"] == "original host is physically unrecoverable"
    # The endpoint is recorded as a digest, never as a readable address.
    assert "192.0.2.50" not in paths.metadata_file.read_text(encoding="utf-8")
    assert "w" * 20 not in paths.metadata_file.read_text(encoding="utf-8")


def test_rotation_refuses_when_round_trip_evidence_is_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _rotation_paths(tmp_path, monkeypatch)
    paths.metadata_file.write_text(json.dumps({"encrypted_round_trip": "fail"}), encoding="utf-8")
    with pytest.raises(GovernanceError, match="round-trip evidence must pass"):
        rotate_server_endpoint(
            paths,
            tmp_path / "sops",
            tmp_path / "age-keygen",
            host="192.0.2.50",
            port=22,
            username="replacement",
            password="w" * 24,
            reason="unrecoverable host",
        )


def test_rotation_aborts_without_writing_when_round_trip_mismatches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _rotation_paths(tmp_path, monkeypatch)
    # Decrypt returns a different bundle than was encrypted: the store must stay untouched.
    monkeypatch.setattr("faultwitness_dev.bootstrap.decrypt_bundle", lambda *_: bundle())
    with pytest.raises(GovernanceError, match="rotated secret round-trip"):
        rotate_server_endpoint(
            paths,
            tmp_path / "sops",
            tmp_path / "age-keygen",
            host="192.0.2.50",
            port=22,
            username="replacement",
            password="w" * 24,
            reason="unrecoverable host",
        )
    assert paths.encrypted_store.read_text(encoding="utf-8") == "sops: old fixture\n"
    assert paths.known_hosts_file.exists()


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
    assert set(metadata["credential_acceptance"].values()) == {"pending_operator_confirmation"}
    assert metadata["credential_policy"] == "operator_declared_long_lived"
    assert "x" * 20 not in paths.metadata_file.read_text(encoding="utf-8")


def test_accept_existing_credentials_changes_status_without_changing_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = BootstrapPaths.under(tmp_path / "private")
    paths.metadata_file.parent.mkdir(parents=True)
    paths.metadata_file.write_text(
        json.dumps(
            {
                "encrypted_round_trip": "pass",
                "rotation": {
                    "server.password": "pending",
                    "bailian.api_key": "pending",
                    "langsmith.api_key": "pending",
                },
                "ssh_key_verified": False,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("faultwitness_dev.bootstrap.load_secret_bundle", lambda *_: bundle())

    accept_existing_credentials(paths, tmp_path / "sops")

    metadata = json.loads(paths.metadata_file.read_text(encoding="utf-8"))
    assert "rotation" not in metadata
    assert set(metadata["credential_acceptance"].values()) == {"accepted_existing"}
    assert metadata["credential_verification"]["server.password"] == "pending_login"


def test_finalize_refuses_pending_acceptance_and_preserves_handoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "envs.txt"
    source.write_text("opaque", encoding="utf-8")
    paths = BootstrapPaths.under(tmp_path / "private")
    metadata = {
        "credential_acceptance": {
            "server.password": "pending_operator_confirmation",
            "bailian.api_key": "accepted_existing",
            "langsmith.api_key": "accepted_existing",
        },
        "credential_verification": {"server.password": "verified_login"},
        "host_key_verified": True,
        "ssh_key_verified": True,
        "capability_reprobe_match": False,
    }
    monkeypatch.setattr("faultwitness_dev.bootstrap.validate_migration", lambda *_: metadata)
    with pytest.raises(GovernanceError, match="server.password"):
        finalize_handoff(source, paths, tmp_path / "sops")
    assert source.is_file()


def test_finalize_deletes_handoff_before_capability_probe_after_identity_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "envs.txt"
    source.write_text("opaque", encoding="utf-8")
    paths = BootstrapPaths.under(tmp_path / "private")
    metadata = {
        "credential_acceptance": {
            "server.password": "accepted_existing",
            "bailian.api_key": "accepted_existing",
            "langsmith.api_key": "accepted_existing",
        },
        "credential_verification": {"server.password": "verified_login"},
        "host_key_verified": True,
        "ssh_key_verified": True,
        "capability_reprobe_match": False,
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
    schema = load_data(
        Path(__file__).parents[2] / "schemas" / "bootstrap" / "capability-baseline.schema.json"
    )
    validate_capability_baseline(report, candidate, schema)

    failed = capability_document()
    failed["cpu_count"] = 31
    with pytest.raises(GovernanceError, match="cpu_count"):
        validate_capability_baseline(canonical_capability_report(failed, candidate), candidate)


def test_capability_schema_rejects_undeclared_fields() -> None:
    candidate = "a" * 40
    report = canonical_capability_report(capability_document(), candidate)
    report["private_host"] = "must-not-be-published"
    schema = load_data(
        Path(__file__).parents[2] / "schemas" / "bootstrap" / "capability-baseline.schema.json"
    )
    with pytest.raises(GovernanceError, match="Additional properties"):
        validate_capability_baseline(report, candidate, schema)


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


@pytest.mark.parametrize(
    ("stderr", "expected"),
    [
        ("Permission denied (publickey,password).", "authentication_rejected"),
        ("Host key verification failed.", "host_key_rejected"),
        ("CreateProcessW failed error:2", "askpass_unavailable"),
        ("opaque failure", "remote_command_or_transport_failed"),
    ],
)
def test_ssh_failure_category_never_echoes_raw_diagnostics(stderr: str, expected: str) -> None:
    category = ssh_failure_category(stderr)
    assert category == expected
    assert stderr not in category


@pytest.mark.parametrize(
    ("stderr", "expected"),
    [
        ("sh: python3: not found", "python3_unavailable"),
        (
            "Traceback (most recent call last):\n  <redacted>\nValueError: bad",
            "remote_probe_exception_ValueError",
        ),
        (
            "FW_PROBE_ERROR:gpu_state:TypeError",
            "remote_probe_gpu_state_TypeError",
        ),
        ("opaque transport failure", "remote_probe_transport_failed"),
    ],
)
def test_remote_probe_failure_category_is_allowlisted(stderr: str, expected: str) -> None:
    category = remote_probe_failure_category(stderr)
    assert category == expected
    assert "redacted" not in category
