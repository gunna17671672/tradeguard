# TradeGuard

Open-source, self-hosted trading journal with an automated discipline engine. Import your broker executions; TradeGuard reconstructs round-trip trades (FIFO lot matching, partial fills, scale-in/out), computes performance stats, and audits every trade against your own written rules. Local-first — your data never leaves your machine.

**Status:** early development. Milestone 1 (data core: models, grouping engine, Webull + generic CSV importers, CLI), Milestone 2 (discipline engine: six built-in rules configured via `rules.yaml` — see the [rules.example.yaml](rules.example.yaml) template — automatic audit on import, adherence score and weekly report data), and Milestone 3 (FastAPI routes + Next.js web UI: Dashboard, Trades, Discipline, Import, Settings) are complete. Packaging (Docker, CI) comes next — see [SPEC.md](SPEC.md) for the roadmap.

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

## Running the app (dev mode)

Two processes: the FastAPI backend on **:8000** and the Next.js frontend on **:3000**. Requires Node 20+.

```bash
# Terminal 1 — API (from backend/, with the venv active)
uvicorn app.main:app --reload

# Terminal 2 — web UI
cd frontend
npm install        # first time only
npm run dev
```

Open <http://localhost:3000>. The frontend talks to the API at `http://127.0.0.1:8000` (override with `NEXT_PUBLIC_API_URL`); the backend allows the dev origin via CORS.

The API resolves its SQLite database from `TRADEGUARD_DB` (default `tradeguard.db` in the working directory) and its rules from `TRADEGUARD_RULES` (default: the nearest `rules.yaml` walking up from the working directory — running from `backend/` finds the repo root's file). Interactive API docs live at <http://127.0.0.1:8000/docs>.

### Configuring your rules

Your discipline rules live in `rules.yaml` at the repo root. That file is **yours** — it holds your real account size and is rewritten when you save from the Settings page — so it is gitignored and never committed. The checked-in template is [rules.example.yaml](rules.example.yaml): on first run the API copies it to `rules.yaml` automatically if none exists, or copy it by hand and edit the params to match your plan.

You can import CSVs from the web UI (Import page) or the CLI; both audit against rules.yaml and are idempotent. Editing a trade's stop/target/tag/notes or saving rules from Settings re-audits automatically.

## Development

```bash
cd backend
pytest -q                      # tests
ruff check . && ruff format .  # lint/format

cd frontend
npm run build                  # type-checks and builds the UI
```

## License

[MIT](LICENSE)
