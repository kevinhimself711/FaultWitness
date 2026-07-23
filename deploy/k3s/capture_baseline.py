from __future__ import annotations

import hashlib
import ipaddress
import json
import shutil
import socket
import subprocess
from pathlib import Path
from typing import Any


def run_json(arguments: list[str]) -> Any:
    result = subprocess.run(arguments, check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def cgroup_version() -> int:
    return 2 if Path("/sys/fs/cgroup/cgroup.controllers").exists() else 1


def docker_state() -> dict[str, Any]:
    if shutil.which("docker") is None:
        raise RuntimeError("docker is required")
    identifiers = subprocess.run(
        ["docker", "ps", "-aq"], check=True, capture_output=True, text=True
    ).stdout.split()
    containers = run_json(["docker", "inspect", *identifiers]) if identifiers else []
    normalized = []
    for container in containers:
        state = container["State"]
        health = state.get("Health", {}).get("Status", "none")
        normalized.append(
            {
                "id": container["Id"],
                "name": container["Name"].lstrip("/"),
                "image": container["Config"]["Image"],
                "running": state["Running"],
                "status": state["Status"],
                "health": health,
                "restart_count": container["RestartCount"],
                "ports": container["HostConfig"].get("PortBindings") or {},
                "networks": sorted(container["NetworkSettings"]["Networks"]),
            }
        )
    networks: list[dict[str, Any]] = []
    # Docker's JSON-lines formatter avoids locale-dependent table parsing.
    network_rows = subprocess.run(
        ["docker", "network", "ls", "--format", "{{json .}}"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    network_names = [json.loads(row)["Name"] for row in network_rows if row]
    if network_names:
        for network in run_json(["docker", "network", "inspect", *network_names]):
            networks.append(
                {
                    "id": network["Id"],
                    "name": network["Name"],
                    "driver": network["Driver"],
                    "subnets": sorted(
                        item["Subnet"]
                        for item in (network.get("IPAM", {}).get("Config") or [])
                        if item.get("Subnet")
                    ),
                }
            )
    return {
        "containers": sorted(normalized, key=lambda item: item["name"]),
        "networks": sorted(networks, key=lambda item: item["name"]),
    }


def listeners() -> list[dict[str, Any]]:
    result = subprocess.run(["ss", "-H", "-lntup"], check=True, capture_output=True, text=True)
    rows = []
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) >= 5:
            rows.append({"protocol": fields[0], "local": fields[4]})
    return sorted(rows, key=lambda item: (item["protocol"], item["local"]))


def main() -> None:
    docker = docker_state()
    subnets = [
        ipaddress.ip_network(subnet, strict=False)
        for network in docker["networks"]
        for subnet in network["subnets"]
    ]
    reserved = [ipaddress.ip_network("10.42.0.0/16"), ipaddress.ip_network("10.43.0.0/16")]
    document = {
        "schema_version": "1.0.0",
        "architecture": subprocess.run(
            ["uname", "-m"], check=True, capture_output=True, text=True
        ).stdout.strip(),
        "kernel_release": subprocess.run(
            ["uname", "-r"], check=True, capture_output=True, text=True
        ).stdout.strip(),
        "cgroup_version": cgroup_version(),
        "hostname_sha256": hashlib.sha256(socket.gethostname().encode()).hexdigest(),
        "k3s_installed": shutil.which("k3s") is not None,
        "helm_installed": shutil.which("helm") is not None,
        "docker": docker,
        "listeners": listeners(),
        "reserved_cidr_overlap": any(a.overlaps(b) for a in subnets for b in reserved),
    }
    print(json.dumps(document, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
