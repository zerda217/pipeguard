from datetime import datetime

import pandas as pd
import pytest

from pipeguard import CheckOutcome, ExitCode, register, run_checks
from pipeguard.registry import RegistryError, available, unregister
from helpers import check

DF = pd.DataFrame({"id": [1, 2, 2], "amount": [10, -5, 20]})


def test_all_pass_exits_zero():
    run = run_checks(DF, [check("row_count", min=1)])
    assert run.passed and run.exit_code == ExitCode.OK


def test_error_failure_blocks_the_gate():
    run = run_checks(DF, [check("unique", columns="id")])
    assert not run.passed
    assert run.exit_code == ExitCode.CHECK_FAILED
    assert [r.status for r in run.results] == ["fail"]


def test_warning_does_not_block_by_default():
    run = run_checks(DF, [check("range", severity="warn", column="amount", min=0)])
    assert run.passed
    assert len(run.warnings) == 1 and not run.errors


def test_fail_on_warn_blocks_on_warnings():
    run = run_checks(DF, [check("range", severity="warn", column="amount", min=0)], fail_on_warn=True)
    assert run.exit_code == ExitCode.CHECK_FAILED


def test_every_check_runs_even_after_a_failure():
    run = run_checks(DF, [check("unique", columns="id"), check("row_count", min=1)])
    assert [r.status for r in run.results] == ["fail", "pass"]


def test_missing_column_fails_closed():
    run = run_checks(DF, [check("not_null", column="nope")])
    assert not run.passed
    assert "not found" in run.results[0].message


def test_crashing_check_fails_closed():
    run = run_checks(DF, [check("expression", expr="amount + 1")])
    assert not run.passed
    assert run.results[0].message.startswith("check raised TypeError")


def test_naive_now_is_treated_as_utc():
    df = pd.DataFrame({"ts": ["2026-10-27T11:00:00+00:00"]})
    run = run_checks(df, [check("freshness", column="ts", max_age="2h")], now=datetime(2026, 10, 27, 12, 0))
    assert run.passed


def test_summary_dict():
    run = run_checks(DF, [check("unique", columns="id"), check("row_count", min=1)])
    summary = run.to_dict()["summary"]
    assert summary == {"total": 2, "passed": 1, "errors": 1, "warnings": 0}


def test_custom_check_plugin():
    @register("even_rows")
    def even_rows(df, params, ctx):
        """Row count must be even."""
        return CheckOutcome(passed=len(df) % 2 == 0, message=f"{len(df)} rows")

    try:
        assert "even_rows" in [s.name for s in available()]
        assert not run_checks(DF, [check("even_rows")]).passed
        with pytest.raises(RegistryError, match="already registered"):
            register("even_rows")(even_rows)
    finally:
        unregister("even_rows")
