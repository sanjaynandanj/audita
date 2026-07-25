import { useEffect, useState } from "react";
import Nav from "../components/Nav";
import AppTabs from "../components/AppTabs";
import { type CloseResponse, getClose, setCloseItem } from "../lib/api";

function currentPeriod(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export default function Close() {
  const [period, setPeriod] = useState(currentPeriod());
  const [data, setData] = useState<CloseResponse | null>(null);
  const [actor, setActor] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    getClose(period).then(setData).catch((e: Error) => setError(e.message));
  }, [period]);

  async function toggle(key: string, done: boolean) {
    if (done && !actor.trim()) { setError("Enter your name (top right) before ticking items."); return; }
    setError("");
    const res = await setCloseItem(period, key, done, actor.trim());
    setData(res);
  }

  const items = data?.workbook.items ?? [];
  const doneCount = data?.done_count ?? 0;
  const pct = items.length ? Math.round((doneCount / items.length) * 100) : 0;

  return (
    <div className="min-h-screen bg-paper pb-24 text-ink">
      <Nav /><AppTabs />
      <main className="mx-auto max-w-4xl px-6 pt-10">
        <div className="flex flex-wrap items-end justify-between gap-6 border-b-2 border-ink pb-5">
          <div>
            <div className="label-caps">Close Agent · Month-end workbook</div>
            <h1 className="mt-2 text-3xl font-extrabold tracking-tight">Close {period}</h1>
          </div>
          <div className="flex items-end gap-4">
            <div>
              <label className="label-caps block">Period</label>
              <input
                type="month" value={period} onChange={(e) => setPeriod(e.target.value)}
                className="border-0 border-b border-rule-2 bg-transparent px-0 py-1.5 font-mono text-sm outline-none focus:border-ink"
              />
            </div>
            <div>
              <label className="label-caps block">Your name</label>
              <input
                value={actor} onChange={(e) => setActor(e.target.value)} placeholder="Reviewer"
                className="border-0 border-b border-rule-2 bg-transparent px-0 py-1.5 text-sm outline-none focus:border-ink"
              />
            </div>
          </div>
        </div>

        <div className="mt-6 flex items-center gap-4">
          <div className="h-2 flex-1 bg-rule/60">
            <div className="h-full bg-ledger transition-all duration-500" style={{ width: `${pct}%` }} />
          </div>
          <div className="font-mono text-sm font-semibold tabular-nums">{doneCount}/{items.length} · {pct}%</div>
        </div>

        {error && (
          <div className="mt-5 border-l-2 border-oxide bg-oxide/[.05] px-4 py-3 text-[13px] font-medium text-oxide-2">
            {error}
          </div>
        )}

        <div className="mt-8 border-t border-rule">
          {items.map((item, idx) => (
            <label
              key={item.key}
              className="flex cursor-pointer items-start gap-4 border-b border-rule py-4 transition-colors hover:bg-card"
            >
              <input
                type="checkbox" checked={item.done}
                onChange={(e) => toggle(item.key, e.target.checked)}
                className="mt-1 h-4 w-4 accent-[#17140e]"
              />
              <span className="w-7 pt-0.5 font-mono text-xs text-sub">{String(idx + 1).padStart(2, "0")}</span>
              <span className="flex-1">
                <span className={`text-[14.5px] font-medium ${item.done ? "text-sub line-through decoration-rule-2" : ""}`}>
                  {item.title}
                </span>
                {item.done && (
                  <span className="ml-3 font-mono text-[11px] text-ledger">
                    ✓ {item.done_by} · {item.done_at.slice(0, 10)}
                  </span>
                )}
                {item.note && <span className="ml-3 text-[12px] italic text-sub">{item.note}</span>}
              </span>
            </label>
          ))}
        </div>

        <p className="mt-6 text-[12px] leading-relaxed text-sub">
          Every tick and un-tick is written to the append-only event log with your name on it.
          The workbook is per-period — switch the month above to roll forward.
        </p>
      </main>
    </div>
  );
}
