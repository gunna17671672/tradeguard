/** Small shared pieces of the ledger UI. */

import type { Severity } from "@/lib/api";

export function PageHeader({ title, sub }: { title: string; sub?: string }) {
  return (
    <header className="mb-7 flex items-baseline justify-between border-b border-hairline pb-4">
      <h1 className="text-[19px] font-semibold tracking-wide">{title}</h1>
      {sub ? <span className="label">{sub}</span> : null}
    </header>
  );
}

export function Panel({
  title,
  right,
  children,
  className = "",
}: {
  title?: string;
  right?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      {title ? (
        <div className="flex items-center justify-between border-b border-hairline px-4 py-2.5">
          <span className="label">{title}</span>
          {right}
        </div>
      ) : null}
      {children}
    </section>
  );
}

export function ErrorNote({ message }: { message: string }) {
  return (
    <div className="panel border-loss/40 px-4 py-3 text-[13px] text-loss">
      <span className="label mr-3 text-loss">error</span>
      {message}
    </div>
  );
}

export function Loading() {
  return (
    <div className="px-4 py-6">
      <span className="label animate-pulse">loading…</span>
    </div>
  );
}

export function Empty({ note }: { note: string }) {
  return <div className="px-4 py-6 text-[13px] text-muted">{note}</div>;
}

const SEVERITY_TONE: Record<Severity, string> = {
  violation: "text-loss border-loss/50",
  warn: "text-warn border-warn/50",
  info: "text-ink-2 border-baseline",
};

export function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <span
      className={`num inline-block border px-1.5 py-0.5 text-[9px] uppercase tracking-[0.12em] ${SEVERITY_TONE[severity]}`}
    >
      {severity}
    </span>
  );
}

export function RuleChip({ ruleId }: { ruleId: string }) {
  return (
    <span className="num inline-block bg-panel-2 px-1.5 py-0.5 text-[10px] text-ink-2">
      {ruleId}
    </span>
  );
}
