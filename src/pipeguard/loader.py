"""Read a dataset into a DataFrame."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import pandas as pd


class DataLoadError(Exception):
    """The dataset file is missing or unreadable."""


def load_dataframe(path: Path, fmt: str, parse_dates: Sequence[str] = ()) -> pd.DataFrame:
    if not path.exists():
        raise DataLoadError(f"dataset not found: {path}")
    try:
        if fmt == "csv":
            df = pd.read_csv(path)
        elif fmt == "jsonl":
            df = pd.read_json(path, lines=True)
        elif fmt == "parquet":
            df = pd.read_parquet(path)
        else:
            raise DataLoadError(f"unsupported format '{fmt}'")
    except DataLoadError:
        raise
    except ImportError as exc:
        raise DataLoadError(f"{fmt} support needs an extra dependency: {exc}") from None
    except Exception as exc:  # noqa: BLE001 - any parse failure is a load failure
        raise DataLoadError(f"could not read {path} as {fmt}: {exc}") from None

    for col in parse_dates:
        # A missing date column is left for the checks to report, not a load failure.
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], utc=True, errors="coerce")
    return df
