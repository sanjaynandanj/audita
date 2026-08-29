import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import Nav from "../components/Nav";
import { useAuth } from "../lib/auth";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await login(email.trim(), password);
      navigate(params.get("next") ?? "/app");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen bg-paper text-ink">
      <Nav />
      <main className="mx-auto max-w-sm px-6 pt-20 pb-24">
        <div className="label-caps">Sign in</div>
        <h1 className="mt-2 text-3xl font-extrabold tracking-tight">Welcome back</h1>

        <form onSubmit={submit} className="mt-10 space-y-6">
          <div>
            <label className="label-caps block">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              required
              className="w-full border-0 border-b border-rule-2 bg-transparent px-0 py-1.5 text-sm outline-none focus:border-ink"
            />
          </div>
          <div>
            <label className="label-caps block">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
              className="w-full border-0 border-b border-rule-2 bg-transparent px-0 py-1.5 text-sm outline-none focus:border-ink"
            />
          </div>

          {error && <p className="text-sm font-medium text-oxide-2">{error}</p>}

          <button
            type="submit"
            disabled={busy || !email.trim() || !password}
            className="w-full bg-ink px-7 py-3.5 text-[13px] font-bold uppercase tracking-[0.08em] text-paper transition-opacity disabled:opacity-40"
          >
            {busy ? "…" : "Sign in"}
          </button>
        </form>

        <p className="mt-8 text-sm text-sub">
          New to Audita?{" "}
          <Link to="/signup" className="font-semibold text-ink underline underline-offset-4">
            Create a workspace
          </Link>
        </p>
      </main>
    </div>
  );
}
