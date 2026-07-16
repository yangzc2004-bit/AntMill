# Phase Zeta Decision Log

## 2026-07-15: Outcome-blind read-supply audit clarification

Before any Zeta run started and without inspecting any behavioral outcome, the
exact-yoke evidence check was strengthened to verify the already-recorded
`active_candidate_count` on every retrieval. Each of the original 30
seed-by-round manipulation rows still checks the frozen target against
`budgeted_append_budget` and `budgeted_append_selected`; it now also requires
all retrieval records in that round to expose exactly the same target-sized
candidate pool.

This is an engineering consistency check for the preregistered read-supply
manipulation. It does not change the arm, schedule, endpoint, contrast,
bootstrap, interpretation rule, or stopping rule.
