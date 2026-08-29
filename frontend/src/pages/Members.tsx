import { useCallback, useEffect, useState } from "react";
import Nav from "../components/Nav";
import AppTabs from "../components/AppTabs";
import { useAuth } from "../lib/auth";
import {
  createInvite,
  listInvites,
  listMembers,
  removeMember,
  setMemberRole,
} from "../lib/api";
import type { OrgMember, PendingInvite } from "../lib/api";

const ROLES = ["owner", "reviewer", "preparer", "viewer"];
const INVITE_ROLES = ["preparer", "reviewer", "viewer"];

export default function Members() {
  const { user, activeOrg } = useAuth();
  const [members, setMembers] = useState<OrgMember[]>([]);
  const [invites, setInvites] = useState<PendingInvite[]>([]);
  const [inviteRole, setInviteRole] = useState("preparer");
  const [inviteUrl, setInviteUrl] = useState("");
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const orgId = activeOrg?.org_id ?? "";

  const load = useCallback(() => {
    if (!orgId) return;
    setError("");
    Promise.all([listMembers(orgId), listInvites(orgId)])
      .then(([m, i]) => {
        setMembers(m.members);
        setInvites(i.invites);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load members."));
  }, [orgId]);

  useEffect(load, [load]);

  async function makeInvite() {
    setBusy(true);
    setError("");
    setCopied(false);
    try {
      const inv = await createInvite(orgId, inviteRole);
      setInviteUrl(`${window.location.origin}${inv.invite_path}`);
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create invite.");
    } finally {
      setBusy(false);
    }
  }

  async function copyInvite() {
    await navigator.clipboard.writeText(inviteUrl);
    setCopied(true);
  }

  async function changeRole(member: OrgMember, role: string) {
    setError("");
    try {
      await setMemberRole(orgId, member.user_id, role);
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to change role.");
    }
  }

  async function remove(member: OrgMember) {
    if (!window.confirm(`Remove ${member.display_name} from ${activeOrg?.org_name}?`)) return;
    setError("");
    try {
      await removeMember(orgId, member.user_id);
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to remove member.");
    }
  }

  return (
    <div className="min-h-screen bg-paper pb-24 text-ink">
      <Nav />
      <AppTabs />
      <main className="mx-auto max-w-6xl px-6 pt-10">
        <div className="flex flex-wrap items-end justify-between gap-6 border-b-2 border-ink pb-5">
          <div>
            <div className="label-caps">Workspace</div>
            <h1 className="mt-2 text-3xl font-extrabold tracking-tight">Members</h1>
          </div>
          <div className="flex items-end gap-4">
            <div>
              <label className="label-caps block">Invite as</label>
              <select
                value={inviteRole}
                onChange={(e) => setInviteRole(e.target.value)}
                className="border-0 border-b border-rule-2 bg-transparent px-0 py-1.5 text-sm outline-none focus:border-ink"
              >
                {INVITE_ROLES.map((r) => (
                  <option key={r} value={r}>{r}</option>
                ))}
              </select>
            </div>
            <button
              onClick={makeInvite}
              disabled={busy || !orgId}
              className="bg-ink px-4 py-1.5 text-[11px] font-bold uppercase tracking-[0.1em] text-paper transition-opacity disabled:opacity-40"
            >
              {busy ? "…" : "Create invite link"}
            </button>
          </div>
        </div>

        {error && <p className="mt-6 text-sm font-medium text-oxide-2">{error}</p>}

        {inviteUrl && (
          <div className="mt-6 flex flex-wrap items-center gap-3 border border-rule bg-card px-4 py-3">
            <span className="label-caps">Invite link (7 days, one use)</span>
            <code className="max-w-full overflow-x-auto text-[12px] text-ink">{inviteUrl}</code>
            <button
              onClick={copyInvite}
              className="border border-ink px-3 py-1 text-[11px] font-bold uppercase tracking-[0.1em] text-ink"
            >
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
        )}

        <table className="mt-8 w-full text-left text-sm">
          <thead>
            <tr className="border-b border-rule-2">
              <th className="label-caps py-2">Name</th>
              <th className="label-caps py-2">Email</th>
              <th className="label-caps py-2">CA no.</th>
              <th className="label-caps py-2">Role</th>
              <th className="py-2" />
            </tr>
          </thead>
          <tbody>
            {members.map((m) => (
              <tr key={m.user_id} className="border-b border-rule">
                <td className="py-3 font-semibold">{m.display_name}{m.user_id === user?.user_id && " (you)"}</td>
                <td className="py-3 text-sub">{m.email}</td>
                <td className="py-3 text-sub">{m.ca_membership_no || "—"}</td>
                <td className="py-3">
                  <select
                    value={m.role}
                    onChange={(e) => changeRole(m, e.target.value)}
                    className="border-0 border-b border-rule-2 bg-transparent px-0 py-1 text-sm outline-none focus:border-ink"
                  >
                    {ROLES.map((r) => (
                      <option key={r} value={r}>{r}</option>
                    ))}
                  </select>
                </td>
                <td className="py-3 text-right">
                  {m.user_id !== user?.user_id && (
                    <button onClick={() => remove(m)} className="text-[12px] font-semibold text-oxide-2 hover:underline">
                      Remove
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {invites.length > 0 && (
          <>
            <h2 className="label-caps mt-12">Pending invites</h2>
            <table className="mt-3 w-full text-left text-sm">
              <tbody>
                {invites.map((i) => (
                  <tr key={i.invite_id} className="border-b border-rule">
                    <td className="py-2 font-semibold">{i.role}</td>
                    <td className="py-2 text-sub">{i.email || "anyone with the link"}</td>
                    <td className="py-2 text-sub">expires {new Date(i.expires_at).toLocaleDateString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </main>
    </div>
  );
}
