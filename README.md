# SEC — Shared-Experience Collapse in Multi-Agent LLM Systems

> An "AI ant mill": when several LLM agents learn from a **shared** experiential memory and use
> their own **consensus** (rather than external ground truth) as the signal for which experiences
> to keep, the shared memory can become a self-reinforcing feedback channel. This project studies
> when such a system collapses into an absorbing state of **high consensus, low accuracy, and
> collapsed diversity** — agents that are confidently, collectively wrong.

The framing is a deliberate isomorphism to the army-ant *circular mill* / death spiral and to
*model collapse* (recursion on self-generated signal without an external anchor). See
[`death_spiral_analogy.md`](death_spiral_analogy.md).

## Status

Research work in progress. The experimental design is **pre-registered** before running; thresholds
and pass/fail criteria are frozen in [`prereg_phase_minus1_0.md`](prereg_phase_minus1_0.md) and must
not be tuned post hoc.

## Design

- [`experiment_architecture.md`](experiment_architecture.md) — the strawman-proof architecture:
  reproduce a validated gain first, then induce collapse with a single realistic perturbation
  (remove ground-truth anchoring / long horizon), with controls that isolate the shared substrate.
- [`prereg_phase_minus1_0.md`](prereg_phase_minus1_0.md) — frozen configs and decision thresholds
  for Phase -1 (sanity anchors) and Phase 0 (collapse existence proof).
- [`death_spiral_analogy.md`](death_spiral_analogy.md) — paper-ready framing, the formal
  control-parameter / phase-transition correspondence, and falsifiable predictions P1–P6.

## System under test

- **Multi-Agent Debate** substrate (R rounds; agents see peers and may revise).
- **ExpeL-style cross-task experiential memory** with top-k retrieval and voting-based fusion.
- Success signal when unsupervised = **self-consistency / consensus** (the practice being
  stress-tested); ground-truth anchoring is mixed in with probability `anchor_rho`.

Two control parameters: experience **assimilation** (memory mode: none / private / shared / frozen)
and external **anchoring** `anchor_rho` ∈ [0, 1] (the "severed trail" knob).

## Code layout (`sec/`)

| module | role |
|---|---|
| `config.py` | run configuration (debate rounds, retrieval-k, memory mode, anchor_rho, ...) |
| `data.py` | benchmark loaders (GSM8K, MATH, HotpotQA, MuSiQue, 2WikiMultiHop), disjoint train/held-out splits |
| `llm.py` | async OpenAI-compatible client with disk cache, retries, throttle |
| `debate.py` | R-round multi-agent debate |
| `memory.py` | shared / private / frozen insight pools, top-k retrieval |
| `fusion.py` | insight distillation + voting fusion (`reviewer_synthesize_v2`) |
| `metrics.py` | accuracy / consensus / diversity (`D_t`), EWS, joint-collapse test |
| `loop_v2.py` | the SEC experiment loop (debate + memory + anchoring) |
| `phases.py` / `run_phases.py` | pre-registered Phase -1 / 0 configs and runner |
| `analysis_stats.py` | cross-arm judgments: paired-bootstrap gains, existence proof, EWS test |
| `selftest.py` / `selftest_v2.py` | offline logic + mock-LLM pipeline tests |

The original single-pass pipeline (`loop.py`, `run.py`, `calibration.py`) is retained and still
importable; the v2 modules above are additive.

## Setup

```bash
pip install -r requirements.txt
export YOUR_KEY_ENV=sk-...        # any OpenAI-compatible endpoint
```

Offline sanity (no API needed):

```bash
python -m sec.selftest
python -m sec.selftest_v2
```

## Running the pre-registered phases

Model / endpoint are supplied at run time (left blank by default):

The primary benchmark is `--dataset gsm8k` (default; numeric answers give clean verification);
switch to `--dataset math` if the model is too strong for the [0.25, 0.60] calibration band, or to
`musique` / `2wikimultihop` for the generalization domain.

```bash
# Phase -1: reproduce the validated gains (gate)
python -m sec.run_phases --phase A0 --dataset gsm8k --model <id> --base-url <url> --api-key-env <ENV> --seeds 0,1,2
python -m sec.run_phases --phase A1 --dataset gsm8k --model <id> --base-url <url> --api-key-env <ENV> --seeds 0,1,2

# Phase 0: collapse existence proof
python -m sec.run_phases --phase P0 --dataset gsm8k --model <id> --base-url <url> --api-key-env <ENV> --seeds 0,1,2

# Cross-arm judgments (offline, reads runs_v2/*/result.json)
python -m sec.analysis_stats --phase A0 --out-dir runs_v2
python -m sec.analysis_stats --phase A1 --out-dir runs_v2
python -m sec.analysis_stats --phase P0 --out-dir runs_v2
```

Budget knobs: `--heldout-size`, `--T`, `--concurrency`, `--rpm`. Run artifacts (`runs_*/`,
`cache_*/`) are git-ignored.
