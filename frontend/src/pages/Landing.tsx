import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import Nav from "../components/Nav";

const steps = [
  {
    bg: "bg-mustard", fg: "text-ink", label: "UPLOAD",
    line: "Two files: GSTR-2B and your purchase register.",
    n: "01",
  },
  {
    bg: "bg-slate2", fg: "text-white", label: "RECONCILE",
    line: "Agents match, bucket, and price the credit at risk.",
    n: "02",
  },
  {
    bg: "bg-oxide", fg: "text-white", label: "VERIFY",
    line: "A chartered accountant signs every rupee in the headline.",
    n: "03",
  },
];

type QueueRow = {
  id: string; op: string; cat: string; ts: string;
  status: "COMPLETE" | "RUNNING" | "PROCESSING" | "QUEUED";
};

const initialQueue: QueueRow[] = [
  { id: "#4417", op: "GSTR-2B Parsed — 3,214 documents", cat: "ITC Recon", ts: "09:41:22", status: "COMPLETE" },
  { id: "#4418", op: "Purchase Register Normalised", cat: "ITC Recon", ts: "09:41:45", status: "COMPLETE" },
  { id: "#4419", op: "Invoice Matching Running", cat: "ITC Recon", ts: "09:42:10", status: "RUNNING" },
  { id: "#4420", op: "Bank Statement Reconciling — HDFC CA-0042", cat: "Bank Recon", ts: "09:42:15", status: "PROCESSING" },
  { id: "#4421", op: "Scanned Bill Extraction", cat: "Vision", ts: "09:42:40", status: "PROCESSING" },
  { id: "#4422", op: "Close Workbook Rollforward — 2026-04", cat: "Close", ts: "09:43:00", status: "QUEUED" },
];

const statusColor: Record<QueueRow["status"], string> = {
  COMPLETE: "text-ledger",
  RUNNING: "text-running status-live",
  PROCESSING: "text-process status-live",
  QUEUED: "text-sub",
};

const agents = [
  { n: "01", name: "Recon Agent", status: "IN SERVICE", live: true, desc: "Matches every purchase invoice against GSTR-2B and prices the credit at risk — every exception traced to its source row." },
  { n: "02", name: "Bank Recon Agent", status: "IN SERVICE", live: true, desc: "Statement vs bank ledger. Unrecorded charges, uncleared cheques, deposits in transit — the classic BRS, done in seconds." },
  { n: "03", name: "Close Agent", status: "IN SERVICE", live: true, desc: "Month-end close workbook per period — twelve controls from ITC recon to suspense, every tick logged with a name on it." },
  { n: "04", name: "Vision Agent", status: "IN BETA", live: false, desc: "Reads the actual bills — photographed, crumpled, vernacular — and resolves what matching alone can't explain." },
];

export default function Landing() {
  const [queue, setQueue] = useState(initialQueue);

  useEffect(() => {
    const t = setInterval(() => {
      setQueue((q) =>
        q.map((row) =>
          row.status === "RUNNING" ? { ...row, status: "COMPLETE" }
          : row.status === "PROCESSING" ? { ...row, status: "RUNNING" }
          : row.status === "QUEUED" ? { ...row, status: "PROCESSING" }
          : row,
        ),
      );
    }, 2600);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="min-h-screen bg-paper text-ink">
      <Nav />

      {/* HERO */}
      <header className="mx-auto grid max-w-6xl gap-14 px-6 pb-20 pt-16 lg:grid-cols-[1.1fr_1fr] lg:items-center">
        <div>
          <div className="label-caps mb-6">For businesses that pay hefty audit fees</div>
          <h1 className="text-[46px] font-extrabold leading-[1.02] tracking-[-0.03em] md:text-[62px]">
            Your books are leaking input tax credit.
          </h1>
          <p className="mt-6 max-w-xl text-[16.5px] leading-relaxed text-sub">
            Audita's agents reconcile your GSTR-2B against your purchase register, put a rupee figure on
            the credit at risk, and a chartered accountant signs every number before you see it.
            The grind is automated. The judgment stays human.
          </p>
          <div className="mt-9 flex flex-wrap items-center gap-4">
            <Link
              to="/app/recon"
              className="border border-ink bg-ink px-7 py-3.5 text-[13px] font-bold uppercase tracking-[0.08em] text-paper transition-colors hover:bg-paper hover:text-ink"
            >
              Find your ₹ at risk
            </Link>
            <a href="#method" className="px-2 py-3.5 text-[13px] font-bold uppercase tracking-[0.08em] text-ink underline decoration-rule-2 decoration-2 underline-offset-8 hover:decoration-ink">
              The method
            </a>
          </div>
          <div className="mt-10 flex gap-10 border-t border-rule pt-5">
            {[["±₹1", "amount tolerance, or 0.1%"], ["0", "unverified rupees in a headline"], ["100%", "of exceptions traced to source"]].map(([v, d]) => (
              <div key={d}>
                <div className="font-mono text-lg font-semibold tabular-nums">{v}</div>
                <div className="text-xs text-sub">{d}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Ledger sheet mock */}
        <div className="relative border border-rule-2 bg-card shadow-[4px_4px_0_0_rgba(23,20,14,0.1)]">
          <div className="pointer-events-none absolute bottom-0 left-10 top-0 w-px bg-oxide/40" />
          <div className="border-b border-rule px-14 py-4">
            <div className="label-caps">ITC Reconciliation · April 2026</div>
            <div className="mt-1 text-lg font-bold tracking-tight">Acme Textiles Pvt Ltd</div>
          </div>
          <div className="ruled px-14 pb-6 pt-2">
            <table className="w-full text-[13px]">
              <tbody className="font-mono">
                {[
                  ["E0007", "Ghost Supplier LLP", "not in GSTR-2B", "7,200.00"],
                  ["E0008", "Supplier One Pvt Ltd", "not in GSTR-2B", "4,500.00"],
                  ["E0009", "Near Match & Co", "not in GSTR-2B", "2,700.00"],
                ].map(([id, who, why, amt]) => (
                  <tr key={id} className="h-8 align-middle">
                    <td className="pr-3 text-[11px] text-sub">{id}</td>
                    <td className="pr-3 font-sans font-medium">{who}</td>
                    <td className="hidden pr-3 text-[11px] italic text-oxide sm:table-cell">{why}</td>
                    <td className="text-right tabular-nums text-oxide">{amt}</td>
                  </tr>
                ))}
                <tr className="h-8">
                  <td colSpan={3} className="pr-3 text-right font-sans text-[11px] font-bold uppercase tracking-widest text-sub">
                    Credit at risk
                  </td>
                  <td className="rule-double text-right font-semibold tabular-nums text-oxide">14,400.00</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div className="flex items-center justify-between border-t border-rule px-14 py-4">
            <div className="text-[11px] text-sub">Every line traced to its source row.</div>
            <span className="stamp">CA Verified</span>
          </div>
        </div>
      </header>

      {/* COLOR-BLOCK STEPS */}
      <section id="method" className="mx-auto max-w-6xl px-6">
        <div className="grid md:grid-cols-3">
          {steps.map((s) => (
            <div key={s.n} className={`relative ${s.bg} ${s.fg} flex min-h-[280px] flex-col justify-between p-8`}>
              <div>
                <div className="text-[10px] font-bold uppercase tracking-[0.25em] opacity-70">{s.label}</div>
                <p className="mt-4 max-w-[260px] text-[21px] font-semibold leading-snug tracking-tight">{s.line}</p>
              </div>
              <div className="text-[64px] font-light leading-none tracking-tight opacity-90">{s.n}</div>
              <span className="v-step absolute right-4 top-8">Step {s.n}</span>
            </div>
          ))}
        </div>
      </section>

      {/* ACTIVE AGENTS — live queue */}
      <section id="agents" className="mx-auto max-w-6xl px-6 py-20">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <h2 className="h-block text-[44px] md:text-[56px]">Active Agents</h2>
          <div className="label-caps flex items-center gap-2 pb-2">
            <span className="status-live inline-block h-1.5 w-1.5 rounded-full bg-ledger" />
            Live processing queue
          </div>
        </div>

        <div className="mt-8 border-t border-rule">
          <table className="w-full">
            <thead>
              <tr>
                {["ID", "Operation", "Category", "Timestamp", "Status"].map((h, i) => (
                  <th key={h} className={`border-b border-rule px-3 py-3 text-[10px] font-bold uppercase tracking-[0.18em] text-sub ${i >= 4 ? "text-right" : "text-left"} ${i === 2 || i === 3 ? "hidden sm:table-cell" : ""}`}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {queue.map((row) => (
                <tr key={row.id} className="border-b border-rule">
                  <td className="px-3 py-4 font-mono text-xs text-sub">{row.id}</td>
                  <td className="px-3 py-4 text-[14px] font-semibold">{row.op}</td>
                  <td className="hidden px-3 py-4 text-[13px] text-sub sm:table-cell">{row.cat}</td>
                  <td className="hidden px-3 py-4 font-mono text-xs text-sub sm:table-cell">{row.ts}</td>
                  <td className={`px-3 py-4 text-right font-mono text-[11px] font-semibold tracking-[0.12em] ${statusColor[row.status]}`}>
                    {row.status}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* agent roster */}
        <div className="mt-14 grid gap-0 border-t-2 border-ink sm:grid-cols-2 md:grid-cols-4 md:divide-x md:divide-rule">
          {agents.map((a) => (
            <div key={a.n} className="py-7 md:px-8 md:first:pl-0 md:last:pr-0">
              <div className="flex items-baseline justify-between">
                <span className="font-mono text-[13px] text-oxide">{a.n}</span>
                <span className={`font-mono text-[10px] font-semibold tracking-[0.18em] ${a.live ? "text-ledger" : "text-sub"}`}>
                  {a.live && <span className="status-live mr-1.5 inline-block h-1.5 w-1.5 rounded-full bg-ledger align-middle" />}
                  {a.status}
                </span>
              </div>
              <h3 className="mt-3 text-[17px] font-bold tracking-tight">{a.name}</h3>
              <p className="mt-2 text-[13.5px] leading-relaxed text-sub">{a.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* NOTES TO THE READER */}
      <section id="notes" className="border-t border-rule bg-card">
        <div className="mx-auto max-w-6xl px-6 py-20">
          <h2 className="h-block text-[32px] md:text-[40px]">Notes to the reader</h2>
          <div className="mt-10 grid gap-x-14 gap-y-8 md:grid-cols-2">
            {[
              ["1.", "Human sign-off, always.", "The headline counts only exceptions a named chartered accountant has verified. The software proposes; a professional disposes."],
              ["2.", "The trail cannot be edited.", "Every agent action lands in an append-only log. UPDATE and DELETE are rejected at the database level — by design, not by policy."],
              ["3.", "Your data stays yours.", "Processed for your report only, deleted on request, shared through signed links that expire on their own."],
              ["4.", "Built for the Indian stack.", "Tally exports, GSTN portal JSON, GST invoice formats, scanned bills. The mess everyone else avoids is the whole point."],
            ].map(([n, t, d]) => (
              <div key={n} className="flex gap-4 border-t border-rule pt-5">
                <div className="font-mono text-[15px] font-semibold text-oxide">{n}</div>
                <div>
                  <h3 className="text-[14.5px] font-bold">{t}</h3>
                  <p className="mt-1.5 text-[13.5px] leading-relaxed text-sub">{d}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="border-t border-rule">
        <div className="mx-auto max-w-6xl px-6 py-24">
          <h2 className="h-block max-w-3xl text-[40px] md:text-[54px]">
            The recon takes minutes. The blocked credit is already yours.
          </h2>
          <div className="mt-10 flex flex-wrap items-center gap-6">
            <Link
              to="/app/recon"
              className="border border-ink bg-ink px-9 py-4 text-[13px] font-bold uppercase tracking-[0.08em] text-paper transition-colors hover:bg-paper hover:text-ink"
            >
              Run your first recon
            </Link>
            <p className="max-w-sm text-[13px] text-sub">
              Upload this month's files. If the number doesn't make you reach for your phone, the report was free anyway.
            </p>
          </div>
        </div>
      </section>

      <footer className="border-t border-rule">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-6 py-8 text-[11px] text-sub">
          <span className="text-sm font-extrabold uppercase tracking-tight text-ink">Audita</span>
          <span>Reports are CA-reviewed workpapers, not statutory audit opinions. · © 2026</span>
        </div>
      </footer>
    </div>
  );
}
