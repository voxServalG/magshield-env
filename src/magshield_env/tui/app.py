"""Textual five-step environment builder."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, ClassVar

from pydantic import ValidationError
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.reactive import reactive
from textual.widgets import Button, Footer, Header, Input, Label, Static

from magshield_env.domain.errors import MagshieldEnvError

from .services import (
    BuilderService,
    PackageBuilderService,
    ValidationIssue,
    ValidationResult,
)


class MagshieldEnvApp(App[Mapping[str, Any] | None]):
    """Guide one draft from named fields through validation and export.

    ``STEPS`` names the stable five-page contract and ``current_step`` selects
    the visible page.  ``service`` receives the draft assembled by ``_draft``;
    ``_validation`` preserves the exact report shown on the review page; and
    the Textual widgets in ``compose`` collect inputs, surface field help,
    preview referenced files, navigate backward and forward, and finally show
    the service's export result.
    """

    TITLE = "magshield-env"
    SUB_TITLE = "Validated magnetic-control environment builder"
    STEPS: ClassVar[tuple[str, ...]] = (
        "Sampling region",
        "Forward response and paths",
        "Hardware constraints",
        "Scenario and Gymnasium",
        "Validate and export",
    )
    BINDINGS: ClassVar[list[Binding | tuple[str, str] | tuple[str, str, str]]] = [
        ("ctrl+right", "next", "Next step"),
        ("ctrl+left", "previous", "Previous step"),
        ("ctrl+q", "quit", "Quit"),
    ]
    CSS = """
    Screen { layout: vertical; }
    #step-title { height: 3; padding: 1 2; background: $boost; text-style: bold; }
    .wizard-page { display: none; height: 1fr; padding: 1 2; }
    .wizard-page.active { display: block; }
    .field-help { color: $text-muted; margin-bottom: 1; }
    .preview { border: round $primary; padding: 0 1; margin: 1 0; min-height: 3; }
    #status { min-height: 3; padding: 1 2; color: $warning; }
    #summary, #blocking-errors { border: round $primary; padding: 1; margin: 1 0; }
    #blocking-errors { border: round $error; }
    #navigation { height: 3; align-horizontal: right; padding-right: 2; }
    #navigation Button { margin-left: 1; }
    Input { margin-bottom: 1; }
    """

    current_step = reactive(0)

    def __init__(self, service: BuilderService | None = None) -> None:
        super().__init__()
        self.service: BuilderService = service or PackageBuilderService()
        self._validation: ValidationResult | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="step-title")
        yield from self._sampling_page()
        yield from self._forward_page()
        yield from self._hardware_page()
        yield from self._scenario_page()
        yield from self._review_page()
        yield Static(id="status")
        with Horizontal(id="navigation"):
            yield Button("Back", id="back", variant="default")
            yield Button("Next", id="next", variant="primary")
        yield Footer()

    def _sampling_page(self) -> ComposeResult:
        with VerticalScroll(classes="wizard-page", id="page-0"):
            yield Label("Environment name")
            yield Input(value="magnetic-control", id="name")
            yield Static(
                "Choose sphere_cartesian, sphere_surface, box_cartesian, "
                "cylinder_cartesian, or import. Distances use metres.",
                classes="field-help",
            )
            yield Label("Region kind")
            yield Input(value="sphere_cartesian", id="region-kind")
            yield Label("Radius (m) / imported point file")
            yield Input(value="0.1", id="region-primary")
            yield Label("Spacing (m) / sphere-surface point count")
            yield Input(value="0.02", id="region-spacing")
            yield Label("Centre x,y,z (m)")
            yield Input(value="0,0,0", id="region-center")
            yield Label("Box minimum x,y,z (m)")
            yield Input(value="-0.1,-0.1,-0.1", id="region-minimum")
            yield Label("Box maximum x,y,z (m)")
            yield Input(value="0.1,0.1,0.1", id="region-maximum")
            yield Label("Cylinder height (m) and axis")
            yield Input(value="0.2", id="region-height")
            yield Input(value="z", id="region-axis")
            yield Label("Coordinate frame")
            yield Input(value="body", id="region-frame")
            yield Static(id="preview-0", classes="preview")

    def _forward_page(self) -> ComposeResult:
        with VerticalScroll(classes="wizard-page", id="page-1"):
            yield Static(
                "Choose fixed_matrix, finite_element, or geometry. File paths "
                "are passed unchanged to the builder.",
                classes="field-help",
            )
            yield Label("Forward kind")
            yield Input(value="fixed_matrix", id="forward-kind")
            yield Label("Matrix/path file, or comma-separated finite-element files")
            yield Input(placeholder="physics.h5", id="forward-source")
            yield Label("Channel metadata file (geometry only)")
            yield Input(placeholder="channels.csv", id="forward-channels")
            yield Label("Channel IDs, comma separated")
            yield Input(value="ch0", id="forward-channel-ids")
            yield Label("HDF5 dataset")
            yield Input(value="/response_matrix", id="forward-dataset")
            yield Label("Geometry path coordinate frame")
            yield Input(value="lab", id="path-frame")
            yield Label("Geometry pose source / target frame")
            yield Input(value="body", id="pose-source-frame")
            yield Input(value="lab", id="pose-target-frame")
            yield Static(id="preview-1", classes="preview")

    def _hardware_page(self) -> ComposeResult:
        with VerticalScroll(classes="wizard-page", id="page-2"):
            yield Static(
                "Each comma-separated property must have one SI value per "
                "channel. The builder rejects inconsistent channel identity.",
                classes="field-help",
            )
            yield Label("Timestep (s)")
            yield Input(value="0.01", id="timestep")
            yield Label("Channel IDs")
            yield Input(value="ch0", id="hardware-channel-ids")
            yield Label("Current lower / upper (A)")
            yield Input(value="-1", id="current-lower")
            yield Input(value="1", id="current-upper")
            yield Label("Slew limit (A/s), resistance (ohm), voltage limit (V)")
            yield Input(value="10", id="slew-rate")
            yield Input(value="1", id="resistance")
            yield Input(value="10", id="voltage")
            yield Static(id="preview-2", classes="preview")

    def _scenario_page(self) -> ComposeResult:
        with VerticalScroll(classes="wizard-page", id="page-3"):
            yield Static(
                "Scenario paths may provide external field and pose data. "
                "Actions are normalized current deltas; invalid actions are "
                "either reported after projection or terminate the episode.",
                classes="field-help",
            )
            yield Label("Scenario kind: static or trajectory")
            yield Input(value="static", id="scenario-kind")
            yield Label("External-field or trajectory file (optional for static)")
            yield Input(id="scenario-path")
            yield Label("External-field vector component frame")
            yield Input(value="body", id="external-field-frame")
            yield Label("Episode length")
            yield Input(value="1", id="episode-length")
            yield Label("Trajectory random start: true or false")
            yield Input(value="false", id="random-start")
            yield Label("Static pose translation x,y,z (m)")
            yield Input(value="0,0,0", id="static-translation")
            yield Label("Static pose quaternion x,y,z,w")
            yield Input(value="0,0,0,1", id="static-quaternion")
            yield Label("Observation mode: full_field or basis")
            yield Input(value="full_field", id="observation-mode")
            yield Label("Basis path (required for basis mode)")
            yield Input(id="basis-path")
            yield Label("Basis vector component frame (required for basis mode)")
            yield Input(value="body", id="basis-frame")
            yield Label("Include pose in observation: true or false")
            yield Input(value="true", id="include-pose")
            yield Label("Constraint mode: project_and_report or terminate")
            yield Input(value="project_and_report", id="constraint-mode")
            yield Label("Field reward: threshold (T), scale (T), weight")
            yield Input(value="1e-7", id="field-threshold")
            yield Input(value="1e-6", id="field-scale")
            yield Input(value="1", id="field-weight")
            yield Label("Power reward: scale (W), weight")
            yield Input(value="1", id="power-scale")
            yield Input(value="0", id="power-weight")
            yield Label("Slew reward: scale (A), weight")
            yield Input(value="1", id="slew-scale")
            yield Input(value="0", id="slew-weight")
            yield Label("Constraint reward: scale (A), weight")
            yield Input(value="1", id="constraint-scale")
            yield Input(value="1", id="constraint-weight")
            yield Label("Optional nominal currents (A), scale (A), weight")
            yield Input(id="nominal-currents")
            yield Input(id="nominal-scale")
            yield Input(id="nominal-weight")
            yield Static(id="preview-3", classes="preview")

    def _review_page(self) -> ComposeResult:
        with VerticalScroll(classes="wizard-page", id="page-4"):
            yield Static(
                "Review builder-derived dimensions and all blocking errors "
                "before writing a self-contained environment package.",
                classes="field-help",
            )
            yield Label("Output directory")
            yield Input(value="environment", id="output-dir")
            yield Static(id="summary")
            yield Static(id="blocking-errors")
            yield Static(id="preview-4", classes="preview")
            yield Button("Validate again", id="validate", variant="default")
            yield Button("Export environment", id="export", variant="success")

    def on_mount(self) -> None:
        self._show_step()
        self._update_previews()

    def watch_current_step(self, _old: int, _new: int) -> None:
        if self.is_running:
            self._show_step()

    def _show_step(self) -> None:
        for index in range(len(self.STEPS)):
            page = self.query_one(f"#page-{index}")
            page.set_class(index == self.current_step, "active")
        self.query_one("#step-title", Static).update(
            f"Step {self.current_step + 1} of {len(self.STEPS)}: {self.STEPS[self.current_step]}"
        )
        self.query_one("#back", Button).disabled = self.current_step == 0
        self.query_one("#next", Button).disabled = self.current_step == 4
        if self.current_step == 4:
            self._validate_draft()

    @on(Input.Changed)
    def _input_changed(self, _event: Input.Changed) -> None:
        self._validation = None
        self._update_previews()
        if self.current_step < 4:
            errors = self._local_errors(self.current_step)
            self.query_one("#status", Static).update("\n".join(errors))

    @on(Button.Pressed)
    def _button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "next":
            self.action_next()
        elif event.button.id == "back":
            self.action_previous()
        elif event.button.id == "validate":
            self._validate_draft()
        elif event.button.id == "export":
            self._export()

    def action_next(self) -> None:
        if self.current_step >= len(self.STEPS) - 1:
            return
        errors = self._local_errors(self.current_step)
        if errors:
            self.query_one("#status", Static).update("\n".join(errors))
            return
        self.query_one("#status", Static).update("")
        self.current_step += 1

    def action_previous(self) -> None:
        if self.current_step > 0:
            self.query_one("#status", Static).update("")
            self.current_step -= 1

    def _local_errors(self, step: int) -> list[str]:
        try:
            if step == 0:
                self._region()
                self._required("name", "Environment name")
            elif step == 1:
                self._forward()
            elif step == 2:
                self._hardware()
            elif step == 3:
                self._scenario()
                self._environment()
        except ValueError as exc:
            return [str(exc)]
        return []

    def _validate_draft(self) -> None:
        try:
            draft = self._draft()
            self._validation = self.service.validate(draft)
        except (ValueError, ValidationError, MagshieldEnvError) as exc:
            self._validation = ValidationResult(issues=(self._issue(exc),), summary={})
        except Exception as exc:  # service boundary: expose, never continue export
            self._validation = ValidationResult(
                issues=(
                    ValidationIssue(
                        code="builder_failure",
                        message=str(exc),
                        hint="Inspect the builder error and correct its input contract.",
                    ),
                ),
                summary={},
            )
        self._render_validation()

    def _render_validation(self) -> None:
        assert self._validation is not None
        summary = self._validation.summary
        summary_text = (
            "\n".join(f"{key.replace('_', ' ').title()}: {value}" for key, value in summary.items())
            or "No metrics are available because validation failed."
        )
        self.query_one("#summary", Static).update(summary_text)
        if self._validation.issues:
            error_text = "\n".join(self._format_issue(issue) for issue in self._validation.issues)
        else:
            error_text = "No blocking errors."
        self.query_one("#blocking-errors", Static).update(error_text)
        self.query_one("#export", Button).disabled = not self._validation.ok

    def _export(self) -> None:
        self._validate_draft()
        assert self._validation is not None
        if not self._validation.ok:
            self.query_one("#status", Static).update(
                "Export blocked: correct every validation error first."
            )
            return
        try:
            result = self.service.export(self._draft())
        except Exception as exc:  # service boundary: a failed build remains failed
            issue = self._issue(exc)
            self.query_one("#blocking-errors", Static).update(self._format_issue(issue))
            self.query_one("#status", Static).update("Export failed.")
            return
        self._render_export_success(result)
        self.exit(result)

    def _render_export_success(self, result: Mapping[str, Any]) -> None:
        """Render the exact successful export state before returning it to a caller."""

        self.query_one("#summary", Static).update(
            json.dumps(result, indent=2, sort_keys=True, default=str)
        )
        self.query_one("#blocking-errors", Static).update("No blocking errors.")
        self.query_one("#status", Static).update("Environment package exported.")

    def _draft(self) -> dict[str, Any]:
        return {
            "schema_name": "magshield_env.build_config",
            "schema_version": 1,
            "name": self._required("name", "Environment name"),
            "region": self._region(),
            "forward": self._forward(),
            "hardware": self._hardware(),
            "scenario": self._scenario(),
            "environment": self._environment(),
            "output_dir": self._required("output-dir", "Output directory"),
        }

    def _region(self) -> dict[str, Any]:
        kind = self._required("region-kind", "Region kind")
        frame = self._required("region-frame", "Region frame")
        primary = self._required("region-primary", "Region radius or point file")
        if kind == "import":
            return {"kind": kind, "path": primary, "frame": frame, "dataset": "/"}
        center = self._vector("region-center", "Region centre")
        if kind == "sphere_cartesian":
            return {
                "kind": kind,
                "radius_m": self._positive(primary, "Radius"),
                "spacing_m": self._positive_input("region-spacing", "Spacing"),
                "center_m": center,
                "frame": frame,
            }
        if kind == "sphere_surface":
            return {
                "kind": kind,
                "radius_m": self._positive(primary, "Radius"),
                "point_count": self._integer("region-spacing", "Point count", minimum=4),
                "center_m": center,
                "frame": frame,
            }
        if kind == "box_cartesian":
            return {
                "kind": kind,
                "minimum_m": self._vector("region-minimum", "Box minimum"),
                "maximum_m": self._vector("region-maximum", "Box maximum"),
                "spacing_m": self._positive_input("region-spacing", "Spacing"),
                "frame": frame,
            }
        if kind == "cylinder_cartesian":
            return {
                "kind": kind,
                "radius_m": self._positive(primary, "Radius"),
                "height_m": self._positive_input("region-height", "Height"),
                "spacing_m": self._positive_input("region-spacing", "Spacing"),
                "center_m": center,
                "axis": self._required("region-axis", "Cylinder axis"),
                "frame": frame,
            }
        raise ValueError(f"Unsupported region kind: {kind}")

    def _forward(self) -> dict[str, Any]:
        kind = self._required("forward-kind", "Forward kind")
        source = self._required("forward-source", "Forward source")
        channel_ids = self._csv("forward-channel-ids", "Forward channel IDs")
        if kind == "fixed_matrix":
            return {
                "kind": kind,
                "path": source,
                "dataset": self._required("forward-dataset", "Matrix dataset"),
                "channel_ids": channel_ids,
            }
        if kind == "finite_element":
            files = tuple(part.strip() for part in source.split(",") if part.strip())
            if len(files) != len(channel_ids):
                raise ValueError("Finite-element files must match the channel ID count.")
            return {
                "kind": kind,
                "channel_files": files,
                "channel_ids": channel_ids,
                "coordinate_tolerance_m": 0.0,
            }
        if kind == "geometry":
            return {
                "kind": kind,
                "paths": source,
                "channels": self._required("forward-channels", "Geometry channel metadata file"),
                "path_frame": self._required("path-frame", "Path frame"),
                "pose_source_frame": self._required("pose-source-frame", "Pose source frame"),
                "pose_target_frame": self._required("pose-target-frame", "Pose target frame"),
                "pose_cache_size": 64,
            }
        raise ValueError(f"Unsupported forward kind: {kind}")

    def _hardware(self) -> dict[str, Any]:
        ids = self._csv("hardware-channel-ids", "Hardware channel IDs")
        properties = {
            "current_lower_a": self._float_csv("current-lower", "Lower currents"),
            "current_upper_a": self._float_csv("current-upper", "Upper currents"),
            "slew_rate_upper_a_per_s": self._float_csv("slew-rate", "Slew limits"),
            "resistance_ohm": self._float_csv("resistance", "Resistances"),
            "voltage_upper_v": self._float_csv("voltage", "Voltage limits"),
        }
        for name, values in properties.items():
            if len(values) != len(ids):
                raise ValueError(f"{name} must contain one value per hardware channel.")
        channels = []
        for index, channel_id in enumerate(ids):
            channels.append(
                {
                    "channel_id": channel_id,
                    **{name: values[index] for name, values in properties.items()},
                }
            )
        return {
            "timestep_seconds": self._positive_input("timestep", "Timestep"),
            "channels": tuple(channels),
        }

    def _scenario(self) -> dict[str, Any]:
        kind = self._required("scenario-kind", "Scenario kind")
        path = self._value("scenario-path")
        if kind == "static":
            return {
                "kind": kind,
                "external_field": path or None,
                "external_field_component_frame": self._required(
                    "external-field-frame", "External-field component frame"
                ),
                "episode_length": self._integer("episode-length", "Episode length", minimum=1),
                "translation_m": self._vector("static-translation", "Static pose translation"),
                "quaternion_xyzw": self._fixed_float_csv(
                    "static-quaternion", "Static pose quaternion", count=4
                ),
            }
        if kind == "trajectory":
            if not path:
                raise ValueError("Trajectory file is required for a trajectory scenario.")
            return {
                "kind": kind,
                "path": path,
                "external_field_component_frame": self._required(
                    "external-field-frame", "External-field component frame"
                ),
                "episode_length": self._integer("episode-length", "Episode length", minimum=1),
                "random_start": self._boolean("random-start", "Random start"),
            }
        raise ValueError(f"Unsupported scenario kind: {kind}")

    def _environment(self) -> dict[str, Any]:
        observation = self._required("observation-mode", "Observation mode")
        basis_path = self._value("basis-path") or None
        basis_frame = self._value("basis-frame") or None
        if observation == "basis" and basis_path is None:
            raise ValueError("Basis path is required for basis observation mode.")
        if observation not in {"full_field", "basis"}:
            raise ValueError(f"Unsupported observation mode: {observation}")
        nominal_currents = self._value("nominal-currents")
        nominal_scale = self._value("nominal-scale")
        nominal_weight = self._value("nominal-weight")
        nominal_fields = (nominal_currents, nominal_scale, nominal_weight)
        if any(nominal_fields) and not all(nominal_fields):
            raise ValueError(
                "Nominal currents, nominal scale, and nominal weight must be provided together."
            )
        reward: dict[str, Any] = {
            "field_threshold_t": self._nonnegative_input("field-threshold", "Field threshold"),
            "field_scale_t": self._positive_input("field-scale", "Field scale"),
            "field_weight": self._nonnegative_input("field-weight", "Field weight"),
            "power_scale_w": self._positive_input("power-scale", "Power scale"),
            "power_weight": self._nonnegative_input("power-weight", "Power weight"),
            "slew_scale_a": self._positive_input("slew-scale", "Slew scale"),
            "slew_weight": self._nonnegative_input("slew-weight", "Slew weight"),
            "constraint_scale_a": self._positive_input("constraint-scale", "Constraint scale"),
            "constraint_weight": self._nonnegative_input("constraint-weight", "Constraint weight"),
        }
        if all(nominal_fields):
            reward.update(
                {
                    "nominal_currents_a": self._float_csv("nominal-currents", "Nominal currents"),
                    "nominal_scale_a": self._positive_input("nominal-scale", "Nominal scale"),
                    "nominal_weight": self._nonnegative_input("nominal-weight", "Nominal weight"),
                }
            )
        return {
            "observation_mode": observation,
            "basis_path": basis_path,
            "basis_component_frame": basis_frame if observation == "basis" else None,
            "include_pose": self._boolean("include-pose", "Include pose"),
            "action_mode": "current_delta",
            "constraint_mode": self._required("constraint-mode", "Constraint mode"),
            "reward": reward,
        }

    def _update_previews(self) -> None:
        if not self.is_running:
            return
        region_source = self._value("region-primary")
        forward_source = self._value("forward-source")
        scenario_source = self._value("scenario-path")
        output = self._value("output-dir")
        self.query_one("#preview-0", Static).update(
            self._path_preview("Sampling source", region_source)
            if self._value("region-kind") == "import"
            else f"Generated region: {self._value('region-kind')} in SI metres"
        )
        self.query_one("#preview-1", Static).update(
            self._path_preview("Forward source", forward_source)
        )
        channel_count = len(self._csv_unchecked("hardware-channel-ids"))
        self.query_one("#preview-2", Static).update(
            f"Hardware preview: {channel_count} channel(s), dt={self._value('timestep')} s"
        )
        self.query_one("#preview-3", Static).update(
            self._path_preview("Scenario source", scenario_source)
            if scenario_source
            else "Static scenario: no source file selected"
        )
        self.query_one("#preview-4", Static).update(
            f"Package destination: {Path(output).expanduser() if output else '(required)'}"
        )

    @staticmethod
    def _path_preview(label: str, value: str) -> str:
        if not value:
            return f"{label}: (required)"
        path = Path(value).expanduser()
        return f"{label}: {path} ({'exists' if path.exists() else 'not found'})"

    @staticmethod
    def _issue(exc: Exception) -> ValidationIssue:
        if isinstance(exc, MagshieldEnvError):
            record = exc.record
            return ValidationIssue(
                code=f"{record.type}.{record.subtype}",
                message=record.message,
                hint=record.hint,
            )
        if isinstance(exc, ValidationError):
            first = exc.errors()[0]
            return ValidationIssue(
                code="invalid_config",
                field=".".join(str(part) for part in first["loc"]),
                message=first["msg"],
                hint="Correct the field and validate again.",
            )
        return ValidationIssue(code="builder_failure", message=str(exc))

    @staticmethod
    def _format_issue(issue: ValidationIssue) -> str:
        location = f" [{issue.field}]" if issue.field else ""
        hint = f" Hint: {issue.hint}" if issue.hint else ""
        return f"{issue.code}{location}: {issue.message}.{hint}"

    def _value(self, widget_id: str) -> str:
        return self.query_one(f"#{widget_id}", Input).value.strip()

    def _required(self, widget_id: str, label: str) -> str:
        value = self._value(widget_id)
        if not value:
            raise ValueError(f"{label} is required.")
        return value

    def _vector(self, widget_id: str, label: str) -> tuple[float, float, float]:
        values = self._float_csv(widget_id, label)
        if len(values) != 3:
            raise ValueError(f"{label} must contain exactly three values.")
        return values[0], values[1], values[2]

    def _csv(self, widget_id: str, label: str) -> tuple[str, ...]:
        values = self._csv_unchecked(widget_id)
        if not values:
            raise ValueError(f"{label} must contain at least one value.")
        if len(values) != len(set(values)):
            raise ValueError(f"{label} must not contain duplicates.")
        return values

    def _csv_unchecked(self, widget_id: str) -> tuple[str, ...]:
        return tuple(part.strip() for part in self._value(widget_id).split(",") if part.strip())

    def _float_csv(self, widget_id: str, label: str) -> tuple[float, ...]:
        raw = self._csv_unchecked(widget_id)
        try:
            return tuple(float(value) for value in raw)
        except ValueError as exc:
            raise ValueError(f"{label} must contain only numeric values.") from exc

    def _fixed_float_csv(self, widget_id: str, label: str, *, count: int) -> tuple[float, ...]:
        values = self._float_csv(widget_id, label)
        if len(values) != count:
            raise ValueError(f"{label} must contain exactly {count} values.")
        return values

    def _boolean(self, widget_id: str, label: str) -> bool:
        raw = self._required(widget_id, label).lower()
        if raw == "true":
            return True
        if raw == "false":
            return False
        raise ValueError(f"{label} must be true or false.")

    def _positive_input(self, widget_id: str, label: str) -> float:
        return self._positive(self._required(widget_id, label), label)

    @staticmethod
    def _positive(raw: str, label: str) -> float:
        try:
            value = float(raw)
        except ValueError as exc:
            raise ValueError(f"{label} must be numeric.") from exc
        if value <= 0:
            raise ValueError(f"{label} must be greater than zero.")
        return value

    def _nonnegative_input(self, widget_id: str, label: str) -> float:
        value = self._positive_or_zero(self._required(widget_id, label), label)
        return value

    @staticmethod
    def _positive_or_zero(raw: str, label: str) -> float:
        try:
            value = float(raw)
        except ValueError as exc:
            raise ValueError(f"{label} must be numeric.") from exc
        if value < 0:
            raise ValueError(f"{label} must not be negative.")
        return value

    def _integer(self, widget_id: str, label: str, minimum: int) -> int:
        raw = self._required(widget_id, label)
        try:
            value = int(raw)
        except ValueError as exc:
            raise ValueError(f"{label} must be an integer.") from exc
        if value < minimum:
            raise ValueError(f"{label} must be at least {minimum}.")
        return value
