"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { api, type ImportDeleteResponse, type ImportResponse } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { sessionStamp } from "@/lib/format";
import { Empty, ErrorNote, PageHeader, Panel } from "@/components/ui";

type Broker = "webull" | "generic";

const MAPPING_PLACEHOLDER = `{
  "symbol": "Ticker", "side": "Action", "qty": "Shares",
  "price": "FillPrice", "executed_at": "When",
  "datetime_format": "%m/%d/%Y %H:%M:%S", "timezone": "America/New_York"
}`;

// Webull writes timestamps in the exporting device's local timezone, so the
// right choice is wherever the trader's machine was — not the exchange's zone.
const TIMEZONES: [string, string][] = [
  ["America/New_York", "Eastern — ET"],
  ["America/Chicago", "Central — CT"],
  ["America/Denver", "Mountain — MT"],
  ["America/Phoenix", "Arizona — no DST"],
  ["America/Los_Angeles", "Pacific — PT"],
  ["America/Anchorage", "Alaska — AKT"],
  ["Pacific/Honolulu", "Hawaii — HT"],
  ["UTC", "UTC"],
];

export default function ImportPage() {
  const [broker, setBroker] = useState<Broker>("webull");
  const [mapping, setMapping] = useState("");
  const [timezone, setTimezone] = useState("America/New_York");
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ImportResponse | null>(null);
  const [deleted, setDeleted] = useState<ImportDeleteResponse | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const batches = useApi(api.imports.list);

  async function send(file: File) {
    setBusy(true);
    setError(null);
    setResult(null);
    setDeleted(null);
    try {
      const trimmed = mapping.trim();
      setResult(
        await api.imports.create(
          file,
          broker,
          broker === "generic" && trimmed ? trimmed : undefined,
          broker === "webull" ? timezone : undefined,
        ),
      );
      batches.reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function removeBatch(id: number) {
    setBusy(true);
    setError(null);
    setResult(null);
    setDeleted(null);
    setConfirmDelete(null);
    try {
      setDeleted(await api.imports.delete(id));
      batches.reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  function onDrop(event: React.DragEvent) {
    event.preventDefault();
    setDragging(false);
    const file = event.dataTransfer.files?.[0];
    if (file) void send(file);
  }

  return (
    <>
      <PageHeader title="Import" sub="idempotent — re-importing is safe" />

      <div className="grid gap-3 lg:grid-cols-[1fr_360px]">
        <div
          role="button"
          tabIndex={0}
          aria-label="Drop a CSV file or click to browse"
          onClick={() => fileInput.current?.click()}
          onKeyDown={(e) => e.key === "Enter" && fileInput.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          className={`flex min-h-72 cursor-pointer flex-col items-center justify-center border-2 border-dashed px-6 py-10 text-center transition-colors ${
            dragging ? "border-accent bg-accent/5" : "border-baseline bg-panel hover:border-muted"
          }`}
        >
          <span className="num text-[40px] leading-none text-baseline">⇣</span>
          <p className="mt-4 text-[14px] text-ink-2">
            {busy ? "Working…" : "Drop a broker CSV here, or click to browse"}
          </p>
          <p className="num mt-2 text-[11px] text-muted">
            parsed as <span className="text-accent">{broker}</span> · fills dedup on content hash
          </p>
          <input
            ref={fileInput}
            type="file"
            accept=".csv,text/csv"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void send(file);
              e.target.value = "";
            }}
          />
        </div>

        <div className="flex flex-col gap-3">
          <Panel title="broker">
            <div className="flex flex-col gap-px p-2">
              {(["webull", "generic"] as const).map((b) => (
                <label
                  key={b}
                  className={`flex cursor-pointer items-baseline gap-3 px-3 py-2.5 transition-colors ${
                    broker === b ? "bg-panel-2 text-ink" : "text-ink-2 hover:bg-panel-2"
                  }`}
                >
                  <input
                    type="radio"
                    name="broker"
                    checked={broker === b}
                    onChange={() => setBroker(b)}
                    className="accent-[#3987e5]"
                  />
                  <span className="num text-[13px] font-medium">{b}</span>
                  <span className="text-[11px] text-muted">
                    {b === "webull" ? "orders export (US stocks)" : "any CSV + column mapping"}
                  </span>
                </label>
              ))}
            </div>
          </Panel>

          {broker === "webull" ? (
            <Panel title="export timezone">
              <div className="p-3">
                <select
                  value={timezone}
                  onChange={(e) => setTimezone(e.target.value)}
                  className="num w-full border border-hairline bg-panel-2 p-2 text-[12px] text-ink focus:border-accent focus:outline-none"
                >
                  {TIMEZONES.map(([zone, label]) => (
                    <option key={zone} value={zone}>
                      {zone} · {label}
                    </option>
                  ))}
                </select>
                <p className="mt-2 text-[11px] leading-relaxed text-muted">
                  Webull exports use your <em>device&apos;s</em> local time, not Eastern — pick
                  the timezone the exporting device was in.
                </p>
              </div>
            </Panel>
          ) : (
            <Panel title="column mapping · optional json">
              <div className="p-3">
                <textarea
                  className="num h-40 w-full resize-y border border-hairline bg-panel-2 p-2 text-[11px] leading-relaxed text-ink placeholder:text-muted focus:border-accent focus:outline-none"
                  value={mapping}
                  onChange={(e) => setMapping(e.target.value)}
                  placeholder={MAPPING_PLACEHOLDER}
                  spellCheck={false}
                />
                <p className="mt-2 text-[11px] leading-relaxed text-muted">
                  Leave empty if your CSV already uses <span className="num">symbol, side, qty,
                  price, executed_at</span> (ISO-8601 UTC).
                </p>
              </div>
            </Panel>
          )}
        </div>
      </div>

      {error ? (
        <div className="mt-3">
          <ErrorNote message={error} />
        </div>
      ) : null}

      {result ? (
        <div className="mt-3">
          <Panel title={`batch #${result.batch_id} · ${result.filename}`}>
            <div className="grid grid-cols-2 gap-4 px-4 py-4 md:grid-cols-4">
              <div>
                <span className="label block">fills inserted</span>
                <span className="num mt-1 block text-[22px] text-gain">{result.inserted}</span>
              </div>
              <div>
                <span className="label block">duplicates skipped</span>
                <span className="num mt-1 block text-[22px] text-ink-2">
                  {result.skipped_duplicates}
                </span>
              </div>
              <div>
                <span className="label block">trades rebuilt</span>
                <span className="num mt-1 block text-[22px]">{result.trades_rebuilt}</span>
              </div>
              <div>
                <span className="label block">violations</span>
                <span
                  className={`num mt-1 block text-[22px] ${
                    !result.audited
                      ? "text-muted"
                      : result.violations_recorded > 0
                        ? "text-loss"
                        : "text-gain"
                  }`}
                >
                  {result.audited ? result.violations_recorded : "not audited"}
                </span>
              </div>
            </div>
            <div className="border-t border-hairline px-4 py-3">
              {result.skipped_unfilled > 0 ? (
                <p className="num mb-2 text-[11px] text-muted">
                  {result.skipped_unfilled} unfilled order row
                  {result.skipped_unfilled === 1 ? "" : "s"} (cancelled / pending / rejected)
                  skipped
                </p>
              ) : null}
              <Link href="/trades" className="label text-accent hover:underline">
                view trades →
              </Link>
              {result.violations_recorded > 0 ? (
                <Link href="/discipline" className="label ml-6 text-loss hover:underline">
                  review violations →
                </Link>
              ) : null}
            </div>
          </Panel>
        </div>
      ) : null}

      {deleted ? (
        <div className="mt-3">
          <Panel title={`batch #${deleted.batch_id} deleted · ${deleted.filename}`}>
            <p className="num px-4 py-3 text-[12px] text-ink-2">
              {deleted.fills_deleted} fill{deleted.fills_deleted === 1 ? "" : "s"} removed ·{" "}
              {deleted.trades_rebuilt} trade{deleted.trades_rebuilt === 1 ? "" : "s"} regrouped
              from what remains ·{" "}
              {deleted.audited
                ? `${deleted.violations_recorded} violation${
                    deleted.violations_recorded === 1 ? "" : "s"
                  } after re-audit`
                : "not re-audited (no rules.yaml)"}
            </p>
          </Panel>
        </div>
      ) : null}

      <div className="mt-3">
        <Panel title="import batches">
          {batches.error ? (
            <div className="p-3">
              <ErrorNote message={batches.error} />
            </div>
          ) : !batches.data || batches.data.length === 0 ? (
            <Empty note={batches.loading ? "loading…" : "no imports yet"} />
          ) : (
            <table className="w-full text-[12px]">
              <tbody>
                {batches.data.map((batch) => (
                  <tr key={batch.id} className="border-b border-hairline last:border-b-0">
                    <td className="num px-4 py-2.5 text-muted">#{batch.id}</td>
                    <td className="px-2 py-2.5">{batch.filename}</td>
                    <td className="num px-2 py-2.5 text-ink-2">{batch.broker}</td>
                    <td className="num px-2 py-2.5 text-muted">
                      {sessionStamp(batch.imported_at)} ET
                    </td>
                    <td className="num px-2 py-2.5 text-ink-2">
                      {batch.inserted_count} fill{batch.inserted_count === 1 ? "" : "s"}
                    </td>
                    <td className="px-4 py-2.5 text-right">
                      {confirmDelete === batch.id ? (
                        <>
                          <button
                            onClick={() => void removeBatch(batch.id)}
                            disabled={busy}
                            className="label text-loss hover:underline disabled:opacity-50"
                          >
                            confirm delete
                          </button>
                          <button
                            onClick={() => setConfirmDelete(null)}
                            className="label ml-4 text-muted hover:underline"
                          >
                            keep
                          </button>
                        </>
                      ) : (
                        <button
                          onClick={() => setConfirmDelete(batch.id)}
                          disabled={busy}
                          className="label text-muted hover:text-loss hover:underline disabled:opacity-50"
                        >
                          delete
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <p className="border-t border-hairline px-4 py-2.5 text-[11px] text-muted">
            Deleting a batch removes its fills, regroups affected trades, and re-audits — use it
            to redo an import made with the wrong timezone.
          </p>
        </Panel>
      </div>
    </>
  );
}
