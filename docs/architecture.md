# Architecture

## Boundary

`magshield-env` converts explicit physical inputs into a validated,
self-contained Gymnasium environment package. It does not design coils, invoke
finite-element software, train policies, or know any experiment-specific
directory layout.

## Components and dependency direction

```text
Textual / CLI -> builder API -> domain contracts
                             -> physics models
Gymnasium Env -> plant + hardware + scenario contracts
```

The domain layer has no dependency on terminal or Gymnasium code. Physics code
accepts SI arrays and returns SI arrays. The Gymnasium layer consumes a plant
interface and never reads source export formats. The TUI only gathers values and
calls the builder API.

## Core invariants

- Points are shaped `[N, 3]` and response matrices `[N, 3, M]` in `float64`.
- Coordinates are metres, field is tesla, current is ampere, time is seconds,
  resistance is ohm, and voltage is volt unless an importer declares and records
  an explicit conversion.
- Point order, channel order, coordinate frame, array shape, and content hashes
  are bound in `manifest.json`.
- Finite-element channel files must describe the same points. Reordering is only
  allowed through an explicit, unique point identity or an explicit coordinate
  tolerance recorded in the build configuration.
- Dynamic geometry keeps conductors fixed in their declared frame, transforms
  body-frame points with the declared pose, and recomputes the analytic segment
  field. It never substitutes a fixed matrix.
- Hardware projection is observable through `info`; no illegal action is
  silently clipped.
- Export succeeds atomically only after every contract has passed.

## Data flow

The builder resolves YAML input, creates or imports points, constructs either a
fixed response or conductor geometry, validates hardware and scenario data, and
writes canonical HDF5/YAML files plus their manifest. `make_env` reads only this
package. At each `step`, the plant returns a response matrix for the active pose,
the hardware model maps normalized current deltas into the legal interval, and
the environment returns residual field, reward, termination state, and explicit
constraint evidence.

## Decisions

- [0001: Canonical scientific exchange formats](decisions/0001-canonical-formats.md)
- [0002: Gymnasium public environment contract](decisions/0002-gymnasium-contract.md)
- [0003: Runtime geometry response](decisions/0003-runtime-geometry.md)
- [0004: Textual as the interactive front end](decisions/0004-textual-tui.md)

## Operator documentation

- [Environment input guide](user-guide/index.md)
- [Canonical format contracts](formats.md)
- [Builder skill](../skills/magshield-env-builder/SKILL.md)
