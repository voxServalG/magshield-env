"""Install the built wheel in isolation and exercise its public runtime contract."""

from __future__ import annotations

import csv
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def _run(command: list[str], *, cwd: Path, env: dict[str, str]) -> None:
    subprocess.run(command, cwd=cwd, env=env, check=True)


def _venv_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _venv_cli(venv: Path) -> Path:
    return venv / ("Scripts/magshield-env.exe" if os.name == "nt" else "bin/magshield-env")


def _orchestrate() -> None:
    repository = Path(__file__).resolve().parents[2]
    wheels = tuple((repository / "dist").glob("magshield_env-*.whl"))
    if len(wheels) != 1:
        raise RuntimeError(f"wheel smoke requires exactly one wheel; found {len(wheels)}")
    with tempfile.TemporaryDirectory(prefix="magshield-env-wheel-smoke-") as temporary:
        root = Path(temporary)
        venv = root / "venv"
        empty_cwd = root / "empty-cwd"
        empty_cwd.mkdir()
        child_env = os.environ.copy()
        child_env.pop("VIRTUAL_ENV", None)
        _run(
            ["uv", "venv", "--python", sys.executable, str(venv)],
            cwd=empty_cwd,
            env=child_env,
        )
        python = _venv_python(venv)
        _run(
            ["uv", "pip", "install", "--python", str(python), str(wheels[0])],
            cwd=empty_cwd,
            env=child_env,
        )
        _run([str(_venv_cli(venv)), "--help"], cwd=empty_cwd, env=child_env)
        _run(
            [str(python), str(Path(__file__).resolve()), "--installed-smoke"],
            cwd=empty_cwd,
            env=child_env,
        )


def _installed_smoke() -> None:
    import numpy as np

    from magshield_env import (
        build_environment,
        load_json_schema,
        make_env,
        validate_environment,
    )

    root = Path.cwd()
    points = root / "points.csv"
    field = root / "field.csv"
    with points.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(("point_id", "x_m", "y_m", "z_m", "weight"))
        writer.writerow(("p0", 0.0, 0.0, 0.0, 1.0))
    with field.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(("point_id", "bx_T", "by_T", "bz_T"))
        writer.writerow(("p0", -1.0, 0.0, 0.0))
    package = root / "environment"
    report = build_environment(
        {
            "schema_name": "magshield_env.build_config",
            "schema_version": 1,
            "name": "wheel-smoke",
            "region": {"kind": "import", "path": points, "frame": "lab"},
            "forward": {
                "kind": "finite_element",
                "channel_files": [field],
                "channel_ids": ["coil"],
            },
            "hardware": {
                "timestep_seconds": 0.1,
                "channels": [
                    {
                        "channel_id": "coil",
                        "current_lower_a": -1.0,
                        "current_upper_a": 1.0,
                        "slew_rate_upper_a_per_s": 1.0,
                        "resistance_ohm": 1.0,
                        "voltage_upper_v": 1.0,
                    }
                ],
            },
            "scenario": {
                "kind": "static",
                "episode_length": 1,
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
                    "power_weight": 0.0,
                    "slew_scale_a": 1.0,
                    "slew_weight": 0.0,
                    "constraint_scale_a": 1.0,
                    "constraint_weight": 1.0,
                },
            },
            "output_dir": package,
        }
    )
    validation = validate_environment(package)
    environment = make_env(package)
    observation, _ = environment.reset(seed=1)
    next_observation, reward, terminated, truncated, _ = environment.step(
        np.zeros(1, dtype=np.float64)
    )
    if validation.package_identity != report.package_identity:
        raise RuntimeError("installed wheel changed the exported package identity")
    if not environment.observation_space.contains(observation):
        raise RuntimeError("installed wheel reset returned an invalid observation")
    if not environment.observation_space.contains(next_observation):
        raise RuntimeError("installed wheel step returned an invalid observation")
    if not np.isfinite(reward) or terminated or not truncated:
        raise RuntimeError("installed wheel episode did not satisfy the Gymnasium contract")
    if load_json_schema("build-config").get("title") != "BuildConfig":
        raise RuntimeError("installed wheel JSON Schema resource is unavailable or invalid")


if __name__ == "__main__":
    if sys.argv[1:] == ["--installed-smoke"]:
        _installed_smoke()
    elif sys.argv[1:]:
        raise SystemExit(f"unexpected arguments: {sys.argv[1:]}")
    else:
        _orchestrate()
