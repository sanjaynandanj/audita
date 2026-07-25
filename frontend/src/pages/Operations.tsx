import { useEffect, useState } from "react";
import Nav from "../components/Nav";
import AppTabs from "../components/AppTabs";
import { type TrailEvent, getOperations } from "../lib/api";

const ACTION_STATUS: Record<string, { label: string; cls: string }> = {
  parsed: { label: "COMPLETE", cls: "text-ledger" },
  recon_completed: { label: "COMPLETE", cls: "text-ledger" },
  bankrec_completed: { label: "COMPLETE", cls: "text-ledger" },
  exception_verified: { label: "VERIFIED", cls: "text-ledger" },
  report_exported: { label: "COMPLETE", cls: "text-ledger" },
  close_item_done: { label: "COMPLETE", cls: "text-ledger" },
  close_item_reopened: { label: "REOPENED", cls: "text-running" },
  parse_failed: { label: "FAILED", cls: "text-oxide" },
};

const AGENT_CATEGORY: Record<string, string> = {
  "itc-recon-agent/0.1": "ITC Recon",
  "bank-recon-agent/0.1": "Bank Recon",
  "close-agent/0.1": "Close",
};

function opTitle(ev: TrailEvent): string {
  const map: Record<string, string> = {
    parsed: "Documents Parsed",
    recon_completed: "ITC Reconciliation Complete",
    bankrec_completed: "Bank Reconciliation Complete",
    exception_verified: `Exception ${ev.input_doc_ref} Verified`,
    report_exported: "Workpaper Exported",
    close_item_done: `Close Item Done — ${ev.input_doc_ref}`,
    close_item_reopened: `Close Item Reopened — ${ev.input_doc_ref}`,
    parse_failed: "Parse Failed",
  };
  return map[ev.action] ?? ev.action;
}

export default function Operations() {
  const [events, setEvents] = useState<TrailEvent[]>([]);
  const [live, setLive] = useState(true);

  useEffect(() => {
    let stop = false;
    const load = () => getOperations(50).then((r) => { if (!stop) setEvents(r.events); }).catch(() => {});
    load();
    const t = setInterval(() => { if (live) load(); }, 2500);
    return () => { stop = true; clearInterval(t); };
  }, [live]);

  return (
    <div className="min-h-screen bg-paper pb-24 text-ink">
      <Nav /><AppTabs />
      <main className="mx-auto max-w-6xl px-6 pt-10">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <h1 className="h-block text-[40px] md:text-[52px]">Active Agents</h1>
          <button
            onClick={() => setLive((v) => !v)}
            className="label-caps flex items-center gap-2 pb-2"
          >
            <span className={`inline-block h-1.5 w-1.5 rounded-full ${live ? "status-live bg-ledger" : "bg-rule-2"}`} />
            {live ? "Live processing queue" : "Paused — click to resume"}
          </button>
        </div>

        <div className="mt-8 border-t border-rule">
          <table className="w-full">
            <thead>
              <tr>
                {["ID", "Operation", "Category", "Actor", "Timestamp", "Status"].map((h, i) => (
                  <th key={h} className={`border-b border-rule px-3 py-3 text-[10px] font-bold uppercase tracking-[0.18em] text-sub ${i === 5 ? "text-right" : "text-left"} ${i === 2 || i === 3 || i === 4 ? "hidden sm:table-cell" : ""}`}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {events.map((ev) => {
                const status = ACTION_STATUS[ev.action] ?? { label: ev.action.toUpperCase(), cls: "text-sub" };
                return (
                  <tr key={ev.event_id} className="border-b border-rule">
                    <td className="px-3 py-3.5 font-mono text-xs text-sub">#{ev.event_id}</td>
                    <td className="px-3 py-3.5 text-[14px] font-semibold">{opTitle(ev)}</td>
                    <td className="hidden px-3 py-3.5 text-[13px] text-sub sm:table-cell">
                      {AGENT_CATEGORY[ev.agent] ?? ev.agent}
                    </td>
                    <td className="hidden px-3 py-3.5 text-[13px] text-sub sm:table-cell">{ev.actor || "—"}</td>
                    <td className="hidden px-3 py-3.5 font-mono text-xs text-sub sm:table-cell">{ev.ts.slice(11, 19)}</td>
                    <td className={`px-3 py-3.5 text-right font-mono text-[11px] font-semibold tracking-[0.12em] ${status.cls}`}>
                      {status.label}
                    </td>
                  </tr>
                );
              })}
              {!events.length && (
                <tr><td colSpan={6} className="px-3 py-10 text-center text-sm text-sub">
                  No operations yet — run a reconciliation and watch the queue fill.
                </td></tr>
              )}
            </tbody>
          </table>
        </div>

        <p className="mt-5 text-[12px] text-sub">
          This queue reads the real append-only event log — the same trail annexed to every workpaper.
          Nothing here can be edited or deleted.
        </p>
      </main>
    </div>
  );
}
