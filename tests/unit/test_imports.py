from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pytest

from magshield_env.physics import (
    FieldSample,
    PhysicsValidationError,
    PointSet,
    assemble_response_matrix,
    load_channel_paths_csv,
    load_points_csv,
    load_points_hdf5,
    load_points_vtk,
    write_points_csv,
    write_points_hdf5,
    write_points_vtk,
)


@pytest.fixture
def point_set() -> PointSet:
    return PointSet(
        ("sensor-left", "sensor-right"),
        np.array([[-0.1, 0.0, 0.0], [0.1, 0.0, 0.0]], dtype=np.float64),
        np.array([0.25, 0.75], dtype=np.float64),
        "body",
    )


def test_point_set_round_trips_csv_hdf5_and_vtk(tmp_path: Path, point_set: PointSet) -> None:
    csv_path = tmp_path / "points.csv"
    h5_path = tmp_path / "points.h5"
    vtk_path = tmp_path / "points.vtu"
    write_points_csv(point_set, csv_path)
    write_points_hdf5(point_set, h5_path)
    write_points_vtk(point_set, vtk_path)

    loaded = (
        load_points_csv(csv_path, coordinate_frame="body"),
        load_points_hdf5(h5_path),
        load_points_vtk(vtk_path, coordinate_frame="body"),
    )
    for actual in loaded:
        assert actual.point_ids == point_set.point_ids
        assert actual.coordinate_frame == point_set.coordinate_frame
        np.testing.assert_array_equal(actual.points_m, point_set.points_m)
        np.testing.assert_array_equal(actual.weights, point_set.weights)


def test_csv_requires_exact_columns(tmp_path: Path) -> None:
    path = tmp_path / "bad.csv"
    path.write_text("point_id,x_m,y_m,z_m\np0,0,0,0\n", encoding="utf-8")

    with pytest.raises(PhysicsValidationError, match="columns must be exactly"):
        load_points_csv(path, coordinate_frame="lab")


def test_finite_element_fields_assemble_only_in_exact_point_and_channel_order(
    point_set: PointSet,
) -> None:
    first = FieldSample("c0", point_set.point_ids, np.ones((2, 3), dtype=np.float64), "body")
    second = FieldSample("c1", point_set.point_ids, 2.0 * np.ones((2, 3), dtype=np.float64), "body")
    response = assemble_response_matrix(point_set, (first, second), channel_ids=("c0", "c1"))
    assert response.response_T_per_A.shape == (2, 3, 2)
    np.testing.assert_array_equal(response.response_T_per_A[:, :, 0], 1.0)
    np.testing.assert_array_equal(response.response_T_per_A[:, :, 1], 2.0)

    reordered = FieldSample(
        "c1", tuple(reversed(point_set.point_ids)), second.field_T_per_A, "body"
    )
    with pytest.raises(PhysicsValidationError, match="point identity/order"):
        assemble_response_matrix(point_set, (first, reordered))
    with pytest.raises(PhysicsValidationError, match="channel order"):
        assemble_response_matrix(point_set, (first, second), channel_ids=("c1", "c0"))


def test_csv_paths_preserve_explicit_channel_path_and_vertex_order(tmp_path: Path) -> None:
    path = tmp_path / "paths.csv"
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("channel_id", "path_id", "vertex_index", "x_m", "y_m", "z_m", "closed"))
        writer.writerows(
            (
                ("c0", "loop", 0, 0, 0, 0, "true"),
                ("c0", "loop", 1, 1, 0, 0, "true"),
                ("c0", "loop", 2, 0, 1, 0, "true"),
                ("c1", "lead", 0, 0, 0, 0, "false"),
                ("c1", "lead", 1, 0, 0, 1, "false"),
            )
        )

    channels = load_channel_paths_csv(path)
    assert tuple(channel.channel_id for channel in channels) == ("c0", "c1")
    assert channels[0].polylines[0].closed is True
    np.testing.assert_array_equal(channels[0].polylines[0].vertices_m[1], (1.0, 0.0, 0.0))
