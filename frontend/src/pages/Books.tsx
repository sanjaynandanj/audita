import { useCallback, useEffect, useRef, useState } from "react";
import Nav from "../components/Nav";
import AppTabs from "../components/AppTabs";
import {
  type Account,
  type CatRule,
  type LedgerResponse,
  type LedgerTxn,
  confirmTxn,
  getCoa,
  getLedger,
  getRules,
  importStatement,
  inr,
  ledgerCsvUrl,
} from "../lib/api";

function currentPeriod(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

const SOURCE_BADGE: Record<string, string> = {
  rule: "bg-ledger/10 text-ledger",
  human: "bg-ink/10 text-ink",
  llm: "bg-rule/60 text-sub",
};

function PendingRow({
  txn,
  period,
  accounts,
  actor,
  onConfirmed,
  onError,
}: {
  txn: LedgerTxn;
  period: string;
  accounts: Account[];
  actor: string;
  onConfirmed: (r: LedgerResponse) => void;
  onError: (msg: string) => void;
}) {
  const [account, setAccount] = useState(txn.suggested_account || "");
  const [rulePattern, setRulePattern] = useState("");
  const [busy, setBusy] = useState(false);

  async function confirm() {
    setBusy(true);
    try {
      const r = await confirmTxn(period, txn.txn_id, account, actor.trim(), rulePattern.trim());
      onConfirmed(r);
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <tr className="border-b border-rule align-top">
      <td className="py-2.5 pr-4 font-mono text-xs whitespace-nowrap">{txn.txn_date}</td>
      <td className="py-2.5 pr-4">
        <div className="text-[13.5px] font-medium">{txn.description}</div>
        {txn.ref && <div className="font-mono text-[11px] text-sub">{txn.ref}</div>}
        {txn.suggested_account && (
          <div className="mt-0.5 text-[11px] italic text-sub">
            agent suggests {txn.suggested_account}
            {txn.confidence && ` · confidence ${txn.confidence}`} — advice only, never counted
          </div>
        )}
      </td>
      <td className="py-2.5 pr-4 text-right font-mono tabular-nums whitespace-nowrap">
        {inr(txn.amount)}
      </td>
      <td className="py-2.5 pr-4">
        <select
          value={account}
          onChange={(e) => setAccount(e.target.value)}
          className="w-full max-w-[220px] border-0 border-b border-rule-2 bg-transparent px-0 py-1 text-[13px] outline-none focus:border-ink"
        >
          <option value="">— pick account —</option>
          {accounts.map((a) => (
            <option key={a.code} value={a.code}>
              {a.code} · {a.name}
            </option>
          ))}
        </select>
        <input
          value={rulePattern}
          onChange={(e) => setRulePattern(e.target.value)}
          placeholder="save as rule: description contains…"
          className="mt-1 w-full max-w-[220px] border-0 border-b border-rule bg-transparent px-0 py-1 text-[11px] outline-none placeholder:text-sub/70 focus:border-ink"
        />
      </td>
      <td className="py-2.5 text-right">
        <button
          onClick={confirm}
          disabled={busy || !account || !actor.trim()}
          className="bg-ink px-4 py-1.5 text-[11px] font-bold uppercase tracking-[0.1em] text-paper transition-opacity disabled:opacity-40"
        >
          {busy ? "…" : "Confirm"}
        </button>
      </td>
    </tr>
  );
}

export default function Books() {
  const [period, setPeriod] = useState(currentPeriod());
  const [data, setData] = useState<LedgerResponse | null>(null);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [rules, setRules] = useState<CatRule[]>([]);
  const [actor, setActor] = useState("");
  const [error, setError] = useState("");
  const [uploading, setUploading] = useState(false);
  const [showRules, setShowRules] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const refresh = useCallback(() => {
    getLedger(period)
      .then(setData)
      .catch((e: Error) => setError(e.message));
    getRules()
      .then((r) => setRules(r.rules))
      .catch(() => undefined);
  }, [period]);

  useEffect(() => {
    getCoa()
      .then((r) => setAccounts(r.accounts))
      .catch((e: Error) => setError(e.message));
  }, []);
  useEffect(refresh, [refresh]);

  async function onUpload(files: FileList | null) {
    if (!files?.length) return;
    setUploading(true);
    setError("");
    try {
      for (const file of Array.from(files)) {
        setData(await importStatement(period, file));
      }
      refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  const txns = data?.ledger.txns ?? [];
  const pending = txns.filter((t) => t.status === "pending");
  const categorized = txns.filter((t) => t.status !== "pending");
  const summary = data?.summary;
  const names = data?.account_names ?? {};

  return (
    <div className="min-h-screen bg-paper pb-24 text-ink">
      <Nav />
      <AppTabs />
      <main className="mx-auto max-w-5xl px-6 pt-10">
        <div className="flex flex-wrap items-end justify-between gap-6 border-b-2 border-ink pb-5">
          <div>
            <div className="label-caps">Bookkeeping Agent · transaction coding</div>
            <h1 className="mt-2 text-3xl font-extrabold tracking-tight">Books {period}</h1>
          </div>
          <div className="flex items-end gap-6">
            <div>
              <label className="label-caps block">Working as</label>
              <input
                value={actor}
                onChange={(e) => setActor(e.target.value)}
                placeholder="Your name"
                className="border-0 border-b border-rule-2 bg-transparent px-0 py-1.5 text-sm outline-none focus:border-ink"
              />
            </div>
            <div>
              <label className="label-caps block">Period</label>
              <input
                type="month"
                value={period}
                onChange={(e) => setPeriod(e.target.value)}
                className="border-0 border-b border-rule-2 bg-transparent px-0 py-1.5 font-mono text-sm outline-none focus:border-ink"
              />
            </div>
          </div>
        </div>

        <label className="mt-8 flex cursor-pointer flex-col items-center gap-2 border-2 border-dashed border-rule-2 px-6 py-10 text-center transition-colors hover:border-ink hover:bg-card">
          <input
            ref={fileRef}
            type="file"
            multiple
            accept=".csv,.xlsx,.xls"
            className="hidden"
            onChange={(e) => onUpload(e.target.files)}
          />
          <span className="text-[14.5px] font-semibold">
            {uploading ? "Importing…" : "Drop a bank statement here, or click to choose"}
          </span>
          <span className="text-[12px] text-sub">
            CSV · XLSX — your rules auto-code what they match; everything else queues for a named
            human. LLM suggestions are advice only and never enter a total.
          </span>
        </label>

        {error && (
          <div className="mt-5 border-l-2 border-oxide bg-oxide/[.05] px-4 py-3 text-[13px] font-medium text-oxide-2">
            {error}
          </div>
        )}

        {summary && summary.txn_count > 0 && (
          <div className="mt-8 grid grid-cols-2 gap-px border border-rule bg-rule sm:grid-cols-4">
            {[
              ["Transactions", String(summary.txn_count)],
              ["Coded by rules", String(summary.coded_count)],
              ["Human-confirmed", String(summary.confirmed_count)],
              ["Awaiting review", String(summary.pending_count)],
            ].map(([label, value]) => (
              <div key={label} className="bg-paper px-4 py-3">
                <div className="label-caps">{label}</div>
                <div className="mt-1 font-mono text-2xl font-bold tabular-nums">{value}</div>
              </div>
            ))}
          </div>
        )}

        <section className="mt-10">
          <h2 className="text-[13px] font-bold uppercase tracking-[0.1em]">
            Review queue <span className="ml-1 font-mono text-sub">({pending.length})</span>
          </h2>
          {pending.length === 0 ? (
            <p className="mt-3 text-[13px] text-sub">
              Nothing waiting. Import a statement above — rule misses land here.
            </p>
          ) : (
            <table className="mt-3 w-full border-collapse text-[13px]">
              <thead>
                <tr className="border-b-2 border-ink text-left">
                  <th className="py-2 pr-4 label-caps">Date</th>
                  <th className="py-2 pr-4 label-caps">Narration</th>
                  <th className="py-2 pr-4 text-right label-caps">Amount</th>
                  <th className="py-2 pr-4 label-caps">Account</th>
                  <th className="py-2 label-caps"></th>
                </tr>
              </thead>
              <tbody>
                {pending.map((t) => (
                  <PendingRow
                    key={t.txn_id}
                    txn={t}
                    period={period}
                    accounts={accounts}
                    actor={actor}
                    onConfirmed={(r) => {
                      setData(r);
                      getRules().then((x) => setRules(x.rules)).catch(() => undefined);
                    }}
                    onError={setError}
                  />
                ))}
              </tbody>
            </table>
          )}
          {pending.length > 0 && !actor.trim() && (
            <p className="mt-2 text-[12px] italic text-sub">
              Enter your name under “Working as” to confirm categorizations.
            </p>
          )}
        </section>

        <section className="mt-12">
          <div className="flex items-baseline justify-between">
            <h2 className="text-[13px] font-bold uppercase tracking-[0.1em]">
              Categorized ledger{" "}
              <span className="ml-1 font-mono text-sub">({categorized.length})</span>
            </h2>
            {categorized.length > 0 && (
              <a
                href={ledgerCsvUrl(period)}
                className="text-[12px] font-bold uppercase tracking-[0.1em] underline decoration-rule-2 underline-offset-4 hover:decoration-ink"
              >
                Export ledger CSV
              </a>
            )}
          </div>
          {summary && Object.keys(summary.accounts).length > 0 && (
            <table className="mt-3 w-full border-collapse text-[13px]">
              <thead>
                <tr className="border-b-2 border-ink text-left">
                  <th className="py-2 pr-4 label-caps">Account</th>
                  <th className="py-2 pr-4 text-right label-caps">Entries</th>
                  <th className="py-2 text-right label-caps">Net</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(summary.accounts).map(([code, b]) => (
                  <tr key={code} className="border-b border-rule">
                    <td className="py-2.5 pr-4 font-medium">
                      <span className="font-mono text-xs text-sub">{code}</span>{" "}
                      {names[code] ?? ""}
                    </td>
                    <td className="py-2.5 pr-4 text-right font-mono tabular-nums">{b.count}</td>
                    <td className="py-2.5 text-right font-mono tabular-nums">{inr(b.total)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {categorized.length > 0 && (
            <details className="mt-4">
              <summary className="cursor-pointer text-[12px] font-bold uppercase tracking-[0.1em] text-sub hover:text-ink">
                Every entry ({categorized.length})
              </summary>
              <table className="mt-3 w-full border-collapse text-[13px]">
                <tbody>
                  {categorized.map((t) => (
                    <tr key={t.txn_id} className="border-b border-rule">
                      <td className="py-2 pr-4 font-mono text-xs whitespace-nowrap">{t.txn_date}</td>
                      <td className="py-2 pr-4">{t.description}</td>
                      <td className="py-2 pr-4 text-right font-mono tabular-nums whitespace-nowrap">
                        {inr(t.amount)}
                      </td>
                      <td className="py-2 pr-4 whitespace-nowrap">
                        <span className="font-mono text-xs text-sub">{t.account_code}</span>{" "}
                        {names[t.account_code] ?? ""}
                      </td>
                      <td className="py-2 whitespace-nowrap">
                        <span
                          className={`px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.1em] ${SOURCE_BADGE[t.source] ?? "bg-rule/60 text-sub"}`}
                        >
                          {t.source === "human" ? t.confirmed_by || "human" : t.source}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
          )}
        </section>

        <section className="mt-12">
          <button
            onClick={() => setShowRules(!showRules)}
            className="text-[13px] font-bold uppercase tracking-[0.1em] hover:underline"
          >
            Rules <span className="ml-1 font-mono text-sub">({rules.length})</span>{" "}
            {showRules ? "▾" : "▸"}
          </button>
          {showRules && (
            <table className="mt-3 w-full border-collapse text-[13px]">
              <thead>
                <tr className="border-b-2 border-ink text-left">
                  <th className="py-2 pr-4 label-caps">When</th>
                  <th className="py-2 pr-4 label-caps">Account</th>
                  <th className="py-2 pr-4 label-caps">Created by</th>
                  <th className="py-2 text-right label-caps">Priority</th>
                </tr>
              </thead>
              <tbody>
                {rules.map((r) => (
                  <tr key={r.rule_id} className="border-b border-rule">
                    <td className="py-2.5 pr-4">
                      {r.field} contains{" "}
                      <span className="font-mono text-xs">“{r.contains}”</span>
                    </td>
                    <td className="py-2.5 pr-4">
                      <span className="font-mono text-xs text-sub">{r.account_code}</span>{" "}
                      {names[r.account_code] ?? ""}
                    </td>
                    <td className="py-2.5 pr-4">{r.created_by}</td>
                    <td className="py-2.5 text-right font-mono tabular-nums">{r.priority}</td>
                  </tr>
                ))}
                {rules.length === 0 && (
                  <tr>
                    <td colSpan={4} className="py-3 text-[13px] text-sub">
                      No rules yet — confirm a transaction with “save as rule” to teach the agent.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          )}
        </section>

        <p className="mt-8 text-[12px] leading-relaxed text-sub">
          Account totals include only rule-coded and human-confirmed entries. Suggestions from the
          LLM are advice attached to pending rows — they never categorize anything and never enter
          a number. Every import, confirmation and rule lands in the append-only event log.
        </p>
      </main>
    </div>
  );
}
