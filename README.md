# TradeGuard

Open-source, self-hosted trading journal with an automated discipline engine. Import your broker executions; TradeGuard reconstructs round-trip trades (FIFO lot matching, partial fills, scale-in/out), computes performance stats, and audits every trade against your own written rules. Local-first — your data never leaves your machine.

**Status:** early development. Milestone 1 (data core: models, grouping engine, Webull + generic CSV importers, CLI) is complete. Rules engine, API, and web UI are coming next — see [SPEC.md](SPEC.md) for the roadmap.

## Quickstart

Requires Python 3.11+.

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"

# Import a Webull CSV export
python -m app.cli import my_orders.csv --broker webull

# Or any CSV with a custom column mapping
python -m app.cli import fills.csv --broker generic --mapping mapping.json
```

A generic `mapping.json` names your CSV's columns and time handling:

```json
{
  "symbol": "Ticker", "side": "Action", "qty": "Shares",
  "price": "FillPrice", "fees": "Commission", "executed_at": "When",
  "datetime_format": "%m/%d/%Y %H:%M:%S", "timezone": "America/New_York"
}
```

Imports are idempotent — re-importing the same file is safe. Fills land in a local SQLite database (`tradeguard.db`) and are grouped into trades automatically.

## Development

```bash
cd backend
pytest -q                      # tests
ruff check . && ruff format .  # lint/format
```

## License

[MIT](LICENSE)
