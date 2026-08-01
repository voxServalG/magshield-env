# Import a Point Set

Use an imported point set when the sampling locations already exist, such as a
sensor survey or an evaluation grid exported by another program. CSV, HDF5,
and VTK-family point files are supported. Their exact fields are documented in
[Format Contracts](../formats.md).

## Prepare identities first

Assign one non-empty, unique `point_id` to every point and preserve row order.
Coordinates are metres and weights are finite, strictly positive values. CSV
and VTK do not carry a trusted frame in this contract, so the build definition
must declare one. HDF5 carries its own `coordinate_frame` attribute and rejects
a separate override.

Point identity is the join key for finite-element fields. Equal coordinates do
not excuse missing, duplicated, or reordered identifiers. This prevents two
physically different sampling grids from being assembled accidentally.

## Validate the import

Preview the count, bounds, first and last identities, coordinate frame, and
weight range. Compare those facts with the originating measurement or solver
export. If validation reports an identity, unit, or shape mismatch, repair the
source export; do not sort, interpolate, or drop rows to make the error vanish.

Current command arguments and examples are available only from the relevant
`--help` output.
