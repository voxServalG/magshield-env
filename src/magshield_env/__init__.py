"""Build and load validated Gymnasium magnetic-control environments."""

from .api import inspect_environment, make_env, validate_environment
from .builder import build_environment, inspect_build
from .cli import main
from .domain import BuildConfig, BuildReport, ValidationReport, load_build_config
from .resources import load_json_schema

__all__ = [
    "BuildConfig",
    "BuildReport",
    "ValidationReport",
    "build_environment",
    "inspect_build",
    "inspect_environment",
    "load_build_config",
    "load_json_schema",
    "main",
    "make_env",
    "validate_environment",
]
