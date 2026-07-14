/**
 * Typed client for the TradeGuard API.
 *
 * Dev mode: the FastAPI server runs on 127.0.0.1:8000 (uvicorn default) and
 * allows the Next dev origin via CORS. Override with NEXT_PUBLIC_API_URL.
 * Money is always a decimal *string* — never parse it into a float for
 * anything but chart geometry.
 */

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  constructor(
    public status: number,
    detail: string,
  ) {
    super(detail);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, init);
  } catch {
    throw new ApiError(
      0,
      `Cannot reach the API at ${API_URL}. Is uvicorn running? (cd backend && uvicorn app.main:app --reload)`,
    );
  }
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") detail = body.detail;
      else if (body.detail) detail = JSON.stringify(body.detail);
    } catch {
      /* non-JSON error body; keep the status line */
    }
    throw new ApiError(response.status, detail);
  }
  return response.json() as Promise<T>;
}

/* ---------- types (mirror backend/app/schemas.py) ---------- */

export type Severity = "info" | "warn" | "violation";
export type TradeStatus = "open" | "closed";
export type Direction = "long" | "short";

export interface Violation {
  id: number;
  trade_id: number;
  rule_id: string;
  severity: Severity;
  message: string;
}

export interface Trade {
  id: number;
  account_label: string;
  symbol: string;
  direction: Direction;
  status: TradeStatus;
  opened_at: string;
  closed_at: string | null;
  max_qty: string;
  avg_entry_price: string;
  avg_exit_price: string | null;
  gross_pnl: string;
  net_pnl: string;
  total_fees: string;
  hold_time_seconds: number | null;
  fill_count: number;
  planned_stop: string | null;
  planned_target: string | null;
  setup_tag: string | null;
  notes: string | null;
  stop_set_at: string | null;
  r_multiple: string | null;
  violations: Violation[];
}

export interface Execution {
  id: number;
  broker: string;
  account_label: string;
  symbol: string;
  asset_type: string;
  side: "buy" | "sell";
  qty: string;
  price: string;
  fees: string;
  executed_at: string;
  trade_id: number | null;
}

export interface TradeDetail extends Trade {
  executions: Execution[];
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface ViolationFeedItem extends Violation {
  symbol: string;
  opened_at: string;
  closed_at: string | null;
  net_pnl: string;
}

export interface StatsSummary {
  closed_trades: number;
  wins: number;
  losses: number;
  scratches: number;
  win_rate_pct: string | null;
  profit_factor: string | null;
  avg_win: string | null;
  avg_loss: string | null;
  expectancy: string | null;
  gross_pnl: string;
  net_pnl: string;
  total_fees: string;
}

export interface EquityPoint {
  trade_id: number;
  closed_at: string;
  net_pnl: string;
  cumulative_pnl: string;
}

export interface CalendarDay {
  day: string;
  net_pnl: string;
  trade_count: number;
}

export interface WeeklyReport {
  week_start: string;
  week_end: string;
  closed_trades: number;
  wins: number;
  losses: number;
  gross_pnl: string;
  net_pnl: string;
  total_fees: string;
  adherence_pct: string | null;
  violation_count: number;
  violations_by_rule: Record<string, number>;
  streak_days: number;
}

export type RuleParams = Record<string, unknown>;

export interface RulesFile {
  account: Record<string, unknown>;
  rules: Record<string, RuleParams>;
  enabled_rule_ids: string[];
  available_rules: string[];
}

export interface RulesUpdateResponse extends RulesFile {
  violations_recorded: number;
}

export interface ImportResponse {
  batch_id: number;
  broker: string;
  filename: string;
  inserted: number;
  skipped_duplicates: number;
  trades_rebuilt: number;
  violations_recorded: number;
  audited: boolean;
}

export interface TradeListFilters {
  symbol?: string;
  tag?: string;
  status?: TradeStatus;
  has_violations?: boolean;
  from?: string;
  to?: string;
  limit?: number;
  offset?: number;
}

export interface TradePatch {
  planned_stop?: string | null;
  planned_target?: string | null;
  setup_tag?: string | null;
  notes?: string | null;
}

/* ---------- endpoints ---------- */

function query(params: Record<string, unknown>): string {
  const pairs = Object.entries(params).filter(
    ([, v]) => v !== undefined && v !== null && v !== "",
  );
  if (pairs.length === 0) return "";
  const search = new URLSearchParams(
    pairs.map(([k, v]) => [k, String(v)]),
  );
  return `?${search}`;
}

export const api = {
  trades: {
    list: (filters: TradeListFilters = {}) =>
      request<Page<Trade>>(`/api/trades${query({ ...filters })}`),
    get: (id: number) => request<TradeDetail>(`/api/trades/${id}`),
    update: (id: number, patch: TradePatch) =>
      request<TradeDetail>(`/api/trades/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      }),
  },
  violations: {
    list: (params: { rule_id?: string; severity?: Severity; limit?: number; offset?: number } = {}) =>
      request<Page<ViolationFeedItem>>(`/api/violations${query({ ...params })}`),
  },
  stats: {
    summary: (params: { from?: string; to?: string } = {}) =>
      request<StatsSummary>(`/api/stats/summary${query({ ...params })}`),
    equity: () => request<EquityPoint[]>(`/api/stats/equity`),
    calendar: () => request<CalendarDay[]>(`/api/stats/calendar`),
  },
  reports: {
    weekly: (week?: string) =>
      request<WeeklyReport>(`/api/reports/weekly${query({ week })}`),
  },
  rules: {
    get: () => request<RulesFile>(`/api/rules`),
    put: (body: { account: Record<string, unknown>; rules: Record<string, RuleParams> }) =>
      request<RulesUpdateResponse>(`/api/rules`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }),
  },
  imports: {
    create: (file: File, broker: string, mapping?: string) => {
      const form = new FormData();
      form.append("file", file);
      form.append("broker", broker);
      if (mapping) form.append("mapping", mapping);
      return request<ImportResponse>(`/api/imports`, { method: "POST", body: form });
    },
  },
};
