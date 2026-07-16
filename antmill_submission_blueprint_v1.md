# AntMill Submission Blueprint v1

**Status:** Authoritative research and writing blueprint  
**Frozen on:** 2026-07-12  
**Scope:** All new experiments, analyses, figures, and manuscript claims for the AAAI
submission.

This document supersedes the narrative and forward-looking experimental choices in
`maze_strategy_degradation_blueprint.md` and `death_spiral_analogy.md`. Those files remain
historical working notes; they are not sources of submission claims.

## 0. Change Control

This blueprint is deliberately restrictive. A new result is admissible only when it implements a
stage defined below and has a preregistration/execution appendix frozen before formal outcomes are
read.

- Do not retrospectively alter an endpoint, benchmark subset, model roster, topology, or gate after
  inspecting the affected formal outcomes.
- Record any necessary deviation in a numbered amendment, with the reason, the affected stage, and
  a statement of which claims become unavailable.
- Engineering smoke tests are not outcome data. They may establish that an interface is usable, but
  never support or reject a scientific claim.
- The current MiniWoB++ P3 artifacts are **not evaluable** because the action interface was
  semantically invalid. They must not appear as a negative transfer result.
- Never use the phrases "proves the mechanism," "phase transition," "necessary and sufficient,"
  "model-universal," or "real-world deployment risk" for this paper.

## 1. The Paper We Are Actually Writing

### 1.1 Canonical one-sentence claim

In a controlled multi-agent shared-experience system, LLM reviewer consolidation can turn
locally plausible trajectory lessons into a smaller and repeatedly reused active strategy supply,
coinciding with more costly and loop-prone behavior; the size and transfer of this effect must be
measured rather than assumed.

### 1.2 Claim boundaries

The paper is **not** about poisoned memory, false facts, generic multi-agent failure, animal
collective behavior, or a leaderboard comparison among models.

The paper is about one concrete feedback composition:

```text
trajectory logs
  -> shared experience pool
  -> LLM reviewer consolidation
  -> retrieval into later agent contexts
  -> later trajectory logs
```

Every arrow is auditable. The central empirical question is whether this composition can induce
silent behavioral degradation even when individual actions are legal and the written lessons are
locally plausible.

### 1.3 Allowed conclusions

| Evidence level | Permitted conclusion |
|---|---|
| V3 five-arm maze matrix | The tested protocol exhibits a controlled, model-specific degradation phenomenon in a maze microscope. |
| V3 intervention/audit results | Active-supply compression is a robust correlate; the completed interventions bound, but do not identify, causal mechanism. |
| Three-model maze triangle | The phenomenon is observed, not observed, or not evaluable on each named model under a matched protocol. |
| Workflow benchmark | The same behavioral signature transfers, does not transfer, or remains unresolved for the specified role graph and task family. |
| Two workflow families | The paper may call the result cross-workflow only when both families pass their preregistered transfer gates. |

### 1.4 Forbidden conclusion upgrades

- A maze result is not a result for all MAS architectures.
- A compression audit is not proof that compression alone caused degradation.
- A positive result on one additional model is not cross-model universality.
- A browser or software-engineering result on one model is not a general model ranking.
- A failure to reproduce is "not detected under this protocol," unless an engineering validity
  failure makes the condition "not evaluable."

## 2. Narrative Spine: Circular Mill to Workflow

### 2.1 The opening metaphor

Use the army-ant circular mill as a **brief ecological metaphor**, not as a biological model or a
formal isomorphism. The useful intuition is narrow: individually sensible local trail-following can
become collectively wasteful when the only signal being reinforced is produced by the group itself.
Do not claim that LLM agents "are ants," that the system is an absorbing biological state, or that
the experiments establish a phase transition.

Suggested opening move:

> A circular mill of army ants is unsettling because no ant needs to make an obviously irrational
> move: each follows a locally available trail, while the group repeatedly strengthens the trail it
> created itself. Shared experiential memory gives LLM agents an analogous engineering risk. A
> lesson can be plausible, a retrieval can be relevant, and an action can be legal, yet their
> repeated composition may still make a team slower and more repetitive.

The metaphor should occupy at most one short introductory paragraph. Cite
`schneirla1944circularmill` and `delsuc2003armyants`; do not add an ant image unless its licensing
and purpose are clear. A self-drawn feedback-loop diagram is preferable.

### 2.2 The evidence ladder

The narrative must progress in this order:

1. **Ecological intuition:** self-reinforcing local signals can be globally costly.
2. **V3 maze microscope:** expose the feedback loop under exact route-cost measurement and
   factor-by-factor memory controls.
3. **Cross-model maze triangle:** test whether the same controlled phenomenon survives changes in
   model provider and capability tier.
4. **Role-graph workflow transfer:** test the same memory intervention in a recognizable
   collaborative MAS topology on real work-like tasks.
5. **Bounded conclusion:** identify where the signature appears, where it does not, and what
   remains unresolved.

This ordering is essential. The workflow stage is not an excuse to skip the maze controls; the
maze provides the identification that a large workflow benchmark cannot provide cheaply.

### 2.3 The role of V3

The completed DeepSeek-V3 matrix is the paper's **mechanism anchor**, not its universal proof.
It establishes the condition decomposition:

```text
no memory / frozen write-only / private memory / shared append / shared consolidated
```

It also establishes the audit vocabulary: success, failure-penalized cost, loops/stalls, route
behavior, active-pool size, distinct retrieved experiences, and retrieval concentration.

The manuscript must describe the current V3 result as:

> A preregistered controlled phenomenon under a specified shared-memory protocol.

It must not describe the system as a standard dialogue/debate MAS. The four maze solvers run
independently; their only coupling channel is the memory pool. That isolation is useful for
mechanism identification, but it is not ecological realism.

### 2.4 Why daily knowledge QA is not a main benchmark

Question answering can be a useful diagnostic or negative control, but it is not the main transfer
target for this paper. The hypothesized failure is a cumulative, action-conditioned memory loop:
writing after trajectories, retrieving a strategy, acting, and writing again. Static QA often
reduces that process to answer selection or answer memorization and therefore weakens the claim.

MAEL appropriately includes knowledge/reasoning and generation tasks in its broad evaluation, but
it also uses a graph-structured collaboration network with task-conditioned experience
retrieval (`li2025mael`). Our transfer evaluation should preserve the latter property, not merely
copy the former benchmark list.

## 3. Architecture Decision

### 3.1 Keep the current system for the maze

Keep the current implementation for the maze microscope. Do not replace it with a large framework
such as MetaGPT, AutoGen, CrewAI, or LangGraph merely to borrow a recognizable name. Replacing the
substrate would change the mechanism, obscure the existing audit trail, and spend the budget on
framework integration instead of evidence.

### 3.2 Add one reference topology for workflow transfer

For real workflows, implement a small, explicit **MAEL-inspired role graph**. This is an
architectural reference point, not a reproduction claim.

```text
task specification and observable state
                 |
                 v
             Planner
                 |
                 v
       Executor <----> Verifier
                 |
                 v
          task outcome / trace
                 |
                 v
          Memory curator
                 |
                 v
          role-addressable experience pool
```

- **Planner:** decomposes the task and proposes a state-conditioned plan.
- **Executor:** performs browser or repository actions.
- **Verifier:** checks the plan against observable state, task constraints, and final evidence; it
  may request a re-plan, but it does not silently take over execution.
- **Memory curator:** after an episode, writes or consolidates experience from the fixed trace
  summary. It is not a solver vote and is not allowed access to hidden reward information beyond
  the benchmark's public task outcome.
- **Coordinator:** may route messages and enforce budgets, but must be deterministic and must not
  supply task-specific content.

The topology, role prompts, action schema, tool budget, context limits, trace summary, and
curator prompt are held fixed across all memory arms. The memory protocol is the only causal
intervention.

Call this design **"MAEL-inspired role graph with a shared experiential-memory ablation."**
Never call it a "MAEL reproduction." MAEL uses graph-structured collaboration and individual
experience pools; MetaGPT supplies a separate reference for role-specialized SOP-style workflows
(`li2025mael`, `hong2024metagpt`). AgentVerse and MultiAgentBench motivate evaluating explicit
coordination structures rather than treating independent copies of a solver as a realistic MAS
(`chen2023agentverse`, `zhu2025multiagentbench`).

### 3.3 Workflow memory arms

The workflow transfer matrix begins with three arms:

1. `frozen`: the curator produces the same kind of experience records, but solvers do not read
   them.
2. `shared_append`: role-addressable experiences are appended and retrieved; no curator
   consolidation merges, edits, or votes them away.
3. `shared_consolidated`: the curator applies the same bounded
   `ADD`/`EDIT`/`UPVOTE`/`DOWNVOTE` protocol as the maze condition.

`no_memory` and `private_memory` are already identification controls in the V3 matrix. Do not
pay their workflow cost by default. Add a preregistered workflow `private_memory` diagnostic only
after a valid consolidated-vs-frozen workflow effect is detected; it is then used to distinguish
sharing from a generic effect of role-local experience.

## 4. Experiment Program

### Stage A: Preserve and Report the Existing V3 Evidence

**Purpose:** Mechanism identification in a controlled setting.

- Retain the full V3 five-arm maze matrix as the primary controlled result.
- Retain the negative and non-evaluable intervention decisions. In particular, P1b did not pass
  its diversity-expansion manipulation check, so it is not evidence that equal-dose archive rescue
  is ineffective.
- Treat the Qwen3-32B probe as a bounded probe: its compression observation may be reported, but
  its behavioral effect is unresolved.
- Exclude the invalid MiniWoB++ formal artifacts from all outcome plots, tables, and aggregate
  counts.
- Before final writing, regenerate every V3 table and figure from the frozen manifests and
  analysis scripts, with per-seed signs and paired-route intervals visible.

### Stage B: Three-Model Maze Triangle

**Purpose:** Replicate the controlled phenomenon across current, cross-provider model substrates
without repeating the whole five-arm V3 matrix.

#### B.1 Formal model roster

The intended roster is fixed as:

1. `DeepSeek-V4-Flash`
2. `Grok-4.5`
3. `GPT-5.6-terra`

Before formal outcomes, freeze the exact provider endpoint, model identifier, API version, date,
temperature, thinking/reasoning setting, token limits, retry policy, and price/accounting source
for each model. If a provider does not expose the stated identifier or cannot satisfy the semantic
action smoke, label that model **not evaluable**. Do not silently substitute a different model.

The three models are deliberately not a performance leaderboard. They differ in provider,
capability, latency, and cost; results answer whether the intervention has a matched behavioral
signature, not which model is "best."

#### B.2 Formal maze matrix

For each evaluable model:

| Item | Fixed value |
|---|---|
| Arms | `frozen`, `shared_append`, `shared_consolidated` |
| Rounds | `T=4` |
| Experimental seeds | `0, 1, 2` |
| Solvers | `4` independent solvers |
| Heldout tasks | `12` matched mazes per round and solver |
| Train batch | `4` matched mazes per round and solver |
| Maze family | Existing `15x15` trap family, local observation, exact shortest-path evaluator |
| Retrieval | Same `k`, pool cap, sanitizer, and trace schema as V3 unless a frozen compatibility amendment states otherwise |
| Statistics | Seed-clustered, paired-route bootstrap; report per-seed signs and raw route counts |

The `frozen -> append -> consolidated` triangle is enough for cross-model replication because V3
already provides the broader factor decomposition. Do not rerun `no_memory` or `private_memory`
for every new model unless a prespecified diagnostic trigger fires.

#### B.3 Validity and decision gate

Before the full matrix, each model must pass a smoke test on the exact action schema:

- parser success at least 95%;
- no floor or ceiling task-success saturation;
- exhausted API/error rate at most 1%;
- complete route/memory/latency/token audit files;
- independent replay or cache-salt checks as appropriate.

The primary cross-model endpoints are:

1. **Failure-penalized route cost** relative to `frozen`.
2. **Loop/stall burden** relative to `frozen`.

Success, success-only excess steps, route diversity, active-pool size, distinct injected
experiences, and retrieval concentration are secondary or mechanism-audit endpoints.

A model is called **maze-phenomenon positive** only when `shared_consolidated - frozen` worsens
both primary endpoints with 95% paired bootstrap intervals entirely above zero and both endpoints
have the same harmful direction in at least two of three seeds. Any other valid outcome is
`not_detected_or_underpowered`, not a model-boundary claim.

#### B.4 Stop rule

- **Two or three positive models:** proceed to Stage C with the first two positive models under
  the fixed reporting priority `DeepSeek-V4-Flash`, `Grok-4.5`, `GPT-5.6-terra`.
- **Exactly one positive model:** proceed to Stage C only with that model and label all workflow
  conclusions model-conditioned.
- **No positive model:** stop workflow expansion. The submission remains a V3 controlled study
  with qualified cross-model non-replication; do not search for a friendlier benchmark or retune
  the models.
- **Not evaluable models:** report the implementation reason separately from scientific outcomes.

### Stage C: Main Workflow Transfer

**Purpose:** Test the same memory intervention in a recognizable MAS role graph on realistic,
action-bearing work.

#### C.1 Benchmark 1: Office workflow

Use **WorkArena++ through BrowserGym** as the primary office benchmark. WorkArena++ is designed
around compositional, routine knowledge-work tasks in an enterprise web environment, rather than
single-click toy interactions (`boisvert2024workarenapp`, `chezelles2024browsergym`).

- MiniWoB++ is no longer the headline bridge. It may be used only as an engineering action-schema
  calibration after a bid-aware semantic execution test, never as an outcome-bearing substitute
  for WorkArena++.
- Formal WorkArena++ instances must cover at least four workflow types and include composition,
  retrieval, and state-verification demands. Freeze exact task IDs and the coverage table before
  the first formal arm. Use at least 48 formal task instances, balanced across the frozen
  workflow types.
- Primary endpoints: task success, failure-penalized browser-action cost, repeated
  action-on-equivalent-state, retry/replan count, tool/browser error rate, token cost, and
  wall-clock latency.

#### C.2 Benchmark 2: Software-engineering workflow

Use **SWE-bench Verified** as the independent programming workflow. It evaluates a repository
plus issue-to-patch process with executable validation, making it closer to a multi-role
engineering workflow than code-generation questions (`jimenez2024swebench`).

- Freeze a public, repository-stratified subset before formal outcomes: at least 60 instances
  across at least six repositories, with no repository contributing more than one third of the
  instances.
- Keep the execution environment, test harness, shell/tool permissions, role prompts, and token
  budget fixed across memory arms.
- Primary endpoints: resolved issue/test success, failure-penalized tool/action cost, repeated
  inspect-edit-test cycles without new evidence, verifier rejection/replan count, token cost, and
  wall-clock latency.
- Report results by repository as well as pooled. Do not treat tasks from the same repository as
  independent model seeds.

#### C.3 Workflow design and gate

For each selected workflow model and each benchmark:

| Item | Fixed value |
|---|---|
| Role graph | Planner, Executor, Verifier, Memory curator |
| Memory arms | `frozen`, `shared_append`, `shared_consolidated` |
| Experimental seeds | `0, 1, 2` |
| Rounds | `T=4`, with no final-round writing |
| Pairing | Same task, seed, role graph, tool state, and solver slot across arms |
| Primary contrast | `shared_consolidated - frozen` |
| Secondary contrast | `shared_append - frozen` |

The workflow primary endpoints are failure-penalized cost and repeat/stall burden. A benchmark
passes transfer only when both are worse for `shared_consolidated` than `frozen`, with a 95%
paired, seed-clustered bootstrap interval above zero and the harmful direction in at least two
of three seeds. Success is always reported but is not allowed to conceal a degradation in
failure-penalized burden.

Interpretation:

- Both WorkArena++ and SWE-bench pass for the same model: **cross-workflow transfer under one
  named role graph and model**.
- One benchmark passes: **task-family-specific transfer evidence**.
- Neither passes: **workflow transfer not detected under this topology and protocol**.
- A benchmark fails engineering validation: **not evaluable**; no scientific sign is assigned.

#### C.4 Optional appendix only

MultiAgentBench can be used after the two main workflow benchmarks as an appendix-level topology
coverage check. It is valuable for comparing star, chain, tree, and graph coordination settings,
but its simulated scenarios are not a replacement for the office and repository workflows
(`zhu2025multiagentbench`). It must not block submission.

#### C.5 No main QA benchmark

Do not add MMLU, GSM8K, or a generic daily-QA benchmark to the main experiment matrix. At most,
add one small, clearly labelled appendix diagnostic after Stage C if a reviewer-facing ablation
needs to show that the observed effect is not simply "any retrieval makes any answer worse." It
cannot be used as a main transfer figure or to replace either workflow benchmark.

## 5. Measurement and Reporting Contract

Every formal arm must produce:

- `manifest.json` with model/provider settings, commit hashes, package versions, benchmark IDs,
  prompt hashes, seeds, date, and cost-accounting rule;
- route/task-level results with failure and infrastructure-error labels;
- role messages, action traces, state hashes, retrieved experiences, and curator operations;
- `memory_audit.json` containing active-pool trajectory, distinct injected experiences, effective
  rank, retrieval entropy/top-1 share, archive/merge/deletion counts, and sanitizer rejects;
- token, latency, cache, retry, parser, and tool-error summaries;
- paired-bootstrap report, per-seed sign table, and a deviation log.

The primary presentation unit is the paired task effect with seed-level uncertainty. Do not pool
routes as if hundreds of task traces were hundreds of independent model replications.

Use failure-penalized outcomes as primary. Success-only path/action cost is a conditional
secondary metric and must always appear beside success and failure-penalized cost.

## 6. Manuscript Blueprint

Target the current AAAI anonymous-submission format, but verify the official page and reference
rules immediately before submission. Keep the core paper compact; put prompts, full manifests,
all task IDs, extended per-family results, and replay instructions in the anonymous supplement.

### 6.1 Title direction

Primary working title:

> Locally Plausible, Globally Wasteful: When Consensus Consolidation Degrades Shared Experience in Multi-Agent LLM Systems

Do not use "death spiral," "collapse," "universal," or a specific benchmark/model name in the
title. The result is more credible when its scope is visible from the title.

### 6.2 Section-by-section outline

| Section | Job | Evidence that must appear |
|---|---|---|
| Abstract | State the protocol, controlled finding, transfer scope, and limitation in one pass. | V3 result; three-model/workflow outcome only after completed. |
| 1. Introduction | Use the circular-mill intuition, define the engineering risk, and state why legal successful behavior can still be costly. | Feedback-loop diagram; bounded contributions. |
| 2. Related Work | Separate experiential memory, MAS role graphs, and task benchmarks. | ExpeL, MAEL, MetaGPT/AgentVerse, WorkArena++, SWE-bench. |
| 3. Study Design | Define the system under test, causal contrast, endpoints, and statistical unit before results. | Five-arm V3 matrix and audit contract. |
| 4. V3 Mechanism Microscope | Present the full control matrix, negative findings, and intervention boundary honestly. | Forest/table, trajectory case, compression audit. |
| 5. Cross-Model Maze Triangle | Report all three named models symmetrically, including non-detections and not-evaluable outcomes. | One forest plot with one row per model. |
| 6. Workflow Transfer | Introduce the MAEL-inspired role graph and the two workflow benchmarks. | Topology figure; WorkArena++ and SWE-bench results. |
| 7. Limitations and Discussion | Explain what the study does not establish and how failure modes differ by model/task. | Maze scope, model heterogeneity, topology specificity, non-causal compression audit. |
| 8. Conclusion | Restate the actionable design lesson. | Keep memory consolidation observable and benchmark it as a dynamic system. |

### 6.3 Figure and table plan

1. **Figure 1: Feedback composition.** A self-drawn circular feedback diagram from trace to memory
   to retrieval to later trace. The ant metaphor appears as a small textual cue, not evidence.
2. **Figure 2: V3 controlled microscope.** Five-arm forest/trajectory result with a matched route
   case study; show both burden and success.
3. **Figure 3: Cross-model triangle.** Three-model, three-arm forest plot with per-seed signs and
   "not detected"/"not evaluable" labels rather than missing rows.
4. **Figure 4: Workflow topology and transfer.** Role graph on the left; matched WorkArena++ and
   SWE-bench effect panels on the right.
5. **Table 1: Protocol and construct map.** Published component family, our instantiation, and
   deviations. Do not claim implementation-identical reproductions.
6. **Table 2: Benchmark and claim map.** Maze, office, and coding task family; what each can and
   cannot establish.

### 6.4 Related-work references to carry into the paper

| Citation key | Why it belongs |
|---|---|
| `schneirla1944circularmill`, `delsuc2003armyants` | Restrained factual support for the opening ecological metaphor. |
| `zhao2024expel`, `park2023generative`, `shinn2023reflexion` | Experience writing, retrieval, and reflection components. |
| `li2025mael`, `qian2024colearning` | Shared/cross-task experiential learning in multi-agent settings. |
| `hong2024metagpt`, `chen2023agentverse` | Role-specialized and explicit multi-agent collaboration architectures. |
| `zhu2025multiagentbench` | Explicit evaluation of coordination topologies; appendix-only benchmark option. |
| `boisvert2024workarenapp`, `chezelles2024browsergym` | Office workflow and browser-agent evaluation environment. |
| `jimenez2024swebench` | Executable, repository-level software-engineering workflow benchmark. |

## 7. Writing Rules

- Say "can degrade," "is associated with," "we observe," "under this protocol," and "bounded
  evidence."
- State the architecture before making a MAS claim. "Four independent solvers sharing only
  memory" and "MAEL-inspired role graph" are different systems and must never be conflated.
- Put non-results in the main narrative when they constrain the mechanism: no E3 dose-response,
  P1b not evaluable, Qwen behavioral effect unresolved, and invalid MiniWoB P3 excluded.
- Explain the ecological metaphor once, then return to engineering terms: shared pool, curator,
  retrieval, active supply, loop/stall, cost, and validation.
- Do not use the word "consensus" to imply solver voting. In the maze experiment it means an LLM
  reviewer update over batched traces; in the workflow experiment the curator is likewise not a
  vote.
- Do not use QA generalization to claim real MAS utility. Use action-bearing workflow evidence.

## 8. Immediate Execution Checklist

1. Create `Phase Delta` preregistration for the three-model maze triangle before any smoke or
   formal run. Freeze endpoint-specific settings and semantic action smoke criteria.
2. Implement or validate model adapters only through engineering smoke tests; retain all smoke
   manifests.
3. Run the complete Stage B triangle and publish every model row.
4. Create a separate `Phase Epsilon` preregistration for the MAEL-inspired role graph, exact
   WorkArena++/SWE-bench subsets, role prompts, and semantic tool checks.
5. Implement the role graph and pass benchmark-specific semantic calibration before formal arms.
6. Run Stage C only under the Stage B stop rule.
7. Rewrite the manuscript in the section order above. Do not add transfer claims until the
   corresponding Stage C gate has completed.

## 9. Decision Summary

The project does **not** reduce to "V3 found something, so run fashionable models on fashionable
benchmarks." It asks a tighter question in a sequence that can survive review:

```text
controlled V3 identification
  -> matched three-model replication attempt
  -> one explicit MAS role graph
  -> two real workflow families
  -> bounded design conclusion
```

That is the submission's spine. Everything outside it is either engineering support, an appendix,
or out of scope.
