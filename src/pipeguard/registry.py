"""Plugin registry for checks.

A check is a plain function ``(df, params, ctx) -> CheckOutcome`` registered
under a type name. The registry also declares which parameters each check
accepts, so a config can be validated *before* any data is loaded.

Adding a check::

    from pipeguard.registry import register
    from pipeguard.result import CheckOutcome

    @register("positive", required=("column",))
    def positive(df, params, ctx):
        bad = df[params["column"]] <= 0
        return CheckOutcome(passed=not bad.any(), failed_count=int(bad.sum()))
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

import pandas as pd

from .result import CheckOutcome


@dataclass(frozen=True)
class CheckContext:
    """Run-level information a check may need. ``now`` makes time-based checks testable."""

    now: datetime


CheckFn = Callable[[pd.DataFrame, dict[str, Any], CheckContext], CheckOutcome]
Validator = Callable[[dict[str, Any]], None]


@dataclass(frozen=True)
class CheckSpec:
    name: str
    fn: CheckFn
    required: tuple[str, ...]
    optional: tuple[str, ...]
    validate: Validator | None
    description: str

    @property
    def allowed(self) -> set[str]:
        return set(self.required) | set(self.optional)


class RegistryError(Exception):
    pass


_REGISTRY: dict[str, CheckSpec] = {}


def register(
    name: str,
    *,
    required: tuple[str, ...] = (),
    optional: tuple[str, ...] = (),
    validate: Validator | None = None,
) -> Callable[[CheckFn], CheckFn]:
    """Register a check function under ``name``."""

    def decorator(fn: CheckFn) -> CheckFn:
        if name in _REGISTRY:
            raise RegistryError(f"check type '{name}' is already registered")
        doc = (fn.__doc__ or "").strip().splitlines()
        _REGISTRY[name] = CheckSpec(
            name=name,
            fn=fn,
            required=tuple(required),
            optional=tuple(optional),
            validate=validate,
            description=doc[0] if doc else "",
        )
        return fn

    return decorator


def unregister(name: str) -> None:
    """Remove a check type. Mainly for tests that register temporary checks."""
    _REGISTRY.pop(name, None)


def get(name: str) -> CheckSpec:
    try:
        return _REGISTRY[name]
    except KeyError:
        known = ", ".join(sorted(_REGISTRY))
        raise RegistryError(f"unknown check type '{name}' (available: {known})") from None


def available() -> list[CheckSpec]:
    return [_REGISTRY[k] for k in sorted(_REGISTRY)]
