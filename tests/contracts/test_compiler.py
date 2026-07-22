from __future__ import annotations

import copy
import json
from hashlib import sha256
from pathlib import Path

import pytest

from faultwitness.contracts.compiler import (
    CONTRACTS_VERSION,
    SOURCE_SPECS,
    ContractCompilationError,
    assert_generated_resource_current,
    compile_repository,
    compile_source_bytes,
    load_generated_resource,
    load_packaged_resource,
    read_source_bytes,
)

ROOT = Path(__file__).resolve().parents[2]


def _sources() -> dict[str, bytes]:
    return read_source_bytes(ROOT)


def test_regeneration_is_byte_stable_and_checked_in() -> None:
    first = compile_repository(ROOT)
    second = compile_repository(ROOT)

    assert first == second
    assert first.endswith(b"\n")
    assert_generated_resource_current(ROOT)


def test_bundle_has_version_digests_and_frozen_authority_counts() -> None:
    raw_sources = _sources()
    bundle = json.loads(compile_source_bytes(raw_sources))

    assert bundle["contracts_version"] == CONTRACTS_VERSION == "1.1.0"
    assert bundle["format_version"] == "1.0.0"
    assert "generated_at" not in bundle
    assert set(bundle["documents"]) == set(SOURCE_SPECS)
    for name, source in bundle["sources"].items():
        assert source["path"] == SOURCE_SPECS[name].path
        assert source["sha256"] == sha256(raw_sources[name]).hexdigest()

    documents = bundle["documents"]
    machines = [
        document for name, document in documents.items() if name.startswith("state_machine.")
    ]
    assert len(documents["types"]["types"]) == 21
    assert sum(len(machine["states"]) for machine in machines) == 52
    assert sum(len(machine["transitions"]) for machine in machines) == 82
    assert len(documents["commands_events"]["commands"]) == 34
    assert len(documents["commands_events"]["events"]) == 43
    assert len(documents["failures"]["errors"]) == 10


def test_checked_in_resource_passes_its_content_integrity_check() -> None:
    bundle = load_generated_resource(ROOT)

    assert len(bundle["artifact_sha256"]) == 64
    assert bundle["documents"]["state_machine.incident"]["id"] == "incident"


def test_resource_is_available_through_installed_package_api() -> None:
    assert load_packaged_resource() == load_generated_resource(ROOT)


@pytest.mark.parametrize("mutation", ["missing", "unknown"])
def test_source_manifest_rejects_missing_and_unknown_sources(mutation: str) -> None:
    sources = _sources()
    if mutation == "missing":
        sources.pop("types")
        message = "missing"
    else:
        sources["surprise"] = b"schema_version: 1.0.0\n"
        message = "unknown sources"

    with pytest.raises(ContractCompilationError, match=message):
        compile_source_bytes(sources)


def test_malformed_yaml_fails_closed() -> None:
    sources = _sources()
    sources["types"] = b"schema_version: [unterminated\n"

    with pytest.raises(ContractCompilationError, match="malformed YAML"):
        compile_source_bytes(sources)


def test_duplicate_yaml_key_fails_closed() -> None:
    sources = _sources()
    sources["types"] = b'schema_version: "1.0.0"\nschema_version: "1.0.0"\ntypes: []\n'

    with pytest.raises(ContractCompilationError, match="duplicate key"):
        compile_source_bytes(sources)


def test_unknown_top_level_field_fails_closed() -> None:
    sources = _sources()
    sources["types"] += b"unexpected_authority: true\n"

    with pytest.raises(ContractCompilationError, match="unknown top-level keys"):
        compile_source_bytes(sources)


def test_state_machine_file_identity_cannot_be_swapped() -> None:
    sources = _sources()
    sources["state_machine.incident"] = sources["state_machine.runtime_task"]

    with pytest.raises(ContractCompilationError, match="expected id='incident'"):
        compile_source_bytes(sources)


def test_source_change_updates_source_and_artifact_digests() -> None:
    sources = _sources()
    baseline = json.loads(compile_source_bytes(sources))
    changed = copy.copy(sources)
    changed["types"] = sources["types"] + b"\n"

    result = json.loads(compile_source_bytes(changed))

    assert result["documents"] == baseline["documents"]
    assert result["sources"]["types"]["sha256"] != baseline["sources"]["types"]["sha256"]
    assert result["artifact_sha256"] != baseline["artifact_sha256"]
