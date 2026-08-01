"""Portable environment-package metadata contracts.

``EnvironmentPackageConfig`` names the immutable package files and declares
how ``make_env`` consumes their physics, scenario, hardware, observations,
actions, and rewards. ``BuildReport`` and ``ValidationReport`` expose the same
resolved dimensions and identity to Python, CLI, and TUI callers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .config import RewardConfig


def canonical_units() -> dict[str, str]:
    """Return the exact SI unit map bound into every portable package."""

    return {
        "length": "m",
        "field": "T",
        "current": "A",
        "response": "T/A",
        "time": "s",
        "resistance": "ohm",
        "voltage": "V",
    }


class PackageStrictModel(BaseModel):
    """Reject package metadata drift and non-finite numeric values."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class PackagedPhysics(PackageStrictModel):
    """Tell the loader which physics data and runtime mode to consume."""

    mode: Literal["fixed", "dynamic_geometry"]
    file: Literal["physics.h5"] = "physics.h5"
    response_dataset: Literal["/response_T_per_A"] = "/response_T_per_A"
    path_frame: str | None = None
    pose_source_frame: str | None = None
    pose_target_frame: str | None = None
    pose_cache_size: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def require_mode_specific_frames(self) -> PackagedPhysics:
        dynamic_members = (self.path_frame, self.pose_source_frame, self.pose_target_frame)
        if self.mode == "dynamic_geometry":
            if any(value is None or not value for value in dynamic_members):
                raise ValueError("dynamic geometry requires path and pose source/target frames")
            if self.pose_target_frame != self.path_frame:
                raise ValueError("pose_target_frame must equal path_frame")
        elif any(value is not None for value in dynamic_members):
            raise ValueError("fixed physics must not declare dynamic geometry frames")
        return self


class PackagedScenario(PackageStrictModel):
    """Tell the loader how to consume exogenous field and pose frames."""

    file: Literal["scenario.h5"] = "scenario.h5"
    episode_length: int = Field(ge=1)
    random_start: bool = False
    has_pose: bool
    external_field_component_frame: str = Field(min_length=1)


class EnvironmentPackageConfig(PackageStrictModel):
    """Load one self-contained Gymnasium environment package."""

    schema_name: Literal["magshield_env.environment_package"]
    schema_version: Literal[1]
    name: str
    manifest_file: Literal["manifest.json"] = "manifest.json"
    hardware_file: Literal["hardware.yaml"] = "hardware.yaml"
    physics: PackagedPhysics
    scenario: PackagedScenario
    observation_mode: Literal["full_field", "basis"]
    observation_basis_dataset: Literal["/observation_basis"] | None = None
    observation_basis_component_frame: str | None = Field(default=None, min_length=1)
    include_pose: bool
    action_mode: Literal["current_delta"] = "current_delta"
    constraint_mode: Literal["project_and_report", "terminate"]
    reward: RewardConfig

    @model_validator(mode="after")
    def require_observation_basis_contract(self) -> EnvironmentPackageConfig:
        basis_members = (
            self.observation_basis_dataset,
            self.observation_basis_component_frame,
        )
        if self.observation_mode == "basis" and any(value is None for value in basis_members):
            raise ValueError("basis observations require dataset and component frame")
        if self.observation_mode == "full_field" and any(
            value is not None for value in basis_members
        ):
            raise ValueError("full_field observations must not declare basis metadata")
        return self


class BuildReport(PackageStrictModel):
    """Report one completed package and its physically resolved dimensions."""

    output_dir: Path
    package_identity: str
    point_count: int = Field(gt=0)
    channel_count: int = Field(gt=0)
    response_shape: tuple[int, int, int]
    response_rank: int = Field(ge=0)
    response_memory_bytes: int = Field(ge=0)
    physics_mode: Literal["fixed", "dynamic_geometry"]


class ValidationReport(PackageStrictModel):
    """Report a package whose hashes and cross-file contracts all passed."""

    package_dir: Path
    package_identity: str
    point_count: int = Field(gt=0)
    channel_count: int = Field(gt=0)
    response_shape: tuple[int, int, int]
    response_rank: int = Field(ge=0)
    physics_mode: Literal["fixed", "dynamic_geometry"]


def load_environment_package_config(path: str | Path) -> EnvironmentPackageConfig:
    """Load strict package YAML without resolving its portable relative names."""

    source = Path(path)
    payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("environment package config must be a YAML object")
    return EnvironmentPackageConfig.model_validate(payload)
