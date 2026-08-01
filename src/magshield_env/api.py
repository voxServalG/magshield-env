"""Public package validation, inspection, and Gymnasium construction."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .builder import pose_to_transform
from .domain.config import HardwareConfig
from .domain.errors import MagshieldEnvError, io_error, validation_error
from .domain.identity import array_sha256, canonical_json_sha256, file_sha256
from .domain.package import (
    EnvironmentPackageConfig,
    ValidationReport,
    canonical_units,
    load_environment_package_config,
)
from .environment import (
    ActionConfig,
    DynamicLinearPlant,
    FixedLinearPlant,
    HardwareLimits,
    LinearPlant,
    MagneticControlEnv,
    RewardConfig,
    Scenario,
)
from .package_io import (
    LoadedPhysics,
    LoadedScenario,
    load_hardware_yaml,
    load_manifest,
    load_physics_h5,
    load_scenario_h5,
)
from .physics import DynamicPathResponse


@dataclass(frozen=True, slots=True)
class LoadedPackage:
    """Carry all validated package members consumed by ``make_env``.

    ``directory`` anchors portable file names; ``config`` declares behavior;
    ``manifest`` binds identities; ``physics`` reconstructs the plant;
    ``hardware`` constrains actions; and ``scenario`` supplies exogenous frames.
    No member is loaded from the original build sources.
    """

    directory: Path
    config: EnvironmentPackageConfig
    manifest: dict[str, Any]
    physics: LoadedPhysics
    hardware: HardwareConfig
    scenario: LoadedScenario


def validate_environment(path: str | Path) -> ValidationReport:
    """Validate every file hash, semantic array identity, and cross-file contract."""

    try:
        loaded = _load_and_validate(path)
        response = loaded.physics.response.response_T_per_A
        return ValidationReport(
            package_dir=loaded.directory,
            package_identity=str(loaded.manifest["package_identity"]),
            point_count=loaded.physics.point_set.count,
            channel_count=len(loaded.physics.response.channel_ids),
            response_shape=response.shape,
            response_rank=int(np.linalg.matrix_rank(response.reshape(-1, response.shape[-1]))),
            physics_mode=loaded.config.physics.mode,
        )
    except MagshieldEnvError:
        raise
    except FileNotFoundError as exc:
        raise io_error(
            "package_missing",
            str(exc),
            "Provide an exported environment directory or its environment.yaml.",
        ) from exc
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise validation_error(
            "package_contract",
            str(exc),
            "Restore the original package or rebuild it from validated sources.",
        ) from exc


def inspect_environment(path: str | Path) -> dict[str, Any]:
    """Return validated package facts without constructing an environment."""

    loaded = _load_and_validate_public(path)
    response = loaded.physics.response.response_T_per_A
    scenario_frames = (
        1
        if loaded.scenario.external_field_t.ndim == 2
        else int(loaded.scenario.external_field_t.shape[0])
    )
    return {
        "package_dir": str(loaded.directory),
        "package_identity": loaded.manifest["package_identity"],
        "name": loaded.config.name,
        "physics_mode": loaded.config.physics.mode,
        "point_count": loaded.physics.point_set.count,
        "channel_count": len(loaded.physics.response.channel_ids),
        "channel_ids": list(loaded.physics.response.channel_ids),
        "response_shape": list(response.shape),
        "response_rank": int(np.linalg.matrix_rank(response.reshape(-1, response.shape[-1]))),
        "response_memory_bytes": int(response.nbytes),
        "observation_mode": loaded.config.observation_mode,
        "include_pose": loaded.config.include_pose,
        "scenario_frames": scenario_frames,
        "episode_length": loaded.config.scenario.episode_length,
        "frames": loaded.manifest["frames"],
        "units": loaded.manifest["units"],
    }


def make_env(path: str | Path) -> MagneticControlEnv:
    """Construct a Gymnasium environment using only one validated package."""

    loaded = _load_and_validate_public(path)
    physics = loaded.physics
    plant: LinearPlant
    if loaded.config.physics.mode == "fixed":
        plant = FixedLinearPlant(physics.response.response_T_per_A)
    else:
        if physics.channels is None or physics.contributions is None or physics.path_frame is None:
            raise validation_error(
                "dynamic_geometry_missing",
                "dynamic package does not contain complete conductor geometry",
                "Rebuild the environment package from geometry sources.",
            )
        dynamic = DynamicPathResponse(
            physics.channels,
            lab_frame=physics.path_frame,
            contributions=physics.contributions,
            max_cache_entries=loaded.config.physics.pose_cache_size,
        )

        def response_for_pose(pose: np.ndarray) -> np.ndarray:
            result = dynamic.response(physics.point_set, pose_to_transform(pose))
            return result.response_T_per_A

        plant = DynamicLinearPlant(
            response_for_pose,
            point_count=physics.point_set.count,
            channel_count=len(physics.response.channel_ids),
        )
    hardware = loaded.hardware
    limits = HardwareLimits(
        current_min_a=np.asarray(
            [channel.current_lower_a for channel in hardware.channels], dtype=np.float64
        ),
        current_max_a=np.asarray(
            [channel.current_upper_a for channel in hardware.channels], dtype=np.float64
        ),
        slew_rate_a_per_s=np.asarray(
            [channel.slew_rate_upper_a_per_s for channel in hardware.channels],
            dtype=np.float64,
        ),
        resistance_ohm=np.asarray(
            [channel.resistance_ohm for channel in hardware.channels], dtype=np.float64
        ),
        voltage_max_v=np.asarray(
            [channel.voltage_upper_v for channel in hardware.channels], dtype=np.float64
        ),
    )
    reward = loaded.config.reward
    nominal = (
        None
        if reward.nominal_currents_a is None
        else np.asarray(reward.nominal_currents_a, dtype=np.float64)
    )
    environment_reward = RewardConfig(
        field_threshold_t=reward.field_threshold_t,
        field_scale_t=float(reward.field_scale_t),
        field_weight=reward.field_weight,
        power_scale_w=float(reward.power_scale_w),
        power_weight=reward.power_weight,
        slew_scale_a=float(reward.slew_scale_a),
        slew_weight=reward.slew_weight,
        constraint_scale_a=float(reward.constraint_scale_a),
        constraint_weight=reward.constraint_weight,
        nominal_currents_a=nominal,
        nominal_scale_a=(None if reward.nominal_scale_a is None else float(reward.nominal_scale_a)),
        nominal_weight=reward.nominal_weight,
    )
    scenario = Scenario(
        external_field_t=loaded.scenario.external_field_t,
        pose=loaded.scenario.pose,
        episode_length=loaded.config.scenario.episode_length,
        random_start=loaded.config.scenario.random_start,
    )
    return MagneticControlEnv(
        plant=plant,
        hardware=limits,
        scenario=scenario,
        action_config=ActionConfig(
            delta_scale_a=limits.slew_rate_a_per_s * hardware.timestep_seconds,
            constraint_mode=loaded.config.constraint_mode,
        ),
        reward_config=environment_reward,
        timestep_s=hardware.timestep_seconds,
        point_weights=physics.point_set.weights,
        observation_basis=physics.basis,
        include_pose=loaded.config.include_pose,
    )


def _load_and_validate_public(path: str | Path) -> LoadedPackage:
    try:
        return _load_and_validate(path)
    except MagshieldEnvError:
        raise
    except FileNotFoundError as exc:
        raise io_error(
            "package_missing",
            str(exc),
            "Provide an exported environment directory or its environment.yaml.",
        ) from exc
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise validation_error(
            "package_contract",
            str(exc),
            "Restore the original package or rebuild it from validated sources.",
        ) from exc


def _load_and_validate(path: str | Path) -> LoadedPackage:
    directory, environment_path = _resolve_package_path(path)
    manifest_path = directory / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"package manifest does not exist: {manifest_path}")
    manifest = load_manifest(manifest_path)
    if manifest.get("schema_name") != "magshield_env.manifest":
        raise ValueError("manifest schema_name mismatch")
    if manifest.get("schema_version") != 1:
        raise ValueError("manifest schema_version mismatch")
    _verify_artifact_hashes(directory, manifest)
    config = load_environment_package_config(environment_path)
    physics = load_physics_h5(directory / config.physics.file)
    hardware = load_hardware_yaml(directory / config.hardware_file)
    scenario = load_scenario_h5(directory / config.scenario.file)
    loaded = LoadedPackage(directory, config, manifest, physics, hardware, scenario)
    _verify_semantics(loaded)
    return loaded


def _resolve_package_path(path: str | Path) -> tuple[Path, Path]:
    candidate = Path(path).expanduser().resolve()
    if candidate.is_dir():
        environment = candidate / "environment.yaml"
        directory = candidate
    elif candidate.is_file() and candidate.name == "environment.yaml":
        environment = candidate
        directory = candidate.parent
    else:
        raise FileNotFoundError(
            f"environment package path must be a directory or environment.yaml: {candidate}"
        )
    if not environment.is_file():
        raise FileNotFoundError(f"environment config does not exist: {environment}")
    return directory, environment


def _verify_artifact_hashes(directory: Path, manifest: dict[str, Any]) -> None:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        raise ValueError("manifest artifacts must be an object")
    required = {
        "environment.yaml",
        "physics.h5",
        "hardware.yaml",
        "scenario.h5",
        "README.md",
    }
    package_members = {path.name for path in directory.iterdir()}
    expected_members = required | {"manifest.json"}
    if package_members != expected_members:
        raise ValueError(f"package members must be exactly {sorted(expected_members)}")
    if set(artifacts) != required:
        raise ValueError(f"manifest artifact names must be exactly {sorted(required)}")
    for name in sorted(required):
        record = artifacts[name]
        if not isinstance(record, dict):
            raise ValueError(f"manifest artifact record {name!r} must be an object")
        artifact = directory / name
        if not artifact.is_file():
            raise FileNotFoundError(f"package artifact does not exist: {artifact}")
        if artifact.stat().st_size != record.get("size_bytes"):
            raise ValueError(f"artifact size mismatch: {name}")
        if file_sha256(artifact) != record.get("sha256"):
            raise ValueError(f"artifact SHA-256 mismatch: {name}")


def _verify_semantics(loaded: LoadedPackage) -> None:
    config = loaded.config
    manifest = loaded.manifest
    physics = loaded.physics
    response = physics.response.response_T_per_A
    channel_ids = physics.response.channel_ids
    hardware_ids = tuple(channel.channel_id for channel in loaded.hardware.channels)
    if hardware_ids != channel_ids:
        raise ValueError("hardware and physics channel identity/order differ")
    if loaded.scenario.external_field_t.shape[-2:] != (physics.point_set.count, 3):
        raise ValueError("scenario and physics point dimensions differ")
    if (
        loaded.scenario.external_field_component_frame
        != config.scenario.external_field_component_frame
    ):
        raise ValueError("scenario external field component frame differs from metadata")
    if loaded.scenario.external_field_component_frame != physics.response.coordinate_frame:
        raise ValueError("external field components and response use different frames")
    if config.scenario.has_pose != (loaded.scenario.pose is not None):
        raise ValueError("scenario pose presence differs from environment.yaml")
    if config.include_pose and loaded.scenario.pose is None:
        raise ValueError("include_pose=true but scenario has no pose")
    if config.physics.mode == "dynamic_geometry":
        if any(
            value is None
            for value in (
                physics.channels,
                physics.contributions,
                physics.path_frame,
                physics.pose_source_frame,
                physics.pose_target_frame,
            )
        ):
            raise ValueError("dynamic geometry package is incomplete")
        assert physics.channels is not None
        assert physics.contributions is not None
        assert physics.path_frame is not None
        assert physics.pose_source_frame is not None
        assert physics.pose_target_frame is not None
        if loaded.scenario.pose is None:
            raise ValueError("dynamic geometry package requires pose data")
        if config.physics.path_frame != physics.path_frame:
            raise ValueError("dynamic path frame differs between metadata and physics")
        if config.physics.pose_source_frame != physics.pose_source_frame:
            raise ValueError("dynamic pose source frame differs between metadata and physics")
        if config.physics.pose_target_frame != physics.pose_target_frame:
            raise ValueError("dynamic pose target frame differs between metadata and physics")
        if physics.point_set.coordinate_frame != physics.pose_source_frame:
            raise ValueError("dynamic pose source frame differs from the point-set frame")
        if physics.path_frame != physics.pose_target_frame:
            raise ValueError("dynamic pose target frame differs from the path frame")
        reference_pose = (
            loaded.scenario.pose
            if loaded.scenario.pose.ndim == 1
            else loaded.scenario.pose[0]
        )
        dynamic = DynamicPathResponse(
            physics.channels,
            lab_frame=physics.path_frame,
            contributions=physics.contributions,
            max_cache_entries=0,
        )
        rebuilt = dynamic.response(
            physics.point_set,
            pose_to_transform(reference_pose),
        ).response_T_per_A
        if not np.array_equal(rebuilt, response):
            raise ValueError("dynamic reference response differs from stored conductor geometry")
    elif any(
        value is not None
        for value in (
            physics.channels,
            physics.contributions,
            physics.path_frame,
            physics.pose_source_frame,
            physics.pose_target_frame,
        )
    ):
        raise ValueError("fixed package must not contain runtime geometry")
    if config.observation_mode == "basis" and physics.basis is None:
        raise ValueError("basis observation mode requires observation_basis")
    if config.observation_mode == "full_field" and physics.basis is not None:
        raise ValueError("full_field observation mode must not contain observation_basis")
    if config.observation_basis_component_frame != physics.basis_component_frame:
        raise ValueError("basis component frame differs between metadata and physics")
    if (
        physics.basis_component_frame is not None
        and physics.basis_component_frame != physics.response.coordinate_frame
    ):
        raise ValueError("basis components and response use different frames")
    nominal = config.reward.nominal_currents_a
    if nominal is not None and len(nominal) != len(channel_ids):
        raise ValueError("nominal current count differs from channel count")
    arrays = {
        "point_ids": canonical_json_sha256(list(physics.point_set.point_ids)),
        "points_m": array_sha256(physics.point_set.points_m),
        "weights": array_sha256(physics.point_set.weights),
        "channel_ids": canonical_json_sha256(list(channel_ids)),
        "response_T_per_A": array_sha256(response),
        "external_field_t": array_sha256(loaded.scenario.external_field_t),
        "pose": (None if loaded.scenario.pose is None else array_sha256(loaded.scenario.pose)),
        "observation_basis": (None if physics.basis is None else array_sha256(physics.basis)),
    }
    if manifest.get("arrays") != arrays:
        raise ValueError("manifest semantic array identities differ from package arrays")
    if manifest.get("point_count") != physics.point_set.count:
        raise ValueError("manifest point_count mismatch")
    if manifest.get("channel_count") != len(channel_ids):
        raise ValueError("manifest channel_count mismatch")
    if manifest.get("response_shape") != list(response.shape):
        raise ValueError("manifest response_shape mismatch")
    rank = int(np.linalg.matrix_rank(response.reshape(-1, response.shape[-1])))
    if manifest.get("response_rank") != rank:
        raise ValueError("manifest response_rank mismatch")
    identity_inputs = manifest.get("identity_inputs")
    if not isinstance(identity_inputs, dict):
        raise ValueError("manifest identity_inputs must be an object")
    environment_identity = config.model_dump(mode="json")
    environment_identity.pop("name")
    if identity_inputs.get("environment") != environment_identity:
        raise ValueError("manifest environment identity differs from environment.yaml")
    if identity_inputs.get("hardware") != loaded.hardware.model_dump(mode="json"):
        raise ValueError("manifest hardware identity differs from hardware.yaml")
    if identity_inputs.get("arrays") != arrays:
        raise ValueError("manifest identity array inputs differ from package arrays")
    sources = manifest.get("sources")
    if not isinstance(sources, dict):
        raise ValueError("manifest sources must be an object")
    source_hashes: dict[str, str] = {}
    for key, record in sources.items():
        if not isinstance(key, str) or not key or not isinstance(record, dict):
            raise ValueError("manifest source records must be named objects")
        if set(record) != {"name", "size_bytes", "sha256"}:
            raise ValueError("manifest source records require name, size_bytes, and sha256")
        if (
            not isinstance(record["name"], str)
            or not record["name"]
            or isinstance(record["size_bytes"], bool)
            or not isinstance(record["size_bytes"], int)
            or record["size_bytes"] < 0
            or not isinstance(record["sha256"], str)
            or len(record["sha256"]) != 64
        ):
            raise ValueError("manifest source record values are invalid")
        source_hashes[key] = record["sha256"]
    if identity_inputs.get("sources") != dict(sorted(source_hashes.items())):
        raise ValueError("manifest identity source hashes differ from source records")
    if identity_inputs.get("point_frame") != physics.point_set.coordinate_frame:
        raise ValueError("manifest identity point frame differs from physics")
    if identity_inputs.get("response_frame") != physics.response.coordinate_frame:
        raise ValueError("manifest identity response frame differs from physics")
    units = canonical_units()
    if manifest.get("units") != units:
        raise ValueError("manifest units must equal the canonical SI unit contract")
    if identity_inputs.get("units") != units:
        raise ValueError("manifest identity units differ from the canonical SI contract")
    provenance = _validate_build_provenance(manifest)
    if identity_inputs.get("build_provenance") != provenance:
        raise ValueError("manifest identity build provenance differs from manifest")
    expected_identity = canonical_json_sha256(identity_inputs)
    if manifest.get("package_identity") != expected_identity:
        raise ValueError("manifest package_identity mismatch")
    frames = manifest.get("frames")
    expected_frames = {
        "points": physics.point_set.coordinate_frame,
        "response": physics.response.coordinate_frame,
        "paths": physics.path_frame,
        "pose_source": physics.pose_source_frame,
        "pose_target": physics.pose_target_frame,
        "external_field_components": loaded.scenario.external_field_component_frame,
        "observation_basis_components": physics.basis_component_frame,
    }
    if frames != expected_frames:
        raise ValueError("manifest coordinate frames differ from physics")


def _validate_build_provenance(manifest: dict[str, Any]) -> dict[str, Any]:
    provenance = manifest.get("build_provenance")
    if not isinstance(provenance, dict):
        raise ValueError("manifest build_provenance must be an object")
    sources = manifest.get("sources")
    if not isinstance(sources, dict):
        raise ValueError("manifest sources must be an object")
    source_keys = set(sources)
    if "fixed_response" in source_keys:
        expected_kind = "fixed_matrix"
    elif {"geometry_paths", "geometry_channels"}.issubset(source_keys):
        expected_kind = "geometry"
    elif any(key.startswith("finite_element_") for key in source_keys):
        expected_kind = "finite_element"
    else:
        raise ValueError("manifest sources do not identify a supported forward kind")
    if provenance.get("forward_kind") != expected_kind:
        raise ValueError("manifest forward_kind differs from source records")
    if provenance.get("source_unit_contract") != "canonical_si":
        raise ValueError("manifest source_unit_contract must be canonical_si")
    allowed = {"forward_kind", "source_unit_contract"}
    if expected_kind == "finite_element":
        tolerance = provenance.get("coordinate_tolerance_m")
        if (
            isinstance(tolerance, bool)
            or not isinstance(tolerance, (int, float))
            or not np.isfinite(tolerance)
            or tolerance < 0.0
        ):
            raise ValueError("finite-element provenance requires coordinate_tolerance_m")
        allowed.add("coordinate_tolerance_m")
    if set(provenance) != allowed:
        raise ValueError(f"manifest build_provenance keys must be exactly {sorted(allowed)}")
    return provenance
