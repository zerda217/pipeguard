"""pipeguard: declarative data quality gate for batch pipelines."""

__version__ = "0.1.0"

from . import checks as _builtin_checks  # noqa: E402,F401  (registers built-in checks)
from .config import ConfigError, load_config, parse_config  # noqa: E402
from .registry import register  # noqa: E402
from .result import CheckOutcome, ExitCode, Severity  # noqa: E402
from .runner import run_checks, run_config  # noqa: E402

__all__ = [
    "CheckOutcome",
    "ConfigError",
    "ExitCode",
    "Severity",
    "load_config",
    "parse_config",
    "register",
    "run_checks",
    "run_config",
]
