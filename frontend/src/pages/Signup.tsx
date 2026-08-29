import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import Nav from "../components/Nav";
import { useAuth } from "../lib/auth";
import { previewInvite } from "../lib/api";
import type { InvitePreview } from "../lib/api";

export default function Signup() {
  const { signup } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const inviteToken = params.get("invite") ?? "";

  const [invite, setInvite] = useState<InvitePreview | null>(null);
  const [inviteError, setInviteError] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [orgName, setOrgName] = useState("");
  const [caNo, setCaNo] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!inviteToken) return;
    previewInvite(inviteToken)
      .then((p) => {
        setInvite(p);
        if (p.email) setEmail(p.email);
      })
      .catch((err) => setInviteError(err instanceof Error ? err.message : "Invalid invite."));
  }, [inviteToken]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await signup({
        email: email.trim(),
        password,
        display_name: displayName.trim(),
        org_name: inviteToken ? "" : orgName.trim(),
        invite_token: inviteToken,
        ca_membership_no: caNo.trim(),
      });
      navigate("/app");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Signup failed.");
    } finally {
      setBusy(false);
    }
  }

  const field =
    "w-full border-0 border-b border-rule-2 bg-transparent px-0 py-1.5 text-sm outline-none focus:border-ink";

  return (
    <div className="min-h-screen bg-paper text-ink">
      <Nav />
      <main className="mx-auto max-w-sm px-6 pt-20 pb-24">
        <div className="label-caps">{invite ? "Join workspace" : "Get started"}</div>
        <h1 className="mt-2 text-3xl font-extrabold tracking-tight">
          {invite ? invite.org_name : "Create your workspace"}
        </h1>

        {inviteToken && inviteError && (
          <p className="mt-6 border border-oxide bg-oxide/[.05] px-4 py-3 text-sm font-medium text-oxide-2">
            {inviteError}
          </p>
        )}
        {invite && (
          <p className="mt-4 text-sm text-sub">
            You are joining <span className="font-semibold text-ink">{invite.org_name}</span> as{" "}
            <span className="font-semibold text-ink">{invite.role}</span>.
          </p>
        )}

        <form onSubmit={submit} className="mt-10 space-y-6">
          <div>
            <label className="label-caps block">Your name</label>
            <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} required className={field} />
          </div>
          <div>
            <label className="label-caps block">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              required
              className={field}
            />
          </div>
          <div>
            <label className="label-caps block">Password (8+ characters)</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="new-password"
              minLength={8}
              required
              className={field}
            />
          </div>
          {!inviteToken && (
            <div>
              <label className="label-caps block">Workspace name</label>
              <input
                value={orgName}
                onChange={(e) => setOrgName(e.target.value)}
                placeholder="Your business or practice"
                required
                className={field}
              />
            </div>
          )}
          <div>
            <label className="label-caps block">CA membership no. (optional)</label>
            <input value={caNo} onChange={(e) => setCaNo(e.target.value)} className={field} />
          </div>

          {error && <p className="text-sm font-medium text-oxide-2">{error}</p>}

          <button
            type="submit"
            disabled={busy || Boolean(inviteToken && inviteError)}
            className="w-full bg-ink px-7 py-3.5 text-[13px] font-bold uppercase tracking-[0.08em] text-paper transition-opacity disabled:opacity-40"
          >
            {busy ? "…" : invite ? "Join workspace" : "Create workspace"}
          </button>
        </form>

        <p className="mt-8 text-sm text-sub">
          Already have an account?{" "}
          <Link to="/login" className="font-semibold text-ink underline underline-offset-4">
            Sign in
          </Link>
        </p>
      </main>
    </div>
  );
}
