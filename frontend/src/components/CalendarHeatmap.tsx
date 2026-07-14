"use client";

import { useMemo, useState } from "react";
import type { CalendarDay } from "@/lib/api";
import { plainDate, pnl, pnlTone } from "@/lib/format";

/**
 * PnL calendar: GitHub-style week columns over the traded date range.
 * Diverging encoding — teal for profit days, red for loss days, with cell
 * opacity scaled by |PnL| against the best/worst day; the tooltip always
 * shows the signed exact value, so color never carries the sign alone.
 */

const CELL = 15;
const GAP = 3;
const DOW = ["Mon", "", "Wed", "", "Fri", "", ""];

function isoDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

export function CalendarHeatmap({ days }: { days: CalendarDay[] }) {
  const [hover, setHover] = useState<CalendarDay | null>(null);

  const grid = useMemo(() => {
    if (days.length === 0) return null;
    const byDay = new Map(days.map((d) => [d.day, d]));
    const maxAbs = Math.max(...days.map((d) => Math.abs(parseFloat(d.net_pnl))), 1);

    const first = new Date(`${days[0].day}T12:00:00Z`);
    const last = new Date(`${days[days.length - 1].day}T12:00:00Z`);
    // Snap to the Monday on/before the first traded day.
    const start = new Date(first);
    start.setUTCDate(start.getUTCDate() - ((start.getUTCDay() + 6) % 7));

    const weeks: { day: string; data: CalendarDay | undefined }[][] = [];
    for (let cursor = new Date(start); cursor <= last; ) {
      const week: { day: string; data: CalendarDay | undefined }[] = [];
      for (let i = 0; i < 7; i++) {
        const key = isoDate(cursor);
        week.push({ day: key, data: byDay.get(key) });
        cursor.setUTCDate(cursor.getUTCDate() + 1);
      }
      weeks.push(week);
    }
    return { weeks, maxAbs };
  }, [days]);

  if (!grid) {
    return <div className="px-1 py-4 text-[13px] text-muted">No trading days yet.</div>;
  }

  return (
    <div className="relative">
      <div className="flex gap-[3px] overflow-x-auto pb-1">
        <div className="mr-1 flex flex-col gap-[3px]">
          {DOW.map((label, i) => (
            <span
              key={i}
              className="label flex items-center"
              style={{ height: CELL, fontSize: 8 }}
            >
              {label}
            </span>
          ))}
        </div>
        {grid.weeks.map((week, wi) => (
          <div key={wi} className="flex flex-col gap-[3px]">
            {week.map(({ day, data }) => {
              if (!data) {
                return (
                  <div
                    key={day}
                    style={{ width: CELL, height: CELL }}
                    className="bg-panel-2 opacity-50"
                  />
                );
              }
              const value = parseFloat(data.net_pnl);
              const intensity = 0.25 + 0.75 * (Math.abs(value) / grid.maxAbs);
              const color = value === 0 ? "#383835" : value > 0 ? "#199e70" : "#e66767";
              return (
                <button
                  key={day}
                  type="button"
                  aria-label={`${day}: ${data.net_pnl}`}
                  style={{
                    width: CELL,
                    height: CELL,
                    backgroundColor: color,
                    opacity: value === 0 ? 1 : intensity,
                  }}
                  className="cursor-default outline outline-1 outline-transparent transition-[outline-color] hover:outline-ink"
                  onMouseEnter={() => setHover(data)}
                  onMouseLeave={() => setHover(null)}
                />
              );
            })}
          </div>
        ))}
      </div>
      <div className="mt-2 flex h-9 items-center justify-between">
        {hover ? (
          <div className="num text-[12px]">
            <span className="text-ink-2">{plainDate(hover.day)}</span>
            <span className={`ml-3 ${pnlTone(hover.net_pnl)}`}>{pnl(hover.net_pnl)}</span>
            <span className="ml-3 text-muted">
              {hover.trade_count} trade{hover.trade_count === 1 ? "" : "s"}
            </span>
          </div>
        ) : (
          <span className="label">hover a day</span>
        )}
        <div className="flex items-center gap-2">
          <span className="label">loss</span>
          <span className="inline-block h-3 w-3" style={{ background: "#e66767" }} />
          <span className="inline-block h-3 w-3" style={{ background: "#383835" }} />
          <span className="inline-block h-3 w-3" style={{ background: "#199e70" }} />
          <span className="label">gain</span>
        </div>
      </div>
    </div>
  );
}
