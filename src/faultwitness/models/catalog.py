from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from faultwitness.contracts.models import ModelFamily
from faultwitness.models.types import ChannelName, ModelCapability


class CatalogModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class ModelProfile(CatalogModel):
    family: ModelFamily
    channel: ChannelName
    model_id: str = Field(min_length=1)
    capabilities: frozenset[ModelCapability]
    request_overrides: dict[str, bool] = Field(default_factory=dict)
    input_usd_per_million: float | None = Field(default=None, ge=0)
    output_usd_per_million: float | None = Field(default=None, ge=0)

    def supports(self, capability: ModelCapability) -> bool:
        return capability in self.capabilities


class RoutePolicy(CatalogModel):
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    routes: dict[ModelFamily, tuple[str, ...]]
    max_transient_retries: int = Field(default=1, ge=0, le=1)
    max_repairs: int = Field(default=1, ge=0, le=1)


class CapabilityCatalog(CatalogModel):
    schema_version: str = "1.0.0"
    catalog_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    profiles: dict[str, ModelProfile]
    route_policy: RoutePolicy

    @model_validator(mode="after")
    def routes_reference_compatible_profiles(self) -> CapabilityCatalog:
        for family, names in self.route_policy.routes.items():
            if not names:
                raise ValueError(f"family {family.value} has no route")
            for index, name in enumerate(names):
                profile = self.profiles.get(name)
                if profile is None:
                    raise ValueError(f"invalid route {name} for {family.value}")
                if index == 0 and profile.family is not family:
                    raise ValueError(f"primary route {name} does not match {family.value}")
        return self

    @classmethod
    def load(cls, path: Path) -> CapabilityCatalog:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        return cls.model_validate(document, strict=False)

    def candidates(
        self, family: ModelFamily, capability: ModelCapability
    ) -> tuple[ModelProfile, ...]:
        return tuple(
            self.profiles[name]
            for name in self.route_policy.routes[family]
            if self.profiles[name].supports(capability)
        )
