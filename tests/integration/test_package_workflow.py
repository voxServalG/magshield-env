from __future__ import annotations

import shutil
from pathlib import Path

import h5py
import numpy as np

from magshield_env.api import make_env, validate_environment
from magshield_env.builder import build_environment


def test_fixed_package_survives_move_and_source_deletion(tmp_path: Path) -> None:
    source = tmp_path / "sources"
    source.mkdir()
    points = source / "points.h5"
    response = source / "response.h5"
    text = h5py.string_dtype(encoding="utf-8")
    point_ids = np.asarray(("left", "right"), dtype=text)
    channel_ids = np.asarray(("x", "y"), dtype=text)
    with h5py.File(points, "w") as file:
        file.attrs["coordinate_frame"] = "lab"
        file.attrs["length_unit"] = "m"
        file.create_dataset("point_ids", data=point_ids)
        file.create_dataset("points_m", data=[[-0.1, 0.0, 0.0], [0.1, 0.0, 0.0]])
        file.create_dataset("weights", data=[1.0, 1.0])
    matrix = np.zeros((2, 3, 2), dtype=np.float64)
    matrix[:, 0, 0] = -1.0
    matrix[:, 1, 1] = -1.0
    with h5py.File(response, "w") as file:
        file.attrs["coordinate_frame"] = "lab"
        file.attrs["field_unit"] = "T/A"
        file.create_dataset("point_ids", data=point_ids)
        file.create_dataset("channel_ids", data=channel_ids)
        file.create_dataset("response_T_per_A", data=matrix)
    package = tmp_path / "built"
    config = {
        "schema_name": "magshield_env.build_config",
        "schema_version": 1,
        "name": "portable-fixed",
        "region": {"kind": "import", "path": points, "frame": "lab"},
        "forward": {
            "kind": "fixed_matrix",
            "path": response,
            "channel_ids": ["x", "y"],
        },
        "hardware": {
            "timestep_seconds": 0.1,
            "channels": [
                {
                    "channel_id": channel,
                    "current_lower_a": -2.0,
                    "current_upper_a": 2.0,
                    "slew_rate_upper_a_per_s": 10.0,
                    "resistance_ohm": 1.0,
                    "voltage_upper_v": 2.0,
                }
                for channel in ("x", "y")
            ],
        },
        "scenario": {
            "kind": "static",
            "episode_length": 2,
            "external_field_component_frame": "lab",
        },
        "environment": {
            "observation_mode": "full_field",
            "include_pose": False,
            "constraint_mode": "project_and_report",
            "reward": {
                "field_scale_t": 1.0,
                "field_threshold_t": 0.0,
                "field_weight": 1.0,
                "power_scale_w": 1.0,
                "power_weight": 0.1,
                "slew_scale_a": 1.0,
                "slew_weight": 0.1,
                "constraint_scale_a": 1.0,
                "constraint_weight": 1.0,
            },
        },
        "output_dir": package,
    }

    report = build_environment(config)
    moved = tmp_path / "elsewhere" / "portable-package"
    moved.parent.mkdir()
    shutil.move(report.output_dir, moved)
    shutil.rmtree(source)

    validation = validate_environment(moved)
    env = make_env(moved)
    observation, _ = env.reset(seed=13)
    first, reward, terminated, truncated, info = env.step(np.array([0.5, -0.25], dtype=np.float64))
    second, _, _, truncated_after_second, _ = env.step(np.zeros(2, dtype=np.float64))

    assert validation.package_identity == report.package_identity
    assert env.observation_space.contains(observation)
    assert env.observation_space.contains(first)
    assert env.observation_space.contains(second)
    assert np.isfinite(reward)
    assert not terminated
    assert not truncated
    assert truncated_after_second
    assert info["constraint"]["violated"] is False
