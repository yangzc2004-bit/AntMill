# AntMill: Shared-Experience Strategy Degradation in Multi-Agent LLM Systems

> An "AI ant mill": locally reasonable strategies can be written into shared
> experiential memory, retrieved by many agents, and amplified through iterative reuse until the
> system becomes globally inefficient, route-homogeneous, or trapped in silent loops.

This repository currently focuses on a MazeEval-style mechanism benchmark for studying
**strategy degradation** in shared-experience multi-agent systems (MAS). The claim is not simply
that erroneous memories pollute future reasoning. Instead, the central hypothesis is sharper:
experiences can be legal, useful, and textually correct in isolation, while the shared memory
mechanism still creates a positive-feedback channel that degrades global behavior.

The ant-mill analogy is structural. Ants do not follow an obviously false proposition; they follow
a locally plausible trail signal until the group forms a destructive global loop. We use mazes as a
controlled microscope for this mechanism because legality, success, shortest-path cost, repeated
states, route diversity, and replayable trajectories can all be measured precisely.

## Current Status

Research work in progress. The active track is **Phase Alpha**, a visual maze pilot with:

- local observations rather than full-map planning;
- generic ExpeL-style experience extraction, not maze-specific answer caching;
- single-agent ExpeL calibration;
- MAS controls for private, shared, frozen, reviewer-written, direct, and oracle-written memory;
- replayable HTML trajectories, route atlas images, memory audits, and summary curves.

The earlier QA/math preregistration files are retained as a legacy exploration track. They are
useful context, but the benchmark plan has changed: the next bridge after mazes should be
tool-use or web-task environments where steps, tool calls, repeated actions, stagnation, token cost,
and time-to-success can replace maze shortest-path cost. QA/math is not the current first bridge
because it is too easy for "experience" to become answer caching.

## Research Question

We study whether multi-agent shared-experience systems can turn locally feasible strategies into
global degradation through consensus-driven writing, retrieval, and reuse.

Evidence for the mechanism can include:

- success remains high but path cost rises;
- route diversity collapses across agents;
- loop, revisit, or stagnation rates increase;
- retrieval concentrates on a few memories;
- memory provenance shows that textually correct rules came from inefficient trajectories.

## Phase Alpha Benchmark

Phase Alpha implements a generated maze family rather than a single fixed maze. Agents receive
local observations, current and goal positions, open directions, distance-to-wall feedback, recent
history, visited/tried directions, and retrieved experience. Solvers do not see the hidden maze
graph, full route, or shortest path. The environment enforces movement semantics: attempted
wall-crossing is blocked and logged, and success requires submitting at the goal cell.

Current pilot settings:

- `maze_family=trap`
- `maze_width=15`, `maze_height=15`
- `maze_min_shortest=30`
- `max_steps=180`
- `maze_agent_mode=state_guided` for the main LLM-per-step pilot
- `stateful_dfs` / `oracle_dfs` only as sanity or upper-bound controllers

Splits:

- `fixed_demo`: fixed mazes for debugging and replay demonstrations;
- `train`: sampled mazes used for experience writing;
- `heldout`: fixed unseen mazes used for comparable evaluation curves.

## Experience Extraction

The memory writer follows the common ExpeL / Reflexion pattern: after an episode, trajectories,
outcomes, and quality signals are distilled into reusable natural-language `do` / `avoid`
experiences. For MAS experiments, the organization is MAEL-like: multiple agents can write to
private pools or a shared global pool. The maze implementation is only a task adapter that formats
trajectory logs and quality fields for the generic extractor in `sec/expel.py`.

The writer is explicitly forbidden from storing route answers. Memories must not include maze IDs,
coordinates, full paths, or fixed action scripts. The sanitizer rejects over-specific insights so
that the experiment tests strategy reuse, not memorized maze solutions.

## Code Layout

| module | role |
|---|---|
| `sec/config.py` | shared run configuration, including maze and memory knobs |
| `sec/llm.py` | async OpenAI-compatible client with disk cache, retries, throttle |
| `sec/memory.py` | shared / private / frozen insight pools and top-k retrieval |
| `sec/expel.py` | generic ExpeL-style experience distillation |
| `sec/maze_env.py` | generated maze environment, solver-visible observations, shortest-path evaluator |
| `sec/maze_alpha.py` | Phase Alpha experiment loop, metrics, replays, route atlas, memory audit |
| `sec/run_maze_alpha.py` | CLI entrypoint for maze experiments |
| `sec/scan_maze_difficulty.py` | offline maze difficulty scan |
| `sec/maze_mechanism_stats.py` | retrieval-concentration and mechanism statistics |
| `sec/maze_mechanism_audit.py` | memory provenance and case-study helper |
| `sec/summarize_maze_alpha.py` | aggregate summaries and figures |
| `sec/selftest_maze.py` | offline maze pipeline self-test |
| `sec/fusion.py` / `sec/run_phases.py` | legacy QA/math SEC track retained for comparison |

## Setup

```bash
pip install -r requirements.txt
export YOUR_KEY_ENV=sk-...        # any OpenAI-compatible endpoint
```

On Windows PowerShell:

```powershell
$env:YOUR_KEY_ENV = "sk-..."
```

Offline sanity checks, no API needed:

```bash
python -m sec.selftest_maze
python -m sec.selftest_v2
```

## Recommended Phase Alpha Runs

Tiny smoke:

```bash
python -m sec.run_maze_alpha \
  --phase smoke \
  --model <id> \
  --base-url <url> \
  --api-key-env <ENV> \
  --T 3 \
  --train-batch 5 \
  --heldout-size 10 \
  --maze-width 15 \
  --maze-height 15 \
  --maze-family trap \
  --maze-agent-mode state_guided \
  --maze-min-shortest 30 \
  --max-steps 180
```

Single-agent ExpeL pilot:

```bash
python -m sec.run_maze_alpha \
  --phase single_expel_pilot \
  --model <id> \
  --base-url <url> \
  --api-key-env <ENV> \
  --seeds 0 \
  --T 3 \
  --train-size 9 \
  --train-batch 3 \
  --heldout-size 10 \
  --maze-width 15 \
  --maze-height 15 \
  --maze-family trap \
  --maze-agent-mode state_guided \
  --maze-min-shortest 30 \
  --max-steps 180 \
  --solver-temp 0.7 \
  --max-tokens-solver 256 \
  --concurrency 1
```

Core MAS memory matrix:

```bash
python -m sec.run_maze_alpha \
  --phase core \
  --model <id> \
  --base-url <url> \
  --api-key-env <ENV> \
  --seeds 0,1,2 \
  --T 3 \
  --train-batch 5 \
  --heldout-size 12 \
  --maze-width 15 \
  --maze-height 15 \
  --maze-family trap \
  --maze-agent-mode state_guided \
  --maze-min-shortest 30 \
  --max-steps 180
```

Artifacts are written under `runs_maze_alpha*/` and are git-ignored by default. Each run can
produce `result.json`, `memory_audit.json`, `curves.png`, `route_atlas/*.png`,
`replays/index.html`, and summary JSON/Markdown.

## Drafts And Figures

- `maze_strategy_degradation_blueprint.md`: current research blueprint.
- `paper_draft/maze_experiment_section.tex`: English LaTeX experiment-section draft.
- `paper_draft/maze_experiment_section_zh.tex`: Chinese LaTeX draft for discussion.
- `paper_draft/figures/*.png`: selected pilot figures for the draft.

Compiled PDFs and rendered page images are intentionally ignored; regenerate them locally from the
LaTeX sources.

## Legacy QA/Math Track

The older SEC code path remains available for comparison:

```bash
python -m sec.run_phases --phase A0 --dataset gsm8k --model <id> --base-url <url> --api-key-env <ENV>
python -m sec.run_phases --phase A1 --dataset gsm8k --model <id> --base-url <url> --api-key-env <ENV>
python -m sec.run_phases --phase P0 --dataset gsm8k --model <id> --base-url <url> --api-key-env <ENV>
```

These files should be treated as historical design context until the new Phase Alpha protocol is
formally frozen:

- `experiment_architecture.md`
- `prereg_phase_minus1_0.md`
- `death_spiral_analogy.md`
