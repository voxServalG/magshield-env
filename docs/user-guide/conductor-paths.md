# Prepare CSV or VTP Conductor Paths

Runtime geometry mode evaluates finite straight conductor segments with the
analytic Biot-Savart expression. It requires explicit path geometry; it never
falls back to a fixed matrix or interpolated response when the pose changes.

## CSV paths

Write one vertex per row using the exact header in
[Format Contracts](../formats.md). Rows for each `(channel_id, path_id)` must be
contiguous and `vertex_index` must be `0..K-1`. `closed` is lowercase `true` or
`false` and must be identical on every row of a path. A closed CSV path lists
each geometric vertex once; closure adds the last-to-first segment. An open
path retains its two physical endpoints.

## VTP paths

Use one PolyData line cell per polyline. The v1 reader accepts only inline ASCII
arrays and requires cell data `channel_id`, `path_id`, and `closed`. A closed
line repeats its first point as its final connectivity index; an open line must
not. This explicit distinction prevents an accidental lead segment or missing
return segment.

## Channel metadata and repeated conductors

The geometry-channel YAML fixes channel order and declares one or more general
field contributions. Each contribution has a 3 by 3 rotation, translation in
metres, gain, and an explicit `allow_improper` decision for reflections. A
reflection is never inferred from the installation layout.

Confirm current direction, vertex order, path closure, coordinate frame, and
channel order before export. Changing any of these creates a different physical
model and invalidates cached responses. CLI parameters remain solely in live
`--help`.
