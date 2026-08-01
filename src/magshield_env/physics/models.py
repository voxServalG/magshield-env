"""Strict, SI-valued data contracts consumed by the physics layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import ArrayLike, NDArray

FloatArray = NDArray[np.float64]
MU_0_T_M_PER_A: Final[float] = 4.0e-7 * np.pi


class PhysicsValidationError(ValueError):
    """Raised when physical input violates an identity or shape contract."""


def _float64_array(value: ArrayLike, *, name: str, ndim: int) -> FloatArray:
    array = np.asarray(value, dtype=np.float64)
    if array.ndim != ndim:
        raise PhysicsValidationError(f"{name} must have {ndim} dimensions; got {array.ndim}")
    if not np.all(np.isfinite(array)):
        raise PhysicsValidationError(f"{name} must contain only finite float64 values")
    return np.ascontiguousarray(array)


def _identifiers(values: tuple[str, ...] | list[str], *, name: str) -> tuple[str, ...]:
    identifiers = tuple(values)
    if not identifiers:
        raise PhysicsValidationError(f"{name} must not be empty")
    if any(not isinstance(value, str) or not value for value in identifiers):
        raise PhysicsValidationError(f"{name} must contain non-empty strings")
    if len(set(identifiers)) != len(identifiers):
        raise PhysicsValidationError(f"{name} must be unique")
    return identifiers


@dataclass(frozen=True, slots=True)
class PointSet:
    """A consumer uses point_ids to bind ordering, points_m as SI coordinates,
    weights for deterministic spatial aggregation, and coordinate_frame to decide
    which explicit transform is required before field evaluation.
    """

    point_ids: tuple[str, ...]
    points_m: FloatArray
    weights: FloatArray
    coordinate_frame: str

    def __post_init__(self) -> None:
        point_ids = _identifiers(self.point_ids, name="point_ids")
        points_m = _float64_array(self.points_m, name="points_m", ndim=2)
        weights = _float64_array(self.weights, name="weights", ndim=1)
        if points_m.shape != (len(point_ids), 3):
            raise PhysicsValidationError(
                f"points_m must have shape ({len(point_ids)}, 3); got {points_m.shape}"
            )
        if weights.shape != (len(point_ids),):
            raise PhysicsValidationError(
                f"weights must have shape ({len(point_ids)},); got {weights.shape}"
            )
        if np.any(weights <= 0.0):
            raise PhysicsValidationError("weights must be strictly positive")
        if not isinstance(self.coordinate_frame, str) or not self.coordinate_frame:
            raise PhysicsValidationError("coordinate_frame must be a non-empty string")
        object.__setattr__(self, "point_ids", point_ids)
        object.__setattr__(self, "points_m", points_m)
        object.__setattr__(self, "weights", weights)

    @property
    def count(self) -> int:
        return len(self.point_ids)


@dataclass(frozen=True, slots=True)
class FieldSample:
    """The assembler consumes channel_id as the response column identity,
    point_ids as its exact row binding, field_T as full vector tesla per ampere,
    and coordinate_frame as the frame compatibility guard.
    """

    channel_id: str
    point_ids: tuple[str, ...]
    field_T_per_A: FloatArray
    coordinate_frame: str

    def __post_init__(self) -> None:
        if not isinstance(self.channel_id, str) or not self.channel_id:
            raise PhysicsValidationError("channel_id must be a non-empty string")
        point_ids = _identifiers(self.point_ids, name="point_ids")
        field = _float64_array(self.field_T_per_A, name="field_T_per_A", ndim=2)
        if field.shape != (len(point_ids), 3):
            raise PhysicsValidationError(
                f"field_T_per_A must have shape ({len(point_ids)}, 3); got {field.shape}"
            )
        if not isinstance(self.coordinate_frame, str) or not self.coordinate_frame:
            raise PhysicsValidationError("coordinate_frame must be a non-empty string")
        object.__setattr__(self, "point_ids", point_ids)
        object.__setattr__(self, "field_T_per_A", field)


@dataclass(frozen=True, slots=True)
class ResponseMatrix:
    """An environment binds point_ids and channel_ids to the first and third
    axes of response_T_per_A, then requires coordinate_frame to match its field.
    """

    point_ids: tuple[str, ...]
    channel_ids: tuple[str, ...]
    response_T_per_A: FloatArray
    coordinate_frame: str

    def __post_init__(self) -> None:
        point_ids = _identifiers(self.point_ids, name="point_ids")
        channel_ids = _identifiers(self.channel_ids, name="channel_ids")
        response = _float64_array(self.response_T_per_A, name="response_T_per_A", ndim=3)
        required = (len(point_ids), 3, len(channel_ids))
        if response.shape != required:
            raise PhysicsValidationError(
                f"response_T_per_A must have shape {required}; got {response.shape}"
            )
        if not isinstance(self.coordinate_frame, str) or not self.coordinate_frame:
            raise PhysicsValidationError("coordinate_frame must be a non-empty string")
        object.__setattr__(self, "point_ids", point_ids)
        object.__setattr__(self, "channel_ids", channel_ids)
        object.__setattr__(self, "response_T_per_A", response)


@dataclass(frozen=True, slots=True)
class Polyline:
    """The field evaluator consumes path_id for diagnostics, vertices_m in
    declared order to orient current, and closed to decide whether to add the
    final segment back to the first vertex.
    """

    path_id: str
    vertices_m: FloatArray
    closed: bool

    def __post_init__(self) -> None:
        if not isinstance(self.path_id, str) or not self.path_id:
            raise PhysicsValidationError("path_id must be a non-empty string")
        vertices = _float64_array(self.vertices_m, name="vertices_m", ndim=2)
        if vertices.shape[1:] != (3,):
            raise PhysicsValidationError(f"vertices_m must have shape (P, 3); got {vertices.shape}")
        minimum = 3 if self.closed else 2
        if len(vertices) < minimum:
            raise PhysicsValidationError(
                f"{'closed' if self.closed else 'open'} path needs at least {minimum} vertices"
            )
        segment_starts = vertices
        segment_ends = np.roll(vertices, -1, axis=0) if self.closed else vertices[1:]
        if not self.closed:
            segment_starts = vertices[:-1]
        if np.any(np.linalg.norm(segment_ends - segment_starts, axis=1) == 0.0):
            raise PhysicsValidationError("path contains a zero-length segment")
        object.__setattr__(self, "vertices_m", vertices)


@dataclass(frozen=True, slots=True)
class ChannelPath:
    """The response model uses channel_id for matrix column identity and sums
    every explicitly listed polyline as conductors carrying the same channel current.
    """

    channel_id: str
    polylines: tuple[Polyline, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.channel_id, str) or not self.channel_id:
            raise PhysicsValidationError("channel_id must be a non-empty string")
        polylines = tuple(self.polylines)
        if not polylines:
            raise PhysicsValidationError("polylines must not be empty")
        path_ids = tuple(path.path_id for path in polylines)
        if len(set(path_ids)) != len(path_ids):
            raise PhysicsValidationError("path_id values must be unique within a channel")
        object.__setattr__(self, "polylines", polylines)


@dataclass(frozen=True, slots=True)
class RigidTransform:
    """A geometry consumer multiplies coordinates by rotation and then adds
    translation_m; allow_improper declares whether a reflection is intentional.
    """

    rotation: FloatArray
    translation_m: FloatArray
    allow_improper: bool = False

    def __post_init__(self) -> None:
        rotation = _float64_array(self.rotation, name="rotation", ndim=2)
        translation = _float64_array(self.translation_m, name="translation_m", ndim=1)
        if rotation.shape != (3, 3):
            raise PhysicsValidationError(f"rotation must have shape (3, 3); got {rotation.shape}")
        if translation.shape != (3,):
            raise PhysicsValidationError(
                f"translation_m must have shape (3,); got {translation.shape}"
            )
        if not np.allclose(rotation.T @ rotation, np.eye(3), rtol=0.0, atol=1e-12):
            raise PhysicsValidationError(
                "rotation must be orthogonal within absolute tolerance 1e-12"
            )
        determinant = float(np.linalg.det(rotation))
        expected = (-1.0, 1.0) if self.allow_improper else (1.0,)
        if not any(abs(determinant - value) <= 1e-12 for value in expected):
            raise PhysicsValidationError(
                "rotation determinant must be +1 unless allow_improper explicitly permits -1"
            )
        object.__setattr__(self, "rotation", rotation)
        object.__setattr__(self, "translation_m", translation)

    @classmethod
    def identity(cls) -> RigidTransform:
        return cls(np.eye(3, dtype=np.float64), np.zeros(3, dtype=np.float64))

    def apply_points(self, points_m: ArrayLike) -> FloatArray:
        points = _float64_array(points_m, name="points_m", ndim=2)
        if points.shape[1:] != (3,):
            raise PhysicsValidationError(f"points_m must have shape (N, 3); got {points.shape}")
        return np.ascontiguousarray(points @ self.rotation.T + self.translation_m)


@dataclass(frozen=True, slots=True)
class FieldContribution:
    """The path evaluator transforms every source conductor with transform,
    evaluates its unit-current field, and multiplies that field by explicit gain.
    """

    transform: RigidTransform
    gain: float

    def __post_init__(self) -> None:
        gain = float(self.gain)
        if not np.isfinite(gain):
            raise PhysicsValidationError("gain must be finite")
        object.__setattr__(self, "gain", gain)


IDENTITY_CONTRIBUTION: Final[FieldContribution] = FieldContribution(
    transform=RigidTransform.identity(), gain=1.0
)
