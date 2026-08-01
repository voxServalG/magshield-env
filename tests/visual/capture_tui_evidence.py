"""Capture deterministic SVG evidence for every TUI acceptance state."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from textual.widgets import Input

from magshield_env.domain.config import BuildConfig
from magshield_env.tui import MagshieldEnvApp, ValidationIssue, ValidationResult

ROOT = Path(__file__).resolve().parents[2]
DESTINATION = ROOT / "docs" / "evidence" / "tui"


class EvidenceBuilder:
    """Validate a real draft while returning deterministic review evidence."""

    def __init__(self, issues: tuple[ValidationIssue, ...] = ()) -> None:
        self.issues = issues

    def validate(self, draft: Mapping[str, Any]) -> ValidationResult:
        BuildConfig.model_validate(draft)
        return ValidationResult(
            summary={
                "point_count": 515,
                "channel_count": 6,
                "response_shape": "[515, 3, 6]",
                "rank": 6,
                "memory_estimate": "72.42 KiB",
                "dynamic_compute_cost": "not applicable",
            },
            issues=self.issues,
        )

    def export(self, draft: Mapping[str, Any]) -> Mapping[str, Any]:
        return {
            "package": str(draft["output_dir"]),
            "package_identity": "37d13f66b03d...f0bd",
            "status": "built",
        }


async def _capture_page(step: int) -> None:
    app = MagshieldEnvApp(EvidenceBuilder())
    async with app.run_test(size=(150, 64)) as pilot:
        app.query_one("#forward-source", Input).value = "response.h5"
        app.current_step = step
        await pilot.pause()
        app.save_screenshot(filename=f"step-{step + 1}.svg", path=str(DESTINATION))


async def _capture_blocked() -> None:
    issue = ValidationIssue(
        code="identity.channel_order",
        field="forward.channel_ids",
        message="channel order differs from hardware",
        hint="Use the declared hardware order.",
    )
    app = MagshieldEnvApp(EvidenceBuilder((issue,)))
    async with app.run_test(size=(150, 64)) as pilot:
        app.query_one("#forward-source", Input).value = "response.h5"
        app.current_step = 4
        await pilot.pause()
        app.save_screenshot(filename="review-blocked.svg", path=str(DESTINATION))


async def _capture_success() -> None:
    service = EvidenceBuilder()
    app = MagshieldEnvApp(service)
    async with app.run_test(size=(150, 64)) as pilot:
        app.query_one("#forward-source", Input).value = "response.h5"
        app.current_step = 4
        await pilot.pause()
        result = service.export(app._draft())
        app._render_export_success(result)
        await pilot.pause()
        app.save_screenshot(filename="review-exported.svg", path=str(DESTINATION))


async def main() -> None:
    DESTINATION.mkdir(parents=True, exist_ok=True)
    for existing in DESTINATION.glob("*.svg"):
        existing.unlink()
    for step in range(5):
        await _capture_page(step)
    await _capture_blocked()
    await _capture_success()


if __name__ == "__main__":
    asyncio.run(main())
