from __future__ import annotations

import ipaddress
import json
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path


def command_output(arguments: list[str]) -> str:
    result = subprocess.run(
        arguments,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def memory_total() -> int:
    text = Path("/proc/meminfo").read_text(encoding="utf-8")
    match = re.search(r"^MemTotal:\s+(\d+)\s+kB$", text, re.MULTILINE)
    return int(match.group(1)) * 1024 if match else 0


def proc_status_value(name: str) -> int:
    text = Path("/proc/self/status").read_text(encoding="utf-8")
    match = re.search(rf"^{re.escape(name)}:\s+(\d+)$", text, re.MULTILINE)
    return int(match.group(1)) if match else 0


def docker_state() -> tuple[int, int]:
    if not shutil.which("docker"):
        return 0, 0
    statuses = command_output(["docker", "ps", "--format", "{{.Status}}"])
    rows = [row for row in statuses.splitlines() if row.strip()]
    unhealthy = sum("unhealthy" in row.casefold() for row in rows)
    return len(rows), unhealthy


def protected_ports_in_use() -> bool:
    output = command_output(["ss", "-H", "-ltn"])
    ports: set[int] = set()
    for line in output.splitlines():
        fields = line.split()
        if len(fields) < 4:
            continue
        match = re.search(r":(\d+)$", fields[3])
        if match:
            ports.add(int(match.group(1)))
    return 80 in ports and 443 in ports


def docker_cidr_conflict() -> bool:
    if not shutil.which("docker"):
        return False
    identifiers = command_output(["docker", "network", "ls", "-q"]).splitlines()
    if not identifiers:
        return False
    text = command_output(["docker", "network", "inspect", *identifiers])
    try:
        networks = json.loads(text)
    except json.JSONDecodeError:
        return True
    reserved = (ipaddress.ip_network("10.42.0.0/16"), ipaddress.ip_network("10.43.0.0/16"))
    for network in networks:
        for config in network.get("IPAM", {}).get("Config", []):
            subnet = config.get("Subnet")
            if not subnet:
                continue
            try:
                parsed = ipaddress.ip_network(subnet, strict=False)
            except ValueError:
                return True
            if any(parsed.overlaps(item) for item in reserved):
                return True
    return False


def gpu_state() -> tuple[bool, str, int]:
    if not shutil.which("nvidia-smi"):
        return False, "unavailable", 0
    output = command_output(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.total",
            "--format=csv,noheader,nounits",
        ]
    )
    first = output.splitlines()[0] if output else ""
    if "," not in first:
        return False, "unavailable", 0
    model, memory_mib = (item.strip() for item in first.split(",", 1))
    return True, model, int(float(memory_mib) * 1024 * 1024)


def main() -> None:
    running, unhealthy = docker_state()
    gpu_available, gpu_model, gpu_memory = gpu_state()
    root = os.statvfs("/")
    root_filesystem = command_output(["findmnt", "-n", "-o", "FSTYPE", "/"]) or "unknown"
    user_namespace_limit = int(
        Path("/proc/sys/user/max_user_namespaces").read_text(encoding="utf-8").strip()
    )
    document = {
        "architecture": platform.machine(),
        "cpu_count": os.cpu_count() or 0,
        "memory_bytes": memory_total(),
        "kernel_release": platform.release(),
        "cgroup_version": 2 if Path("/sys/fs/cgroup/cgroup.controllers").exists() else 1,
        "kvm_available": Path("/dev/kvm").exists(),
        "seccomp_available": proc_status_value("Seccomp") > 0,
        "user_namespace_available": user_namespace_limit > 0,
        "docker_available": shutil.which("docker") is not None,
        "docker_running_count": running,
        "docker_unhealthy_count": unhealthy,
        "ports_80_443_in_use": protected_ports_in_use(),
        "k3s_available": shutil.which("k3s") is not None,
        "helm_available": shutil.which("helm") is not None,
        "gvisor_available": shutil.which("runsc") is not None,
        "kata_available": shutil.which("kata-runtime") is not None,
        "nvidia_available": gpu_available,
        "gpu_model": gpu_model,
        "gpu_memory_bytes": gpu_memory,
        "root_filesystem": root_filesystem,
        "root_total_bytes": root.f_blocks * root.f_frsize,
        "cidr_conflict_with_10_42_10_43": docker_cidr_conflict(),
    }
    print(json.dumps(document, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
