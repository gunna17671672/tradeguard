"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const ITEMS = [
  { href: "/", label: "Dashboard", code: "01" },
  { href: "/trades", label: "Trades", code: "02" },
  { href: "/discipline", label: "Discipline", code: "03" },
  { href: "/import", label: "Import", code: "04" },
  { href: "/settings", label: "Settings", code: "05" },
];

export function Nav() {
  const pathname = usePathname();
  return (
    <aside className="sticky top-0 flex h-screen w-52 shrink-0 flex-col border-r border-hairline bg-panel">
      <Link href="/" className="block border-b border-hairline px-5 py-6">
        <span className="num block text-[15px] font-semibold tracking-[0.22em] text-ink">
          TRADE<span className="text-accent">GUARD</span>
        </span>
        <span className="label mt-1 block">discipline engine</span>
      </Link>
      <nav className="flex flex-col gap-px py-4">
        {ITEMS.map((item) => {
          const active =
            item.href === "/"
              ? pathname === "/"
              : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`group flex items-baseline gap-3 border-l-2 px-5 py-2.5 transition-colors ${
                active
                  ? "border-accent bg-panel-2 text-ink"
                  : "border-transparent text-ink-2 hover:bg-panel-2 hover:text-ink"
              }`}
            >
              <span className={`num text-[10px] ${active ? "text-accent" : "text-muted"}`}>
                {item.code}
              </span>
              <span className="text-[13px] font-medium tracking-wide">{item.label}</span>
            </Link>
          );
        })}
      </nav>
      <div className="mt-auto border-t border-hairline px-5 py-4">
        <span className="label block">local-first</span>
        <span className="num mt-1 block text-[11px] text-ink-2">127.0.0.1 · v0.1</span>
      </div>
    </aside>
  );
}
