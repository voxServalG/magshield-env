from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest
from textual.widgets import Input, Static

from magshield_env.domain.config import BuildConfig
from magshield_env.tui import MagshieldEnvApp, ValidationIssue, ValidationResult


class RecordingBuilder:
    """Record the same draft that the wizard validates and exports."""

    def __init__(self, *, issues: tuple[ValidationIssue, ...] = ()) -> None:
        self.issues = issues
        self.validated: list[Mapping[str, Any]] = []
        self.exported: list[Mapping[str, Any]] = []

    def validate(self, draft: Mapping[str, Any]) -> ValidationResult:
        BuildConfig.model_validate(draft)
        self.validated.append(draft)
        return ValidationResult(
            summary={
                "point_count": 7,
                "channel_count": 1,
                "response_shape": "[7, 3, 1]",
                "rank": 1,
                "memory_estimate": "168 B",
                "dynamic_compute_cost": "not applicable",
            },
            issues=self.issues,
        )

    def export(self, draft: Mapping[str, Any]) -> Mapping[str, Any]:
        self.exported.append(draft)
        return {"package": str(draft["output_dir"]), "status": "built"}


@pytest.mark.asyncio
async def test_wizard_has_five_steps_and_supports_back_navigation() -> None:
    app = MagshieldEnvApp(RecordingBuilder())
    async with app.run_test(size=(120, 50)) as pilot:
        assert len(app.STEPS) == 5
        assert app.current_step == 0

        await pilot.click("#next")
        assert app.current_step == 1
        await pilot.click("#back")
        assert app.current_step == 0


@pytest.mark.asyncio
async def test_invalid_page_blocks_forward_navigation() -> None:
    app = MagshieldEnvApp(RecordingBuilder())
    async with app.run_test(size=(120, 50)) as pilot:
        app.query_one("#name", Input).value = ""
        await pilot.pause()
        await pilot.click("#next")

        assert app.current_step == 0
        assert "required" in str(app.query_one("#status", Static).content)


@pytest.mark.asyncio
async def test_review_renders_builder_metrics_and_exports_exact_draft() -> None:
    builder = RecordingBuilder()
    app = MagshieldEnvApp(builder)
    async with app.run_test(size=(120, 60)) as pilot:
        app.action_next()
        app.query_one("#forward-source", Input).value = "physics.h5"
        await pilot.pause()
        app.action_next()
        await pilot.pause()
        app.action_next()
        await pilot.pause()
        app.action_next()
        await pilot.pause()

        assert app.current_step == 4
        summary = str(app.query_one("#summary", Static).content)
        assert "Point Count: 7" in summary
        assert "Response Shape: [7, 3, 1]" in summary
        assert not app.query_one("#export").disabled

        await pilot.click("#export")
        await pilot.pause()

    assert builder.validated
    assert len(builder.exported) == 1
    assert builder.exported[0] == builder.validated[-1]


@pytest.mark.asyncio
async def test_builder_issue_is_visible_and_blocks_export() -> None:
    builder = RecordingBuilder(
        issues=(
            ValidationIssue(
                code="identity.channel_order",
                field="forward.channel_ids",
                message="channel order differs from hardware",
                hint="Use the declared hardware order.",
            ),
        )
    )
    app = MagshieldEnvApp(builder)
    async with app.run_test(size=(120, 60)) as pilot:
        app.query_one("#forward-source", Input).value = "physics.h5"
        app.current_step = 4
        await pilot.pause()

        errors = str(app.query_one("#blocking-errors", Static).content)
        assert "identity.channel_order" in errors
        assert "Use the declared hardware order" in errors
        assert app.query_one("#export").disabled
