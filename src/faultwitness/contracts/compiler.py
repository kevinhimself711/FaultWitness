"""Deterministic compiler for the frozen G00 contract authority.

The compiler deliberately has no discovery mode.  A contract source becomes part
of the executable contract only after it is added to :data:`SOURCE_SPECS`; this
prevents an unexpected YAML file from silently changing the runtime authority.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from importlib.resources import files
from pathlib import Path, PurePosixPath
from typing import Any, Final

import yaml

CONTRACTS_VERSION: Final = "1.1.0"
RESOURCE_FORMAT_VERSION: Final = "1.0.0"
GENERATED_RESOURCE: Final = "generated/contracts-v1.1.0.json"


@dataclass(frozen=True, slots=True)
class SourceSpec:
    path: str
    required_keys: frozenset[str]
    allowed_keys: frozenset[str]
    identity: tuple[str, str] | None = None


SOURCE_SPECS: Final[dict[str, SourceSpec]] = {
    "commands_events": SourceSpec(
        "docs/contracts/COMMAND_EVENT_CATALOG.yaml",
        frozenset({"schema_version", "commands", "events"}),
        frozenset({"schema_version", "commands", "events"}),
    ),
    "types": SourceSpec(
        "docs/contracts/TYPE_CATALOG.yaml",
        frozenset({"schema_version", "types"}),
        frozenset({"schema_version", "types"}),
    ),
    "failures": SourceSpec(
        "docs/contracts/FAILURE_SEMANTICS.yaml",
        frozenset({"schema_version", "errors", "failures"}),
        frozenset({"schema_version", "errors", "failures"}),
    ),
    "state_machine.action_transaction": SourceSpec(
        "docs/contracts/state-machines/action_transaction.yaml",
        frozenset(
            {
                "schema_version",
                "id",
                "owner_component",
                "authoritative_store",
                "initial_state",
                "terminal_states",
                "states",
                "transitions",
                "invariants",
            }
        ),
        frozenset(
            {
                "schema_version",
                "id",
                "owner_component",
                "authoritative_store",
                "initial_state",
                "terminal_states",
                "states",
                "transitions",
                "invariants",
            }
        ),
        ("id", "action_transaction"),
    ),
    "state_machine.agent_graph": SourceSpec(
        "docs/contracts/state-machines/agent_graph.yaml",
        frozenset(
            {
                "schema_version",
                "id",
                "owner_component",
                "authoritative_store",
                "initial_state",
                "terminal_states",
                "states",
                "transitions",
                "invariants",
            }
        ),
        frozenset(
            {
                "schema_version",
                "id",
                "owner_component",
                "authoritative_store",
                "initial_state",
                "terminal_states",
                "states",
                "transitions",
                "invariants",
            }
        ),
        ("id", "agent_graph"),
    ),
    "state_machine.incident": SourceSpec(
        "docs/contracts/state-machines/incident.yaml",
        frozenset(
            {
                "schema_version",
                "id",
                "owner_component",
                "authoritative_store",
                "initial_state",
                "terminal_states",
                "states",
                "transitions",
                "invariants",
            }
        ),
        frozenset(
            {
                "schema_version",
                "id",
                "owner_component",
                "authoritative_store",
                "initial_state",
                "terminal_states",
                "states",
                "transitions",
                "invariants",
            }
        ),
        ("id", "incident"),
    ),
    "state_machine.runtime_task": SourceSpec(
        "docs/contracts/state-machines/runtime_task.yaml",
        frozenset(
            {
                "schema_version",
                "id",
                "owner_component",
                "authoritative_store",
                "initial_state",
                "terminal_states",
                "states",
                "transitions",
                "invariants",
            }
        ),
        frozenset(
            {
                "schema_version",
                "id",
                "owner_component",
                "authoritative_store",
                "initial_state",
                "terminal_states",
                "states",
                "transitions",
                "invariants",
            }
        ),
        ("id", "runtime_task"),
    ),
    "openapi": SourceSpec(
        "docs/contracts/openapi.yaml",
        frozenset({"openapi", "info", "security", "paths", "components"}),
        frozenset({"openapi", "info", "security", "paths", "components"}),
        ("openapi", "3.1.0"),
    ),
    "asyncapi": SourceSpec(
        "docs/contracts/asyncapi.yaml",
        frozenset(
            {"asyncapi", "info", "defaultContentType", "channels", "operations", "components"}
        ),
        frozenset(
            {"asyncapi", "info", "defaultContentType", "channels", "operations", "components"}
        ),
        ("asyncapi", "3.0.0"),
    ),
}


class ContractCompilationError(ValueError):
    """The frozen source set cannot be compiled without ambiguity."""


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_mapping(
    loader: _UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in result
        except TypeError as exc:
            raise ContractCompilationError("contract mapping contains a non-scalar key") from exc
        if duplicate:
            raise ContractCompilationError(f"contract mapping contains duplicate key {key!r}")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


def _canonical(value: Any, *, source: str) -> Any:
    """Return a JSON-compatible tree with stable mapping order and scalar types."""
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise ContractCompilationError(f"{source}: every mapping key must be a string")
        return {key: _canonical(value[key], source=source) for key in sorted(value)}
    if isinstance(value, list):
        return [_canonical(item, source=source) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise ContractCompilationError(
        f"{source}: unsupported YAML value of type {type(value).__name__}"
    )


def _parse_source(name: str, raw: bytes) -> dict[str, Any]:
    spec = SOURCE_SPECS[name]
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ContractCompilationError(f"{spec.path}: source is not UTF-8") from exc
    try:
        parsed = yaml.load(text, Loader=_UniqueKeyLoader)
    except ContractCompilationError:
        raise
    except yaml.YAMLError as exc:
        raise ContractCompilationError(f"{spec.path}: malformed YAML") from exc
    if not isinstance(parsed, dict):
        raise ContractCompilationError(f"{spec.path}: top-level document must be a mapping")
    keys = set(parsed)
    if missing := sorted(spec.required_keys - keys):
        raise ContractCompilationError(f"{spec.path}: missing required keys {missing}")
    if unknown := sorted(keys - spec.allowed_keys):
        raise ContractCompilationError(f"{spec.path}: unknown top-level keys {unknown}")
    if spec.identity is not None:
        field, expected = spec.identity
        if parsed[field] != expected:
            raise ContractCompilationError(
                f"{spec.path}: expected {field}={expected!r}, got {parsed[field]!r}"
            )
    if name not in {"openapi", "asyncapi"}:
        version = parsed.get("schema_version")
        if not isinstance(version, str) or version.count(".") != 2:
            raise ContractCompilationError(f"{spec.path}: malformed schema_version")
    return _canonical(parsed, source=spec.path)


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def compile_source_bytes(sources: Mapping[str, bytes]) -> bytes:
    """Compile one exact, in-memory source set to the canonical resource bytes."""
    expected = set(SOURCE_SPECS)
    actual = set(sources)
    if missing := sorted(expected - actual):
        raise ContractCompilationError(f"contract source set is missing {missing}")
    if unknown := sorted(actual - expected):
        raise ContractCompilationError(f"contract source set contains unknown sources {unknown}")

    documents: dict[str, Any] = {}
    source_records: dict[str, Any] = {}
    for name in sorted(SOURCE_SPECS):
        raw = sources[name]
        if not isinstance(raw, bytes):
            raise ContractCompilationError(f"{name}: source payload must be bytes")
        spec = SOURCE_SPECS[name]
        documents[name] = _parse_source(name, raw)
        source_records[name] = {
            "path": PurePosixPath(spec.path).as_posix(),
            "sha256": sha256(raw).hexdigest(),
        }

    digest_input = {
        "contracts_version": CONTRACTS_VERSION,
        "documents": documents,
        "format_version": RESOURCE_FORMAT_VERSION,
        "sources": source_records,
    }
    bundle = {
        "artifact_sha256": sha256(_json_bytes(digest_input)).hexdigest(),
        "contracts_version": CONTRACTS_VERSION,
        "documents": documents,
        "format_version": RESOURCE_FORMAT_VERSION,
        "sources": source_records,
    }
    return _json_bytes(bundle)


def read_source_bytes(repository_root: Path) -> dict[str, bytes]:
    """Read only the fixed source manifest from *repository_root*."""
    root = repository_root.resolve()
    sources: dict[str, bytes] = {}
    for name, spec in SOURCE_SPECS.items():
        path = (root / Path(spec.path)).resolve()
        if root not in path.parents:
            raise ContractCompilationError(f"source escapes repository root: {spec.path}")
        try:
            sources[name] = path.read_bytes()
        except FileNotFoundError as exc:
            raise ContractCompilationError(f"missing contract source: {spec.path}") from exc
        except OSError as exc:
            raise ContractCompilationError(f"cannot read contract source: {spec.path}") from exc
    return sources


def compile_repository(repository_root: Path) -> bytes:
    """Compile the repository's frozen source set without writing files."""
    return compile_source_bytes(read_source_bytes(repository_root))


def write_generated_resource(repository_root: Path) -> Path:
    """Atomically replace the package resource with deterministic compiled bytes."""
    root = repository_root.resolve()
    target = root / "src" / "faultwitness" / "contracts" / GENERATED_RESOURCE
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_bytes(compile_repository(root))
    temporary.replace(target)
    return target


def assert_generated_resource_current(repository_root: Path) -> None:
    """Fail if the checked-in package resource is absent or byte-stale."""
    root = repository_root.resolve()
    target = root / "src" / "faultwitness" / "contracts" / GENERATED_RESOURCE
    expected = compile_repository(root)
    try:
        actual = target.read_bytes()
    except FileNotFoundError as exc:
        raise ContractCompilationError(f"missing generated contract resource: {target}") from exc
    if actual != expected:
        raise ContractCompilationError(
            f"generated contract resource drifted: {target.relative_to(root).as_posix()}"
        )


def load_generated_resource(repository_root: Path) -> dict[str, Any]:
    """Load and integrity-check the generated resource for tooling and tests."""
    root = repository_root.resolve()
    target = root / "src" / "faultwitness" / "contracts" / GENERATED_RESOURCE
    try:
        raw = target.read_bytes()
    except OSError as exc:
        raise ContractCompilationError(
            f"cannot load generated contract resource: {target}"
        ) from exc
    return _decode_generated_resource(raw, str(target))


def load_packaged_resource() -> dict[str, Any]:
    """Load the integrity-checked resource from an installed FaultWitness package."""
    resource = files("faultwitness.contracts").joinpath(GENERATED_RESOURCE)
    try:
        raw = resource.read_bytes()
    except OSError as exc:
        raise ContractCompilationError(
            f"cannot load packaged contract resource: {GENERATED_RESOURCE}"
        ) from exc
    return _decode_generated_resource(raw, GENERATED_RESOURCE)


def _decode_generated_resource(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractCompilationError(f"malformed generated contract resource: {label}") from exc
    if not isinstance(value, dict):
        raise ContractCompilationError("generated contract resource must be a JSON object")
    if value.get("contracts_version") != CONTRACTS_VERSION:
        raise ContractCompilationError("generated contract resource has an unknown version")
    if value.get("format_version") != RESOURCE_FORMAT_VERSION:
        raise ContractCompilationError("generated contract resource has an unknown format")
    digest_input = {
        "contracts_version": value.get("contracts_version"),
        "documents": value.get("documents"),
        "format_version": value.get("format_version"),
        "sources": value.get("sources"),
    }
    expected_digest = sha256(_json_bytes(digest_input)).hexdigest()
    if value.get("artifact_sha256") != expected_digest:
        raise ContractCompilationError("generated contract resource failed integrity check")
    return value
