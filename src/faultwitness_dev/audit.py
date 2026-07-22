from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from shutil import which
from typing import Any

from faultwitness_dev.checks import repository_files
from faultwitness_dev.errors import GovernanceError

TEXT_SUFFIXES = {
    "",
    ".cmd",
    ".json",
    ".md",
    ".mjs",
    ".ps1",
    ".py",
    ".sh",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
ALLOWED_LICENSES = {
    "0BSD",
    "Apache-2.0",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "CC-BY-4.0",
    "EPL-2.0",
    "ISC",
    "MIT",
    "MPL-2.0",
    "OFL-1.1",
    "PSF-2.0",
    "Python-2.0",
    "Unlicense",
}
LICENSE_TOKEN = re.compile(r"[A-Za-z0-9.-]+")
ACTION_USE = re.compile(r"^\s*-?\s*uses:\s*([^\s#]+)", re.MULTILINE)
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class Component:
    ecosystem: str
    name: str
    version: str
    license_expression: str

    @property
    def bom_ref(self) -> str:
        return f"pkg:{self.ecosystem}/{self.name}@{self.version}"


def _run_json(command: list[str], root: Path) -> Any:
    executable = which(command[0])
    if executable is None:
        raise GovernanceError(f"required executable not found: {command[0]}")
    result = subprocess.run(
        [executable, *command[1:]],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(result.stdout)


def _run_locked(command: list[str], root: Path) -> None:
    executable = which(command[0])
    if executable is None:
        raise GovernanceError(f"required executable not found: {command[0]}")
    result = subprocess.run([executable, *command[1:]], cwd=root)
    if result.returncode:
        raise GovernanceError(f"lock verification failed: {' '.join(command)}")


def _license_is_allowed(expression: str) -> bool:
    tokens = {
        token
        for token in LICENSE_TOKEN.findall(expression)
        if token.upper() not in {"AND", "OR", "WITH"}
    }
    return bool(tokens) and tokens.issubset(ALLOWED_LICENSES)


def _normalize_license(expression: str) -> str:
    aliases = {
        "BSD License": "BSD-3-Clause",
    }
    return aliases.get(expression.strip(), expression.strip())


def _license_from_file(package_path: Path) -> str | None:
    candidates = sorted(
        path
        for path in package_path.iterdir()
        if path.is_file() and path.name.lower().startswith(("license", "licence", "copying"))
    )
    for path in candidates:
        text = path.read_text(encoding="utf-8", errors="ignore")[:1000].lower()
        if "mit license" in text:
            return "MIT"
        if "apache license" in text and "version 2.0" in text:
            return "Apache-2.0"
        if "bsd 3-clause" in text:
            return "BSD-3-Clause"
        if "bsd 2-clause" in text:
            return "BSD-2-Clause"
    return None


def python_components() -> list[Component]:
    components: list[Component] = []
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata.get("Name")
        if not name:
            continue
        expression = distribution.metadata.get("License-Expression")
        if not expression:
            license_value = distribution.metadata.get("License")
            if license_value and "::" not in license_value:
                expression = license_value
        if not expression:
            classifiers = distribution.metadata.get_all("Classifier") or []
            expressions = [
                item.rsplit("::", 1)[-1].strip()
                for item in classifiers
                if "License ::" in item
            ]
            expression = " OR ".join(expressions)
        components.append(
            Component(
                "pypi",
                name,
                distribution.version,
                _normalize_license(expression or "Unknown"),
            )
        )
    return components


def node_components(root: Path) -> list[Component]:
    license_groups = _run_json(["pnpm", "licenses", "list", "--json"], root)
    components: list[Component] = []
    for group_expression, packages in license_groups.items():
        for package in packages:
            expression = group_expression
            if expression == "Unknown":
                paths = [Path(item) for item in package.get("paths", [])]
                expression = next(
                    (
                        detected
                        for detected in (_license_from_file(path) for path in paths)
                        if detected
                    ),
                    "Unknown",
                )
            for version in package["versions"]:
                components.append(
                    Component("npm", package["name"], version, _normalize_license(expression))
                )
    return components


def validate_licenses(components: list[Component]) -> None:
    rejected = sorted(
        f"{item.bom_ref} ({item.license_expression})"
        for item in components
        if not _license_is_allowed(item.license_expression)
    )
    if rejected:
        raise GovernanceError("incompatible or unknown licenses: " + ", ".join(rejected))


def validate_action_pins(root: Path) -> None:
    violations: list[str] = []
    for path in sorted((root / ".github" / "workflows").glob("*.y*ml")):
        text = path.read_text(encoding="utf-8")
        for action in ACTION_USE.findall(text):
            if action.startswith("./"):
                continue
            revision = action.rsplit("@", 1)[-1] if "@" in action else ""
            if not FULL_SHA.fullmatch(revision):
                violations.append(f"{path.relative_to(root).as_posix()}: {action}")
    if violations:
        raise GovernanceError("GitHub Actions must use full commit SHAs: " + ", ".join(violations))


def validate_source_ownership(root: Path) -> None:
    unowned = sorted(
        path.relative_to(root).as_posix()
        for path in (root / "src").rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and "faultwitness_dev" not in path.parts
    )
    if unowned:
        raise GovernanceError("unowned source files: " + ", ".join(unowned))


def _secret_patterns() -> list[tuple[str, re.Pattern[str]]]:
    return [
        (
            "private-key",
            re.compile("-----BEGIN " + r"(?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        ),
        ("github-token", re.compile("gh" + r"[pousr]_[A-Za-z0-9]{30,}")),
        ("openai-key", re.compile("sk" + r"-(?:proj-)?[A-Za-z0-9_-]{20,}")),
        ("langsmith-key", re.compile("lsv2_" + r"pt_[A-Za-z0-9_-]{20,}")),
        ("aws-access-key", re.compile("AKIA" + r"[A-Z0-9]{16}")),
        (
            "credential-assignment",
            re.compile(
                r"(?i)(?:password|passwd|api[_-]?key|access[_-]?token|client[_-]?secret)"
                r"\s*[:=]\s*['\"]?(?!example|placeholder|not_applicable|none|null)"
                r"[A-Za-z0-9_+/.=-]{12,}"
            ),
        ),
    ]


def scan_publication_boundary(root: Path, paths: list[Path] | None = None) -> None:
    violations: list[str] = []
    absolute_path = re.compile(
        r"(?:[A-Za-z]:[\\/](?:Users|项目|Projects|repos)[\\/]|/(?:Users|home)/[^/\s]+/)"
    )
    for path in paths or repository_files(root):
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {"Makefile", ".nvmrc"}:
            continue
        relative = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8", errors="strict")
        for line_number, line in enumerate(text.splitlines(), 1):
            if absolute_path.search(line):
                violations.append(f"absolute-local-path:{relative}:{line_number}")
            for name, pattern in _secret_patterns():
                if pattern.search(line):
                    violations.append(f"{name}:{relative}:{line_number}")
    if violations:
        raise GovernanceError("publication boundary violations: " + ", ".join(violations))


def build_sbom(components: list[Component], candidate_sha: str) -> dict[str, Any]:
    unique = {item.bom_ref: item for item in components}
    if len(unique) != len(components):
        duplicates = sorted(
            ref
            for ref in {item.bom_ref for item in components}
            if sum(component.bom_ref == ref for component in components) > 1
        )
        raise GovernanceError("duplicate SBOM components: " + ", ".join(duplicates))
    serial = hashlib.sha256(candidate_sha.encode()).hexdigest()
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": (
            f"urn:uuid:{serial[:8]}-{serial[8:12]}-{serial[12:16]}-"
            f"{serial[16:20]}-{serial[20:32]}"
        ),
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(UTC).isoformat(),
            "component": {
                "type": "application",
                "name": "faultwitness",
                "version": "0.0.0",
                "properties": [{"name": "faultwitness:candidate-sha", "value": candidate_sha}],
            },
        },
        "components": [
            {
                "type": "library",
                "bom-ref": item.bom_ref,
                "name": item.name,
                "version": item.version,
                "purl": item.bom_ref,
                "licenses": [{"expression": item.license_expression}],
            }
            for item in sorted(components, key=lambda value: value.bom_ref)
        ],
    }


def validate_sbom(document: dict[str, Any]) -> None:
    if document.get("bomFormat") != "CycloneDX" or document.get("specVersion") != "1.6":
        raise GovernanceError("SBOM must be CycloneDX 1.6")
    components = document.get("components", [])
    refs = [item.get("bom-ref") for item in components]
    if not components or None in refs or len(refs) != len(set(refs)):
        raise GovernanceError("SBOM components must be non-empty and uniquely referenced")
    if any(not item.get("version") or not item.get("licenses") for item in components):
        raise GovernanceError("every SBOM component needs a version and license")


def candidate_sha(root: Path) -> str:
    configured = os.environ.get("FW_CANDIDATE_SHA")
    if configured:
        if not FULL_SHA.fullmatch(configured):
            raise GovernanceError("FW_CANDIDATE_SHA must be a full 40-character commit SHA")
        return configured
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout.strip()


def audit_repository(root: Path, output_dir: Path | None = None) -> dict[str, Any]:
    _run_locked(["uv", "lock", "--check"], root)
    _run_locked(["pnpm", "install", "--lockfile-only", "--frozen-lockfile"], root)
    scan_publication_boundary(root)
    validate_action_pins(root)
    validate_source_ownership(root)
    components = python_components() + node_components(root)
    validate_licenses(components)
    revision = candidate_sha(root)
    sbom = build_sbom(components, revision)
    validate_sbom(sbom)
    output = output_dir or root / ".audit"
    output.mkdir(parents=True, exist_ok=True)
    (output / "sbom.cdx.json").write_text(
        json.dumps(sbom, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    summary = {
        "candidate_sha": revision,
        "status": "pass",
        "checks": {
            "action_sha_pins": "pass",
            "licenses": "pass",
            "lockfiles": "pass",
            "publication_boundary": "pass",
            "source_ownership": "pass",
            "sbom": "pass",
        },
        "component_count": len(components),
    }
    (output / "audit-summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def validate_g00_closure_documents(
    state: dict[str, Any],
    gate: dict[str, Any],
    iterations: list[dict[str, Any]],
    manifests: list[dict[str, Any]],
) -> None:
    if state.get("active_gate") != "G00" or state.get("active_gate_status") != "in_progress":
        raise GovernanceError("G00 closure requires the active Gate to be in progress")
    if state.get("active_iteration") is not None or state.get("next_iteration") is not None:
        raise GovernanceError("G00 closure requires no active or pending Iteration")
    if gate.get("status") != "in_progress":
        raise GovernanceError("G00 Gate record must be in progress before closure")
    if gate.get("waivers"):
        raise GovernanceError("G00 closure does not permit waivers")

    expected = set(gate["iterations"])
    records = {record["id"]: record for record in iterations}
    if set(records) != expected:
        raise GovernanceError("G00 closure requires exactly the Iterations declared by the Gate")
    incomplete = sorted(
        iteration_id
        for iteration_id, record in records.items()
        if record.get("status") != "completed" or not record.get("commit")
    )
    if incomplete:
        raise GovernanceError("G00 has incomplete Iterations: " + ", ".join(incomplete))

    manifest_by_iteration: dict[str, dict[str, Any]] = {}
    for manifest in manifests:
        iteration_id = manifest["iteration"]
        if iteration_id in manifest_by_iteration:
            raise GovernanceError(f"G00 has duplicate Eval manifests for {iteration_id}")
        manifest_by_iteration[iteration_id] = manifest
    if set(manifest_by_iteration) != expected:
        raise GovernanceError("G00 closure requires one Eval manifest per Iteration")
    unresolved = sorted(
        iteration_id
        for iteration_id, manifest in manifest_by_iteration.items()
        if manifest.get("status") != "pass" or manifest.get("open_evidence")
    )
    if unresolved:
        raise GovernanceError("G00 has unresolved Eval evidence: " + ", ".join(unresolved))


def validate_g00_closure_readiness(root: Path) -> str:
    from faultwitness_dev.schemas import load_data

    state = load_data(root / "PROJECT_STATE.yaml")
    gate = load_data(root / "governance" / "gates" / "G00.yaml")
    iterations = [
        load_data(root / "governance" / "iterations" / f"{iteration_id}.yaml")
        for iteration_id in gate["iterations"]
    ]
    manifests = [
        load_data(root / "docs" / "evals" / f"EVAL-G00-{number:03d}" / "manifest.json")
        for number in range(1, len(gate["iterations"]) + 1)
    ]
    validate_g00_closure_documents(state, gate, iterations, manifests)
    return f"{len(iterations)} completed Iterations and {len(manifests)} passing Evals"


def check_external_links(root: Path, output_dir: Path | None = None) -> dict[str, Any]:
    import urllib.error
    import urllib.request

    urls: set[str] = set()
    pattern = re.compile(r"https?://[^\s)>]+")
    for path in repository_files(root):
        if path.suffix.lower() != ".md":
            continue
        text = path.read_text(encoding="utf-8")
        urls.update(value.rstrip(".,") for value in pattern.findall(text))
    results = []
    for url in sorted(urls):
        status: int | str
        try:
            request = urllib.request.Request(
                url,
                method="HEAD",
                headers={"User-Agent": "FaultWitness-link-audit/1.0"},
            )
            with urllib.request.urlopen(request, timeout=10) as response:
                status = response.status
        except (urllib.error.URLError, TimeoutError) as error:
            status = type(error).__name__
        results.append({"url": url, "status": status})
    report = {"blocking": False, "checked": len(results), "results": results}
    output = output_dir or root / ".audit"
    output.mkdir(parents=True, exist_ok=True)
    (output / "external-links.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return report
