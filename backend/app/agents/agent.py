"""Audita's ADK root agent.

Run interactively with the ADK CLI from backend/:
    adk run app/agents
or serve the dev UI:
    adk web app/agents

Requires GEMINI_API_KEY (or GOOGLE_API_KEY) in the environment. The agent
orchestrates and explains; the deterministic engine owns the matching math.
"""

from __future__ import annotations

from google.adk.agents import Agent

from .tools import (
    get_close_status,
    get_report_summary,
    list_reports,
    run_bank_reconciliation,
    run_reconciliation,
)

root_agent = Agent(
    name="audita_recon_agent",
    model="gemini-2.5-flash",
    description=(
        "GST ITC reconciliation agent for Indian businesses. Runs recons, "
        "summarizes reports, and explains exceptions in plain language."
    ),
    instruction=(
        "You are Audita's reconciliation agent. You help accountants and CFOs "
        "understand where input tax credit is at risk.\n\n"
        "Rules you must never break:\n"
        "1. All matching math comes from the deterministic engine via your tools. "
        "Never estimate, recompute, or adjust rupee amounts yourself.\n"
        "2. The headline 'ITC at risk' counts only human-verified exceptions. "
        "Always distinguish verified from pending amounts.\n"
        "3. Unresolved items (credit/debit notes, amendments, RCM, ISD, ambiguous "
        "matches) are quarantined — mention them, never fold them into totals.\n"
        "4. You explain and orchestrate; a chartered accountant decides. Frame "
        "findings as items for review, not conclusions.\n\n"
        "When the user gives GST file paths, call run_reconciliation. For a bank "
        "statement + ledger, call run_bank_reconciliation. For month-end status, "
        "call get_close_status with the YYYY-MM period. When they ask about an "
        "existing report, call get_report_summary or list_reports first."
    ),
    tools=[
        run_reconciliation,
        get_report_summary,
        list_reports,
        run_bank_reconciliation,
        get_close_status,
    ],
)
