"""Command-line interface with stable machine-readable execution results."""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, is_dataclass
from importlib import import_module
from pathlib import Path
from typing import Any, Protocol, TextIO

from magshield_env.domain.errors import MagshieldEnvError
from magshield_env.tui import BuilderService, MagshieldEnvApp, PackageBuilderService

SCHEMA = "magshield-env.cli.v1"


class CommandService(Protocol):
    """Supply package validation and inspection to non-interactive commands.

    ``validate_environment`` checks one package path and returns its report;
    ``inspect_environment`` reads the same public package contract and returns
    metadata.  ``run`` serializes either result, while this service remains the
    owner of all package and physics access.
    """

    def validate_environment(self, path: Path) -> Any:
        """Validate a built environment package."""

    def inspect_environment(self, path: Path) -> Any:
        """Inspect a built environment package without changing it."""


class PackageCommandService:
    """Resolve the command service from the package's public Python API."""

    def validate_environment(self, path: Path) -> Any:
        package = import_module("magshield_env")
        function = package.validate_environment
        return function(path)

    def inspect_environment(self, path: Path) -> Any:
        package = import_module("magshield_env")
        function = package.inspect_environment
        return function(path)


def build_parser() -> argparse.ArgumentParser:
    """Build the sole source of CLI arguments, defaults, help, and examples."""

    parser = argparse.ArgumentParser(
        prog="magshield-env",
        description=("Build and inspect validated Gymnasium magnetic-control environments."),
        epilog=(
            "examples:\n"
            "  magshield-env tui\n"
            "  magshield-env validate environment/\n"
            "  magshield-env inspect environment/ --pretty"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    tui = subparsers.add_parser(
        "tui",
        help="open the five-step full-screen environment builder",
        description=(
            "Open the five-step full-screen builder. Interactive rendering is "
            "written to stderr so stdout remains unused."
        ),
    )
    tui.add_argument("--no-mouse", action="store_true", help="disable Textual mouse input")

    validate = subparsers.add_parser(
        "validate",
        help="validate an exported environment package",
        description="Validate identities, schemas, arrays, and package checksums.",
    )
    validate.add_argument("path", type=Path, help="environment package directory")
    validate.add_argument("--pretty", action="store_true", help="indent the JSON result")

    inspect = subparsers.add_parser(
        "inspect",
        help="inspect an exported environment package",
        description="Read package metadata and derived dimensions without mutation.",
    )
    inspect.add_argument("path", type=Path, help="environment package directory")
    inspect.add_argument("--pretty", action="store_true", help="indent the JSON result")
    return parser


def run(
    argv: Sequence[str] | None = None,
    *,
    service: CommandService | None = None,
    builder_service: BuilderService | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    app_factory: Callable[[BuilderService], MagshieldEnvApp] = MagshieldEnvApp,
) -> int:
    """Execute one command and return a process exit status."""

    out = stdout or sys.stdout
    err = stderr or sys.stderr
    args = build_parser().parse_args(argv)
    if args.command == "tui":
        app = app_factory(builder_service or PackageBuilderService())
        # Textual constructs its terminal driver from stdout. Redirecting only
        # for the app lifetime preserves the CLI's stdout JSON contract.
        with contextlib.redirect_stdout(err):
            app.run(mouse=not args.no_mouse)
        return 0

    command_service = service or PackageCommandService()
    path = args.path.expanduser().resolve()
    print(f"{args.command}: {path}", file=err)
    try:
        if args.command == "validate":
            result = command_service.validate_environment(path)
        else:
            result = command_service.inspect_environment(path)
    except Exception as exc:
        _write_json(
            out,
            {
                "schema": SCHEMA,
                "ok": False,
                "command": args.command,
                "error": _error_payload(exc),
            },
            pretty=args.pretty,
        )
        return 1

    _write_json(
        out,
        {
            "schema": SCHEMA,
            "ok": True,
            "command": args.command,
            "result": _normalize(result),
        },
        pretty=args.pretty,
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Console-script entry point."""

    return run(argv)


def _write_json(stream: TextIO, payload: Mapping[str, Any], *, pretty: bool) -> None:
    json.dump(
        payload,
        stream,
        indent=2 if pretty else None,
        separators=None if pretty else (",", ":"),
        sort_keys=True,
    )
    stream.write("\n")


def _error_payload(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, MagshieldEnvError):
        record = exc.record
        return {
            "type": record.type,
            "subtype": record.subtype,
            "message": record.message,
            "hint": record.hint,
        }
    return {
        "type": "internal",
        "subtype": type(exc).__name__,
        "message": str(exc),
        "hint": "Inspect stderr and correct the command input or package contract.",
    }


def _normalize(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _normalize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    if hasattr(value, "model_dump"):
        return _normalize(value.model_dump(mode="json"))
    if is_dataclass(value) and not isinstance(value, type):
        return _normalize(asdict(value))
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise TypeError(f"Public command result is not JSON serializable: {type(value)!r}")
