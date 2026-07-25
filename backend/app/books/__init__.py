"""Bookkeeping Agent — transaction categorization (PRD-2 Phase 2).

Deterministic rules engine first; env-gated LLM suggestions second; nothing
enters an account total until it was coded by a user-authored rule or
confirmed by a named human.
"""
