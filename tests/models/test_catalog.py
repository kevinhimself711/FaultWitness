from pathlib import Path

import pytest
from pydantic import ValidationError

from faultwitness.contracts.models import ModelFamily
from faultwitness.models.catalog import CapabilityCatalog
from faultwitness.models.types import ModelCapability

ROOT = Path(__file__).resolve().parents[2]


def test_catalog_loads_three_families_with_exact_routes() -> None:
    catalog = CapabilityCatalog.load(ROOT / "config/models/catalog.yaml")
    assert set(catalog.route_policy.routes) == set(ModelFamily)
    for family in ModelFamily:
        candidates = catalog.candidates(family, ModelCapability.STRUCTURED)
        assert len(candidates) == 3
        assert candidates[0].family is family


def test_catalog_rejects_cross_family_route() -> None:
    catalog = CapabilityCatalog.load(ROOT / "config/models/catalog.yaml")
    document = catalog.model_dump(mode="json")
    document["route_policy"]["routes"]["qwen"] = ["glm_primary"]
    with pytest.raises(ValidationError, match="primary route"):
        CapabilityCatalog.model_validate(document, strict=False)
