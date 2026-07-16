# Phase Gamma preregistration: mechanism rescue, compression, cross-model and task-generalization

Frozen before any new P1 formal data. Gamma reuses Phase Beta's paired route-level statistics, cache-salt discipline, sanitizer discipline, and same-maze/agent pairing. All deviations must be appended to this file before looking at the affected outcome data.

## 0. Motivation and time budget

Phase Beta E2 established endogenous degradation for `shared_consolidated_expel` relative to `frozen` at 5 seeds: success-only excess steps CI entirely above 0, looped CI above 0, and 5/5 same-sign seeds. E4 further showed that by `t=3`, consolidated vs frozen already worsens success, looped, and failure-penalized excess steps. Gamma therefore uses short, gated additions rather than another broad matrix.

Base compute budget: P1 16-21h, P2 15-40h, P3 8-24h, total 39-85h. Because archive rescue injects more text, reserve +15% wall-clock/token contingency. P4 tau2-bench is stretch only and does not block submission.

## 1. P0 instrumentation and drift probe

Each formal arm-seed must output `result.json`, `memory_audit.json`, `manifest/config`, latency/tokens summary, route rows, paired bootstrap CI, per-seed sign table, and deviation log. LLM audit fields include total/network/cache calls, trace tokens, p50/p95 network latency, retry count, content-filter count, parse-failure count, and elapsed wall time.

Before reusing cached E2 controls, run `gamma_drift_probe` with cache disabled:

```powershell
python -m sec.run_maze_alpha --phase gamma_drift_probe --model DeepSeek-V3 --base-url https://api.modelarts-maas.com/v2 --api-key-env MODELARTS_MAAS_KEY --out-dir runs_maze_gamma_drift --cache-dir cache_maze_gamma_drift --seeds 0 --maze-width 15 --maze-height 15 --maze-family trap --maze-agent-mode state_guided --maze-min-shortest 30 --max-steps 120 --concurrency 8 --retrieval-k 6 --library-cap 80 --max-tokens-solver 256 --max-tokens-reviewer 512
python -m sec.gamma_stats drift-probe --baseline-result runs_maze_beta_e2/n4_gt_false_seed0_e2_frozen_reviewer/result.json --probe-result runs_maze_gamma_drift/n4_gt_false_seed0_gamma_drift_frozen_t0/result.json --out-dir runs_maze_gamma_drift_stats
```

Pass criterion: probe means for success, looped, cost ratio, and failure-penalized steps all fall inside the E2 seed0/t0 bootstrap 95% CI. If any metric fails, cached E2 controls cannot be used for P1 formal comparisons; rerun contemporaneous `gamma_p1_controls` for seeds 0-2 and compare P1 intervention arms only against those controls.

## 2. P1 DeepSeek maze mechanism interventions

All P1 arms inherit E2 formal settings unless explicitly stated: `DeepSeek-V3`, ModelArts MaaS base URL, trap maze, `15x15`, `maze_min_shortest=30`, `T=6`, `heldout=12`, `train_batch=4`, `n_solvers=4`, `retrieval_k=6`, `library_cap=80`, `max_steps=120`, `state_guided`, `retrieval_scoring=ga`, `ga_lambda=0`, `skip_final_train=true`. Start with seeds 0-2; add seeds 3-4 only when specified by the gate.

Rescue arm: `gamma_p1_shared_consolidated_archive_rescue`. The consolidated write protocol is unchanged: the reviewer still issues ADD/EDIT/UPVOTE/DOWNVOTE over the visible active pool. The only intervention is read-side archive access for solvers. Do not describe the active pool as unchanged: online trajectories may diverge after t=0. The audit must report rescue active-pool trajectory next to E2 consolidated active-pool trajectory.

Archive sources are fixed: DOWNVOTE target text, EDIT pre-edit text, and similarity-merge discarded text. Archive retrieval is read-only and cannot change reviewer operations or active-pool membership.

Rescue primary contrast: `consolidated+archive` vs standard `shared_consolidated_expel` at final round. Report success, success_excess_steps, looped, mas_antmill if available, and failure-penalized steps/cost. Gate passes only if success non-inferiority CI lower bound > -0.05; sxs or looped significantly improves; the other endpoint has non-worse point estimate; failure-penalized cost has non-worse point estimate; and same-sign seeds are >=2/3. If the direction is favorable but CI contains 0, add seeds 3-4. At 5 seeds require pooled CI excluding 0 and >=4/5 same-sign seeds, otherwise mark rescue inconclusive.

Compression arm: run only after the rescue gate is evaluated. `gamma_p1_budgeted_append_yoked` keeps append writing unchanged but restricts solver reads to a persistent whitelist yoked to E2 consolidated active distinct counts. Schedule is cumulative-max: seed0 `[0,6,7,8,8,8]`, seed1 `[0,8,8,8,8,8]`, seed2 `[0,8,8,8,8,8]`, seed3 `[0,6,6,7,8,9]`, seed4 `[0,7,8,8,8,9]`. Once admitted, an item remains retrievable through a snapshot even if the live append pool later changes. Budget increases admit never-admitted candidates using fixed seed/t RNG.

Compression primary contrast: `budgeted_append` vs standard `shared_append_ga`. Frozen is phenomenon context only. A compression-positive result means low active supply can induce harm; it is not by itself a clean proof of necessity/sufficiency.

Interpretation branches are fixed: both rescue and compression positive = convergent intervention evidence; rescue positive but compression negative = scale alone is insufficient and identity/content selection likely matters; compression positive but rescue negative = low active supply can harm but archive rescue did not isolate the mechanism; both negative = no new mechanism claim beyond E2/E4.

## 3. P2 cross-model replication

Primary target is `qwen3-32b`. Before formal data, smoke-test parsing and task success with thinking disabled. If MaaS honors `extra_body.enable_thinking=false`, use it; otherwise use the preregistered `/no_think` prompt marker; if stable only with `max_tokens_solver=512`, use 512 for all Qwen arms. Smoke pass: success in [25%, 85%], action parse >=95%, and manageable API/runtime error rates. If Qwen fails this smoke, switch to `glm-5.1` and label Qwen not evaluable, not a model boundary.

Formal P2 settings: `T=4`, `heldout=12`, seeds 0-2, arms frozen / append / consolidated. T=4 is justified by E4 t=3 degradation. Primary comparison mirrors E2: `consolidated vs frozen` only. Append/private are secondary. Gate passes when success_excess_steps is worse with CI excluding 0 and 3/3 seed signs, plus looped or mas_antmill worsens with CI excluding 0. Negative results are reported as not detected or underpowered, not as model-boundary evidence.

Only if P2 phenomenon is positive and time remains, run same-model rescue seeds 0-2 with the P1 rescue gate.

## 4. P3 MiniWoB++ task-generalization

Use BrowserGym MiniWoB with MiniWoB++ pinned to `7fd85d71a4b60325c6585396ec4f48377d049838`. Record BrowserGym package versions and `MINIWOB_URL`. Primary tasks: `click-button`, `choose-list`, `enter-text`, `click-checkboxes`, `login-user`, `use-autocomplete-nodelay`. Replacement tasks: `click-menu`, `choose-date-nodelay`, `form-sequence`.

Architecture: same task instance/seed, four independent browser envs, one per solver. Do not use one-env majority action. Reviewer input is fixed to a deterministic summary: goal, success, steps, invalid/error count, repeated-state count, first 3 actions, last 8 `(action, normalized_state_hash, visible_text_delta, error)` records, and at most 1200 chars of final normalized AXTree. Full per-step AXTree is forbidden in reviewer prompts.

State hash normalization hides volatile bids, focus/hover flags, dynamic ids, and coordinates; keeps visible text and form values; collapses whitespace; and includes URL/path plus last_action_error. Smoke replay must show >=95% hash agreement under identical reset/step sequences.

Formal P3 settings: `T=4`, `heldout=12 per family`, seeds 0-2, arms frozen / append / consolidated, `max_steps=15`. Primary comparison is `consolidated vs frozen`; append is secondary. Metrics: success, failure-penalized steps/cost, repeated-action-on-same-state, and nontermination. Because max_steps truncation can move mass between loop and nontermination, judge them jointly as loop/stall burden. Run MiniWoB rescue only if P3 phenomenon is positive.

## 5. P4 tau2-bench stretch

P4 uses the tau2-bench retail subset only if P1-P3 are complete or after submission. It is non-blocking and not part of the main mechanism claim. Keep naming under `tau2_*` to avoid confusion with `sec/tau_env.py`. Minimal design: `T=3`, seeds 0-2, frozen vs consolidated, direction only.

## 6. Claim language

Gamma must use "convergent intervention evidence" rather than "necessity" or "sufficiency". Limitations must state that rescue also restores content previously downvoted or edited away, and compression uses a random persistent subset rather than an LLM-selected subset; supply scale and content selection are therefore not perfectly separated.

## 7. 2026-07-11 P3 execution appendix

Before generating P3 smoke or formal outcomes, the implementation details, technical smoke gate, replacement-task order, six-family formal scope, stratified paired-bootstrap gate, and no-rescue stopping rule are frozen in `prereg_phase_gamma_p3_execution.md`. This appendix follows the P1b decision log: P3 is phenomenon replication only, with no MiniWoB rescue or compression.
