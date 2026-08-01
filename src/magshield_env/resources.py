"""Load the versioned JSON Schemas shipped with the installed distribution."""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Any, Final, Literal

type JsonSchemaName = Literal[
    "build-config",
    "environment-package",
    "geometry-channels",
]
SCHEMA_NAMES: Final[frozenset[str]] = frozenset(
    {"build-config", "environment-package", "geometry-channels"}
)


def load_json_schema(name: JsonSchemaName | str) -> dict[str, Any]:
    """Return one immutable-contract Schema as a newly decoded JSON object.

    ``name`` selects exactly one of the three public contracts. The package
    resource is consumed directly from the installed distribution; an unknown
    name, missing wheel resource, or malformed non-object document fails
    immediately instead of consulting a source checkout or another location.
    """

    if name not in SCHEMA_NAMES:
        choices = ", ".join(sorted(SCHEMA_NAMES))
        raise ValueError(f"unknown JSON Schema {name!r}; expected one of: {choices}")
    resource = files("magshield_env").joinpath("schemas", f"{name}.schema.json")
    with resource.open("r", encoding="utf-8") as stream:
        payload: Any = json.load(stream)
    if not isinstance(payload, dict):
        raise ValueError(f"packaged JSON Schema {name!r} must be an object")
    return payload


__all__ = ["SCHEMA_NAMES", "JsonSchemaName", "load_json_schema"]
