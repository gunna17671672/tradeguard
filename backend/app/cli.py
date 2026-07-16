"""Command-line interface.

    python -m app.cli import fills.csv --broker webull
    python -m app.cli import fills.csv --broker generic --mapping mapping.json

A generic-importer mapping.json may contain: symbol, side, qty, price,
executed_at, fees, account_label (CSV column names), plus optional
datetime_format (strptime) and timezone (IANA name, default UTC).

Imports are audited against rules.yaml automatically: pass --rules, or let the
CLI discover the file by walking up from the current directory.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.db import default_db_path, init_db, make_engine, make_session_factory, session_scope
from app.importers import available_brokers, get_importer, mapping_kwargs_from_config
from app.importers.base import ImporterError
from app.ingest import import_fills
from app.rules import RuleConfigError
from app.rules.loader import RulesConfig, find_rules_file, load_rules_config


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tradeguard", description="TradeGuard CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    imp = sub.add_parser("import", help="Import a broker CSV of executions")
    imp.add_argument("file", type=Path, help="Path to the CSV file")
    imp.add_argument("--broker", required=True, choices=available_brokers())
    imp.add_argument(
        "--mapping",
        type=Path,
        default=None,
        help="JSON column-mapping file (generic importer only)",
    )
    default_db = default_db_path()
    imp.add_argument(
        "--db", type=Path, default=default_db, help=f"SQLite path (default {default_db})"
    )
    imp.add_argument(
        "--rules",
        type=Path,
        default=None,
        help="rules.yaml for the discipline audit (default: nearest rules.yaml above the cwd)",
    )
    return parser


def _importer_kwargs(args: argparse.Namespace) -> dict[str, object]:
    if args.mapping is None:
        return {}
    if args.broker != "generic":
        raise ImporterError("--mapping is only supported with --broker generic")
    config = json.loads(args.mapping.read_text(encoding="utf-8"))
    return mapping_kwargs_from_config(config)


def _load_rules(args: argparse.Namespace) -> RulesConfig | None:
    path = args.rules if args.rules is not None else find_rules_file()
    if path is None:
        print("note: no rules.yaml found; skipping the discipline audit")
        return None
    return load_rules_config(path)


def cmd_import(args: argparse.Namespace) -> int:
    if not args.file.exists():
        print(f"error: file not found: {args.file}", file=sys.stderr)
        return 2
    try:
        rules_config = _load_rules(args)
        importer = get_importer(args.broker, **_importer_kwargs(args))
        fills = importer.parse(args.file)
    except (ImporterError, RuleConfigError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    engine = make_engine(args.db)
    init_db(engine)
    factory = make_session_factory(engine)
    with session_scope(factory) as session:
        result = import_fills(
            session, fills, broker=args.broker, filename=args.file.name, rules_config=rules_config
        )

    audit_note = (
        f"recorded {result.violations_recorded} rule violation(s)"
        if rules_config is not None
        else "audit skipped"
    )
    unfilled_note = (
        f", {importer.skipped_unfilled} unfilled order row(s) skipped"
        if importer.skipped_unfilled
        else ""
    )
    print(
        f"Imported {result.inserted} fill(s) from {args.file.name} "
        f"({result.skipped_duplicates} duplicate(s) skipped{unfilled_note}); "
        f"rebuilt {result.trades_rebuilt} trade(s); {audit_note}. Batch #{result.batch_id}."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "import":
        return cmd_import(args)
    return 2  # pragma: no cover — argparse enforces the subcommand


if __name__ == "__main__":
    raise SystemExit(main())
