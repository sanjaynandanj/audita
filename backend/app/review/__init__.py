"""Review Agent — monthly financial review (PRD-2 Phase 3).

Deterministic computation from the categorized ledger (P&L snapshot,
month-over-month variance, anomaly flags); LLM narration is env-gated and
cites only computed numbers. Flags carry the same verified/pending gating
and CA sign-off column as every other workpaper.
"""
