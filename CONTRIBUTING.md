# Contributing

Use Python 3.12 and `uv` for every dependency and command.

```bash
uv sync
uv run ruff check .
uv run mypy src
uv run pytest
uv build
```

Keep domain and physics logic outside CLI and Textual classes. Public failures
must remain structured, and new user-visible behavior requires unit,
integration, and contract coverage. Design decisions and implementation belong
in the same pull request.
