from __future__ import annotations

from pathlib import Path

import pytest

from magshield_env.physics.models import PhysicsValidationError
from magshield_env.physics.vtp import load_channel_paths_vtp


def _vtp(points_format: str = "ascii", closed: str = "1") -> str:
    return f"""<?xml version="1.0"?>
<VTKFile type="PolyData" version="0.1" byte_order="LittleEndian">
  <PolyData>
    <Piece NumberOfPoints="4" NumberOfLines="1">
      <Points>
        <DataArray type="Float64" NumberOfComponents="3" format="{points_format}">
          0 0 0  1 0 0  0 1 0  0 0 0
        </DataArray>
      </Points>
      <Lines>
        <DataArray type="Int64" Name="connectivity" format="ascii">0 1 2 0</DataArray>
        <DataArray type="Int64" Name="offsets" format="ascii">4</DataArray>
      </Lines>
      <CellData>
        <DataArray type="String" Name="channel_id" format="ascii">coil_a</DataArray>
        <DataArray type="String" Name="path_id" format="ascii">loop_0</DataArray>
        <DataArray type="UInt8" Name="closed" format="ascii">{closed}</DataArray>
      </CellData>
    </Piece>
  </PolyData>
</VTKFile>
"""


def test_ascii_vtp_loads_explicit_closed_polyline(tmp_path: Path) -> None:
    path = tmp_path / "coil.vtp"
    path.write_text(_vtp(), encoding="utf-8")

    channels = load_channel_paths_vtp(path)

    assert tuple(channel.channel_id for channel in channels) == ("coil_a",)
    polyline = channels[0].polylines[0]
    assert polyline.path_id == "loop_0"
    assert polyline.closed is True
    assert polyline.vertices_m.shape == (3, 3)


def test_vtp_rejects_binary_data_and_inconsistent_closure(tmp_path: Path) -> None:
    binary = tmp_path / "binary.vtp"
    binary.write_text(_vtp(points_format="binary"), encoding="utf-8")
    with pytest.raises(PhysicsValidationError, match="only inline ASCII"):
        load_channel_paths_vtp(binary)

    open_metadata = tmp_path / "open.vtp"
    open_metadata.write_text(_vtp(closed="0"), encoding="utf-8")
    with pytest.raises(PhysicsValidationError, match="open path"):
        load_channel_paths_vtp(open_metadata)
