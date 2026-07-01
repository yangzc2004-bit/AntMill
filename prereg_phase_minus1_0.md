# Pre-registration: Phase -1 (sanity) & Phase 0 (existence)

> **Status note (legacy track):** this pre-registration belongs to the earlier QA/math SEC route.
> The active research plan has moved to the Phase Alpha MazeEval-style strategy-degradation
> benchmark in `README.md` and `maze_strategy_degradation_blueprint.md`. Do not treat the
> GSM8K/MATH settings below as the current primary benchmark.

Frozen 2026-06-29. Thresholds and pass/fail criteria below are fixed BEFORE running; results are
reported against them without post-hoc adjustment. Any deviation is logged as a documented
amendment with reason.

---

## 0. Faithful base config (shared by all arms unless overridden)

Maps to `sec/config.py` fields; new fields marked (NEW).

| field | value | note |
|---|---|---|
| model / base_url / api_key_env | **<USER-SPECIFIED, left blank>** | filled per run by the user; >=2 model families required by Phase 1+ |
| dataset (primary) | **gsm8k** (use **math** if the model exceeds the band) | numeric answers -> clean verification, no EM noise; reasoning/experience-sensitive; the self-consistency-as-signal practice (Huang 2022) was validated here, so collapse here is maximally meaningful |
| dataset (generalization) | musique / 2wikimultihop (closed-book) | shows collapse is not math-specific |
| use_context | true | |
| max_context_chars | 12000 | |
| max_tokens_solver | 1024 | mimo needs this to reach calibrated A0~0.46 |
| max_tokens_reviewer | 1024 | |
| max_tokens_self_eval | 512 | |
| n_solvers (N) | 4 | 1 for single-agent arms |
| debate_rounds R (NEW) | 3 | 1 for single-agent arms |
| solver_temp | 0.7 | faithful: same temp all rounds, NO late-round cooling |
| retrieval_k (NEW) | 6 | ExpeL-style top-k insight retrieval (NOT whole-library) |
| library_cap | 200 | raised from 60 so cap-saturation does not mask accumulation |
| memory_mode (NEW) | {none, private, shared, frozen} | per arm |
| anchor_rho (NEW) | in [0,1] | per arm; prob. a task-batch uses gold to label success |
| success_rule (NEW) | consensus | faithful self-improvement; gold used only via anchor_rho |
| seed | per seed in {0,1,2} | 3 seeds Phase -1/0 |

Debate protocol (faithful MAD, Du et al. 2023): round 1 each agent answers independently from
`retrieval_k` insights + context; rounds 2..R each agent additionally sees peers' previous-round
answers+rationales and may revise; final answer = majority of round R. No conformity instruction.

Anchoring: each training batch is, with prob `anchor_rho`, labeled by gold exact-match; otherwise
labeled by consensus (majority cluster treated as success). `rho=0` pure self-improvement;
`rho=1` fully supervised.

---

## 1. Phase -1: sanity anchors (run FIRST, gate the rest)

### A0 - MAD gain over single agent (no memory loop)

| arm | N | R | memory_mode | T | batch_M | n_train | heldout | seeds |
|---|---|---|---|---|---|---|---|---|
| A0-single | 1 | 1 | none | 1 | 0 | 0 | 200 | 0,1,2 |
| A0-mad | 4 | 3 | none | 1 | 0 | 0 | 200 | 0,1,2 |

**PASS criterion (pre-registered):** mean(A0-mad) - mean(A0-single) >= **+0.03** accuracy, and the
paired bootstrap 95% CI (10k resamples over held-out questions, aggregated across seeds) excludes 0.
*If fail:* the MAD instantiation is not reproducing the published gain -> fix before any collapse
run. Do not proceed.

### A1 - Experiential-memory gain (short horizon, gold-anchored = "good" memory)

| arm | N | R | memory_mode | anchor_rho | T | batch_M | n_train | heldout | seeds |
|---|---|---|---|---|---|---|---|---|---|
| A1-mem | 4 | 3 | shared | 1.0 | 5 | 15 | 75 | 150 | 0,1,2 |
| A1-nomem | 4 | 3 | none | - | 5 | 15 | 75 | 150 | 0,1,2 |

Eval at t=0 and t=4 (final). **PASS criterion:** mean(A1-mem final) - mean(A1-nomem final) >=
**+0.02**, paired bootstrap 95% CI excludes 0. *If fail:* memory is not a faithful "helpful"
component on this dataset -> fix retrieval/extraction or switch to a more experience-sensitive
benchmark (MATH, or the agentic ExpeL settings ALFWorld/WebShop). Do NOT lower the threshold; a
weak gain here means there is no validated "good thing" to break.

---

## 2. Phase 0: existence proof of SEC

Common: N=4, R=3, T=20, batch_M=15, n_train=300, heldout=100, seeds {0,1,2}, eval every round.

| arm | memory_mode | anchor_rho | role |
|---|---|---|---|
| 0-collapse | shared | 0.0 | pure-consensus shared memory (predicted to collapse) |
| 0-nomem | none | - | baseline (no memory) |
| 0-anchor | shared | 1.0 | antidote (gold-anchored shared memory) |

---

## 3. Pre-registered metrics

- **A_t**: held-out accuracy vs gold (EM, normalized). Evaluation isolated from training signal.
- **C_t**: mean over held-out of the majority-cluster fraction among the N agents' final answers.
- **D_t (diversity, headline)**: mean over held-out of normalized answer entropy
  `H = -sum p_i log p_i / log N`, where p_i = cluster-size fractions of the N agents' final
  answers. Range [0,1] (0 = full agreement, 1 = maximal diversity).
  Secondary D: mean pairwise trajectory-embedding distance; memory effective rank (`eff_rank`).
- **G_t = C_t - A_t** (hallucinated-consensus gap).

---

## 4. Pre-registered collapse definition (joint)

A run is labeled **collapsed at t\*** iff ALL hold:

1. **Accuracy drop (within-run):** exists t* with A_{t*} <= running_max(A_{0..t*}) - **delta**,
   delta = **0.10**, sustained for **k_persist = 5** consecutive rounds.
2. **High consensus:** mean C_t over the sustained window >= **c_high = 0.75**.
3. **Diversity collapse:** mean D_t over the sustained window <= **0.5 * D_0** (diversity at least
   halved from round 0) AND below the matched 0-nomem baseline's D over the same rounds.
4. **Below no-memory baseline:** mean A_final(arm) < mean A_final(0-nomem) - **0.05**, with paired
   bootstrap 95% CI across seeds excluding 0.

**Existence proof PASSES** iff `0-collapse` satisfies (1)-(4) AND neither `0-nomem` nor `0-anchor`
satisfies (1)-(3). If 0-collapse does not collapse at faithful settings, report as a negative/
conditional result and move the mechanism dials (Phase 4) up - do NOT silently tune knobs to force it.

---

## 5. Pre-registered early-warning-signal (EWS) test

On the pre-t* window of each collapsing run, compute rolling variance and lag-1 autocorrelation of
D_t and of G_t (existing `sec/metrics.py::ews`). EWS is **confirmed** iff the Kendall rank
correlation tau of each indicator vs round index is **> 0 with p < 0.05**, AND the same indicators
in 0-nomem / 0-anchor show no significant rising trend (tau not significant). Window = rounds
0..t*-1 (require t* >= 6 for a testable window).

---

## 6. Statistical protocol

- Seeds: 3 (Phase -1/0), 5 (Phase 1+ headline arms).
- Per-round curves: mean +/- 95% CI across seeds.
- Accuracy-gain / below-baseline tests: paired bootstrap over held-out questions within seed
  (10k resamples), then aggregate across seeds; report CI.
- All thresholds (delta, c_high, D_low factor 0.5, +0.03/+0.02 gains, -0.05 below-baseline,
  Kendall p<0.05) are frozen as of this document's date.

---

## 7. Budget notes

A0 ~ 200 x N x R x seeds calls; A1/Phase-0 dominated by per-round eval (heldout x N x R) over T
rounds. Run order: A0 -> A1 (gate) -> Phase 0. Reuse `sec/llm.py` disk cache across arms sharing
prompts. If Phase-0 token budget is tight, reduce heldout to 80 before reducing T (need T>=~12 for
a testable EWS window).
