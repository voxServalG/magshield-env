from __future__ import annotations

import csv
import json
from pathlib import Path

import h5py
import meshio
import numpy as np
import pytest
import yaml

from magshield_env.api import make_env, validate_environment
from magshield_env.builder import build_environment
from magshield_env.domain.errors import MagshieldEnvError
from magshield_env.package_io import load_physics_h5

POINT_IDS = ("0", "1")
POINTS = np.array([[-0.1, 0.0, 0.0], [0.1, 0.0, 0.0]], dtype=np.float64)
RESPONSE = np.array(
    [
        [[-1.0, 0.0], [0.0, -0.5], [0.0, 0.0]],
        [[-0.8, 0.0], [0.0, -0.4], [0.0, 0.0]],
    ],
    dtype=np.float64,
)


def _write_points(path: Path, *, frame: str = "lab") -> None:
    text = h5py.string_dtype(encoding="utf-8")
    with h5py.File(path, "w") as file:
        file.attrs["coordinate_frame"] = frame
        file.attrs["length_unit"] = "m"
        file.create_dataset("point_ids", data=np.asarray(POINT_IDS, dtype=text))
        file.create_dataset("points_m", data=POINTS)
        file.create_dataset("weights", data=np.ones(2, dtype=np.float64))


def _write_fixed_response(path: Path, response: np.ndarray = RESPONSE) -> None:
    text = h5py.string_dtype(encoding="utf-8")
    with h5py.File(path, "w") as file:
        file.attrs["coordinate_frame"] = "lab"
        file.attrs["field_unit"] = "T/A"
        file.create_dataset("point_ids", data=np.asarray(POINT_IDS, dtype=text))
        file.create_dataset("channel_ids", data=np.asarray(("c0", "c1"), dtype=text))
        file.create_dataset("response_T_per_A", data=response)


def _reward() -> dict[str, float]:
    return {
        "field_scale_t": 1.0,
        "field_threshold_t": 0.0,
        "field_weight": 1.0,
        "power_scale_w": 1.0,
        "power_weight": 0.1,
        "slew_scale_a": 1.0,
        "slew_weight": 0.1,
        "constraint_scale_a": 1.0,
        "constraint_weight": 1.0,
    }


def _hardware(channel_ids: tuple[str, ...] = ("c0", "c1")) -> dict[str, object]:
    return {
        "timestep_seconds": 0.1,
        "channels": [
            {
                "channel_id": channel_id,
                "current_lower_a": -2.0,
                "current_upper_a": 2.0,
                "slew_rate_upper_a_per_s": 10.0,
                "resistance_ohm": 1.0,
                "voltage_upper_v": 2.0,
            }
            for channel_id in channel_ids
        ],
    }


def _base_config(
    tmp_path: Path,
    *,
    output_name: str,
    forward: dict[str, object],
    channel_ids: tuple[str, ...] = ("c0", "c1"),
    pose: bool = False,
) -> dict[str, object]:
    point_path = tmp_path / "points.h5"
    if not point_path.exists():
        _write_points(point_path)
    scenario: dict[str, object] = {
        "kind": "static",
        "episode_length": 2,
        "external_field_component_frame": "lab",
    }
    if pose:
        scenario.update(
            {
                "translation_m": [0.0, 0.0, 0.0],
                "quaternion_xyzw": [0.0, 0.0, 0.0, 1.0],
            }
        )
    return {
        "schema_name": "magshield_env.build_config",
        "schema_version": 1,
        "name": output_name,
        "region": {"kind": "import", "path": point_path, "frame": "lab"},
        "forward": forward,
        "hardware": _hardware(channel_ids),
        "scenario": scenario,
        "environment": {
            "observation_mode": "full_field",
            "include_pose": pose,
            "constraint_mode": "project_and_report",
            "reward": _reward(),
        },
        "output_dir": tmp_path / output_name,
    }


def _fixed_config(tmp_path: Path, output_name: str) -> dict[str, object]:
    response_path = tmp_path / "response.h5"
    if not response_path.exists():
        _write_fixed_response(response_path)
    return _base_config(
        tmp_path,
        output_name=output_name,
        forward={
            "kind": "fixed_matrix",
            "path": response_path,
            "channel_ids": ["c0", "c1"],
        },
    )


def _write_field_csv(path: Path, values: np.ndarray) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(("point_id", "bx_T", "by_T", "bz_T"))
        for point_id, vector in zip(POINT_IDS, values, strict=True):
            writer.writerow((point_id, *vector.tolist()))


def _write_field_vtu(path: Path, values: np.ndarray) -> None:
    meshio.write(
        path,
        meshio.Mesh(
            POINTS,
            [("vertex", np.arange(2, dtype=np.int64).reshape(-1, 1))],
            point_data={
                "point_id": np.arange(2, dtype=np.int64),
                "field_T_per_A": values,
            },
        ),
    )


def test_build_refuses_existing_output_directory(tmp_path: Path) -> None:
    config = _fixed_config(tmp_path, "occupied")
    output = Path(str(config["output_dir"]))
    output.mkdir()

    with pytest.raises(MagshieldEnvError) as captured:
        build_environment(config)

    assert captured.value.record.type == "io"
    assert captured.value.record.subtype == "output_exists"


def test_artifact_tampering_is_rejected_before_loading(tmp_path: Path) -> None:
    package = tmp_path / "tamper"
    build_environment(_fixed_config(tmp_path, package.name))
    physics = package / "physics.h5"
    with physics.open("ab") as stream:
        stream.write(b"tampered")

    with pytest.raises(MagshieldEnvError) as captured:
        validate_environment(package)

    assert captured.value.record.subtype == "package_contract"
    assert "artifact size mismatch" in captured.value.record.message


def test_extra_package_member_is_rejected(tmp_path: Path) -> None:
    package = tmp_path / "extra-member"
    build_environment(_fixed_config(tmp_path, package.name))
    (package / "notes.txt").write_text("not part of the package contract\n", encoding="utf-8")

    with pytest.raises(MagshieldEnvError) as captured:
        validate_environment(package)

    assert captured.value.record.subtype == "package_contract"
    assert "package members must be exactly" in captured.value.record.message


def test_manifest_unit_tampering_is_rejected(tmp_path: Path) -> None:
    package = tmp_path / "unit-tamper"
    build_environment(_fixed_config(tmp_path, package.name))
    manifest_path = package / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["units"]["magnetic_field"] = "gauss"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")

    with pytest.raises(MagshieldEnvError) as captured:
        validate_environment(package)

    assert captured.value.record.subtype == "package_contract"
    assert "canonical SI" in captured.value.record.message


def test_package_identity_is_stable_for_identical_physics(tmp_path: Path) -> None:
    first_config = _fixed_config(tmp_path, "first")
    second_config = _fixed_config(tmp_path, "second")
    first_config["name"] = "identical-input"
    second_config["name"] = "identical-input"
    first = build_environment(first_config)
    second = build_environment(second_config)

    assert first.package_identity == second.package_identity
    first_manifest = json.loads((first.output_dir / "manifest.json").read_text())
    second_manifest = json.loads((second.output_dir / "manifest.json").read_text())
    assert first_manifest["identity_inputs"] == second_manifest["identity_inputs"]


def test_finite_element_csv_and_vtk_assemble_the_same_response(tmp_path: Path) -> None:
    channel_values = (RESPONSE[:, :, 0], RESPONSE[:, :, 1])
    csv_files: list[Path] = []
    vtk_files: list[Path] = []
    for index, values in enumerate(channel_values):
        csv_path = tmp_path / f"field-{index}.csv"
        vtk_path = tmp_path / f"field-{index}.vtu"
        _write_field_csv(csv_path, values)
        _write_field_vtu(vtk_path, values)
        csv_files.append(csv_path)
        vtk_files.append(vtk_path)

    csv_report = build_environment(
        _base_config(
            tmp_path,
            output_name="from-csv",
            forward={
                "kind": "finite_element",
                "channel_files": csv_files,
                "channel_ids": ["c0", "c1"],
            },
        )
    )
    vtk_report = build_environment(
        _base_config(
            tmp_path,
            output_name="from-vtk",
            forward={
                "kind": "finite_element",
                "channel_files": vtk_files,
                "channel_ids": ["c0", "c1"],
            },
        )
    )

    csv_physics = load_physics_h5(csv_report.output_dir / "physics.h5")
    vtk_physics = load_physics_h5(vtk_report.output_dir / "physics.h5")
    np.testing.assert_array_equal(
        csv_physics.response.response_T_per_A,
        vtk_physics.response.response_T_per_A,
    )


def test_static_geometry_package_reconstructs_dynamic_environment(tmp_path: Path) -> None:
    paths = tmp_path / "paths.csv"
    paths.write_text(
        "channel_id,path_id,vertex_index,x_m,y_m,z_m,closed\n"
        "coil,loop,0,-0.2,-0.2,0.2,true\n"
        "coil,loop,1,0.2,-0.2,0.2,true\n"
        "coil,loop,2,0.2,0.2,0.2,true\n"
        "coil,loop,3,-0.2,0.2,0.2,true\n",
        encoding="utf-8",
    )
    metadata = tmp_path / "channels.yaml"
    metadata.write_text(
        yaml.safe_dump(
            {
                "schema_name": "magshield_env.geometry_channels",
                "schema_version": 1,
                "channel_ids": ["coil"],
                "contributions": [{}],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    config = _base_config(
        tmp_path,
        output_name="dynamic",
        forward={
            "kind": "geometry",
            "paths": paths,
            "channels": metadata,
            "path_frame": "lab",
            "pose_source_frame": "lab",
            "pose_target_frame": "lab",
            "pose_cache_size": 2,
        },
        channel_ids=("coil",),
        pose=True,
    )

    report = build_environment(config)
    validation = validate_environment(report.output_dir)
    env = make_env(report.output_dir)
    observation, _ = env.reset(seed=7)
    next_observation, reward, terminated, truncated, info = env.step(
        np.array([0.1], dtype=np.float64)
    )

    assert validation.physics_mode == "dynamic_geometry"
    assert env.observation_space.contains(observation)
    assert env.observation_space.contains(next_observation)
    assert np.isfinite(reward)
    assert not terminated
    assert not truncated
    assert info["constraint"]["violated"] is False


def test_trajectory_and_basis_package_runs_a_complete_episode(tmp_path: Path) -> None:
    trajectory_path = tmp_path / "trajectory.h5"
    basis_path = tmp_path / "basis.h5"
    text = h5py.string_dtype(encoding="utf-8")
    with h5py.File(trajectory_path, "w") as file:
        file.attrs["field_unit"] = "T"
        file.attrs["external_field_component_frame"] = "lab"
        file.attrs["pose_length_unit"] = "m"
        file.attrs["pose_quaternion_order"] = "xyzw"
        file.create_dataset("point_ids", data=np.asarray(POINT_IDS, dtype=text))
        file.create_dataset(
            "external_field",
            data=np.array(
                [
                    [[1.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
                    [[0.5, 0.0, 0.0], [0.5, 0.0, 0.0]],
                    [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0]],
                ],
                dtype=np.float64,
            ),
        )
        pose = file.create_group("pose")
        pose.create_dataset("translation_m", data=np.zeros((3, 3), dtype=np.float64))
        pose.create_dataset(
            "quaternion_xyzw",
            data=np.tile(np.array([0.0, 0.0, 0.0, 1.0]), (3, 1)),
        )
    with h5py.File(basis_path, "w") as file:
        file.create_dataset("point_ids", data=np.asarray(POINT_IDS, dtype=text))
        basis = file.create_dataset(
            "basis",
            data=np.array([[[1.0, 0.0, 0.0], [1.0, 0.0, 0.0]]], dtype=np.float64),
        )
        basis.attrs["component_frame"] = "lab"

    config = _fixed_config(tmp_path, "trajectory-basis")
    config["scenario"] = {
        "kind": "trajectory",
        "path": trajectory_path,
        "external_field_component_frame": "lab",
        "episode_length": 2,
        "random_start": False,
    }
    config["environment"] = {
        "observation_mode": "basis",
        "basis_path": basis_path,
        "basis_component_frame": "lab",
        "include_pose": True,
        "constraint_mode": "project_and_report",
        "reward": _reward(),
    }

    report = build_environment(config)
    validation = validate_environment(report.output_dir)
    env = make_env(report.output_dir)
    observation, _ = env.reset(seed=2)
    first, _, terminated, truncated, _ = env.step(np.zeros(2, dtype=np.float64))
    second, _, terminated_final, truncated_final, _ = env.step(np.zeros(2, dtype=np.float64))

    assert validation.physics_mode == "fixed"
    assert observation.shape == (10,)
    assert env.observation_space.contains(observation)
    assert env.observation_space.contains(first)
    assert env.observation_space.contains(second)
    assert not terminated
    assert not truncated
    assert not terminated_final
    assert truncated_final


def test_trajectory_rejects_undeclared_pose_unit(tmp_path: Path) -> None:
    trajectory_path = tmp_path / "bad-trajectory.h5"
    text = h5py.string_dtype(encoding="utf-8")
    with h5py.File(trajectory_path, "w") as file:
        file.attrs["field_unit"] = "T"
        file.attrs["external_field_component_frame"] = "lab"
        file.attrs["pose_quaternion_order"] = "xyzw"
        file.create_dataset("point_ids", data=np.asarray(POINT_IDS, dtype=text))
        file.create_dataset("external_field", data=np.zeros((2, 2, 3), dtype=np.float64))
        pose = file.create_group("pose")
        pose.create_dataset("translation_m", data=np.zeros((2, 3), dtype=np.float64))
        pose.create_dataset(
            "quaternion_xyzw",
            data=np.tile(np.array([0.0, 0.0, 0.0, 1.0]), (2, 1)),
        )
    config = _fixed_config(tmp_path, "bad-trajectory")
    config["scenario"] = {
        "kind": "trajectory",
        "path": trajectory_path,
        "external_field_component_frame": "lab",
        "episode_length": 1,
    }

    with pytest.raises(MagshieldEnvError, match="pose_length_unit"):
        build_environment(config)
