# magshield-env

`magshield-env` builds and loads self-contained Gymnasium environments from
declared magnetic sampling points, forward responses or conductor geometry,
hardware limits, and scenarios. It does not train policies or run a
finite-element solver.

## Install

For development from a source checkout:

```bash
uv sync --locked
uv run magshield-env --help
```

To install a built wheel as a command-line tool:

```bash
uv tool install dist/magshield_env-0.1.0-py3-none-any.whl
magshield-env --help
```

Python projects can add the same wheel with `uv add /path/to/magshield_env.whl`.
Inspect the current command arguments and defaults with `magshield-env --help`
and each subcommand's `--help` output.

## Build and use one environment

The shortest interactive workflow is:

```bash
uv run magshield-env tui
uv run magshield-env validate path/to/environment
uv run magshield-env inspect path/to/environment --pretty
```

The five-step Textual interface collects the sampling region, forward model,
hardware contract, scenario, and Gymnasium behavior. The exported directory can
then be loaded without the original source files:

```python
import numpy as np

from magshield_env import make_env

env = make_env("path/to/environment")
observation, info = env.reset(seed=7)
observation, reward, terminated, truncated, info = env.step(
    np.zeros(env.action_space.shape, dtype=np.float64)
)
```

For programmatic construction and validation:

```python
from magshield_env import build_environment, load_build_config, validate_environment

config = load_build_config("build.yaml")
report = build_environment(config)
validation = validate_environment(report.output_dir)
```

## Documentation

The bilingual user documentation (Chinese authoritative, English translation)
is published on ReadTheDocs: <https://magshield-env.readthedocs.io/>. Sources
live in [`site/`](site/); build and translation workflows are described in
[`site/README.md`](site/README.md).

## Contracts and examples

- [`docs/formats.md`](docs/formats.md) defines units, identities, CSV, HDF5,
  VTK/VTP, YAML, and package layout contracts.
- [`schemas/`](schemas/) contains the authoritative JSON Schema projections.
  Installed wheels also expose them through
  `load_json_schema("build-config")`, `load_json_schema("environment-package")`,
  and `load_json_schema("geometry-channels")`.
- [`examples/minimal-finite-element/`](examples/minimal-finite-element/) contains
  a minimal finite-element CSV build definition; [`examples/geometry/`](examples/geometry/)
  contains equivalent CSV and VTP conductor-path examples.
- [`docs/user-guide/`](docs/user-guide/) explains sampling, imports, hardware,
  scenarios, and package validation.
- [`docs/architecture.md`](docs/architecture.md) records system boundaries, and
  [`skills/magshield-env-builder/SKILL.md`](skills/magshield-env-builder/SKILL.md)
  gives the reusable builder workflow.
