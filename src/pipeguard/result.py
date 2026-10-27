"""Result types shared by checks, the runner and reporters."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Severity(str, Enum):
    """How a failed check affects the gate.

    ERROR stops the batch (non-zero exit). WARN is reported but lets the batch
    continue, unless the run is invoked with ``--fail-on-warn``.
    """

    ERROR = "error"
    WARN = "warn"


class ExitCode:
    """Process exit codes. Schedulers branch on these, so they are part of the API."""

    OK = 0             # all error-level checks passed (warnings may exist)
    CHECK_FAILED = 1   # at least one error-level check failed
    CONFIG_ERROR = 2   # the YAML config is invalid
    DATA_ERROR = 3     # the dataset could not be loaded


@dataclass(frozen=True)
class CheckOutcome:
    """What a check function returns. Kept minimal so new checks are easy to write."""

    passed: bool
    message: str = ""
    failed_count: int = 0
    sample: list[Any] = field(default_factory=list)


@dataclass(frozen=True)
class CheckResult:
    """A check outcome enriched with the metadata the config declared."""

    name: str
    check_type: str
    severity: Severity
    passed: bool
    message: str = ""
    failed_count: int = 0
    sample: list[Any] = field(default_factory=list)

    @property
    def status(self) -> str:
        if self.passed:
            return "pass"
        return "fail" if self.severity is Severity.ERROR else "warn"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.check_type,
            "severity": self.severity.value,
            "status": self.status,
            "message": self.message,
            "failed_count": self.failed_count,
            "sample": [_jsonable(v) for v in self.sample],
        }


@dataclass(frozen=True)
class RunResult:
    """All check results for one dataset, plus the gate decision."""

    dataset: str
    row_count: int
    results: list[CheckResult]
    fail_on_warn: bool = False

    @property
    def errors(self) -> list[CheckResult]:
        return [r for r in self.results if r.status == "fail"]

    @property
    def warnings(self) -> list[CheckResult]:
        return [r for r in self.results if r.status == "warn"]

    @property
    def passed(self) -> bool:
        if self.errors:
            return False
        return not (self.fail_on_warn and self.warnings)

    @property
    def exit_code(self) -> int:
        return ExitCode.OK if self.passed else ExitCode.CHECK_FAILED

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "row_count": self.row_count,
            "passed": self.passed,
            "exit_code": self.exit_code,
            "summary": {
                "total": len(self.results),
                "passed": sum(r.passed for r in self.results),
                "errors": len(self.errors),
                "warnings": len(self.warnings),
            },
            "checks": [r.to_dict() for r in self.results],
        }


def _jsonable(value: Any) -> Any:
    """Convert numpy/pandas scalars in samples into plain JSON types."""
    if hasattr(value, "item") and callable(value.item):
        try:
            return value.item()
        except (ValueError, TypeError):
            pass
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, float) and value != value:  # NaN
        return None
    return value
