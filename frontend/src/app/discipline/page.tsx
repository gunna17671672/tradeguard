"use client";

import { useMemo, useState } from "react";
import { api, type Severity } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { plainDate, pnl, pnlTone } from "@/lib/format";
import { ViolationFeed } from "@/components/ViolationFeed";
import { ErrorNote, Loading, PageHeader, Panel } from "@/components/ui";

const selectCls =
  "num h-8 border border-hairline bg-panel-2 px-2 text-[12px] text-ink focus:border-accent focus:outline-none";

function isoDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function mondayOf(d: Date): Date {
  const copy = new Date(d);
  copy.setUTCDate(copy.getUTCDate() - ((copy.getUTCDay() + 6) % 7));
  return copy;
}

export default function DisciplinePage() {
  const [weekStart, setWeekStart] = useState(() => mondayOf(new Date()));
  const [ruleFilter, setRuleFilter] = useState("");
  const [severityFilter, setSeverityFilter] = useState<"" | Severity>("");

  const week = isoDate(weekStart);
  const weekly = useApi(() => api.reports.weekly(week), [week]);
  const violations = useApi(
    () =>
      api.violations.list({
        rule_id: ruleFilter || undefined,
        severity: severityFilter || undefined,
        limit: 100,
      }),
    [ruleFilter, severityFilter],
  );
  const rulesInFeed = useMemo(() => {
    const ids = new Set((violations.data?.items ?? []).map((v) => v.rule_id));
    if (ruleFilter) ids.add(ruleFilter);
    return [...ids].sort();
  }, [violations.data, ruleFilter]);

  function shiftWeek(days: number) {
    const next = new Date(weekStart);
    next.setUTCDate(next.getUTCDate() + days);
    setWeekStart(next);
  }

  const r = weekly.data;
  const maxRuleCount = r ? Math.max(...Object.values(r.violations_by_rule), 1) : 1;

  return (
    <>
      <PageHeader title="Discipline" sub="rules audited on every import" />
      {weekly.error ? <ErrorNote message={weekly.error} /> : null}

      <Panel
        title="weekly report"
        right={
          <div className="flex items-center gap-2">
            <button type="button" onClick={() => shiftWeek(-7)} className="label px-1 text-ink-2 hover:text-accent">
              ← prev
            </button>
            <span className="num text-[11px] text-ink-2">
              {r ? `${plainDate(r.week_start)} – ${plainDate(r.week_end)}` : week}
            </span>
            <button type="button" onClick={() => shiftWeek(7)} className="label px-1 text-ink-2 hover:text-accent">
              next →
            </button>
          </div>
        }
      >
        {weekly.loading ? (
          <Loading />
        ) : r ? (
          <div className="grid gap-6 px-4 py-5 md:grid-cols-[220px_1fr]">
            <div>
              <span className="label block">adherence</span>
              <div
                className={`num mt-2 text-[52px] font-medium leading-none ${
                  r.adherence_pct === null
                    ? "text-muted"
                    : parseFloat(r.adherence_pct) >= 90
                      ? "text-gain"
                      : parseFloat(r.adherence_pct) >= 70
                        ? "text-warn"
                        : "text-loss"
                }`}
              >
                {r.adherence_pct !== null ? `${r.adherence_pct}%` : "—"}
              </div>
              <span className="num mt-2 block text-[11px] text-muted">
                clean closed trades this week
              </span>
              <div className="mt-5 border-t border-hairline pt-4">
                <span className="label block">clean streak</span>
                <div className={`num mt-1 text-[26px] ${r.streak_days > 0 ? "text-gain" : "text-ink-2"}`}>
                  {r.streak_days} day{r.streak_days === 1 ? "" : "s"}
                </div>
              </div>
            </div>

            <div>
              <div className="grid grid-cols-2 gap-x-4 gap-y-4 sm:grid-cols-4">
                <div>
                  <span className="label block">closed trades</span>
                  <span className="num mt-1 block text-[18px]">{r.closed_trades}</span>
                </div>
                <div>
                  <span className="label block">w / l</span>
                  <span className="num mt-1 block text-[18px]">
                    <span className="text-gain">{r.wins}</span>
                    <span className="text-muted"> / </span>
                    <span className="text-loss">{r.losses}</span>
                  </span>
                </div>
                <div>
                  <span className="label block">net pnl</span>
                  <span className={`num mt-1 block text-[18px] ${pnlTone(r.net_pnl)}`}>
                    {pnl(r.net_pnl)}
                  </span>
                </div>
                <div>
                  <span className="label block">violations</span>
                  <span
                    className={`num mt-1 block text-[18px] ${r.violation_count > 0 ? "text-loss" : "text-gain"}`}
                  >
                    {r.violation_count}
                  </span>
                </div>
              </div>

              <div className="mt-6">
                <span className="label block">violations by rule</span>
                {Object.keys(r.violations_by_rule).length === 0 ? (
                  <p className="mt-2 text-[13px] text-muted">None this week.</p>
                ) : (
                  <ul className="mt-3 flex flex-col gap-2">
                    {Object.entries(r.violations_by_rule)
                      .sort(([, a], [, b]) => b - a)
                      .map(([ruleId, count]) => (
                        <li key={ruleId} className="flex items-center gap-3">
                          <span className="num w-44 shrink-0 text-[11px] text-ink-2">{ruleId}</span>
                          <div className="h-3.5 flex-1 bg-panel-2">
                            <div
                              className="h-full bg-loss"
                              style={{ width: `${(count / maxRuleCount) * 100}%`, opacity: 0.85 }}
                            />
                          </div>
                          <span className="num w-6 text-right text-[12px]">{count}</span>
                        </li>
                      ))}
                  </ul>
                )}
              </div>
            </div>
          </div>
        ) : null}
      </Panel>

      <div className="mt-3">
        <Panel
          title="violations feed"
          right={
            <div className="flex items-center gap-2">
              <select
                className={selectCls}
                value={ruleFilter}
                onChange={(e) => setRuleFilter(e.target.value)}
              >
                <option value="">all rules</option>
                {rulesInFeed.map((id) => (
                  <option key={id} value={id}>
                    {id}
                  </option>
                ))}
              </select>
              <select
                className={selectCls}
                value={severityFilter}
                onChange={(e) => setSeverityFilter(e.target.value as "" | Severity)}
              >
                <option value="">all severities</option>
                <option value="violation">violation</option>
                <option value="warn">warn</option>
                <option value="info">info</option>
              </select>
            </div>
          }
        >
          {violations.error ? (
            <div className="p-3">
              <ErrorNote message={violations.error} />
            </div>
          ) : violations.loading ? (
            <Loading />
          ) : (
            <ViolationFeed items={violations.data?.items ?? []} />
          )}
        </Panel>
      </div>
    </>
  );
}
