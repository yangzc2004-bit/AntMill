# AAAI Paper Blueprint: Experience-Mediated Lock-In in Parallel LLM Agents

Status: evidence-closed after the audited 12-layer Kimi MaaS confirmation,
two independent retrospective trajectory audits, and the prospectively frozen
fixed-three-reference control. The bilingual manuscript follows this version.

## One-Sentence Thesis

In a layered parallel Mixture-of-Agents coding system, blinded shared
experience can repeatedly pull independent workers into a common
implementation attractor without sustained score collapse; cumulative history
growth is not necessary in the tested setting, and admission gates trade
false-completion blocking against rejection of strong solutions.

## Narrative Spine

1. Start from the army-ant mill only as a motivating systems metaphor: locally
   useful signals can become globally constraining when repeatedly reinforced.
   The metaphor is not evidence and must not appear in the title or claims.
2. Replace the old V3 maze as the empirical center with a real layered MoA
   workflow: three independent MiniSWE workers solve the same executable coding
   task in private workspaces, synchronize at a barrier, and receive blinded
   shared experience.
3. Ask a falsifiable question: does repeated experience transfer produce a
   sustained degradation curve, or does it produce a different failure mode?
4. Report the negative result first. Across DeepSeek-V4-Flash, GLM-5, and
   Kimi-K2.6 raw accumulation, catastrophic 0-score outputs are sparse,
   model-dependent, and not reproducibly persistent.
5. Show the positive result supported by the strongest audit. In the fresh
   Kimi MaaS 12-layer run, cumulative self-report transfer makes every worker
   share the same 33/37 failure signature from layer 3 and the same exact
   snapshot from layer 5, despite no terminal collapse.
6. Establish recurrence without pretending that layers are independent
   samples. Two separately executed cumulative trajectories reproduce
   consecutive exact-snapshot lock-in under retrospective audit, while their
   matched no-transfer controls do not.
7. Test the main alternative explanation prospectively. A fixed-reference
   control gives every worker only the three most recent summaries and still
   reaches exact lock-in at layers 2--3. This rules out cumulative
   reference-count growth as a necessary condition, but not transferred
   context or token load as contributors.
8. Use recursive manager synthesis as a mechanism stress test. On cfgpipe, a
   centralized playbook reaches a textual fixed point and can make independent
   workers converge on a globally inferior behavior. On log_query, xjq, and
   sequential tasks, the same family of mechanisms is neutral or beneficial.
9. Close with governance rather than a universal pathology. Local admission
   rejects zero-command false completions and prevents direct propagation, but
   the frozen three-command rule also rejects high-quality 34/37 outputs.
   Retrospective threshold replay exposes the precision-recall trade-off.

## Research Questions

- RQ1: Does weakly verified cumulative experience reproducibly cause sustained
  performance degradation with depth?
- RQ2: Does shared experience reduce implementation and behavioral diversity
  even when aggregate performance remains stable?
- RQ3: Does centralized recursive synthesis create a privileged behavioral
  fixed point?
- RQ4: Can a local completion-and-smoke gate block false completion without
  rejecting useful experience?
- RQ5: Which observations survive changes in model, task, and transfer policy?

## Evidence Hierarchy

### Tier A: Confirmatory Main Evidence

- Kimi-K2.6 MaaS, cfgpipe checkpoint 1, 3 workers, 12 layers, 12 actions.
- Frozen arms: no transfer, cumulative self-report, cumulative local admission.
- 108/108 external evaluations pass target, model-query, blinding, and access
  integrity gates.
- Allowed conclusions:
  - the preregistered recurrent catastrophic-tail replication is falsified;
  - cumulative self-report reaches a stable behavioral lock-in;
  - the local gate mechanically rejects two zero-command 0/37 outputs;
  - the same gate rejects five 34/37 outputs with two successful commands.

### Tier A2: Replication and Prospective Alternative-Explanation Control

- Independent Kimi Coding cumulative r2:
  exact three-worker snapshot lock-in from layers 3--10.
- Independent Kimi MaaS cumulative r1:
  exact lock-in from layers 4--9 and layer 11, with intermittent no-snapshot
  failures demonstrating re-entry rather than permanent irreversibility.
- Prospective Kimi MaaS bounded-recent control:
  exactly three references per worker and layer; exact lock-in at layers 2--3;
  all 18 outputs score 34/37 and Core 4/4.
- Matched no-transfer controls:
  no two consecutive exact-lock-in layers and three terminal snapshots.
- Allowed conclusions:
  - exact implementation lock-in recurs across independent trajectories;
  - cumulative reference-count growth is not necessary in the tested setting;
  - transferred context and unmatched token load remain plausible contributors;
  - the attractor is conditional and not irreversible.

### Tier B: Mechanism Stress Probes

- Kimi recursive Core-gated manager on cfgpipe:
  exact manager fixed point; exact worker snapshot convergence; 32/37 terminal
  treatment versus 34/37 no transfer.
- DeepSeek recursive self-report manager on cfgpipe:
  manager near-fixed point and shared five-test failure signature, but the
  bootstrap contains a 0/37 source and there is no matched control in that run.
- Allowed conclusion:
  centralized synthesis can compress heterogeneous trajectories into a stable
  shared behavior; it does not establish amplification of globally correct
  experience.

### Tier C: Cross-Model and Cross-Task Boundaries

- Raw cumulative self-report:
  DeepSeek has two isolated 0/37 events; GLM-5 has none; Kimi has one in an
  initial run and none in two independent replications, including depth 12.
- Recursive manager:
  log_query and xjq improve at the terminal layer; cfgpipe sequential strongly
  favors treatment against a noisy control; execution_server is descriptive
  only because the no-transfer control is action-boundary censored.
- Allowed conclusion:
  direction and severity are model-, task-, and protocol-dependent.

## Primary Metrics

- External all-test score and Core score.
- Exact catastrophic event rate (0/all tests).
- Exact implementation diversity:
  number of unique snapshot hashes and dominant-snapshot share.
- Behavioral diversity:
  number of unique failed-test signatures, dominant-signature share, and mean
  pairwise Jaccard similarity of failed-test sets.
- Coordination load:
  received experience characters, reference count, and input-token ratio to
  no transfer.
- Admission trade-off:
  catastrophic rejection recall and high-quality retention under replayed
  successful-command thresholds.

## Main Figure Plan

### Figure 1: System and Causal Separation

- Archetype: schematic-led composite.
- Hero panel: layered parallel MoA with private workers, barrier, blinded
  transfer, optional manager, and hidden external evaluator.
- Subpanels: three admission policies and the distinction between performance
  collapse, implementation lock-in, and behavioral lock-in.

### Figure 2: Main Result, Replications, and Context-Growth Control

- Archetype: quantitative grid with a score-curve hero.
- Panel a: all-test score by layer for all three arms, showing no sustained
  treatment collapse and stochastic tails in no transfer/local admission.
- Panel b: dominant snapshot share and failure-signature similarity, showing
  self-report lock-in.
- Panel c: unique snapshot count across the main run, two independent
  cumulative audits, the bounded control, no-transfer controls, and the
  verified `log_query` boundary.
- Panel d: received-reference count with exact-lock-in layers marked, showing
  that the bounded arm meets its frozen criterion at exactly three references.

### Figure 3: Admission and Boundary Conditions

- Archetype: asymmetric mixed-modality figure.
- Hero panel: command-threshold replay, catastrophic rejection versus
  high-quality retention.
- Subpanel: cross-model raw-append 0-score rates.
- Subpanel: recursive-manager terminal treatment-control direction by task,
  with invalid or stress-probe settings visibly separated.

## Manuscript Structure

1. Introduction
   - army-ant metaphor as motivation only;
   - why experience sharing is distinct from ordinary debate;
   - negative result and revised contribution stated up front.
2. Related Work
   - layered MoA and multi-agent collaboration;
   - experiential learning and shared memory;
   - conformity, debate failure, and diversity collapse;
   - iterative coding benchmarks and SlopCodeBench.
3. Audited Parallel-Agent Testbed
   - topology, private workspaces, barrier, transfer policies;
   - blinded external evaluation and frozen validity gates;
   - metrics and claim-decision rules.
4. Results
   - RQ1: sustained degradation is not reproduced;
   - RQ2: experience transfer produces behavioral fixed points;
   - RQ3: recursive synthesis can privilege and stabilize shared errors;
   - RQ4: admission gates have a measurable false-rejection cost;
   - RQ5: model/task boundaries.
5. Discussion
   - stability-diversity trade-off;
   - verification-governance implications;
   - why more layers are not an automatic causal test.
6. Limitations
   - one main task and three workers;
   - provider/model stochasticity;
   - retrospective threshold replay;
   - partial task coverage and action-budget censoring;
   - no universal causal claim.
7. Conclusion

## Claim Firewall

Allowed:

- "can induce behavioral lock-in";
- "rapidly reduced diversity in the audited cfgpipe setting";
- "exact lock-in recurred across three cumulative trajectories";
- "cumulative reference-count growth was not necessary in the tested setting";
- "the implementation attractor was conditional and not irreversible";
- "catastrophic tails were intermittent and model-dependent";
- "the frozen replication did not support a sustained death spiral";
- "the admission proxy blocked observed zero-command false completions";
- "the admission threshold incurred false-rejection cost."

Forbidden:

- "shared experience generally degrades MAS";
- "we demonstrate an ant-mill death spiral";
- "complexity causes catastrophic collapse";
- "the local gate prevents future failures";
- "two commands is the optimal universal threshold";
- "recursive synthesis is harmful across tasks";
- pooling exploratory, invalid, and confirmatory runs as exchangeable repeats.

## Evidence-Closure Checklist

- Completed deterministic source-data export from audited JSON artifacts.
- Completed implementation and failed-test diversity audit for every main-run
  layer and two independent cumulative trajectories.
- Completed retrospective command-threshold replay over thresholds 0--6.
- Completed cross-model raw-append and cross-task manager boundary tables.
- Completed a prospectively frozen fixed-three-reference mechanism control.
- Completed a strict verified-transfer second-task boundary on `log_query`.
- No further model calls are required for this first-draft claim boundary.
