from datetime import timedelta

import pandas as pd
import pytest

from pipeguard.checks import ParamError, parse_duration
from pipeguard.registry import get
from helpers import NOW, run


# ------------------------------------------------------------- not_null


def test_not_null_passes_without_nulls():
    out = run("not_null", pd.DataFrame({"a": [1, 2, 3]}), column="a")
    assert out.passed


def test_not_null_fails_and_counts_nulls():
    out = run("not_null", pd.DataFrame({"a": [1, None, None]}), column="a")
    assert not out.passed
    assert out.failed_count == 2


def test_not_null_respects_max_ratio():
    df = pd.DataFrame({"a": [1, None, 3, 4]})  # 25% null
    assert run("not_null", df, column="a", max_ratio=0.25).passed
    assert not run("not_null", df, column="a", max_ratio=0.2).passed


def test_not_null_on_empty_frame_passes():
    assert run("not_null", pd.DataFrame({"a": []}), column="a").passed


@pytest.mark.parametrize("ratio", [-0.1, 1.5, "10%"])
def test_not_null_rejects_bad_ratio(ratio):
    with pytest.raises(ParamError):
        get("not_null").validate({"column": "a", "max_ratio": ratio})


# --------------------------------------------------------------- unique


def test_unique_passes():
    assert run("unique", pd.DataFrame({"id": [1, 2, 3]}), columns="id").passed


def test_unique_counts_extra_rows_only():
    out = run("unique", pd.DataFrame({"id": [1, 1, 1, 2]}), columns="id")
    assert not out.passed
    assert out.failed_count == 2  # first occurrence is not counted
    assert out.sample == [1]


def test_unique_composite_key():
    df = pd.DataFrame({"d": ["x", "x", "y"], "c": ["KR", "US", "KR"]})
    assert run("unique", df, columns=["d", "c"]).passed
    assert not run("unique", df, columns=["d"]).passed


def test_unique_composite_sample_is_tuple():
    df = pd.DataFrame({"d": ["x", "x"], "c": ["KR", "KR"]})
    assert run("unique", df, columns=["d", "c"]).sample == [("x", "KR")]


@pytest.mark.parametrize("cols", [[], [1], {"a": 1}])
def test_unique_rejects_bad_columns(cols):
    with pytest.raises(ParamError):
        get("unique").validate({"columns": cols})


# ---------------------------------------------------------------- range


def test_range_inclusive_bounds():
    assert run("range", pd.DataFrame({"v": [0, 5, 10]}), column="v", min=0, max=10).passed


def test_range_detects_both_sides():
    out = run("range", pd.DataFrame({"v": [-1, 5, 11]}), column="v", min=0, max=10)
    assert out.failed_count == 2
    assert sorted(out.sample) == [-1, 11]


def test_range_min_only():
    assert not run("range", pd.DataFrame({"v": [-1, 1e9]}), column="v", min=0).passed


def test_range_ignores_nulls():
    assert run("range", pd.DataFrame({"v": [1, None]}), column="v", min=0).passed


def test_range_flags_non_numeric_values():
    out = run("range", pd.DataFrame({"v": ["1", "abc"]}), column="v", min=0)
    assert not out.passed
    assert "non-numeric" in out.message


@pytest.mark.parametrize(
    "params",
    [{"column": "v"}, {"column": "v", "min": 5, "max": 1}, {"column": "v", "min": "0"}],
)
def test_range_rejects_bad_params(params):
    with pytest.raises(ParamError):
        get("range").validate(params)


# ------------------------------------------------------- allowed_values


def test_allowed_values_pass_and_fail():
    df = pd.DataFrame({"c": ["KR", "US", "XX", "XX", None]})
    assert run("allowed_values", df, column="c", values=["KR", "US", "XX"]).passed
    out = run("allowed_values", df, column="c", values=["KR", "US"])
    assert out.failed_count == 2
    assert out.sample == ["XX"]  # distinct offending values


def test_allowed_values_requires_list():
    with pytest.raises(ParamError):
        get("allowed_values").validate({"column": "c", "values": "KR"})


# ------------------------------------------------------------ freshness


@pytest.mark.parametrize(
    "text,expected",
    [("30m", timedelta(minutes=30)), ("24h", timedelta(hours=24)), ("7d", timedelta(days=7)), (" 5 s ", timedelta(seconds=5))],
)
def test_parse_duration(text, expected):
    assert parse_duration(text) == expected


@pytest.mark.parametrize("text", ["24", "1w", "h", "-1h"])
def test_parse_duration_rejects(text):
    with pytest.raises(ParamError):
        parse_duration(text)


def test_freshness_pass_and_fail():
    df = pd.DataFrame({"ts": [(NOW - timedelta(hours=30)).isoformat(), (NOW - timedelta(hours=2)).isoformat()]})
    assert run("freshness", df, column="ts", max_age="3h").passed
    assert not run("freshness", df, column="ts", max_age="1h").passed


def test_freshness_fails_without_timestamps():
    out = run("freshness", pd.DataFrame({"ts": [None, "not a date"]}), column="ts", max_age="1d")
    assert not out.passed


# ------------------------------------------------------------ row_count


@pytest.mark.parametrize("n,lo,hi,ok", [(5, 1, 10, True), (0, 1, None, False), (11, None, 10, False), (10, 10, 10, True)])
def test_row_count(n, lo, hi, ok):
    params = {k: v for k, v in (("min", lo), ("max", hi)) if v is not None}
    assert run("row_count", pd.DataFrame({"a": range(n)}), **params).passed is ok


# ----------------------------------------------------------- expression


def test_expression_counts_violations():
    df = pd.DataFrame({"start": [1, 5, 3], "end": [2, 4, 3]})
    out = run("expression", df, expr="end >= start")
    assert out.failed_count == 1
    assert out.sample == ["row 1"]


def test_expression_must_be_boolean():
    with pytest.raises(TypeError):
        run("expression", pd.DataFrame({"a": [1]}), expr="a + 1")


# --------------------------------------------------------- missing col


@pytest.mark.parametrize(
    "check_type,params",
    [
        ("not_null", {"column": "missing"}),
        ("unique", {"columns": "missing"}),
        ("range", {"column": "missing", "min": 0}),
        ("allowed_values", {"column": "missing", "values": [1]}),
        ("freshness", {"column": "missing", "max_age": "1h"}),
    ],
)
def test_missing_column_raises_key_error(check_type, params):
    with pytest.raises(KeyError, match="missing"):
        run(check_type, pd.DataFrame({"a": [1]}), **params)
