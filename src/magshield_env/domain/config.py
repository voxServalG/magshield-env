"""Versioned environment-builder configuration models.

``BuildConfig`` tells the builder which point source, forward source, hardware
contract, scenario, and Gymnasium interface to consume.  Each nested model
validates one boundary before file I/O begins.  The builder then resolves the
declared sources into a self-contained environment package, and ``make_env``
consumes that package without retaining the original source files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, PositiveFloat, model_validator


class StrictModel(BaseModel):
    """Reject unknown fields so configuration drift fails immediately."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class SphereRegion(StrictModel):
    kind: Literal["sphere_cartesian"]
    radius_m: PositiveFloat
    spacing_m: PositiveFloat
    center_m: tuple[float, float, float] = (0.0, 0.0, 0.0)
    frame: str = "body"


class SphereSurfaceRegion(StrictModel):
    kind: Literal["sphere_surface"]
    radius_m: PositiveFloat
    point_count: int = Field(ge=4)
    center_m: tuple[float, float, float] = (0.0, 0.0, 0.0)
    frame: str = "body"


class BoxRegion(StrictModel):
    kind: Literal["box_cartesian"]
    minimum_m: tuple[float, float, float]
    maximum_m: tuple[float, float, float]
    spacing_m: PositiveFloat
    frame: str = "body"

    @model_validator(mode="after")
    def require_positive_extent(self) -> BoxRegion:
        if any(high <= low for low, high in zip(self.minimum_m, self.maximum_m, strict=True)):
            raise ValueError("box maximum_m must be greater than minimum_m on every axis")
        return self


class CylinderRegion(StrictModel):
    kind: Literal["cylinder_cartesian"]
    radius_m: PositiveFloat
    height_m: PositiveFloat
    spacing_m: PositiveFloat
    center_m: tuple[float, float, float] = (0.0, 0.0, 0.0)
    axis: Literal["x", "y", "z"] = "z"
    frame: str = "body"


class ImportedRegion(StrictModel):
    kind: Literal["import"]
    path: Path
    frame: str
    dataset: str = "/"


RegionConfig = Annotated[
    SphereRegion | SphereSurfaceRegion | BoxRegion | CylinderRegion | ImportedRegion,
    Field(discriminator="kind"),
]


class FixedMatrixForward(StrictModel):
    kind: Literal["fixed_matrix"]
    path: Path
    dataset: str = "/response_T_per_A"
    channel_ids: tuple[str, ...]


class FiniteElementForward(StrictModel):
    kind: Literal["finite_element"]
    channel_files: tuple[Path, ...]
    channel_ids: tuple[str, ...]
    coordinate_tolerance_m: float = Field(default=0.0, ge=0.0)

    @model_validator(mode="after")
    def require_one_file_per_channel(self) -> FiniteElementForward:
        if not self.channel_files or len(self.channel_files) != len(self.channel_ids):
            raise ValueError("finite_element requires one field file per channel_id")
        if len(set(self.channel_ids)) != len(self.channel_ids):
            raise ValueError("channel_ids must be unique")
        return self


class GeometryForward(StrictModel):
    kind: Literal["geometry"]
    paths: Path
    channels: Path
    path_frame: str = Field(min_length=1)
    pose_source_frame: str = Field(min_length=1)
    pose_target_frame: str = Field(min_length=1)
    pose_cache_size: int = Field(default=64, ge=0)

    @model_validator(mode="after")
    def require_pose_target_to_be_path_frame(self) -> GeometryForward:
        if self.pose_target_frame != self.path_frame:
            raise ValueError("pose_target_frame must equal path_frame")
        return self


ForwardConfig = Annotated[
    FixedMatrixForward | FiniteElementForward | GeometryForward,
    Field(discriminator="kind"),
]


class HardwareChannelConfig(StrictModel):
    channel_id: str = Field(min_length=1)
    current_lower_a: float
    current_upper_a: float
    slew_rate_upper_a_per_s: PositiveFloat
    resistance_ohm: PositiveFloat
    voltage_upper_v: PositiveFloat

    @model_validator(mode="after")
    def require_ordered_current_bounds(self) -> HardwareChannelConfig:
        if self.current_lower_a >= self.current_upper_a:
            raise ValueError("current_lower_a must be less than current_upper_a")
        return self


class HardwareConfig(StrictModel):
    timestep_seconds: PositiveFloat
    channels: tuple[HardwareChannelConfig, ...]

    @model_validator(mode="after")
    def require_unique_channels(self) -> HardwareConfig:
        ids = [channel.channel_id for channel in self.channels]
        if not ids or len(ids) != len(set(ids)):
            raise ValueError("hardware channel_id values must be non-empty and unique")
        return self


class StaticScenario(StrictModel):
    kind: Literal["static"]
    external_field: Path | None = None
    external_field_component_frame: str = Field(min_length=1)
    episode_length: int = Field(default=1, ge=1)
    translation_m: tuple[float, float, float] | None = None
    quaternion_xyzw: tuple[float, float, float, float] | None = None

    @model_validator(mode="after")
    def require_complete_pose(self) -> StaticScenario:
        pose_values = (self.translation_m, self.quaternion_xyzw)
        if any(value is None for value in pose_values) and not all(
            value is None for value in pose_values
        ):
            raise ValueError("translation_m and quaternion_xyzw must be supplied together")
        return self


class TrajectoryScenario(StrictModel):
    kind: Literal["trajectory"]
    path: Path
    external_field_component_frame: str = Field(min_length=1)
    external_field_dataset: str = "/external_field"
    translation_dataset: str | None = "/pose/translation_m"
    quaternion_dataset: str | None = "/pose/quaternion_xyzw"
    episode_length: int = Field(ge=1)
    random_start: bool = False

    @model_validator(mode="after")
    def require_complete_pose_datasets(self) -> TrajectoryScenario:
        pose_datasets = (self.translation_dataset, self.quaternion_dataset)
        if any(value is None for value in pose_datasets) and not all(
            value is None for value in pose_datasets
        ):
            raise ValueError("translation_dataset and quaternion_dataset must be supplied together")
        return self


ScenarioConfig = Annotated[StaticScenario | TrajectoryScenario, Field(discriminator="kind")]


class RewardConfig(StrictModel):
    field_scale_t: PositiveFloat
    field_threshold_t: float = Field(ge=0.0)
    field_weight: float = Field(ge=0.0)
    power_scale_w: PositiveFloat
    power_weight: float = Field(ge=0.0)
    slew_scale_a: PositiveFloat
    slew_weight: float = Field(ge=0.0)
    constraint_scale_a: PositiveFloat
    constraint_weight: float = Field(ge=0.0)
    nominal_currents_a: tuple[float, ...] | None = None
    nominal_scale_a: PositiveFloat | None = None
    nominal_weight: float | None = Field(default=None, ge=0.0)

    @model_validator(mode="after")
    def require_complete_nominal_term(self) -> RewardConfig:
        nominal_values = (
            self.nominal_currents_a,
            self.nominal_scale_a,
            self.nominal_weight,
        )
        if any(value is None for value in nominal_values) and not all(
            value is None for value in nominal_values
        ):
            raise ValueError(
                "nominal_currents_a, nominal_scale_a and nominal_weight must be supplied together"
            )
        return self


class EnvironmentInterfaceConfig(StrictModel):
    observation_mode: Literal["full_field", "basis"] = "full_field"
    basis_path: Path | None = None
    basis_dataset: str = "/basis"
    basis_component_frame: str | None = Field(default=None, min_length=1)
    include_pose: bool = False
    action_mode: Literal["current_delta"] = "current_delta"
    constraint_mode: Literal["project_and_report", "terminate"] = "project_and_report"
    reward: RewardConfig

    @model_validator(mode="after")
    def require_basis_for_basis_observation(self) -> EnvironmentInterfaceConfig:
        basis_members = (self.basis_path, self.basis_component_frame)
        if self.observation_mode == "basis" and any(value is None for value in basis_members):
            raise ValueError(
                "basis_path and basis_component_frame are required when observation_mode is basis"
            )
        if self.observation_mode == "full_field" and any(
            value is not None for value in basis_members
        ):
            raise ValueError(
                "basis_path and basis_component_frame are only valid for basis observations"
            )
        return self


class BuildConfig(StrictModel):
    schema_name: Literal["magshield_env.build_config"]
    schema_version: Literal[1]
    name: str = Field(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    region: RegionConfig
    forward: ForwardConfig
    hardware: HardwareConfig
    scenario: ScenarioConfig
    environment: EnvironmentInterfaceConfig
    output_dir: Path


def load_build_config(path: str | Path) -> BuildConfig:
    """Load strict YAML relative to its own directory, preserving source intent."""

    source = Path(path).resolve()
    payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("build config must be a YAML object")
    config = BuildConfig.model_validate(payload)
    return _resolve_paths(config, source.parent)


def _resolve_paths(config: BuildConfig, base: Path) -> BuildConfig:
    """Resolve every declared path against the configuration file directory."""

    payload = config.model_dump(mode="python")

    def resolve(value: Path | None) -> Path | None:
        if value is None:
            return None
        return value if value.is_absolute() else (base / value).resolve()

    region = payload["region"]
    if region["kind"] == "import":
        region["path"] = resolve(region["path"])
    forward = payload["forward"]
    if forward["kind"] == "fixed_matrix":
        forward["path"] = resolve(forward["path"])
    elif forward["kind"] == "finite_element":
        forward["channel_files"] = tuple(resolve(path) for path in forward["channel_files"])
    else:
        forward["paths"] = resolve(forward["paths"])
        forward["channels"] = resolve(forward["channels"])
    scenario = payload["scenario"]
    if scenario["kind"] == "static":
        scenario["external_field"] = resolve(scenario["external_field"])
    else:
        scenario["path"] = resolve(scenario["path"])
    interface = payload["environment"]
    interface["basis_path"] = resolve(interface["basis_path"])
    payload["output_dir"] = resolve(payload["output_dir"])
    return BuildConfig.model_validate(payload)
