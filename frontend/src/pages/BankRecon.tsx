import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import Nav from "../components/Nav";
import AppTabs from "../components/AppTabs";
import CountUp from "../components/CountUp";
import { type BankItem, type BankReport, getBankReport, inr, runBankRec } from "../lib/api";

function DropZone({ label, hint, accept, file, onFile }: {
  label: string; hint: string; accept: string; file: File | null; onFile: (f: File) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);
  return (
    <button
      type="button"
      onClick={() => input.current?.click()}
      onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
      onDragLeave={() => setDrag(false)}
      onDrop={(e) => {
        e.preventDefault(); setDrag(false);
        if (e.dataTransfer.files[0]) onFile(e.dataTransfer.files[0]);
      }}
      className={`border border-dashed p-7 text-left transition-colors ${
        file ? "border-ledger bg-ledger/[.04]" : drag ? "border-ink bg-ink/[.03]" : "border-rule-2 hover:border-ink"
      }`}
    >
      <input ref={input} type="file" accept={accept} className="hidden"
             onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])} />
      <div className="label-caps">{label}</div>
      <div className="mt-1.5 text-[13px] text-sub">{hint}</div>
      {file ? (
        <div className="mt-3 break-all font-mono text-xs font-medium text-ledger">✓ {file.name}</div>
      ) : (
        <div className="mt-3 font-mono text-xs text-sub">drop file or click to browse</div>
      )}
    </button>
  );
}

function BankSideCell({ side }: { side: BankItem["bank"] }) {
  if (!side) return <span className="text-sub">—</span>;
  return (
    <div>
      <div className="text-[13px] font-medium">{side.description || "—"}</div>
      <div className="mt-0.5 font-mono text-[11px] text-sub">{side.txn_date} · {side.ref || "no ref"}</div>
      <div className="font-mono text-[10px] text-rule-2">{side.source_ref}</div>
    </div>
  );
}

const TH = "px-3 py-2.5 text-left text-[10px] font-bold uppercase tracking-[0.14em] text-sub border-b border-rule";
const TD = "px-3 py-3 align-top border-b border-rule text-[13px]";

function ItemTable({ items, sideLabel, sideKey }: {
  items: BankItem[]; sideLabel: string; sideKey: "bank" | "books";
}) {
  return (
    <table className="w-full border-collapse">
      <thead><tr>
        <th className={TH}>Ref</th><th className={TH}>{sideLabel}</th>
        <th className={`${TH} text-right`}>Amount (₹)</th><th className={TH}>Remarks</th>
      </tr></thead>
      <tbody>
        {items.map((i) => (
          <tr key={i.item_id}>
            <td className={`${TD} font-mono text-xs`}>{i.item_id}</td>
            <td className={TD}><BankSideCell side={i[sideKey]} /></td>
            <td className={`${TD} text-right font-mono font-semibold tabular-nums ${Number(i.amount) < 0 ? "text-oxide" : "text-ledger"}`}>
              {Number(i.amount).toLocaleString("en-IN")}
            </td>
            <td className={`${TD} text-xs text-sub`}>{i.reason}</td>
          </tr>
        ))}
        {!items.length && <tr><td className={`${TD} py-6 text-center text-sub`} colSpan={4}>None.</td></tr>}
      </tbody>
    </table>
  );
}

export function BankReportPage() {
  const { token = "" } = useParams();
  const [report, setReport] = useState<BankReport | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getBankReport(token).then((r) => setReport(r.report)).catch((e: Error) => setError(e.message));
  }, [token]);

  if (error) {
    return (
      <div className="min-h-screen bg-paper"><Nav /><AppTabs />
        <div className="mx-auto mt-24 max-w-md border border-oxide/40 bg-card p-10 text-center">
          <div className="text-xl font-bold text-oxide">Cannot open report</div>
          <p className="mt-3 text-sm text-sub">{error}</p>
        </div>
      </div>
    );
  }
  if (!report) {
    return (
      <div className="min-h-screen bg-paper"><Nav /><AppTabs />
        <div className="mt-32 text-center font-mono text-xs text-sub">Loading…</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-paper pb-24 text-ink">
      <Nav /><AppTabs />
      <main className="mx-auto max-w-6xl px-6 pt-10">
        <div className="border-b-2 border-ink pb-5">
          <div className="label-caps">Bank Reconciliation Statement</div>
          <h1 className="mt-2 text-3xl font-extrabold tracking-tight">{report.client_name}</h1>
          <div className="mt-1 font-mono text-xs text-sub">
            {report.period_note && <>{report.period_note} · </>}
            report {report.report_id} · prepared {report.created_at.slice(0, 10)}
          </div>
        </div>

        <div className="mt-8 grid grid-cols-2 gap-y-8 border-y border-rule py-6 md:grid-cols-4 md:divide-x md:divide-rule">
          <div className="md:pr-8">
            <div className="label-caps">Unrecorded in books</div>
            <div className="mt-2 font-mono text-[26px] font-semibold tabular-nums text-oxide">
              <CountUp value={report.unrecorded_total} />
            </div>
            <div className="mt-1 text-[11px] text-sub">{report.unrecorded.length} bank entries missing from books</div>
          </div>
          <div className="md:px-8">
            <div className="label-caps">Uncleared / in transit</div>
            <div className="mt-2 font-mono text-[26px] font-semibold tabular-nums">
              <CountUp value={report.uncleared_total} />
            </div>
            <div className="mt-1 text-[11px] text-sub">{report.uncleared.length} book entries not yet in bank</div>
          </div>
          <div className="md:px-8">
            <div className="label-caps">Matched clean</div>
            <div className="mt-2 font-mono text-[26px] font-semibold tabular-nums">{report.matched_count}</div>
            <div className="mt-1 text-[11px] text-sub">{inr(report.matched_total)} reconciled</div>
          </div>
          <div className="md:pl-8">
            <div className="label-caps">Items to action</div>
            <div className="mt-2 font-mono text-[26px] font-semibold tabular-nums text-oxide">
              {report.unrecorded.length + report.uncleared.length}
            </div>
            <div className="mt-1 text-[11px] text-sub">journal entries / follow-ups</div>
          </div>
        </div>

        <section className="mt-12">
          <div className="flex items-baseline gap-3 border-b-2 border-ink pb-2">
            <span className="font-mono text-sm font-semibold text-oxide">Schedule A</span>
            <h2 className="text-lg font-bold">In bank, not in books — pass these entries</h2>
            <span className="ml-auto font-mono text-xs text-sub">{report.unrecorded.length} item(s)</span>
          </div>
          <ItemTable items={report.unrecorded} sideLabel="Per bank statement" sideKey="bank" />
        </section>

        <section className="mt-12">
          <div className="flex items-baseline gap-3 border-b-2 border-ink pb-2">
            <span className="font-mono text-sm font-semibold text-oxide">Schedule B</span>
            <h2 className="text-lg font-bold">In books, not in bank — uncleared & in transit</h2>
            <span className="ml-auto font-mono text-xs text-sub">{report.uncleared.length} item(s)</span>
          </div>
          <ItemTable items={report.uncleared} sideLabel="Per books (bank ledger)" sideKey="books" />
        </section>
      </main>
    </div>
  );
}

export default function BankRecon() {
  const nav = useNavigate();
  const [clientName, setClientName] = useState("");
  const [period, setPeriod] = useState("");
  const [stmt, setStmt] = useState<File | null>(null);
  const [ledger, setLedger] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!stmt || !ledger) { setError("Both files are required."); return; }
    setBusy(true); setError("");
    const form = new FormData();
    form.append("client_name", clientName);
    form.append("period_note", period);
    form.append("statement_file", stmt);
    form.append("ledger_file", ledger);
    try {
      const { token } = await runBankRec(form);
      nav(`/app/bank/r/${encodeURIComponent(token)}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Reconciliation failed.");
      setBusy(false);
    }
  }

  const inputCls =
    "w-full border-0 border-b border-rule-2 bg-transparent px-0 py-2 text-[15px] outline-none transition-colors focus:border-ink";

  return (
    <div className="min-h-screen bg-paper text-ink">
      <Nav /><AppTabs />
      <main className="mx-auto max-w-xl px-6 py-14">
        <div className="label-caps">Bank Recon Agent</div>
        <h1 className="mt-2 text-3xl font-extrabold tracking-tight">Reconcile a bank account</h1>
        <p className="mt-3 text-[14px] leading-relaxed text-sub">
          Bank statement vs your Tally bank ledger. Unrecorded charges, uncleared cheques,
          deposits in transit — the classic BRS, done by the agent.
        </p>

        <form onSubmit={submit} className="mt-9 border border-rule-2 bg-card p-8 shadow-[3px_3px_0_0_rgba(23,20,14,0.1)]">
          <label className="label-caps block">Client / business name</label>
          <input required value={clientName} onChange={(e) => setClientName(e.target.value)}
                 placeholder="Acme Textiles Pvt Ltd" className={inputCls} />
          <label className="label-caps mt-7 block">Period <span className="normal-case tracking-normal">— optional</span></label>
          <input value={period} onChange={(e) => setPeriod(e.target.value)}
                 placeholder="April 2026 · HDFC CA-0042" className={inputCls} />

          <div className="mt-8 grid gap-4 sm:grid-cols-2">
            <DropZone label="Bank statement" hint="CSV / XLSX from netbanking"
                      accept=".csv,.xlsx,.xls" file={stmt} onFile={setStmt} />
            <DropZone label="Bank ledger (books)" hint="Tally ledger CSV / XLSX export"
                      accept=".csv,.xlsx,.xls" file={ledger} onFile={setLedger} />
          </div>

          {error && (
            <div className="mt-6 border-l-2 border-oxide bg-oxide/[.05] px-4 py-3 text-[13px] font-medium text-oxide-2">
              {error}
            </div>
          )}

          <button disabled={busy}
                  className="mt-8 w-full border border-ink bg-ink py-3.5 text-[13px] font-bold uppercase tracking-[0.08em] text-paper transition-colors hover:bg-card hover:text-ink disabled:opacity-50">
            {busy ? "Agent at work…" : "Run bank reconciliation"}
          </button>
        </form>
      </main>
    </div>
  );
}
