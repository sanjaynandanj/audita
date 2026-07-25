import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import Nav from "../components/Nav";
import AppTabs from "../components/AppTabs";
import {
  type TrailEvent,
  type WorkItem,
  getOperations,
  getWorkqueue,
  inr,
} from "../lib/api";

const AGENT_LABEL: Record<WorkItem["agent"], string> = {
  "itc-recon": "ITC Recon",
  invoice: "Invoices",
  bookkeeping: "Books",
  close: "Close",
  review: "Review",
};

const AGENT_BADGE: Record<WorkItem["agent"], string> = {
  "itc-recon": "bg-oxide/10 text-oxide-2",
  invoice: "bg-ink/10 text-ink",
  bookkeeping: "bg-ledger/10 text-ledger",
  close: "bg-rule/60 text-sub",
  review: "bg-running/10 text-running",
};

function ageLabel(days: number): string {
  if (days <= 0) return "today";
  if (days === 1) return "1 day";
  return `${days} days`;
}

export default function Workspace() {
  const [items, setItems] = useState<WorkItem[]>([]);
  const [total, setTotal] = useState(0);
  const [byAgent, setByAgent] = useState<Record<string, number>>({});
  const [events, setEvents] = useState<TrailEvent[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    let stop = false;
    const load = () => {
      getWorkqueue()
        .then((r) => {
          if (stop) return;
          setItems(r.items);
          setTotal(r.total_decisions);
          setByAgent(r.by_agent);
        })
        .catch((e: Error) => setError(e.message));
      getOperations(15)
        .then((r) => { if (!stop) setEvents(r.events); })
        .catch(() => undefined);
    };
    load();
    const t = setInterval(load, 5000);
    return () => { stop = true; clearInterval(t); };
  }, []);

  return (
    <div className="min-h-screen bg-paper pb-24 text-ink">
      <Nav />
      <AppTabs />
      <main className="mx-auto max-w-6xl px-6 pt-10">
        <div className="flex flex-wrap items-end justify-between gap-6 border-b-2 border-ink pb-5">
          <div>
            <div className="label-caps">Agent Workspace · every pending decision</div>
            <h1 className="mt-2 text-3xl font-extrabold tracking-tight">
              {total === 0 ? "All clear" : `${total} decision${total === 1 ? "" : "s"} waiting`}
            </h1>
          </div>
          <div className="flex gap-6">
            {Object.entries(AGENT_LABEL).map(([agent, label]) => (
              <div key={agent}>
                <div className="label-caps">{label}</div>
                <div className="mt-1 font-mono text-xl font-bold tabular-nums">
                  {byAgent[agent] ?? 0}
                </div>
              </div>
            ))}
          </div>
        </div>

        {error && (
          <div className="mt-5 border-l-2 border-oxide bg-oxide/[.05] px-4 py-3 text-[13px] font-medium text-oxide-2">
            {error}
          </div>
        )}

        <div className="mt-8 grid gap-10 lg:grid-cols-3">
          <section className="lg:col-span-2">
            <h2 className="text-[13px] font-bold uppercase tracking-[0.1em]">
              Review queue <span className="ml-1 font-mono text-sub">({items.length})</span>
            </h2>
            {items.length === 0 ? (
              <p className="mt-3 text-[13px] text-sub">
                Nothing needs a human right now. Upload bills in Invoices, import a statement in
                Books, or run a recon — anything an agent can't decide lands here.
              </p>
            ) : (
              <div className="mt-3 border-t border-rule">
                {items.map((item) => (
                  <Link
                    key={`${item.kind}-${item.ref}`}
                    to={item.link}
                    className="flex items-center gap-4 border-b border-rule py-3.5 transition-colors hover:bg-card"
                  >
                    <span
                      className={`px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.1em] ${AGENT_BADGE[item.agent]}`}
                    >
                      {AGENT_LABEL[item.agent]}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[14px] font-medium">{item.title}</span>
                      <span className="block truncate text-[12px] text-sub">{item.detail}</span>
                    </span>
                    <span className="whitespace-nowrap font-mono text-[11px] text-sub">
                      {ageLabel(item.age_days)}
                    </span>
                    {item.amount && (
                      <span className="whitespace-nowrap font-mono text-sm tabular-nums">
                        {inr(item.amount)}
                      </span>
                    )}
                    <span className="text-sub">→</span>
                  </Link>
                ))}
              </div>
            )}
            <p className="mt-4 text-[12px] leading-relaxed text-sub">
              Each row is a decision only a named human can make — nothing enters a headline
              number until someone here says so.
            </p>
          </section>

          <section>
            <div className="flex items-baseline justify-between">
              <h2 className="text-[13px] font-bold uppercase tracking-[0.1em]">Activity</h2>
              <Link
                to="/app/ops"
                className="text-[11px] font-bold uppercase tracking-[0.1em] text-sub underline decoration-rule-2 underline-offset-4 hover:text-ink"
              >
                Full log
              </Link>
            </div>
            <div className="mt-3 border-t border-rule">
              {events.map((ev) => (
                <div key={ev.event_id} className="border-b border-rule py-2.5">
                  <div className="flex items-baseline justify-between gap-3">
                    <span className="truncate text-[12.5px] font-medium">
                      {ev.action.replaceAll("_", " ")}
                    </span>
                    <span className="whitespace-nowrap font-mono text-[10px] text-sub">
                      {ev.ts.slice(11, 19)}
                    </span>
                  </div>
                  <div className="truncate font-mono text-[10.5px] text-sub">
                    {ev.agent.split("/")[0]}
                    {ev.actor && ` · ${ev.actor}`}
                  </div>
                </div>
              ))}
              {!events.length && (
                <p className="py-3 text-[12px] text-sub">No agent activity yet.</p>
              )}
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}
