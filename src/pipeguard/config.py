"""Load and validate a pipeguard YAML config.

Validation happens entirely here, before any data is read, so a typo in a rule
fails in milliseconds with exit code 2 instead of after a large file load.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from . import registry
from .checks import ParamError
from .result import Severity

SUPPORTED_VERSIONS = {1}
FORMATS = {"csv", "parquet", "jsonl"}
_RESERVED = {"name", "type", "severity", "description"}


class ConfigError(Exception):
    """The config file is missing, malformed or semantically invalid."""


@dataclass(frozen=True)
class CheckConfig:
    name: str
    type: str
    severity: Severity
    params: dict[str, Any] = field(default_factory=dict)
    description: str = ""


@dataclass(frozen=True)
class DatasetConfig:
    path: Path
    format: str
    parse_dates: tuple[str, ...] = ()


@dataclass(frozen=True)
class Config:
    dataset: DatasetConfig
    checks: list[CheckConfig]


def load_config(path: str | Path) -> Config:
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ConfigError(f"config file not found: {path}") from None
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {path}: {exc}") from None
    return parse_config(raw, base_dir=path.parent)


def parse_config(raw: Any, base_dir: Path = Path(".")) -> Config:
    if not isinstance(raw, dict):
        raise ConfigError("config must be a mapping with 'version', 'dataset' and 'checks'")

    version = raw.get("version", 1)
    if version not in SUPPORTED_VERSIONS:
        raise ConfigError(f"unsupported config version {version!r}")

    dataset = _parse_dataset(raw.get("dataset"), base_dir)

    checks_raw = raw.get("checks")
    if not isinstance(checks_raw, list) or not checks_raw:
        raise ConfigError("'checks' must be a non-empty list")

    checks = [_parse_check(item, i) for i, item in enumerate(checks_raw)]
    seen: set[str] = set()
    for check in checks:
        if check.name in seen:
            raise ConfigError(f"duplicate check name '{check.name}'")
        seen.add(check.name)
    return Config(dataset=dataset, checks=checks)


def _parse_dataset(raw: Any, base_dir: Path) -> DatasetConfig:
    if not isinstance(raw, dict) or not raw.get("path"):
        raise ConfigError("'dataset.path' is required")
    path = Path(raw["path"])
    if not path.is_absolute():
        path = base_dir / path
    fmt = raw.get("format") or infer_format(path)
    if fmt not in FORMATS:
        raise ConfigError(f"unsupported dataset format '{fmt}' (supported: {', '.join(sorted(FORMATS))})")
    parse_dates = raw.get("parse_dates", [])
    if not isinstance(parse_dates, list) or not all(isinstance(c, str) for c in parse_dates):
        raise ConfigError("'dataset.parse_dates' must be a list of column names")
    return DatasetConfig(path=path, format=fmt, parse_dates=tuple(parse_dates))


def infer_format(path: Path) -> str:
    suffix = path.suffix.lower().lstrip(".")
    return {"ndjson": "jsonl", "pq": "parquet"}.get(suffix, suffix)


def _parse_check(item: Any, index: int) -> CheckConfig:
    where = f"checks[{index}]"
    if not isinstance(item, dict):
        raise ConfigError(f"{where}: each check must be a mapping")

    check_type = item.get("type")
    if not check_type:
        raise ConfigError(f"{where}: 'type' is required")
    try:
        spec = registry.get(check_type)
    except registry.RegistryError as exc:
        raise ConfigError(f"{where}: {exc}") from None

    severity_raw = item.get("severity", "error")
    try:
        severity = Severity(severity_raw)
    except ValueError:
        raise ConfigError(f"{where}: severity must be 'error' or 'warn', got {severity_raw!r}") from None

    params = {k: v for k, v in item.items() if k not in _RESERVED}
    name = item.get("name") or _default_name(check_type, params, index)
    where = f"{where} ('{name}')"

    missing = [p for p in spec.required if p not in params]
    if missing:
        raise ConfigError(f"{where}: missing required parameter(s): {', '.join(missing)}")
    unknown = sorted(set(params) - spec.allowed)
    if unknown:
        raise ConfigError(f"{where}: unknown parameter(s): {', '.join(unknown)}")
    if spec.validate:
        try:
            spec.validate(params)
        except ParamError as exc:
            raise ConfigError(f"{where}: {exc}") from None

    return CheckConfig(
        name=str(name),
        type=check_type,
        severity=severity,
        params=params,
        description=str(item.get("description", "")),
    )


def _default_name(check_type: str, params: dict[str, Any], index: int) -> str:
    target = params.get("column") or params.get("columns")
    if isinstance(target, list):
        target = "+".join(map(str, target))
    return f"{check_type}:{target}" if target else f"{check_type}#{index}"
