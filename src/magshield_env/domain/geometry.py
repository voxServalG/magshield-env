"""Versioned channel ordering and repeated-conductor metadata.

``GeometryChannelsConfig`` binds channel order to the path artifact and lists
every ``ContributionConfig`` that must be applied to every declared conductor.
Each contribution consumes its rotation, translation, reflection declaration,
and gain when the runtime Biot-Savart response is evaluated.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, model_validator


class GeometryStrictModel(BaseModel):
    """Reject unknown or non-finite geometry metadata."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class ContributionConfig(GeometryStrictModel):
    """Describe one transformed copy of all source conductors."""

    rotation: tuple[
        tuple[float, float, float],
        tuple[float, float, float],
        tuple[float, float, float],
    ] = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    translation_m: tuple[float, float, float] = (0.0, 0.0, 0.0)
    allow_improper: bool = False
    gain: float = 1.0


class GeometryChannelsConfig(GeometryStrictModel):
    """Bind a path file to channel order and explicit conductor copies."""

    schema_name: Literal["magshield_env.geometry_channels"]
    schema_version: Literal[1]
    channel_ids: tuple[str, ...]
    contributions: tuple[ContributionConfig, ...] = (ContributionConfig(),)

    @model_validator(mode="after")
    def require_nonempty_unique_members(self) -> GeometryChannelsConfig:
        if not self.channel_ids or len(set(self.channel_ids)) != len(self.channel_ids):
            raise ValueError("channel_ids must be non-empty and unique")
        if not self.contributions:
            raise ValueError("contributions must not be empty")
        return self


def load_geometry_channels_config(path: str | Path) -> GeometryChannelsConfig:
    """Load strict YAML geometry metadata from one explicit file."""

    source = Path(path)
    payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("geometry channel metadata must be a YAML object")
    return GeometryChannelsConfig.model_validate(payload)
