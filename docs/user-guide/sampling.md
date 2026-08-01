# Generate a Sampling Region

Generated regions are appropriate when the controlled volume is defined by
geometry rather than an existing sensor list. Choose one region kind and a
coordinate frame before choosing a response source. The frame name is an
identity, not a display label: every field and pose that refers to the points
must use the same declared frame.

## Cartesian volume samples

`sphere_cartesian`, `box_cartesian`, and `cylinder_cartesian` place points on a
deterministic Cartesian lattice. Specify all distances in metres. The builder
includes only lattice points that satisfy the declared primitive and preserves
the generator's point order in the package. Changing spacing or geometry
therefore changes point identity and invalidates previously exported fields.

For a sphere, decide centre, radius, and spacing. For a box, decide the minimum
and maximum coordinate on every axis plus spacing. Every maximum must be
strictly greater than its minimum. For a cylinder, decide centre, radius,
height, axis, and spacing.

## Sphere-surface samples

`sphere_surface` uses a declared point count rather than Cartesian spacing.
Decide centre, radius, point count, and frame. Treat a changed point count as a
new physical discretization; do not reuse finite-element results from the old
point set.

## Review before continuing

On the first TUI page, review point count, bounds, frame, weights, and ordering.
Stop if the generated extent is not the intended control region. Command names,
configuration arguments, and examples are maintained by the live CLI help;
consult `magshield-env --help` before automation.
