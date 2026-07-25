import { useCallback, useEffect, useRef, useState } from "react";
import Nav from "../components/Nav";
import AppTabs from "../components/AppTabs";
import {
  type InvoiceDoc,
  type InvoiceFields,
  confirmInvoice,
  inr,
  listInvoices,
  registerCsvUrl,
  uploadInvoice,
} from "../lib/api";

function currentPeriod(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

const AMOUNT_KEYS: (keyof InvoiceFields)[] = ["taxable_value", "igst", "cgst", "sgst", "cess", "total"];
const TEXT_LABELS: Partial<Record<keyof InvoiceFields, string>> = {
  supplier_gstin: "Supplier GSTIN",
  supplier_name: "Party name",
  invoice_no: "Invoice no",
  invoice_date: "Invoice date",
  taxable_value: "Taxable value",
  igst: "IGST",
  cgst: "CGST",
  sgst: "SGST",
  cess: "Cess",
  total: "Total",
};

function DraftEditor({ doc, onConfirmed }: { doc: InvoiceDoc; onConfirmed: () => void }) {
  const [fields, setFields] = useState<InvoiceFields>({ ...doc.fields });
  const [actor, setActor] = useState("");
  const [signoff, setSignoff] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  function set(key: keyof InvoiceFields, value: string) {
    setFields((f) => ({ ...f, [key]: value }));
  }

  async function confirm() {
    setBusy(true);
    setError("");
    try {
      await confirmInvoice(doc.invoice_id, fields, actor.trim(), signoff.trim());
      onConfirmed();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="border-l-2 border-rule-2 bg-card px-5 py-4">
      <div className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-5">
        {(Object.keys(TEXT_LABELS) as (keyof InvoiceFields)[]).map((key) => (
          <div key={key}>
            <label className="label-caps block">{TEXT_LABELS[key]}</label>
            <input
              value={fields[key]}
              onChange={(e) => set(key, e.target.value)}
              className={`w-full border-0 border-b border-rule-2 bg-transparent px-0 py-1 text-sm outline-none focus:border-ink ${
                AMOUNT_KEYS.includes(key) ? "font-mono tabular-nums" : ""
              }`}
            />
          </div>
        ))}
      </div>
      <div className="mt-4 flex flex-wrap items-end gap-4 border-t border-rule pt-4">
        <div>
          <label className="label-caps block">Confirmed by *</label>
          <input
            value={actor} onChange={(e) => setActor(e.target.value)} placeholder="Your name"
            className="border-0 border-b border-rule-2 bg-transparent px-0 py-1 text-sm outline-none focus:border-ink"
          />
        </div>
        <div>
          <label className="label-caps block">CA sign-off (optional)</label>
          <input
            value={signoff} onChange={(e) => setSignoff(e.target.value)} placeholder="Name / membership no."
            className="border-0 border-b border-rule-2 bg-transparent px-0 py-1 text-sm outline-none focus:border-ink"
          />
        </div>
        <button
          onClick={confirm}
          disabled={busy || !actor.trim()}
          className="ml-auto bg-ink px-5 py-2 text-[12px] font-bold uppercase tracking-[0.1em] text-paper transition-opacity disabled:opacity-40"
        >
          {busy ? "Confirming…" : "Confirm into register"}
        </button>
      </div>
      {error && (
        <div className="mt-3 border-l-2 border-oxide bg-oxide/[.05] px-3 py-2 text-[13px] font-medium text-oxide-2">
          {error}
        </div>
      )}
      <p className="mt-3 text-[11px] text-sub">
        Confirmation is final — the row becomes part of the {doc.period} purchase register and the
        event log. Corrections after confirmation are recorded as new entries, never edits.
      </p>
    </div>
  );
}

export default function Invoices() {
  const [period, setPeriod] = useState(currentPeriod());
  const [invoices, setInvoices] = useState<InvoiceDoc[]>([]);
  const [open, setOpen] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const refresh = useCallback(() => {
    listInvoices(period)
      .then((r) => setInvoices(r.invoices))
      .catch((e: Error) => setError(e.message));
  }, [period]);

  useEffect(refresh, [refresh]);

  async function onUpload(files: FileList | null) {
    if (!files?.length) return;
    setUploading(true);
    setError("");
    try {
      for (const file of Array.from(files)) {
        const { invoice } = await uploadInvoice(period, file);
        setOpen(invoice.invoice_id);
      }
      refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  const drafts = invoices.filter((i) => i.status === "draft");
  const confirmed = invoices.filter((i) => i.status === "confirmed");

  return (
    <div className="min-h-screen bg-paper pb-24 text-ink">
      <Nav /><AppTabs />
      <main className="mx-auto max-w-5xl px-6 pt-10">
        <div className="flex flex-wrap items-end justify-between gap-6 border-b-2 border-ink pb-5">
          <div>
            <div className="label-caps">Invoice Agent · AP capture</div>
            <h1 className="mt-2 text-3xl font-extrabold tracking-tight">Invoices {period}</h1>
          </div>
          <div>
            <label className="label-caps block">Period</label>
            <input
              type="month" value={period} onChange={(e) => setPeriod(e.target.value)}
              className="border-0 border-b border-rule-2 bg-transparent px-0 py-1.5 font-mono text-sm outline-none focus:border-ink"
            />
          </div>
        </div>

        <label
          className="mt-8 flex cursor-pointer flex-col items-center gap-2 border-2 border-dashed border-rule-2 px-6 py-10 text-center transition-colors hover:border-ink hover:bg-card"
        >
          <input
            ref={fileRef} type="file" multiple accept=".jpg,.jpeg,.png,.webp,.pdf"
            className="hidden" onChange={(e) => onUpload(e.target.files)}
          />
          <span className="text-[14.5px] font-semibold">
            {uploading ? "Uploading…" : "Drop invoice photos or PDFs here, or click to choose"}
          </span>
          <span className="text-[12px] text-sub">
            JPG · PNG · WEBP · PDF — fields are extracted where Vision is configured, then a named
            human confirms every rupee before it enters the register.
          </span>
        </label>

        {error && (
          <div className="mt-5 border-l-2 border-oxide bg-oxide/[.05] px-4 py-3 text-[13px] font-medium text-oxide-2">
            {error}
          </div>
        )}

        <section className="mt-10">
          <div className="flex items-baseline justify-between">
            <h2 className="text-[13px] font-bold uppercase tracking-[0.1em]">
              Review queue <span className="ml-1 font-mono text-sub">({drafts.length})</span>
            </h2>
          </div>
          {drafts.length === 0 && (
            <p className="mt-3 text-[13px] text-sub">No drafts waiting. Upload a bill above.</p>
          )}
          <div className="mt-3 border-t border-rule">
            {drafts.map((doc) => (
              <div key={doc.invoice_id} className="border-b border-rule">
                <button
                  onClick={() => setOpen(open === doc.invoice_id ? null : doc.invoice_id)}
                  className="flex w-full items-center gap-4 py-3 text-left transition-colors hover:bg-card"
                >
                  <span className="font-mono text-xs text-sub">{doc.invoice_id.slice(0, 8)}</span>
                  <span className="flex-1 text-[14px] font-medium">
                    {doc.fields.supplier_name || doc.source_file}
                    {doc.fields.invoice_no && (
                      <span className="ml-2 font-mono text-xs text-sub">{doc.fields.invoice_no}</span>
                    )}
                  </span>
                  <span
                    className={`px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.1em] ${
                      doc.extraction === "vision"
                        ? "bg-ledger/10 text-ledger"
                        : doc.extraction === "failed"
                          ? "bg-oxide/10 text-oxide-2"
                          : "bg-rule/60 text-sub"
                    }`}
                  >
                    {doc.extraction}
                  </span>
                  <span className="font-mono text-sm tabular-nums">{inr(doc.fields.total)}</span>
                </button>
                {open === doc.invoice_id && (
                  <>
                    {doc.extraction_note && (
                      <p className="px-5 pb-2 text-[12px] italic text-sub">{doc.extraction_note}</p>
                    )}
                    <DraftEditor doc={doc} onConfirmed={() => { setOpen(null); refresh(); }} />
                  </>
                )}
              </div>
            ))}
          </div>
        </section>

        <section className="mt-12">
          <div className="flex items-baseline justify-between">
            <h2 className="text-[13px] font-bold uppercase tracking-[0.1em]">
              Confirmed register <span className="ml-1 font-mono text-sub">({confirmed.length})</span>
            </h2>
            {confirmed.length > 0 && (
              <a
                href={registerCsvUrl(period)}
                className="text-[12px] font-bold uppercase tracking-[0.1em] underline decoration-rule-2 underline-offset-4 hover:decoration-ink"
              >
                Export register CSV → run ITC recon
              </a>
            )}
          </div>
          {confirmed.length === 0 ? (
            <p className="mt-3 text-[13px] text-sub">Nothing confirmed for {period} yet.</p>
          ) : (
            <table className="mt-3 w-full border-collapse text-[13px]">
              <thead>
                <tr className="border-b-2 border-ink text-left">
                  <th className="py-2 pr-4 label-caps">Supplier</th>
                  <th className="py-2 pr-4 label-caps">Invoice</th>
                  <th className="py-2 pr-4 label-caps">Date</th>
                  <th className="py-2 pr-4 text-right label-caps">Taxable</th>
                  <th className="py-2 pr-4 text-right label-caps">Tax</th>
                  <th className="py-2 pr-4 label-caps">Confirmed by</th>
                  <th className="py-2 label-caps">CA sign-off</th>
                </tr>
              </thead>
              <tbody>
                {confirmed.map((doc) => {
                  const f = doc.fields;
                  const tax =
                    parseFloat(f.igst || "0") + parseFloat(f.cgst || "0") +
                    parseFloat(f.sgst || "0") + parseFloat(f.cess || "0");
                  return (
                    <tr key={doc.invoice_id} className="border-b border-rule">
                      <td className="py-2.5 pr-4 font-medium">
                        {f.supplier_name || "—"}
                        <span className="ml-2 font-mono text-[11px] text-sub">{f.supplier_gstin}</span>
                      </td>
                      <td className="py-2.5 pr-4 font-mono text-xs">{f.invoice_no}</td>
                      <td className="py-2.5 pr-4 font-mono text-xs">{f.invoice_date}</td>
                      <td className="py-2.5 pr-4 text-right font-mono tabular-nums">{inr(f.taxable_value)}</td>
                      <td className="py-2.5 pr-4 text-right font-mono tabular-nums">{inr(tax)}</td>
                      <td className="py-2.5 pr-4">{doc.confirmed_by}</td>
                      <td className="py-2.5">
                        {doc.ca_signoff ? (
                          <span className="font-mono text-[11px] text-ledger">✓ {doc.ca_signoff}</span>
                        ) : (
                          <span className="text-sub">—</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </section>

        <p className="mt-8 text-[12px] leading-relaxed text-sub">
          Every upload, extraction and confirmation lands in the append-only event log. Only
          confirmed invoices enter the register export — drafts and failed extractions never touch
          a headline number.
        </p>
      </main>
    </div>
  );
}
