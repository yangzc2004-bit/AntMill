# Maze Strategy-Degradation Blueprint

Working title: **Shared-Experience Strategy Degradation in Multi-Agent LLM Systems**

Status: research-design blueprint / experimental protocol draft. This document is not yet a
pre-registration; once the open decisions in Section 9 are frozen, the corresponding thresholds and
run grid should be copied into a pre-registration document.

---

## 1. Core Thesis

We study how locally feasible strategies in multi-agent shared-experience systems can be amplified
by consensus-driven experience writing, retrieval, and iterative reuse, causing "experience
learning" to degrade into globally inefficient, path-homogeneous, and silent-loop behavior.

This is not an EDV-style claim that wrong experiences contaminate memory. The sharper claim is that
each individual strategy can be legal, reasonable, and locally useful, while the shared memory
system still amplifies and recombines those strategies into globally worse behavior.

The ant-mill analogy is therefore structural: ants do not follow a false proposition; they locally
follow a plausible trail signal until the group forms a destructive global loop.

---

## 2. Research Questions

### RQ1. Is experiential learning useful in this environment?

Run single-agent ExpeL calibration first. The goal is to show that experience writing and retrieval
are measurable and can improve or at least meaningfully alter maze-solving behavior under a stable
single-agent setup.

Primary comparison:

- `single no-memory`
- `single ExpeL reviewer-write`
- `single ExpeL oracle/success-write`
- `single ExpeL self-eval-write`

### RQ2. Is multi-agent execution itself pathological?

Run no-memory multi-agent baselines. The goal is to show that multiple agents are not inherently
unstable before shared memory is introduced.

Primary comparison:

- `single no-memory`
- `MAD no-memory`

### RQ3. Does shared experience create a positive-feedback channel for strategy degradation?

Core comparison:

- `private memory` vs `shared memory`
- `oracle-write` vs `consensus/reviewer-write`
- `frozen memory` vs active retrieval
- `reviewer-write` vs direct-vote-write

Evidence for the mechanism should appear as:

- route homogeneity increases;
- path length, steps, token cost, or tool-call cost increase;
- loop, revisit, or repeated-state behavior increases;
- retrieval concentrates on a few experiences;
- success may remain high, decline late, or remain unchanged while efficiency collapses.

### RQ4. Does the mechanism bridge to realistic tool-use tasks?

Maze is a mechanism microscope, not the whole paper. After the mechanism is established, validate
analogous signals on tool/web tasks where shortest paths are unavailable but step count, tool calls,
tokens, repeated states, stagnation, and time-to-success can be measured.

Candidate directions:

- browser mini-tasks;
- MiniWoB-style tasks;
- tau-bench-like tool workflows;
- lightweight file/API tasks.

Avoid making QA/math the first bridge because they can collapse into answer memorization and do not
expose state/action loops as cleanly.

---

## 3. Scope And Non-Claims

This project is about **strategy degradation**, not merely task failure.

We do not need success rate to collapse for the mechanism to matter. In the maze setting, the most
interesting outcome may be:

> Agents still solve the maze, but shared experience makes them solve it more slowly, with more
> repeated states, less route diversity, and increasing reliance on a small set of retrieved
> strategy rules.

Maze should be described as a controlled, visual mechanism benchmark. It is not a final proof of
real-world deployment risk by itself.

---

## 4. Benchmark Design

### 4.1 Maze Family

Use a generated maze family rather than a single fixed maze.

Splits:

- `fixed_demo`: 2-3 fixed mazes for debugging and replay demos only.
- `train`: fresh sampled mazes for experience writing.
- `heldout`: fixed unseen mazes for repeated evaluation curves.

Recommended current settings:

- `9x9`: debug/smoke only.
- `15x15 trap, min_shortest >= 30`: low-cost pilot.
- `25x25 trap, min_shortest >= 50`: formal candidate, but expensive if every step calls an LLM.

### 4.2 Observation

Use local observation plus memory/history, not full-map planning.

Agent-visible information:

- current position;
- goal position;
- local open directions;
- distance to wall in four directions;
- recent path/history;
- visited/revisit information exposed through state memory;
- retrieved experience.

Hidden from solver agents:

- full maze map;
- shortest path;
- global optimal route;
- heldout labels beyond the ordinary environment feedback.

The runner may compute shortest path for evaluation only.

### 4.3 Execution Semantics

Each solver agent walks an independent copy of the same maze. A move into a wall does not pass
through the wall; it records an invalid move and leaves the agent in place. `submit` only succeeds
at the goal.

---

## 5. Agent Architecture

### 5.1 Three Roles Of Control

The architecture must not accidentally turn the experiment into "we wrote a DFS solver".

Keep three modes conceptually separate:

- `prompt_only`: weak baseline. LLM sees local observations and decides actions. Useful for showing
  that prompt-only agents can legally loop.
- `oracle/controller DFS`: environment upper bound or sanity check. It proves the maze is solvable
  and estimates search cost. It should not be the main subject of experience-learning claims.
- `state-aware agent`: main experimental subject. The system externalizes working memory
  (visited, tried directions, frontier, backtrack candidates), but strategy selection should remain
  influenced by the agent and retrieved experience.

### 5.2 Controller Boundary

The controller may:

- record observed state;
- prevent impossible/invalid execution semantics;
- expose candidate actions and search-state summaries;
- warn about repeated states or exhausted branches.

The controller should not, in the main experiment:

- reveal hidden map structure;
- reveal shortest path;
- fully decide every strategic choice if the claim is about experience-guided strategy;
- inject coordinate-specific route solutions.

If a stronger controller is used for cost control, label that condition separately as a controller
baseline.

---

## 6. Experience Design

### 6.1 Experience Style

Use ExpeL/MAEL-like natural-language strategy memories with quality metadata and provenance.

Allowed:

> If a recovery action returns to the same fork without new information, switch to an untried
> direction rather than repeating the same correction.

Disallowed:

> In maze `heldout_trap_200008`, go left at `(16,21)`.

The reviewer must not write:

- maze IDs;
- exact coordinates;
- full paths;
- fixed action sequences;
- answer-like route caches.

### 6.2 Experience Writers

Conditions:

- `reviewer-write`: ExpeL-like reviewer summarizes trajectory logs.
- `oracle/success-write`: reviewer receives success/quality labels from the runner, not hidden
  routes.
- `self-eval-write`: agent/reviewer estimates whether a trajectory was good from visible logs.
- `direct-vote-write`: agents vote or directly contribute strategy rules.

Reviewer visibility should mimic realistic MAS systems: logs, success, steps, invalid moves,
revisits, token/tool cost, and loop indicators. The reviewer should not see the hidden shortest
path as an input to the experience text, though the researcher can use shortest path for metrics.

---

## 7. Metrics

### 7.1 Feasibility

- `success_rate`: fraction of episodes that reach the goal and submit.

### 7.2 Efficiency

- `actual_steps`: all moves/inspects/submits, including backtracking.
- `shortest_path_length`: researcher-only BFS shortest path length.
- `cost_ratio = actual_steps / shortest_path_length`.
- `excess_steps = actual_steps - shortest_path_length`.
- `invalid_move_rate`.
- optional: token cost, tool-call cost, wall-clock time.

### 7.3 Loop And Stagnation

Single-agent loop:

- position cycle of length 2-8 repeated at least twice, with no improvement in best distance to
  goal; or
- any cell visited at least 10 times.

Stagnation:

- consecutive `k` steps without improving best distance-to-goal or without discovering a new cell.

MAS ant-mill signal:

- at least half of agents in the same episode show loop/stagnation; and
- route overlap is meaningfully higher than no-memory or private-memory baseline.

### 7.4 Strategy Distribution

- `route_diversity`: distance between agents' routes or visited-cell sets.
- `state_visitation_entropy`: entropy over visited states across agents/runs.
- `action_ngram_diversity`: diversity of short action patterns.
- `retrieval_concentration`: whether many agents increasingly retrieve the same few experiences.
- `memory_effective_rank`: diversity of the active memory pool.

---

## 8. Collapse Definition

The headline endpoint should be **efficiency collapse**, not only success collapse.

Proposed definition:

An arm exhibits strategy-degradation / efficiency collapse if, relative to its no-memory or private
memory control:

1. success does not significantly improve, or remains high while efficiency worsens;
2. `cost_ratio` or `excess_steps` increases persistently after memory accumulation;
3. `route_diversity` decreases or route overlap increases;
4. `loop_rate`, `revisit_max`, or stagnation increases;
5. `retrieval_concentration` increases, indicating positive feedback through a small set of
   memories.

This lets the paper claim:

> Shared experience did not simply make agents fail; it made successful behavior increasingly
> inefficient, homogeneous, and loop-prone.

---

## 9. Local Feasible Strategies

This is the most important design choice to freeze.

Candidate locally feasible strategy families:

### A. Obstacle-avoidance heuristics

Example: if blocked, turn right or backtrack. Locally reasonable, but repeated application can cause
large detours.

### B. Exploration heuristics

Example: prioritize unvisited neighbors. Locally reasonable, but over-amplified experience can
cause excessive exploration even near the goal.

### C. Safety heuristics

Example: avoid regions marked as risky or high-revisit. Locally reasonable, but may avoid necessary
temporary backtracking.

### D. Correction heuristics

Example: after a bad move, step back and try an alternative. Locally reasonable, but multiple
correction rules can compose into oscillation.

Preferred current focus: **D. correction heuristics degrading into oscillation**, because it most
directly matches the ant-mill mechanism: legal local correction signals can create global loops
when reinforced and recombined.

---

## 10. Experimental Order

### Stage 0. Debug And Calibration

- 9x9 or 15x15 smoke.
- Verify movement, wall handling, submit semantics, replay, atlas, metrics, and memory audit.

### Stage 1. Single-Agent ExpeL Calibration

Goal: show experience learning is measurable before multi-agent sharing is introduced.

Conditions:

- `single no-memory`
- `single ExpeL reviewer-write`
- `single ExpeL oracle/success-write`
- `single ExpeL self-eval-write`

Recommended pilot:

- `15x15 trap, min_shortest >= 30`
- seed `0`
- `T=5`
- train batch `5`
- heldout `20`

Recommended formal candidate:

- `25x25 trap, min_shortest >= 50`
- use cost-controlled action mode or sparse LLM intervention before scaling.

### Stage 2. MAS No-Memory Calibration

Goal: show multi-agent execution is not itself pathological.

Conditions:

- `single no-memory`
- `MAD no-memory`

### Stage 3. Core MAS Memory Matrix

Conditions:

- `MAD + private memory + reviewer-write`
- `MAD + shared memory + reviewer-write`
- `MAD + shared memory + oracle/success-write`
- `MAD + frozen shared memory`
- `MAD + shared memory + direct-vote-write`

Goal: identify whether shared memory, active retrieval, reviewer/consensus writing, or direct vote
drives degradation.

### Stage 4. Bridge Task

Use a lightweight tool/web task where success, steps, repeated state/action, tool calls, and token
cost are observable.

---

## 11. Artifacts

Each condition should emit:

- `result.json`: config, curves, final metrics, token stats.
- `memory_audit.json`: every experience, provenance, support, retrieval count, affected episodes.
- `replays/*.html`: playable route replay.
- `route_atlas/*.png`: heldout route overlays.
- `curves.png`: success, cost ratio, loop/stagnation, route diversity, memory size, retrieval
  concentration.

---

## 12. Open Decisions To Freeze

1. Which local feasible strategy family is the headline mechanism?
   - Current recommendation: correction heuristics -> oscillation.

2. What is the exact efficiency-collapse threshold?
   - Current recommendation: persistent excess-step/cost-ratio increase plus route-diversity drop
     and retrieval-concentration rise.

3. How much control may the state-aware controller exert?
   - Current recommendation: expose state/candidates in the main experiment; reserve fully enforced
     DFS for sanity/cost-control baselines.

4. What maze difficulty is formal?
   - Current recommendation: 15x15 for pilot; 25x25 trap with `min_shortest >= 50` for formal only
     after reducing per-step LLM cost.

5. What is the first bridge task?
   - Current recommendation: browser/tool mini-task rather than QA/math.
