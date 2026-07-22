from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from faultwitness_dev.errors import GovernanceError


def load_data(path: Path) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
        return json.loads(text) if path.suffix == ".json" else yaml.safe_load(text)
    except (OSError, json.JSONDecodeError, yaml.YAMLError) as error:
        raise GovernanceError(f"cannot parse {path}: {error}") from error


def validate_document(document: Any, schema: dict[str, Any], label: str) -> None:
    errors = sorted(
        Draft202012Validator(schema).iter_errors(document), key=lambda item: list(item.path)
    )
    if errors:
        formatted = "; ".join(
            f"{'.'.join(str(part) for part in error.path) or '<root>'}: {error.message}"
            for error in errors
        )
        raise GovernanceError(f"schema validation failed for {label}: {formatted}")


def _check_unique_ids(document: Any, label: str) -> None:
    if not isinstance(document, dict):
        return
    for key in ("requirements", "claims", "adrs"):
        records = document.get(key)
        if not isinstance(records, list):
            continue
        ids = [record.get("id") for record in records if isinstance(record, dict)]
        duplicates = sorted(item for item, count in Counter(ids).items() if item and count > 1)
        if duplicates:
            raise GovernanceError(f"duplicate IDs in {label}: {', '.join(duplicates)}")


def validate_repository_schemas(root: Path) -> dict[str, Any]:
    catalog_path = root / "governance" / "ASSETS.yaml"
    catalog = load_data(catalog_path)
    loaded: dict[str, Any] = {}
    for entry in catalog["assets"]:
        schema_path = root / entry["schema"]
        schema = load_data(schema_path)
        matches = sorted(root.glob(entry["path"]))
        if not matches:
            raise GovernanceError(f"asset pattern matched no files: {entry['path']}")
        for path in matches:
            document = load_data(path)
            label = path.relative_to(root).as_posix()
            validate_document(document, schema, label)
            _check_unique_ids(document, label)
            loaded[label] = document
    _check_cross_references(loaded)
    _check_ruleset_invariants(loaded[".github/rulesets/main.json"])
    return loaded


def _check_ruleset_invariants(ruleset: dict[str, Any]) -> None:
    rules = {rule["type"]: rule for rule in ruleset["rules"]}
    required_types = {"deletion", "non_fast_forward", "pull_request", "required_status_checks"}
    missing = sorted(required_types - set(rules))
    if missing:
        raise GovernanceError(f"main ruleset is missing rules: {missing}")
    pull_request = rules["pull_request"]["parameters"]
    if not pull_request.get("dismiss_stale_reviews_on_push"):
        raise GovernanceError("main ruleset must dismiss stale reviews")
    if not pull_request.get("required_review_thread_resolution"):
        raise GovernanceError("main ruleset must require review thread resolution")
    status_parameters = rules["required_status_checks"]["parameters"]
    contexts = {item["context"] for item in status_parameters["required_status_checks"]}
    expected = {"verify (ubuntu-latest)", "verify (windows-latest)"}
    if contexts != expected:
        raise GovernanceError(f"main ruleset status checks drifted: {sorted(contexts)}")
    if not status_parameters.get("strict_required_status_checks_policy"):
        raise GovernanceError("main ruleset must require an up-to-date branch")


def _check_cross_references(loaded: dict[str, Any]) -> None:
    state = loaded["PROJECT_STATE.yaml"]
    gates = {
        document["id"]: document
        for path, document in loaded.items()
        if path.startswith("governance/gates/")
    }
    iterations = {
        document["id"]: document
        for path, document in loaded.items()
        if path.startswith("governance/iterations/")
    }
    requirements = loaded["docs/requirements/REQUIREMENTS.yaml"]["requirements"]
    requirement_ids = {record["id"] for record in requirements}
    if state["active_gate"] not in gates:
        raise GovernanceError(f"unknown active_gate: {state['active_gate']}")
    for field in ("active_iteration", "next_iteration"):
        value = state.get(field)
        if value is not None and value not in iterations:
            raise GovernanceError(f"unknown {field}: {value}")
    for path, manifest in loaded.items():
        if not path.endswith("manifest.json"):
            continue
        if manifest["gate"] not in gates:
            raise GovernanceError(f"unknown eval gate in {path}: {manifest['gate']}")
        if manifest["iteration"] not in iterations:
            raise GovernanceError(f"unknown eval iteration in {path}: {manifest['iteration']}")
    claims = loaded["docs/claims/CLAIMS.yaml"]["claims"]
    for claim in claims:
        unknown = sorted(set(claim["requirements"]) - requirement_ids)
        if unknown:
            raise GovernanceError(f"claim {claim['id']} has unknown requirements: {unknown}")
