# Audita — Security & Data Protection

Status: v1.0 · 2026-07-23 · applies to the single-tenant pilot deployment.
Be honest with prospects: this section says what exists, not what we aspire to.

## 1. Data classification

| Data | Sensitivity | Where |
|---|---|---|
| GSTR-2B, purchase registers, bank statements/ledgers | **High** — client financial data | `data/uploads/`, parsed into reports |
| Recon/BRS reports | High — derived financials + reviewer names | `data/reports/`, `data/bankrecs/` |
| Close workbooks | Medium | `data/close/` |
| Event log | Medium — operational metadata, actor names | `data/events.db` |
| Signing key | **Critical** | `AUDITA_SECRET_KEY` env (prod) / `data/secret_key` (dev fallback) |

## 2. Current controls

- **Transport:** TLS is the deployment platform's job (Cloud Run / reverse proxy). The app
  must never be exposed on plain HTTP beyond localhost.
- **Report access:** capability URLs — `itsdangerous` signed tokens, per-purpose salts
  (`audita-report-link`, `audita-bankrec-link`), default expiry 7 days
  (`AUDITA_LINK_MAX_AGE`). Tampered ⇒ 404, expired ⇒ 410 (tested).
- **Upload hygiene:** extension allowlist (`.json .csv .xlsx .xls`); files stored with
  random temp names; parsed with stdlib/openpyxl (no macro execution, no pickle).
- **Path traversal:** store IDs validated `isalnum()` before touching the filesystem (tested).
- **Injection surface:** SQL uses parameterized queries only; no shell-outs; Jinja
  autoescaping on server-rendered pages; React escapes by default.
- **Audit trail integrity:** `agent_events` rejects UPDATE/DELETE via DB triggers — tamper
  attempts fail at the database, not in app code (tested).
- **Container:** non-root user (uid 1001), slim base image, no build tools in runtime layer.
- **Secrets:** `.env` git-ignored; `.env.example` documents required vars; the only secret the
  app needs is the signing key (+ optional `GEMINI_API_KEY`).
- **LLM boundary:** Gemini receives invoice *images* for field extraction only when the Vision
  path is explicitly enabled; the ADK agent's tools expose summaries, and the agent cannot
  mutate amounts (tools do the math; instructions forbid recomputation).

## 3. Honest gaps (accepted for founder-operated pilot ONLY)

| Gap | Risk | Required before |
|---|---|---|
| **No user authentication** — anyone with the app URL can run recons; anyone with a report link can view AND verify | Impersonated verification; data upload by strangers if URL leaks | Any deployment beyond founder-controlled access (mitigate now: IAP/Access-restricted URL, VPN, or Cloud Run auth) — hard requirement before multi-tenant |
| Verify actions trust the typed reviewer name | Sign-off column is attestation, not identity proof | Real pilots with external CAs → authenticated reviewer identities |
| No rate limiting / upload size caps at app level | DoS via huge files | Public exposure (set platform limits meanwhile) |
| No encryption at rest at app level | Disk access = data access | Rely on platform disk encryption (GCP default) now; app-level envelope encryption when multi-tenant |
| Uploads retained indefinitely | Data minimization violation over time | Implement scheduled purge (uploads > 30 days) before onboarding non-founder-network clients |

## 4. DPDP Act posture (India)

Pilot commitments (must be kept, they're in the product's marketing):
1. **Consent:** written consent from each pilot business before processing; purpose limited to
   producing their report.
2. **Deletion on request:** delete `data/uploads/*`, the client's reports, and derived JSON on
   request. (Event-log rows are metadata, retain for integrity; they contain no financial
   figures from client docs beyond aggregate refs.)
3. **Residency:** deploy in **GCP asia-south1 (Mumbai)**; Gemini calls use Google's API —
   disclose this in the consent note when Vision is enabled.
4. **Breach duty:** DPDP requires notifying the Data Protection Board and affected principals;
   maintain the incident checklist below.
5. Full DPDP design (retention schedules, consent management, DPO designation as applicable)
   is scheduled with the CA-review layer phase — before scaling past founder-network pilots.

## 5. Threat model (abridged)

| Threat | Vector | Control |
|---|---|---|
| Report link leaks | forwarded email/chat | expiry + regeneration; future: viewer auth |
| Malicious upload | crafted xlsx/json/csv | allowlist, safe parsers, size limits at proxy, container isolation |
| Trail tampering | insider/compromise edits history | DB-level append-only triggers; future: hash-chain + periodic external anchor |
| Signing key theft | env/dev file leak | prod key only via secret manager; rotate ⇒ all links invalidate (feature, not bug) |
| Prompt injection via invoice images | adversarial text in scans | Vision output is structured fields feeding deterministic code; no tool-calling from vision output |
| Wrong ₹ headline | engine bug / LLM drift | LLM never computes; ambiguous ⇒ unresolved; human verification gate; 62 automated tests |

## 6. Incident checklist

1. Revoke: rotate `AUDITA_SECRET_KEY` (kills all live links), redeploy.
2. Freeze: snapshot the `/data` volume (evidence, incl. append-only log).
3. Assess scope from `agent_events` (what ran, when, by whom).
4. Notify affected pilot businesses; DPDP Board notification if personal data involved.
5. Post-mortem in `docs/incidents/`.
