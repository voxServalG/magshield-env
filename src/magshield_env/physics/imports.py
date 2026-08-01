"""Strict import and export adapters for standardized physics artifacts."""

from __future__ import annotations

import csv
from collections import OrderedDict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import h5py
import meshio
import numpy as np

from .models import (
    ChannelPath,
    FieldSample,
    PhysicsValidationError,
    PointSet,
    Polyline,
    ResponseMatrix,
)
from .vtp import load_channel_paths_vtp

POINT_COLUMNS = ("point_id", "x_m", "y_m", "z_m", "weight")
FIELD_COLUMNS = ("point_id", "bx_T", "by_T", "bz_T")
PATH_COLUMNS = (
    "channel_id",
    "path_id",
    "vertex_index",
    "x_m",
    "y_m",
    "z_m",
    "closed",
)


def _path(path: str | Path) -> Path:
    resolved = Path(path)
    if not resolved.is_file():
        raise PhysicsValidationError(f"input file does not exist: {resolved}")
    return resolved


def _csv_rows(path: str | Path, expected_columns: tuple[str, ...]) -> list[dict[str, str]]:
    resolved = _path(path)
    with resolved.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != expected_columns:
            raise PhysicsValidationError(
                f"{resolved} columns must be exactly {expected_columns}; got {reader.fieldnames}"
            )
        rows = list(reader)
    if not rows:
        raise PhysicsValidationError(f"{resolved} must contain at least one data row")
    return rows


def _float(text: str, *, field: str, row_number: int) -> float:
    try:
        value = float(text)
    except ValueError as error:
        raise PhysicsValidationError(f"row {row_number} field {field} is not a float") from error
    if not np.isfinite(value):
        raise PhysicsValidationError(f"row {row_number} field {field} must be finite")
    return value


def _required_frame(coordinate_frame: str | None, *, format_name: str) -> str:
    if coordinate_frame is None or not coordinate_frame:
        raise PhysicsValidationError(
            f"coordinate_frame is required explicitly when importing {format_name}"
        )
    return coordinate_frame


def load_points_csv(path: str | Path, *, coordinate_frame: str) -> PointSet:
    rows = _csv_rows(path, POINT_COLUMNS)
    ids = tuple(row["point_id"] for row in rows)
    points = np.array(
        [
            [_float(row[key], field=key, row_number=index + 2) for key in ("x_m", "y_m", "z_m")]
            for index, row in enumerate(rows)
        ],
        dtype=np.float64,
    )
    weights = np.array(
        [
            _float(row["weight"], field="weight", row_number=index + 2)
            for index, row in enumerate(rows)
        ],
        dtype=np.float64,
    )
    return PointSet(ids, points, weights, coordinate_frame)


def write_points_csv(point_set: PointSet, path: str | Path) -> None:
    destination = Path(path)
    with destination.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(POINT_COLUMNS)
        for point_id, point, weight in zip(
            point_set.point_ids, point_set.points_m, point_set.weights, strict=True
        ):
            writer.writerow((point_id, *(float(value) for value in point), float(weight)))


def _decode_hdf5_strings(values: Any, *, name: str) -> tuple[str, ...]:
    array = np.asarray(values)
    if array.ndim != 1:
        raise PhysicsValidationError(f"{name} must be a one-dimensional string dataset")
    decoded = tuple(
        value.decode("utf-8") if isinstance(value, bytes) else str(value)
        for value in array.tolist()
    )
    return decoded


def _hdf5_text_attribute(container: Any, name: str) -> str:
    if name not in container.attrs:
        raise PhysicsValidationError(f"HDF5 attribute {name!r} is required")
    value = container.attrs[name]
    return value.decode("utf-8") if isinstance(value, bytes) else str(value)


def load_points_hdf5(path: str | Path) -> PointSet:
    with h5py.File(_path(path), "r") as file:
        required = {"point_ids", "points_m", "weights"}
        if not required.issubset(file.keys()):
            raise PhysicsValidationError(f"HDF5 point set requires datasets {sorted(required)}")
        if _hdf5_text_attribute(file, "length_unit") != "m":
            raise PhysicsValidationError("HDF5 length_unit must be exactly 'm'")
        return PointSet(
            _decode_hdf5_strings(file["point_ids"][...], name="point_ids"),
            np.asarray(file["points_m"][...], dtype=np.float64),
            np.asarray(file["weights"][...], dtype=np.float64),
            _hdf5_text_attribute(file, "coordinate_frame"),
        )


def write_points_hdf5(point_set: PointSet, path: str | Path) -> None:
    with h5py.File(Path(path), "w") as file:
        file.attrs["coordinate_frame"] = point_set.coordinate_frame
        file.attrs["length_unit"] = "m"
        string_type = h5py.string_dtype(encoding="utf-8")
        file.create_dataset("point_ids", data=np.asarray(point_set.point_ids, dtype=string_type))
        file.create_dataset("points_m", data=point_set.points_m, dtype=np.float64)
        file.create_dataset("weights", data=point_set.weights, dtype=np.float64)


def _decode_vtk_ids(point_data: dict[str, np.ndarray], count: int) -> tuple[str, ...]:
    if "point_id_utf8" in point_data and "point_id_length" in point_data:
        encoded = np.asarray(point_data["point_id_utf8"], dtype=np.uint8)
        lengths = np.asarray(point_data["point_id_length"], dtype=np.int64).reshape(-1)
        if encoded.ndim != 2 or encoded.shape[0] != count or lengths.shape != (count,):
            raise PhysicsValidationError("VTK UTF-8 point identity arrays have invalid shapes")
        if np.any(lengths < 1) or np.any(lengths > encoded.shape[1]):
            raise PhysicsValidationError("VTK point_id_length contains an invalid byte count")
        try:
            return tuple(
                bytes(row[:length]).decode("utf-8")
                for row, length in zip(encoded, lengths, strict=True)
            )
        except UnicodeDecodeError as error:
            raise PhysicsValidationError("VTK point_id_utf8 is not valid UTF-8") from error
    if "point_id" not in point_data:
        raise PhysicsValidationError(
            "VTK point data must contain point_id or point_id_utf8 plus point_id_length"
        )
    raw = np.asarray(point_data["point_id"]).reshape(-1)
    if raw.shape != (count,):
        raise PhysicsValidationError("VTK point_id must contain exactly one scalar per point")
    return tuple(str(value.item() if hasattr(value, "item") else value) for value in raw)


def load_points_vtk(path: str | Path, *, coordinate_frame: str) -> PointSet:
    mesh = meshio.read(_path(path))
    points = np.asarray(mesh.points, dtype=np.float64)
    if points.ndim != 2 or points.shape[1] != 3:
        raise PhysicsValidationError(f"VTK points must have shape (N, 3); got {points.shape}")
    if "weight" not in mesh.point_data:
        raise PhysicsValidationError("VTK point data must contain weight")
    weights = np.asarray(mesh.point_data["weight"], dtype=np.float64).reshape(-1)
    ids = _decode_vtk_ids(mesh.point_data, len(points))
    return PointSet(ids, points, weights, coordinate_frame)


def _encoded_ids(ids: tuple[str, ...]) -> tuple[np.ndarray, np.ndarray]:
    encoded = tuple(value.encode("utf-8") for value in ids)
    width = max(len(value) for value in encoded)
    matrix = np.zeros((len(ids), width), dtype=np.uint8)
    lengths = np.empty(len(ids), dtype=np.int64)
    for index, value in enumerate(encoded):
        matrix[index, : len(value)] = np.frombuffer(value, dtype=np.uint8)
        lengths[index] = len(value)
    return matrix, lengths


def write_points_vtk(point_set: PointSet, path: str | Path) -> None:
    encoded, lengths = _encoded_ids(point_set.point_ids)
    vertices = np.arange(point_set.count, dtype=np.int64).reshape(-1, 1)
    mesh = meshio.Mesh(
        point_set.points_m,
        [("vertex", vertices)],
        point_data={
            "weight": point_set.weights,
            "point_id_utf8": encoded,
            "point_id_length": lengths,
        },
    )
    mesh.write(Path(path))


def load_point_set(path: str | Path, *, coordinate_frame: str | None = None) -> PointSet:
    suffix = Path(path).suffix.lower()
    if suffix == ".csv":
        return load_points_csv(
            path, coordinate_frame=_required_frame(coordinate_frame, format_name="CSV")
        )
    if suffix in {".h5", ".hdf5"}:
        if coordinate_frame is not None:
            raise PhysicsValidationError("coordinate_frame must come from HDF5, not an override")
        return load_points_hdf5(path)
    if suffix in {".vtk", ".vtu", ".vtp"}:
        return load_points_vtk(
            path, coordinate_frame=_required_frame(coordinate_frame, format_name="VTK")
        )
    raise PhysicsValidationError(f"unsupported point-set suffix: {suffix}")


def load_field_csv(path: str | Path, *, channel_id: str, coordinate_frame: str) -> FieldSample:
    rows = _csv_rows(path, FIELD_COLUMNS)
    ids = tuple(row["point_id"] for row in rows)
    field = np.array(
        [
            [_float(row[key], field=key, row_number=index + 2) for key in ("bx_T", "by_T", "bz_T")]
            for index, row in enumerate(rows)
        ],
        dtype=np.float64,
    )
    return FieldSample(channel_id, ids, field, coordinate_frame)


def load_field_hdf5(path: str | Path, *, channel_id: str | None = None) -> FieldSample:
    with h5py.File(_path(path), "r") as file:
        required = {"point_ids", "field_T_per_A"}
        if not required.issubset(file.keys()):
            raise PhysicsValidationError(f"HDF5 field requires datasets {sorted(required)}")
        if _hdf5_text_attribute(file, "field_unit") != "T/A":
            raise PhysicsValidationError("HDF5 field_unit must be exactly 'T/A'")
        stored_channel = _hdf5_text_attribute(file, "channel_id")
        if channel_id is not None and channel_id != stored_channel:
            raise PhysicsValidationError(
                f"requested channel_id {channel_id!r} does not match stored {stored_channel!r}"
            )
        return FieldSample(
            stored_channel,
            _decode_hdf5_strings(file["point_ids"][...], name="point_ids"),
            np.asarray(file["field_T_per_A"][...], dtype=np.float64),
            _hdf5_text_attribute(file, "coordinate_frame"),
        )


def load_field_vtk(path: str | Path, *, channel_id: str, coordinate_frame: str) -> FieldSample:
    mesh = meshio.read(_path(path))
    if "field_T_per_A" not in mesh.point_data:
        raise PhysicsValidationError("VTK point data must contain field_T_per_A")
    ids = _decode_vtk_ids(mesh.point_data, len(mesh.points))
    return FieldSample(
        channel_id,
        ids,
        np.asarray(mesh.point_data["field_T_per_A"], dtype=np.float64),
        coordinate_frame,
    )


def assemble_response_matrix(
    point_set: PointSet,
    fields: Iterable[FieldSample],
    *,
    channel_ids: tuple[str, ...] | None = None,
) -> ResponseMatrix:
    samples = tuple(fields)
    if not samples:
        raise PhysicsValidationError("at least one field sample is required")
    actual_ids = tuple(sample.channel_id for sample in samples)
    if len(set(actual_ids)) != len(actual_ids):
        raise PhysicsValidationError("field channel_id values must be unique")
    expected_ids = actual_ids if channel_ids is None else tuple(channel_ids)
    if actual_ids != expected_ids:
        raise PhysicsValidationError(
            f"field channel order {actual_ids} does not match required order {expected_ids}"
        )
    for sample in samples:
        if sample.point_ids != point_set.point_ids:
            raise PhysicsValidationError(
                f"field {sample.channel_id!r} point identity/order does not match point set"
            )
        if sample.coordinate_frame != point_set.coordinate_frame:
            raise PhysicsValidationError(
                f"field {sample.channel_id!r} frame {sample.coordinate_frame!r} does not match "
                f"point frame {point_set.coordinate_frame!r}"
            )
    response = np.stack(tuple(sample.field_T_per_A for sample in samples), axis=2)
    return ResponseMatrix(point_set.point_ids, expected_ids, response, point_set.coordinate_frame)


def load_response_matrix_hdf5(path: str | Path) -> ResponseMatrix:
    with h5py.File(_path(path), "r") as file:
        required = {"point_ids", "channel_ids", "response_T_per_A"}
        if not required.issubset(file.keys()):
            raise PhysicsValidationError(f"HDF5 response requires datasets {sorted(required)}")
        if _hdf5_text_attribute(file, "field_unit") != "T/A":
            raise PhysicsValidationError("HDF5 field_unit must be exactly 'T/A'")
        return ResponseMatrix(
            _decode_hdf5_strings(file["point_ids"][...], name="point_ids"),
            _decode_hdf5_strings(file["channel_ids"][...], name="channel_ids"),
            np.asarray(file["response_T_per_A"][...], dtype=np.float64),
            _hdf5_text_attribute(file, "coordinate_frame"),
        )


def write_response_matrix_hdf5(response: ResponseMatrix, path: str | Path) -> None:
    string_type = h5py.string_dtype(encoding="utf-8")
    with h5py.File(Path(path), "w") as file:
        file.attrs["coordinate_frame"] = response.coordinate_frame
        file.attrs["field_unit"] = "T/A"
        file.create_dataset("point_ids", data=np.asarray(response.point_ids, dtype=string_type))
        file.create_dataset("channel_ids", data=np.asarray(response.channel_ids, dtype=string_type))
        file.create_dataset("response_T_per_A", data=response.response_T_per_A, dtype=np.float64)


def _parse_bool(text: str, *, row_number: int) -> bool:
    if text == "true":
        return True
    if text == "false":
        return False
    raise PhysicsValidationError(f"row {row_number} closed must be exactly 'true' or 'false'")


def load_channel_paths_csv(path: str | Path) -> tuple[ChannelPath, ...]:
    rows = _csv_rows(path, PATH_COLUMNS)
    groups: OrderedDict[tuple[str, str], list[tuple[int, np.ndarray, bool]]] = OrderedDict()
    for row_number, row in enumerate(rows, start=2):
        try:
            vertex_index = int(row["vertex_index"])
        except ValueError as error:
            raise PhysicsValidationError(
                f"row {row_number} vertex_index is not an integer"
            ) from error
        if vertex_index < 0:
            raise PhysicsValidationError(f"row {row_number} vertex_index must be non-negative")
        vertex = np.array(
            [_float(row[key], field=key, row_number=row_number) for key in ("x_m", "y_m", "z_m")],
            dtype=np.float64,
        )
        key = (row["channel_id"], row["path_id"])
        if not all(key):
            raise PhysicsValidationError(
                f"row {row_number} channel_id and path_id must be non-empty"
            )
        groups.setdefault(key, []).append(
            (vertex_index, vertex, _parse_bool(row["closed"], row_number=row_number))
        )

    channels: OrderedDict[str, list[Polyline]] = OrderedDict()
    for (channel_id, path_id), values in groups.items():
        indices = tuple(value[0] for value in values)
        if indices != tuple(range(len(values))):
            raise PhysicsValidationError(
                f"path {channel_id}/{path_id} vertex_index must be ordered 0..{len(values) - 1}"
            )
        closed_values = {value[2] for value in values}
        if len(closed_values) != 1:
            raise PhysicsValidationError(
                f"path {channel_id}/{path_id} has inconsistent closed values"
            )
        polyline = Polyline(
            path_id, np.stack(tuple(value[1] for value in values)), closed_values.pop()
        )
        channels.setdefault(channel_id, []).append(polyline)
    return tuple(ChannelPath(channel_id, tuple(paths)) for channel_id, paths in channels.items())


def _vtk_cell_scalar(mesh: meshio.Mesh, name: str, cell_type: str, count: int) -> np.ndarray:
    values_by_type = mesh.cell_data_dict.get(name)
    if values_by_type is None or cell_type not in values_by_type:
        raise PhysicsValidationError(f"VTK line cell data must contain {name}")
    values = np.asarray(values_by_type[cell_type]).reshape(-1)
    if values.shape != (count,):
        raise PhysicsValidationError(f"VTK {name} must contain one scalar per line cell")
    return values


def load_channel_paths_vtk(path: str | Path) -> tuple[ChannelPath, ...]:
    if Path(path).suffix.lower() == ".vtp":
        return load_channel_paths_vtp(path)
    mesh = meshio.read(_path(path))
    line_blocks = [block for block in mesh.cells if block.type == "line"]
    if len(line_blocks) != 1:
        raise PhysicsValidationError("VTK path import requires exactly one line cell block")
    lines = np.asarray(line_blocks[0].data, dtype=np.int64)
    if lines.ndim != 2 or lines.shape[1] != 2:
        raise PhysicsValidationError(
            "VTK path line cells must each contain exactly two point indices"
        )
    channel_ids = _vtk_cell_scalar(mesh, "channel_id", "line", len(lines))
    path_ids = _vtk_cell_scalar(mesh, "path_id", "line", len(lines))
    closed = _vtk_cell_scalar(mesh, "closed", "line", len(lines))
    groups: OrderedDict[tuple[str, str], list[tuple[np.ndarray, bool]]] = OrderedDict()
    for index, line in enumerate(lines):
        is_closed = int(closed[index])
        if is_closed not in {0, 1}:
            raise PhysicsValidationError("VTK closed values must be 0 or 1")
        key = (str(channel_ids[index]), str(path_ids[index]))
        groups.setdefault(key, []).append((line, bool(is_closed)))
    channels: OrderedDict[str, list[Polyline]] = OrderedDict()
    for (channel_id, path_id), segments in groups.items():
        closed_values = {segment[1] for segment in segments}
        if len(closed_values) != 1:
            raise PhysicsValidationError(
                f"VTK path {channel_id}/{path_id} has inconsistent closed values"
            )
        indices = [int(segments[0][0][0]), int(segments[0][0][1])]
        for segment, _ in segments[1:]:
            if int(segment[0]) != indices[-1]:
                raise PhysicsValidationError(
                    f"VTK path {channel_id}/{path_id} segments must be ordered and oriented"
                )
            indices.append(int(segment[1]))
        is_closed = closed_values.pop()
        if is_closed:
            if indices[-1] != indices[0]:
                raise PhysicsValidationError(
                    f"VTK closed path {channel_id}/{path_id} must end at its first point"
                )
            indices.pop()
        polyline = Polyline(path_id, np.asarray(mesh.points[indices], dtype=np.float64), is_closed)
        channels.setdefault(channel_id, []).append(polyline)
    return tuple(ChannelPath(channel_id, tuple(paths)) for channel_id, paths in channels.items())
