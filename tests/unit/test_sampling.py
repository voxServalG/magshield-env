from __future__ import annotations

import numpy as np
import pytest

from magshield_env.physics import (
    PhysicsValidationError,
    generate_box,
    generate_cylinder,
    generate_sphere,
    generate_sphere_surface,
)


def test_solid_sphere_has_deterministic_lexicographic_points_and_voxel_weights() -> None:
    points = generate_sphere(1.0, 1.0, coordinate_frame="body")

    assert points.point_ids == tuple(f"p{index:06d}" for index in range(7))
    np.testing.assert_array_equal(
        points.points_m,
        np.array(
            [
                [-1.0, 0.0, 0.0],
                [0.0, -1.0, 0.0],
                [0.0, 0.0, -1.0],
                [0.0, 0.0, 0.0],
                [0.0, 0.0, 1.0],
                [0.0, 1.0, 0.0],
                [1.0, 0.0, 0.0],
            ]
        ),
    )
    np.testing.assert_array_equal(points.weights, np.ones(7))
    assert points.points_m.dtype == np.float64
    assert points.coordinate_frame == "body"


def test_surface_box_and_cylinder_generators_bind_counts_and_weights() -> None:
    surface = generate_sphere_surface(2.0, 32)
    np.testing.assert_allclose(np.linalg.norm(surface.points_m, axis=1), 2.0)
    assert np.sum(surface.weights) == pytest.approx(16.0 * np.pi)

    box = generate_box((2.0, 2.0, 2.0), 1.0)
    assert box.count == 27
    np.testing.assert_array_equal(box.points_m[0], (-1.0, -1.0, -1.0))
    np.testing.assert_array_equal(box.points_m[-1], (1.0, 1.0, 1.0))

    cylinder = generate_cylinder(1.0, 2.0, 1.0, axis="z")
    assert cylinder.count == 15
    assert np.all(np.sum(cylinder.points_m[:, :2] ** 2, axis=1) <= 1.0)


def test_generators_reject_ambiguous_nonintegral_spacing() -> None:
    with pytest.raises(PhysicsValidationError, match="integer multiple"):
        generate_box((1.0, 1.0, 1.0), 0.3)

    with pytest.raises(PhysicsValidationError, match="point_count"):
        generate_sphere_surface(1.0, 0)
