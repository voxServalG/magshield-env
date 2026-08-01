from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml
from pydantic import BaseModel

from magshield_env.builder import build_environment
from magshield_env.domain.config import BuildConfig, load_build_config
from magshield_env.domain.geometry import GeometryChannelsConfig
from magshield_env.domain.package import EnvironmentPackageConfig
from magshield_env.package_io import load_physics_h5

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("model", "schema_name"),
    [
        (BuildConfig, "build-config.schema.json"),
        (GeometryChannelsConfig, "geometry-channels.schema.json"),
        (EnvironmentPackageConfig, "environment-package.schema.json"),
    ],
)
def test_frozen_json_schema_matches_authoritative_model(
    model: type[BaseModel], schema_name: str
) -> None:
    frozen = json.loads((ROOT / "schemas" / schema_name).read_text(encoding="utf-8"))

    assert frozen == model.model_json_schema()


def test_minimal_build_example_satisfies_strict_schema_and_resolves_paths() -> None:
    source = ROOT / "examples" / "minimal-finite-element" / "build.yaml"
    raw: Any = yaml.safe_load(source.read_text(encoding="utf-8"))

    direct = BuildConfig.model_validate(raw)
    resolved = load_build_config(source)

    assert direct.schema_name == "magshield_env.build_config"
    assert resolved.region.kind == "import"
    assert resolved.region.path.is_file()
    assert resolved.forward.kind == "finite_element"
    assert all(path.is_file() for path in resolved.forward.channel_files)


def test_geometry_metadata_example_satisfies_strict_schema() -> None:
    source = ROOT / "examples" / "geometry" / "channels.yaml"
    raw: Any = yaml.safe_load(source.read_text(encoding="utf-8"))

    config = GeometryChannelsConfig.model_validate(raw)

    assert config.channel_ids == ("ch0",)
    assert config.contributions[0].gain == 1.0


def test_minimal_example_has_frozen_cross_platform_package_identity(tmp_path: Path) -> None:
    source = ROOT / "examples" / "minimal-finite-element" / "build.yaml"
    config = load_build_config(source).model_copy(update={"output_dir": tmp_path / "environment"})

    report = build_environment(config)

    assert report.package_identity == (
        "d3ac2cfb818390ac1b64b12c994f741676f2c92f804008449534a0f499329141"
    )
    physics = load_physics_h5(report.output_dir / "physics.h5")
    expected = np.array(
        [
            [[1.0e-6, 0.0], [0.0, 1.0e-6], [0.0, 0.0]],
            [[1.0e-6, 0.0], [0.0, 1.0e-6], [0.0, 0.0]],
        ],
        dtype=np.float64,
    )
    np.testing.assert_array_equal(physics.response.response_T_per_A, expected)
