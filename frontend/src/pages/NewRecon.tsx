import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import Nav from "../components/Nav";
import AppTabs from "../components/AppTabs";
import { runRecon } from "../lib/api";

function DropZone({
  label, hint, accept, file, onFile,
}: {
  label: string; hint: string; accept: string;
  file: File | null; onFile: (f: File) => void;
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
        file
          ? "border-ledger bg-ledger/[.04]"
          : drag
            ? "border-ink bg-ink/[.03]"
            : "border-rule-2 hover:border-ink"
      }`}
    >
      <input
        ref={input} type="file" accept={accept} className="hidden"
        onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])}
      />
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

export default function NewRecon() {
  const nav = useNavigate();
  const [clientName, setClientName] = useState("");
  const [period, setPeriod] = useState("");
  const [g2b, setG2b] = useState<File | null>(null);
  const [reg, setReg] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!g2b || !reg) { setError("Both files are required."); return; }
    setBusy(true); setError("");
    const form = new FormData();
    form.append("client_name", clientName);
    form.append("period_note", period);
    form.append("gstr2b_file", g2b);
    form.append("register_file", reg);
    try {
      const { token } = await runRecon(form);
      nav(`/app/r/${encodeURIComponent(token)}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Reconciliation failed.");
      setBusy(false);
    }
  }

  const inputCls =
    "w-full border-0 border-b border-rule-2 bg-transparent px-0 py-2 text-[15px] outline-none transition-colors focus:border-ink";

  return (
    <div className="min-h-screen bg-paper text-ink">
      <Nav />
      <AppTabs />
      <main className="mx-auto max-w-xl px-6 py-16">
        <div className="label-caps">New engagement</div>
        <h1 className="mt-2 font-display text-4xl font-semibold tracking-tight">Run a reconciliation</h1>
        <p className="mt-3 text-[14px] leading-relaxed text-sub">
          Two files. The Recon Agent does the rest — and the headline stays at ₹0 until a human verifies it.
        </p>

        <form onSubmit={submit} className="mt-10 border border-rule-2 bg-card p-8 shadow-[3px_3px_0_0_rgba(28,24,17,0.08)]">
          <label className="label-caps block">Client / business name</label>
          <input
            required value={clientName} onChange={(e) => setClientName(e.target.value)}
            placeholder="Acme Textiles Pvt Ltd" className={inputCls}
          />
          <label className="label-caps mt-7 block">Period <span className="normal-case tracking-normal">— optional</span></label>
          <input
            value={period} onChange={(e) => setPeriod(e.target.value)}
            placeholder="FY 2025-26 · April" className={inputCls}
          />

          <div className="mt-8 grid gap-4 sm:grid-cols-2">
            <DropZone
              label="GSTR-2B" hint="Portal JSON, or CSV / XLSX"
              accept=".json,.csv,.xlsx,.xls" file={g2b} onFile={setG2b}
            />
            <DropZone
              label="Purchase register" hint="Tally CSV / XLSX export"
              accept=".csv,.xlsx,.xls" file={reg} onFile={setReg}
            />
          </div>

          {error && (
            <div className="mt-6 border-l-2 border-oxide bg-oxide/[.05] px-4 py-3 text-[13px] font-medium text-oxide-2">
              {error}
            </div>
          )}

          <button
            disabled={busy}
            className="mt-8 w-full border border-ink bg-ink py-3.5 text-[14px] font-semibold text-paper transition-colors hover:bg-card hover:text-ink disabled:cursor-not-allowed disabled:opacity-50"
          >
            {busy ? "Agents at work…" : "Run reconciliation"}
          </button>
        </form>

        <div className="mt-8 space-y-1.5 text-[11.5px] leading-relaxed text-sub">
          <p>1. Processed for this report only; deleted on request.</p>
          <p>2. The headline counts only CA-verified exceptions.</p>
          <p>3. Every agent action is logged, append-only.</p>
        </div>
      </main>
    </div>
  );
}
