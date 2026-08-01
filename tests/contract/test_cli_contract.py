from __future__ import annotations

import argparse
import io
import json
from pathlib import Path
from typing import Any

import pytest

from magshield_env.cli import build_parser, run


class ContractService:
    """Expose stable results so stream serialization is tested without I/O."""

    def validate_environment(self, path: Path) -> Any:
        return {"package_dir": path, "valid": True}

    def inspect_environment(self, path: Path) -> Any:
        return {"package_dir": path, "response_shape": (2, 3, 1)}


def _commands(parser: argparse.ArgumentParser) -> set[str]:
    actions = (
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    )
    subparsers = tuple(actions)
    assert len(subparsers) == 1
    return set(subparsers[0].choices)


def test_help_contract_is_plain_text_and_lists_only_public_commands() -> None:
    parser = build_parser()
    help_text = parser.format_help()

    assert help_text.startswith("usage: magshield-env")
    assert _commands(parser) == {"tui", "validate", "inspect"}
    assert not help_text.lstrip().startswith("{")
    for command in _commands(parser):
        assert command in help_text


@pytest.mark.parametrize("command", ["validate", "inspect"])
def test_automation_stdout_is_one_json_envelope_and_progress_is_stderr(
    command: str, tmp_path: Path
) -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = run(
        [command, str(tmp_path)],
        service=ContractService(),
        stdout=stdout,
        stderr=stderr,
    )

    documents = stdout.getvalue().splitlines()
    assert exit_code == 0
    assert len(documents) == 1
    payload = json.loads(documents[0])
    assert payload["schema"] == "magshield-env.cli.v1"
    assert payload["ok"] is True
    assert payload["command"] == command
    assert stderr.getvalue().startswith(f"{command}:")


def test_unexpected_failure_is_still_a_structured_json_error(tmp_path: Path) -> None:
    class FailingService(ContractService):
        def validate_environment(self, path: Path) -> Any:
            raise ValueError(f"not an environment package: {path.name}")

    stdout = io.StringIO()
    stderr = io.StringIO()
    exit_code = run(
        ["validate", str(tmp_path)],
        service=FailingService(),
        stdout=stdout,
        stderr=stderr,
    )

    payload = json.loads(stdout.getvalue())
    assert exit_code == 1
    assert payload["ok"] is False
    assert set(payload["error"]) == {"type", "subtype", "message", "hint"}
    assert payload["error"]["subtype"] == "ValueError"
    assert stderr.getvalue().startswith("validate:")
