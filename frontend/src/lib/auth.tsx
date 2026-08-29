import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { setApiOrg } from "./api";

export interface AuthUser {
  user_id: string;
  email: string;
  display_name: string;
  ca_membership_no: string;
}

export interface AuthMembership {
  org_id: string;
  org_name: string;
  role: "owner" | "preparer" | "reviewer" | "viewer";
}

interface MeResponse {
  user: AuthUser;
  memberships: AuthMembership[];
}

export interface SignupPayload {
  email: string;
  password: string;
  display_name: string;
  org_name?: string;
  invite_token?: string;
  ca_membership_no?: string;
}

interface AuthState {
  loading: boolean;
  user: AuthUser | null;
  memberships: AuthMembership[];
  activeOrg: AuthMembership | null;
  setActiveOrgId: (orgId: string) => void;
  login: (email: string, password: string) => Promise<void>;
  signup: (payload: SignupPayload) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

const ORG_KEY = "audita-active-org";

const AuthContext = createContext<AuthState | null>(null);

async function post<T>(url: string, body?: unknown): Promise<T> {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* non-JSON */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [loading, setLoading] = useState(true);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [memberships, setMemberships] = useState<AuthMembership[]>([]);
  const [activeOrgId, setActiveOrgIdState] = useState<string>(() => localStorage.getItem(ORG_KEY) ?? "");

  const apply = useCallback((me: MeResponse | null) => {
    setUser(me?.user ?? null);
    setMemberships(me?.memberships ?? []);
  }, []);

  const refresh = useCallback(async () => {
    try {
      const res = await fetch("/api/auth/me");
      apply(res.ok ? ((await res.json()) as MeResponse) : null);
    } catch {
      apply(null);
    }
  }, [apply]);

  useEffect(() => {
    refresh().finally(() => setLoading(false));
  }, [refresh]);

  const setActiveOrgId = useCallback((orgId: string) => {
    localStorage.setItem(ORG_KEY, orgId);
    setActiveOrgIdState(orgId);
  }, []);

  const activeOrg = useMemo(() => {
    if (memberships.length === 0) return null;
    return memberships.find((m) => m.org_id === activeOrgId) ?? memberships[0];
  }, [memberships, activeOrgId]);

  // Synchronous on purpose: children render (and fetch) in the same pass,
  // so an effect would leave the first page load without an org.
  setApiOrg(activeOrg?.org_id ?? "");

  const login = useCallback(
    async (email: string, password: string) => {
      apply(await post<MeResponse>("/api/auth/login", { email, password }));
    },
    [apply],
  );

  const signup = useCallback(
    async (payload: SignupPayload) => {
      apply(await post<MeResponse>("/api/auth/signup", payload));
    },
    [apply],
  );

  const logout = useCallback(async () => {
    await post("/api/auth/logout");
    apply(null);
  }, [apply]);

  const value: AuthState = {
    loading,
    user,
    memberships,
    activeOrg,
    setActiveOrgId,
    login,
    signup,
    logout,
    refresh,
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
}
