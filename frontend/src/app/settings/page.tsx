"use client";

import { useEffect, useState } from "react";
import { api, type RuleParams } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { ErrorNote, Loading, PageHeader, Panel } from "@/components/ui";

const inputCls =
  "num h-8 border border-hairline bg-panel-2 px-2 text-[12px] text-ink placeholder:text-muted focus:border-accent focus:outline-none";

/** Sensible starting params when enabling a rule that isn't in the file yet. */
const RULE_TEMPLATES: Record<string, Record<string, string>> = {
  max_trades_per_day: { n: "6" },
  stop_required: { within_minutes: "5" },
  max_risk_per_trade: { pct_of_account: "1.0" },
  blocked_entry_window: { start: "09:30", end: "09:35" },
  revenge_trade: { cooldown_minutes: "15", size_multiplier: "1.5" },
  max_daily_loss: { amount: "500" },
};

const RULE_HELP: Record<string, string> = {
  max_trades_per_day: "No more than n round trips entered per session day.",
  stop_required: "A planned stop must be recorded within N minutes of entry.",
  max_risk_per_trade: "|entry − stop| × size may not exceed this % of account size.",
  blocked_entry_window: "No entries inside this ET window (end is allowed).",
  revenge_trade: "Re-entry within the cooldown after a loss at ≥ multiplier × its size.",
  max_daily_loss: "Flags every entry after daily realized PnL breaches −amount (or r × r_value).",
};

interface RuleDraft {
  present: boolean;
  enabled: boolean;
  severity: "violation" | "warn" | "info";
  params: Record<string, string>;
}

function draftsFromFile(
  rules: Record<string, RuleParams>,
  available: string[],
): Record<string, RuleDraft> {
  const drafts: Record<string, RuleDraft> = {};
  for (const id of available) {
    const body = rules[id];
    if (body === undefined) {
      drafts[id] = {
        present: false,
        enabled: false,
        severity: "violation",
        params: { ...(RULE_TEMPLATES[id] ?? {}) },
      };
      continue;
    }
    const params: Record<string, string> = {};
    for (const [key, value] of Object.entries(body)) {
      if (key !== "enabled" && key !== "severity") params[key] = String(value);
    }
    drafts[id] = {
      present: true,
      enabled: body.enabled !== false,
      severity: (body.severity as RuleDraft["severity"]) ?? "violation",
      params,
    };
  }
  return drafts;
}

export default function SettingsPage() {
  const { data, error, loading, reload } = useApi(() => api.rules.get());
  const [account, setAccount] = useState({ account_size: "", timezone: "", r_value: "" });
  const [drafts, setDrafts] = useState<Record<string, RuleDraft>>({});
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveNote, setSaveNote] = useState<string | null>(null);

  useEffect(() => {
    if (!data) return;
    setAccount({
      account_size: String(data.account.account_size ?? ""),
      timezone: String(data.account.timezone ?? "America/New_York"),
      r_value: data.account.r_value != null ? String(data.account.r_value) : "",
    });
    setDrafts(draftsFromFile(data.rules, data.available_rules));
  }, [data]);

  function patchRule(id: string, patch: Partial<RuleDraft>) {
    setDrafts((prev) => ({ ...prev, [id]: { ...prev[id], ...patch } }));
  }

  async function save() {
    setSaving(true);
    setSaveError(null);
    setSaveNote(null);
    const rules: Record<string, RuleParams> = {};
    for (const [id, draft] of Object.entries(drafts)) {
      if (!draft.present && !draft.enabled) continue; // never in file, still off
      const body: RuleParams = { ...draft.params };
      if (!draft.enabled) body.enabled = false;
      if (draft.severity !== "violation") body.severity = draft.severity;
      rules[id] = body;
    }
    const accountBody: Record<string, unknown> = {
      account_size: account.account_size.trim(),
      timezone: account.timezone.trim() || "America/New_York",
    };
    if (account.r_value.trim() !== "") accountBody.r_value = account.r_value.trim();
    try {
      const response = await api.rules.put({ account: accountBody, rules });
      setSaveNote(
        `Saved. Re-audit recorded ${response.violations_recorded} violation${
          response.violations_recorded === 1 ? "" : "s"
        } across all trades.`,
      );
      reload();
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <Loading />;
  if (error) return <ErrorNote message={error} />;
  if (!data) return null;

  return (
    <>
      <PageHeader title="Settings" sub="rules.yaml · validated before write" />

      <Panel title="account">
        <div className="flex flex-wrap gap-4 px-4 py-4">
          <label className="flex flex-col gap-1">
            <span className="label">account size ($)</span>
            <input
              className={`${inputCls} w-36`}
              value={account.account_size}
              onChange={(e) => setAccount({ ...account, account_size: e.target.value })}
              inputMode="decimal"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="label">timezone (iana)</span>
            <input
              className={`${inputCls} w-52`}
              value={account.timezone}
              onChange={(e) => setAccount({ ...account, timezone: e.target.value })}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="label">r value ($ per 1R, optional)</span>
            <input
              className={`${inputCls} w-36`}
              value={account.r_value}
              onChange={(e) => setAccount({ ...account, r_value: e.target.value })}
              placeholder="150"
              inputMode="decimal"
            />
          </label>
        </div>
      </Panel>

      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        {data.available_rules.map((id) => {
          const draft = drafts[id];
          if (!draft) return null;
          return (
            <Panel key={id} className={draft.enabled ? "" : "opacity-60"}>
              <div className="flex items-center gap-3 border-b border-hairline px-4 py-2.5">
                <label className="flex cursor-pointer items-center gap-2.5">
                  <input
                    type="checkbox"
                    checked={draft.enabled}
                    onChange={(e) => patchRule(id, { enabled: e.target.checked })}
                    className="accent-[#3987e5]"
                  />
                  <span className="num text-[13px] font-semibold">{id}</span>
                </label>
                <select
                  className={`${inputCls} ml-auto h-7 text-[11px]`}
                  value={draft.severity}
                  onChange={(e) =>
                    patchRule(id, { severity: e.target.value as RuleDraft["severity"] })
                  }
                >
                  <option value="violation">violation</option>
                  <option value="warn">warn</option>
                  <option value="info">info</option>
                </select>
              </div>
              <div className="px-4 py-3">
                <p className="text-[12px] leading-snug text-muted">{RULE_HELP[id] ?? ""}</p>
                <div className="mt-3 flex flex-wrap gap-3">
                  {Object.entries(draft.params).map(([key, value]) => (
                    <label key={key} className="flex flex-col gap-1">
                      <span className="label">{key}</span>
                      <input
                        className={`${inputCls} w-28`}
                        value={value}
                        onChange={(e) =>
                          patchRule(id, { params: { ...draft.params, [key]: e.target.value } })
                        }
                      />
                    </label>
                  ))}
                </div>
              </div>
            </Panel>
          );
        })}
      </div>

      {saveError ? (
        <div className="mt-3">
          <ErrorNote message={saveError} />
        </div>
      ) : null}

      <div className="mt-4 flex items-center gap-4 border-t border-hairline pt-4">
        <button
          type="button"
          onClick={save}
          disabled={saving}
          className="label border border-accent bg-accent/10 px-5 py-2.5 text-accent transition-colors hover:bg-accent hover:text-page disabled:opacity-50"
        >
          {saving ? "saving…" : "validate + save rules.yaml"}
        </button>
        {saveNote ? <span className="label text-gain">{saveNote}</span> : null}
        <span className="ml-auto text-[11px] text-muted">
          Saving rewrites rules.yaml (hand-written comments are lost) and re-audits every trade.
        </span>
      </div>
    </>
  );
}
