from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def test_distribution_has_no_dependency_on_original_project() -> None:
    payload: dict[str, Any] = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = payload["project"]["dependencies"]

    assert all(not dependency.lower().startswith("magshield") for dependency in dependencies)


def test_source_never_imports_original_magshield_package() -> None:
    forbidden = re.compile(r"(?:^|\n)\s*(?:from|import)\s+magshield(?:\s|\.)")
    offenders = [
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "src" / "magshield_env").rglob("*.py")
        if forbidden.search(path.read_text(encoding="utf-8"))
    ]

    assert offenders == []
