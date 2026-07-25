import { Link, useLocation } from "react-router-dom";

const tabs = [
  { to: "/app", label: "ITC Recon", match: (p: string) => p === "/app" || p.startsWith("/app/r/") },
  { to: "/app/bank", label: "Bank Recon", match: (p: string) => p.startsWith("/app/bank") },
  { to: "/app/invoices", label: "Invoices", match: (p: string) => p.startsWith("/app/invoices") },
  { to: "/app/books", label: "Books", match: (p: string) => p.startsWith("/app/books") },
  { to: "/app/review", label: "Review", match: (p: string) => p.startsWith("/app/review") },
  { to: "/app/close", label: "Close", match: (p: string) => p.startsWith("/app/close") },
  { to: "/app/ops", label: "Operations", match: (p: string) => p.startsWith("/app/ops") },
];

export default function AppTabs() {
  const { pathname } = useLocation();
  return (
    <div className="border-b border-rule bg-paper">
      <div className="mx-auto flex max-w-6xl gap-1 px-6">
        {tabs.map((t) => {
          const active = t.match(pathname);
          return (
            <Link
              key={t.to}
              to={t.to}
              className={`-mb-px border-b-2 px-4 py-3 text-[12px] font-bold uppercase tracking-[0.1em] transition-colors ${
                active ? "border-ink text-ink" : "border-transparent text-sub hover:text-ink"
              }`}
            >
              {t.label}
            </Link>
          );
        })}
      </div>
    </div>
  );
}
