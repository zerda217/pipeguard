import json
from pathlib import Path

import pytest

from pipeguard.cli import main
from pipeguard.result import ExitCode

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
CONFIG = str(EXAMPLES / "orders.yaml")
AS_OF = ["--as-of", "2026-10-26T23:59:00+00:00"]


def test_good_data_passes(capsys):
    assert main(["run", CONFIG, *AS_OF]) == ExitCode.OK
    assert "Result: PASSED" in capsys.readouterr().out


def test_bad_data_blocks_and_reports(capsys, tmp_path):
    out_file = tmp_path / "report" / "result.json"
    code = main(["run", CONFIG, "--data", str(EXAMPLES / "orders_bad.csv"), "--json-out", str(out_file), *AS_OF])
    assert code == ExitCode.CHECK_FAILED

    report = json.loads(out_file.read_text(encoding="utf-8"))
    failed = {c["name"] for c in report["checks"] if c["status"] == "fail"}
    assert failed == {"order_id_unique", "amount_in_range", "known_country"}
    assert report["summary"]["warnings"] == 1
    assert "Result: FAILED" in capsys.readouterr().out


def test_stale_data_fails_freshness():
    assert main(["run", CONFIG, "--as-of", "2026-11-30T00:00:00+00:00"]) == ExitCode.CHECK_FAILED


def test_fail_on_warn(tmp_path):
    args = ["run", CONFIG, "--data", str(EXAMPLES / "orders_bad.csv"), "--fail-on-warn", *AS_OF]
    assert main(args) == ExitCode.CHECK_FAILED


def test_config_error_exit_code(tmp_path, capsys):
    bad = tmp_path / "bad.yaml"
    bad.write_text("version: 1\ndataset: {path: x.csv}\nchecks: [{type: nope}]\n", encoding="utf-8")
    assert main(["run", str(bad)]) == ExitCode.CONFIG_ERROR
    assert "config error" in capsys.readouterr().err


def test_data_error_exit_code(capsys):
    assert main(["run", CONFIG, "--data", "does/not/exist.csv"]) == ExitCode.DATA_ERROR
    assert "data error" in capsys.readouterr().err


def test_validate_command(capsys):
    assert main(["validate", CONFIG]) == ExitCode.OK
    assert "9 checks" in capsys.readouterr().out


def test_list_checks(capsys):
    assert main(["list-checks"]) == ExitCode.OK
    out = capsys.readouterr().out
    for name in ["not_null", "unique", "range", "allowed_values", "freshness", "row_count", "expression"]:
        assert name in out


def test_invalid_as_of_is_rejected():
    with pytest.raises(SystemExit):
        main(["run", CONFIG, "--as-of", "yesterday"])
