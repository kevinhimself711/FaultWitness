from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import os
import re
import secrets
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from faultwitness_dev.errors import GovernanceError

FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
AGE_RECIPIENT = re.compile(r"^age1[0-9a-z]+$")
SAFE_USERNAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,63}$")
SAFE_HOSTNAME = re.compile(
    r"^(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)*"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$"
)
REQUIRED_SECRET_NAMES = (
    "server.host",
    "server.port",
    "server.username",
    "server.password",
    "bailian.api_key",
    "langsmith.api_key",
)


@dataclass(frozen=True, repr=False)
class SecretBundle:
    server_host: str
    server_port: int
    server_username: str
    server_password: str
    bailian_api_key: str
    langsmith_api_key: str

    def __repr__(self) -> str:
        return "SecretBundle(<redacted>)"

    def to_document(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0.0",
            "server": {
                "host": self.server_host,
                "port": self.server_port,
                "username": self.server_username,
                "password": self.server_password,
            },
            "bailian": {"api_key": self.bailian_api_key},
            "langsmith": {"api_key": self.langsmith_api_key},
        }

    @classmethod
    def from_document(cls, document: dict[str, Any]) -> SecretBundle:
        try:
            server = document["server"]
            bundle = cls(
                server_host=str(server["host"]),
                server_port=int(server["port"]),
                server_username=str(server["username"]),
                server_password=str(server["password"]),
                bailian_api_key=str(document["bailian"]["api_key"]),
                langsmith_api_key=str(document["langsmith"]["api_key"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise GovernanceError("secret document does not match the required schema") from error
        validate_bundle(bundle)
        return bundle


@dataclass(frozen=True)
class BootstrapPaths:
    config_root: Path
    identity_file: Path
    encrypted_store: Path
    metadata_file: Path
    ssh_private_key: Path
    known_hosts_file: Path
    private_evidence_dir: Path

    @classmethod
    def defaults(cls) -> BootstrapPaths:
        appdata = os.environ.get("APPDATA")
        if not appdata:
            raise GovernanceError("APPDATA is required for the private bootstrap store")
        root = Path(appdata) / "FaultWitness"
        return cls(
            config_root=root,
            identity_file=root / "keys" / "age" / "identity.txt",
            encrypted_store=root / "secrets" / "faultwitness.secrets.yaml",
            metadata_file=root / "state" / "bootstrap-metadata.json",
            ssh_private_key=root / "keys" / "ssh" / "faultwitness_ed25519",
            known_hosts_file=root / "ssh" / "known_hosts",
            private_evidence_dir=root / "evidence" / "I-0007",
        )

    @classmethod
    def under(cls, root: Path) -> BootstrapPaths:
        return cls(
            config_root=root,
            identity_file=root / "keys" / "age" / "identity.txt",
            encrypted_store=root / "secrets" / "faultwitness.secrets.yaml",
            metadata_file=root / "state" / "bootstrap-metadata.json",
            ssh_private_key=root / "keys" / "ssh" / "faultwitness_ed25519",
            known_hosts_file=root / "ssh" / "known_hosts",
            private_evidence_dir=root / "evidence" / "I-0007",
        )


def default_sops_executable() -> Path:
    local_appdata = os.environ.get("LOCALAPPDATA")
    if not local_appdata:
        raise GovernanceError("LOCALAPPDATA is required for the pinned SOPS executable")
    return Path(local_appdata) / "FaultWitness" / "tools" / "sops" / "3.13.2" / "sops.exe"


def default_age_keygen_executable() -> Path:
    local_appdata = os.environ.get("LOCALAPPDATA")
    if not local_appdata:
        raise GovernanceError("LOCALAPPDATA is required for the pinned Age executable")
    return (
        Path(local_appdata)
        / "FaultWitness"
        / "tools"
        / "age"
        / "1.3.1"
        / "age-keygen.exe"
    )


def default_ssh_askpass_executable() -> Path:
    local_appdata = os.environ.get("LOCALAPPDATA")
    if not local_appdata:
        raise GovernanceError("LOCALAPPDATA is required for the SSH askpass helper")
    return (
        Path(local_appdata)
        / "FaultWitness"
        / "tools"
        / "ssh-askpass"
        / "1.0.0"
        / "faultwitness-ssh-askpass.exe"
    )


def _value_after_separator(line: str) -> str:
    for separator in ("：", ":", "="):
        if separator in line:
            return line.split(separator, 1)[1].strip()
    return ""


def _next_nonempty(lines: list[str], start: int) -> str:
    for line in lines[start:]:
        if line.strip():
            return line.strip()
    return ""


def parse_handoff(text: str) -> SecretBundle:
    values: dict[str, str] = {}
    lines = text.splitlines()
    for index, raw_line in enumerate(lines):
        line = raw_line.strip()
        lowered = line.casefold()
        if not line:
            continue
        if "服务器" in line and "ip" in lowered:
            values["server.host"] = _value_after_separator(line)
        elif "端口" in line:
            values["server.port"] = _value_after_separator(line)
        elif "用户" in line or "账号" in line:
            values["server.username"] = _value_after_separator(line)
        elif "密码" in line:
            values["server.password"] = _value_after_separator(line)
        elif "百炼" in line and ("key" in lowered or "密钥" in line):
            value = _value_after_separator(line)
            if not value:
                match = re.search(r"(?i)(?:key|密钥)\s+(.+)$", line)
                value = match.group(1).strip() if match else ""
            values["bailian.api_key"] = value
        elif "langsmith" in lowered:
            value = _value_after_separator(line) or _next_nonempty(lines, index + 1)
            values["langsmith.api_key"] = value

    missing = [name for name in REQUIRED_SECRET_NAMES if not values.get(name)]
    if missing:
        raise GovernanceError("handoff is missing required secret fields: " + ", ".join(missing))
    try:
        port = int(values["server.port"])
    except ValueError as error:
        raise GovernanceError("server.port must be an integer") from error
    bundle = SecretBundle(
        server_host=values["server.host"],
        server_port=port,
        server_username=values["server.username"],
        server_password=values["server.password"],
        bailian_api_key=values["bailian.api_key"],
        langsmith_api_key=values["langsmith.api_key"],
    )
    validate_bundle(bundle)
    return bundle


def validate_bundle(bundle: SecretBundle) -> None:
    try:
        ipaddress.ip_address(bundle.server_host)
        host_valid = True
    except ValueError:
        host_valid = bool(SAFE_HOSTNAME.fullmatch(bundle.server_host))
    if not host_valid:
        raise GovernanceError("server.host is not a valid IP address or hostname")
    if not 1 <= bundle.server_port <= 65535:
        raise GovernanceError("server.port is outside the valid range")
    if not SAFE_USERNAME.fullmatch(bundle.server_username):
        raise GovernanceError("server.username contains unsupported characters")
    if not bundle.server_password or any(
        character in bundle.server_password for character in "\r\n\0"
    ):
        raise GovernanceError("server.password is empty or contains a forbidden control character")
    for name, value in (
        ("bailian.api_key", bundle.bailian_api_key),
        ("langsmith.api_key", bundle.langsmith_api_key),
    ):
        if len(value) < 20 or any(character.isspace() for character in value):
            raise GovernanceError(f"{name} does not meet the bootstrap shape policy")


def derive_age_recipient(age_keygen: Path, identity_file: Path) -> str:
    if not age_keygen.is_file() or not identity_file.is_file():
        raise GovernanceError("pinned age-keygen or project Age identity is missing")
    result = subprocess.run(
        [str(age_keygen), "-y", str(identity_file)],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    recipient = result.stdout.strip()
    if result.returncode or not AGE_RECIPIENT.fullmatch(recipient):
        raise GovernanceError("failed to derive a valid Age recipient")
    return recipient


def _run_sops(
    sops: Path,
    arguments: list[str],
    input_text: str,
    identity_file: Path | None = None,
) -> str:
    if not sops.is_file():
        raise GovernanceError("pinned SOPS executable is missing")
    environment = os.environ.copy()
    if identity_file is not None:
        environment["SOPS_AGE_KEY_FILE"] = str(identity_file)
    result = subprocess.run(
        [str(sops), *arguments],
        input=input_text,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=environment,
    )
    if result.returncode:
        raise GovernanceError("SOPS operation failed without emitting secret material")
    return result.stdout


def encrypt_bundle(bundle: SecretBundle, sops: Path, recipient: str) -> str:
    if not AGE_RECIPIENT.fullmatch(recipient):
        raise GovernanceError("invalid Age recipient")
    plaintext = json.dumps(bundle.to_document(), ensure_ascii=False, separators=(",", ":"))
    return _run_sops(
        sops,
        [
            "encrypt",
            "--age",
            recipient,
            "--input-type",
            "json",
            "--output-type",
            "yaml",
            "--filename-override",
            "faultwitness.secrets.yaml",
        ],
        plaintext,
    )


def decrypt_bundle(ciphertext: str, sops: Path, identity_file: Path) -> SecretBundle:
    plaintext = _run_sops(
        sops,
        [
            "decrypt",
            "--input-type",
            "yaml",
            "--output-type",
            "json",
            "--filename-override",
            "faultwitness.secrets.yaml",
        ],
        ciphertext,
        identity_file,
    )
    try:
        document = json.loads(plaintext)
    except json.JSONDecodeError as error:
        raise GovernanceError("decrypted secret document is not valid JSON") from error
    return SecretBundle.from_document(document)


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    try:
        temporary.write_text(content, encoding="utf-8", newline="\n")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def bundle_fingerprint(bundle: SecretBundle) -> bytes:
    document = json.dumps(bundle.to_document(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(document.encode("utf-8")).digest()


def migrate_handoff(
    handoff: Path,
    paths: BootstrapPaths,
    sops: Path,
    age_keygen: Path,
    now: datetime | None = None,
) -> dict[str, Any]:
    if not handoff.is_file():
        raise GovernanceError("plaintext handoff file is missing")
    if paths.encrypted_store.exists() or paths.metadata_file.exists():
        raise GovernanceError("bootstrap secret store already exists; refusing to overwrite it")
    bundle = parse_handoff(handoff.read_text(encoding="utf-8"))
    recipient = derive_age_recipient(age_keygen, paths.identity_file)
    ciphertext = encrypt_bundle(bundle, sops, recipient)
    _atomic_write(paths.encrypted_store, ciphertext)
    round_trip = decrypt_bundle(ciphertext, sops, paths.identity_file)
    if not secrets.compare_digest(bundle_fingerprint(bundle), bundle_fingerprint(round_trip)):
        raise GovernanceError("encrypted secret round-trip verification failed")
    timestamp = (now or datetime.now(UTC)).isoformat()
    metadata = {
        "schema_version": "1.0.0",
        "migrated_at": timestamp,
        "secret_names": list(REQUIRED_SECRET_NAMES),
        "encrypted_round_trip": "pass",
        "credential_policy": "operator_declared_long_lived",
        "credential_acceptance": {
            "server.password": "pending_operator_confirmation",
            "bailian.api_key": "pending_operator_confirmation",
            "langsmith.api_key": "pending_operator_confirmation",
        },
        "credential_verification": {
            "server.password": "pending_login",
            "bailian.api_key": "deferred_to_I-0014_live_eval",
            "langsmith.api_key": "deferred_to_I-0013_live_eval",
        },
        "host_key_verified": False,
        "ssh_key_verified": False,
        "capability_reprobe_match": False,
        "handoff_deleted": False,
    }
    _atomic_write(paths.metadata_file, json.dumps(metadata, indent=2) + "\n")
    return metadata


def load_private_metadata(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise GovernanceError("private bootstrap metadata is missing")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise GovernanceError("private bootstrap metadata is invalid") from error
    return document


def _write_private_metadata(paths: BootstrapPaths, metadata: dict[str, Any]) -> None:
    _atomic_write(paths.metadata_file, json.dumps(metadata, indent=2) + "\n")


def load_secret_bundle(paths: BootstrapPaths, sops: Path) -> SecretBundle:
    if not paths.encrypted_store.is_file():
        raise GovernanceError("encrypted secret store is missing")
    return decrypt_bundle(
        paths.encrypted_store.read_text(encoding="utf-8"), sops, paths.identity_file
    )


def accept_existing_credentials(paths: BootstrapPaths, sops: Path) -> None:
    load_secret_bundle(paths, sops)
    metadata = load_private_metadata(paths.metadata_file)
    if metadata.get("encrypted_round_trip") != "pass":
        raise GovernanceError("encrypted round-trip evidence must pass before acceptance")
    metadata.pop("rotation", None)
    metadata.pop("rotation_method", None)
    metadata.pop("rotated_at", None)
    metadata.pop("initial_server_password_policy", None)
    metadata["credential_policy"] = "operator_declared_long_lived"
    metadata["credential_acceptance"] = {
        name: "accepted_existing" for name in (
            "server.password",
            "bailian.api_key",
            "langsmith.api_key",
        )
    }
    metadata["credential_verification"] = {
        "server.password": (
            "verified_login" if metadata.get("ssh_key_verified") is True else "pending_login"
        ),
        "bailian.api_key": "deferred_to_I-0014_live_eval",
        "langsmith.api_key": "deferred_to_I-0013_live_eval",
    }
    metadata["credential_acceptance_method"] = "operator_confirmed_existing_long_lived"
    metadata["credentials_accepted_at"] = datetime.now(UTC).isoformat()
    _write_private_metadata(paths, metadata)


def record_live_api_verification(
    paths: BootstrapPaths, *, secret_name: str, iteration: str
) -> None:
    owners = {"langsmith.api_key": "I-0013", "bailian.api_key": "I-0014"}
    if owners.get(secret_name) != iteration:
        raise GovernanceError("API credential verification owner is invalid")
    metadata = load_private_metadata(paths.metadata_file)
    if metadata.get("credential_acceptance", {}).get(secret_name) != "accepted_existing":
        raise GovernanceError("API credential must be accepted before live verification")
    verification = metadata.setdefault("credential_verification", {})
    if verification.get("bailian.api_key") == "deferred_to_I-0013_live_eval":
        verification["bailian.api_key"] = "deferred_to_I-0014_live_eval"
    verification[secret_name] = f"verified_live_{iteration}"
    metadata.setdefault("credential_verified_at", {})[secret_name] = datetime.now(UTC).isoformat()
    _write_private_metadata(paths, metadata)


def validate_migration(paths: BootstrapPaths, sops: Path) -> dict[str, Any]:
    if not paths.encrypted_store.is_file():
        raise GovernanceError("encrypted secret store is missing")
    bundle = decrypt_bundle(
        paths.encrypted_store.read_text(encoding="utf-8"), sops, paths.identity_file
    )
    metadata = load_private_metadata(paths.metadata_file)
    if metadata.get("encrypted_round_trip") != "pass":
        raise GovernanceError("encrypted round-trip evidence is not passing")
    if set(metadata.get("secret_names", [])) != set(REQUIRED_SECRET_NAMES):
        raise GovernanceError("private metadata secret-name coverage drifted")
    validate_bundle(bundle)
    return metadata


def host_key_fingerprint(known_host_line: str) -> str:
    fields = known_host_line.split()
    if len(fields) < 3 or fields[1] != "ssh-ed25519":
        raise GovernanceError("host-key scan did not return one Ed25519 key")
    try:
        key_blob = base64.b64decode(fields[2], validate=True)
    except (ValueError, TypeError) as error:
        raise GovernanceError("host-key scan returned invalid key data") from error
    digest = base64.b64encode(hashlib.sha256(key_blob).digest()).decode("ascii").rstrip("=")
    return f"SHA256:{digest}"


def capture_host_key_candidate(paths: BootstrapPaths, sops: Path) -> str:
    bundle = load_secret_bundle(paths, sops)
    result = subprocess.run(
        [
            "ssh-keyscan",
            "-T",
            "10",
            "-p",
            str(bundle.server_port),
            "-t",
            "ed25519",
            bundle.server_host,
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    lines = [line for line in result.stdout.splitlines() if line and not line.startswith("#")]
    if result.returncode or len(lines) != 1:
        raise GovernanceError("failed to capture exactly one server Ed25519 host key")
    fingerprint = host_key_fingerprint(lines[0])
    candidate = paths.known_hosts_file.with_suffix(".candidate")
    _atomic_write(candidate, lines[0] + "\n")
    return fingerprint


def accept_host_key_candidate(paths: BootstrapPaths, expected_fingerprint: str) -> None:
    candidate = paths.known_hosts_file.with_suffix(".candidate")
    if not candidate.is_file():
        raise GovernanceError("host-key candidate is missing")
    lines = [line for line in candidate.read_text(encoding="utf-8").splitlines() if line]
    if len(lines) != 1:
        raise GovernanceError("host-key candidate must contain exactly one key")
    actual = host_key_fingerprint(lines[0])
    if not secrets.compare_digest(actual, expected_fingerprint):
        raise GovernanceError("out-of-band host fingerprint does not match the scanned key")
    _atomic_write(paths.known_hosts_file, lines[0] + "\n")
    metadata = load_private_metadata(paths.metadata_file)
    metadata["host_key_verified"] = True
    metadata["host_key_verification_method"] = "operator_out_of_band"
    _write_private_metadata(paths, metadata)


def _ssh_base_arguments(bundle: SecretBundle, paths: BootstrapPaths) -> list[str]:
    return [
        "ssh",
        "-p",
        str(bundle.server_port),
        "-o",
        "ConnectTimeout=10",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        f"UserKnownHostsFile={paths.known_hosts_file}",
        "-o",
        "LogLevel=ERROR",
    ]


def ssh_failure_category(stderr: str) -> str:
    lowered = stderr.casefold()
    categories = (
        ("permission denied", "authentication_rejected"),
        ("host key verification failed", "host_key_rejected"),
        ("connection timed out", "connection_timeout"),
        ("connection refused", "connection_refused"),
        ("connection reset", "connection_reset"),
        ("connection closed", "connection_closed"),
        ("lost connection", "connection_lost"),
        ("kex_exchange_identification", "ssh_handshake_rejected"),
        ("no route to host", "network_unreachable"),
        ("could not resolve hostname", "name_resolution_failed"),
        ("ssh_askpass", "askpass_unavailable"),
        ("read_passphrase", "askpass_unavailable"),
        ("createprocessw failed", "askpass_unavailable"),
        ("a password is required", "sudo_password_required"),
        ("incorrect password", "sudo_authentication_rejected"),
        ("is not in the sudoers", "sudo_not_authorized"),
        ("no tty present", "sudo_tty_required"),
        ("sudo:", "sudo_failed"),
        ("no such file or directory", "remote_path_missing"),
        ("path canonicalization failed", "remote_path_missing"),
        ("subsystem request failed", "sftp_unavailable"),
    )
    return next(
        (category for marker, category in categories if marker in lowered),
        "remote_command_or_transport_failed",
    )


def install_and_verify_ssh_key(
    paths: BootstrapPaths,
    sops: Path,
    askpass: Path,
) -> None:
    metadata = validate_migration(paths, sops)
    if metadata.get("host_key_verified") is not True or not paths.known_hosts_file.is_file():
        raise GovernanceError("host key must be verified out of band before authentication")
    public_key_path = paths.ssh_private_key.with_suffix(".pub")
    if not paths.ssh_private_key.is_file() or not public_key_path.is_file():
        raise GovernanceError("project SSH identity is incomplete")
    if not askpass.is_file():
        raise GovernanceError("SSH askpass helper is missing")
    bundle = load_secret_bundle(paths, sops)
    public_key = public_key_path.read_text(encoding="utf-8").strip()
    paths.private_evidence_dir.mkdir(parents=True, exist_ok=True)
    askpass_sentinel = paths.private_evidence_dir / ".askpass-invoked"
    if askpass_sentinel.exists():
        askpass_sentinel.unlink()
    environment = os.environ.copy()
    environment.update(
        {
            "SSH_ASKPASS": str(askpass),
            "SSH_ASKPASS_REQUIRE": "force",
            "DISPLAY": "faultwitness-bootstrap",
            "FW_SSH_PASSWORD": bundle.server_password,
            "FW_SSH_ASKPASS_SENTINEL": str(askpass_sentinel),
        }
    )
    install_command = (
        'umask 077; mkdir -p "$HOME/.ssh"; touch "$HOME/.ssh/authorized_keys"; '
        'chmod 700 "$HOME/.ssh"; chmod 600 "$HOME/.ssh/authorized_keys"; '
        'IFS= read -r key; grep -qxF "$key" "$HOME/.ssh/authorized_keys" || '
        'printf "%s\\n" "$key" >> "$HOME/.ssh/authorized_keys"'
    )
    password_arguments = [
        *_ssh_base_arguments(bundle, paths),
        "-o",
        "PubkeyAuthentication=no",
        "-o",
        "PreferredAuthentications=password,keyboard-interactive",
        f"{bundle.server_username}@{bundle.server_host}",
    ]
    preflight = subprocess.run(
        [*password_arguments, "true"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=environment,
    )
    if preflight.returncode:
        askpass_invoked = askpass_sentinel.is_file()
        if askpass_invoked:
            askpass_sentinel.unlink()
        environment.pop("FW_SSH_PASSWORD", None)
        environment.pop("FW_SSH_ASKPASS_SENTINEL", None)
        category = ssh_failure_category(preflight.stderr)
        if category == "authentication_rejected" and not askpass_invoked:
            category = "askpass_not_invoked"
        raise GovernanceError(
            "password-authenticated SSH preflight failed ("
            + category
            + ")"
        )
    result = subprocess.run(
        [
            *password_arguments,
            install_command,
        ],
        input=public_key + "\n",
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=environment,
    )
    environment.pop("FW_SSH_PASSWORD", None)
    environment.pop("FW_SSH_ASKPASS_SENTINEL", None)
    if askpass_sentinel.exists():
        askpass_sentinel.unlink()
    if result.returncode:
        raise GovernanceError(
            "public-key installation command failed ("
            + ssh_failure_category(result.stderr)
            + ")"
        )
    verification = subprocess.run(
        [
            *_ssh_base_arguments(bundle, paths),
            "-o",
            "BatchMode=yes",
            "-o",
            "PasswordAuthentication=no",
            "-i",
            str(paths.ssh_private_key),
            f"{bundle.server_username}@{bundle.server_host}",
            "true",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if verification.returncode:
        raise GovernanceError("dedicated SSH key verification failed")
    metadata = load_private_metadata(paths.metadata_file)
    metadata["ssh_key_verified"] = True
    metadata.setdefault("credential_verification", {})[
        "server.password"
    ] = "verified_login"
    _write_private_metadata(paths, metadata)


def run_capability_probe(
    paths: BootstrapPaths,
    sops: Path,
    probe_script: Path,
    candidate_sha: str,
    public_output: Path,
) -> dict[str, Any]:
    metadata = validate_migration(paths, sops)
    if (
        metadata.get("host_key_verified") is not True
        or metadata.get("ssh_key_verified") is not True
    ):
        raise GovernanceError("host pin and dedicated SSH key must pass before capability probes")
    if not probe_script.is_file():
        raise GovernanceError("allowlisted host probe script is missing")
    bundle = load_secret_bundle(paths, sops)
    script = probe_script.read_text(encoding="utf-8")
    arguments = [
        *_ssh_base_arguments(bundle, paths),
        "-o",
        "BatchMode=yes",
        "-o",
        "PasswordAuthentication=no",
        "-i",
        str(paths.ssh_private_key),
        f"{bundle.server_username}@{bundle.server_host}",
        "python3 -",
    ]
    reports: list[dict[str, Any]] = []
    for attempt in range(1, 3):
        result = subprocess.run(
            arguments,
            input=script,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if result.returncode:
            category = remote_probe_failure_category(result.stderr)
            paths.private_evidence_dir.mkdir(parents=True, exist_ok=True)
            _atomic_write(
                paths.private_evidence_dir / "capability-probe-failure.json",
                json.dumps(
                    {
                        "schema_version": "1.0.0",
                        "candidate_sha": candidate_sha,
                        "attempt": attempt,
                        "category": category,
                        "recorded_at": datetime.now(UTC).isoformat(),
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
            )
            raise GovernanceError(
                "allowlisted read-only host capability probe failed (" + category + ")"
            )
        try:
            raw = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise GovernanceError("host capability probe returned invalid JSON") from error
        assert_no_sensitive_capability_fields(raw)
        reports.append(canonical_capability_report(raw, candidate_sha))
    if reports[0] != reports[1]:
        raise GovernanceError("two normalized capability probes did not match")
    assert_no_sensitive_capability_fields(reports[0])
    _atomic_write(public_output, json.dumps(reports[0], indent=2, sort_keys=True) + "\n")
    paths.private_evidence_dir.mkdir(parents=True, exist_ok=True)
    _atomic_write(
        paths.private_evidence_dir / "capability-summary.json",
        json.dumps(reports[0], indent=2, sort_keys=True) + "\n",
    )
    metadata = load_private_metadata(paths.metadata_file)
    metadata["capability_reprobe_match"] = True
    _write_private_metadata(paths, metadata)
    return reports[0]


def finalize_handoff(handoff: Path, paths: BootstrapPaths, sops: Path) -> None:
    metadata = validate_migration(paths, sops)
    acceptance = metadata.get("credential_acceptance", {})
    required_credentials = ("server.password", "bailian.api_key", "langsmith.api_key")
    pending = [name for name in required_credentials if acceptance.get(name) != "accepted_existing"]
    if pending:
        raise GovernanceError("existing credentials are not accepted: " + ", ".join(pending))
    verification = metadata.get("credential_verification", {})
    if verification.get("server.password") != "verified_login":
        raise GovernanceError("existing server password has not passed login verification")
    required_flags = ("host_key_verified", "ssh_key_verified")
    missing_flags = [name for name in required_flags if metadata.get(name) is not True]
    if missing_flags:
        raise GovernanceError("bootstrap evidence is incomplete: " + ", ".join(missing_flags))
    if not handoff.is_file():
        raise GovernanceError(
            "plaintext handoff is already absent; refusing ambiguous finalization"
        )
    handoff.unlink()
    metadata["handoff_deleted"] = True
    metadata["finalized_at"] = datetime.now(UTC).isoformat()
    _atomic_write(paths.metadata_file, json.dumps(metadata, indent=2) + "\n")


def canonical_capability_report(document: dict[str, Any], candidate_sha: str) -> dict[str, Any]:
    if not FULL_SHA.fullmatch(candidate_sha):
        raise GovernanceError("candidate SHA must contain 40 lowercase hexadecimal characters")
    required = {
        "architecture",
        "cpu_count",
        "memory_bytes",
        "kernel_release",
        "cgroup_version",
        "kvm_available",
        "seccomp_available",
        "user_namespace_available",
        "docker_available",
        "docker_running_count",
        "docker_unhealthy_count",
        "ports_80_443_in_use",
        "k3s_available",
        "helm_available",
        "gvisor_available",
        "kata_available",
        "nvidia_available",
        "gpu_model",
        "gpu_memory_bytes",
        "root_filesystem",
        "root_total_bytes",
        "cidr_conflict_with_10_42_10_43",
    }
    missing = sorted(required - set(document))
    unexpected = sorted(set(document) - required)
    if missing or unexpected:
        raise GovernanceError(
            f"capability report shape drift: missing={missing}, unexpected={unexpected}"
        )
    report = {
        "schema_version": "1.0.0",
        "candidate_sha": candidate_sha,
        "capabilities": {name: document[name] for name in sorted(required)},
    }
    serialized = json.dumps(report, sort_keys=True, separators=(",", ":"))
    report["normalized_sha256"] = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return report


def assert_no_sensitive_capability_fields(document: dict[str, Any]) -> None:
    forbidden_exact = {
        "host",
        "hostname",
        "ip",
        "username",
        "user",
        "password",
        "secret",
        "token",
        "api_key",
        "host_fingerprint",
        "container_names",
    }
    forbidden_suffixes = ("_password", "_secret", "_token", "_api_key")

    def walk(value: Any, path: tuple[str, ...] = ()) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                lowered = str(key).casefold()
                if lowered in forbidden_exact or lowered.endswith(forbidden_suffixes):
                    raise GovernanceError(
                        "capability report contains a forbidden field: "
                        + ".".join((*path, str(key)))
                    )
                walk(child, (*path, str(key)))
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, (*path, str(index)))

    walk(document)


def remote_probe_failure_category(stderr: str) -> str:
    lowered = stderr.casefold()
    structured = re.search(
        r"FW_PROBE_ERROR:([a-z_]+):([A-Za-z_][A-Za-z0-9_]*)", stderr
    )
    if structured:
        return "remote_probe_" + structured.group(1) + "_" + structured.group(2)
    if "python3" in lowered and ("not found" in lowered or "not recognized" in lowered):
        return "python3_unavailable"
    if "permission denied" in lowered:
        return "remote_permission_denied"
    if "traceback (most recent call last)" in lowered:
        exception_names = re.findall(
            r"(?m)^([A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception)):", stderr
        )
        return (
            "remote_probe_exception_" + exception_names[-1]
            if exception_names
            else "remote_probe_exception"
        )
    if "connection timed out" in lowered:
        return "connection_timeout"
    return "remote_probe_transport_failed"
