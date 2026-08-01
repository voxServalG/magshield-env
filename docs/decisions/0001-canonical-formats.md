# 0001: Canonical scientific exchange formats

- **Status**: accepted
- **Date**: 2026-08-01
- **Context**: Users need files readable from Python, MATLAB, finite-element
  exports, and common visualization tools without binding the environment to one
  solver.
- **Decision**: In the need for cross-language scientific exchange, facing
  large dense arrays and geometric paths, we choose YAML/JSON Schema, HDF5,
  CSV, and VTK/VTP instead of project-private NumPy files, gaining explicit
  metadata and interoperability while accepting additional import dependencies.
- **Consequences**: Canonical bundles remain portable; importers must perform
  strict shape, unit, and identity validation.
- **Alternatives Considered**: NumPy-only artifacts were rejected because they
  do not provide a sufficient cross-language metadata contract. Parquet was
  deferred because it does not improve the v1 scientific array boundary.
