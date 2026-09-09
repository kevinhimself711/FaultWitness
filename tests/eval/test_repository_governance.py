from __future__ import annotations

import ast
import copy
import importlib.util
import re
from pathlib import Path

import pytest

import faultwitness_dev.checks as active_checks
from faultwitness_dev.checks import validate_current_state
from faultwitness_dev.errors import GovernanceError
from faultwitness_dev.schemas import (
    _check_adr_invariants,
    _check_architecture_invariants,
    _check_evidence_invariants,
    _check_unique_ids,
    load_data,
    validate_document,
    validate_repository_schemas,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "governance"
SCHEMAS = ROOT / "schemas" / "governance"


def test_active_governance_assets_are_valid_without_legacy_epoch() -> None:
    loaded = validate_repository_schemas(ROOT)
    assert "PROJECT_STATE.yaml" in loaded
    assert not any(path.startswith("governance/gates/") for path in loaded)
    assert not any(path.startswith("docs/evals/") for path in loaded)


def test_current_state_references_real_plan_report_and_release() -> None:
    validate_current_state(ROOT)


def test_project_state_has_one_small_v2_shape() -> None:
    state = load_data(ROOT / "PROJECT_STATE.yaml")
    assert set(state) == {
        "governance_version",
        "active_gate",
        "active_gate_status",
        "last_closed_gate",
        "active_plan",
        "active_report",
        "latest_release",
    }
    assert "active_iteration" not in state
    assert "next_iteration" not in state


def test_missing_required_project_field_is_rejected() -> None:
    state = load_data(ROOT / "PROJECT_STATE.yaml")
    state.pop("active_plan")
    schema = load_data(SCHEMAS / "project-state.schema.json")
    with pytest.raises(GovernanceError, match="required property"):
        validate_document(state, schema, "missing-active-plan")


def test_duplicate_identifier_is_rejected() -> None:
    document = load_data(FIXTURES / "duplicate_requirements.yaml")
    with pytest.raises(GovernanceError, match="duplicate IDs"):
        _check_unique_ids(document, "duplicate_requirements")


def _evidence_assets() -> tuple[list[dict], dict, dict]:
    requirements = load_data(ROOT / "docs/requirements/REQUIREMENTS.yaml")
    sources = load_data(ROOT / "docs/requirements/SOURCE_CATALOG.yaml")
    matrix = load_data(ROOT / "docs/requirements/EVIDENCE_MATRIX.yaml")
    return requirements["requirements"], sources, matrix


def test_mandatory_requirement_cannot_rely_only_on_tier_c() -> None:
    requirements, sources, matrix = _evidence_assets()
    mutated = copy.deepcopy(requirements)
    mutated[0]["source_ids"] = ["SRC-UPSTREAM-001"]
    with pytest.raises(GovernanceError, match="supported only by Tier C"):
        _check_evidence_invariants(mutated, sources, matrix)


def test_unknown_requirement_source_is_rejected() -> None:
    requirements, sources, matrix = _evidence_assets()
    mutated = copy.deepcopy(requirements)
    mutated[0]["source_ids"].append("SRC-NOT-REAL")
    with pytest.raises(GovernanceError, match="unknown sources"):
        _check_evidence_invariants(mutated, sources, matrix)


def test_architecture_retains_three_engineering_planes() -> None:
    architecture = load_data(ROOT / "docs/architecture/ARCHITECTURE.yaml")
    mutated = copy.deepcopy(architecture)
    mutated["engineering_planes"].remove("data_eval_training")
    with pytest.raises(GovernanceError, match="three mandatory engineering planes"):
        _check_architecture_invariants(mutated)


def test_cross_owner_state_write_is_rejected() -> None:
    architecture = load_data(ROOT / "docs/architecture/ARCHITECTURE.yaml")
    mutated = copy.deepcopy(architecture)
    component = next(item for item in mutated["components"] if item["id"] == "CMP-INCIDENT-CONSOLE")
    component["writes_states"].append("Incident Lifecycle")
    with pytest.raises(GovernanceError, match="cross-owner state write"):
        _check_architecture_invariants(mutated)


def test_mandatory_prohibited_path_cannot_be_removed() -> None:
    architecture = load_data(ROOT / "docs/architecture/ARCHITECTURE.yaml")
    mutated = copy.deepcopy(architecture)
    mutated["prohibited_paths"] = [
        item
        for item in mutated["prohibited_paths"]
        if item["id"] != "DENY-AGENT-DIRECT-ACTION"
    ]
    with pytest.raises(GovernanceError, match="mandatory prohibited path"):
        _check_architecture_invariants(mutated)


def test_accepted_adr_must_resolve_to_a_file() -> None:
    index = load_data(ROOT / "docs/adr/INDEX.yaml")
    mutated = copy.deepcopy(index)
    mutated["adrs"][0]["path"] = "docs/adr/ADR-NOT-REAL.md"
    with pytest.raises(GovernanceError, match="accepted ADR path does not exist"):
        _check_adr_invariants(ROOT, mutated)


FORBIDDEN_LIFECYCLE_MODULES = {
    "faultwitness_dev.changes",
    "faultwitness_dev.evals",
    "faultwitness_dev.g01_eval",
    "faultwitness_dev.g02_eval",
    "faultwitness_dev.model_eval",
}


def _local_module_path(module: str) -> Path | None:
    relative = Path(*module.split("."))
    module_file = ROOT / "src" / relative.with_suffix(".py")
    if module_file.is_file():
        return module_file
    package_file = ROOT / "src" / relative / "__init__.py"
    return package_file if package_file.is_file() else None


def _imports(module: str, path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported: set[str] = set()
    package = module if path.name == "__init__.py" else module.rpartition(".")[0]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
            continue
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level:
            target = importlib.util.resolve_name(
                "." * node.level + (node.module or ""), package
            )
        else:
            target = node.module or ""
        if target:
            imported.add(target)
            for alias in node.names:
                possible_submodule = f"{target}.{alias.name}"
                if _local_module_path(possible_submodule) is not None:
                    imported.add(possible_submodule)
    return {
        name
        for name in imported
        if name == "faultwitness"
        or name == "faultwitness_dev"
        or name.startswith(("faultwitness.", "faultwitness_dev."))
    }


def _cli_import_closure() -> dict[str, Path]:
    pending = ["faultwitness_dev.cli"]
    closure: dict[str, Path] = {}
    while pending:
        module = pending.pop()
        if module in closure:
            continue
        path = _local_module_path(module)
        if path is None:
            continue
        closure[module] = path
        pending.extend(sorted(_imports(module, path) - closure.keys()))
    return closure


def test_active_cli_and_pytest_imports_cannot_reach_legacy_lifecycle() -> None:
    closure = _cli_import_closure()
    assert "faultwitness_dev.cli" in closure
    assert FORBIDDEN_LIFECYCLE_MODULES.isdisjoint(closure)

    test_imports: set[str] = set()
    for path in sorted((ROOT / "tests").rglob("*.py")):
        test_imports.update(_imports("tests." + path.stem, path))
    assert FORBIDDEN_LIFECYCLE_MODULES.isdisjoint(test_imports)
    assert all(_local_module_path(module) is None for module in FORBIDDEN_LIFECYCLE_MODULES)


LEGACY_REFERENCE = re.compile(
    r"--candidate-sha|candidate_sha|candidate-binding|evaluated_revision|"
    r"evidence_head(?:_sha)?|active_iteration|eval-changed|"
    r"(?<![A-Z0-9])(?:I-[0-9]{4}|[AC]-G02-[0-9]{3})(?![A-Z0-9])",
    re.IGNORECASE,
)


def test_active_templates_entrypoints_and_ci_are_minimal() -> None:
    templates = {path.name for path in (ROOT / "docs/templates").iterdir() if path.is_file()}
    assert templates == {"ADR.example.yaml", "REQUIREMENT.example.yaml"}

    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    shim = (ROOT / "tools/bin/make.cmd").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/baseline.yml").read_text(encoding="utf-8")
    assert makefile.count("verify-fast") == 3
    assert "verify-docs:" in makefile
    assert "eval" not in makefile.lower()
    assert "Only verify-fast and verify-docs are active make targets" in shim
    assert "make verify-fast" in workflow
    assert "windows-latest" not in workflow
    assert "matrix.os" not in workflow
    assert not LEGACY_REFERENCE.search(makefile + shim + workflow)
    assert not (ROOT / ".github/rulesets/main.json").exists()


def test_verify_fast_invokes_only_active_local_checks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    commands: list[tuple[str, ...]] = []
    calls: list[str] = []
    monkeypatch.setattr(active_checks, "repository_files", lambda _root: [])
    monkeypatch.setattr(active_checks, "check_utf8", lambda *_args: calls.append("utf8"))
    monkeypatch.setattr(
        active_checks,
        "check_release_evidence",
        lambda _root: calls.append("evidence"),
    )
    monkeypatch.setattr(
        active_checks,
        "check_markdown_basics",
        lambda *_args: calls.append("markdown"),
    )
    monkeypatch.setattr(
        active_checks,
        "check_local_links",
        lambda *_args: calls.append("links"),
    )
    monkeypatch.setattr(
        active_checks,
        "validate_repository_schemas",
        lambda _root: calls.append("schemas"),
    )
    monkeypatch.setattr(
        active_checks,
        "validate_current_state",
        lambda _root: calls.append("state"),
    )
    monkeypatch.setattr(active_checks, "run_repository_audit", lambda _root: calls.append("audit"))
    monkeypatch.setattr(
        active_checks,
        "run",
        lambda command, _root: commands.append(tuple(command)),
    )
    active_checks.verify_fast(tmp_path)
    assert calls == ["utf8", "evidence"]
    assert commands == [
        ("ruff", "check", "src", "tests"),
        ("pytest", "-q"),
        ("git", "diff", "--check"),
    ]
    forbidden = ("git log", "rev-list", "eval-changed", "gate eval", "ssh", "kubectl")
    rendered = "\n".join(" ".join(command).lower() for command in commands)
    assert not any(value in rendered for value in forbidden)
