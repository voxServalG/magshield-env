"""Deterministic SI sampling-region generators."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from numpy.typing import ArrayLike

from .models import FloatArray, PhysicsValidationError, PointSet, _float64_array


def _positive_scalar(value: float, *, name: str) -> float:
    result = float(value)
    if not np.isfinite(result) or result <= 0.0:
        raise PhysicsValidationError(f"{name} must be finite and strictly positive")
    return result


def _vector3(value: ArrayLike, *, name: str) -> FloatArray:
    result = _float64_array(value, name=name, ndim=1)
    if result.shape != (3,):
        raise PhysicsValidationError(f"{name} must have shape (3,); got {result.shape}")
    return result


def _spacing3(value: float | Sequence[float]) -> FloatArray:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        spacing = _vector3(value, name="spacing_m")
    else:
        spacing = np.full(3, _positive_scalar(float(value), name="spacing_m"))
    if np.any(spacing <= 0.0):
        raise PhysicsValidationError("spacing_m entries must be strictly positive")
    return spacing


def _interval_axis(half_extent_m: float, spacing_m: float, *, name: str) -> FloatArray:
    ratio = 2.0 * half_extent_m / spacing_m
    interval_count = round(ratio)
    if interval_count < 1 or not np.isclose(ratio, interval_count, rtol=0.0, atol=1e-12):
        raise PhysicsValidationError(
            f"{name} extent must be an integer multiple of its spacing; got ratio {ratio!r}"
        )
    return np.linspace(-half_extent_m, half_extent_m, interval_count + 1, dtype=np.float64)


def _point_ids(count: int) -> tuple[str, ...]:
    width = max(6, len(str(count - 1)))
    return tuple(f"p{index:0{width}d}" for index in range(count))


def _point_set(
    points_m: FloatArray,
    *,
    weight: float | FloatArray,
    coordinate_frame: str,
) -> PointSet:
    weights = (
        np.full(len(points_m), float(weight), dtype=np.float64)
        if np.asarray(weight).ndim == 0
        else np.asarray(weight, dtype=np.float64)
    )
    return PointSet(
        point_ids=_point_ids(len(points_m)),
        points_m=points_m,
        weights=weights,
        coordinate_frame=coordinate_frame,
    )


def generate_sphere(
    radius_m: float,
    spacing_m: float,
    *,
    center_m: ArrayLike = (0.0, 0.0, 0.0),
    coordinate_frame: str = "lab",
) -> PointSet:
    """Generate a lexicographic Cartesian grid whose centers lie in a solid sphere."""

    radius = _positive_scalar(radius_m, name="radius_m")
    spacing = _positive_scalar(spacing_m, name="spacing_m")
    center = _vector3(center_m, name="center_m")
    axis = _interval_axis(radius, spacing, name="sphere diameter")
    x, y, z = np.meshgrid(axis, axis, axis, indexing="ij")
    offsets = np.column_stack((x.ravel(), y.ravel(), z.ravel()))
    inside = np.einsum("ij,ij->i", offsets, offsets) <= radius * radius
    points = np.ascontiguousarray(offsets[inside] + center)
    return _point_set(points, weight=spacing**3, coordinate_frame=coordinate_frame)


def generate_sphere_surface(
    radius_m: float,
    point_count: int,
    *,
    center_m: ArrayLike = (0.0, 0.0, 0.0),
    coordinate_frame: str = "lab",
) -> PointSet:
    """Generate an equal-area deterministic Fibonacci sampling of a sphere surface."""

    radius = _positive_scalar(radius_m, name="radius_m")
    if isinstance(point_count, bool) or not isinstance(point_count, int) or point_count < 1:
        raise PhysicsValidationError("point_count must be a strictly positive integer")
    center = _vector3(center_m, name="center_m")
    indices = np.arange(point_count, dtype=np.float64)
    z = 1.0 - 2.0 * (indices + 0.5) / point_count
    radial = np.sqrt(1.0 - z * z)
    golden_angle = np.pi * (3.0 - np.sqrt(5.0))
    azimuth = golden_angle * indices
    unit_points = np.column_stack((radial * np.cos(azimuth), radial * np.sin(azimuth), z))
    points = np.ascontiguousarray(radius * unit_points + center)
    return _point_set(
        points,
        weight=4.0 * np.pi * radius * radius / point_count,
        coordinate_frame=coordinate_frame,
    )


def generate_box(
    size_m: ArrayLike,
    spacing_m: float | Sequence[float],
    *,
    center_m: ArrayLike = (0.0, 0.0, 0.0),
    coordinate_frame: str = "lab",
) -> PointSet:
    """Generate an axis-aligned lexicographic Cartesian box including its boundary."""

    size = _vector3(size_m, name="size_m")
    if np.any(size <= 0.0):
        raise PhysicsValidationError("size_m entries must be strictly positive")
    spacing = _spacing3(spacing_m)
    center = _vector3(center_m, name="center_m")
    axes = tuple(
        _interval_axis(float(size[index] / 2.0), float(spacing[index]), name=f"box axis {index}")
        for index in range(3)
    )
    x, y, z = np.meshgrid(*axes, indexing="ij")
    points = np.ascontiguousarray(np.column_stack((x.ravel(), y.ravel(), z.ravel())) + center)
    return _point_set(points, weight=float(np.prod(spacing)), coordinate_frame=coordinate_frame)


def generate_cylinder(
    radius_m: float,
    height_m: float,
    spacing_m: float | Sequence[float],
    *,
    center_m: ArrayLike = (0.0, 0.0, 0.0),
    axis: str = "z",
    coordinate_frame: str = "lab",
) -> PointSet:
    """Generate a Cartesian grid masked to a solid cylinder along an explicit axis."""

    radius = _positive_scalar(radius_m, name="radius_m")
    height = _positive_scalar(height_m, name="height_m")
    spacing = _spacing3(spacing_m)
    center = _vector3(center_m, name="center_m")
    if axis not in {"x", "y", "z"}:
        raise PhysicsValidationError("axis must be exactly one of 'x', 'y', or 'z'")
    axial_index = {"x": 0, "y": 1, "z": 2}[axis]
    radial_indices = tuple(index for index in range(3) if index != axial_index)
    half_extents = np.full(3, radius, dtype=np.float64)
    half_extents[axial_index] = height / 2.0
    axes = tuple(
        _interval_axis(
            float(half_extents[index]), float(spacing[index]), name=f"cylinder axis {index}"
        )
        for index in range(3)
    )
    grids = np.meshgrid(*axes, indexing="ij")
    offsets = np.column_stack(tuple(grid.ravel() for grid in grids))
    radial_squared = np.sum(offsets[:, radial_indices] ** 2, axis=1)
    inside = radial_squared <= radius * radius
    points = np.ascontiguousarray(offsets[inside] + center)
    return _point_set(points, weight=float(np.prod(spacing)), coordinate_frame=coordinate_frame)


sphere_points = generate_sphere
sphere_surface_points = generate_sphere_surface
box_points = generate_box
cylinder_points = generate_cylinder
