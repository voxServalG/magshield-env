"""Builder boundary consumed by the interactive configuration wizard.

The TUI deliberately knows only this module.  Domain validation and package
construction remain behind ``BuilderService``, so a caller can inject the real
builder, a remote adapter, or a deterministic test double without putting
physics code in the presentation layer.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, is_dataclass
from importlib import import_module
from pathlib import Path
from typing import Any, Protocol, cast, runtime_checkable

from pydantic import ValidationError

from magshield_env.domain.config import BuildConfig
from magshield_env.domain.errors import MagshieldEnvError


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """Carry one blocking problem from the builder to the final wizard page."""

    code: str
    message: str
    field: str | None = None
    hint: str | None = None


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Carry builder metrics and every blocking issue without hiding failures."""

    summary: Mapping[str, Any]
    issues: tuple[ValidationIssue, ...] = ()

    @property
    def ok(self) -> bool:
        """Return whether export is allowed."""

        return not self.issues


@runtime_checkable
class BuilderService(Protocol):
    """Let the wizard validate a draft and then export that exact draft.

    The wizard creates ``draft`` from its fields, ``validate`` turns it into a
    reviewable report, and ``export`` consumes the unchanged mapping plus its
    declared ``output_dir``.  The returned mappings become user-facing
    summaries; the service remains the sole owner of physical I/O and build
    decisions.
    """

    def validate(self, draft: Mapping[str, Any]) -> ValidationResult:
        """Validate one complete draft and return metrics and blocking issues."""

    def export(self, draft: Mapping[str, Any]) -> Mapping[str, Any]:
        """Build one package from a previously validated draft."""


class PackageBuilderService:
    """Connect the wizard to the package's public domain and build APIs.

    ``validate`` turns the mapping into ``BuildConfig`` and calls
    ``inspect_build`` so the final page reports dimensions derived from the
    actual physical sources. ``export`` repeats strict model validation and
    passes the model to the public ``build_environment`` function. The class
    therefore owns no physics and never silently repairs malformed input.
    """

    def validate(self, draft: Mapping[str, Any]) -> ValidationResult:
        try:
            config = BuildConfig.model_validate(draft)
        except ValidationError as exc:
            issues = tuple(
                ValidationIssue(
                    code="invalid_config",
                    field=".".join(str(part) for part in error["loc"]),
                    message=error["msg"],
                    hint="Correct the field and validate the draft again.",
                )
                for error in exc.errors()
            )
            return ValidationResult(summary={}, issues=issues)

        from magshield_env.builder import inspect_build

        try:
            summary = inspect_build(config)
        except MagshieldEnvError as exc:
            record = exc.record
            return ValidationResult(
                summary={},
                issues=(
                    ValidationIssue(
                        code=f"{record.type}.{record.subtype}",
                        message=record.message,
                        hint=record.hint,
                    ),
                ),
            )
        except (OSError, ValueError) as exc:
            return ValidationResult(
                summary={},
                issues=(
                    ValidationIssue(
                        code="build_contract",
                        message=str(exc),
                        hint="Correct the physical source contract and validate again.",
                    ),
                ),
            )
        return ValidationResult(summary=summary)

    def export(self, draft: Mapping[str, Any]) -> Mapping[str, Any]:
        config = BuildConfig.model_validate(draft)
        # Resolve at the call boundary to avoid a package-initialization cycle.
        package = import_module("magshield_env")
        build_environment = cast("Callable[[BuildConfig], Any]", vars(package)["build_environment"])
        result = build_environment(config)
        return normalize_mapping(result)


def normalize_mapping(value: Any) -> Mapping[str, Any]:
    """Convert a public result object to a JSON-like summary mapping."""

    if isinstance(value, Mapping):
        return {str(key): _normalize(item) for key, item in value.items()}
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(mode="json")
        if isinstance(dumped, Mapping):
            return {str(key): _normalize(item) for key, item in dumped.items()}
    if is_dataclass(value) and not isinstance(value, type):
        return {str(key): _normalize(item) for key, item in asdict(value).items()}
    return {"value": _normalize(value)}


def _normalize(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _normalize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    if hasattr(value, "model_dump"):
        return _normalize(value.model_dump(mode="json"))
    return value
