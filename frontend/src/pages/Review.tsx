import { Fragment, useCallback, useEffect, useState } from "react";
import Nav from "../components/Nav";
import AppTabs from "../components/AppTabs";
import {
  type PnlLine,
  type ReviewFlag,
  type ReviewWorkbook,
  buildReview,
  getReview,
  inr,
  verifyReviewFlag,
} from "../lib/api";

function currentPeriod(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

const KIND_LABEL: Record<ReviewFlag["kind"], string> = {
  variance: "Variance",
  new_activity: "New counterparty",
  round_sum: "Round sum",
  gst_drift: "GST drift",
};

const TYPE_ORDER = ["income", "cogs", "expense", "tax", "asset", "liability", "equity", "unknown"];

function FlagRow({
  flag,
  period,
  actor,
  onUpdated,
  onError,
}: {
  flag: ReviewFlag;
  period: string;
  actor: string;
  onUpdated: (wb: ReviewWorkbook) => void;
  onError: (msg: string) => void;
}) {
  const [signoff, setSignoff] = useState("");
  const [busy, setBusy] = useState(false);

  async function verify() {
    setBusy(true);
    try {
      const r = await verifyReviewFlag(period, flag.flag_id, actor.trim(), signoff.trim());
      onUpdated(r.workbook);
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="border-b border-rule py-3">
      <div className="flex flex-wrap items-start gap-3">
        <span
          className={`mt-0.5 px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.1em] ${
            flag.status === "verified" ? "bg-ledger/10 text-ledger" : "bg-oxide/10 text-oxide-2"
          }`}
        >
          {KIND_LABEL[flag.kind]}
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-[14px] font-medium">{flag.title}</div>
          <div className="mt-0.5 font-mono text-[11px] text-sub">{flag.detail}</div>
        </div>
        <span className="font-mono text-sm tabular-nums">{inr(flag.amount)}</span>
        {flag.status === "verified" ? (
          <span className="text-[12px] text-ledger">
            ✓ {flag.verified_by}
            {flag.ca_signoff && <span className="ml-1 font-mono text-[11px]">({flag.ca_signoff})</span>}
          </span>
        ) : (
          <span className="flex items-center gap-2">
            <input
              value={signoff}
              onChange={(e) => setSignoff(e.target.value)}
              placeholder="CA sign-off (optional)"
              className="w-40 border-0 border-b border-rule-2 bg-transparent px-0 py-1 text-[12px] outline-none placeholder:text-sub/70 focus:border-ink"
            />
            <button
              onClick={verify}
              disabled={busy || !actor.trim()}
              className="bg-ink px-3 py-1.5 text-[11px] font-bold uppercase tracking-[0.1em] text-paper transition-opacity disabled:opacity-40"
            >
              {busy ? "…" : "Verify"}
            </button>
          </span>
        )}
      </div>
    </div>
  );
}

export default function Review() {
  const [period, setPeriod] = useState(currentPeriod());
  const [workbook, setWorkbook] = useState<ReviewWorkbook | null>(null);
  const [actor, setActor] = useState("");
  const [error, setError] = useState("");
  const [notFound, setNotFound] = useState(false);
  const [building, setBuilding] = useState(false);

  const refresh = useCallback(() => {
    setError("");
    getReview(period)
      .then((r) => {
        setWorkbook(r.workbook);
        setNotFound(false);
      })
      .catch(() => {
        setWorkbook(null);
        setNotFound(true);
      });
  }, [period]);

  useEffect(refresh, [refresh]);

  async function build() {
    setBuilding(true);
    setError("");
    try {
      const r = await buildReview(period);
      setWorkbook(r.workbook);
      setNotFound(false);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBuilding(false);
    }
  }

  const pnlByType = new Map<string, PnlLine[]>();
  if (workbook) {
    for (const line of workbook.pnl) {
      const list = pnlByType.get(line.account_type) ?? [];
      list.push(line);
      pnlByType.set(line.account_type, list);
    }
  }

  return (
    <div className="min-h-screen bg-paper pb-24 text-ink">
      <Nav />
      <AppTabs />
      <main className="mx-auto max-w-5xl px-6 pt-10">
        <div className="flex flex-wrap items-end justify-between gap-6 border-b-2 border-ink pb-5">
          <div>
            <div className="label-caps">Review Agent · monthly financial review</div>
            <h1 className="mt-2 text-3xl font-extrabold tracking-tight">Review {period}</h1>
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
            <button
              onClick={build}
              disabled={building}
              className="bg-ink px-5 py-2 text-[12px] font-bold uppercase tracking-[0.1em] text-paper transition-opacity disabled:opacity-40"
            >
              {building ? "Computing…" : workbook ? "Rebuild workbook" : "Build workbook"}
            </button>
          </div>
        </div>

        {error && (
          <div className="mt-5 border-l-2 border-oxide bg-oxide/[.05] px-4 py-3 text-[13px] font-medium text-oxide-2">
            {error}
          </div>
        )}

        {notFound && !error && (
          <p className="mt-8 text-[13px] text-sub">
            No review workbook for {period} yet. Code the month's transactions in Books, then
            build. Every figure is computed deterministically from the categorized ledger —
            verified and rule-coded entries only.
          </p>
        )}

        {workbook && (
          <>
            <div className="mt-8 grid grid-cols-2 gap-px border border-rule bg-rule sm:grid-cols-4">
              {[
                ["Income", workbook.summary.income],
                ["COGS", workbook.summary.cogs],
                ["Expenses", workbook.summary.expense],
                ["Net result", workbook.summary.net_result],
              ].map(([label, value]) => (
                <div key={label} className="bg-paper px-4 py-3">
                  <div className="label-caps">{label}</div>
                  <div className="mt-1 font-mono text-xl font-bold tabular-nums">{inr(value)}</div>
                </div>
              ))}
            </div>

            <section className="mt-10">
              <h2 className="text-[13px] font-bold uppercase tracking-[0.1em]">
                Movement vs {workbook.prior_period}
              </h2>
              <table className="mt-3 w-full border-collapse text-[13px]">
                <thead>
                  <tr className="border-b-2 border-ink text-left">
                    <th className="py-2 pr-4 label-caps">Account</th>
                    <th className="py-2 pr-4 text-right label-caps">{workbook.prior_period}</th>
                    <th className="py-2 pr-4 text-right label-caps">{workbook.period}</th>
                    <th className="py-2 pr-4 text-right label-caps">Change</th>
                    <th className="py-2 text-right label-caps">%</th>
                  </tr>
                </thead>
                <tbody>
                  {TYPE_ORDER.filter((t) => pnlByType.has(t)).map((type) => (
                    <Fragment key={type}>
                      <tr className="border-b border-rule bg-card">
                        <td colSpan={5} className="py-1.5 label-caps">{type}</td>
                      </tr>
                      {pnlByType.get(type)!.map((line) => (
                        <tr key={line.account_code} className="border-b border-rule">
                          <td className="py-2 pr-4">
                            <span className="font-mono text-xs text-sub">{line.account_code}</span>{" "}
                            {line.account_name}
                          </td>
                          <td className="py-2 pr-4 text-right font-mono tabular-nums">{inr(line.prior)}</td>
                          <td className="py-2 pr-4 text-right font-mono tabular-nums">{inr(line.current)}</td>
                          <td className="py-2 pr-4 text-right font-mono tabular-nums">{inr(line.change)}</td>
                          <td className="py-2 text-right font-mono tabular-nums">
                            {line.change_pct ? `${line.change_pct}%` : "—"}
                          </td>
                        </tr>
                      ))}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </section>

            <section className="mt-12">
              <h2 className="text-[13px] font-bold uppercase tracking-[0.1em]">
                Flags{" "}
                <span className="ml-1 font-mono text-sub">
                  ({workbook.verified_count} verified · {workbook.pending_count} pending)
                </span>
              </h2>
              {workbook.flags.length === 0 ? (
                <p className="mt-3 text-[13px] text-sub">Nothing flagged for this period.</p>
              ) : (
                <div className="mt-3 border-t border-rule">
                  {workbook.flags.map((flag) => (
                    <FlagRow
                      key={flag.flag_id}
                      flag={flag}
                      period={period}
                      actor={actor}
                      onUpdated={setWorkbook}
                      onError={setError}
                    />
                  ))}
                </div>
              )}
              {workbook.pending_count > 0 && !actor.trim() && (
                <p className="mt-2 text-[12px] italic text-sub">
                  Enter your name under “Working as” to verify flags.
                </p>
              )}
            </section>

            <section className="mt-12">
              <h2 className="text-[13px] font-bold uppercase tracking-[0.1em]">Review notes</h2>
              {workbook.narrative ? (
                <div className="mt-3 whitespace-pre-wrap border-l-2 border-rule-2 bg-card px-5 py-4 text-[13.5px] leading-relaxed">
                  {workbook.narrative}
                  <p className="mt-3 text-[11px] italic text-sub">
                    Narrated by the agent from computed figures only — the numbers above are the
                    authority, the prose is commentary.
                  </p>
                </div>
              ) : (
                <p className="mt-3 text-[13px] text-sub">{workbook.narrative_note}</p>
              )}
            </section>
          </>
        )}

        <p className="mt-8 text-[12px] leading-relaxed text-sub">
          The review workbook is an annex to the month-end close: deterministic P&L movement and
          anomaly flags from the categorized ledger, with named verification and CA sign-off on
          every flag. Rebuilding recomputes the figures; verified flags keep their sign-off when
          the finding is unchanged.
        </p>
      </main>
    </div>
  );
}
