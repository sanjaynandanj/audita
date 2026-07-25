import { Link, useLocation } from "react-router-dom";

export default function Nav() {
  const { pathname } = useLocation();
  const onLanding = pathname === "/";
  return (
    <nav className="sticky top-0 z-50 border-b border-rule bg-paper/95 backdrop-blur-sm">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
        <Link to="/" className="flex items-baseline gap-3">
          <span className="text-xl font-extrabold uppercase tracking-tight text-ink">Audita</span>
          <span className="label-caps hidden sm:inline">GST audit agents</span>
        </Link>
        <div className="flex items-center gap-7">
          {onLanding && (
            <>
              <a href="#agents" className="hidden text-[13px] font-medium text-sub hover:text-ink md:block">The agents</a>
              <a href="#method" className="hidden text-[13px] font-medium text-sub hover:text-ink md:block">Method</a>
              <a href="#notes" className="hidden text-[13px] font-medium text-sub hover:text-ink md:block">Notes</a>
            </>
          )}
          <Link
            to="/app/recon"
            className="border border-ink bg-ink px-5 py-2 text-[13px] font-semibold text-paper transition-colors hover:bg-paper hover:text-ink"
          >
            Run a recon
          </Link>
        </div>
      </div>
    </nav>
  );
}
