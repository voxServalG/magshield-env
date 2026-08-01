# Project instructions

## Engineering

- Use `uv` for dependency management and command execution.
- Keep modules highly cohesive and loosely coupled.
- Do not add fallbacks, heuristic bandages, silent clipping, or post-processing
  that hides a violated contract. Invalid physical inputs fail explicitly.
- A class docstring must tell the consumption story using all of its members.
- `docs/` explains architecture and invariants; `skills/` explains workflows;
  live `--help` is the only source for flags and command parameters.
- Command results use structured JSON on stdout. Progress, diagnostics, and the
  Textual terminal surface use stderr.

## Scope

This project only builds and loads magnetic-control Gymnasium environments. It
does not train agents, launch finite-element solvers, or depend on
`magnet-field-modulation-refactor`.
