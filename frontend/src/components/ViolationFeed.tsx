import Link from "next/link";
import type { ViolationFeedItem } from "@/lib/api";
import { pnl, pnlTone, sessionStamp } from "@/lib/format";
import { Empty, RuleChip, SeverityBadge } from "./ui";

export function ViolationFeed({ items }: { items: ViolationFeedItem[] }) {
  if (items.length === 0) {
    return <Empty note="No violations recorded. Keep it that way." />;
  }
  return (
    <ul className="divide-y divide-hairline">
      {items.map((v) => (
        <li key={v.id}>
          <Link
            href={`/trades/detail?id=${v.trade_id}`}
            className="block px-4 py-3 transition-colors hover:bg-panel-2"
          >
            <div className="flex items-center gap-2.5">
              <SeverityBadge severity={v.severity} />
              <span className="num text-[13px] font-semibold">{v.symbol}</span>
              <RuleChip ruleId={v.rule_id} />
              <span className={`num ml-auto text-[12px] ${pnlTone(v.net_pnl)}`}>
                {pnl(v.net_pnl)}
              </span>
            </div>
            <p className="mt-1.5 text-[13px] leading-snug text-ink-2">{v.message}</p>
            <span className="num mt-1 block text-[10px] text-muted">
              entered {sessionStamp(v.opened_at)} ET
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}
