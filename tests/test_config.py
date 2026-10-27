from pathlib import Path

import pytest

from pipeguard.config import ConfigError, load_config, parse_config
from pipeguard.result import Severity


def cfg(*checks, dataset=None, **extra):
    raw = {"version": 1, "dataset": dataset or {"path": "data.csv"}, "checks": list(checks)}
    raw.update(extra)
    return raw


def test_minimal_config_defaults():
    config = parse_config(cfg({"type": "not_null", "column": "id"}), base_dir=Path("/base"))
    check = config.checks[0]
    assert check.name == "not_null:id"
    assert check.severity is Severity.ERROR
    assert check.params == {"column": "id"}
    assert config.dataset.path == Path("/base/data.csv")
    assert config.dataset.format == "csv"


def test_default_name_for_composite_and_columnless_checks():
    config = parse_config(cfg({"type": "unique", "columns": ["a", "b"]}, {"type": "row_count", "min": 1}))
    assert [c.name for c in config.checks] == ["unique:a+b", "row_count#1"]


@pytest.mark.parametrize("path,fmt", [("x.parquet", "parquet"), ("x.ndjson", "jsonl"), ("x.jsonl", "jsonl")])
def test_format_inferred_from_extension(path, fmt):
    config = parse_config(cfg({"type": "row_count", "min": 1}, dataset={"path": path}))
    assert config.dataset.format == fmt


def test_parse_dates_is_read():
    config = parse_config(cfg({"type": "row_count", "min": 1}, dataset={"path": "d.csv", "parse_dates": ["ts"]}))
    assert config.dataset.parse_dates == ("ts",)


@pytest.mark.parametrize(
    "raw,match",
    [
        (None, "mapping"),
        (cfg({"type": "row_count", "min": 1}, version=2), "version"),
        ({"version": 1, "checks": [{"type": "row_count", "min": 1}]}, "dataset.path"),
        (cfg({"type": "row_count", "min": 1}, dataset={"path": "x.xlsx"}), "unsupported dataset format"),
        (cfg(dataset={"path": "d.csv"}), "non-empty list"),
        (cfg("not_null"), "must be a mapping"),
        (cfg({"column": "a"}), "'type' is required"),
        (cfg({"type": "no_such_check"}), "unknown check type"),
        (cfg({"type": "not_null", "column": "a", "severity": "fatal"}), "severity"),
        (cfg({"type": "not_null"}), "missing required parameter"),
        (cfg({"type": "not_null", "column": "a", "colum": "b"}), "unknown parameter"),
        (cfg({"type": "freshness", "column": "ts", "max_age": "soon"}), "invalid duration"),
        (cfg({"type": "row_count", "min": 1, "name": "x"}, {"type": "row_count", "max": 9, "name": "x"}), "duplicate"),
    ],
)
def test_invalid_configs(raw, match):
    with pytest.raises(ConfigError, match=match):
        parse_config(raw)


def test_error_message_points_to_the_check():
    with pytest.raises(ConfigError, match=r"checks\[1\] \('amount_ok'\)"):
        parse_config(cfg({"type": "row_count", "min": 1}, {"type": "range", "column": "a", "name": "amount_ok"}))


def test_load_config_missing_file(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nope.yaml")


def test_load_config_invalid_yaml(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("checks: [unclosed", encoding="utf-8")
    with pytest.raises(ConfigError, match="invalid YAML"):
        load_config(path)


def test_example_config_is_valid():
    root = Path(__file__).resolve().parents[1]
    config = load_config(root / "examples" / "orders.yaml")
    assert len(config.checks) == 9
    assert config.dataset.path == root / "examples" / "orders.csv"
