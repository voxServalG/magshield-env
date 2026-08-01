# Environment Input Guide

This guide prepares source files for the five builder stages. It defines the
physical and data decisions that must be made before opening the TUI; it does
not duplicate command arguments. Run `magshield-env --help` and the selected
subcommand's `--help` for the current invocation syntax.

1. [Generate a sampling region](sampling.md), or [import a measured point
   set](point-set-import.md).
2. Choose exactly one response source: [finite-element field
   results](finite-element-import.md), a fixed HDF5 response matrix, or
   [conductor paths](conductor-paths.md).
3. [Declare hardware, external field, and pose](hardware-scenarios.md).
4. [Validate and export](validate-export.md) the self-contained environment.
5. If a gate fails, use [Troubleshooting](troubleshooting.md) to repair the
   declared source rather than bypassing validation.

The exact CSV, HDF5, VTK/VTP, YAML, and package layouts are frozen in
[Format Contracts](../formats.md).
