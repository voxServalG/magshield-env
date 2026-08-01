from __future__ import annotations

import argparse
import re
from pathlib import Path

from magshield_env.cli import build_parser

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills" / "magshield-env-builder" / "SKILL.md"


def _public_commands() -> set[str]:
    parser = build_parser()
    actions = (
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    )
    subparsers = tuple(actions)
    assert len(subparsers) == 1
    return set(subparsers[0].choices)


def test_skill_command_names_track_cli_without_copying_flags() -> None:
    text = SKILL.read_text(encoding="utf-8")
    normalized_text = " ".join(text.split())
    mentioned = {
        match
        for match in re.findall(r"magshield-env\s+([a-z-]+)", text)
        if not match.startswith("-")
    }
    copied_flags = set(re.findall(r"(?<![A-Za-z0-9_])--[a-z][a-z-]*", text))

    assert mentioned == _public_commands()
    assert copied_flags == {"--help"}
    assert "parameters and flags are intentionally not duplicated here" in normalized_text


def test_skill_routes_every_builder_stage_to_a_guide() -> None:
    text = SKILL.read_text(encoding="utf-8")
    expected = {
        "sampling.md",
        "point-set-import.md",
        "finite-element-import.md",
        "conductor-paths.md",
        "hardware-scenarios.md",
        "validate-export.md",
    }

    assert all(name in text for name in expected)
    assert all((ROOT / "docs" / "user-guide" / name).is_file() for name in expected)
