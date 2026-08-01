---
name: magshield-env-builder
version: 1.0.0
description: Build and validate a magnetic-control Gymnasium environment.
metadata:
  cliHelp: magshield-env --help
---

# Role

Guide a user from declared physical inputs to one validated environment bundle.
This skill does not train a policy or launch an external field solver.

# Workflow

1. Establish the control region and its coordinate frame. Generate a declared
   primitive or import a point set, then review point count, extent, order, and
   weights.
2. Select exactly one forward source: fixed matrix, finite-element channel
   fields, or conductor geometry. Confirm its point and channel identities.
3. Declare every channel's current, slew, resistance, and voltage limits plus
   the controller timestep.
4. Bind a static or trajectory scenario, then declare observation, action,
   reward, and illegal-action behavior.
5. Validate the complete definition. Resolve every blocking error at its source;
   do not change models or relax tolerances as a fallback.
6. Export only after validation reports no blocking issue, then load the bundle
   once to confirm its Gymnasium contract.

Read the task guide that matches the current stage:

- `docs/user-guide/sampling.md` for generated primitives;
- `docs/user-guide/point-set-import.md` for sensor or evaluation grids;
- `docs/user-guide/finite-element-import.md` for completed solver fields;
- `docs/user-guide/conductor-paths.md` for CSV/VTP geometry;
- `docs/user-guide/hardware-scenarios.md` for limits, external field, and pose;
- `docs/user-guide/validate-export.md` for the final gate and handoff.

# Input preparation

- For generated regions, decide the physical boundary, spacing or surface point
  count, origin, and frame before opening the builder.
- For field exports, produce one full three-component field per channel on the
  same declared point set. Use explicit channel identifiers and SI conversion.
- For conductor geometry, preserve vertex order, path closure, channel identity,
  current direction, and path frame.
- For trajectories, preserve timestamps, external-field rows, translation, and
  quaternion order in one identity-bound file.

# Safety and recovery

- Never infer a coordinate frame or unit.
- Never average, reorder, interpolate, or drop channels unless the input contract
  explicitly requests and records that operation.
- On validation failure, follow the returned hint and repair the source file or
  configuration. Do not retry with a different physical model.
- Before invoking a command, run its current `--help`; command parameters and
  flags are intentionally not duplicated here.

# Commands

- `magshield-env tui` — interactive five-step environment builder.
- `magshield-env validate` — validate a definition or exported package.
- `magshield-env inspect` — inspect package identity and dimensions.

Run each command with `--help` before use to obtain current parameters and
examples.

# Acceptance decisions

- Proceed from sampling only after count, extent, frame, order, and weights
  match the intended control region.
- Proceed from physics only after all point and channel identities match in
  exact order and units are canonical SI.
- Proceed from hardware and scenario only after every runtime frame has the
  exogenous field and pose required by its declared physics mode.
- Export only to a new empty directory after the complete validator has no
  blocking issue. A warning is never permission to ignore an identity error.
- After export, validate, inspect, load through Gymnasium, and execute one legal
  step before handing the package to downstream code.
