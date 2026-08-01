"""Strict ASCII VTP PolyData conductor-path import."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections import OrderedDict
from pathlib import Path

import numpy as np

from .models import ChannelPath, PhysicsValidationError, Polyline


def _local_name(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _children(element: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in element if _local_name(child) == name]


def _only_child(element: ET.Element, name: str) -> ET.Element:
    matches = _children(element, name)
    if len(matches) != 1:
        raise PhysicsValidationError(
            f"VTP {element.tag!r} must contain exactly one {name}; got {len(matches)}"
        )
    return matches[0]


def _ascii_tokens(data_array: ET.Element, *, name: str) -> list[str]:
    data_format = data_array.attrib.get("format", "ascii")
    if data_format != "ascii":
        raise PhysicsValidationError(
            f"VTP DataArray {name!r} uses unsupported format {data_format!r}; "
            "only inline ASCII is accepted"
        )
    text = data_array.text or ""
    tokens = text.split()
    if not tokens:
        raise PhysicsValidationError(f"VTP DataArray {name!r} must not be empty")
    return tokens


def _float_array(data_array: ET.Element, *, name: str) -> np.ndarray:
    tokens = _ascii_tokens(data_array, name=name)
    try:
        values = np.asarray(tokens, dtype=np.float64)
    except ValueError as error:
        raise PhysicsValidationError(f"VTP DataArray {name!r} contains a non-float") from error
    if not np.all(np.isfinite(values)):
        raise PhysicsValidationError(f"VTP DataArray {name!r} must contain finite values")
    return values


def _integer_array(data_array: ET.Element, *, name: str) -> np.ndarray:
    tokens = _ascii_tokens(data_array, name=name)
    try:
        values = np.asarray(tokens, dtype=np.int64)
    except ValueError as error:
        raise PhysicsValidationError(f"VTP DataArray {name!r} contains a non-integer") from error
    return values


def _named_arrays(parent: ET.Element, *, section: str) -> dict[str, ET.Element]:
    arrays: dict[str, ET.Element] = {}
    for data_array in _children(parent, "DataArray"):
        name = data_array.attrib.get("Name")
        if not name:
            raise PhysicsValidationError(f"every VTP {section} DataArray must have Name")
        if name in arrays:
            raise PhysicsValidationError(f"duplicate VTP {section} DataArray {name!r}")
        arrays[name] = data_array
    return arrays


def _required_named_array(arrays: dict[str, ET.Element], name: str, *, section: str) -> ET.Element:
    try:
        return arrays[name]
    except KeyError as error:
        raise PhysicsValidationError(f"VTP {section} must contain DataArray {name!r}") from error


def _piece(root: ET.Element) -> ET.Element:
    if root.attrib.get("type") != "PolyData":
        raise PhysicsValidationError("VTP root type must be exactly 'PolyData'")
    if root.attrib.get("header_type") == "UInt64" and _children(root, "AppendedData"):
        raise PhysicsValidationError("VTP appended data is unsupported; use inline ASCII")
    poly_data = _only_child(root, "PolyData")
    pieces = _children(poly_data, "Piece")
    if len(pieces) != 1:
        raise PhysicsValidationError(
            f"VTP PolyData must contain exactly one Piece; got {len(pieces)}"
        )
    return pieces[0]


def _points(piece: ET.Element) -> np.ndarray:
    points_element = _only_child(piece, "Points")
    arrays = _children(points_element, "DataArray")
    if len(arrays) != 1:
        raise PhysicsValidationError("VTP Points must contain exactly one DataArray")
    data_array = arrays[0]
    if data_array.attrib.get("NumberOfComponents") != "3":
        raise PhysicsValidationError("VTP Points DataArray NumberOfComponents must be exactly 3")
    values = _float_array(data_array, name="Points")
    if values.size % 3 != 0:
        raise PhysicsValidationError("VTP Points value count must be divisible by 3")
    points = values.reshape(-1, 3)
    declared = piece.attrib.get("NumberOfPoints")
    if declared is None:
        raise PhysicsValidationError("VTP Piece NumberOfPoints is required")
    try:
        declared_count = int(declared)
    except ValueError as error:
        raise PhysicsValidationError("VTP Piece NumberOfPoints must be an integer") from error
    if points.shape != (declared_count, 3):
        raise PhysicsValidationError(
            f"VTP declares {declared_count} points but stores {len(points)}"
        )
    return points


def _line_indices(piece: ET.Element, point_count: int) -> tuple[np.ndarray, ...]:
    lines = _only_child(piece, "Lines")
    arrays = _named_arrays(lines, section="Lines")
    connectivity = _integer_array(
        _required_named_array(arrays, "connectivity", section="Lines"),
        name="connectivity",
    )
    offsets = _integer_array(
        _required_named_array(arrays, "offsets", section="Lines"), name="offsets"
    )
    declared = piece.attrib.get("NumberOfLines")
    if declared is None:
        raise PhysicsValidationError("VTP Piece NumberOfLines is required")
    try:
        declared_count = int(declared)
    except ValueError as error:
        raise PhysicsValidationError("VTP Piece NumberOfLines must be an integer") from error
    if offsets.shape != (declared_count,):
        raise PhysicsValidationError(
            f"VTP declares {declared_count} lines but stores {len(offsets)} offsets"
        )
    if np.any(offsets <= 0) or np.any(np.diff(offsets) <= 0):
        raise PhysicsValidationError(
            "VTP line offsets must be strictly increasing positive integers"
        )
    if len(offsets) == 0 or int(offsets[-1]) != len(connectivity):
        raise PhysicsValidationError("VTP final line offset must equal connectivity length")
    if np.any(connectivity < 0) or np.any(connectivity >= point_count):
        raise PhysicsValidationError("VTP line connectivity contains an out-of-range point index")
    starts = np.concatenate((np.array([0], dtype=np.int64), offsets[:-1]))
    cells = tuple(connectivity[start:end] for start, end in zip(starts, offsets, strict=True))
    if any(len(cell) < 2 for cell in cells):
        raise PhysicsValidationError("every VTP line must contain at least two point indices")
    return cells


def _cell_tokens(piece: ET.Element, line_count: int) -> dict[str, tuple[str, ...]]:
    cell_data = _only_child(piece, "CellData")
    arrays = _named_arrays(cell_data, section="CellData")
    result: dict[str, tuple[str, ...]] = {}
    for name in ("channel_id", "path_id", "closed"):
        tokens = tuple(
            _ascii_tokens(_required_named_array(arrays, name, section="CellData"), name=name)
        )
        if len(tokens) != line_count:
            raise PhysicsValidationError(f"VTP CellData {name!r} must contain one scalar per line")
        result[name] = tokens
    return result


def _closed(text: str, *, line_index: int) -> bool:
    if text in {"1", "true"}:
        return True
    if text in {"0", "false"}:
        return False
    raise PhysicsValidationError(
        f"VTP line {line_index} closed must be exactly 0, 1, false, or true"
    )


def load_channel_paths_vtp(path: str | Path) -> tuple[ChannelPath, ...]:
    """Load one ASCII VTP line cell per explicitly ordered conductor polyline."""

    resolved = Path(path)
    if not resolved.is_file():
        raise PhysicsValidationError(f"input file does not exist: {resolved}")
    try:
        tree = ET.parse(resolved)
    except (ET.ParseError, OSError) as error:
        raise PhysicsValidationError(f"cannot parse VTP XML: {resolved}") from error
    root = tree.getroot()
    if _local_name(root) != "VTKFile":
        raise PhysicsValidationError("VTP root element must be VTKFile")
    piece = _piece(root)
    points = _points(piece)
    cells = _line_indices(piece, len(points))
    metadata = _cell_tokens(piece, len(cells))

    channels: OrderedDict[str, list[Polyline]] = OrderedDict()
    seen_paths: set[tuple[str, str]] = set()
    for index, cell in enumerate(cells):
        channel_id = metadata["channel_id"][index]
        path_id = metadata["path_id"][index]
        if not channel_id or not path_id:
            raise PhysicsValidationError(
                f"VTP line {index} channel_id and path_id must be non-empty"
            )
        identity = (channel_id, path_id)
        if identity in seen_paths:
            raise PhysicsValidationError(
                f"VTP path {channel_id}/{path_id} must occupy exactly one line cell"
            )
        seen_paths.add(identity)
        is_closed = _closed(metadata["closed"][index], line_index=index)
        indices = cell.tolist()
        if is_closed:
            if indices[-1] != indices[0]:
                raise PhysicsValidationError(
                    f"VTP closed path {channel_id}/{path_id} must repeat its first point"
                )
            indices.pop()
        elif indices[-1] == indices[0]:
            raise PhysicsValidationError(
                f"VTP open path {channel_id}/{path_id} must not end at its first point"
            )
        polyline = Polyline(path_id, points[indices], is_closed)
        channels.setdefault(channel_id, []).append(polyline)
    if not channels:
        raise PhysicsValidationError("VTP must contain at least one conductor line")
    return tuple(
        ChannelPath(channel_id, tuple(polylines)) for channel_id, polylines in channels.items()
    )
