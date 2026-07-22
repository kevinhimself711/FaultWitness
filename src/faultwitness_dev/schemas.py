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
    for key in ("requirements", "claims", "adrs", "sources"):
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
    _check_adr_invariants(root, loaded["docs/adr/INDEX.yaml"])
    _check_architecture_documents(root)
    from faultwitness_dev.contracts import validate_contracts

    validate_contracts(root, loaded)
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
    expected = {
        "audit (ubuntu-latest)",
        "verify (ubuntu-latest)",
        "verify (windows-latest)",
    }
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
    source_catalog = loaded["docs/requirements/SOURCE_CATALOG.yaml"]
    evidence_matrix = loaded["docs/requirements/EVIDENCE_MATRIX.yaml"]
    _check_evidence_invariants(requirements, source_catalog, evidence_matrix)
    _check_architecture_invariants(loaded["docs/architecture/ARCHITECTURE.yaml"])
    if "docs/evals/EVAL-G00-006/WALKTHROUGHS.yaml" in loaded:
        _check_gate_walkthroughs(
            loaded["docs/evals/EVAL-G00-006/WALKTHROUGHS.yaml"],
            loaded["docs/contracts/WALKTHROUGH_BINDINGS.yaml"],
        )
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


def _check_evidence_invariants(
    requirements: list[dict[str, Any]],
    source_catalog: dict[str, Any],
    evidence_matrix: dict[str, Any],
) -> None:
    sources = source_catalog["sources"]
    source_by_id = {source["id"]: source for source in sources}

    actual_counts = {
        "job_descriptions": sum(
            source["included"] and source["kind"] == "job_description" for source in sources
        ),
        "included_interviews": sum(
            source["included"] and source["kind"] in {"interview", "interview_collection"}
            for source in sources
        ),
        "excluded_empty_interviews": sum(
            not source["included"]
            and source["kind"] in {"interview", "interview_collection"}
            for source in sources
        ),
        "technical_references": sum(
            source["included"] and source["kind"] == "technical_reference"
            for source in sources
        ),
        "upstream_reports": sum(
            source["included"] and source["kind"] == "upstream_report" for source in sources
        ),
    }
    if actual_counts != source_catalog["expected_counts"]:
        raise GovernanceError(
            f"source catalog count drift: expected {source_catalog['expected_counts']}, "
            f"got {actual_counts}"
        )

    for source in sources:
        if source["included"]:
            if not source["indexed"] or source["exclusion_reason"] is not None:
                raise GovernanceError(f"included source is not indexed cleanly: {source['id']}")
        elif source["indexed"] or not source["exclusion_reason"]:
            raise GovernanceError(f"excluded source lacks an exclusion record: {source['id']}")

    requirement_ids = {requirement["id"] for requirement in requirements}
    for requirement in requirements:
        unknown_sources = sorted(set(requirement["source_ids"]) - set(source_by_id))
        if unknown_sources:
            raise GovernanceError(
                f"requirement {requirement['id']} has unknown sources: {unknown_sources}"
            )
        excluded_sources = sorted(
            source_id
            for source_id in requirement["source_ids"]
            if not source_by_id[source_id]["included"]
        )
        if excluded_sources:
            raise GovernanceError(
                f"requirement {requirement['id']} cites excluded sources: {excluded_sources}"
            )
        if requirement["mandatory"] and not any(
            source_by_id[source_id]["tier"] in {"A", "B"}
            for source_id in requirement["source_ids"]
        ):
            raise GovernanceError(
                f"mandatory requirement {requirement['id']} is supported only by Tier C evidence"
            )

    covered: list[str] = []
    for entry in evidence_matrix["entries"]:
        covered.extend(entry["requirement_ids"])
        unknown_requirements = sorted(set(entry["requirement_ids"]) - requirement_ids)
        if unknown_requirements:
            raise GovernanceError(
                f"evidence matrix has unknown requirements: {unknown_requirements}"
            )
        unknown_sources = sorted(set(entry["source_ids"]) - set(source_by_id))
        if unknown_sources:
            raise GovernanceError(f"evidence matrix has unknown sources: {unknown_sources}")
        if any(not source_by_id[source_id]["included"] for source_id in entry["source_ids"]):
            raise GovernanceError("evidence matrix cites an excluded source")

    duplicate_coverage = sorted(
        requirement_id
        for requirement_id, count in Counter(covered).items()
        if count > 1
    )
    if duplicate_coverage:
        raise GovernanceError(
            f"evidence matrix duplicates requirement coverage: {duplicate_coverage}"
        )
    missing_coverage = sorted(requirement_ids - set(covered))
    if missing_coverage:
        raise GovernanceError(f"evidence matrix misses requirements: {missing_coverage}")


def _check_architecture_invariants(architecture: dict[str, Any]) -> None:
    expected_engineering_planes = {
        "agent_application",
        "runtime_infra",
        "data_eval_training",
    }
    if set(architecture["engineering_planes"]) != expected_engineering_planes:
        raise GovernanceError("architecture must include all three mandatory engineering planes")
    expected_logical_planes = {
        "experience_plane",
        "control_plane",
        "data_plane",
        "execution_plane",
        "evaluation_plane",
    }
    if set(architecture["logical_planes"]) != expected_logical_planes:
        raise GovernanceError("architecture must include all five logical planes")

    components = {component["id"]: component for component in architecture["components"]}
    stores = {store["id"]: store for store in architecture["stores"]}
    if len(components) != len(architecture["components"]):
        raise GovernanceError("architecture has duplicate component IDs")
    if len(stores) != len(architecture["stores"]):
        raise GovernanceError("architecture has duplicate store IDs")

    for component in components.values():
        unknown_stores = sorted(set(component["authoritative_stores"]) - set(stores))
        unknown_invocations = sorted(set(component["invokes"]) - set(components))
        if unknown_stores or unknown_invocations:
            raise GovernanceError(
                f"component {component['id']} has unknown references: "
                f"stores={unknown_stores}, invokes={unknown_invocations}"
            )
    for store in stores.values():
        if store["owner_component"] not in components:
            raise GovernanceError(f"store {store['id']} has unknown owner")

    ownership = architecture["state_ownership"]
    expected_states = {
        "Incident Lifecycle",
        "Runtime Task",
        "Agent Graph State",
        "ActionTransaction",
        "Agent Trace/Eval",
        "Artifact/Dataset",
    }
    state_names = [record["state"] for record in ownership]
    duplicates = sorted(name for name, count in Counter(state_names).items() if count > 1)
    if duplicates:
        raise GovernanceError(f"architecture has duplicate state owners: {duplicates}")
    if set(state_names) != expected_states:
        raise GovernanceError("architecture state ownership set is incomplete")
    owner_by_state = {record["state"]: record["owner_component"] for record in ownership}
    store_by_state = {record["state"]: record["authoritative_store"] for record in ownership}
    for state, owner in owner_by_state.items():
        if owner not in components or store_by_state[state] not in stores:
            raise GovernanceError(f"state {state} has an unknown owner or store")
        if state not in components[owner]["writes_states"]:
            raise GovernanceError(
                f"state owner {owner} does not declare write authority for {state}"
            )
    for component in components.values():
        for state in component["writes_states"]:
            if owner_by_state.get(state) != component["id"]:
                raise GovernanceError(
                    f"component {component['id']} declares cross-owner state write: {state}"
                )

    for boundary in architecture["trust_boundaries"]:
        if (
            boundary["from_component"] not in components
            or boundary["to_component"] not in components
        ):
            raise GovernanceError(f"trust boundary {boundary['id']} has an unknown component")
    required_denials = {
        "DENY-AGENT-DIRECT-ACTION",
        "DENY-AGENT-GROUND-TRUTH",
        "DENY-CROSS-TENANT",
        "DENY-UNSANDBOXED-CODE",
    }
    denial_ids = {path["id"] for path in architecture["prohibited_paths"]}
    if not required_denials.issubset(denial_ids):
        raise GovernanceError("architecture is missing a mandatory prohibited path")

    required_walkthroughs = {f"W-ARCH-{number:03d}" for number in range(1, 11)}
    walkthrough_ids = [walkthrough["id"] for walkthrough in architecture["walkthroughs"]]
    if set(walkthrough_ids) != required_walkthroughs or len(walkthrough_ids) != 10:
        raise GovernanceError("architecture walkthrough set must be exactly W-ARCH-001 through 010")
    for walkthrough in architecture["walkthroughs"]:
        unknown = sorted(set(walkthrough["component_path"]) - set(components))
        if unknown:
            raise GovernanceError(
                f"walkthrough {walkthrough['id']} has unknown components: {unknown}"
            )


def _check_gate_walkthroughs(document: dict[str, Any], bindings: dict[str, Any]) -> None:
    expected = {f"W-G00-{number:03d}" for number in range(1, 15)}
    records = document["walkthroughs"]
    ids = [record["id"] for record in records]
    if len(ids) != len(set(ids)) or set(ids) != expected:
        raise GovernanceError("G00 walkthrough set must be exactly W-G00-001 through 014")
    binding_ids = {record["id"] for record in bindings["bindings"]}
    unknown = sorted(
        record["source_binding"]
        for record in records
        if record["source_binding"] not in binding_ids
    )
    if unknown:
        raise GovernanceError(f"G00 walkthroughs reference unknown contract bindings: {unknown}")
    if any(record["status"] != "pass" for record in records):
        raise GovernanceError("all fourteen G00 design walkthroughs must pass")


def _check_adr_invariants(root: Path, index: dict[str, Any]) -> None:
    required = {f"ADR-{number:04d}" for number in range(1, 7)}
    records = {record["id"]: record for record in index["adrs"]}
    missing = sorted(required - set(records))
    if missing:
        raise GovernanceError(f"architecture decision baseline is incomplete: {missing}")
    for record in records.values():
        if record["status"] == "accepted" and not (root / record["path"]).is_file():
            raise GovernanceError(f"accepted ADR path does not exist: {record['path']}")


def _check_architecture_documents(root: Path) -> None:
    document_names = {
        "SYSTEM_CONTEXT.md",
        "CONTAINER_ARCHITECTURE.md",
        "DATA_AND_CONTROL_FLOW.md",
        "DEPLOYMENT_AND_TRUST_BOUNDARIES.md",
        "STATE_MACHINES.md",
    }
    architecture_root = root / "docs" / "architecture"
    for name in sorted(document_names):
        path = architecture_root / name
        if not path.is_file():
            raise GovernanceError(f"missing architecture document: {name}")
        text = path.read_text(encoding="utf-8")
        if "```mermaid" not in text:
            raise GovernanceError(f"architecture document has no Mermaid view: {name}")
        missing_links = sorted(other for other in document_names - {name} if other not in text)
        if missing_links:
            raise GovernanceError(
                f"architecture document {name} is missing cross-links: {missing_links}"
            )
    if not (root / "docs" / "security" / "THREAT_MODEL.md").is_file():
        raise GovernanceError("missing initial Threat Model")
