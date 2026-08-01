"""Analytic finite-segment Biot-Savart evaluation and dynamic responses."""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from collections.abc import Sequence
from typing import Any

import numpy as np
from numpy.typing import ArrayLike

from .models import (
    IDENTITY_CONTRIBUTION,
    MU_0_T_M_PER_A,
    ChannelPath,
    FieldContribution,
    FloatArray,
    PhysicsValidationError,
    PointSet,
    Polyline,
    ResponseMatrix,
    RigidTransform,
    _float64_array,
)


def _point_matrix(value: ArrayLike, *, name: str) -> FloatArray:
    points = _float64_array(value, name=name, ndim=2)
    if points.shape[1:] != (3,):
        raise PhysicsValidationError(f"{name} must have shape (N, 3); got {points.shape}")
    return points


def _point3(value: ArrayLike, *, name: str) -> FloatArray:
    point = _float64_array(value, name=name, ndim=1)
    if point.shape != (3,):
        raise PhysicsValidationError(f"{name} must have shape (3,); got {point.shape}")
    return point


def finite_segment_field(
    points_m: ArrayLike,
    start_m: ArrayLike,
    end_m: ArrayLike,
    *,
    current_A: float = 1.0,
    singularity_tolerance_m: float = 0.0,
) -> FloatArray:
    """Return the exact full-vector field of one oriented finite segment."""

    points = _point_matrix(points_m, name="points_m")
    start = _point3(start_m, name="start_m")
    end = _point3(end_m, name="end_m")
    current = float(current_A)
    tolerance = float(singularity_tolerance_m)
    if not np.isfinite(current):
        raise PhysicsValidationError("current_A must be finite")
    if not np.isfinite(tolerance) or tolerance < 0.0:
        raise PhysicsValidationError("singularity_tolerance_m must be finite and non-negative")
    segment = end - start
    length = float(np.linalg.norm(segment))
    if length == 0.0:
        raise PhysicsValidationError("Biot-Savart segment must have nonzero length")
    tangent = segment / length
    from_start = points - start
    axial = from_start @ tangent
    perpendicular = from_start - axial[:, None] * tangent
    rho_squared = np.einsum("ij,ij->i", perpendicular, perpendicular)
    singular = (axial >= 0.0) & (axial <= length) & (rho_squared <= tolerance * tolerance)
    if np.any(singular):
        raise PhysicsValidationError(
            "field is singular at points on conductor segment: "
            f"indices {np.flatnonzero(singular).tolist()}"
        )

    result = np.zeros_like(points)
    off_axis = rho_squared > 0.0
    if np.any(off_axis):
        rho2 = rho_squared[off_axis]
        s = axial[off_axis]
        first_cosine = s / np.sqrt(rho2 + s * s)
        from_end = s - length
        second_cosine = from_end / np.sqrt(rho2 + from_end * from_end)
        angular_factor = first_cosine - second_cosine
        direction_over_rho = np.cross(tangent, perpendicular[off_axis]) / rho2[:, None]
        result[off_axis] = (
            MU_0_T_M_PER_A * current / (4.0 * np.pi) * angular_factor[:, None] * direction_over_rho
        )
    return np.ascontiguousarray(result)


def polyline_field(
    points_m: ArrayLike,
    polyline: Polyline,
    *,
    current_A: float = 1.0,
    contribution: FieldContribution = IDENTITY_CONTRIBUTION,
    singularity_tolerance_m: float = 0.0,
) -> FloatArray:
    """Evaluate all explicitly declared segments of one transformed polyline."""

    points = _point_matrix(points_m, name="points_m")
    vertices = contribution.transform.apply_points(polyline.vertices_m)
    starts = vertices if polyline.closed else vertices[:-1]
    ends = np.roll(vertices, -1, axis=0) if polyline.closed else vertices[1:]
    field = np.zeros_like(points)
    for start, end in zip(starts, ends, strict=True):
        field += finite_segment_field(
            points,
            start,
            end,
            current_A=current_A,
            singularity_tolerance_m=singularity_tolerance_m,
        )
    return np.ascontiguousarray(field * contribution.gain)


def channel_field(
    points_m: ArrayLike,
    channel: ChannelPath,
    *,
    current_A: float = 1.0,
    contributions: Sequence[FieldContribution] = (IDENTITY_CONTRIBUTION,),
    singularity_tolerance_m: float = 0.0,
) -> FloatArray:
    """Sum only the paths and transformed contributions explicitly listed."""

    points = _point_matrix(points_m, name="points_m")
    declared = tuple(contributions)
    if not declared:
        raise PhysicsValidationError("contributions must contain at least one explicit term")
    field = np.zeros_like(points)
    for contribution in declared:
        if not isinstance(contribution, FieldContribution):
            raise PhysicsValidationError("every contribution must be a FieldContribution")
        for polyline in channel.polylines:
            field += polyline_field(
                points,
                polyline,
                current_A=current_A,
                contribution=contribution,
                singularity_tolerance_m=singularity_tolerance_m,
            )
    return np.ascontiguousarray(field)


def response_from_paths(
    point_set: PointSet,
    channels: Sequence[ChannelPath],
    *,
    contributions: Sequence[FieldContribution] = (IDENTITY_CONTRIBUTION,),
    singularity_tolerance_m: float = 0.0,
) -> ResponseMatrix:
    """Build ``A[N, 3, M]`` by evaluating every channel at exactly one ampere."""

    declared_channels = tuple(channels)
    if not declared_channels:
        raise PhysicsValidationError("channels must not be empty")
    channel_ids = tuple(channel.channel_id for channel in declared_channels)
    if len(set(channel_ids)) != len(channel_ids):
        raise PhysicsValidationError("channel_id values must be unique")
    columns = tuple(
        channel_field(
            point_set.points_m,
            channel,
            contributions=contributions,
            singularity_tolerance_m=singularity_tolerance_m,
        )
        for channel in declared_channels
    )
    return ResponseMatrix(
        point_set.point_ids,
        channel_ids,
        np.stack(columns, axis=2),
        point_set.coordinate_frame,
    )


def transform_point_set(
    point_set: PointSet, pose_source_to_target: RigidTransform, *, target_frame: str
) -> PointSet:
    """Apply one pose while preserving point identities, order, and weights."""

    if pose_source_to_target.allow_improper:
        raise PhysicsValidationError("a body pose must be a proper transform, not a reflection")
    return PointSet(
        point_set.point_ids,
        pose_source_to_target.apply_points(point_set.points_m),
        point_set.weights,
        target_frame,
    )


def response_at_pose(
    body_points: PointSet,
    channels_lab: Sequence[ChannelPath],
    pose_body_to_lab: RigidTransform,
    *,
    lab_frame: str = "lab",
    contributions: Sequence[FieldContribution] = (IDENTITY_CONTRIBUTION,),
    singularity_tolerance_m: float = 0.0,
) -> ResponseMatrix:
    """Move body samples into lab and recompute against fixed lab conductors."""

    lab_points = transform_point_set(body_points, pose_body_to_lab, target_frame=lab_frame)
    return response_from_paths(
        lab_points,
        channels_lab,
        contributions=contributions,
        singularity_tolerance_m=singularity_tolerance_m,
    )


def _hash_array(digest: Any, value: np.ndarray) -> None:
    canonical = np.ascontiguousarray(value, dtype="<f8")
    digest.update(np.asarray(canonical.shape, dtype="<i8").tobytes())
    digest.update(canonical.tobytes())


def _hash_text(digest: Any, value: str) -> None:
    encoded = value.encode("utf-8")
    digest.update(len(encoded).to_bytes(8, byteorder="little", signed=False))
    digest.update(encoded)


class DynamicPathResponse:
    """Evaluate fixed conductors against explicitly posed body sample points.

    ``channels_lab`` and ``contributions`` define fixed geometry; ``lab_frame``
    names its output; ``singularity_tolerance_m`` controls rejection;
    ``max_cache_entries`` bounds the least-recently-used cache; and ``_cache``
    binds every physical input into each cached response identity.
    """

    def __init__(
        self,
        channels_lab: Sequence[ChannelPath],
        *,
        lab_frame: str = "lab",
        contributions: Sequence[FieldContribution] = (IDENTITY_CONTRIBUTION,),
        singularity_tolerance_m: float = 0.0,
        max_cache_entries: int = 64,
    ) -> None:
        self.channels_lab = tuple(channels_lab)
        if not self.channels_lab:
            raise PhysicsValidationError("channels_lab must not be empty")
        channel_ids = tuple(channel.channel_id for channel in self.channels_lab)
        if len(set(channel_ids)) != len(channel_ids):
            raise PhysicsValidationError("channel_id values must be unique")
        self.contributions = tuple(contributions)
        if not self.contributions:
            raise PhysicsValidationError("contributions must not be empty")
        self.lab_frame = lab_frame
        if not self.lab_frame:
            raise PhysicsValidationError("lab_frame must be a non-empty string")
        self.singularity_tolerance_m = float(singularity_tolerance_m)
        if not np.isfinite(self.singularity_tolerance_m) or self.singularity_tolerance_m < 0.0:
            raise PhysicsValidationError("singularity_tolerance_m must be finite and non-negative")
        if isinstance(max_cache_entries, bool) or not isinstance(max_cache_entries, int):
            raise PhysicsValidationError("max_cache_entries must be a non-negative integer")
        if max_cache_entries < 0:
            raise PhysicsValidationError("max_cache_entries must be a non-negative integer")
        self.max_cache_entries = max_cache_entries
        self._cache: OrderedDict[str, ResponseMatrix] = OrderedDict()

    def _identity(self, body_points: PointSet, pose: RigidTransform) -> str:
        digest = hashlib.sha256()
        _hash_text(digest, body_points.coordinate_frame)
        for point_id in body_points.point_ids:
            _hash_text(digest, point_id)
        _hash_array(digest, body_points.points_m)
        _hash_array(digest, body_points.weights)
        _hash_array(digest, pose.rotation)
        _hash_array(digest, pose.translation_m)
        _hash_text(digest, self.lab_frame)
        digest.update(np.asarray([self.singularity_tolerance_m], dtype="<f8").tobytes())
        for channel in self.channels_lab:
            _hash_text(digest, channel.channel_id)
            for polyline in channel.polylines:
                _hash_text(digest, polyline.path_id)
                digest.update(bytes((int(polyline.closed),)))
                _hash_array(digest, polyline.vertices_m)
        for contribution in self.contributions:
            _hash_array(digest, contribution.transform.rotation)
            _hash_array(digest, contribution.transform.translation_m)
            digest.update(np.asarray([contribution.gain], dtype="<f8").tobytes())
        return digest.hexdigest()

    def response(self, body_points: PointSet, pose_body_to_lab: RigidTransform) -> ResponseMatrix:
        identity = self._identity(body_points, pose_body_to_lab)
        cached = self._cache.get(identity)
        if cached is not None:
            self._cache.move_to_end(identity)
            return cached
        response = response_at_pose(
            body_points,
            self.channels_lab,
            pose_body_to_lab,
            lab_frame=self.lab_frame,
            contributions=self.contributions,
            singularity_tolerance_m=self.singularity_tolerance_m,
        )
        if self.max_cache_entries > 0:
            self._cache[identity] = response
            self._cache.move_to_end(identity)
            while len(self._cache) > self.max_cache_entries:
                self._cache.popitem(last=False)
        return response

    @property
    def cache_size(self) -> int:
        return len(self._cache)


class FixedResponse:
    """response is the calibrated tensor; response_for verifies point identity
    and coordinate frame before returning it to a consumer.
    """

    def __init__(self, response: ResponseMatrix) -> None:
        self.response = response

    def response_for(self, point_set: PointSet) -> ResponseMatrix:
        if point_set.point_ids != self.response.point_ids:
            raise PhysicsValidationError("point identity/order does not match fixed response")
        if point_set.coordinate_frame != self.response.coordinate_frame:
            raise PhysicsValidationError("point frame does not match fixed response")
        return self.response


finite_wire_segment_field = finite_segment_field
PathResponseModel = DynamicPathResponse
FixedResponseModel = FixedResponse
