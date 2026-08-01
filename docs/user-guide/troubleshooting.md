# Troubleshoot a Rejected Build or Package

Every rejection identifies a violated source or package contract. Repair that
contract and validate again; do not relax tolerances, reorder data, or switch
physics modes merely to obtain a package.

## Frame mismatch

Check point coordinates, response components, external-field components, and
optional basis components separately. Their frame strings are exact identities.
For dynamic geometry, the pose source must be the point frame and the pose
target must be the path frame. A rotation changes both point locations and the
meaning of vector components, so a matching shape is not sufficient evidence.

## Point or channel order mismatch

Compare identifiers row by row. Regenerate the field export on the authoritative
point set or regenerate all dependent fields after changing the sampling grid.
Do not sort one file independently. Hardware channels must appear in exactly the
response-column order.

## Unit rejection

Version 0.1 consumes canonical SI artifacts only. Convert the source through a
deterministic, reviewed preprocessing step, preserve that source and conversion
record, and import the converted artifact. Renaming a column or attribute does
not convert its values.

## Existing or altered output

Export to a new directory. A portable package contains exactly six files; extra
notes, modified bytes, or edited manifest metadata invalidate it. Keep analysis
beside the package rather than inside it.

## Dynamic response mismatch

The validator rebuilds the stored reference response from packaged paths,
contributions, points, and the first pose. A mismatch means those members do not
describe the same physical model. Rebuild the package from one consistent set
of sources; there is no fixed-matrix fallback.
