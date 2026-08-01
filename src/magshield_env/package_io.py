"""Canonical serialization for self-contained environment packages."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import yaml
from numpy.typing import NDArray

from .domain.config import HardwareConfig
from .domain.package import EnvironmentPackageConfig
from .physics import (
    ChannelPath,
    FieldContribution,
    PointSet,
    Polyline,
    ResponseMatrix,
    RigidTransform,
)

FloatArray = NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class LoadedPhysics:
    """Carry every item consumed when reconstructing a runtime plant.

    ``point_set`` and ``response`` bind matrix axes, ``basis`` optionally
    compresses observations and ``basis_component_frame`` binds its vector
    components. ``channels`` and ``contributions`` reconstruct dynamic
    geometry; ``path_frame`` and the pose source/target frames define the
    transform. Fixed packages leave the geometry members empty.
    """

    point_set: PointSet
    response: ResponseMatrix
    basis: FloatArray | None
    basis_component_frame: str | None
    channels: tuple[ChannelPath, ...] | None
    contributions: tuple[FieldContribution, ...] | None
    path_frame: str | None
    pose_source_frame: str | None
    pose_target_frame: str | None


@dataclass(frozen=True, slots=True)
class LoadedScenario:
    """Carry field, component frame, and optional pose consumed by ``Scenario``."""

    external_field_t: FloatArray
    external_field_component_frame: str
    pose: FloatArray | None


def _strings(values: tuple[str, ...]) -> np.ndarray:
    string_type = h5py.string_dtype(encoding="utf-8")
    return np.asarray(values, dtype=string_type)


def _decode_strings(values: Any, *, name: str) -> tuple[str, ...]:
    array = np.asarray(values)
    if array.ndim != 1:
        raise ValueError(f"{name} must be a one-dimensional string dataset")
    decoded = tuple(
        value.decode("utf-8") if isinstance(value, bytes) else str(value)
        for value in array.tolist()
    )
    if not decoded or any(not value for value in decoded):
        raise ValueError(f"{name} must contain non-empty strings")
    return decoded


def _dataset(group: h5py.Group, name: str, data: Any, **kwargs: Any) -> h5py.Dataset:
    return group.create_dataset(name, data=data, track_times=False, **kwargs)


def write_physics_h5(
    path: Path,
    *,
    point_set: PointSet,
    response: ResponseMatrix,
    basis: FloatArray | None,
    basis_component_frame: str | None,
    channels: tuple[ChannelPath, ...] | None,
    contributions: tuple[FieldContribution, ...] | None,
    path_frame: str | None,
    pose_source_frame: str | None,
    pose_target_frame: str | None,
) -> None:
    """Write canonical response, sampling, and optional runtime geometry."""

    basis_members = (basis, basis_component_frame)
    if any(value is None for value in basis_members) and not all(
        value is None for value in basis_members
    ):
        raise ValueError("observation basis and component frame must be supplied together")
    geometry_members = (
        channels,
        contributions,
        path_frame,
        pose_source_frame,
        pose_target_frame,
    )
    geometry_present = all(value is not None for value in geometry_members)
    if any(value is None for value in geometry_members) and not all(
        value is None for value in geometry_members
    ):
        raise ValueError("dynamic geometry members must be supplied together")
    with h5py.File(path, "w", libver="earliest") as file:
        file.attrs["schema_name"] = "magshield_env.physics"
        file.attrs["schema_version"] = 1
        file.attrs["point_coordinate_frame"] = point_set.coordinate_frame
        file.attrs["response_coordinate_frame"] = response.coordinate_frame
        file.attrs["length_unit"] = "m"
        file.attrs["field_response_unit"] = "T/A"
        _dataset(file, "point_ids", _strings(point_set.point_ids))
        _dataset(file, "points_m", point_set.points_m, dtype=np.float64)
        _dataset(file, "weights", point_set.weights, dtype=np.float64)
        _dataset(file, "channel_ids", _strings(response.channel_ids))
        _dataset(
            file,
            "response_T_per_A",
            response.response_T_per_A,
            dtype=np.float64,
        )
        if basis is not None:
            assert basis_component_frame is not None
            basis_dataset = _dataset(file, "observation_basis", basis, dtype=np.float64)
            basis_dataset.attrs["component_frame"] = basis_component_frame
        if geometry_present:
            assert channels is not None
            assert contributions is not None
            assert path_frame is not None
            assert pose_source_frame is not None
            assert pose_target_frame is not None
            _write_geometry(
                file,
                channels,
                contributions,
                path_frame,
                pose_source_frame,
                pose_target_frame,
            )


def _write_geometry(
    file: h5py.File,
    channels: tuple[ChannelPath, ...],
    contributions: tuple[FieldContribution, ...],
    path_frame: str,
    pose_source_frame: str,
    pose_target_frame: str,
) -> None:
    group = file.create_group("geometry", track_order=True)
    group.attrs["path_frame"] = path_frame
    group.attrs["pose_source_frame"] = pose_source_frame
    group.attrs["pose_target_frame"] = pose_target_frame
    paths = tuple(
        (channel_index, polyline)
        for channel_index, channel in enumerate(channels)
        for polyline in channel.polylines
    )
    offsets = [0]
    vertices: list[np.ndarray] = []
    for _, polyline in paths:
        vertices.append(polyline.vertices_m)
        offsets.append(offsets[-1] + len(polyline.vertices_m))
    _dataset(group, "path_ids", _strings(tuple(path.path_id for _, path in paths)))
    _dataset(
        group,
        "path_channel_index",
        np.asarray([index for index, _ in paths], dtype=np.int64),
        dtype=np.int64,
    )
    _dataset(
        group,
        "path_closed",
        np.asarray([path.closed for _, path in paths], dtype=np.bool_),
        dtype=np.bool_,
    )
    _dataset(group, "path_vertex_offsets", np.asarray(offsets, dtype=np.int64))
    _dataset(group, "vertices_m", np.concatenate(vertices, axis=0), dtype=np.float64)
    _dataset(
        group,
        "contribution_rotation",
        np.stack([item.transform.rotation for item in contributions]),
        dtype=np.float64,
    )
    _dataset(
        group,
        "contribution_translation_m",
        np.stack([item.transform.translation_m for item in contributions]),
        dtype=np.float64,
    )
    _dataset(
        group,
        "contribution_allow_improper",
        np.asarray([item.transform.allow_improper for item in contributions], dtype=np.bool_),
    )
    _dataset(
        group,
        "contribution_gain",
        np.asarray([item.gain for item in contributions], dtype=np.float64),
    )


def load_physics_h5(path: Path) -> LoadedPhysics:
    """Load and validate canonical physics and optional runtime geometry."""

    with h5py.File(path, "r") as file:
        if file.attrs.get("schema_name") != "magshield_env.physics":
            raise ValueError("physics.h5 schema_name mismatch")
        if int(file.attrs.get("schema_version", -1)) != 1:
            raise ValueError("physics.h5 schema_version mismatch")
        if file.attrs.get("length_unit") != "m":
            raise ValueError("physics.h5 length_unit must be 'm'")
        if file.attrs.get("field_response_unit") != "T/A":
            raise ValueError("physics.h5 field_response_unit must be 'T/A'")
        required = {"point_ids", "points_m", "weights", "channel_ids", "response_T_per_A"}
        if not required.issubset(file.keys()):
            raise ValueError(
                f"physics.h5 is missing datasets {sorted(required - set(file.keys()))}"
            )
        point_frame = str(file.attrs.get("point_coordinate_frame", ""))
        response_frame = str(file.attrs.get("response_coordinate_frame", ""))
        point_set = PointSet(
            _decode_strings(file["point_ids"][...], name="point_ids"),
            np.asarray(file["points_m"][...], dtype=np.float64),
            np.asarray(file["weights"][...], dtype=np.float64),
            point_frame,
        )
        response = ResponseMatrix(
            point_set.point_ids,
            _decode_strings(file["channel_ids"][...], name="channel_ids"),
            np.asarray(file["response_T_per_A"][...], dtype=np.float64),
            response_frame,
        )
        basis: FloatArray | None = None
        basis_component_frame: str | None = None
        if "observation_basis" in file:
            basis_dataset = file["observation_basis"]
            basis = np.asarray(basis_dataset[...], dtype=np.float64)
            basis_component_frame = str(basis_dataset.attrs.get("component_frame", ""))
            if not basis_component_frame:
                raise ValueError("observation_basis component_frame is required")
        channels: tuple[ChannelPath, ...] | None = None
        contributions: tuple[FieldContribution, ...] | None = None
        path_frame: str | None = None
        pose_source_frame: str | None = None
        pose_target_frame: str | None = None
        if "geometry" in file:
            (
                channels,
                contributions,
                path_frame,
                pose_source_frame,
                pose_target_frame,
            ) = _load_geometry(
                file["geometry"], response.channel_ids
            )
    return LoadedPhysics(
        point_set,
        response,
        basis,
        basis_component_frame,
        channels,
        contributions,
        path_frame,
        pose_source_frame,
        pose_target_frame,
    )


def _load_geometry(
    group: h5py.Group, channel_ids: tuple[str, ...]
) -> tuple[tuple[ChannelPath, ...], tuple[FieldContribution, ...], str, str, str]:
    required = {
        "path_ids",
        "path_channel_index",
        "path_closed",
        "path_vertex_offsets",
        "vertices_m",
        "contribution_rotation",
        "contribution_translation_m",
        "contribution_allow_improper",
        "contribution_gain",
    }
    if not required.issubset(group.keys()):
        raise ValueError(
            f"physics geometry is missing datasets {sorted(required - set(group.keys()))}"
        )
    path_frame = str(group.attrs.get("path_frame", ""))
    pose_source_frame = str(group.attrs.get("pose_source_frame", ""))
    pose_target_frame = str(group.attrs.get("pose_target_frame", ""))
    if not path_frame or not pose_source_frame or not pose_target_frame:
        raise ValueError("physics geometry requires path and pose source/target frames")
    if pose_target_frame != path_frame:
        raise ValueError("physics geometry pose_target_frame must equal path_frame")
    path_ids = _decode_strings(group["path_ids"][...], name="geometry/path_ids")
    channel_index = np.asarray(group["path_channel_index"][...], dtype=np.int64)
    closed = np.asarray(group["path_closed"][...], dtype=np.bool_)
    offsets = np.asarray(group["path_vertex_offsets"][...], dtype=np.int64)
    vertices = np.asarray(group["vertices_m"][...], dtype=np.float64)
    path_count = len(path_ids)
    if channel_index.shape != (path_count,) or closed.shape != (path_count,):
        raise ValueError("physics geometry path metadata shapes are inconsistent")
    if offsets.shape != (path_count + 1,) or offsets[0] != 0 or offsets[-1] != len(vertices):
        raise ValueError("physics geometry path offsets are inconsistent")
    if np.any(np.diff(offsets) <= 0):
        raise ValueError("physics geometry path offsets must be strictly increasing")
    if np.any(channel_index < 0) or np.any(channel_index >= len(channel_ids)):
        raise ValueError("physics geometry path channel index is out of range")
    by_channel: list[list[Polyline]] = [[] for _ in channel_ids]
    for index, path_id in enumerate(path_ids):
        start = int(offsets[index])
        end = int(offsets[index + 1])
        by_channel[int(channel_index[index])].append(
            Polyline(path_id, vertices[start:end], bool(closed[index]))
        )
    channels = tuple(
        ChannelPath(channel_id, tuple(polylines))
        for channel_id, polylines in zip(channel_ids, by_channel, strict=True)
    )
    rotations = np.asarray(group["contribution_rotation"][...], dtype=np.float64)
    translations = np.asarray(group["contribution_translation_m"][...], dtype=np.float64)
    improper = np.asarray(group["contribution_allow_improper"][...], dtype=np.bool_)
    gains = np.asarray(group["contribution_gain"][...], dtype=np.float64)
    count = len(gains)
    if rotations.shape != (count, 3, 3) or translations.shape != (count, 3):
        raise ValueError("physics geometry contribution shapes are inconsistent")
    if improper.shape != (count,) or count == 0:
        raise ValueError("physics geometry contribution metadata is inconsistent")
    contributions = tuple(
        FieldContribution(RigidTransform(rotation, translation, bool(allow)), float(gain))
        for rotation, translation, allow, gain in zip(
            rotations, translations, improper, gains, strict=True
        )
    )
    return channels, contributions, path_frame, pose_source_frame, pose_target_frame


def write_scenario_h5(
    path: Path,
    *,
    external_field_t: FloatArray,
    external_field_component_frame: str,
    pose: FloatArray | None,
) -> None:
    """Write canonical external field and optional pose arrays."""

    with h5py.File(path, "w", libver="earliest") as file:
        file.attrs["schema_name"] = "magshield_env.scenario"
        file.attrs["schema_version"] = 1
        file.attrs["field_unit"] = "T"
        file.attrs["external_field_component_frame"] = external_field_component_frame
        file.attrs["pose_layout"] = "translation_m,quaternion_xyzw"
        _dataset(file, "external_field_t", external_field_t, dtype=np.float64)
        if pose is not None:
            _dataset(file, "pose", pose, dtype=np.float64)


def load_scenario_h5(path: Path) -> LoadedScenario:
    """Load canonical external field and optional pose arrays."""

    with h5py.File(path, "r") as file:
        if file.attrs.get("schema_name") != "magshield_env.scenario":
            raise ValueError("scenario.h5 schema_name mismatch")
        if int(file.attrs.get("schema_version", -1)) != 1:
            raise ValueError("scenario.h5 schema_version mismatch")
        if file.attrs.get("field_unit") != "T":
            raise ValueError("scenario.h5 field_unit must be 'T'")
        if file.attrs.get("pose_layout") != "translation_m,quaternion_xyzw":
            raise ValueError("scenario.h5 pose_layout mismatch")
        component_frame = str(file.attrs.get("external_field_component_frame", ""))
        if not component_frame:
            raise ValueError("scenario.h5 external_field_component_frame is required")
        if "external_field_t" not in file:
            raise ValueError("scenario.h5 is missing external_field_t")
        field = np.asarray(file["external_field_t"][...], dtype=np.float64)
        pose = np.asarray(file["pose"][...], dtype=np.float64) if "pose" in file else None
    return LoadedScenario(field, component_frame, pose)


def write_yaml(path: Path, payload: Any) -> None:
    """Write deterministic UTF-8 YAML for JSON-compatible values."""

    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
        newline="\n",
    )


def load_hardware_yaml(path: Path) -> HardwareConfig:
    """Load strict portable hardware YAML."""

    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("hardware.yaml must be a YAML object")
    return HardwareConfig.model_validate(payload)


def load_manifest(path: Path) -> dict[str, Any]:
    """Load a manifest JSON object without repairing malformed values."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("manifest.json must be a JSON object")
    return payload


def write_manifest(path: Path, payload: dict[str, Any]) -> None:
    """Write canonical manifest JSON."""

    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def write_environment_yaml(path: Path, config: EnvironmentPackageConfig) -> None:
    """Write one strict portable environment configuration."""

    write_yaml(path, config.model_dump(mode="json"))
