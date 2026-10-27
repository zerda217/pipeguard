import pandas as pd
import pytest

from pipeguard.loader import DataLoadError, load_dataframe


def test_csv_with_parse_dates(tmp_path):
    path = tmp_path / "d.csv"
    path.write_text("id,ts\n1,2026-10-27T00:00:00+00:00\n2,garbage\n", encoding="utf-8")
    df = load_dataframe(path, "csv", parse_dates=["ts", "not_a_column"])
    assert pd.api.types.is_datetime64_any_dtype(df["ts"])
    assert df["ts"].isna().sum() == 1  # unparseable value becomes NaT, checks decide what that means


def test_jsonl(tmp_path):
    path = tmp_path / "d.jsonl"
    path.write_text('{"id": 1}\n{"id": 2}\n', encoding="utf-8")
    assert load_dataframe(path, "jsonl")["id"].tolist() == [1, 2]


def test_missing_file(tmp_path):
    with pytest.raises(DataLoadError, match="not found"):
        load_dataframe(tmp_path / "nope.csv", "csv")


def test_unreadable_file(tmp_path):
    path = tmp_path / "d.jsonl"
    path.write_text("{not json\n", encoding="utf-8")
    with pytest.raises(DataLoadError, match="could not read"):
        load_dataframe(path, "jsonl")


def test_unsupported_format(tmp_path):
    path = tmp_path / "d.xlsx"
    path.write_text("x", encoding="utf-8")
    with pytest.raises(DataLoadError, match="unsupported"):
        load_dataframe(path, "xlsx")
