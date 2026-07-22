from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import os
import re
import shlex
import subprocess
import tarfile
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from faultwitness_dev.bootstrap import (
    BootstrapPaths,
    _atomic_write,
    _ssh_base_arguments,
    default_sops_executable,
    load_private_metadata,
    load_secret_bundle,
    ssh_failure_category,
)
from faultwitness_dev.errors import GovernanceError

FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
PUBLIC_IMAGE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9./_:@-]{0,255}$")


@dataclass(frozen=True)
class InfraPaths:
    evidence_dir: Path

    @classmethod
    def defaults(cls) -> InfraPaths:
        appdata = os.environ.get("APPDATA")
        if not appdata:
            raise GovernanceError("APPDATA is required for private infrastructure evidence")
        return cls(Path(appdata) / "FaultWitness" / "evidence" / "I-0008")


def _remote_arguments(paths: BootstrapPaths) -> tuple[Any, list[str]]:
    metadata = load_private_metadata(paths.metadata_file)
    if (
        metadata.get("host_key_verified") is not True
        or metadata.get("ssh_key_verified") is not True
    ):
        raise GovernanceError("verified host pin and dedicated SSH key are required")
    bundle = load_secret_bundle(paths, default_sops_executable())
    arguments = [
        *_ssh_base_arguments(bundle, paths),
        "-o",
        "BatchMode=yes",
        "-o",
        "PasswordAuthentication=no",
        "-i",
        str(paths.ssh_private_key),
        f"{bundle.server_username}@{bundle.server_host}",
    ]
    return bundle, arguments


def run_remote_script(script: str, *, privileged: bool, timeout: int = 120) -> str:
    paths = BootstrapPaths.defaults()
    bundle, arguments = _remote_arguments(paths)
    if privileged:
        # Keep the script and password on separate channels. A NOPASSWD or cached sudo policy
        # may leave stdin unread, so feeding password + script through one stream is unsafe.
        encoded = base64.b64encode(script.encode("utf-8")).decode("ascii")
        decoder = f"printf %s {shlex.quote(encoded)} | base64 -d | /bin/sh"
        command = "sudo -k -S -p '' /bin/sh -c " + shlex.quote(decoder)
        stdin = bundle.server_password + "\n"
    else:
        command = "/bin/sh -s"
        stdin = script
    result = subprocess.run(
        [*arguments, command],
        input=stdin,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
    )
    if result.returncode:
        marker = next(
            (line for line in result.stderr.splitlines() if line.startswith("FW_")),
            "",
        )
        detail = f"; {marker}" if marker else ""
        raise GovernanceError(
            "remote infrastructure command failed ("
            + ssh_failure_category(result.stderr)
            + f"; exit={result.returncode}"
            + detail
            + ")"
        )
    return result.stdout


def inspect_infra_prerequisites(*, privileged: bool = True) -> dict[str, Any]:
    script = """set -u
step=begin
on_exit() {
    status=$?
    if test "$status" -ne 0; then
        printf 'FW_INSPECT_FAILED step=%s status=%s\\n' "$step" "$status" >&2
    fi
}
trap on_exit 0
step=identity
printf 'uid=%s\\n' "$(id -u)"
step=tools
for tool in sudo curl sha256sum sha512sum tar zstd gcc make systemctl ss python3 docker; do
    if command -v "$tool" >/dev/null 2>&1; then
        printf '%s=present\\n' "$tool"
    else
        printf '%s=absent\\n' "$tool"
    fi
done
candidate=$(apt-cache policy zstd 2>/dev/null | awk '/Candidate:/ {print $2; exit}')
printf 'zstd_candidate=%s\\n' "${candidate:-absent}"
if test -f /tmp/faultwitness-i0008/kata-static.tar.zst; then
    printf 'kata_stage_bytes=%s\\n' \
        "$(stat -c %s /tmp/faultwitness-i0008/kata-static.tar.zst)"
else
    echo kata_stage_bytes=0
fi
if test -d /tmp/faultwitness-i0008/images; then
    echo image_stage_dir=present
else
    echo image_stage_dir=absent
fi
if test -w /tmp/faultwitness-i0008/images; then
    echo image_stage_writable=yes
else
    echo image_stage_writable=no
fi
step=state
if test -x /usr/local/bin/k3s; then echo k3s=present; else echo k3s=absent; fi
if test -x /usr/local/bin/helm; then echo helm=present; else echo helm=absent; fi
if test -x /usr/local/bin/runsc; then echo runsc=present; else echo runsc=absent; fi
if command -v nvidia-container-runtime >/dev/null 2>&1; then
    echo nvidia_runtime=present
else
    echo nvidia_runtime=absent
fi
if test -x /usr/local/bin/containerd-shim-runsc-v1; then
    echo runsc_shim=present
else
    echo runsc_shim=absent
fi
containerd_config=/var/lib/rancher/k3s/agent/etc/containerd/config.toml
if grep -F 'io.containerd.runsc.v1' "$containerd_config" >/dev/null 2>&1; then
    echo runsc_config=present
else
    echo runsc_config=absent
fi
if grep -F 'nvidia-container-runtime' "$containerd_config" >/dev/null 2>&1; then
    echo nvidia_config=present
else
    echo nvidia_config=absent
fi
if grep -Eq '^version[[:space:]]*=[[:space:]]*3$' "$containerd_config" >/dev/null 2>&1; then
    echo containerd_config=v3
else
    echo containerd_config=legacy
fi
if systemctl is-active --quiet k3s.service; then
    echo k3s_service=active
else
    echo k3s_service=inactive
fi
if /usr/local/bin/k3s ctr images list -q 2>/dev/null \
    | grep -F 'rancher/mirrored-pause:3.6' >/dev/null; then
    echo pause_image=present
else
    echo pause_image=absent
fi
pause_refs=$(/usr/local/bin/k3s ctr images list -q 2>/dev/null \
    | grep -F 'rancher/mirrored-pause' | tr '\\n' ',' || true)
printf 'pause_refs=%s\\n' "${pause_refs:-none}"
if test -e /etc/rancher/k3s/config.yaml; then echo config=present; else echo config=absent; fi
if /opt/kata/runtime-rs/bin/containerd-shim-kata-v2 --version >/dev/null 2>&1; then
    echo kata_runtime_rs=compatible
else
    echo kata_runtime_rs=unavailable
fi
coredns=$(/usr/local/bin/k3s kubectl -n kube-system get deployment coredns \
    -o jsonpath='{.status.readyReplicas}' 2>/dev/null || true)
printf 'coredns_ready=%s\\n' "${coredns:-0}"
dns_endpoints=$(/usr/local/bin/k3s kubectl -n kube-system get endpoints kube-dns \
    -o jsonpath='{.subsets[0].addresses[0].ip}' 2>/dev/null || true)
if test -n "$dns_endpoints"; then echo dns_endpoint=present; else echo dns_endpoint=absent; fi
step=complete
"""
    output = run_remote_script(script, privileged=privileged)
    values = dict(line.split("=", 1) for line in output.splitlines() if "=" in line)
    required = ("curl", "sha256sum", "sha512sum", "tar", "systemctl", "ss", "python3", "docker")
    missing = [name for name in required if values.get(name) != "present"]
    if privileged and values.get("uid") != "0":
        raise GovernanceError("privileged remote runner did not obtain uid 0")
    if missing:
        raise GovernanceError("remote host is missing prerequisites: " + ", ".join(missing))
    return values


def diagnose_k3s_failure() -> dict[str, Any]:
    output = run_remote_script(
        "journalctl -u k3s.service -n 120 -o cat --no-pager; "
        "printf '\\n--- containerd ---\\n'; "
        "tail -n 120 /var/lib/rancher/k3s/agent/containerd/containerd.log 2>/dev/null || true\n",
        privileged=True,
    )
    evidence = InfraPaths.defaults().evidence_dir
    evidence.mkdir(parents=True, exist_ok=True)
    _atomic_write(evidence / "k3s-failure.log", output)
    lowered = output.casefold()
    markers = {
        "template_render": ("template", "render"),
        "toml_parse": ("toml", "parse"),
        "containerd_exit": ("containerd", "exited"),
        "runtime_config": ("runtime", "config"),
        "invalid_plugin": ("invalid plugin config",),
        "unknown_runtime": ("unknown runtime",),
        "containerd_toml": ("failed to load toml",),
        "address_conflict": ("address already in use",),
    }
    categories = [name for name, words in markers.items() if all(word in lowered for word in words)]
    return {
        "sha256": hashlib.sha256(output.encode()).hexdigest(),
        "categories": categories or ["unclassified"],
    }


def diagnose_nvidia_failure() -> dict[str, Any]:
    output = run_remote_script(
        "/usr/local/bin/k3s kubectl -n kube-system get pods "
        "-l app.kubernetes.io/name=nvidia-device-plugin -o json; "
        "printf '\\n--- describe ---\\n'; "
        "/usr/local/bin/k3s kubectl -n kube-system describe "
        "daemonset/nvidia-device-plugin; "
        "printf '\\n--- logs ---\\n'; "
        "/usr/local/bin/k3s kubectl -n kube-system logs "
        "daemonset/nvidia-device-plugin --all-containers=true --tail=100 2>&1 || true; "
        "printf '\\n--- k3s journal ---\\n'; "
        "journalctl -u k3s.service -n 200 -o cat --no-pager\n",
        privileged=True,
    )
    evidence = InfraPaths.defaults().evidence_dir
    evidence.mkdir(parents=True, exist_ok=True)
    _atomic_write(evidence / "nvidia-failure.log", output)
    lowered = output.casefold()
    markers = {
        "image_pull": ("failed to pull image",),
        "image_backoff": ("imagepullbackoff",),
        "runtime_handler": ("no runtime for",),
        "nvml": ("nvml",),
        "driver_library": ("libnvidia-ml",),
        "crash_loop": ("crashloopbackoff",),
        "admission": ("forbidden",),
    }
    categories = [name for name, words in markers.items() if all(word in lowered for word in words)]
    return {
        "sha256": hashlib.sha256(output.encode()).hexdigest(),
        "categories": categories or ["unclassified"],
    }


def diagnose_runtime_smokes() -> dict[str, Any]:
    output = run_remote_script(
        "/usr/local/bin/k3s kubectl -n fw-eval get jobs,pods -o json; "
        "printf '\\n--- events ---\\n'; "
        "/usr/local/bin/k3s kubectl -n fw-eval get events "
        "--sort-by=.metadata.creationTimestamp; "
        "printf '\\n--- logs ---\\n'; "
        "for job in smoke-runc smoke-gvisor smoke-kata smoke-nvidia; do "
        "echo FW_JOB=$job; /usr/local/bin/k3s kubectl -n fw-eval logs "
        "job/$job --tail=100 2>&1 || true; done\n",
        privileged=True,
    )
    evidence = InfraPaths.defaults().evidence_dir
    evidence.mkdir(parents=True, exist_ok=True)
    _atomic_write(evidence / "runtime-smoke-failure.log", output)
    lowered = output.casefold()
    markers = {
        "image_pull": ("failed to pull image",),
        "runtime_handler": ("no runtime for",),
        "scheduling": ("failedscheduling",),
        "quota": ("exceeded quota",),
        "pod_security": ("violates podsecurity",),
        "container_create": ("createcontainererror",),
        "sandbox": ("failedcreatepodsandbox",),
        "kata": ("kata", "error"),
    }
    categories = [name for name, words in markers.items() if all(word in lowered for word in words)]
    return {
        "sha256": hashlib.sha256(output.encode()).hexdigest(),
        "categories": categories or ["pending_or_unclassified"],
    }


def diagnose_network_matrix() -> dict[str, Any]:
    output = run_remote_script(
        "for ns in fw-control fw-data; do echo FW_NAMESPACE=$ns; "
        "/usr/local/bin/k3s kubectl -n \"$ns\" get all,networkpolicy "
        "-l faultwitness.dev/eval=EVAL-G01-002-network -o json; "
        "/usr/local/bin/k3s kubectl -n \"$ns\" get events "
        "--sort-by=.metadata.creationTimestamp; "
        "for job in network-allow network-deny-same network-deny-cross "
        "network-dns network-deny-internet; do echo FW_JOB=$job; "
        "/usr/local/bin/k3s kubectl -n \"$ns\" logs job/$job "
        "--tail=100 2>&1 || true; done; done\n",
        privileged=True,
    )
    evidence = InfraPaths.defaults().evidence_dir
    evidence.mkdir(parents=True, exist_ok=True)
    _atomic_write(evidence / "network-matrix-failure.log", output)
    lowered = output.casefold()
    markers = {
        "image": ("errimage",),
        "admission": ("forbidden",),
        "scheduling": ("failedscheduling",),
        "quota": ("exceeded quota",),
        "container": ("createcontainer",),
    }
    categories = [
        name for name, words in markers.items() if all(word in lowered for word in words)
    ]
    return {
        "sha256": hashlib.sha256(output.encode()).hexdigest(),
        "categories": categories or ["unclassified"],
    }


def resolve_public_image_digest(image: str) -> str:
    if not PUBLIC_IMAGE.fullmatch(image):
        raise GovernanceError("public image reference contains unsupported characters")
    output = run_remote_script(
        "docker manifest inspect --verbose " + shlex.quote(image) + "\n", privileged=False
    )
    try:
        document = json.loads(output)
    except json.JSONDecodeError as error:
        raise GovernanceError("registry returned an invalid image manifest") from error
    descriptors = document if isinstance(document, list) else [document]
    for descriptor in descriptors:
        platform = descriptor.get("Descriptor", {}).get("platform", {})
        if platform.get("os") == "linux" and platform.get("architecture") == "amd64":
            digest = descriptor.get("Descriptor", {}).get("digest", "")
            if re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
                return digest
    digest = document.get("Descriptor", {}).get("digest", "") if isinstance(document, dict) else ""
    if re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        return digest
    raise GovernanceError("registry manifest has no linux/amd64 digest")


def validate_preinstall_baseline(document: dict[str, Any]) -> None:
    containers = document.get("docker", {}).get("containers", [])
    failures = {
        "architecture": document.get("architecture") in {"x86_64", "amd64"},
        "kernel": str(document.get("kernel_release", "")).startswith("5.15."),
        "cgroup_v1": document.get("cgroup_version") == 1,
        "k3s_absent": document.get("k3s_installed") is False,
        "reserved_cidrs_free": document.get("reserved_cidr_overlap") is False,
        "docker_running": any(item.get("running") is True for item in containers),
        "docker_healthy": all(item.get("health") != "unhealthy" for item in containers),
    }
    failed = sorted(name for name, passed in failures.items() if not passed)
    if failed:
        raise GovernanceError("infrastructure preflight failed: " + ", ".join(failed))


def capture_preinstall_baseline(root: Path, candidate_sha: str) -> dict[str, Any]:
    if not FULL_SHA.fullmatch(candidate_sha):
        raise GovernanceError("candidate SHA must contain 40 lowercase hexadecimal characters")
    script_path = root / "deploy" / "k3s" / "capture_baseline.py"
    if not script_path.is_file():
        raise GovernanceError("allowlisted infrastructure baseline script is missing")
    stdout = run_remote_script(
        "python3 - <<'FW_BASELINE'\n" + script_path.read_text(encoding="utf-8") + "\nFW_BASELINE\n",
        privileged=True,
    )
    try:
        document = json.loads(stdout)
    except json.JSONDecodeError as error:
        raise GovernanceError("infrastructure baseline returned invalid JSON") from error
    validate_preinstall_baseline(document)
    evidence = InfraPaths.defaults().evidence_dir
    evidence.mkdir(parents=True, exist_ok=True)
    _atomic_write(
        evidence / "docker-baseline-before.json",
        json.dumps(document, indent=2, sort_keys=True) + "\n",
    )
    digest = hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    summary = {
        "schema_version": "1.0.0",
        "candidate_sha": candidate_sha,
        "captured_at": datetime.now(UTC).isoformat(),
        "baseline_sha256": digest,
        "container_count": len(document["docker"]["containers"]),
        "network_count": len(document["docker"]["networks"]),
        "unhealthy_count": sum(
            item["health"] == "unhealthy" for item in document["docker"]["containers"]
        ),
        "status": "pass",
    }
    _atomic_write(
        evidence / "preinstall-summary.json", json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )
    return summary


def render_core_installer(root: Path) -> str:
    lock = yaml.safe_load((root / "deploy" / "k3s" / "versions.lock.yaml").read_text())
    artifacts = lock["artifacts"]
    values = {
        "K3S_URL": artifacts["k3s"]["url"],
        "K3S_SHA256": artifacts["k3s"]["sha256"],
        "K3S_VERSION": artifacts["k3s"]["version"],
        "K3S_STAGE": "/tmp/faultwitness-i0008/k3s",
        "HELM_URL": artifacts["helm"]["url"],
        "HELM_SHA256": artifacts["helm"]["sha256"],
        "HELM_VERSION": artifacts["helm"]["version"],
        "HELM_STAGE": "/tmp/faultwitness-i0008/helm.tar.gz",
    }
    template = (root / "deploy" / "k3s" / "install_core.sh").read_text(encoding="utf-8")
    for name, value in values.items():
        template = template.replace(f"@{name}@", shlex.quote(str(value)))
    if re.search(r"@[A-Z0-9_]+@", template):
        raise GovernanceError("core installer contains an unresolved lock placeholder")
    return template


def _file_digest(path: Path, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _download_verified(
    url: str, expected_digest: str, destination: Path, algorithm: str = "sha256"
) -> None:
    if algorithm not in {"sha256", "sha512"}:
        raise GovernanceError("unsupported infrastructure artifact digest algorithm")
    if destination.is_file() and _file_digest(destination, algorithm) == expected_digest:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".download")
    digest = hashlib.new(algorithm)
    request = urllib.request.Request(url, headers={"User-Agent": "FaultWitness-I-0008/1.0"})
    try:
        with (
            urllib.request.urlopen(request, timeout=30) as response,
            temporary.open("wb") as target,
        ):
            while chunk := response.read(1024 * 1024):
                digest.update(chunk)
                target.write(chunk)
        if digest.hexdigest() != expected_digest:
            raise GovernanceError("downloaded infrastructure artifact checksum mismatch")
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def _ensure_crane(root: Path) -> Path:
    lock = yaml.safe_load((root / "deploy" / "k3s" / "versions.lock.yaml").read_text())
    artifact = lock["artifacts"]["crane"]
    private_root = InfraPaths.defaults().evidence_dir.parent.parent
    archive = private_root / "artifacts" / "I-0008" / "crane.tar.gz"
    executable = private_root / "tools" / "crane" / artifact["version"] / "crane.exe"
    _download_verified(artifact["url"], artifact["sha256"], archive)
    if not executable.is_file():
        executable.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive, mode="r:gz") as package:
            member = next(
                (item for item in package.getmembers() if Path(item.name).name == "crane.exe"),
                None,
            )
            if member is None or not member.isfile():
                raise GovernanceError("pinned crane archive does not contain crane.exe")
            source = package.extractfile(member)
            if source is None:
                raise GovernanceError("failed to read crane.exe from the pinned archive")
            with source, executable.open("wb") as target:
                while chunk := source.read(1024 * 1024):
                    target.write(chunk)
    return executable


def _pull_image_archive(crane: Path, image: str, destination: Path) -> None:
    marker = destination.with_suffix(".json")
    if destination.is_file() and marker.is_file():
        try:
            metadata = json.loads(marker.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            metadata = {}
        if metadata.get("image") == image and metadata.get("tar_sha256") == _file_digest(
            destination, "sha256"
        ):
            return
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".download")
    result = subprocess.run(
        [str(crane), "pull", "--platform", "linux/amd64", image, str(temporary)],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=600,
    )
    if result.returncode:
        if temporary.exists():
            temporary.unlink()
        raise GovernanceError("pinned image pull failed without importing server state")
    os.replace(temporary, destination)
    _atomic_write(
        marker,
        json.dumps(
            {"image": image, "tar_sha256": _file_digest(destination, "sha256")},
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )


def prepare_offline_base_images(root: Path, candidate_sha: str) -> dict[str, Any]:
    if not FULL_SHA.fullmatch(candidate_sha):
        raise GovernanceError("candidate SHA must contain 40 lowercase hexadecimal characters")
    lock = yaml.safe_load((root / "deploy" / "k3s" / "versions.lock.yaml").read_text())
    artifacts = lock["artifacts"]
    crane = _ensure_crane(root)
    private_root = InfraPaths.defaults().evidence_dir.parent.parent / "artifacts" / "I-0008"
    images = {
        "pause": artifacts["pause"]["image"],
        "busybox": artifacts["busybox_smoke"]["image"],
    }
    archives = {name: private_root / "images" / f"{name}.tar" for name in images}
    for name, image in images.items():
        _pull_image_archive(crane, image, archives[name])
    paths = BootstrapPaths.defaults()
    bundle, _ = _remote_arguments(paths)
    owner = shlex.quote(bundle.server_username)
    run_remote_script(
        f'group=$(id -gn {owner}); install -d -m 0700 -o {owner} -g "$group" '
        "/tmp/faultwitness-i0008/images\n",
        privileged=True,
    )
    common = [
        "-P",
        str(bundle.server_port),
        "-o",
        "ConnectTimeout=10",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        f"UserKnownHostsFile={paths.known_hosts_file}",
        "-o",
        "BatchMode=yes",
        "-o",
        "PasswordAuthentication=no",
        "-i",
        str(paths.ssh_private_key),
    ]
    for name, archive in archives.items():
        result = subprocess.run(
            [
                "scp",
                *common,
                str(archive),
                f"{bundle.server_username}@{bundle.server_host}:"
                f"/tmp/faultwitness-i0008/images/{name}.tar",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=300,
        )
        if result.returncode:
            failure_path = InfraPaths.defaults().evidence_dir / "offline-image-scp-failure.log"
            _atomic_write(failure_path, result.stderr)
            raise GovernanceError(
                "offline image staging failed (" + ssh_failure_category(result.stderr) + ")"
            )
    import_script = "set -eu\n" + "\n".join(
        f"/usr/local/bin/k3s ctr images import /tmp/faultwitness-i0008/images/{name}.tar"
        for name in archives
    )
    import_script += """
image_refs=$(/usr/local/bin/k3s ctr images list -q)
if ! /usr/local/bin/k3s ctr images list -q | grep -Fx docker.io/rancher/mirrored-pause:3.6; then
    pause_source=$(printf '%s\n' "$image_refs" \
        | grep '^docker.io/rancher/mirrored-pause:' | head -n1)
    test -n "$pause_source"
    /usr/local/bin/k3s ctr images tag "$pause_source" docker.io/rancher/mirrored-pause:3.6
fi
if ! /usr/local/bin/k3s ctr images list -q | grep -Fx docker.io/library/busybox:1.36.1; then
    busybox_source=$(printf '%s\n' "$image_refs" \
        | grep '^docker.io/library/busybox:' | head -n1)
    test -n "$busybox_source"
    /usr/local/bin/k3s ctr images tag "$busybox_source" docker.io/library/busybox:1.36.1
fi
/usr/local/bin/k3s ctr images list -q | grep -Fx docker.io/rancher/mirrored-pause:3.6
/usr/local/bin/k3s ctr images list -q | grep -Fx docker.io/library/busybox:1.36.1
"""
    run_remote_script(import_script, privileged=True, timeout=300)
    evidence = InfraPaths.defaults().evidence_dir
    summary = {
        "schema_version": "1.0.0",
        "candidate_sha": candidate_sha,
        "prepared_at": datetime.now(UTC).isoformat(),
        "images": sorted(images),
        "status": "pass",
    }
    _atomic_write(
        evidence / "offline-images-summary.json",
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
    )
    return summary


def _stage_core_artifacts(root: Path) -> None:
    lock = yaml.safe_load((root / "deploy" / "k3s" / "versions.lock.yaml").read_text())
    artifacts = lock["artifacts"]
    private_root = InfraPaths.defaults().evidence_dir.parent.parent / "artifacts" / "I-0008"
    local_files = {
        "k3s": private_root / "k3s",
        "helm.tar.gz": private_root / "helm.tar.gz",
    }
    _download_verified(artifacts["k3s"]["url"], artifacts["k3s"]["sha256"], local_files["k3s"])
    _download_verified(
        artifacts["helm"]["url"], artifacts["helm"]["sha256"], local_files["helm.tar.gz"]
    )
    paths = BootstrapPaths.defaults()
    bundle, ssh_arguments = _remote_arguments(paths)
    run_remote_script(
        "umask 077; mkdir -p /tmp/faultwitness-i0008; "
        "rm -f /tmp/faultwitness-i0008/k3s /tmp/faultwitness-i0008/helm.tar.gz\n",
        privileged=False,
    )
    common = [
        "-P",
        str(bundle.server_port),
        "-o",
        "ConnectTimeout=10",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        f"UserKnownHostsFile={paths.known_hosts_file}",
        "-o",
        "LogLevel=ERROR",
        "-o",
        "BatchMode=yes",
        "-o",
        "PasswordAuthentication=no",
        "-i",
        str(paths.ssh_private_key),
    ]
    del ssh_arguments
    for remote_name, local_path in local_files.items():
        result = subprocess.run(
            [
                "scp",
                *common,
                str(local_path),
                f"{bundle.server_username}@{bundle.server_host}:/tmp/faultwitness-i0008/{remote_name}",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=300,
        )
        if result.returncode:
            raise GovernanceError(
                "infrastructure artifact staging failed ("
                + ssh_failure_category(result.stderr)
                + ")"
            )


def _stage_gvisor_artifacts(root: Path) -> None:
    lock = yaml.safe_load((root / "deploy" / "k3s" / "versions.lock.yaml").read_text())
    artifacts = lock["artifacts"]
    private_root = InfraPaths.defaults().evidence_dir.parent.parent / "artifacts" / "I-0008"
    local_files = {
        "runsc": private_root / "runsc",
        "containerd-shim-runsc-v1": private_root / "containerd-shim-runsc-v1",
    }
    _download_verified(
        artifacts["gvisor_runsc"]["url"],
        artifacts["gvisor_runsc"]["sha512"],
        local_files["runsc"],
        "sha512",
    )
    _download_verified(
        artifacts["gvisor_containerd_shim"]["url"],
        artifacts["gvisor_containerd_shim"]["sha512"],
        local_files["containerd-shim-runsc-v1"],
        "sha512",
    )
    paths = BootstrapPaths.defaults()
    bundle, _ = _remote_arguments(paths)
    run_remote_script("umask 077; mkdir -p /tmp/faultwitness-i0008\n", privileged=False)
    common = [
        "-P",
        str(bundle.server_port),
        "-o",
        "ConnectTimeout=10",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        f"UserKnownHostsFile={paths.known_hosts_file}",
        "-o",
        "LogLevel=ERROR",
        "-o",
        "BatchMode=yes",
        "-o",
        "PasswordAuthentication=no",
        "-i",
        str(paths.ssh_private_key),
    ]
    for remote_name, local_path in local_files.items():
        result = subprocess.run(
            [
                "scp",
                *common,
                str(local_path),
                f"{bundle.server_username}@{bundle.server_host}:/tmp/faultwitness-i0008/{remote_name}",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=300,
        )
        if result.returncode:
            raise GovernanceError(
                "gVisor artifact staging failed (" + ssh_failure_category(result.stderr) + ")"
            )


def install_gvisor_runtime(root: Path, candidate_sha: str) -> dict[str, Any]:
    if not FULL_SHA.fullmatch(candidate_sha):
        raise GovernanceError("candidate SHA must contain 40 lowercase hexadecimal characters")
    lock = yaml.safe_load((root / "deploy" / "k3s" / "versions.lock.yaml").read_text())
    artifacts = lock["artifacts"]
    _stage_gvisor_artifacts(root)
    runsc_sha = shlex.quote(artifacts["gvisor_runsc"]["sha512"])
    shim_sha = shlex.quote(artifacts["gvisor_containerd_shim"]["sha512"])
    script = f"""set -eu
runsc_stage=/tmp/faultwitness-i0008/runsc
shim_stage=/tmp/faultwitness-i0008/containerd-shim-runsc-v1
printf '%s  %s\\n' {runsc_sha} "$runsc_stage" | sha512sum --check --status
printf '%s  %s\\n' {shim_sha} "$shim_stage" | sha512sum --check --status
install -m 0755 "$runsc_stage" /usr/local/bin/runsc
install -m 0755 "$shim_stage" /usr/local/bin/containerd-shim-runsc-v1
config_dir=/var/lib/rancher/k3s/agent/etc/containerd
bad_template="$config_dir/config-v3.toml.tmpl"
template="$config_dir/config.toml.tmpl"
if test -e "$bad_template" && ! grep -F 'faultwitness.dev/owner' "$bad_template" >/dev/null; then
    exit 1
fi
rm -f "$bad_template"
if ! test -e "$template"; then
    systemctl restart k3s.service
    attempt=0
    until /usr/local/bin/k3s kubectl get --raw=/readyz >/dev/null 2>&1; do
        attempt=$((attempt + 1))
        test "$attempt" -lt 60
        sleep 2
    done
    cp "$config_dir/config.toml" "$template"
fi
if ! grep -F 'faultwitness.dev/owner' "$template" >/dev/null; then
cat >>"$template" <<'FW_CONTAINERD_TEMPLATE'

# faultwitness.dev/owner=project
[plugins.'io.containerd.cri.v1.runtime'.containerd.runtimes.'runsc']
  runtime_type = "io.containerd.runsc.v1"
FW_CONTAINERD_TEMPLATE
fi
systemctl restart k3s.service
attempt=0
until /usr/local/bin/k3s kubectl get --raw=/readyz >/dev/null 2>&1; do
    attempt=$((attempt + 1))
    test "$attempt" -lt 60
    sleep 2
done
grep -F 'io.containerd.runsc.v1' /var/lib/rancher/k3s/agent/etc/containerd/config.toml >/dev/null
cat <<'FW_RUNTIMECLASS' | /usr/local/bin/k3s kubectl apply -f -
apiVersion: node.k8s.io/v1
kind: RuntimeClass
metadata:
  name: gvisor
  labels:
    app.kubernetes.io/part-of: faultwitness
handler: runsc
---
apiVersion: node.k8s.io/v1
kind: RuntimeClass
metadata:
  name: runc
  labels:
    app.kubernetes.io/part-of: faultwitness
handler: runc
FW_RUNTIMECLASS
/usr/local/bin/k3s kubectl get runtimeclass gvisor runc >/dev/null
"""
    run_remote_script(script, privileged=True, timeout=300)
    evidence = InfraPaths.defaults().evidence_dir
    summary = {
        "schema_version": "1.0.0",
        "candidate_sha": candidate_sha,
        "installed_at": datetime.now(UTC).isoformat(),
        "runtime_classes": ["runc", "gvisor"],
        "gvisor_version": artifacts["gvisor_runsc"]["version"],
        "status": "pass",
    }
    _atomic_write(
        evidence / "gvisor-install-summary.json",
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
    )
    return summary


def _stage_kata_archive(root: Path) -> None:
    lock = yaml.safe_load((root / "deploy" / "k3s" / "versions.lock.yaml").read_text())
    artifact = lock["artifacts"]["kata_static"]
    zstd = lock["artifacts"]["zstd_source"]
    private_root = InfraPaths.defaults().evidence_dir.parent.parent / "artifacts" / "I-0008"
    local_path = private_root / "kata-static-3.32.0-amd64.tar.zst"
    zstd_path = private_root / "zstd-1.5.7.tar.gz"
    _download_verified(artifact["url"], artifact["sha256"], local_path)
    _download_verified(zstd["url"], zstd["sha256"], zstd_path)
    paths = BootstrapPaths.defaults()
    bundle, _ = _remote_arguments(paths)
    run_remote_script("umask 077; mkdir -p /tmp/faultwitness-i0008\n", privileged=False)
    remote_status = run_remote_script(
        "if test -f /tmp/faultwitness-i0008/kata-static.tar.zst && "
        f"printf '%s  %s\\n' {shlex.quote(artifact['sha256'])} "
        "/tmp/faultwitness-i0008/kata-static.tar.zst | sha256sum --check --status; "
        "then echo verified; else echo missing; fi\n",
        privileged=True,
    )
    files = [(zstd_path, "zstd-source.tar.gz", 300)]
    if remote_status.strip() != "verified":
        files.append((local_path, "kata-static.tar.zst", 1800))
    for source, remote_name, timeout in files:
        result = subprocess.run(
            [
                "scp",
                "-P",
                str(bundle.server_port),
                "-o",
                "ConnectTimeout=10",
                "-o",
                "StrictHostKeyChecking=yes",
                "-o",
                f"UserKnownHostsFile={paths.known_hosts_file}",
                "-o",
                "LogLevel=ERROR",
                "-o",
                "BatchMode=yes",
                "-o",
                "PasswordAuthentication=no",
                "-i",
                str(paths.ssh_private_key),
                str(source),
                f"{bundle.server_username}@{bundle.server_host}:"
                f"/tmp/faultwitness-i0008/{remote_name}",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
        )
        if result.returncode:
            raise GovernanceError(
                "Kata artifact staging failed (" + ssh_failure_category(result.stderr) + ")"
            )


def install_kata_runtime(root: Path, candidate_sha: str) -> dict[str, Any]:
    if not FULL_SHA.fullmatch(candidate_sha):
        raise GovernanceError("candidate SHA must contain 40 lowercase hexadecimal characters")
    lock = yaml.safe_load((root / "deploy" / "k3s" / "versions.lock.yaml").read_text())
    kata = lock["artifacts"]["kata_static"]
    zstd = lock["artifacts"]["zstd_source"]
    _stage_kata_archive(root)
    kata_sha = shlex.quote(kata["sha256"])
    zstd_version = shlex.quote(zstd["version"])
    zstd_sha = shlex.quote(zstd["sha256"])
    kata_runtime_config = (
        "/opt/kata/share/defaults/kata-containers/runtime-rs/"
        "configuration-qemu-runtime-rs.toml"
    )
    script = f"""set -eu
archive=/tmp/faultwitness-i0008/kata-static.tar.zst
printf '%s  %s\\n' {kata_sha} "$archive" | sha256sum --check --status
zstd_archive=/tmp/faultwitness-i0008/zstd-source.tar.gz
printf '%s  %s\\n' {zstd_sha} "$zstd_archive" | sha256sum --check --status
zstd_root=/opt/faultwitness/tools/zstd/{zstd_version}
if ! test -x "$zstd_root/zstd"; then
    build=/opt/faultwitness/zstd-build
    rm -rf "$build"
    mkdir -p "$build" "$zstd_root"
    tar -xzf "$zstd_archive" -C "$build" --strip-components=1
    make -C "$build" -j2
    install -m 0755 "$build/programs/zstd" "$zstd_root/zstd"
    rm -rf "$build"
fi
ln -sfn "$zstd_root/zstd" /usr/local/bin/zstd
zstd --version | grep -F 'v{zstd_version}' >/dev/null
if test -e /opt/kata && ! test -f /opt/kata/.faultwitness-owner; then
    exit 1
fi
if ! test -f /opt/kata/.faultwitness-owner; then
    extract=/opt/faultwitness/kata-extract
    rm -rf "$extract"
    mkdir -p "$extract"
    tar --zstd -xf "$archive" -C "$extract"
    test -x "$extract/opt/kata/runtime-rs/bin/containerd-shim-kata-v2"
    mv "$extract/opt/kata" /opt/kata
    rm -rf "$extract"
    printf 'owner=faultwitness\\nversion=%s\\n' {shlex.quote(kata["version"])} \
        >/opt/kata/.faultwitness-owner
fi
ln -sfn /opt/kata/runtime-rs/bin/containerd-shim-kata-v2 \
    /usr/local/bin/containerd-shim-kata-v2
template=/var/lib/rancher/k3s/agent/etc/containerd/config.toml.tmpl
test -f "$template"
if ! grep -F 'io.containerd.kata.v2' "$template" >/dev/null; then
cat >>"$template" <<'FW_KATA_CONFIG'

# faultwitness.dev/runtime=kata
[plugins.'io.containerd.cri.v1.runtime'.containerd.runtimes.'kata']
  runtime_type = "io.containerd.kata.v2"
  [plugins.'io.containerd.cri.v1.runtime'.containerd.runtimes.'kata'.options]
    ConfigPath = "{kata_runtime_config}"
FW_KATA_CONFIG
fi
old_config='/opt/kata/share/defaults/kata-containers/configuration-qemu.toml'
new_config='/opt/kata/share/defaults/kata-containers/runtime-rs/configuration-qemu-runtime-rs.toml'
sed -i "s#$old_config#$new_config#" "$template"
systemctl restart k3s.service
attempt=0
until /usr/local/bin/k3s kubectl get --raw=/readyz >/dev/null 2>&1; do
    attempt=$((attempt + 1))
    test "$attempt" -lt 60
    sleep 2
done
grep -F 'io.containerd.kata.v2' \
    /var/lib/rancher/k3s/agent/etc/containerd/config.toml >/dev/null
cat <<'FW_KATA_RUNTIMECLASS' | /usr/local/bin/k3s kubectl apply -f -
apiVersion: node.k8s.io/v1
kind: RuntimeClass
metadata:
  name: kata
  labels:
    app.kubernetes.io/part-of: faultwitness
handler: kata
overhead:
  podFixed:
    memory: 160Mi
    cpu: 250m
FW_KATA_RUNTIMECLASS
/usr/local/bin/k3s kubectl get runtimeclass kata >/dev/null
"""
    run_remote_script(script, privileged=True, timeout=900)
    evidence = InfraPaths.defaults().evidence_dir
    summary = {
        "schema_version": "1.0.0",
        "candidate_sha": candidate_sha,
        "installed_at": datetime.now(UTC).isoformat(),
        "runtime_class": "kata",
        "runtime_implementation": "runtime-rs",
        "kata_version": kata["version"],
        "zstd_version": zstd["version"],
        "status": "pass",
    }
    _atomic_write(
        evidence / "kata-install-summary.json",
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
    )
    return summary


def install_nvidia_runtime(root: Path, candidate_sha: str) -> dict[str, Any]:
    if not FULL_SHA.fullmatch(candidate_sha):
        raise GovernanceError("candidate SHA must contain 40 lowercase hexadecimal characters")
    lock = yaml.safe_load((root / "deploy" / "k3s" / "versions.lock.yaml").read_text())
    artifact = lock["artifacts"]["nvidia_device_plugin"]
    manifest = (root / "deploy" / "k3s" / "nvidia-device-plugin.yaml").read_text(encoding="utf-8")
    if artifact["image"] not in manifest:
        raise GovernanceError("NVIDIA manifest image does not match the locked digest")
    script = (
        "set -eu\n"
        "cat <<'FW_NVIDIA' | /usr/local/bin/k3s kubectl apply -f -\n" + manifest + "\nFW_NVIDIA\n"
        "/usr/local/bin/k3s kubectl -n kube-system rollout status "
        "daemonset/nvidia-device-plugin --timeout=300s\n"
        "attempt=0\n"
        "while :; do\n"
        "  gpu=$(/usr/local/bin/k3s kubectl get nodes "
        "-o jsonpath='{.items[0].status.allocatable.nvidia\\.com/gpu}')\n"
        '  if test "${gpu:-0}" -ge 1 2>/dev/null; then break; fi\n'
        '  attempt=$((attempt + 1)); test "$attempt" -lt 60; sleep 2\n'
        "done\n"
    )
    run_remote_script(script, privileged=True, timeout=480)
    evidence = InfraPaths.defaults().evidence_dir
    summary = {
        "schema_version": "1.0.0",
        "candidate_sha": candidate_sha,
        "installed_at": datetime.now(UTC).isoformat(),
        "runtime_class": "nvidia",
        "device_plugin_version": artifact["version"],
        "allocatable_gpu_count_minimum": 1,
        "status": "pass",
    }
    _atomic_write(
        evidence / "nvidia-install-summary.json",
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
    )
    return summary


def run_runtime_smokes(root: Path, candidate_sha: str) -> dict[str, Any]:
    if not FULL_SHA.fullmatch(candidate_sha):
        raise GovernanceError("candidate SHA must contain 40 lowercase hexadecimal characters")
    lock = yaml.safe_load((root / "deploy" / "k3s" / "versions.lock.yaml").read_text())
    artifacts = lock["artifacts"]
    manifest = (root / "deploy" / "k3s" / "runtime-smoke.yaml").read_text(encoding="utf-8")
    busybox_tag, busybox_digest = artifacts["busybox_smoke"]["image"].split("@", 1)
    if busybox_tag not in manifest or busybox_digest not in manifest:
        raise GovernanceError("runtime smoke manifest drifted from busybox image lock")
    if artifacts["cuda_vector_add"]["image"] not in manifest:
        raise GovernanceError("runtime smoke manifest drifted from CUDA image lock")
    jobs = ("smoke-runc", "smoke-gvisor", "smoke-kata", "smoke-nvidia")
    delete_jobs = " ".join(jobs)
    script = (
        "set -eu\n"
        f"/usr/local/bin/k3s kubectl -n fw-eval delete job {delete_jobs} "
        "--ignore-not-found=true --wait=true\n"
        "cat <<'FW_SMOKES' | /usr/local/bin/k3s kubectl apply -f -\n" + manifest + "\nFW_SMOKES\n"
        "wait_job() {\n"
        "  name=$1; attempt=0\n"
        '  while test "$attempt" -lt 300; do\n'
        '    complete=$(/usr/local/bin/k3s kubectl -n fw-eval get job "$name" '
        "-o jsonpath='{.status.succeeded}' 2>/dev/null || true)\n"
        '    failed=$(/usr/local/bin/k3s kubectl -n fw-eval get job "$name" '
        "-o jsonpath='{.status.failed}' 2>/dev/null || true)\n"
        '    test "${complete:-0}" = 1 && return 0\n'
        '    test "${failed:-0}" = 0 || return 1\n'
        "    attempt=$((attempt + 1)); sleep 2\n"
        "  done\n"
        "  return 1\n"
        "}\n"
        + "\n".join(f"wait_job {job}" for job in jobs)
        + "\n"
        + "\n".join(
            f"printf 'FW_JOB={job}\\n'; /usr/local/bin/k3s kubectl -n fw-eval logs job/{job}"
            for job in jobs
        )
        + "\n"
    )
    output = run_remote_script(script, privileged=True, timeout=900)
    sections: dict[str, str] = {}
    for block in output.split("FW_JOB=")[1:]:
        name, _, logs = block.partition("\n")
        sections[name.strip()] = logs
    if set(sections) != set(jobs):
        raise GovernanceError("runtime smoke output is missing one or more job sections")
    for job in jobs[:3]:
        if "FW_SMOKE_PASS" not in sections[job]:
            raise GovernanceError(f"{job} did not complete its expected computation")
    kernel_pattern = re.compile(r"^FW_KERNEL=(\S+)$", re.MULTILINE)
    kernels = {
        job: match.group(1) for job in jobs[:3] if (match := kernel_pattern.search(sections[job]))
    }
    if set(kernels) != set(jobs[:3]):
        raise GovernanceError("runtime smoke logs are missing kernel identity evidence")
    if not kernels["smoke-runc"].startswith("5.15."):
        raise GovernanceError("runc workload did not observe the frozen host kernel")
    if kernels["smoke-gvisor"] == kernels["smoke-runc"]:
        raise GovernanceError("gVisor workload did not expose an isolated kernel view")
    if kernels["smoke-kata"] == kernels["smoke-runc"]:
        raise GovernanceError("Kata workload did not boot a guest kernel")
    if "Test PASSED" not in sections["smoke-nvidia"]:
        raise GovernanceError("NVIDIA VectorAdd did not report Test PASSED")
    evidence = InfraPaths.defaults().evidence_dir
    _atomic_write(evidence / "runtime-smoke.log", output)
    summary = {
        "schema_version": "1.0.0",
        "candidate_sha": candidate_sha,
        "completed_at": datetime.now(UTC).isoformat(),
        "runtimes": ["runc", "gvisor", "kata", "nvidia"],
        "kernel_views_distinct": True,
        "gpu_computation": "pass",
        "status": "pass",
    }
    _atomic_write(
        evidence / "runtime-smoke-summary.json",
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
    )
    return summary


def run_network_matrix(root: Path, candidate_sha: str) -> dict[str, Any]:
    if not FULL_SHA.fullmatch(candidate_sha):
        raise GovernanceError("candidate SHA must contain 40 lowercase hexadecimal characters")
    lock = yaml.safe_load((root / "deploy" / "k3s" / "versions.lock.yaml").read_text())
    busybox_tag, busybox_digest = lock["artifacts"]["busybox_smoke"]["image"].split("@", 1)
    manifest = (root / "deploy" / "k3s" / "network-smoke.yaml").read_text(encoding="utf-8")
    if busybox_tag not in manifest or busybox_digest not in manifest:
        raise GovernanceError("network smoke manifest drifted from busybox image lock")
    cases = (
        ("fw-control", "network-allow", "FW_ALLOW_PASS"),
        ("fw-control", "network-deny-same", "FW_DENY_PASS"),
        ("fw-data", "network-deny-cross", "FW_DENY_PASS"),
        ("fw-control", "network-dns", "FW_DNS_PASS"),
        ("fw-control", "network-deny-internet", "FW_DENY_PASS"),
    )
    script = (
        "set -eu\n"
        "for ns in fw-control fw-data; do "
        '/usr/local/bin/k3s kubectl -n "$ns" delete all,networkpolicy '
        "-l faultwitness.dev/eval=EVAL-G01-002-network "
        "--ignore-not-found=true --wait=true; done\n"
        "cat <<'FW_NETWORK' | /usr/local/bin/k3s kubectl apply -f -\n" + manifest + "\nFW_NETWORK\n"
        "/usr/local/bin/k3s kubectl -n fw-control rollout status "
        "deployment/network-server --timeout=180s\n"
        "wait_job() {\n"
        "  ns=$1; name=$2; attempt=0\n"
        '  while test "$attempt" -lt 120; do\n'
        '    complete=$(/usr/local/bin/k3s kubectl -n "$ns" get job "$name" '
        "-o jsonpath='{.status.succeeded}' 2>/dev/null || true)\n"
        '    failed=$(/usr/local/bin/k3s kubectl -n "$ns" get job "$name" '
        "-o jsonpath='{.status.failed}' 2>/dev/null || true)\n"
        '    test "${complete:-0}" = 1 && return 0\n'
        '    test "${failed:-0}" = 0 || return 1\n'
        "    attempt=$((attempt + 1)); sleep 2\n"
        "  done\n"
        "  return 1\n"
        "}\n"
        + "\n".join(f"wait_job {namespace} {job}" for namespace, job, _ in cases)
        + "\n"
        + "\n".join(
            f"printf 'FW_CASE={job}\\n'; /usr/local/bin/k3s kubectl -n {namespace} logs job/{job}"
            for namespace, job, _ in cases
        )
        + "\n"
    )
    output = run_remote_script(script, privileged=True, timeout=600)
    sections: dict[str, str] = {}
    for block in output.split("FW_CASE=")[1:]:
        name, _, logs = block.partition("\n")
        sections[name.strip()] = logs
    for _, job, marker in cases:
        if marker not in sections.get(job, ""):
            raise GovernanceError(f"network matrix case {job} did not emit {marker}")
    cleanup = (
        "for ns in fw-control fw-data; do "
        '/usr/local/bin/k3s kubectl -n "$ns" delete all,networkpolicy '
        "-l faultwitness.dev/eval=EVAL-G01-002-network "
        "--ignore-not-found=true --wait=true; done\n"
    )
    run_remote_script(cleanup, privileged=True, timeout=180)
    evidence = InfraPaths.defaults().evidence_dir
    _atomic_write(evidence / "network-matrix.log", output)
    summary = {
        "schema_version": "1.0.0",
        "candidate_sha": candidate_sha,
        "completed_at": datetime.now(UTC).isoformat(),
        "passed_cases": [job for _, job, _ in cases],
        "matrix_pass_rate": 1.0,
        "status": "pass",
    }
    _atomic_write(
        evidence / "network-matrix-summary.json",
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
    )
    return summary


def compare_docker_baselines(before: dict[str, Any], after: dict[str, Any]) -> None:
    def normalized(document: dict[str, Any]) -> dict[str, Any]:
        docker = document["docker"]
        return {
            "containers": docker["containers"],
            "networks": docker["networks"],
        }

    if normalized(before) != normalized(after):
        raise GovernanceError("existing Docker container or network baseline changed")


def _listener_scope(local: str) -> tuple[str, int]:
    address, separator, port_text = local.rpartition(":")
    if not separator or not port_text.isdigit():
        raise GovernanceError("listener baseline contains an invalid local endpoint")
    address = address.strip("[]")
    if address in {"*", "0.0.0.0", "::"}:
        scope = "wildcard"
    else:
        try:
            parsed = ipaddress.ip_address(address)
            if parsed.is_loopback:
                scope = "loopback"
            elif parsed.is_private or parsed.is_link_local:
                scope = "private"
            else:
                scope = "public"
        except ValueError:
            scope = "public"
    return scope, int(port_text)


def audit_runtime_coexistence(root: Path, candidate_sha: str) -> dict[str, Any]:
    if not FULL_SHA.fullmatch(candidate_sha):
        raise GovernanceError("candidate SHA must contain 40 lowercase hexadecimal characters")
    evidence = InfraPaths.defaults().evidence_dir
    before_path = evidence / "docker-baseline-before.json"
    if not before_path.is_file():
        raise GovernanceError("private preinstall Docker baseline is missing")
    before = json.loads(before_path.read_text(encoding="utf-8"))
    baseline_script = (root / "deploy" / "k3s" / "capture_baseline.py").read_text(encoding="utf-8")
    output = run_remote_script(
        "python3 - <<'FW_BASELINE'\n" + baseline_script + "\nFW_BASELINE\n",
        privileged=True,
    )
    try:
        after = json.loads(output)
    except json.JSONDecodeError as error:
        raise GovernanceError("runtime coexistence baseline returned invalid JSON") from error
    compare_docker_baselines(before, after)
    before_listeners = {(item["protocol"], item["local"]) for item in before.get("listeners", [])}
    new_listeners = [
        item
        for item in after.get("listeners", [])
        if (item["protocol"], item["local"]) not in before_listeners
    ]
    exposed = [
        {"protocol": item["protocol"], "port": _listener_scope(item["local"])[1]}
        for item in new_listeners
        if _listener_scope(item["local"])[0] in {"wildcard", "public"}
    ]
    _atomic_write(
        evidence / "docker-baseline-after-runtimes.json",
        json.dumps(after, indent=2, sort_keys=True) + "\n",
    )
    summary = {
        "schema_version": "1.0.0",
        "candidate_sha": candidate_sha,
        "audited_at": datetime.now(UTC).isoformat(),
        "docker_regression_count": 0,
        "new_nonpublic_listener_count": len(new_listeners) - len(exposed),
        "unexpected_exposed_listeners": exposed,
        "status": "pass" if not exposed else "fail",
    }
    _atomic_write(
        evidence / "coexistence-summary.json",
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
    )
    if exposed:
        ports = ", ".join(f"{item['protocol']}/{item['port']}" for item in exposed)
        raise GovernanceError("new non-loopback listeners detected: " + ports)
    return summary


def harden_runtime_listeners(candidate_sha: str) -> dict[str, Any]:
    if not FULL_SHA.fullmatch(candidate_sha):
        raise GovernanceError("candidate SHA must contain 40 lowercase hexadecimal characters")
    script = """set -eu
config=/etc/rancher/k3s/config.yaml
backup=/etc/rancher/k3s/config.yaml.before-listener-hardening
test -f "$config"
cp "$config" "$backup"
if ! grep -F 'faultwitness.dev/listener-hardening' "$config" >/dev/null; then
cat >>"$config" <<'FW_LISTENER_CONFIG'

# faultwitness.dev/listener-hardening=single-node-v1
flannel-backend: host-gw
FW_LISTENER_CONFIG
fi
recover() {
    cp "$backup" "$config"
    systemctl restart k3s.service >/dev/null 2>&1 || true
}
if ! timeout 240 systemctl restart k3s.service; then
    recover
    exit 1
fi
attempt=0
until /usr/local/bin/k3s kubectl get --raw=/readyz >/dev/null 2>&1; do
    attempt=$((attempt + 1))
    if test "$attempt" -ge 60; then
        recover
        exit 1
    fi
    sleep 2
done
if ip link show flannel.1 >/dev/null 2>&1; then
    ip link delete flannel.1
    sleep 1
fi
exposed=$(ss -H -lntup | awk '$5 ~ /:8472$/ {print $5}' \
    | grep -Ev '^(127\\.0\\.0\\.1|\\[::1\\]):' || true)
if test -n "$exposed"; then
    recover
    exit 1
fi
rm -f "$backup"
"""
    run_remote_script(script, privileged=True, timeout=480)
    evidence = InfraPaths.defaults().evidence_dir
    summary = {
        "schema_version": "1.0.0",
        "candidate_sha": candidate_sha,
        "hardened_at": datetime.now(UTC).isoformat(),
        "flannel_backend": "host-gw",
        "private_cluster_ports": [2379, 2380],
        "removed_exposed_ports": [8472],
        "status": "pass",
    }
    _atomic_write(
        evidence / "listener-hardening-summary.json",
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
    )
    return summary


def recover_cluster_dns(candidate_sha: str) -> dict[str, Any]:
    if not FULL_SHA.fullmatch(candidate_sha):
        raise GovernanceError("candidate SHA must contain 40 lowercase hexadecimal characters")
    script = """set -eu
/usr/local/bin/k3s kubectl -n kube-system rollout restart deployment/coredns
/usr/local/bin/k3s kubectl -n kube-system rollout status deployment/coredns --timeout=240s
endpoint=$(/usr/local/bin/k3s kubectl -n kube-system get endpoints kube-dns \
    -o jsonpath='{.subsets[0].addresses[0].ip}')
test -n "$endpoint"
"""
    run_remote_script(script, privileged=True, timeout=360)
    evidence = InfraPaths.defaults().evidence_dir
    summary = {
        "schema_version": "1.0.0",
        "candidate_sha": candidate_sha,
        "recovered_at": datetime.now(UTC).isoformat(),
        "ready_replicas_minimum": 1,
        "endpoint": "present",
        "status": "pass",
    }
    _atomic_write(
        evidence / "cluster-dns-recovery-summary.json",
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
    )
    return summary


def install_k3s_core(root: Path, candidate_sha: str) -> dict[str, Any]:
    if not FULL_SHA.fullmatch(candidate_sha):
        raise GovernanceError("candidate SHA must contain 40 lowercase hexadecimal characters")
    evidence = InfraPaths.defaults().evidence_dir
    before_path = evidence / "docker-baseline-before.json"
    if not before_path.is_file():
        raise GovernanceError("private preinstall Docker baseline is missing")
    before = json.loads(before_path.read_text(encoding="utf-8"))
    validate_preinstall_baseline(before)
    _stage_core_artifacts(root)
    installer = render_core_installer(root)
    foundation = (root / "deploy" / "k3s" / "foundation.yaml").read_text(encoding="utf-8")
    run_remote_script(installer, privileged=True, timeout=600)
    apply_script = (
        "set -eu\n"
        "cat >/tmp/faultwitness-foundation.yaml <<'FW_FOUNDATION'\n"
        + foundation
        + "\nFW_FOUNDATION\n"
        + "/usr/local/bin/k3s kubectl apply -f /tmp/faultwitness-foundation.yaml\n"
        + "rm -f /tmp/faultwitness-foundation.yaml\n"
    )
    run_remote_script(apply_script, privileged=True, timeout=180)
    baseline_script = (root / "deploy" / "k3s" / "capture_baseline.py").read_text(encoding="utf-8")
    stdout = run_remote_script(
        "python3 - <<'FW_BASELINE'\n" + baseline_script + "\nFW_BASELINE\n",
        privileged=True,
    )
    try:
        after = json.loads(stdout)
    except json.JSONDecodeError as error:
        raise GovernanceError(
            "postinstall infrastructure baseline returned invalid JSON"
        ) from error
    compare_docker_baselines(before, after)
    if after.get("k3s_installed") is not True or after.get("helm_installed") is not True:
        raise GovernanceError("K3s or Helm is absent after the core install")
    _atomic_write(
        evidence / "docker-baseline-after-core.json",
        json.dumps(after, indent=2, sort_keys=True) + "\n",
    )
    summary = {
        "schema_version": "1.0.0",
        "candidate_sha": candidate_sha,
        "installed_at": datetime.now(UTC).isoformat(),
        "docker_regression_count": 0,
        "container_count": len(after["docker"]["containers"]),
        "network_count": len(after["docker"]["networks"]),
        "status": "pass",
    }
    _atomic_write(
        evidence / "core-install-summary.json",
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
    )
    return summary
