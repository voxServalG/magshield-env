from __future__ import annotations

import numpy as np
import pytest

from magshield_env.physics import (
    MU_0_T_M_PER_A,
    ChannelPath,
    DynamicPathResponse,
    FieldContribution,
    PhysicsValidationError,
    PointSet,
    Polyline,
    RigidTransform,
    channel_field,
    finite_segment_field,
    polyline_field,
    response_at_pose,
)


def test_finite_segment_matches_closed_form_and_preserves_full_vector_direction() -> None:
    length = 2.0
    radius = 0.5
    field = finite_segment_field(
        np.array([[radius, 0.0, 0.0]]),
        np.array([0.0, 0.0, -length / 2.0]),
        np.array([0.0, 0.0, length / 2.0]),
    )
    expected_y = (
        MU_0_T_M_PER_A
        / (4.0 * np.pi * radius)
        * length
        / np.sqrt(radius * radius + length * length / 4.0)
    )
    np.testing.assert_allclose(field, [[0.0, expected_y, 0.0]], rtol=1e-14, atol=0.0)


def test_finite_segment_matches_independent_midpoint_quadrature() -> None:
    start = np.array([-0.35, 0.2, -0.6])
    end = np.array([0.45, -0.1, 0.8])
    point = np.array([[0.7, 0.4, -0.2]])
    analytic = finite_segment_field(point, start, end)

    subdivisions = 200_000
    dl = (end - start) / subdivisions
    centers = start + (np.arange(subdivisions, dtype=np.float64)[:, None] + 0.5) * dl
    displacement = point[0] - centers
    integrand = np.cross(np.broadcast_to(dl, displacement.shape), displacement)
    numerical = (
        MU_0_T_M_PER_A
        / (4.0 * np.pi)
        * np.sum(integrand / np.linalg.norm(displacement, axis=1)[:, None] ** 3, axis=0)
    )

    np.testing.assert_allclose(analytic[0], numerical, rtol=2e-11, atol=1e-18)


def test_polygonal_circle_converges_to_analytic_center_field() -> None:
    radius = 0.4
    angle = np.linspace(0.0, 2.0 * np.pi, 1440, endpoint=False)
    vertices = np.column_stack(
        (radius * np.cos(angle), radius * np.sin(angle), np.zeros_like(angle))
    )
    loop = Polyline("circle", vertices, True)

    field = polyline_field(np.array([[0.0, 0.0, 0.0]]), loop)
    expected = MU_0_T_M_PER_A / (2.0 * radius)

    np.testing.assert_allclose(field, [[0.0, 0.0, expected]], rtol=2e-6, atol=1e-18)


def test_zero_current_is_zero_and_sampling_on_conductor_fails() -> None:
    field = finite_segment_field(
        [[1.0, 2.0, 0.0]], [0.0, 0.0, -1.0], [0.0, 0.0, 1.0], current_A=0.0
    )
    np.testing.assert_array_equal(field, np.zeros((1, 3)))

    with pytest.raises(PhysicsValidationError, match="singular"):
        finite_segment_field([[0.0, 0.0, 0.0]], [0.0, 0.0, -1.0], [0.0, 0.0, 1.0])


def test_channel_superposition_and_transformed_gain_are_explicit() -> None:
    wire = Polyline("wire", np.array([[0.0, 0.0, -1.0], [0.0, 0.0, 1.0]]), False)
    channel = ChannelPath("c0", (wire,))
    points = np.array([[1.0, 0.0, 0.0]])
    identity = FieldContribution(RigidTransform.identity(), 1.0)
    translated = FieldContribution(RigidTransform(np.eye(3), np.array([1.0, 1.0, 0.0])), -0.5)

    combined = channel_field(points, channel, contributions=(identity, translated))
    separately = channel_field(points, channel, contributions=(identity,)) + channel_field(
        points, channel, contributions=(translated,)
    )
    np.testing.assert_allclose(combined, separately, rtol=0.0, atol=0.0)


def test_dynamic_pose_recomputes_at_lab_points_and_cache_binds_pose_identity() -> None:
    body_points = PointSet(("p0",), np.array([[1.0, 0.0, 0.0]]), np.array([1.0]), "body")
    wire = Polyline("wire", np.array([[0.0, 0.0, -1.0], [0.0, 0.0, 1.0]]), False)
    channels = (ChannelPath("c0", (wire,)),)
    pose = RigidTransform(np.eye(3), np.array([1.0, 0.0, 0.0]))
    model = DynamicPathResponse(channels)

    first = model.response(body_points, pose)
    repeated = model.response(body_points, pose)
    direct = response_at_pose(body_points, channels, pose)
    assert first is repeated
    assert model.cache_size == 1
    np.testing.assert_allclose(first.response_T_per_A, direct.response_T_per_A)

    moved_pose = RigidTransform(np.eye(3), np.array([2.0, 0.0, 0.0]))
    moved = model.response(body_points, moved_pose)
    assert model.cache_size == 2
    assert not np.array_equal(first.response_T_per_A, moved.response_T_per_A)


def test_ninety_degree_pose_matches_direct_lab_frame_recomputation() -> None:
    body_points = PointSet(("p0",), np.array([[1.0, 0.0, 0.0]]), np.array([1.0]), "body")
    wire = Polyline("wire", np.array([[0.0, 0.0, -1.0], [0.0, 0.0, 1.0]]), False)
    channels = (ChannelPath("c0", (wire,)),)
    rotation = np.array(
        [
            [0.0, -1.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0],
        ]
    )
    pose = RigidTransform(rotation, np.zeros(3))

    transformed = response_at_pose(body_points, channels, pose, lab_frame="lab")
    direct = finite_segment_field(
        np.array([[0.0, 1.0, 0.0]]),
        np.array([0.0, 0.0, -1.0]),
        np.array([0.0, 0.0, 1.0]),
    )

    assert transformed.coordinate_frame == "lab"
    np.testing.assert_allclose(transformed.response_T_per_A[:, :, 0], direct, atol=0.0)


def test_dynamic_pose_cache_can_be_disabled_or_bounded() -> None:
    body_points = PointSet(("p0",), np.array([[1.0, 0.0, 0.0]]), np.array([1.0]), "body")
    wire = Polyline("wire", np.array([[0.0, 0.0, -1.0], [0.0, 0.0, 1.0]]), False)
    channels = (ChannelPath("c0", (wire,)),)
    first_pose = RigidTransform(np.eye(3), np.array([0.0, 0.0, 0.0]))
    second_pose = RigidTransform(np.eye(3), np.array([0.5, 0.0, 0.0]))

    disabled = DynamicPathResponse(channels, max_cache_entries=0)
    first = disabled.response(body_points, first_pose)
    repeated = disabled.response(body_points, first_pose)
    assert first is not repeated
    assert disabled.cache_size == 0

    bounded = DynamicPathResponse(channels, max_cache_entries=1)
    bounded.response(body_points, first_pose)
    bounded.response(body_points, second_pose)
    assert bounded.cache_size == 1
    recomputed = bounded.response(body_points, first_pose)
    assert bounded.cache_size == 1
    np.testing.assert_allclose(recomputed.response_T_per_A, first.response_T_per_A)


@pytest.mark.parametrize("value", [-1, 1.5, True])
def test_dynamic_pose_cache_rejects_invalid_bounds(value: object) -> None:
    wire = Polyline("wire", np.array([[0.0, 0.0, -1.0], [0.0, 0.0, 1.0]]), False)
    with pytest.raises(PhysicsValidationError, match="max_cache_entries"):
        DynamicPathResponse((ChannelPath("c0", (wire,)),), max_cache_entries=value)  # type: ignore[arg-type]
