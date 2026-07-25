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

export async function runRecon(form: FormData): Promise<{ report_id: string; token: string }> {
  return handle(await fetch("/api/recon", { method: "POST", body: form }));
}

export async function getReport(token: string): Promise<ReportResponse> {
  return handle(await fetch(`/api/reports/${encodeURIComponent(token)}`));
}

export async function verifyException(
  token: string,
  exception_id: string,
  actor: string,
  ca_signoff: string,
): Promise<ReportResponse> {
  return handle(
    await fetch(`/api/reports/${encodeURIComponent(token)}/verify`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ exception_id, actor, ca_signoff }),
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
  return handle(await fetch("/api/bankrec", { method: "POST", body: form }));
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
  return handle(await fetch(`/api/close/${encodeURIComponent(period)}`));
}

export async function setCloseItem(
  period: string, key: string, done: boolean, actor: string, note = "",
): Promise<CloseResponse> {
  return handle(
    await fetch(`/api/close/${encodeURIComponent(period)}/item`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key, done, actor, note }),
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
  return handle(await fetch("/api/invoices", { method: "POST", body: form }));
}

export async function listInvoices(
  period = "", status = "",
): Promise<{ invoices: InvoiceDoc[]; periods: string[] }> {
  const params = new URLSearchParams();
  if (period) params.set("period", period);
  if (status) params.set("status", status);
  return handle(await fetch(`/api/invoices?${params}`));
}

export async function confirmInvoice(
  invoice_id: string, fields: InvoiceFields, actor: string, ca_signoff = "",
): Promise<{ invoice: InvoiceDoc; trail: TrailEvent[] }> {
  return handle(
    await fetch(`/api/invoices/${encodeURIComponent(invoice_id)}/confirm`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fields, actor, ca_signoff }),
    }),
  );
}

export function registerCsvUrl(period: string): string {
  return `/api/registers/${encodeURIComponent(period)}.csv`;
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
    await fetch(`/api/books/${encodeURIComponent(period)}/transactions`, {
      method: "POST",
      body: form,
    }),
  );
}

export async function getLedger(period: string): Promise<LedgerResponse> {
  return handle(await fetch(`/api/books/${encodeURIComponent(period)}`));
}

export async function confirmTxn(
  period: string,
  txn_id: string,
  account_code: string,
  actor: string,
  rule_pattern = "",
): Promise<LedgerResponse> {
  return handle(
    await fetch(
      `/api/books/${encodeURIComponent(period)}/txn/${encodeURIComponent(txn_id)}/confirm`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ account_code, actor, rule_pattern }),
      },
    ),
  );
}

export async function getCoa(): Promise<{ accounts: Account[] }> {
  return handle(await fetch("/api/books/coa"));
}

export async function getRules(): Promise<{ rules: CatRule[] }> {
  return handle(await fetch("/api/books/rules"));
}

export function ledgerCsvUrl(period: string): string {
  return `/api/books/${encodeURIComponent(period)}/ledger.csv`;
}

// ---- Operations feed ----

export async function getOperations(limit = 25): Promise<{ events: TrailEvent[] }> {
  return handle(await fetch(`/api/operations?limit=${limit}`));
}
