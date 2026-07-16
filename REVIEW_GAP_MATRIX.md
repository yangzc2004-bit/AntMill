# Reviewer Gap Matrix

This matrix records the evidence needed to move the manuscript from a bounded
synthetic phenomenon report to a stronger, still conditional mechanism study.
It distinguishes implemented protocol changes from evidence that is pending
fresh outcomes.

| Review gap | Frozen response | Evidence artifact | Status |
|---|---|---|---|
| Consolidation vs sharing is conflated | Re-run an explicitly named private-consolidated arm: identical reviewer operations within separate agent pools | `prereg_phase_epsilon.md`, `epsilon_private_consolidated` | Running |
| Pool-size compression may explain the effect | Report the fixed cap-14 control, then run a separate append candidate-pool yoke matched exactly by seed and round to the Epsilon consolidated trajectory | `epsilon_shared_append_cap14`, `prereg_phase_zeta.md`, `zeta_shared_append_exact_yoke` | Cap-14 running; exact yoke frozen and queued |
| Retrieval diversity is not tested | Compare standard GA retrieval with fixed MMR reranking | `epsilon_shared_consolidated_mmr` | Running |
| Protocol choices are narrow | Sweep k, pool cap, reviewer-operation budget, merge threshold, and recency | `epsilon_sensitivity` | Frozen; queued after controls |
| Seed heterogeneity is obscured | Use seed-clustered paired bootstrap and export compact per-seed paired effects | `sec/maze_stats.py`, `sec/epsilon_evidence.py` | Implemented and self-tested |
| Loop/stagnation are implicit | State the exact detector and route-level stagnation formula in Methods | `paper_draft/antmill_memory_aaai27_en.tex` | Implemented and compiled |
| Real web-agent relevance is uncertain | Use a complete bid-aware six-family MiniWoB++ smoke under an immutable browser runtime to authorize a 54-condition formal matrix with seed-clustered statistics and exact cross-run environment checks | P3e smoke report, `runs_miniwob_gamma_p3e`, `sec/miniwob_stats.py` | P3e smoke passed all engineering/provenance checks; formal running |
| Governance framing is thin | Contrast the fixed protocol with applicability, routing, and policy-adjudication approaches | Related-work paragraph and bibliography | Implemented and compiled |

No pending outcome may be used to strengthen the paper until the corresponding
frozen run, quality checks, and evidence report are complete.
