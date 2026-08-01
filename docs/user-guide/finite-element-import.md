# Import Finite-Element Field Results

The builder imports completed field results; it never starts COMSOL or another
finite-element program. Export one complete three-component field per current
channel at exactly the environment's sampling points. Values are response per
ampere, in tesla per ampere.

## Export one channel at a time

For each channel, preserve the declared `channel_id`, point identities, point
order, coordinate frame, and all three vector components. CSV fields use the
strict columns in [Format Contracts](../formats.md). HDF5 fields carry their
channel, frame, and `T/A` unit as attributes. VTK fields use point data named
`field_T_per_A`; their channel and frame are declared at import.

List channel files in the same order as `channel_ids`. Assembly is
deterministic: the first file becomes response column zero, and so on. Every
file must have exactly the same point identities and order as the selected
point set. The builder fails on duplicates, missing components, wrong units,
wrong frame, or order drift.

## Coordinate tolerance

A nonzero coordinate tolerance is a declared comparison bound, not permission
to infer correspondence. Point identity remains authoritative. Choose a bound
only from the precision of the originating export and record the reason outside
the environment package. Never increase it merely to pass validation.

## Fixed response alternative

If the complete response is already assembled, store a float64 array shaped
`[N, 3, M]` in HDF5 with the point and channel identities described in the
format contract. A fixed response is valid only for its declared geometry and
does not become pose-dependent at runtime.

Consult the current subcommand `--help` for invocation syntax.
