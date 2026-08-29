import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../lib/auth";

export default function Nav() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { loading, user, memberships, activeOrg, setActiveOrgId, logout } = useAuth();
  const onLanding = pathname === "/";

  async function handleLogout() {
    await logout();
    navigate("/");
  }

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
          {!loading && user ? (
            <>
              {memberships.length > 1 ? (
                <select
                  value={activeOrg?.org_id ?? ""}
                  onChange={(e) => setActiveOrgId(e.target.value)}
                  className="hidden max-w-40 border-0 border-b border-rule-2 bg-transparent py-1 text-[13px] font-medium text-ink outline-none sm:block"
                >
                  {memberships.map((m) => (
                    <option key={m.org_id} value={m.org_id}>{m.org_name}</option>
                  ))}
                </select>
              ) : (
                <span className="hidden text-[13px] font-medium text-sub sm:block">{activeOrg?.org_name}</span>
              )}
              <span className="hidden text-[13px] font-semibold text-ink md:block">{user.display_name}</span>
              <button
                onClick={handleLogout}
                className="text-[13px] font-medium text-sub hover:text-ink"
              >
                Sign out
              </button>
              <Link
                to="/app"
                className="border border-ink bg-ink px-5 py-2 text-[13px] font-semibold text-paper transition-colors hover:bg-paper hover:text-ink"
              >
                Open workspace
              </Link>
            </>
          ) : (
            !loading && (
              <>
                <Link to="/login" className="text-[13px] font-medium text-sub hover:text-ink">
                  Sign in
                </Link>
                <Link
                  to="/signup"
                  className="border border-ink bg-ink px-5 py-2 text-[13px] font-semibold text-paper transition-colors hover:bg-paper hover:text-ink"
                >
                  Get started
                </Link>
              </>
            )
          )}
        </div>
      </div>
    </nav>
  );
}
