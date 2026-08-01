# Environment Builder Design

## Overview

The builder accepts one strict YAML definition and produces an atomic
environment directory. Its public API is shared by Textual and non-interactive
callers.

## Goals

- Generate or import sampling points.
- Import fixed responses and finite-element channel fields.
- Import conductor paths and evaluate dynamic Biot-Savart responses.
- Bind hardware, scenario, reward, observation, and action contracts.
- Export and load a Gymnasium environment.

## Non-goals

- Running COMSOL or another finite-element solver.
- Coil optimization, experiment orchestration, training, evaluation, or policy
  publication.
- Compatibility with private layouts from another project.

## Error handling

No layer catches an invalid physical definition and substitutes another model.
The domain layer rejects schema drift, importers reject inconsistent files, and
the builder does not replace an existing environment unless the user selects a
new empty output directory.

## Open questions

None for v1. Further file adapters require a new ADR and contract fixtures.
