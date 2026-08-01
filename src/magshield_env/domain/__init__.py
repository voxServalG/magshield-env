"""Validated public domain contracts for magnetic-control environments."""

from .config import (
    BuildConfig,
    EnvironmentInterfaceConfig,
    HardwareChannelConfig,
    HardwareConfig,
    RewardConfig,
    load_build_config,
)
from .errors import MagshieldEnvError
from .geometry import (
    ContributionConfig,
    GeometryChannelsConfig,
    load_geometry_channels_config,
)
from .package import (
    BuildReport,
    EnvironmentPackageConfig,
    ValidationReport,
    load_environment_package_config,
)

__all__ = [
    "BuildConfig",
    "BuildReport",
    "ContributionConfig",
    "EnvironmentInterfaceConfig",
    "EnvironmentPackageConfig",
    "GeometryChannelsConfig",
    "HardwareChannelConfig",
    "HardwareConfig",
    "MagshieldEnvError",
    "RewardConfig",
    "ValidationReport",
    "load_build_config",
    "load_environment_package_config",
    "load_geometry_channels_config",
]
