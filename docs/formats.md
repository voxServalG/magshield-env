# Format Contracts

All numeric physics arrays are float64. Length is metres (`m`), magnetic field
is tesla (`T`), current is amperes (`A`), time is seconds (`s`), resistance is
ohms, and voltage is volts. Imported non-SI source data must be converted before
it reaches these canonical formats; the conversion and source identity belong
in the build provenance.

Coordinate frames bind both locations and vector components. A point frame says
where coordinates live; a response, external-field, or observation-basis frame
says which axes its three vector components use. Equal array shapes never imply
equal frames. Version 0.1 accepts only canonical SI source artifacts: convert a
non-SI export deterministically before import and retain the original source and
conversion procedure outside the portable package for provenance.

Coordinate frames bind both locations and vector components. A point frame says
where coordinates live; a response, external-field, or observation-basis frame
says which axes its three vector components use. Equal array shapes never imply
equal frames. Version 0.1 accepts only canonical SI source artifacts: convert a
non-SI export deterministically before import and retain the original source and
conversion procedure outside the portable package for provenance.

## Point sets

CSV has this exact header and order:

```text
point_id,x_m,y_m,z_m,weight
```

`point_id` is non-empty and unique. Coordinates and weights are finite; weights
are positive. CSV requires the coordinate frame in the build definition.

HDF5 point sets have root datasets `point_ids` (UTF-8, `[N]`), `points_m`
(`[N,3]`), and `weights` (`[N]`), plus root attributes
`coordinate_frame=<non-empty text>` and `length_unit=m`.

VTK-family point sets store coordinates as mesh points and point data `weight`.
Identity is either scalar `point_id`, or the lossless pair `point_id_utf8`
(`[N,W]` uint8) and `point_id_length` (`[N]`). The coordinate frame is declared
in the build definition.

## Per-channel fields

CSV has this exact header and order:

```text
point_id,bx_T,by_T,bz_T
```

The import declaration supplies channel identity and coordinate frame. HDF5
fields have datasets `point_ids` (`[N]`) and `field_T_per_A` (`[N,3]`) plus root
attributes `channel_id`, `coordinate_frame`, and `field_unit=T/A`. VTK-family
fields store `[N,3]` point data `field_T_per_A`, together with point identity;
channel and frame are declared at import.

## Fixed response matrix

Canonical HDF5 uses datasets `point_ids` (`[N]`), `channel_ids` (`[M]`), and
`response_T_per_A` (`[N,3,M]`), with root attributes `coordinate_frame` and
`field_unit=T/A`. Dataset order is semantic and is bound by the manifest.

## Conductor paths

CSV has this exact header and order:

```text
channel_id,path_id,vertex_index,x_m,y_m,z_m,closed
```

VTP is XML `PolyData` with one `Piece`, inline ASCII `Points`, and `Lines`
arrays named `connectivity` and `offsets`. `CellData` contains one value per
line for `channel_id`, `path_id`, and `closed`. Each `(channel_id,path_id)` is
unique. For VTP, closed accepts `1` or `true`, open accepts `0` or `false`.

Geometry-channel YAML has `schema_name: magshield_env.geometry_channels`,
`schema_version: 1`, ordered `channel_ids`, and non-empty `contributions`. Every
contribution declares `rotation`, `translation_m`, `allow_improper`, and `gain`.

## Build definition and JSON Schema

Build YAML has `schema_name: magshield_env.build_config` and
`schema_version: 1`. The authoritative validation model is
`magshield_env.domain.config.BuildConfig`; `schemas/build-config.schema.json` is
its deterministic, committed JSON Schema projection. Contract tests regenerate
the projection and require byte-equivalent JSON content after normalization.
Any model change must update the schema in the same change.

## Exported environment package

An exported directory contains exactly the required portable contract files:

```text
environment.yaml
manifest.json
physics.h5
hardware.yaml
scenario.h5
README.md
```

`environment.yaml` names immutable package members and the Gymnasium interface.
`physics.h5` contains point identity and either response data or conductor
geometry. `hardware.yaml` freezes ordered channel constraints. `scenario.h5`
contains exogenous field and pose frames. `manifest.json` records schema
versions, source identities, coordinate frame, array shapes, channel order, and
SHA-256 for every member. A missing, extra-contract, reordered, or changed
member fails validation.

`physics.h5` always declares `point_coordinate_frame`,
`response_coordinate_frame`, `length_unit=m`, and `field_response_unit=T/A`.
An `observation_basis` dataset additionally declares `component_frame`. Dynamic
geometry declares `path_frame`, `pose_source_frame`, and `pose_target_frame`;
the source must equal the point frame and the target must equal the path frame.

`scenario.h5` declares `field_unit=T`,
`external_field_component_frame`, and
`pose_layout=translation_m,quaternion_xyzw`. Imported trajectory pose datasets
declare `pose_length_unit=m` and `pose_quaternion_order=xyzw`. External-field
components, response components, and optional basis components must use the
same frame before they may be added or projected.

## Field-error metric

For residual vectors `r_i` and positive sampling weights `w_i`, the environment
uses one weighted vector root-mean-square value:

```text
field_rms = sqrt(sum_i(w_i * (rx_i^2 + ry_i^2 + rz_i^2)) / sum_i(w_i))
```

Scaling all weights by the same positive constant leaves the metric unchanged.
This is a vector-magnitude RMS over points, not an RMS over the `3N` scalar
components. The reward applies its declared threshold, scale, and weight to
this value.

`physics.h5` always declares `point_coordinate_frame`,
`response_coordinate_frame`, `length_unit=m`, and `field_response_unit=T/A`.
An `observation_basis` dataset additionally declares `component_frame`. Dynamic
geometry declares `path_frame`, `pose_source_frame`, and `pose_target_frame`;
the source must equal the point frame and the target must equal the path frame.

`scenario.h5` declares `field_unit=T`,
`external_field_component_frame`, and
`pose_layout=translation_m,quaternion_xyzw`. Imported trajectory pose datasets
declare `pose_length_unit=m` and `pose_quaternion_order=xyzw`. External-field
components, response components, and optional basis components must use the
same frame before they may be added or projected.

## Field-error metric

For residual vectors `r_i` and positive sampling weights `w_i`, the environment
uses one weighted vector root-mean-square value:

```text
field_rms = sqrt(sum_i(w_i * (rx_i^2 + ry_i^2 + rz_i^2)) / sum_i(w_i))
```

Scaling all weights by the same positive constant leaves the metric unchanged.
This is a vector-magnitude RMS over points, not an RMS over the `3N` scalar
components. The reward applies its declared threshold, scale, and weight to
this value.

## CLI streams

`validate` and `inspect` write exactly one JSON envelope with schema
`magshield-env.cli.v1` to stdout and progress to stderr. Success has `ok: true`,
`command`, and `result`. Failure has `ok: false`, `command`, and a structured
`error` containing `type`, `subtype`, `message`, and `hint`. `tui` writes its
interactive rendering to stderr and leaves stdout unused. Standard `--help` is
plain text and is the sole source of arguments, defaults, flags, and examples.
