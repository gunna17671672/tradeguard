"use client";

import { useMemo, useRef, useState } from "react";
import type { EquityPoint } from "@/lib/api";
import { pnl, pnlTone, sessionDay } from "@/lib/format";

/**
 * Cumulative net PnL, one step per closed trade (x = trade sequence).
 * Hand-rolled SVG: single series (no legend needed), recessive grid,
 * crosshair + tooltip on hover. Numbers are parsed only for geometry;
 * displayed values use the exact API strings.
 */

const W = 720;
const H = 240;
const PAD = { top: 16, right: 16, bottom: 24, left: 56 };

function niceTicks(min: number, max: number, count = 4): number[] {
  const span = max - min || 1;
  const step = Math.pow(10, Math.floor(Math.log10(span / count)));
  const err = span / count / step;
  const mult = err >= 7.5 ? 10 : err >= 3.5 ? 5 : err >= 1.5 ? 2 : 1;
  const size = mult * step;
  const start = Math.ceil(min / size) * size;
  const ticks: number[] = [];
  for (let v = start; v <= max + 1e-9; v += size) ticks.push(v);
  return ticks;
}

export function EquityCurve({ points }: { points: EquityPoint[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  const geom = useMemo(() => {
    const values = points.map((p) => parseFloat(p.cumulative_pnl));
    const lo = Math.min(0, ...values);
    const hi = Math.max(0, ...values);
    const spread = hi - lo || 1;
    const x = (i: number) =>
      points.length === 1
        ? (PAD.left + W - PAD.right) / 2
        : PAD.left + (i / (points.length - 1)) * (W - PAD.left - PAD.right);
    const y = (v: number) =>
      PAD.top + (1 - (v - lo) / spread) * (H - PAD.top - PAD.bottom);
    return { values, lo, hi, x, y };
  }, [points]);

  if (points.length === 0) {
    return (
      <div className="flex h-48 items-center justify-center text-[13px] text-muted">
        No closed trades yet — import some fills to draw the curve.
      </div>
    );
  }

  const { values, lo, hi, x, y } = geom;
  const line = values.map((v, i) => `${i === 0 ? "M" : "L"}${x(i)},${y(v)}`).join("");
  const area = `${line}L${x(values.length - 1)},${y(0)}L${x(0)},${y(0)}Z`;
  const ticks = niceTicks(lo, hi);

  // Sparse x labels: first, last, and ~3 between, by session date.
  const labelEvery = Math.max(1, Math.ceil(points.length / 5));
  const xLabels = points
    .map((p, i) => ({ i, day: sessionDay(p.closed_at) }))
    .filter(({ i }) => i % labelEvery === 0 || i === points.length - 1);

  function onMove(event: React.MouseEvent<SVGSVGElement>) {
    const rect = svgRef.current!.getBoundingClientRect();
    const px = ((event.clientX - rect.left) / rect.width) * W;
    const t =
      points.length === 1
        ? 0
        : Math.round(
            ((px - PAD.left) / (W - PAD.left - PAD.right)) * (points.length - 1),
          );
    setHover(Math.max(0, Math.min(points.length - 1, t)));
  }

  const h = hover !== null ? points[hover] : null;

  return (
    <div className="relative">
      <svg
        ref={svgRef}
        viewBox={`0 0 ${W} ${H}`}
        className="block w-full"
        onMouseMove={onMove}
        onMouseLeave={() => setHover(null)}
        role="img"
        aria-label="Equity curve: cumulative net PnL per closed trade"
      >
        <defs>
          <linearGradient id="eq-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#3987e5" stopOpacity="0.16" />
            <stop offset="100%" stopColor="#3987e5" stopOpacity="0" />
          </linearGradient>
        </defs>
        {ticks.map((t) => (
          <g key={t}>
            <line
              x1={PAD.left}
              x2={W - PAD.right}
              y1={y(t)}
              y2={y(t)}
              stroke="#2c2c2a"
              strokeWidth="1"
            />
            <text
              x={PAD.left - 8}
              y={y(t) + 3}
              textAnchor="end"
              fontSize="10"
              fill="#898781"
              fontFamily="var(--font-mono)"
            >
              {t >= 1000 || t <= -1000 ? `${t / 1000}k` : t}
            </text>
          </g>
        ))}
        {/* zero baseline, emphasized when the curve crosses it */}
        <line
          x1={PAD.left}
          x2={W - PAD.right}
          y1={y(0)}
          y2={y(0)}
          stroke="#383835"
          strokeWidth="1"
          strokeDasharray={lo < 0 && hi > 0 ? "3 3" : undefined}
        />
        {xLabels.map(({ i, day }) => (
          <text
            key={i}
            x={x(i)}
            y={H - 6}
            textAnchor="middle"
            fontSize="10"
            fill="#898781"
            fontFamily="var(--font-mono)"
          >
            {day}
          </text>
        ))}
        <path d={area} fill="url(#eq-fill)" />
        <path d={line} fill="none" stroke="#3987e5" strokeWidth="2" strokeLinejoin="round" />
        {hover !== null && (
          <g>
            <line
              x1={x(hover)}
              x2={x(hover)}
              y1={PAD.top}
              y2={H - PAD.bottom}
              stroke="#52514e"
              strokeWidth="1"
            />
            <circle
              cx={x(hover)}
              cy={y(values[hover])}
              r="4"
              fill="#3987e5"
              stroke="#1a1a19"
              strokeWidth="2"
            />
          </g>
        )}
      </svg>
      {h !== null && hover !== null && (
        <div
          className="pointer-events-none absolute top-2 panel z-10 px-3 py-2"
          style={{
            left: `${(x(hover) / W) * 100}%`,
            transform: hover > points.length / 2 ? "translateX(-108%)" : "translateX(8%)",
          }}
        >
          <div className="label mb-1">
            trade #{hover + 1} · {sessionDay(h.closed_at)}
          </div>
          <div className="num text-[12px] text-ink-2">
            net <span className={pnlTone(h.net_pnl)}>{pnl(h.net_pnl)}</span>
          </div>
          <div className="num text-[12px] text-ink-2">
            equity <span className={pnlTone(h.cumulative_pnl)}>{pnl(h.cumulative_pnl)}</span>
          </div>
        </div>
      )}
    </div>
  );
}
