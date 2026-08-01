from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import pytest

from magshield_env.cli import run
from magshield_env.domain.errors import validation_error
from magshield_env.tui import BuilderService, ValidationResult


class FakeCommandService:
    """Return deterministic public reports to the CLI serializer."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[tuple[str, Path]] = []

    def validate_environment(self, path: Path) -> Any:
        self.calls.append(("validate", path))
        if self.error:
            raise self.error
        return {"valid": True, "path": path}

    def inspect_environment(self, path: Path) -> Any:
        self.calls.append(("inspect", path))
        if self.error:
            raise self.error
        return {"point_count": 12, "response_shape": (12, 3, 2)}


class UnusedBuilderService:
    """Satisfy the TUI command boundary while a fake app checks stream routing."""

    def validate(self, draft: Mapping[str, Any]) -> ValidationResult:
        raise AssertionError("the fake app must not validate")

    def export(self, draft: Mapping[str, Any]) -> Mapping[str, Any]:
        raise AssertionError("the fake app must not export")


class PrintingApp:
    """Emulate one Textual frame so the CLI stream contract is observable."""

    def run(self, *, mouse: bool) -> None:
        print(f"TUI frame; mouse={mouse}")


def test_help_is_standard_plain_text(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        run(["--help"])

    captured = capsys.readouterr()
    assert raised.value.code == 0
    assert captured.out.startswith("usage: magshield-env")
    assert "validate" in captured.out
    assert "inspect" in captured.out
    assert not captured.out.lstrip().startswith("{")


@pytest.mark.parametrize("command", ["validate", "inspect"])
def test_noninteractive_success_is_json_only_stdout(
    command: str, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    service = FakeCommandService()
    exit_code = run([command, str(tmp_path)], service=service)

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["schema"] == "magshield-env.cli.v1"
    assert payload["ok"] is True
    assert payload["command"] == command
    assert captured.out.count("\n") == 1
    assert f"{command}:" in captured.err


def test_structured_domain_error_is_json_only_stdout(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    service = FakeCommandService(
        validation_error(
            "checksum_mismatch",
            "physics.h5 does not match its manifest",
            "Rebuild the environment package from trusted inputs.",
        )
    )
    exit_code = run(["validate", str(tmp_path)], service=service)

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 1
    assert payload["ok"] is False
    assert payload["error"] == {
        "type": "validation",
        "subtype": "checksum_mismatch",
        "message": "physics.h5 does not match its manifest",
        "hint": "Rebuild the environment package from trusted inputs.",
    }
    assert "checksum_mismatch" not in captured.err


def test_pretty_output_remains_one_json_document(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    exit_code = run(["inspect", str(tmp_path), "--pretty"], service=FakeCommandService())

    captured = capsys.readouterr()
    assert exit_code == 0
    assert json.loads(captured.out)["result"]["response_shape"] == [12, 3, 2]
    assert captured.out.startswith("{\n")


def test_tui_rendering_is_redirected_to_stderr(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def app_factory(_service: BuilderService) -> Any:
        return PrintingApp()

    exit_code = run(
        ["tui", "--no-mouse"],
        builder_service=UnusedBuilderService(),
        app_factory=cast(Any, app_factory),
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out == ""
    assert captured.err == "TUI frame; mouse=False\n"
