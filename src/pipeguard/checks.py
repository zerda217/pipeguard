"""Built-in checks.

Conventions shared by every check:
- Nulls are ignored by value checks (range, allowed_values). Use ``not_null``
  to police nulls explicitly, so one problem is reported by one check.
- ``failed_count`` counts offending rows; ``sample`` holds at most
  ``SAMPLE_SIZE`` offending values for debugging.
- A referenced column that does not exist raises ``KeyError``; the runner
  turns any exception into a failed result (fail closed).
"""

from __future__ import annotations

import re
from datetime import timedelta
from typing import Any

import pandas as pd

from .registry import CheckContext, register
from .result import CheckOutcome

SAMPLE_SIZE = 5

_DURATION = re.compile(r"^\s*(\d+)\s*([smhd])\s*$")
_UNITS = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}


class ParamError(ValueError):
    """Raised by validators when check parameters are invalid."""


# ---------------------------------------------------------------- helpers


def _column(df: pd.DataFrame, name: str) -> pd.Series:
    if name not in df.columns:
        raise KeyError(f"column '{name}' not found in dataset")
    return df[name]


def _sample(values: pd.Series) -> list[Any]:
    return values.head(SAMPLE_SIZE).tolist()


def parse_duration(text: str) -> timedelta:
    """Parse '30m', '24h', '7d' style durations."""
    match = _DURATION.match(str(text))
    if not match:
        raise ParamError(f"invalid duration '{text}' (expected e.g. 30m, 24h, 7d)")
    amount, unit = match.groups()
    return timedelta(**{_UNITS[unit]: int(amount)})


def _require_min_or_max(params: dict[str, Any]) -> None:
    if params.get("min") is None and params.get("max") is None:
        raise ParamError("at least one of 'min' or 'max' is required")
    lo, hi = params.get("min"), params.get("max")
    for key, value in (("min", lo), ("max", hi)):
        if value is not None and not isinstance(value, (int, float)):
            raise ParamError(f"'{key}' must be a number, got {value!r}")
    if lo is not None and hi is not None and lo > hi:
        raise ParamError(f"'min' ({lo}) is greater than 'max' ({hi})")


def _columns_param(params: dict[str, Any]) -> list[str]:
    cols = params["columns"]
    return [cols] if isinstance(cols, str) else list(cols)


# ----------------------------------------------------------------- checks


def _validate_not_null(params: dict[str, Any]) -> None:
    ratio = params.get("max_ratio", 0)
    if not isinstance(ratio, (int, float)) or not 0 <= ratio <= 1:
        raise ParamError(f"'max_ratio' must be between 0 and 1, got {ratio!r}")


@register("not_null", required=("column",), optional=("max_ratio",), validate=_validate_not_null)
def not_null(df: pd.DataFrame, params: dict[str, Any], ctx: CheckContext) -> CheckOutcome:
    """Null ratio of a column must not exceed max_ratio (default 0)."""
    col = _column(df, params["column"])
    nulls = int(col.isna().sum())
    ratio = nulls / len(col) if len(col) else 0.0
    max_ratio = params.get("max_ratio", 0)
    passed = ratio <= max_ratio
    message = f"{nulls} nulls ({ratio:.2%}), allowed {max_ratio:.2%}"
    return CheckOutcome(passed=passed, message=message, failed_count=0 if passed else nulls)


def _validate_unique(params: dict[str, Any]) -> None:
    cols = params["columns"]
    if isinstance(cols, str):
        return
    if not isinstance(cols, list) or not cols or not all(isinstance(c, str) for c in cols):
        raise ParamError("'columns' must be a column name or a non-empty list of names")


@register("unique", required=("columns",), validate=_validate_unique)
def unique(df: pd.DataFrame, params: dict[str, Any], ctx: CheckContext) -> CheckOutcome:
    """Rows must be unique over the given column(s)."""
    cols = _columns_param(params)
    for c in cols:
        _column(df, c)
    extra = df.duplicated(subset=cols, keep="first")
    count = int(extra.sum())
    dup_keys = df.loc[extra, cols].drop_duplicates()
    sample = (
        dup_keys[cols[0]] if len(cols) == 1 else dup_keys.apply(tuple, axis=1)
    )
    return CheckOutcome(
        passed=count == 0,
        message=f"{count} duplicate rows on {', '.join(cols)}",
        failed_count=count,
        sample=_sample(sample),
    )


@register("range", required=("column",), optional=("min", "max"), validate=_require_min_or_max)
def value_range(df: pd.DataFrame, params: dict[str, Any], ctx: CheckContext) -> CheckOutcome:
    """Non-null values must lie within [min, max] (inclusive)."""
    raw = _column(df, params["column"]).dropna()
    values = pd.to_numeric(raw, errors="coerce")
    non_numeric = values.isna()
    lo, hi = params.get("min"), params.get("max")
    bad = non_numeric.copy()
    if lo is not None:
        bad |= values < lo
    if hi is not None:
        bad |= values > hi
    count = int(bad.sum())
    bounds = f"[{'-inf' if lo is None else lo}, {'inf' if hi is None else hi}]"
    message = f"{count} values outside {bounds}"
    if non_numeric.any():
        message += f" ({int(non_numeric.sum())} non-numeric)"
    return CheckOutcome(passed=count == 0, message=message, failed_count=count, sample=_sample(raw[bad]))


def _validate_allowed(params: dict[str, Any]) -> None:
    values = params["values"]
    if not isinstance(values, list) or not values:
        raise ParamError("'values' must be a non-empty list")


@register("allowed_values", required=("column", "values"), validate=_validate_allowed)
def allowed_values(df: pd.DataFrame, params: dict[str, Any], ctx: CheckContext) -> CheckOutcome:
    """Non-null values must be one of the listed values."""
    col = _column(df, params["column"]).dropna()
    allowed = set(params["values"])
    bad = ~col.isin(allowed)
    count = int(bad.sum())
    unexpected = col[bad].drop_duplicates()
    return CheckOutcome(
        passed=count == 0,
        message=f"{count} values not in allowed set ({len(unexpected)} distinct)",
        failed_count=count,
        sample=_sample(unexpected),
    )


def _validate_freshness(params: dict[str, Any]) -> None:
    parse_duration(params["max_age"])


@register("freshness", required=("column", "max_age"), validate=_validate_freshness)
def freshness(df: pd.DataFrame, params: dict[str, Any], ctx: CheckContext) -> CheckOutcome:
    """The latest timestamp in a column must be newer than now - max_age."""
    col = _column(df, params["column"])
    max_age = parse_duration(params["max_age"])
    stamps = pd.to_datetime(col, utc=True, errors="coerce").dropna()
    if stamps.empty:
        return CheckOutcome(passed=False, message="no parseable timestamps")
    latest = stamps.max()
    age = pd.Timestamp(ctx.now) - latest
    passed = age <= max_age
    hours = age.total_seconds() / 3600
    message = f"latest {latest.isoformat()} is {hours:.1f}h old, allowed {params['max_age']}"
    return CheckOutcome(passed=passed, message=message, sample=[] if passed else [latest])


@register("row_count", optional=("min", "max"), validate=_require_min_or_max)
def row_count(df: pd.DataFrame, params: dict[str, Any], ctx: CheckContext) -> CheckOutcome:
    """Number of rows must lie within [min, max]."""
    n = len(df)
    lo, hi = params.get("min"), params.get("max")
    passed = (lo is None or n >= lo) and (hi is None or n <= hi)
    bounds = f"[{lo if lo is not None else 0}, {hi if hi is not None else 'inf'}]"
    return CheckOutcome(passed=passed, message=f"{n} rows, expected {bounds}")


def _validate_expression(params: dict[str, Any]) -> None:
    expr = params["expr"]
    if not isinstance(expr, str) or not expr.strip():
        raise ParamError("'expr' must be a non-empty string")


@register("expression", required=("expr",), validate=_validate_expression)
def expression(df: pd.DataFrame, params: dict[str, Any], ctx: CheckContext) -> CheckOutcome:
    """Every row must satisfy a pandas boolean expression, e.g. 'shipped_at >= ordered_at'."""
    expr = params["expr"]
    result = df.eval(expr)
    if not isinstance(result, pd.Series) or result.dtype != bool:
        raise TypeError(f"expression '{expr}' must evaluate to a boolean per row")
    bad = ~result
    count = int(bad.sum())
    return CheckOutcome(
        passed=count == 0,
        message=f"{count} rows violate '{expr}'",
        failed_count=count,
        sample=[f"row {i}" for i in df.index[bad][:SAMPLE_SIZE]],
    )
