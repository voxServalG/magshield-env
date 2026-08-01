"""Linear magnetic plant interfaces."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import numpy as np
from numpy.typing import ArrayLike, NDArray

FloatArray = NDArray[np.float64]


def _response_matrix(value: ArrayLike, *, expected_shape: tuple[int, int, int]) -> FloatArray:
    matrix = np.asarray(value, dtype=np.float64)
    if matrix.shape != expected_shape:
        raise ValueError(f"response matrix must have shape {expected_shape}, got {matrix.shape}")
    if not np.all(np.isfinite(matrix)):
        raise ValueError("response matrix must contain only finite values")
    return matrix.copy()


@runtime_checkable
class LinearPlant(Protocol):
    """Provide the full three-component response for a pose."""

    @property
    def point_count(self) -> int:
        """Return the sampling-point count bound to every response."""

    @property
    def channel_count(self) -> int:
        """Return the channel count bound to every response."""

    def response_matrix(self, pose: FloatArray | None) -> FloatArray:
        """Return a matrix shaped ``[point, component, channel]``."""


@dataclass(frozen=True, slots=True)
class FixedLinearPlant:
    """Serve one immutable response matrix for every environment frame.

    ``matrix_t_per_a`` establishes both point and channel identity. The
    environment requests it through :meth:`response_matrix`. ``pose`` may still
    be present in an observation or external-field trajectory, but it cannot
    alter this explicitly fixed plant.
    """

    matrix_t_per_a: FloatArray

    def __post_init__(self) -> None:
        matrix = np.asarray(self.matrix_t_per_a, dtype=np.float64)
        if matrix.ndim != 3 or matrix.shape[1] != 3:
            raise ValueError("matrix_t_per_a must have shape [point, 3, channel]")
        if matrix.shape[0] == 0 or matrix.shape[2] == 0:
            raise ValueError("matrix_t_per_a must contain points and channels")
        if not np.all(np.isfinite(matrix)):
            raise ValueError("matrix_t_per_a must contain only finite values")
        object.__setattr__(self, "matrix_t_per_a", matrix.copy())

    @property
    def point_count(self) -> int:
        return int(self.matrix_t_per_a.shape[0])

    @property
    def channel_count(self) -> int:
        return int(self.matrix_t_per_a.shape[2])

    def response_matrix(self, pose: FloatArray | None) -> FloatArray:
        return self.matrix_t_per_a


@dataclass(frozen=True, slots=True)
class DynamicLinearPlant:
    """Evaluate an exact response callback for each requested pose.

    ``callback`` consumes ``pose`` and returns the complete response matrix.
    ``point_count`` and ``channel_count`` declare the callback contract before
    a Gymnasium space is constructed. Every result is shape- and finiteness-
    checked, so a changing callback cannot corrupt observation identity.
    """

    callback: Callable[[FloatArray], ArrayLike]
    point_count: int
    channel_count: int

    def __post_init__(self) -> None:
        if not callable(self.callback):
            raise TypeError("callback must be callable")
        if self.point_count <= 0 or self.channel_count <= 0:
            raise ValueError("point_count and channel_count must be positive")

    def response_matrix(self, pose: FloatArray | None) -> FloatArray:
        if pose is None:
            raise ValueError("a dynamic plant requires a pose for every frame")
        pose_array = np.asarray(pose, dtype=np.float64)
        if pose_array.ndim != 1 or not np.all(np.isfinite(pose_array)):
            raise ValueError("pose must be a finite one-dimensional array")
        expected = (self.point_count, 3, self.channel_count)
        return _response_matrix(self.callback(pose_array.copy()), expected_shape=expected)
