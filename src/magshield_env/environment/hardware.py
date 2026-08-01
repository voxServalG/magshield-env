"""Hardware constraints for magnetic-control environments."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray

FloatArray = NDArray[np.float64]


def _channel_array(value: ArrayLike, *, name: str) -> FloatArray:
    array = np.asarray(value, dtype=np.float64)
    if array.ndim != 1 or array.size == 0:
        raise ValueError(f"{name} must be a non-empty one-dimensional array")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must contain only finite values")
    return array.copy()


@dataclass(frozen=True, slots=True)
class HardwareLimits:
    """Declare the limits that jointly determine each channel's legal current.

    The current bounds provide the absolute envelope. ``slew_rate_a_per_s`` and
    the environment timestep shrink that envelope around the previously applied
    currents. Finally, Ohm's law converts ``voltage_max_v`` and
    ``resistance_ohm`` into another absolute current envelope. Consumers call
    :meth:`legal_current_interval` before applying every action; no member is
    merely descriptive metadata.
    """

    current_min_a: FloatArray
    current_max_a: FloatArray
    slew_rate_a_per_s: FloatArray
    resistance_ohm: FloatArray
    voltage_max_v: FloatArray

    def __post_init__(self) -> None:
        names = (
            "current_min_a",
            "current_max_a",
            "slew_rate_a_per_s",
            "resistance_ohm",
            "voltage_max_v",
        )
        arrays = {name: _channel_array(getattr(self, name), name=name) for name in names}
        sizes = {array.size for array in arrays.values()}
        if len(sizes) != 1:
            raise ValueError("all hardware limits must have the same channel count")
        if np.any(arrays["current_min_a"] >= arrays["current_max_a"]):
            raise ValueError("current_min_a must be smaller than current_max_a")
        if np.any(arrays["slew_rate_a_per_s"] <= 0.0):
            raise ValueError("slew_rate_a_per_s must be strictly positive")
        if np.any(arrays["resistance_ohm"] <= 0.0):
            raise ValueError("resistance_ohm must be strictly positive")
        if np.any(arrays["voltage_max_v"] <= 0.0):
            raise ValueError("voltage_max_v must be strictly positive")
        for name, array in arrays.items():
            object.__setattr__(self, name, array)

        voltage_current = self.voltage_max_v / self.resistance_ohm
        lower = np.maximum(self.current_min_a, -voltage_current)
        upper = np.minimum(self.current_max_a, voltage_current)
        if np.any(lower > upper):
            raise ValueError("current and resistive-voltage limits have no overlap")

    @property
    def channel_count(self) -> int:
        """Return the number of independently constrained channels."""

        return int(self.current_min_a.size)

    def legal_current_interval(
        self, previous_currents_a: ArrayLike, timestep_s: float
    ) -> tuple[FloatArray, FloatArray]:
        """Derive inclusive current bounds for the next action."""

        previous = _channel_array(previous_currents_a, name="previous_currents_a")
        if previous.size != self.channel_count:
            raise ValueError("previous_currents_a has the wrong channel count")
        if not np.isfinite(timestep_s) or timestep_s <= 0.0:
            raise ValueError("timestep_s must be finite and strictly positive")

        voltage_current = self.voltage_max_v / self.resistance_ohm
        slew_delta = self.slew_rate_a_per_s * timestep_s
        lower = np.maximum.reduce((self.current_min_a, -voltage_current, previous - slew_delta))
        upper = np.minimum.reduce((self.current_max_a, voltage_current, previous + slew_delta))
        if np.any(lower > upper):
            raise ValueError("previous currents produce an empty next-step hardware interval")
        return lower, upper
