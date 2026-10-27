"""Execute configured checks against a DataFrame."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from . import registry
from .config import Config, CheckConfig
from .loader import load_dataframe
from .result import CheckResult, RunResult


def run_checks(
    df: pd.DataFrame,
    checks: list[CheckConfig],
    *,
    dataset: str = "<dataframe>",
    now: datetime | None = None,
    fail_on_warn: bool = False,
) -> RunResult:
    """Run every check and collect results. One failing check never stops the others."""
    ctx = registry.CheckContext(now=_utc(now or datetime.now(timezone.utc)))
    results = [_run_one(df, check, ctx) for check in checks]
    return RunResult(dataset=dataset, row_count=len(df), results=results, fail_on_warn=fail_on_warn)


def run_config(config: Config, *, now: datetime | None = None, fail_on_warn: bool = False) -> RunResult:
    """Load the configured dataset and run its checks. Raises DataLoadError on load failure."""
    ds = config.dataset
    df = load_dataframe(ds.path, ds.format, ds.parse_dates)
    return run_checks(df, config.checks, dataset=str(config.dataset.path), now=now, fail_on_warn=fail_on_warn)


def _run_one(df: pd.DataFrame, check: CheckConfig, ctx: registry.CheckContext) -> CheckResult:
    spec = registry.get(check.type)
    try:
        outcome = spec.fn(df, check.params, ctx)
        passed, message, count, sample = outcome.passed, outcome.message, outcome.failed_count, outcome.sample
    except KeyError as exc:
        # Missing column: the data broke its contract. Fail closed.
        passed, message, count, sample = False, str(exc.args[0]) if exc.args else str(exc), 0, []
    except Exception as exc:  # noqa: BLE001 - a crashing check must not pass silently
        passed, message, count, sample = False, f"check raised {type(exc).__name__}: {exc}", 0, []
    return CheckResult(
        name=check.name,
        check_type=check.type,
        severity=check.severity,
        passed=passed,
        message=message,
        failed_count=count,
        sample=list(sample),
    )


def _utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
