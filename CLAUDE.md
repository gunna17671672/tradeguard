# CLAUDE.md — TradeGuard

## What this is
Self-hosted trading journal + automated discipline engine. The full product spec lives in **SPEC.md — read it before any structural change.** Work only on the current milestone (see SPEC.md); do not build ahead without being asked.

## Commands
- Setup (Windows): `cd backend` → `python -m venv .venv` → `.venv\Scripts\activate` → `pip install -e ".[dev]"`
- Tests: `pytest -q` from `backend/` — **must be green before any commit**
- Lint/format: `ruff check . && ruff format .`
- Run API: `uvicorn app.main:app --reload` from `backend/`
- Frontend (M3+): `cd frontend && npm run dev`

## Code style
- Python 3.11+, full type hints everywhere, Pydantic v2 at API boundaries
- **Money is `Decimal` (serialize as string), never float.** Timestamps stored UTC; market-session logic in `America/New_York` via `zoneinfo`
- Parsing, grouping, and rule logic are small pure functions; DB access stays in a thin layer
- Tests are pytest, table-driven where natural; fixtures are synthetic — never real broker exports
- Cross-platform code only (pathlib, no bash-isms in scripts) — dev machine is Windows

## Git
- Atomic commits per logical step, imperative messages ("Add FIFO lot matching")
- Run tests before every commit; never commit failing code
- Never commit: real broker exports, `.env`, `*.db` / SQLite files, `.venv`, `node_modules`, `rules.yaml` (the user's live config with their real account size — the committed template is `rules.example.yaml`)

## Hard rules
- No dependencies beyond the SPEC.md stack without asking first
- No credentials, tokens, or API keys in code, config, or commits — ever
- If Webull CSV columns are ambiguous, ask for a sample header row instead of guessing silently
- If a requirement in SPEC.md seems wrong or underspecified, say so and ask — don't invent
