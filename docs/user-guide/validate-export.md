# Validate and Export an Environment

Validation is a blocking scientific contract, not a best-effort preview. It
checks schemas, source files, dimensions, channel and point order, units,
coordinate frames, hardware feasibility, scenario alignment, and content
identities. Resolve every error at its source and validate again.

The final TUI page reports point and channel counts, response shape and rank,
estimated response memory, dynamic evaluation cost, and every blocking issue.
Export is permitted only when no issue remains. Select a new empty output
directory; the builder writes the package atomically and does not overwrite an
existing environment.

After export, run the package validator and inspector. A successful package has
the canonical files documented in [Format Contracts](../formats.md), and every
manifest checksum matches the file bytes. Then load it once through
`magshield_env.make_env`, call `reset`, and verify one legal `step` before
handing the environment to downstream reinforcement-learning code.

Non-interactive commands emit exactly one JSON document on stdout. Progress and
diagnostics use stderr. Do not parse human help text as JSON, and do not treat a
JSON error envelope as success. The live command `--help` is the only source for
arguments, flags, defaults, and invocation examples.
