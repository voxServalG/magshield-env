"""Explicit behavior configuration for a magnetic-control environment."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
from numpy.typing import NDArray

from .hardware import _channel_array

FloatArray = NDArray[np.float64]
ConstraintMode = Literal["project_and_report", "terminate"]


def _positive(value: float, *, name: str) -> float:
    number = float(value)
    if not np.isfinite(number) or number <= 0.0:
        raise ValueError(f"{name} must be finite and strictly positive")
    return number


def _nonnegative(value: float, *, name: str) -> float:
    number = float(value)
    if not np.isfinite(number) or number < 0.0:
        raise ValueError(f"{name} must be finite and non-negative")
    return number


@dataclass(frozen=True, slots=True)
class ActionConfig:
    """Map normalized current deltas and define violation behavior.

    ``delta_scale_a`` converts the public ``[-1, 1]`` action into amperes.
    ``constraint_mode`` then decides whether an action outside the derived
    hardware interval is explicitly projected and reported, or terminates the
    episode without changing current. Both members are consumed on every step.
    """

    delta_scale_a: FloatArray
    constraint_mode: ConstraintMode

    def __post_init__(self) -> None:
        scale = _channel_array(self.delta_scale_a, name="delta_scale_a")
        if np.any(scale <= 0.0):
            raise ValueError("delta_scale_a must be strictly positive")
        if self.constraint_mode not in ("project_and_report", "terminate"):
            raise ValueError("constraint_mode must be 'project_and_report' or 'terminate'")
        object.__setattr__(self, "delta_scale_a", scale)


@dataclass(frozen=True, slots=True)
class RewardConfig:
    """Declare every reward term's physical scale and dimensionless weight.

    The environment normalizes field error above ``field_threshold_t``, Joule
    power, current change, constraint violation, and optionally deviation from
    ``nominal_currents_a`` using their paired scales. The paired weights form
    the negative weighted sum returned by ``step``. Optional nominal members
    must be supplied together, preventing an implicit reward convention.
    """

    field_threshold_t: float
    field_scale_t: float
    field_weight: float
    power_scale_w: float
    power_weight: float
    slew_scale_a: float
    slew_weight: float
    constraint_scale_a: float
    constraint_weight: float
    nominal_currents_a: FloatArray | None = None
    nominal_scale_a: float | None = None
    nominal_weight: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "field_threshold_t",
            _nonnegative(self.field_threshold_t, name="field_threshold_t"),
        )
        for name in (
            "field_scale_t",
            "power_scale_w",
            "slew_scale_a",
            "constraint_scale_a",
        ):
            object.__setattr__(self, name, _positive(getattr(self, name), name=name))
        for name in (
            "field_weight",
            "power_weight",
            "slew_weight",
            "constraint_weight",
        ):
            object.__setattr__(self, name, _nonnegative(getattr(self, name), name=name))

        nominal_currents = self.nominal_currents_a
        nominal_scale = self.nominal_scale_a
        nominal_weight = self.nominal_weight
        nominal_values = (nominal_currents, nominal_scale, nominal_weight)
        if all(value is None for value in nominal_values):
            return
        if any(value is None for value in nominal_values):
            raise ValueError(
                "nominal_currents_a, nominal_scale_a, and nominal_weight must be supplied together"
            )
        assert nominal_currents is not None
        assert nominal_scale is not None
        assert nominal_weight is not None
        nominal = _channel_array(nominal_currents, name="nominal_currents_a")
        object.__setattr__(self, "nominal_currents_a", nominal)
        object.__setattr__(
            self,
            "nominal_scale_a",
            _positive(nominal_scale, name="nominal_scale_a"),
        )
        object.__setattr__(
            self,
            "nominal_weight",
            _nonnegative(nominal_weight, name="nominal_weight"),
        )
