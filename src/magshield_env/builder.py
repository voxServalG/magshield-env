"""Resolve declared physical sources into one atomic environment package."""

from __future__ import annotations

import csv
import shutil
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import h5py
import meshio
import numpy as np
from numpy.typing import NDArray

from .domain.config import (
    BoxRegion,
    BuildConfig,
    CylinderRegion,
    FiniteElementForward,
    FixedMatrixForward,
    GeometryForward,
    ImportedRegion,
    SphereRegion,
    SphereSurfaceRegion,
    StaticScenario,
    TrajectoryScenario,
)
from .domain.errors import MagshieldEnvError, io_error, validation_error
from .domain.geometry import load_geometry_channels_config
from .domain.identity import array_sha256, canonical_json_sha256, file_sha256
from .domain.package import (
    BuildReport,
    EnvironmentPackageConfig,
    PackagedPhysics,
    PackagedScenario,
    canonical_units,
)
from .package_io import (
    write_environment_yaml,
    write_manifest,
    write_physics_h5,
    write_scenario_h5,
    write_yaml,
)
from .physics import (
    ChannelPath,
    FieldContribution,
    PointSet,
    ResponseMatrix,
    RigidTransform,
    assemble_response_matrix,
    generate_box,
    generate_cylinder,
    generate_sphere,
    generate_sphere_surface,
    load_channel_paths_csv,
    load_channel_paths_vtk,
    load_field_csv,
    load_field_hdf5,
    load_field_vtk,
    load_point_set,
    response_at_pose,
)

FloatArray = NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class ResolvedBuild:
    """Carry every validated value consumed by package serialization.

    ``config`` supplies portable behavior, ``point_set`` and ``response`` bind
    the physical matrix axes, ``external_field_t`` and ``pose`` form the
    scenario, and ``basis`` optionally projects observations. ``channels``,
    ``contributions``, and ``path_frame`` jointly enable runtime geometry;
    ``source_records`` binds every imported file into the manifest.
    """

    config: BuildConfig
    point_set: PointSet
    response: ResponseMatrix
    external_field_t: FloatArray
    pose: FloatArray | None
    basis: FloatArray | None
    channels: tuple[ChannelPath, ...] | None
    contributions: tuple[FieldContribution, ...] | None
    path_frame: str | None
    source_records: dict[str, dict[str, Any]]

    @property
    def physics_mode(self) -> Literal["fixed", "dynamic_geometry"]:
        return "dynamic_geometry" if self.channels is not None else "fixed"


def build_environment(config: BuildConfig | Mapping[str, Any]) -> BuildReport:
    """Build one self-contained package without overwriting an existing path."""

    try:
        validated = (
            config if isinstance(config, BuildConfig) else BuildConfig.model_validate(config)
        )
        resolved = _resolve(validated)
        return _export(resolved)
    except MagshieldEnvError:
        raise
    except FileNotFoundError as exc:
        raise io_error(
            "source_missing",
            str(exc),
            "Provide the declared source file and run the build again.",
        ) from exc
    except (OSError, ValueError) as exc:
        raise validation_error(
            "build_contract",
            str(exc),
            "Correct units, identities, frames, shapes, or ordering and rebuild.",
        ) from exc


def inspect_build(config: BuildConfig | Mapping[str, Any]) -> dict[str, Any]:
    """Resolve all inputs without writing and return final build dimensions."""

    validated = config if isinstance(config, BuildConfig) else BuildConfig.model_validate(config)
    resolved = _resolve(validated)
    matrix = resolved.response.response_T_per_A.reshape(-1, len(resolved.response.channel_ids))
    return {
        "point_count": resolved.point_set.count,
        "channel_count": len(resolved.response.channel_ids),
        "response_shape": list(resolved.response.response_T_per_A.shape),
        "rank": int(np.linalg.matrix_rank(matrix)),
        "memory_estimate_bytes": int(resolved.response.response_T_per_A.nbytes),
        "physics_mode": resolved.physics_mode,
        "dynamic_compute_cost": (
            "finite-segment Biot-Savart per uncached pose"
            if resolved.physics_mode == "dynamic_geometry"
            else "none"
        ),
    }


def _resolve(config: BuildConfig) -> ResolvedBuild:
    sources: dict[str, dict[str, Any]] = {}
    point_set = _resolve_region(config, sources)
    external_field, pose = _resolve_scenario(config, point_set, sources)
    response, channels, contributions, path_frame = _resolve_forward(
        config, point_set, pose, sources
    )
    if config.scenario.external_field_component_frame != response.coordinate_frame:
        raise ValueError(
            "external field component frame must equal the response coordinate frame"
        )
    _require_channel_identity(config, response.channel_ids)
    basis = _resolve_basis(config, point_set, response.coordinate_frame, sources)
    if config.environment.include_pose and pose is None:
        raise ValueError("include_pose=true requires a static or trajectory pose")
    if isinstance(config.forward, GeometryForward) and pose is None:
        raise ValueError("geometry forward mode requires a static or trajectory pose")
    return ResolvedBuild(
        config,
        point_set,
        response,
        external_field,
        pose,
        basis,
        channels,
        contributions,
        path_frame,
        sources,
    )


def _resolve_region(config: BuildConfig, sources: dict[str, dict[str, Any]]) -> PointSet:
    region = config.region
    if isinstance(region, SphereRegion):
        return generate_sphere(
            region.radius_m,
            region.spacing_m,
            center_m=region.center_m,
            coordinate_frame=region.frame,
        )
    if isinstance(region, SphereSurfaceRegion):
        return generate_sphere_surface(
            region.radius_m,
            region.point_count,
            center_m=region.center_m,
            coordinate_frame=region.frame,
        )
    if isinstance(region, BoxRegion):
        minimum = np.asarray(region.minimum_m, dtype=np.float64)
        maximum = np.asarray(region.maximum_m, dtype=np.float64)
        return generate_box(
            maximum - minimum,
            region.spacing_m,
            center_m=(maximum + minimum) / 2.0,
            coordinate_frame=region.frame,
        )
    if isinstance(region, CylinderRegion):
        return generate_cylinder(
            region.radius_m,
            region.height_m,
            region.spacing_m,
            center_m=region.center_m,
            axis=region.axis,
            coordinate_frame=region.frame,
        )
    if not isinstance(region, ImportedRegion):
        raise TypeError(f"unsupported region type: {type(region)!r}")
    _record_source(sources, "region", region.path)
    if region.path.suffix.lower() in {".h5", ".hdf5"} and region.dataset != "/":
        point_set = _load_point_group(region.path, region.dataset)
    else:
        frame = None if region.path.suffix.lower() in {".h5", ".hdf5"} else region.frame
        point_set = load_point_set(region.path, coordinate_frame=frame)
    if point_set.coordinate_frame != region.frame:
        raise ValueError(
            f"imported point frame {point_set.coordinate_frame!r} does not match {region.frame!r}"
        )
    return point_set


def _load_point_group(path: Path, dataset: str) -> PointSet:
    with h5py.File(path, "r") as file:
        if dataset not in file or not isinstance(file[dataset], h5py.Group):
            raise ValueError(f"point dataset {dataset!r} must name an HDF5 group")
        group = file[dataset]
        required = {"point_ids", "points_m", "weights"}
        if not required.issubset(group.keys()):
            raise ValueError(f"point group requires datasets {sorted(required)}")
        if group.attrs.get("length_unit") != "m":
            raise ValueError("point group length_unit must be 'm'")
        ids = _h5_strings(group["point_ids"][...], name="point_ids")
        return PointSet(
            ids,
            np.asarray(group["points_m"][...], dtype=np.float64),
            np.asarray(group["weights"][...], dtype=np.float64),
            str(group.attrs.get("coordinate_frame", "")),
        )


def _resolve_forward(
    config: BuildConfig,
    point_set: PointSet,
    pose: FloatArray | None,
    sources: dict[str, dict[str, Any]],
) -> tuple[
    ResponseMatrix,
    tuple[ChannelPath, ...] | None,
    tuple[FieldContribution, ...] | None,
    str | None,
]:
    forward = config.forward
    if isinstance(forward, FixedMatrixForward):
        _record_source(sources, "fixed_response", forward.path)
        return _load_fixed_response(forward, point_set), None, None, None
    if isinstance(forward, FiniteElementForward):
        fields = []
        for index, (path, channel_id) in enumerate(
            zip(forward.channel_files, forward.channel_ids, strict=True)
        ):
            _record_source(sources, f"finite_element_{index:04d}", path)
            fields.append(_load_field(path, channel_id, point_set, forward.coordinate_tolerance_m))
        response = assemble_response_matrix(point_set, fields, channel_ids=forward.channel_ids)
        return response, None, None, None
    if not isinstance(forward, GeometryForward):
        raise TypeError(f"unsupported forward type: {type(forward)!r}")
    if point_set.coordinate_frame != forward.pose_source_frame:
        raise ValueError(
            "geometry pose_source_frame must equal the sampling point coordinate frame"
        )
    if forward.pose_target_frame != forward.path_frame:
        raise ValueError("geometry pose_target_frame must equal path_frame")
    _record_source(sources, "geometry_paths", forward.paths)
    _record_source(sources, "geometry_channels", forward.channels)
    channels = _load_paths(forward.paths)
    metadata = load_geometry_channels_config(forward.channels)
    actual_ids = tuple(channel.channel_id for channel in channels)
    if actual_ids != metadata.channel_ids:
        raise ValueError(
            f"path channel order {actual_ids} does not match metadata {metadata.channel_ids}"
        )
    contributions = tuple(
        FieldContribution(
            RigidTransform(
                np.asarray(item.rotation, dtype=np.float64),
                np.asarray(item.translation_m, dtype=np.float64),
                item.allow_improper,
            ),
            item.gain,
        )
        for item in metadata.contributions
    )
    if pose is None:
        raise ValueError("geometry forward mode requires pose data")
    reference_pose = pose if pose.ndim == 1 else pose[0]
    response = response_at_pose(
        point_set,
        channels,
        pose_to_transform(reference_pose),
        lab_frame=forward.path_frame,
        contributions=contributions,
    )
    return response, channels, contributions, forward.path_frame


def _load_fixed_response(forward: FixedMatrixForward, point_set: PointSet) -> ResponseMatrix:
    if forward.path.suffix.lower() not in {".h5", ".hdf5"}:
        raise ValueError("fixed_matrix requires an HDF5 file")
    with h5py.File(forward.path, "r") as file:
        if forward.dataset not in file:
            raise ValueError(f"fixed response dataset {forward.dataset!r} does not exist")
        required = {"point_ids", "channel_ids"}
        if not required.issubset(file.keys()):
            raise ValueError(
                f"fixed response HDF5 is missing datasets {sorted(required - set(file.keys()))}"
            )
        if file.attrs.get("field_unit") != "T/A":
            raise ValueError("fixed response field_unit must be 'T/A'")
        stored_frame = str(file.attrs.get("coordinate_frame", ""))
        if not stored_frame:
            raise ValueError("fixed response coordinate_frame is required")
        response = np.asarray(file[forward.dataset][...], dtype=np.float64)
        stored_points = _h5_strings(file["point_ids"][...], name="point_ids")
        if stored_points != point_set.point_ids:
            raise ValueError("fixed response point identity/order does not match the point set")
        stored_channels = _h5_strings(file["channel_ids"][...], name="channel_ids")
        if stored_channels != forward.channel_ids:
            raise ValueError("fixed response channel identity/order does not match config")
        if stored_frame != point_set.coordinate_frame:
            raise ValueError("fixed response coordinate frame does not match the point set")
    return ResponseMatrix(
        point_set.point_ids,
        forward.channel_ids,
        response,
        point_set.coordinate_frame,
    )


def _load_field(
    path: Path,
    channel_id: str,
    point_set: PointSet,
    coordinate_tolerance_m: float,
) -> Any:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return load_field_csv(
            path, channel_id=channel_id, coordinate_frame=point_set.coordinate_frame
        )
    if suffix in {".h5", ".hdf5"}:
        return load_field_hdf5(path, channel_id=channel_id)
    if suffix in {".vtk", ".vtu"}:
        mesh = meshio.read(path)
        coordinates = np.asarray(mesh.points, dtype=np.float64)
        if coordinates.shape != point_set.points_m.shape or not np.allclose(
            coordinates,
            point_set.points_m,
            rtol=0.0,
            atol=coordinate_tolerance_m,
        ):
            raise ValueError(
                f"finite-element coordinates for {channel_id!r} do not match the point set"
            )
        return load_field_vtk(
            path, channel_id=channel_id, coordinate_frame=point_set.coordinate_frame
        )
    raise ValueError(f"unsupported finite-element field suffix: {suffix}")


def _load_paths(path: Path) -> tuple[ChannelPath, ...]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return load_channel_paths_csv(path)
    if suffix in {".vtk", ".vtu", ".vtp"}:
        return load_channel_paths_vtk(path)
    raise ValueError(f"unsupported conductor path suffix: {suffix}")


def _resolve_scenario(
    config: BuildConfig,
    point_set: PointSet,
    sources: dict[str, dict[str, Any]],
) -> tuple[FloatArray, FloatArray | None]:
    scenario = config.scenario
    if isinstance(scenario, StaticScenario):
        if scenario.external_field is None:
            field = np.zeros((point_set.count, 3), dtype=np.float64)
        else:
            _record_source(sources, "static_external_field", scenario.external_field)
            field = _load_external_field(
                scenario.external_field,
                point_set,
                scenario.external_field_component_frame,
            )
        pose = None
        if scenario.translation_m is not None:
            assert scenario.quaternion_xyzw is not None
            pose = _pose_array(
                np.asarray(scenario.translation_m, dtype=np.float64),
                np.asarray(scenario.quaternion_xyzw, dtype=np.float64),
            )
        return field, pose
    if not isinstance(scenario, TrajectoryScenario):
        raise TypeError(f"unsupported scenario type: {type(scenario)!r}")
    _record_source(sources, "trajectory", scenario.path)
    with h5py.File(scenario.path, "r") as file:
        if file.attrs.get("field_unit") != "T":
            raise ValueError("trajectory HDF5 field_unit must be 'T'")
        stored_component_frame = str(
            file.attrs.get("external_field_component_frame", "")
        )
        if stored_component_frame != scenario.external_field_component_frame:
            raise ValueError(
                "trajectory external field component frame does not match the configuration"
            )
        if scenario.external_field_dataset not in file:
            raise ValueError(
                f"trajectory field dataset {scenario.external_field_dataset!r} does not exist"
            )
        field = np.asarray(file[scenario.external_field_dataset][...], dtype=np.float64)
        if "point_ids" not in file:
            raise ValueError("trajectory HDF5 must contain point_ids")
        if _h5_strings(file["point_ids"][...], name="point_ids") != point_set.point_ids:
            raise ValueError("trajectory point identity/order does not match the point set")
        pose = None
        if scenario.translation_dataset is not None:
            assert scenario.quaternion_dataset is not None
            if file.attrs.get("pose_length_unit") != "m":
                raise ValueError("trajectory HDF5 pose_length_unit must be 'm'")
            if file.attrs.get("pose_quaternion_order") != "xyzw":
                raise ValueError("trajectory HDF5 pose_quaternion_order must be 'xyzw'")
            if scenario.translation_dataset not in file or scenario.quaternion_dataset not in file:
                raise ValueError("trajectory pose datasets do not exist")
            pose = _pose_array(
                np.asarray(file[scenario.translation_dataset][...], dtype=np.float64),
                np.asarray(file[scenario.quaternion_dataset][...], dtype=np.float64),
            )
    _validate_external_field(field, point_set)
    if field.ndim != 3:
        raise ValueError("trajectory external field must have shape [frame, point, 3]")
    if pose is not None and pose.ndim != 2:
        raise ValueError("trajectory pose must contain one pose per frame")
    if pose is not None and len(pose) != len(field):
        raise ValueError("trajectory field and pose frame counts differ")
    if scenario.episode_length > len(field):
        raise ValueError("trajectory episode_length exceeds available frames")
    return field, pose


def _load_external_field(
    path: Path,
    point_set: PointSet,
    component_frame: str,
) -> FloatArray:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open("r", encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            expected = ("point_id", "bx_T", "by_T", "bz_T")
            if tuple(reader.fieldnames or ()) != expected:
                raise ValueError(f"external field CSV columns must be exactly {expected}")
            rows = list(reader)
        ids = tuple(row["point_id"] for row in rows)
        if ids != point_set.point_ids:
            raise ValueError("external field point identity/order does not match the point set")
        try:
            field = np.asarray(
                [[row["bx_T"], row["by_T"], row["bz_T"]] for row in rows],
                dtype=np.float64,
            )
        except ValueError as exc:
            raise ValueError("external field CSV contains a non-numeric value") from exc
    elif suffix in {".h5", ".hdf5"}:
        with h5py.File(path, "r") as file:
            if file.attrs.get("field_unit") != "T":
                raise ValueError("external field HDF5 field_unit must be 'T'")
            if str(file.attrs.get("external_field_component_frame", "")) != component_frame:
                raise ValueError(
                    "external field HDF5 component frame does not match the configuration"
                )
            if "external_field_t" not in file or "point_ids" not in file:
                raise ValueError("external field HDF5 requires external_field_t and point_ids")
            if _h5_strings(file["point_ids"][...], name="point_ids") != point_set.point_ids:
                raise ValueError("external field point identity/order does not match the point set")
            field = np.asarray(file["external_field_t"][...], dtype=np.float64)
    elif suffix in {".vtk", ".vtu"}:
        mesh = meshio.read(path)
        if "external_field_T" not in mesh.point_data:
            raise ValueError("external field VTK requires point data external_field_T")
        if not np.array_equal(np.asarray(mesh.points, dtype=np.float64), point_set.points_m):
            raise ValueError("external field VTK coordinates do not exactly match the point set")
        field = np.asarray(mesh.point_data["external_field_T"], dtype=np.float64)
    else:
        raise ValueError(f"unsupported external field suffix: {suffix}")
    _validate_external_field(field, point_set)
    if field.ndim != 2:
        raise ValueError("static external field must have shape [point, 3]")
    return field


def _validate_external_field(field: FloatArray, point_set: PointSet) -> None:
    if field.ndim not in (2, 3) or field.shape[-2:] != (point_set.count, 3):
        raise ValueError("external field must have shape [point, 3] or [frame, point, 3]")
    if not np.all(np.isfinite(field)):
        raise ValueError("external field must contain only finite values")


def _pose_array(translation: FloatArray, quaternion: FloatArray) -> FloatArray:
    if translation.ndim not in (1, 2) or translation.shape[-1] != 3:
        raise ValueError("pose translation must have shape [3] or [frame, 3]")
    if quaternion.ndim != translation.ndim or quaternion.shape[:-1] != translation.shape[:-1]:
        raise ValueError("pose translation and quaternion dimensions differ")
    if quaternion.shape[-1] != 4:
        raise ValueError("pose quaternion must use xyzw shape [4] or [frame, 4]")
    if not np.all(np.isfinite(translation)) or not np.all(np.isfinite(quaternion)):
        raise ValueError("pose must contain only finite values")
    norms = np.linalg.norm(quaternion, axis=-1)
    if not np.allclose(norms, 1.0, rtol=0.0, atol=1e-12):
        raise ValueError("pose quaternion_xyzw must have unit norm within 1e-12")
    return np.concatenate((translation, quaternion), axis=-1, dtype=np.float64)


def pose_to_transform(pose: FloatArray) -> RigidTransform:
    """Convert declared translation plus unit xyzw quaternion to a rigid transform."""

    values = np.asarray(pose, dtype=np.float64)
    if values.shape != (7,):
        raise ValueError("runtime pose must have layout [tx,ty,tz,qx,qy,qz,qw]")
    translation = values[:3]
    x, y, z, w = values[3:]
    norm = float(np.linalg.norm(values[3:]))
    if not np.isclose(norm, 1.0, rtol=0.0, atol=1e-12):
        raise ValueError("runtime quaternion must have unit norm within 1e-12")
    rotation = np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ],
        dtype=np.float64,
    )
    return RigidTransform(rotation, translation)


def _resolve_basis(
    config: BuildConfig,
    point_set: PointSet,
    response_frame: str,
    sources: dict[str, dict[str, Any]],
) -> FloatArray | None:
    interface = config.environment
    if interface.observation_mode == "full_field":
        return None
    assert interface.basis_path is not None
    assert interface.basis_component_frame is not None
    if interface.basis_component_frame != response_frame:
        raise ValueError("basis component frame must equal the response coordinate frame")
    _record_source(sources, "observation_basis", interface.basis_path)
    if interface.basis_path.suffix.lower() not in {".h5", ".hdf5"}:
        raise ValueError("basis observation requires an HDF5 basis file")
    with h5py.File(interface.basis_path, "r") as file:
        if interface.basis_dataset not in file:
            raise ValueError(f"basis dataset {interface.basis_dataset!r} does not exist")
        basis_dataset = file[interface.basis_dataset]
        if str(basis_dataset.attrs.get("component_frame", "")) != interface.basis_component_frame:
            raise ValueError("basis HDF5 component frame does not match the configuration")
        basis = np.asarray(basis_dataset[...], dtype=np.float64)
        if "point_ids" not in file:
            raise ValueError("basis HDF5 must contain point_ids")
        if _h5_strings(file["point_ids"][...], name="point_ids") != point_set.point_ids:
            raise ValueError("basis point identity/order does not match the point set")
    if basis.ndim != 3 or basis.shape[0] == 0 or basis.shape[1:] != (point_set.count, 3):
        raise ValueError("basis must have shape [basis, point, 3]")
    if not np.all(np.isfinite(basis)):
        raise ValueError("basis must contain only finite values")
    return basis


def _require_channel_identity(config: BuildConfig, channel_ids: tuple[str, ...]) -> None:
    hardware_ids = tuple(channel.channel_id for channel in config.hardware.channels)
    if hardware_ids != channel_ids:
        raise ValueError(
            f"hardware channel order {hardware_ids} does not match physics {channel_ids}"
        )
    nominal = config.environment.reward.nominal_currents_a
    if nominal is not None and len(nominal) != len(channel_ids):
        raise ValueError("nominal_currents_a must contain one value per channel")


def _record_source(records: dict[str, dict[str, Any]], key: str, path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"source file does not exist: {path}")
    records[key] = {
        "name": path.name,
        "size_bytes": path.stat().st_size,
        "sha256": file_sha256(path),
    }


def _h5_strings(values: Any, *, name: str) -> tuple[str, ...]:
    array = np.asarray(values)
    if array.ndim != 1:
        raise ValueError(f"{name} must be one-dimensional")
    result = tuple(
        item.decode("utf-8") if isinstance(item, bytes) else str(item) for item in array.tolist()
    )
    if not result or any(not item for item in result):
        raise ValueError(f"{name} must contain non-empty identities")
    return result


def _export(resolved: ResolvedBuild) -> BuildReport:
    output = resolved.config.output_dir
    if output.exists():
        raise io_error(
            "output_exists",
            f"output directory already exists: {output}",
            "Choose a new empty output path; existing packages are never overwritten.",
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    try:
        package_config = _write_package_files(temporary, resolved)
        manifest, identity = _manifest(temporary, resolved, package_config)
        write_manifest(temporary / "manifest.json", manifest)
        temporary.replace(output)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    response = resolved.response.response_T_per_A
    return BuildReport(
        output_dir=output,
        package_identity=identity,
        point_count=resolved.point_set.count,
        channel_count=len(resolved.response.channel_ids),
        response_shape=response.shape,
        response_rank=int(np.linalg.matrix_rank(response.reshape(-1, response.shape[-1]))),
        response_memory_bytes=int(response.nbytes),
        physics_mode=resolved.physics_mode,
    )


def _write_package_files(directory: Path, resolved: ResolvedBuild) -> EnvironmentPackageConfig:
    config = resolved.config
    scenario = config.scenario
    write_physics_h5(
        directory / "physics.h5",
        point_set=resolved.point_set,
        response=resolved.response,
        basis=resolved.basis,
        basis_component_frame=config.environment.basis_component_frame,
        channels=resolved.channels,
        contributions=resolved.contributions,
        path_frame=resolved.path_frame,
        pose_source_frame=(
            config.forward.pose_source_frame
            if isinstance(config.forward, GeometryForward)
            else None
        ),
        pose_target_frame=(
            config.forward.pose_target_frame
            if isinstance(config.forward, GeometryForward)
            else None
        ),
    )
    write_scenario_h5(
        directory / "scenario.h5",
        external_field_t=resolved.external_field_t,
        external_field_component_frame=scenario.external_field_component_frame,
        pose=resolved.pose,
    )
    write_yaml(directory / "hardware.yaml", config.hardware.model_dump(mode="json"))
    package_config = EnvironmentPackageConfig(
        schema_name="magshield_env.environment_package",
        schema_version=1,
        name=config.name,
        physics=PackagedPhysics(
            mode=resolved.physics_mode,
            path_frame=resolved.path_frame,
            pose_source_frame=(
                config.forward.pose_source_frame
                if isinstance(config.forward, GeometryForward)
                else None
            ),
            pose_target_frame=(
                config.forward.pose_target_frame
                if isinstance(config.forward, GeometryForward)
                else None
            ),
            pose_cache_size=(
                config.forward.pose_cache_size if isinstance(config.forward, GeometryForward) else 0
            ),
        ),
        scenario=PackagedScenario(
            episode_length=scenario.episode_length,
            random_start=(
                scenario.random_start if isinstance(scenario, TrajectoryScenario) else False
            ),
            has_pose=resolved.pose is not None,
            external_field_component_frame=scenario.external_field_component_frame,
        ),
        observation_mode=config.environment.observation_mode,
        observation_basis_dataset=("/observation_basis" if resolved.basis is not None else None),
        observation_basis_component_frame=config.environment.basis_component_frame,
        include_pose=config.environment.include_pose,
        constraint_mode=config.environment.constraint_mode,
        reward=config.environment.reward,
    )
    write_environment_yaml(directory / "environment.yaml", package_config)
    (directory / "README.md").write_text(
        "# Portable magshield-env package\n\n"
        "This directory is self-contained. Validate it with `magshield-env validate` "
        "and load it with `magshield_env.make_env`. Do not edit individual files; "
        "their exact identities are bound by `manifest.json`.\n",
        encoding="utf-8",
        newline="\n",
    )
    return package_config


def _manifest(
    directory: Path,
    resolved: ResolvedBuild,
    package_config: EnvironmentPackageConfig,
) -> tuple[dict[str, Any], str]:
    response = resolved.response.response_T_per_A
    arrays = {
        "point_ids": canonical_json_sha256(list(resolved.point_set.point_ids)),
        "points_m": array_sha256(resolved.point_set.points_m),
        "weights": array_sha256(resolved.point_set.weights),
        "channel_ids": canonical_json_sha256(list(resolved.response.channel_ids)),
        "response_T_per_A": array_sha256(response),
        "external_field_t": array_sha256(resolved.external_field_t),
        "pose": None if resolved.pose is None else array_sha256(resolved.pose),
        "observation_basis": (None if resolved.basis is None else array_sha256(resolved.basis)),
    }
    environment_identity = package_config.model_dump(mode="json")
    environment_identity.pop("name")
    units = canonical_units()
    provenance = _build_provenance(resolved.config)
    identity_inputs = {
        "schema_name": "magshield_env.package_identity",
        "schema_version": 1,
        "environment": environment_identity,
        "hardware": resolved.config.hardware.model_dump(mode="json"),
        "arrays": arrays,
        "units": units,
        "build_provenance": provenance,
        "sources": {key: value["sha256"] for key, value in sorted(resolved.source_records.items())},
        "point_frame": resolved.point_set.coordinate_frame,
        "response_frame": resolved.response.coordinate_frame,
    }
    identity = canonical_json_sha256(identity_inputs)
    artifact_names = (
        "environment.yaml",
        "physics.h5",
        "hardware.yaml",
        "scenario.h5",
        "README.md",
    )
    artifacts = {
        name: {
            "size_bytes": (directory / name).stat().st_size,
            "sha256": file_sha256(directory / name),
        }
        for name in artifact_names
    }
    manifest = {
        "schema_name": "magshield_env.manifest",
        "schema_version": 1,
        "package_identity": identity,
        "physics_mode": resolved.physics_mode,
        "point_count": resolved.point_set.count,
        "channel_count": len(resolved.response.channel_ids),
        "response_shape": list(response.shape),
        "response_rank": int(np.linalg.matrix_rank(response.reshape(-1, response.shape[-1]))),
        "frames": {
            "points": resolved.point_set.coordinate_frame,
            "response": resolved.response.coordinate_frame,
            "paths": resolved.path_frame,
            "pose_source": (
                resolved.config.forward.pose_source_frame
                if isinstance(resolved.config.forward, GeometryForward)
                else None
            ),
            "pose_target": (
                resolved.config.forward.pose_target_frame
                if isinstance(resolved.config.forward, GeometryForward)
                else None
            ),
            "external_field_components": resolved.config.scenario.external_field_component_frame,
            "observation_basis_components": (
                resolved.config.environment.basis_component_frame
            ),
        },
        "units": units,
        "build_provenance": provenance,
        "arrays": arrays,
        "artifacts": artifacts,
        "sources": resolved.source_records,
        "identity_inputs": identity_inputs,
    }
    return manifest, identity


def _build_provenance(config: BuildConfig) -> dict[str, Any]:
    forward = config.forward
    provenance: dict[str, Any] = {
        "forward_kind": forward.kind,
        "source_unit_contract": "canonical_si",
    }
    if isinstance(forward, FiniteElementForward):
        provenance["coordinate_tolerance_m"] = forward.coordinate_tolerance_m
    return provenance
