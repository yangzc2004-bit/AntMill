# SEC Experiment Architecture (strawman-proof, attributable)

> **Status note (superseded by Phase Alpha):** this document records the earlier QA/math SEC
> architecture. The active project direction now uses the MazeEval-style strategy-degradation
> benchmark described in `README.md` and `maze_strategy_degradation_blueprint.md`. Keep this file
> as historical design context, not as the current benchmark plan.

Consolidated, defensible architecture for demonstrating Shared-Experience Collapse (SEC) in a
mainstream multi-agent LLM setup. Design backbone: **reproduce the validated gain first, then
induce collapse with a single realistic perturbation** — so the failure is attributable to the
architecture's own mechanism, not to pathological knobs we added.

---

## 0. Design principles (read first)

1. **Faithful before broken.** The System Under Test must be a recognizable instantiation of a
   published, validated method, run at its published settings. We must first replicate its
   *gain*; only then do we perturb.
2. **Realistic perturbation vs mechanism dial.** Two disjoint categories of factors:
   - *Realistic perturbations* (the CLAIM): things real deployments actually do — remove
     ground-truth feedback, run long horizons, share memory. Collapse attributed to these is
     meaningful.
   - *Mechanism dials* (ANALYSIS only): temperature, dissent pruning, sharing fraction,
     retrieval-k. Used to trace the mechanism / phase transition, never as the headline claim.
3. **Attributability.** The headline result must hold at *faithful* dial settings under a
   *realistic* perturbation. If collapse needs pathological dials, report it as conditional.

---

## 1. System Under Test (faithful instantiation)

- **Multi-agent substrate: Multi-Agent Debate** (Du et al., 2023), at published settings:
  N agents, R debate rounds, each agent sees peers' previous answers + rationales and may revise,
  final = majority of last round. Use standard debate prompts; do not inject conformity pressure.
- **Cross-task experiential memory: ExpeL-faithful** (Zhao et al., 2024), NOT homemade
  whole-library injection:
  - insight extraction by contrasting success/failure trajectories,
  - operations ADD / EDIT / UPVOTE / DOWNVOTE,
  - **retrieval of top-k similar insights at inference** (not the whole library).
  Retrieval-k and library cap set to ExpeL's published values.
- **Success signal when no ground truth: self-consistency / consensus** (Huang et al., 2022) —
  the published, advocated no-label training signal we stress-test.

This SUT is recognizably "MAD + ExpeL + self-improvement", three validated, mainstream pieces.

---

## 2. Factors

### 2a. Realistic perturbations (headline claims)

| Factor | Symbol | Range | Real-world meaning |
|---|---|---|---|
| Ground-truth anchoring | rho | {0, 0.25, 0.5, 1.0} | fraction of task-batches given gold feedback; rho=0 = pure self-improvement, rho=1 = supervised. The "severed trail". |
| Deployment horizon | T | {short=5, long=20-40} | how many task-batches the memory recurses over (longitudinal accumulation). |
| Memory provenance | - | {none, private, shared} | no memory / per-agent private / global shared. Tests whether the *shared* substrate is the collapse channel. |

### 2b. Mechanism dials (analysis only, faithful = default)

sharing fraction s in [0,1]; dissent pruning mu; temperature schedule; retrieval-k. Default =
published/faithful values. Swept ONLY in the mechanism section to expose the phase transition.

---

## 3. Sanity anchors (Stage -1, run FIRST)

- **A0 - MAD gain.** Reproduce MAD > single-agent on a standard benchmark at standard settings
  (match published direction/magnitude). Establishes "our MAD is the real MAD".
- **A1 - Experiential gain.** Reproduce ExpeL / self-improvement short-horizon (T=short) gain over
  no-memory. Establishes "our memory is the real, helpful memory".
- Gate: if A0/A1 do not show the published gains, fix the instantiation before any collapse run.

---

## 4. Controls (rule out confounds)

- **Compute-matched single-agent self-consistency**: 1 agent, k=N samples, majority. Isolates
  interaction/sharing from mere multi-sample voting.
- **Memory-off**: SUT with no memory. Baseline for the joint collapse definition.
- **Frozen-memory**: accumulate insights but do NOT inject them back. Isolates the *feedback loop*
  (injection) from memory accumulation per se — collapse should need injection.
- **Prompt-length / token-budget match** where arms are compared.

---

## 5. Generalization

- **>= 2 model families** (e.g., a Qwen/DeepSeek-class and a Llama/GPT-class). Headline claim must
  hold on both, or be reported as model-conditional.
- **>= 2-3 datasets**: HotpotQA (multi-hop) + 2WikiMultiHop / TriviaQA + a reasoning set (GSM8K)
  or knowledge set (MMLU).
- **>= 5 seeds** per condition for headline arms; report mean +/- 95% CI (bootstrap).

---

## 6. Metrics & collapse definition

- A_t: held-out accuracy vs gold (evaluation isolated from training signal).
- C_t: consensus (majority fraction); D_t: diversity (answer entropy + trajectory embedding
  dispersion + memory effective rank); G_t = C_t - A_t.
- **Collapse (joint)**: vs memory-off baseline, A drop >= delta AND C >= c_high AND D <= D_low,
  sustained >= k rounds. Thresholds pre-registered.
- **EWS**: rolling variance + lag-1 autocorrelation of D_t / G_t rising before t* (Scheffer 2009).

---

## 7. Headline experimental logic (one sentence)

> At faithful MAD + ExpeL settings whose gains we first reproduce (Stage -1), applying the single
> realistic perturbation of removing ground-truth anchoring (rho -> 0) over a long deployment
> horizon drives the shared-memory system into an absorbing high-consensus / low-accuracy /
> low-diversity state (SEC), preceded by critical-slowing-down early-warning signals, on >= 2
> model families and >= 2 datasets; the collapse is absent under memory-off, frozen-memory,
> private-memory, and compute-matched single-agent controls.

---

## 8. Run plan (phased, budget-aware)

| Phase | Arms | Seeds | Datasets | Models | Tests |
|---|---|---|---|---|---|
| -1 sanity | A0 MAD gain, A1 experiential gain | 3 | HotpotQA | 1 | establish faithful gains |
| 0 existence | shared/rho=0/long vs memory-off vs shared/rho=1 | 3 | HotpotQA | 1 | crossover A v / C ^ / D v exists |
| 1 anchoring dose | rho in {0,.25,.5,1}, shared, long | 5 | HotpotQA | 2 | P3 antidote, headline |
| 2 provenance/controls | none / private / shared / frozen / self-consistency | 5 | HotpotQA | 2 | P6 + confound controls |
| 3 horizon | T short vs long, rho=0 | 5 | HotpotQA | 1 | recursion/longitudinal effect |
| 4 mechanism | s, mu, temp, k sweeps (ANALYSIS) | 3 | HotpotQA | 1 | P1 tipping, P2 EWS, P4 tradeoff |
| 5 generalization | phase-0/1 core points | 3 | 2WikiMultiHop + GSM8K | 2 | non-dataset-specific |
| 6 (stretch) hysteresis | flip rho 0->1 at t* | 3 | HotpotQA | 1 | P5 absorbing state |

Budget: held-out 150-200, cache reuse, T_long capped by token budget; run Phase -1/0 first and
gate before committing the full grid.
