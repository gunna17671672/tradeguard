"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { api, type TradeDetail, type TradePatch } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import {
  holdTime,
  money,
  pnl,
  pnlTone,
  sessionStamp,
  sessionTime,
  trimZeros,
} from "@/lib/format";
import {
  Empty,
  ErrorNote,
  Loading,
  PageHeader,
  Panel,
  RuleChip,
  SeverityBadge,
} from "@/components/ui";

const inputCls =
  "num h-8 w-full border border-hairline bg-panel-2 px-2 text-[12px] text-ink placeholder:text-muted focus:border-accent focus:outline-none";

function Meta({ label, value, tone = "" }: { label: string; value: string; tone?: string }) {
  return (
    <div>
      <span className="label block">{label}</span>
      <span className={`num mt-1 block text-[14px] ${tone}`}>{value}</span>
    </div>
  );
}

function AnnotationEditor({
  trade,
  onSaved,
}: {
  trade: TradeDetail;
  onSaved: (t: TradeDetail) => void;
}) {
  const [stop, setStop] = useState(trade.planned_stop ?? "");
  const [target, setTarget] = useState(trade.planned_target ?? "");
  const [tag, setTag] = useState(trade.setup_tag ?? "");
  const [notes, setNotes] = useState(trade.notes ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<number | null>(null);

  useEffect(() => {
    setStop(trade.planned_stop ?? "");
    setTarget(trade.planned_target ?? "");
    setTag(trade.setup_tag ?? "");
    setNotes(trade.notes ?? "");
  }, [trade]);

  async function save() {
    setSaving(true);
    setError(null);
    const patch: TradePatch = {
      planned_stop: stop.trim() === "" ? null : stop.trim(),
      planned_target: target.trim() === "" ? null : target.trim(),
      setup_tag: tag.trim() === "" ? null : tag.trim(),
      notes: notes.trim() === "" ? null : notes,
    };
    try {
      const updated = await api.trades.update(trade.id, patch);
      onSaved(updated);
      setSavedAt(Date.now());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="px-4 py-4">
      <div className="grid grid-cols-2 gap-3">
        <label className="flex flex-col gap-1">
          <span className="label">planned stop</span>
          <input
            className={inputCls}
            value={stop}
            onChange={(e) => setStop(e.target.value)}
            placeholder="98.50"
            inputMode="decimal"
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="label">planned target</span>
          <input
            className={inputCls}
            value={target}
            onChange={(e) => setTarget(e.target.value)}
            placeholder="105.00"
            inputMode="decimal"
          />
        </label>
      </div>
      <label className="mt-3 flex flex-col gap-1">
        <span className="label">setup tag</span>
        <input
          className={inputCls}
          value={tag}
          onChange={(e) => setTag(e.target.value)}
          placeholder="breakout / orb / fade…"
          maxLength={50}
        />
      </label>
      <label className="mt-3 flex flex-col gap-1">
        <span className="label">notes</span>
        <textarea
          className={`${inputCls} h-24 resize-y py-2`}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="What was the plan? What actually happened?"
        />
      </label>
      {error ? <p className="mt-2 text-[12px] text-loss">{error}</p> : null}
      <div className="mt-3 flex items-center gap-3">
        <button
          type="button"
          onClick={save}
          disabled={saving}
          className="label border border-accent bg-accent/10 px-4 py-2 text-accent transition-colors hover:bg-accent hover:text-page disabled:opacity-50"
        >
          {saving ? "saving…" : "save annotations"}
        </button>
        {savedAt !== null && !saving ? (
          <span className="label text-gain">saved · re-audited</span>
        ) : null}
      </div>
      <p className="mt-3 text-[11px] leading-relaxed text-muted">
        Saving re-audits this account against rules.yaml — violations may appear or clear.
        Recording a stop stamps <span className="num">stop_set_at</span> the first time only.
      </p>
    </div>
  );
}

function TradeDetailInner() {
  const params = useSearchParams();
  const id = Number(params.get("id"));
  const { data, error, loading, reload } = useApi(() => api.trades.get(id), [id]);
  const [trade, setTrade] = useState<TradeDetail | null>(null);

  useEffect(() => setTrade(data), [data]);

  if (!Number.isFinite(id) || id <= 0) {
    return <ErrorNote message="Missing ?id= — open a trade from the Trades table." />;
  }
  if (loading && !trade) return <Loading />;
  if (error) return <ErrorNote message={error} />;
  if (!trade) return null;

  const closed = trade.status === "closed";

  return (
    <>
      <PageHeader
        title={`${trade.symbol} · ${trade.direction.toUpperCase()}`}
        sub={`trade #${trade.id} · ${trade.status}`}
      />
      <div className="mb-3">
        <Link href="/trades" className="label text-accent hover:underline">
          ← all trades
        </Link>
      </div>

      <div className="panel mb-3 grid grid-cols-3 gap-x-4 gap-y-4 px-4 py-4 md:grid-cols-6">
        <Meta
          label="net pnl"
          value={closed ? pnl(trade.net_pnl) : "open"}
          tone={closed ? `${pnlTone(trade.net_pnl)} font-semibold` : "text-muted"}
        />
        <Meta label="size" value={`${trimZeros(trade.max_qty)} sh`} />
        <Meta label="avg entry" value={money(trade.avg_entry_price)} />
        <Meta label="avg exit" value={trade.avg_exit_price ? money(trade.avg_exit_price) : "—"} />
        <Meta label="hold" value={holdTime(trade.hold_time_seconds)} />
        <Meta
          label="r multiple"
          value={trade.r_multiple ? `${parseFloat(trade.r_multiple).toFixed(2)}R` : "—"}
          tone={trade.r_multiple ? pnlTone(trade.r_multiple) : ""}
        />
        <Meta label="opened (et)" value={sessionStamp(trade.opened_at)} />
        <Meta label="closed (et)" value={trade.closed_at ? sessionStamp(trade.closed_at) : "—"} />
        <Meta label="fees" value={money(trade.total_fees)} />
        <Meta label="fills" value={String(trade.fill_count)} />
        <Meta label="gross pnl" value={money(trade.gross_pnl)} />
        <Meta label="account" value={trade.account_label} />
      </div>

      <div className="grid gap-3 xl:grid-cols-2">
        <div className="flex flex-col gap-3">
          <Panel title={`fills timeline · ${trade.executions.length} executions`}>
            <ul className="divide-y divide-hairline">
              {trade.executions.map((e) => (
                <li key={e.id} className="flex items-center gap-3 px-4 py-2.5">
                  <span
                    className={`num w-10 text-[10px] font-semibold uppercase tracking-wider ${
                      e.side === "buy" ? "text-gain" : "text-loss"
                    }`}
                  >
                    {e.side}
                  </span>
                  <span className="num text-[12px]">{trimZeros(e.qty)}</span>
                  <span className="num text-[12px] text-muted">@</span>
                  <span className="num text-[12px]">{money(e.price)}</span>
                  <span className="num ml-auto text-[11px] text-muted">
                    {sessionTime(e.executed_at)} ET
                  </span>
                </li>
              ))}
            </ul>
          </Panel>

          <Panel title={`violations · ${trade.violations.length}`}>
            {trade.violations.length === 0 ? (
              <Empty note="Clean trade — no rule violations." />
            ) : (
              <ul className="divide-y divide-hairline">
                {trade.violations.map((v) => (
                  <li key={v.id} className="px-4 py-3">
                    <div className="flex items-center gap-2.5">
                      <SeverityBadge severity={v.severity} />
                      <RuleChip ruleId={v.rule_id} />
                    </div>
                    <p className="mt-1.5 text-[13px] leading-snug text-ink-2">{v.message}</p>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </div>

        <Panel title="annotations · stop / target / tag / notes">
          <AnnotationEditor
            trade={trade}
            onSaved={(updated) => {
              setTrade(updated);
              reload();
            }}
          />
        </Panel>
      </div>
    </>
  );
}

export default function TradeDetailPage() {
  return (
    <Suspense fallback={<Loading />}>
      <TradeDetailInner />
    </Suspense>
  );
}
