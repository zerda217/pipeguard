"""Command line interface.

    pipeguard run CONFIG [--data PATH] [--json-out FILE] [--fail-on-warn]
    pipeguard validate CONFIG
    pipeguard list-checks
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Sequence

from . import __version__, registry
from .config import ConfigError, infer_format, load_config
from .loader import DataLoadError
from .report import format_json, format_text
from .result import ExitCode
from .runner import run_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pipeguard", description="Declarative data quality gate.")
    parser.add_argument("--version", action="version", version=f"pipeguard {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run checks and exit non-zero on error-level failures")
    run.add_argument("config", type=Path)
    run.add_argument("--data", type=Path, help="override dataset.path from the config")
    run.add_argument("--json-out", type=Path, help="also write the result as JSON to this file")
    run.add_argument("--fail-on-warn", action="store_true", help="treat warnings as failures")
    run.add_argument(
        "--as-of",
        type=_parse_as_of,
        help="reference time for freshness checks (ISO 8601, default: now). Use for backfills.",
    )

    validate = sub.add_parser("validate", help="validate a config without reading data")
    validate.add_argument("config", type=Path)

    sub.add_parser("list-checks", help="list available check types")
    return parser


def _parse_as_of(text: str) -> datetime:
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid ISO 8601 time: {text!r}") from None


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "list-checks":
        return _list_checks()
    if args.command == "validate":
        return _validate(args.config)
    return _run(args)


def _list_checks() -> int:
    for spec in registry.available():
        params = [*spec.required, *(f"[{p}]" for p in spec.optional)]
        print(f"{spec.name:<15} {' '.join(params):<28} {spec.description}")
    return ExitCode.OK


def _validate(path: Path) -> int:
    try:
        config = load_config(path)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return ExitCode.CONFIG_ERROR
    print(f"config OK: {len(config.checks)} checks for {config.dataset.path}")
    return ExitCode.OK


def _run(args: argparse.Namespace) -> int:
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return ExitCode.CONFIG_ERROR

    if args.data:
        dataset = replace(config.dataset, path=args.data, format=infer_format(args.data))
        config = replace(config, dataset=dataset)

    try:
        run = run_config(config, now=args.as_of, fail_on_warn=args.fail_on_warn)
    except DataLoadError as exc:
        print(f"data error: {exc}", file=sys.stderr)
        return ExitCode.DATA_ERROR

    print(format_text(run))
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(format_json(run), encoding="utf-8")
    return run.exit_code
