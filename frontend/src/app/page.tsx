"use client";

import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { money, pnl, pnlTone } from "@/lib/format";
import { EquityCurve } from "@/components/EquityCurve";
import { CalendarHeatmap } from "@/components/CalendarHeatmap";
import { ViolationFeed } from "@/components/ViolationFeed";
import { ErrorNote, Loading, PageHeader, Panel } from "@/components/ui";
import Link from "next/link";

function StatTile({
  label,
  value,
  tone = "",
  hint,
}: {
  label: string;
  value: string;
  tone?: string;
  hint?: string;
}) {
  return (
    <div className="panel px-4 py-3">
      <span className="label block">{label}</span>
      <span className={`num mt-1.5 block text-[22px] font-medium leading-none ${tone}`}>
        {value}
      </span>
      {hint ? <span className="num mt-1.5 block text-[10px] text-muted">{hint}</span> : null}
    </div>
  );
}

export default function Dashboard() {
  const summary = useApi(() => api.stats.summary());
  const equity = useApi(() => api.stats.equity());
  const calendar = useApi(() => api.stats.calendar());
  const weekly = useApi(() => api.reports.weekly());
  const violations = useApi(() => api.violations.list({ limit: 8 }));

  const firstError =
    summary.error ?? equity.error ?? calendar.error ?? weekly.error ?? violations.error;

  return (
    <>
      <PageHeader title="Dashboard" sub="all history · times in ET" />
      {firstError ? <ErrorNote message={firstError} /> : null}

      <div className="mt-5 grid grid-cols-2 gap-3 lg:grid-cols-5">
        {summary.data ? (
          <>
            <StatTile
              label="net pnl"
              value={pnl(summary.data.net_pnl)}
              tone={pnlTone(summary.data.net_pnl)}
              hint={`${summary.data.closed_trades} closed trades`}
            />
            <StatTile
              label="win rate"
              value={summary.data.win_rate_pct !== null ? `${summary.data.win_rate_pct}%` : "—"}
              hint={`${summary.data.wins}W / ${summary.data.losses}L`}
            />
            <StatTile
              label="profit factor"
              value={summary.data.profit_factor ?? "—"}
              hint={`avg win ${money(summary.data.avg_win)} · avg loss ${money(summary.data.avg_loss)}`}
            />
          </>
        ) : null}
        {weekly.data ? (
          <>
            <StatTile
              label="adherence · this week"
              value={weekly.data.adherence_pct !== null ? `${weekly.data.adherence_pct}%` : "—"}
              tone={
                weekly.data.adherence_pct === null
                  ? ""
                  : parseFloat(weekly.data.adherence_pct) >= 90
                    ? "text-gain"
                    : "text-warn"
              }
              hint={`${weekly.data.violation_count} violation${weekly.data.violation_count === 1 ? "" : "s"} this week`}
            />
            <StatTile
              label="clean streak"
              value={`${weekly.data.streak_days}d`}
              tone={weekly.data.streak_days > 0 ? "text-gain" : ""}
              hint="violation-free trading days"
            />
          </>
        ) : null}
      </div>

      <div className="mt-3 grid gap-3 xl:grid-cols-3">
        <Panel title="equity curve · cumulative net pnl" className="xl:col-span-2">
          <div className="px-4 py-4">
            {equity.loading ? <Loading /> : <EquityCurve points={equity.data ?? []} />}
          </div>
        </Panel>
        <Panel
          title="recent violations"
          right={
            <Link href="/discipline" className="label text-accent hover:underline">
              all →
            </Link>
          }
        >
          {violations.loading ? (
            <Loading />
          ) : (
            <ViolationFeed items={violations.data?.items ?? []} />
          )}
        </Panel>
      </div>

      <div className="mt-3">
        <Panel title="pnl calendar · session days (ET)">
          <div className="px-4 py-4">
            {calendar.loading ? <Loading /> : <CalendarHeatmap days={calendar.data ?? []} />}
          </div>
        </Panel>
      </div>
    </>
  );
}
