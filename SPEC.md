# TradeGuard — Product Spec v0.1

Open-source, self-hosted trading journal with an **automated discipline engine**. Traders import their broker executions; TradeGuard reconstructs trades, computes performance stats, and — the differentiator — audits every trade against the trader's own written rules and reports violations. Local-first: data never leaves the machine.

## Goals / Non-goals

**Goals (v0):** one-command run, privacy (no cloud), deterministic rule auditing, dead-simple broker import, easy to add new importers.

**Non-goals (v0):** live order blocking, options analytics/greeks, multi-user auth, mobile app, cloud sync. Single-user localhost tool.

## Stack

- **Backend:** Python 3.11+, FastAPI, SQLAlchemy 2.0, Pydantic v2, SQLite (file DB), pandas for CSV parsing
- **Frontend:** Next.js + TypeScript + Tailwind (static export, served by FastAPI in production)
- **Tests:** pytest
- **Packaging:** single Dockerfile → `docker run -p 8080:8080 -v tradeguard_data:/data tradeguard`
- **License:** MIT

## Repo layout

```
tradeguard/
  backend/
    app/
      main.py
      db.py
      models.py          # SQLAlchemy models
      schemas.py         # Pydantic schemas
      importers/         # base.py + one module per broker
      grouping.py        # fills -> trades engine
      rules/             # engine.py, builtin.py, loader.py
      api/               # routers: trades, imports, stats, rules, reports
      cli.py             # python -m app.cli import file.csv --broker webull
    tests/
      fixtures/          # synthetic CSVs only — never real account data
    pyproject.toml
  frontend/              # created in M3
  rules.yaml             # user-edited rule config
  CLAUDE.md
  SPEC.md
```

## Core domain

### Executions (fills)
Raw broker rows, one record per fill: `broker, account_label, symbol, asset_type (stock only in v0), side (buy/sell), qty, price, fees, executed_at (UTC), raw_row_json, import_batch_id`.

**Money is Decimal, never float.** Timestamps stored in UTC; market-session logic evaluated in `America/New_York`.

### Trades (round trips)
Built by the grouping engine: per symbol (per account), track net position; a trade **opens** when position leaves 0 and **closes** when it returns to 0. Must handle partial entries/exits (scaling in/out). PnL attribution via **FIFO lot matching**.

Derived fields: direction (long/short), max qty, avg entry, avg exit, open/close times, gross/net PnL, total fees, hold time, fill count. User-annotated fields (editable later via API/UI): `planned_stop, planned_target, setup_tag, notes`. When `planned_stop` exists, compute `r_multiple = pnl / (risk_per_share × size)`.

Positions not yet back to 0 are stored as open trades and excluded from most stats.

### Rules engine
- `rules.yaml` holds account settings (`account_size`, timezone) and enabled rules + params.
- Each built-in rule is a class implementing `evaluate(trade, ctx) -> list[Violation]`. `ctx` exposes that day's trades, the previous closed trade, and account settings. Registry pattern so new rules are one file.
- Violations persisted: `trade_id, rule_id, severity (info|warn|violation), message`.

**Built-in rules for v1:**
1. `max_trades_per_day(n)`
2. `stop_required(within_minutes)` — planned_stop must be set on the trade
3. `max_risk_per_trade(pct_of_account)` — requires planned_stop
4. `blocked_entry_window(start, end)` — e.g. no entries 09:30–09:35 ET
5. `revenge_trade(cooldown_minutes, size_multiplier)` — entry within N minutes after a losing close at size ≥ multiplier × the losing trade's size
6. `max_daily_loss(amount_or_R)` — flags every trade entered after the daily breach

**Adherence score:** % of closed trades with zero violations (weekly), plus current violation-free streak in days.

### Stats
Win rate, profit factor, avg win / avg loss, expectancy, net PnL, cumulative equity curve, PnL calendar heatmap, breakdowns by symbol / weekday / hour-of-day / setup_tag, R-multiple distribution when stops are recorded.

## Importers

Design: `BaseImporter.parse(file) -> list[NormalizedFill]`. Importers are **pure functions with no DB access**, mapping-driven (column-name config dict) so a new broker is ~50 lines.

- **v1: Webull CSV export** (US stocks). Column names vary by app version — do NOT hardcode blindly; map via config and **fail loudly** with an error listing found vs. expected columns. If ambiguous, ask the user for a sample header row.
- **v1: Generic CSV importer** with user-supplied column mapping as fallback.
- **Idempotent imports:** dedup fills on a hash of `(broker, symbol, executed_at, side, qty, price)` so re-importing the same file is safe.
- All test fixtures are synthetic.
- Later (M5): extract importers into a standalone pip package `broker-parse` — keep them dependency-light and DB-free now so extraction is painless.

## API (M3)

```
POST  /api/imports                     multipart file + broker → batch summary
GET   /api/trades                      filters: date range, symbol, tag, has_violations; paginated
GET   /api/trades/{id}
PATCH /api/trades/{id}                 planned_stop, planned_target, setup_tag, notes
GET   /api/stats/summary?from=&to=
GET   /api/stats/equity
GET   /api/stats/calendar
GET   /api/violations
GET   /api/reports/weekly?week=
GET   /api/rules        PUT /api/rules  (validates then writes rules.yaml)
```

## Frontend (M3–M4)

Pages: **Dashboard** (equity curve, this week's adherence score, recent violations), **Trades** (filterable table), **Trade detail** (fills timeline, violations, edit stop/tag/notes), **Discipline** (violations feed, streaks, weekly report), **Import** (drag-drop CSV), **Settings** (form-based rules.yaml editor). Dark, minimal, fast. No auth in v0.

## Milestones

- **M1 — Data core:** scaffold, models, grouping engine (FIFO, partial fills), Webull + generic importers, CLI import command, pytest green. *Done when:* a synthetic ~40-fill CSV imports into the correct trade count and PnL, with partial-fill and scale-out cases proven by tests.
- **M2 — Discipline:** rules engine, 6 built-ins, rules.yaml loader, violations persistence, weekly report data, adherence score. Every rule gets tests proving it fires AND doesn't overfire.
- **M3 — Surface:** FastAPI routes + Next.js Dashboard/Trades/Discipline pages.
- **M4 — Ship:** Dockerfile one-liner, README with GIFs + quickstart, bundled sample dataset, GitHub Actions CI (pytest + ruff).
- **M5 — Grow:** TradingView webhook receiver, IBKR Flex + Schwab/thinkorswim importers, extract `broker-parse` package.

## Engineering rules that matter

- Decimal for money; UTC storage; `America/New_York` for session rules
- Importers pure + config-driven; grouping engine covered by table-driven tests
- Idempotent imports; never commit real account data
- Build only the current milestone — no speculative features
