from datetime import datetime, timezone

import pandas as pd

from pipeguard.config import CheckConfig
from pipeguard.registry import CheckContext, get
from pipeguard.result import Severity

NOW = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
CTX = CheckContext(now=NOW)


def run(check_type: str, df: pd.DataFrame, **params):
    """Call a registered check function directly."""
    return get(check_type).fn(df, params, CTX)


def check(check_type: str, name: str | None = None, severity: str = "error", **params) -> CheckConfig:
    return CheckConfig(name=name or check_type, type=check_type, severity=Severity(severity), params=params)
