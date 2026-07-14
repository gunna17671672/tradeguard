"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, type TradeListFilters, type TradeStatus } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { holdTime, pnl, pnlTone, price, sessionStamp, trimZeros } from "@/lib/format";
import { Empty, ErrorNote, Loading, PageHeader, Panel } from "@/components/ui";

const PAGE_SIZE = 50;

const inputCls =
  "num h-8 border border-hairline bg-panel-2 px-2 text-[12px] text-ink placeholder:text-muted focus:border-accent focus:outline-none";

export default function TradesPage() {
  const router = useRouter();
  const [symbol, setSymbol] = useState("");
  const [tag, setTag] = useState("");
  const [status, setStatus] = useState<"" | TradeStatus>("");
  const [violations, setViolations] = useState<"" | "true" | "false">("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [offset, setOffset] = useState(0);

  const filters: TradeListFilters = {
    symbol: symbol || undefined,
    tag: tag || undefined,
    status: status || undefined,
    has_violations: violations === "" ? undefined : violations === "true",
    from: from || undefined,
    to: to || undefined,
    limit: PAGE_SIZE,
    offset,
  };
  const { data, error, loading } = useApi(
    () => api.trades.list(filters),
    [symbol, tag, status, violations, from, to, offset],
  );

  function setFilter<T>(setter: (v: T) => void) {
    return (value: T) => {
      setOffset(0);
      setter(value);
    };
  }

  const page = data;
  const lastPage = page ? offset + PAGE_SIZE >= page.total : true;

  return (
    <>
      <PageHeader
        title="Trades"
        sub={page ? `${page.total} match${page.total === 1 ? "" : "es"}` : undefined}
      />

      <div className="mb-3 flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1">
          <span className="label">symbol</span>
          <input
            className={`${inputCls} w-24 uppercase`}
            value={symbol}
            onChange={(e) => setFilter(setSymbol)(e.target.value.trim())}
            placeholder="AAPL"
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="label">setup tag</span>
          <input
            className={`${inputCls} w-28`}
            value={tag}
            onChange={(e) => setFilter(setTag)(e.target.value.trim())}
            placeholder="breakout"
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="label">status</span>
          <select
            className={`${inputCls} w-24`}
            value={status}
            onChange={(e) => setFilter(setStatus)(e.target.value as "" | TradeStatus)}
          >
            <option value="">all</option>
            <option value="closed">closed</option>
            <option value="open">open</option>
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="label">violations</span>
          <select
            className={`${inputCls} w-28`}
            value={violations}
            onChange={(e) => setFilter(setViolations)(e.target.value as "" | "true" | "false")}
          >
            <option value="">all</option>
            <option value="true">with</option>
            <option value="false">clean</option>
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="label">from (utc)</span>
          <input
            type="date"
            className={inputCls}
            value={from}
            onChange={(e) => setFilter(setFrom)(e.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="label">to</span>
          <input
            type="date"
            className={inputCls}
            value={to}
            onChange={(e) => setFilter(setTo)(e.target.value)}
          />
        </label>
      </div>

      {error ? <ErrorNote message={error} /> : null}

      <Panel>
        {loading ? (
          <Loading />
        ) : !page || page.items.length === 0 ? (
          <Empty note="No trades match. Import fills from the Import page to get started." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-hairline">
                  {["opened (et)", "symbol", "dir", "qty", "entry", "exit", "net pnl", "r", "hold", "tag", "flags"].map(
                    (h) => (
                      <th key={h} className="label px-3 py-2.5 font-normal">
                        {h}
                      </th>
                    ),
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-hairline">
                {page.items.map((t) => (
                  <tr
                    key={t.id}
                    className="cursor-pointer transition-colors hover:bg-panel-2"
                    onClick={() => router.push(`/trades/detail?id=${t.id}`)}
                  >
                    <td className="num px-3 py-2.5 text-[12px] text-ink-2">
                      {sessionStamp(t.opened_at)}
                    </td>
                    <td className="num px-3 py-2.5 text-[13px] font-semibold">{t.symbol}</td>
                    <td className="px-3 py-2.5">
                      <span
                        className={`num text-[10px] uppercase tracking-wider ${
                          t.direction === "long" ? "text-gain" : "text-loss"
                        }`}
                      >
                        {t.direction}
                      </span>
                    </td>
                    <td className="num px-3 py-2.5 text-[12px]">{trimZeros(t.max_qty)}</td>
                    <td className="num px-3 py-2.5 text-[12px]">{price(t.avg_entry_price)}</td>
                    <td className="num px-3 py-2.5 text-[12px]">
                      {t.avg_exit_price ? price(t.avg_exit_price) : "—"}
                    </td>
                    <td className={`num px-3 py-2.5 text-[12px] font-medium ${pnlTone(t.net_pnl)}`}>
                      {t.status === "closed" ? pnl(t.net_pnl) : "open"}
                    </td>
                    <td className="num px-3 py-2.5 text-[12px]">
                      {t.r_multiple ? `${parseFloat(t.r_multiple).toFixed(2)}R` : "—"}
                    </td>
                    <td className="num px-3 py-2.5 text-[12px] text-ink-2">
                      {holdTime(t.hold_time_seconds)}
                    </td>
                    <td className="num px-3 py-2.5 text-[11px] text-ink-2">{t.setup_tag ?? "—"}</td>
                    <td className="px-3 py-2.5">
                      {t.violations.length > 0 ? (
                        <span className="num text-[11px] text-loss">
                          ⚑ {t.violations.length}
                        </span>
                      ) : (
                        <span className="text-[11px] text-muted">·</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      {page && page.total > PAGE_SIZE ? (
        <div className="mt-3 flex items-center gap-4">
          <button
            type="button"
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            className="label border border-hairline px-3 py-1.5 text-ink-2 enabled:hover:border-accent enabled:hover:text-ink disabled:opacity-40"
          >
            ← prev
          </button>
          <span className="num text-[11px] text-muted">
            {offset + 1}–{Math.min(offset + PAGE_SIZE, page.total)} of {page.total}
          </span>
          <button
            type="button"
            disabled={lastPage}
            onClick={() => setOffset(offset + PAGE_SIZE)}
            className="label border border-hairline px-3 py-1.5 text-ink-2 enabled:hover:border-accent enabled:hover:text-ink disabled:opacity-40"
          >
            next →
          </button>
        </div>
      ) : null}
    </>
  );
}
