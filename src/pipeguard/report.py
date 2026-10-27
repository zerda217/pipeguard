"""Render a RunResult as human-readable text or JSON."""

from __future__ import annotations

import json

from .result import RunResult

_LABEL = {"pass": "PASS", "fail": "FAIL", "warn": "WARN"}


def format_text(run: RunResult) -> str:
    lines = [f"pipeguard · {run.dataset} · {run.row_count:,} rows · {len(run.results)} checks", ""]
    width = max((len(r.name) for r in run.results), default=0)
    for r in run.results:
        line = f"  {_LABEL[r.status]}  {r.name:<{width}}  {r.message}"
        if not r.passed and r.sample:
            line += f"  sample={r.to_dict()['sample']}"
        lines.append(line)

    n_err, n_warn = len(run.errors), len(run.warnings)
    verdict = "PASSED" if run.passed else "FAILED"
    detail = f"{n_err} error(s), {n_warn} warning(s)"
    if run.fail_on_warn and n_warn:
        detail += ", warnings treated as errors"
    lines += ["", f"Result: {verdict} ({detail}) -> exit {run.exit_code}"]
    return "\n".join(lines)


def format_json(run: RunResult) -> str:
    return json.dumps(run.to_dict(), ensure_ascii=False, indent=2, default=str)
