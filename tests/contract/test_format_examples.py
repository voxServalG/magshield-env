from __future__ import annotations

from pathlib import Path

import numpy as np

from magshield_env.physics.imports import (
    assemble_response_matrix,
    load_channel_paths_csv,
    load_field_csv,
    load_points_csv,
)
from magshield_env.physics.vtp import load_channel_paths_vtp

ROOT = Path(__file__).resolve().parents[2]


def test_minimal_finite_element_csvs_form_one_deterministic_response() -> None:
    folder = ROOT / "examples" / "minimal-finite-element"
    points = load_points_csv(folder / "points.csv", coordinate_frame="body")
    fields = (
        load_field_csv(folder / "field_ch0.csv", channel_id="ch0", coordinate_frame="body"),
        load_field_csv(folder / "field_ch1.csv", channel_id="ch1", coordinate_frame="body"),
    )

    response = assemble_response_matrix(points, fields, channel_ids=("ch0", "ch1"))

    assert response.response_T_per_A.shape == (2, 3, 2)
    np.testing.assert_array_equal(response.response_T_per_A[:, 0, 0], 1.0e-6)
    np.testing.assert_array_equal(response.response_T_per_A[:, 1, 1], 1.0e-6)


def test_csv_and_vtp_geometry_examples_describe_the_same_closed_path() -> None:
    folder = ROOT / "examples" / "geometry"
    csv_channels = load_channel_paths_csv(folder / "paths.csv")
    vtp_channels = load_channel_paths_vtp(folder / "paths.vtp")

    assert tuple(channel.channel_id for channel in csv_channels) == ("ch0",)
    assert tuple(channel.channel_id for channel in vtp_channels) == ("ch0",)
    csv_path = csv_channels[0].polylines[0]
    vtp_path = vtp_channels[0].polylines[0]
    assert csv_path.closed is True
    assert vtp_path.closed is True
    np.testing.assert_array_equal(csv_path.vertices_m, vtp_path.vertices_m)
