/** Display formatting. Money strings come from the API as exact decimals. */

/** "$1,234.50" / "-$1,234.50" from a decimal string, without float drift. */
export function money(value: string | null): string {
  if (value === null) return "—";
  const negative = value.startsWith("-");
  const digits = negative ? value.slice(1) : value;
  const [whole, frac = ""] = digits.split(".");
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const cents = frac.length === 0 ? "" : `.${(frac + "00").slice(0, 2)}`;
  return `${negative ? "-" : ""}$${grouped}${cents}`;
}

/** Signed PnL: "+$120.00" / "-$45.00" / "$0.00". */
export function pnl(value: string): string {
  const formatted = money(value);
  return value.startsWith("-") || isZero(value) ? formatted : `+${formatted}`;
}

export function isZero(value: string): boolean {
  return /^-?0*\.?0*$/.test(value);
}

export function pnlTone(value: string): string {
  if (isZero(value)) return "text-muted";
  return value.startsWith("-") ? "text-loss" : "text-gain";
}

/** Trim trailing zeros for quantities/prices: "100.00" -> "100". */
export function trimZeros(value: string): string {
  if (!value.includes(".")) return value;
  return value.replace(/\.?0+$/, "");
}

/** Table price: exact string unless FIFO averaging produced a long tail,
 * then rounded to 4 decimals for display only. */
export function price(value: string): string {
  const frac = value.split(".")[1] ?? "";
  if (frac.length <= 4) return trimZeros(value);
  return trimZeros(Number(value).toFixed(4));
}

const dateFmt = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "2-digit",
  timeZone: "America/New_York",
});
const timeFmt = new Intl.DateTimeFormat("en-US", {
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
  timeZone: "America/New_York",
});

/** UTC instant -> "Jun 01" (ET session date). */
export function sessionDay(iso: string): string {
  return dateFmt.format(new Date(iso));
}

/** UTC instant -> "09:31:05" ET. */
export function sessionTime(iso: string): string {
  return timeFmt.format(new Date(iso));
}

export function sessionStamp(iso: string): string {
  return `${sessionDay(iso)} ${sessionTime(iso)}`;
}

export function holdTime(seconds: number | null): string {
  if (seconds === null) return "—";
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ${seconds % 60}s`;
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
}

/** "2026-06-01" -> "Mon Jun 01" without timezone shifting. */
export function plainDate(day: string): string {
  const [y, m, d] = day.split("-").map(Number);
  return new Intl.DateTimeFormat("en-US", {
    weekday: "short",
    month: "short",
    day: "2-digit",
  }).format(new Date(Date.UTC(y, m - 1, d, 12)));
}
