export interface InvoiceSide {
  gstin: string;
  invoice_no: string;
  supplier_name: string;
  invoice_date: string;
  taxable_value: string;
  total_tax: string;
  source_ref: string;
}

export interface ExceptionItem {
  exception_id: string;
  bucket: string;
  itc_amount: string;
  reason: string;
  books: InvoiceSide | null;
  gstr2b: InvoiceSide | null;
  match_ratio: number | null;
  verified: boolean;
  verified_by: string;
  verified_at: string;
  ca_signoff: string;
}

export interface Report {
  report_id: string;
  client_name: string;
  created_at: string;
  period_note: string;
  matched_count: number;
  matched_tax_total: string;
  exceptions: ExceptionItem[];
  missed_itc: ExceptionItem[];
  unresolved: ExceptionItem[];
  verified_at_risk: string;
  pending_at_risk: string;
  missed_itc_total: string;
  unresolved_total: string;
  token: string;
  export_url: string;
}

export interface TrailEvent {
  event_id: number;
  agent: string;
  action: string;
  input_doc_ref: string;
  output_ref: string;
  actor: string;
  reviewed_by: string;
  ts: string;
}

export interface ReportResponse {
  report: Report;
  trail: TrailEvent[];
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

// The active workspace, set by AuthProvider. All org-scoped endpoints hang
// off /api/orgs/{org_id}; signed-link report endpoints stay unscoped.
let activeOrgId = "";

export function setApiOrg(orgId: string): void {
  activeOrgId = orgId;
}

function orgBase(): string {
  if (!activeOrgId) throw new Error("No active workspace. Sign in first.");
  return `/api/orgs/${encodeURIComponent(activeOrgId)}`;
}

export async function runRecon(form: FormData): Promise<{ report_id: string; token: string }> {
  return handle(await fetch(`${orgBase()}/recon`, { method: "POST", body: form }));
}

export async function getReport(token: string): Promise<ReportResponse> {
  return handle(await fetch(`/api/reports/${encodeURIComponent(token)}`));
}

export async function verifyException(token: string, exception_id: string): Promise<ReportResponse> {
  return handle(
    await fetch(`/api/reports/${encodeURIComponent(token)}/verify`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ exception_id }),
    }),
  );
}

export function inr(value: string | number): string {
  const n = typeof value === "string" ? parseFloat(value) : value;
  if (!isFinite(n)) return "₹0";
  return "₹" + n.toLocaleString("en-IN", { maximumFractionDigits: 0 });
}

// ---- Bank reconciliation ----

export interface BankSide {
  source: string;
  txn_date: string;
  description: string;
  ref: string;
  amount: string;
  source_ref: string;
}

export interface BankItem {
  item_id: string;
  bucket: string;
  amount: string;
  reason: string;
  bank: BankSide | null;
  books: BankSide | null;
}

export interface BankReport {
  report_id: string;
  client_name: string;
  created_at: string;
  period_note: string;
  matched_count: number;
  matched_total: string;
  unrecorded: BankItem[];
  uncleared: BankItem[];
  unrecorded_total: string;
  uncleared_total: string;
  token: string;
}

export async function runBankRec(form: FormData): Promise<{ report_id: string; token: string }> {
  return handle(await fetch(`${orgBase()}/bankrec`, { method: "POST", body: form }));
}

export async function getBankReport(token: string): Promise<{ report: BankReport }> {
  return handle(await fetch(`/api/bankrec/${encodeURIComponent(token)}`));
}

// ---- Close workbook ----

export interface CloseItem {
  key: string;
  title: string;
  done: boolean;
  done_by: string;
  done_at: string;
  note: string;
}

export interface CloseResponse {
  workbook: { period: string; items: CloseItem[] };
  done_count: number;
  periods: string[];
}

export async function getClose(period: string): Promise<CloseResponse> {
  return handle(await fetch(`${orgBase()}/close/${encodeURIComponent(period)}`));
}

export async function setCloseItem(
  period: string, key: string, done: boolean, note = "",
): Promise<CloseResponse> {
  return handle(
    await fetch(`${orgBase()}/close/${encodeURIComponent(period)}/item`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key, done, note }),
    }),
  );
}

// ---- Invoice Agent (AP capture) ----

export interface InvoiceFields {
  supplier_gstin: string;
  supplier_name: string;
  invoice_no: string;
  invoice_date: string;
  taxable_value: string;
  igst: string;
  cgst: string;
  sgst: string;
  cess: string;
  total: string;
}

export interface InvoiceDoc {
  invoice_id: string;
  period: string;
  created_at: string;
  status: "draft" | "confirmed";
  source_file: string;
  stored_file: string;
  extraction: "vision" | "manual" | "failed";
  fields: InvoiceFields;
  extraction_note: string;
  confirmed_by: string;
  confirmed_at: string;
  ca_signoff: string;
}

export async function uploadInvoice(period: string, file: File): Promise<{ invoice: InvoiceDoc }> {
  const form = new FormData();
  form.append("period", period);
  form.append("invoice_file", file);
  return handle(await fetch(`${orgBase()}/invoices`, { method: "POST", body: form }));
}

export async function listInvoices(
  period = "", status = "",
): Promise<{ invoices: InvoiceDoc[]; periods: string[] }> {
  const params = new URLSearchParams();
  if (period) params.set("period", period);
  if (status) params.set("status", status);
  return handle(await fetch(`${orgBase()}/invoices?${params}`));
}

export async function confirmInvoice(
  invoice_id: string, fields: InvoiceFields,
): Promise<{ invoice: InvoiceDoc; trail: TrailEvent[] }> {
  return handle(
    await fetch(`${orgBase()}/invoices/${encodeURIComponent(invoice_id)}/confirm`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fields }),
    }),
  );
}

export function registerCsvUrl(period: string): string {
  return `${orgBase()}/registers/${encodeURIComponent(period)}.csv`;
}

// ---- Bookkeeping Agent (transaction categorization) ----

export interface Account {
  code: string;
  name: string;
  type: string;
}

export interface CatRule {
  rule_id: string;
  priority: number;
  field: string;
  contains: string;
  account_code: string;
  created_by: string;
  created_at: string;
}

export interface LedgerTxn {
  txn_id: string;
  txn_date: string;
  description: string;
  ref: string;
  amount: string;
  source_ref: string;
  status: "pending" | "coded" | "confirmed";
  source: string;
  account_code: string;
  rule_id: string;
  suggested_account: string;
  confidence: string;
  confirmed_by: string;
  confirmed_at: string;
}

export interface LedgerSummary {
  accounts: Record<string, { count: number; total: string }>;
  txn_count: number;
  coded_count: number;
  confirmed_count: number;
  pending_count: number;
  pending_total: string;
}

export interface LedgerResponse {
  ledger: { period: string; created_at: string; txns: LedgerTxn[] };
  summary: LedgerSummary;
  account_names: Record<string, string>;
  periods: string[];
}

export async function importStatement(period: string, file: File): Promise<LedgerResponse> {
  const form = new FormData();
  form.append("statement_file", file);
  return handle(
    await fetch(`${orgBase()}/books/${encodeURIComponent(period)}/transactions`, {
      method: "POST",
      body: form,
    }),
  );
}

export async function getLedger(period: string): Promise<LedgerResponse> {
  return handle(await fetch(`${orgBase()}/books/${encodeURIComponent(period)}`));
}

export async function confirmTxn(
  period: string,
  txn_id: string,
  account_code: string,
  rule_pattern = "",
): Promise<LedgerResponse> {
  return handle(
    await fetch(
      `${orgBase()}/books/${encodeURIComponent(period)}/txn/${encodeURIComponent(txn_id)}/confirm`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ account_code, rule_pattern }),
      },
    ),
  );
}

export async function getCoa(): Promise<{ accounts: Account[] }> {
  return handle(await fetch(`${orgBase()}/books/coa`));
}

export async function getRules(): Promise<{ rules: CatRule[] }> {
  return handle(await fetch(`${orgBase()}/books/rules`));
}

export function ledgerCsvUrl(period: string): string {
  return `${orgBase()}/books/${encodeURIComponent(period)}/ledger.csv`;
}

// ---- Review Agent (monthly financial review) ----

export interface PnlLine {
  account_code: string;
  account_name: string;
  account_type: string;
  current: string;
  prior: string;
  change: string;
  change_pct: string;
}

export interface ReviewFlag {
  flag_id: string;
  kind: "variance" | "new_activity" | "round_sum" | "gst_drift";
  account_code: string;
  title: string;
  detail: string;
  amount: string;
  status: "pending" | "verified";
  verified_by: string;
  verified_at: string;
  ca_signoff: string;
}

export interface ReviewWorkbook {
  period: string;
  prior_period: string;
  created_at: string;
  pnl: PnlLine[];
  summary: { income: string; cogs: string; expense: string; net_result: string };
  flags: ReviewFlag[];
  narrative: string;
  narrative_note: string;
  txn_counts: { current: number; prior: number };
  verified_count: number;
  pending_count: number;
}

export interface ReviewResponse {
  workbook: ReviewWorkbook;
  periods: string[];
}

export async function buildReview(period: string): Promise<ReviewResponse> {
  return handle(
    await fetch(`${orgBase()}/review/${encodeURIComponent(period)}`, { method: "POST" }),
  );
}

export async function getReview(period: string): Promise<ReviewResponse> {
  return handle(await fetch(`${orgBase()}/review/${encodeURIComponent(period)}`));
}

export async function verifyReviewFlag(period: string, flag_id: string): Promise<ReviewResponse> {
  return handle(
    await fetch(
      `${orgBase()}/review/${encodeURIComponent(period)}/flags/${encodeURIComponent(flag_id)}/verify`,
      { method: "POST" },
    ),
  );
}

// ---- Agent Workspace (unified review queue) ----

export interface WorkItem {
  agent: "itc-recon" | "invoice" | "bookkeeping" | "close" | "review";
  kind: string;
  title: string;
  detail: string;
  amount: string;
  count: number;
  ref: string;
  age_days: number;
  link: string;
}

export interface WorkqueueResponse {
  items: WorkItem[];
  total_decisions: number;
  by_agent: Record<string, number>;
}

export async function getWorkqueue(): Promise<WorkqueueResponse> {
  return handle(await fetch(`${orgBase()}/workqueue`));
}

// ---- Auth & org management ----

export interface InvitePreview {
  org_name: string;
  role: string;
  email: string;
}

export interface OrgMember {
  user_id: string;
  email: string;
  display_name: string;
  ca_membership_no: string;
  role: string;
  joined_at: string;
}

export interface PendingInvite {
  invite_id: string;
  role: string;
  email: string;
  created_at: string;
  expires_at: string;
}

export interface CreatedInvite {
  invite_token: string;
  invite_path: string;
  role: string;
  expires_days: number;
}

export async function previewInvite(token: string): Promise<InvitePreview> {
  return handle(await fetch(`/api/invites/${encodeURIComponent(token)}`));
}

export async function createInvite(orgId: string, role: string, email = ""): Promise<CreatedInvite> {
  return handle(
    await fetch(`/api/orgs/${encodeURIComponent(orgId)}/invites`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role, email }),
    }),
  );
}

export async function listInvites(orgId: string): Promise<{ invites: PendingInvite[] }> {
  return handle(await fetch(`/api/orgs/${encodeURIComponent(orgId)}/invites`));
}

export async function listMembers(orgId: string): Promise<{ members: OrgMember[] }> {
  return handle(await fetch(`/api/orgs/${encodeURIComponent(orgId)}/members`));
}

export async function setMemberRole(orgId: string, userId: string, role: string): Promise<{ ok: boolean }> {
  return handle(
    await fetch(`/api/orgs/${encodeURIComponent(orgId)}/members/${encodeURIComponent(userId)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role }),
    }),
  );
}

export async function removeMember(orgId: string, userId: string): Promise<{ ok: boolean }> {
  return handle(
    await fetch(`/api/orgs/${encodeURIComponent(orgId)}/members/${encodeURIComponent(userId)}`, {
      method: "DELETE",
    }),
  );
}

// ---- Operations feed ----

export async function getOperations(limit = 25): Promise<{ events: TrailEvent[] }> {
  return handle(await fetch(`${orgBase()}/operations?limit=${limit}`));
}
