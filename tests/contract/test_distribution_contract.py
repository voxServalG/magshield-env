from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_NAMES = {
    "build-config.schema.json",
    "environment-package.schema.json",
    "geometry-channels.schema.json",
}


def _pyproject() -> dict[str, Any]:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_wheel_maps_the_single_schema_source_into_package_resources() -> None:
    wheel = _pyproject()["tool"]["hatch"]["build"]["targets"]["wheel"]

    assert wheel["packages"] == ["src/magshield_env"]
    assert wheel["force-include"] == {"schemas": "magshield_env/schemas"}
    assert {path.name for path in (ROOT / "schemas").glob("*.schema.json")} == SCHEMA_NAMES
    assert (ROOT / "src" / "magshield_env" / "py.typed").is_file()


def test_sdist_explicitly_carries_reproducibility_assets() -> None:
    include = set(_pyproject()["tool"]["hatch"]["build"]["targets"]["sdist"]["include"])

    assert {
        "/.github",
        "/docs",
        "/examples",
        "/schemas",
        "/skills",
        "/src",
        "/tests",
        "/README.md",
        "/pyproject.toml",
        "/uv.lock",
    } <= include


def test_declared_python_versions_match_ci_matrix() -> None:
    project = _pyproject()["project"]
    workflow = (ROOT / ".github" / "workflows" / "verify.yml").read_text(encoding="utf-8")

    assert project["requires-python"] == ">=3.12,<3.15"
    assert 'python-version: ["3.12", "3.13", "3.14"]' in workflow
