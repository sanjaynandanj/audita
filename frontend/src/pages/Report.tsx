import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import Nav from "../components/Nav";
import AppTabs from "../components/AppTabs";
import CountUp from "../components/CountUp";
import {
  type ExceptionItem, type Report, type TrailEvent,
  getReport, inr, verifyException,
} from "../lib/api";

function SideCell({ side }: { side: ExceptionItem["books"] }) {
  if (!side) return <span className="text-sub">—</span>;
  return (
    <div>
      <div className="font-mono text-xs font-medium">{side.invoice_no}</div>
      <div className="mt-0.5 text-[11px] text-sub">
        {side.invoice_date} · tax {inr(side.total_tax)} · taxable {inr(side.taxable_value)}
      </div>
      <div className="font-mono text-[10px] text-rule-2">{side.source_ref}</div>
    </div>
  );
}

function VerifyForm({ token, exceptionId, onDone }: {
  token: string; exceptionId: string; onDone: (r: Report, t: TrailEvent[]) => void;
}) {
  const [actor, setActor] = useState("");
  const [signoff, setSignoff] = useState("");
  const [busy, setBusy] = useState(false);
  const cls =
    "w-full border-0 border-b border-rule-2 bg-transparent px-0 py-1 text-xs outline-none focus:border-ink";
  return (
    <form
      className="flex min-w-[140px] flex-col gap-1.5"
      onSubmit={async (e) => {
        e.preventDefault();
        if (!actor.trim()) return;
        setBusy(true);
        try {
          const res = await verifyException(token, exceptionId, actor.trim(), signoff.trim());
          onDone(res.report, res.trail);
        } finally {
          setBusy(false);
        }
      }}
    >
      <input value={actor} onChange={(e) => setActor(e.target.value)} placeholder="Reviewer" required className={cls} />
      <input value={signoff} onChange={(e) => setSignoff(e.target.value)} placeholder="CA sign-off (opt)" className={cls} />
      <button
        disabled={busy}
        className="mt-1 border border-ink bg-ink px-3 py-1.5 text-[11px] font-semibold text-paper transition-colors hover:bg-card hover:text-ink disabled:opacity-50"
      >
        {busy ? "…" : "Verify"}
      </button>
    </form>
  );
}

function Schedule({ letter, title, count, children }: {
  letter: string; title: string; count: number; children: React.ReactNode;
}) {
  return (
    <section className="mt-14">
      <div className="flex items-baseline gap-3 border-b-2 border-ink pb-2">
        <span className="font-display text-lg font-semibold text-oxide">Schedule {letter}</span>
        <h2 className="font-display text-lg font-semibold">{title}</h2>
        <span className="ml-auto font-mono text-xs text-sub">{count} item(s)</span>
      </div>
      <div className="overflow-auto">{children}</div>
    </section>
  );
}

const TH = "px-3 py-2.5 text-left text-[10px] font-semibold uppercase tracking-[0.12em] text-sub border-b border-rule";
const THR = TH + " text-right";
const TD = "px-3 py-3 align-top border-b border-rule text-[13px]";

export default function ReportPage() {
  const { token = "" } = useParams();
  const [report, setReport] = useState<Report | null>(null);
  const [trail, setTrail] = useState<TrailEvent[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    getReport(token)
      .then((r) => { setReport(r.report); setTrail(r.trail); })
      .catch((e: Error) => setError(e.message));
  }, [token]);

  if (error) {
    return (
      <div className="min-h-screen bg-paper">
        <Nav />
        <div className="mx-auto mt-28 max-w-md border border-oxide/40 bg-card p-10 text-center">
          <div className="font-display text-2xl font-semibold text-oxide">Cannot open report</div>
          <p className="mt-3 text-sm text-sub">{error}</p>
        </div>
      </div>
    );
  }
  if (!report) {
    return (
      <div className="min-h-screen bg-paper">
        <Nav />
        <div className="mt-32 text-center font-mono text-xs text-sub">Loading report…</div>
      </div>
    );
  }

  const totalExc = report.exceptions.length;
  const verifiedExc = report.exceptions.filter((e) => e.verified).length;
  const onDone = (r: Report, t: TrailEvent[]) => { setReport(r); setTrail(t); };

  return (
    <div className="min-h-screen bg-paper pb-28 text-ink">
      <Nav />
      <AppTabs />
      <main className="mx-auto max-w-6xl px-6 pt-12">
        {/* Workpaper header */}
        <div className="relative flex flex-wrap items-start justify-between gap-6 border-b-2 border-ink pb-6">
          <div>
            <div className="label-caps">Input Tax Credit Reconciliation</div>
            <h1 className="mt-2 font-display text-4xl font-semibold tracking-tight">{report.client_name}</h1>
          </div>
          <div className="flex items-start gap-8">
            <table className="text-[12px]">
              <tbody className="font-mono text-sub">
                <tr><td className="pr-4 py-0.5">Report No.</td><td className="text-ink">{report.report_id}</td></tr>
                <tr><td className="pr-4 py-0.5">Period</td><td className="text-ink">{report.period_note || "—"}</td></tr>
                <tr><td className="pr-4 py-0.5">Prepared</td><td className="text-ink">{report.created_at.slice(0, 10)}</td></tr>
                <tr><td className="pr-4 py-0.5">Verified</td><td className="text-ink">{verifiedExc}/{totalExc} exceptions</td></tr>
              </tbody>
            </table>
            {verifiedExc > 0 && <span className="stamp mt-1">CA Verified</span>}
          </div>
        </div>

        {/* actions */}
        <div className="mt-4 flex gap-5 text-[13px] font-medium print:hidden">
          <a href={report.export_url} className="underline decoration-rule-2 underline-offset-4 hover:decoration-ink">Download Excel</a>
          <button onClick={() => window.print()} className="underline decoration-rule-2 underline-offset-4 hover:decoration-ink">Print</button>
        </div>

        {/* Totals strip */}
        <div className="mt-8 grid grid-cols-2 gap-y-8 border-y border-rule py-6 md:grid-cols-4 md:divide-x md:divide-rule">
          <div className="md:pr-8">
            <div className="label-caps">Credit at risk · verified</div>
            <div className="mt-2 font-mono text-[28px] font-semibold tabular-nums text-oxide">
              <CountUp value={report.verified_at_risk} />
            </div>
            <div className="mt-1 text-[11px] text-sub">{verifiedExc} of {totalExc} exceptions verified</div>
          </div>
          <div className="md:px-8">
            <div className="label-caps">Pending verification</div>
            <div className="mt-2 font-mono text-[28px] font-semibold tabular-nums">
              <CountUp value={report.pending_at_risk} />
            </div>
            <div className="mt-1 text-[11px] text-sub">awaiting reviewer sign-off</div>
          </div>
          <div className="md:px-8">
            <div className="label-caps">Missed credit</div>
            <div className="mt-2 font-mono text-[28px] font-semibold tabular-nums text-ledger">
              <CountUp value={report.missed_itc_total} />
            </div>
            <div className="mt-1 text-[11px] text-sub">{report.missed_itc.length} credit(s) not booked</div>
          </div>
          <div className="md:pl-8">
            <div className="label-caps">Matched clean</div>
            <div className="mt-2 font-mono text-[28px] font-semibold tabular-nums">{report.matched_count}</div>
            <div className="mt-1 text-[11px] text-sub">invoices · {inr(report.matched_tax_total)} reconciled</div>
          </div>
        </div>

        <p className="mt-5 max-w-3xl text-[12.5px] leading-relaxed text-sub">
          <span className="font-semibold text-ink">Basis of preparation.</span> The headline counts only
          human-verified exceptions. Credit/debit notes, GSTR-2B amendments, reverse-charge entries, ISD
          credits and ambiguous matches are quarantined in Schedule C and never enter the headline.
        </p>

        {/* Schedule A */}
        <Schedule letter="A" title="Input tax credit at risk" count={report.exceptions.length}>
          <table className="w-full border-collapse">
            <thead><tr>
              <th className={TH}>Ref</th><th className={TH}>Nature</th><th className={TH}>Supplier</th>
              <th className={TH}>Per books</th><th className={TH}>Per GSTR-2B</th>
              <th className={THR}>Amount (₹)</th><th className={TH}>Remarks</th><th className={TH}>Status</th>
              <th className={`${TH} print:hidden`}>Verify</th>
            </tr></thead>
            <tbody>
              {report.exceptions.map((e) => (
                <tr key={e.exception_id}>
                  <td className={`${TD} font-mono text-xs`}>{e.exception_id}</td>
                  <td className={`${TD} text-xs`}>{e.bucket.replace("_", " ")}</td>
                  <td className={TD}>
                    <div className="font-medium">{(e.books ?? e.gstr2b)?.supplier_name}</div>
                    <div className="font-mono text-[10px] text-sub">{(e.books ?? e.gstr2b)?.gstin}</div>
                  </td>
                  <td className={TD}><SideCell side={e.books} /></td>
                  <td className={TD}><SideCell side={e.gstr2b} /></td>
                  <td className={`${TD} text-right font-mono font-semibold tabular-nums text-oxide`}>{Number(e.itc_amount).toLocaleString("en-IN")}</td>
                  <td className={`${TD} max-w-[190px] text-xs text-sub`}>{e.reason}</td>
                  <td className={TD}>
                    {e.verified ? (
                      <div>
                        <span className="font-mono text-[10.5px] font-semibold uppercase tracking-widest text-ledger">Verified</span>
                        <div className="mt-0.5 text-[11px] text-sub">{e.verified_by}{e.ca_signoff && <> · {e.ca_signoff}</>}</div>
                      </div>
                    ) : (
                      <span className="font-mono text-[10.5px] font-semibold uppercase tracking-widest text-sub">Pending</span>
                    )}
                  </td>
                  <td className={`${TD} print:hidden`}>
                    {!e.verified && <VerifyForm token={token} exceptionId={e.exception_id} onDone={onDone} />}
                  </td>
                </tr>
              ))}
              {report.exceptions.length > 0 && (
                <tr>
                  <td colSpan={5} className="px-3 py-3 text-right text-[11px] font-semibold uppercase tracking-widest text-sub">Total at risk</td>
                  <td className="rule-double px-3 py-3 text-right font-mono font-semibold tabular-nums text-oxide">
                    {(Number(report.verified_at_risk) + Number(report.pending_at_risk)).toLocaleString("en-IN")}
                  </td>
                  <td colSpan={3} />
                </tr>
              )}
              {!report.exceptions.length && (
                <tr><td className={`${TD} py-8 text-center text-sub`} colSpan={9}>No at-risk exceptions — a clean period.</td></tr>
              )}
            </tbody>
          </table>
        </Schedule>

        {/* Schedule B */}
        <Schedule letter="B" title="Credit available but not booked" count={report.missed_itc.length}>
          <table className="w-full border-collapse">
            <thead><tr>
              <th className={TH}>Ref</th><th className={TH}>Supplier</th><th className={TH}>Per GSTR-2B</th>
              <th className={THR}>Amount (₹)</th><th className={TH}>Remarks</th>
            </tr></thead>
            <tbody>
              {report.missed_itc.map((e) => (
                <tr key={e.exception_id}>
                  <td className={`${TD} font-mono text-xs`}>{e.exception_id}</td>
                  <td className={TD}>
                    <div className="font-medium">{e.gstr2b?.supplier_name}</div>
                    <div className="font-mono text-[10px] text-sub">{e.gstr2b?.gstin}</div>
                  </td>
                  <td className={TD}><SideCell side={e.gstr2b} /></td>
                  <td className={`${TD} text-right font-mono font-semibold tabular-nums text-ledger`}>{Number(e.itc_amount).toLocaleString("en-IN")}</td>
                  <td className={`${TD} text-xs text-sub`}>{e.reason}</td>
                </tr>
              ))}
              {!report.missed_itc.length && (
                <tr><td className={`${TD} py-6 text-center text-sub`} colSpan={5}>None.</td></tr>
              )}
            </tbody>
          </table>
        </Schedule>

        {/* Schedule C */}
        <Schedule letter="C" title="Unresolved — excluded from the headline" count={report.unresolved.length}>
          <table className="w-full border-collapse">
            <thead><tr>
              <th className={TH}>Ref</th><th className={TH}>Supplier</th><th className={TH}>Per books</th>
              <th className={TH}>Per GSTR-2B</th><th className={THR}>Amount (₹)</th><th className={TH}>Reason for exclusion</th>
            </tr></thead>
            <tbody>
              {report.unresolved.map((e) => (
                <tr key={e.exception_id}>
                  <td className={`${TD} font-mono text-xs`}>{e.exception_id}</td>
                  <td className={TD}>
                    <div className="font-medium">{(e.books ?? e.gstr2b)?.supplier_name}</div>
                    <div className="font-mono text-[10px] text-sub">{(e.books ?? e.gstr2b)?.gstin}</div>
                  </td>
                  <td className={TD}><SideCell side={e.books} /></td>
                  <td className={TD}><SideCell side={e.gstr2b} /></td>
                  <td className={`${TD} text-right font-mono tabular-nums`}>{Number(e.itc_amount).toLocaleString("en-IN")}</td>
                  <td className={`${TD} text-xs text-sub`}>{e.reason}</td>
                </tr>
              ))}
              {!report.unresolved.length && (
                <tr><td className={`${TD} py-6 text-center text-sub`} colSpan={6}>None.</td></tr>
              )}
            </tbody>
          </table>
        </Schedule>

        {/* Annexure — audit trail */}
        <details className="mt-14">
          <summary className="cursor-pointer border-b-2 border-ink pb-2 font-display text-lg font-semibold">
            Annexure — audit trail <span className="ml-2 font-mono text-xs font-normal text-sub">{trail.length} events · append-only</span>
          </summary>
          <div className="overflow-auto">
            <table className="w-full border-collapse font-mono text-xs">
              <thead><tr>
                <th className={TH}>#</th><th className={TH}>Agent</th><th className={TH}>Action</th>
                <th className={TH}>Input</th><th className={TH}>Output</th><th className={TH}>Actor</th>
                <th className={TH}>Reviewed by</th><th className={TH}>Timestamp (UTC)</th>
              </tr></thead>
              <tbody>
                {trail.map((ev) => (
                  <tr key={ev.event_id}>
                    <td className={TD}>{ev.event_id}</td><td className={TD}>{ev.agent}</td>
                    <td className={TD}>{ev.action}</td><td className={`${TD} max-w-[200px] break-all`}>{ev.input_doc_ref}</td>
                    <td className={TD}>{ev.output_ref}</td><td className={TD}>{ev.actor}</td>
                    <td className={TD}>{ev.reviewed_by}</td><td className={TD}>{ev.ts.slice(0, 19)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-3 text-[11.5px] text-sub">
            Entries physically cannot be edited or deleted — UPDATE and DELETE are rejected at the database level.
          </p>
        </details>
      </main>
    </div>
  );
}
