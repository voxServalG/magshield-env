"""Stable user-facing error records.

``MagshieldEnvError`` carries a stable type and subtype across the Python and
CLI boundaries.  Its message explains the failed contract, while ``hint``
gives the caller one concrete recovery action.  The CLI consumes all four
members to build a machine-readable failure envelope.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ErrorRecord:
    """Describe one public failure and how its consumer can recover."""

    type: str
    subtype: str
    message: str
    hint: str


class MagshieldEnvError(RuntimeError):
    """Expose one validated error record at every public boundary."""

    def __init__(self, record: ErrorRecord) -> None:
        super().__init__(record.message)
        self.record = record


def validation_error(subtype: str, message: str, hint: str) -> MagshieldEnvError:
    """Construct a stable validation error without losing its recovery path."""

    return MagshieldEnvError(
        ErrorRecord(type="validation", subtype=subtype, message=message, hint=hint)
    )


def io_error(subtype: str, message: str, hint: str) -> MagshieldEnvError:
    """Construct a stable input/output error."""

    return MagshieldEnvError(ErrorRecord(type="io", subtype=subtype, message=message, hint=hint))
