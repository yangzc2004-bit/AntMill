# AntMill

<p align="center">
  <strong>Language / 语言:</strong>
  <a href="#readme-zh"><strong>中文</strong></a>
  |
  <a href="#readme-en"><strong>English</strong></a>
</p>

<a id="readme-zh"></a>

## 中文

[Switch to English](#readme-en)

AntMill 是一个用于研究 **多智能体 LLM 系统中共享经验如何导致静默策略退化** 的实验仓库。当前版本已经从早期 Phase-Alpha 迷宫 pilot 推进到 **Phase-Beta 预注册结果版**：在一个可控的 15 x 15 trap-maze 显微镜环境中，系统比较无记忆、私有记忆、共享 append 记忆、共享共识合并记忆，以及只写不读的 frozen 控制组。

核心问题不是“错误经验污染了推理”。更尖锐的假设是：经验文本可以是合法、局部合理、甚至来自成功轨迹的，但当它被共享写入、共识合并、检索并反复注入给多个 agent 时，系统仍可能形成全局低效路线和循环行为。失败是静默的：agent 仍然走合法路线、到达目标、不撞墙、不错误提交，但越来越绕路。

### 当前结论

Phase-Beta 的 E1-E3 结果已经整理成中英文 LaTeX 草稿：

- `paper_draft/beta_results_en.tex`
- `paper_draft/beta_results_zh.tex`
- `paper_draft/figures/beta/`

当前主结论：

1. **E1 单智能体归因控制**：忠实经验学习在单 agent 条件下没有显著移动主效率端点；经验并非被忽略，但单 agent 结果本身不解释后续多 agent 退化。
2. **E2 多智能体记忆矩阵**：主动注入经验会降低效率并放大循环；其中 `shared_consolidated_expel` 相对 frozen write-only 控制组最稳定地退化。
3. **共享特异性边界**：`shared_consolidated_expel` 没有在主效率端点上全面显著差于 private memory，但在 loop rate 上显著高于 private memory。
4. **E3 读端剂量反应为 null**：提高 Generative-Agents-style importance 权重没有产生清晰剂量反应。
5. **机制焦点转到写端**：共识合并压缩了 active strategy supply；`shared_consolidated` 平均只实际注入约 11.0 条不同经验，而 `shared_append` 约为 25.4 条。

关键 E2 数字，均为同迷宫配对 bootstrap，10,000 resamples，95% CI：

| comparison | endpoint | mean diff | 95% CI | interpretation |
|---|---:|---:|---:|---|
| shared consolidated vs frozen | success-only excess steps | +11.84 | [7.66, 16.02] | significant degradation |
| shared consolidated vs frozen | loop rate | +0.138 | [0.092, 0.188] | significant loop amplification |
| private vs frozen | success-only excess steps | +7.32 | [2.83, 11.90] | active private memory also degrades |
| shared consolidated vs private | success-only excess steps | +0.87 | [-4.29, 6.15] | no broad efficiency separation |
| shared consolidated vs private | loop rate | +0.058 | [0.008, 0.113] | shared-consolidated loop-specific risk |

因此，当前版本最稳妥的论文表述是：

> Active consolidated memory, relative to a write-only frozen control, significantly increases successful-route excess steps and loop signatures. The evidence does not establish a broad shared-vs-private efficiency gap; the shared-specific risk is currently loop amplification and write-side strategy-supply compression.

### 实验设置

Phase-Beta 使用可控迷宫作为机制显微镜：

- maze family: `trap`
- size: `15 x 15`
- shortest path constraint: `>= 30`
- agent mode: `state_guided`
- step cap: `120`
- solvers: no hidden maze graph, no shortest path, local observations only
- memory retrieval: top-k retrieved experience injection
- write protocols: append or ExpeL-style ADD / EDIT / UPVOTE / DOWNVOTE operations
- retrieval scoring: similarity or Generative-Agents-style relevance + importance + recency
- statistics: same-maze paired bootstrap with per-seed direction checks
- sanitizer: rejects maze IDs, coordinates, fixed routes, and researcher-authored fallback text

### Phase-Beta Arms

`python -m sec.run_maze_alpha --phase ...` exposes the current phases:

| phase | role |
|---|---|
| `e1_gate` | single-agent attribution control |
| `core_v2` | E2 five-arm memory matrix |
| `e3_lambda` | read-side importance-weight sweep on the append arm |
| `e4_stress` | exploratory T=10 long-horizon stress test |
| `smoke` | small offline/online pipeline check |
| `single`, `single_expel_pilot`, `core` | earlier Phase-Alpha pilots |

E2 condition names:

| condition | meaning |
|---|---|
| `e2_mas_nomem` | four independent solvers, no memory |
| `e2_frozen_reviewer` | reviewer writes memory, but solvers never read it |
| `e2_private_reviewer` | private per-agent memory with ExpeL-style operations |
| `e2_shared_append_ga` | shared append-only memory with GA-style retrieval |
| `e2_shared_consolidated_expel` | shared memory with ExpeL-style consensus consolidation |

### 代码结构

| path | role |
|---|---|
| `sec/run_maze_alpha.py` | main CLI for maze experiments |
| `sec/maze_alpha.py` | Phase Alpha/Beta maze runner, phase definitions, replay and plot outputs |
| `sec/maze_env.py` | generated maze environment and shortest-path evaluator |
| `sec/solver.py` | solver/controller helpers |
| `sec/memory.py` | private/shared/frozen memory pools and retrieval scoring |
| `sec/expel.py` | experience distillation and sanitizer |
| `sec/expel_ops.py` | ExpeL-style pool operations |
| `sec/maze_stats.py` | paired route-level bootstrap statistics |
| `sec/e2_evidence.py` | E2 five-seed evidence package and beta figures |
| `sec/fig1_mechanism.py` | mechanism/case-study figure generator |
| `sec/maze_mechanism_audit.py` | memory provenance and mechanism audit helpers |
| `paper_draft/` | manuscript sections and figures |
| `prereg_phase_beta.md` | frozen Phase-Beta protocol and deviation log |

### 安装

```bash
pip install -r requirements.txt
```

Configure an OpenAI-compatible endpoint:

```bash
export MODELARTS_MAAS_KEY=sk-...
```

PowerShell:

```powershell
$env:MODELARTS_MAAS_KEY = "sk-..."
```

### 快速检查

Offline checks:

```bash
python -m sec.selftest_maze
python -m sec.selftest_p0
python -m sec.selftest_p1
```

Tiny smoke run:

```bash
python -m sec.run_maze_alpha \
  --phase smoke \
  --model <model> \
  --base-url <openai-compatible-url> \
  --api-key-env <ENV_NAME> \
  --T 3 \
  --train-batch 5 \
  --heldout-size 10 \
  --maze-width 15 \
  --maze-height 15 \
  --maze-family trap \
  --maze-agent-mode state_guided \
  --maze-min-shortest 30 \
  --max-steps 120
```

### 复现 Phase-Beta 主矩阵

E2 five-arm matrix:

```bash
python -m sec.run_maze_alpha \
  --phase core_v2 \
  --model DeepSeek-V3 \
  --base-url https://api.modelarts-maas.com/v2 \
  --api-key-env MODELARTS_MAAS_KEY \
  --seeds 0,1,2,3,4 \
  --T 6 \
  --train-batch 4 \
  --train-size 24 \
  --heldout-size 12 \
  --maze-width 15 \
  --maze-height 15 \
  --maze-family trap \
  --maze-min-shortest 30 \
  --maze-agent-mode state_guided \
  --max-steps 120 \
  --retrieval-k 6 \
  --library-cap 80 \
  --concurrency 8 \
  --skip-final-train \
  --out-dir runs_maze_beta_e2 \
  --cache-dir cache_maze_beta_e2
```

E3 lambda sweep:

```bash
python -m sec.run_maze_alpha \
  --phase e3_lambda \
  --model DeepSeek-V3 \
  --base-url https://api.modelarts-maas.com/v2 \
  --api-key-env MODELARTS_MAAS_KEY \
  --seeds 0,1,2 \
  --T 6 \
  --train-batch 4 \
  --train-size 24 \
  --heldout-size 12 \
  --maze-width 15 \
  --maze-height 15 \
  --maze-family trap \
  --maze-min-shortest 30 \
  --maze-agent-mode state_guided \
  --max-steps 120 \
  --retrieval-k 6 \
  --library-cap 80 \
  --concurrency 8 \
  --skip-final-train \
  --out-dir runs_maze_beta_e3 \
  --cache-dir cache_maze_beta_e3
```

Build the E2 evidence package after producing the run and stats directories:

```bash
python -m sec.e2_evidence \
  --runs-dir runs_maze_beta_e2 \
  --stats-dir runs_maze_beta_e2_stats_5seed \
  --stats-vs-private-dir runs_maze_beta_e2_stats_5seed_vs_private \
  --out-dir runs_maze_beta_e2_evidence
```

Each run writes:

- `result.json`
- `memory_audit.json`
- `curves.png`
- `route_atlas/*.png`
- `replays/index.html`

### Manuscript Artifacts

Current result-section drafts:

- `paper_draft/beta_results_en.tex`
- `paper_draft/beta_results_zh.tex`

Current beta figures:

- `paper_draft/figures/beta/figure1_mechanism.*`
- `paper_draft/figures/beta/figure2_e2_main.*`
- `paper_draft/figures/beta/figure2b_shared_vs_private.*`
- `paper_draft/figures/beta/figure3_write_side_compression.*`

Compiled PDFs and run outputs are treated as local artifacts and are not required for source control.

### Legacy Track

The older QA/math SEC path remains in the repository for historical comparison:

```bash
python -m sec.run_phases --phase A0 --dataset gsm8k --model <model> --base-url <url> --api-key-env <ENV_NAME>
python -m sec.run_phases --phase A1 --dataset gsm8k --model <model> --base-url <url> --api-key-env <ENV_NAME>
python -m sec.run_phases --phase P0 --dataset gsm8k --model <model> --base-url <url> --api-key-env <ENV_NAME>
```

It is not the current main evidence path because QA/math can blur experience learning with answer caching, while the maze environment exposes legality, shortest-path cost, repeats, loops, and route diversity directly.

---

<a id="readme-en"></a>

## English

[切换到中文](#readme-zh)

AntMill studies **silent strategy degradation in multi-agent LLM systems with shared experiential memory**. The repository has moved beyond the earlier Phase-Alpha maze pilot and now contains a **Phase-Beta preregistered results track**. The current benchmark is a controlled 15 x 15 trap-maze microscope that compares no memory, private memory, shared append memory, shared consensus-consolidated memory, and a frozen write-only control.

The central claim is not that false memories poison future reasoning. The sharper hypothesis is that experiences can be legal, locally reasonable, and derived from successful trajectories, while the shared-memory mechanism still creates a positive-feedback channel that degrades global behavior. The failure is silent: agents keep taking legal moves, reach the goal, and avoid false submits, but increasingly waste steps and form loops.

### Current Findings

The Phase-Beta E1-E3 results are written up in bilingual LaTeX drafts:

- `paper_draft/beta_results_en.tex`
- `paper_draft/beta_results_zh.tex`
- `paper_draft/figures/beta/`

Current claims:

1. **E1 single-agent attribution control**: faithful experience learning does not significantly move the primary single-agent efficiency endpoints. Experience is not ignored, but single-agent memory use alone does not explain the multi-agent degradation.
2. **E2 multi-agent memory matrix**: active experience injection degrades efficiency and amplifies loops. The `shared_consolidated_expel` arm is the most reproducible degrading arm relative to the frozen write-only control.
3. **Shared-specific boundary**: `shared_consolidated_expel` is not broadly worse than private memory on the main efficiency endpoint, but it loops significantly more than private memory.
4. **E3 read-side dose response is null**: increasing the Generative-Agents-style importance weight does not produce a clean dose-response curve.
5. **Mechanism shifts to the write side**: consensus consolidation compresses the active strategy supply. `shared_consolidated` injects about 11.0 distinct memories on average, versus about 25.4 for `shared_append`.

Key E2 numbers, all same-maze paired bootstrap estimates with 10,000 resamples and 95% CIs:

| comparison | endpoint | mean diff | 95% CI | interpretation |
|---|---:|---:|---:|---|
| shared consolidated vs frozen | success-only excess steps | +11.84 | [7.66, 16.02] | significant degradation |
| shared consolidated vs frozen | loop rate | +0.138 | [0.092, 0.188] | significant loop amplification |
| private vs frozen | success-only excess steps | +7.32 | [2.83, 11.90] | active private memory also degrades |
| shared consolidated vs private | success-only excess steps | +0.87 | [-4.29, 6.15] | no broad efficiency separation |
| shared consolidated vs private | loop rate | +0.058 | [0.008, 0.113] | shared-consolidated loop-specific risk |

Recommended manuscript wording:

> Active consolidated memory, relative to a write-only frozen control, significantly increases successful-route excess steps and loop signatures. The evidence does not establish a broad shared-vs-private efficiency gap; the shared-specific risk is currently loop amplification and write-side strategy-supply compression.

### Experimental Setup

Phase-Beta uses the maze as a mechanism microscope:

- maze family: `trap`
- size: `15 x 15`
- shortest path constraint: `>= 30`
- agent mode: `state_guided`
- step cap: `120`
- solvers see local observations only, never the hidden graph or shortest path
- memory retrieval: top-k experience injection
- write protocols: append or ExpeL-style ADD / EDIT / UPVOTE / DOWNVOTE operations
- retrieval scoring: similarity or Generative-Agents-style relevance + importance + recency
- statistics: same-maze paired bootstrap with per-seed direction checks
- sanitizer: rejects maze IDs, coordinates, fixed routes, and researcher-authored fallback text

### Phase-Beta Arms

`python -m sec.run_maze_alpha --phase ...` exposes the current phases:

| phase | role |
|---|---|
| `e1_gate` | single-agent attribution control |
| `core_v2` | E2 five-arm memory matrix |
| `e3_lambda` | read-side importance-weight sweep on the append arm |
| `e4_stress` | exploratory T=10 long-horizon stress test |
| `smoke` | small offline/online pipeline check |
| `single`, `single_expel_pilot`, `core` | earlier Phase-Alpha pilots |

E2 condition names:

| condition | meaning |
|---|---|
| `e2_mas_nomem` | four independent solvers, no memory |
| `e2_frozen_reviewer` | reviewer writes memory, but solvers never read it |
| `e2_private_reviewer` | private per-agent memory with ExpeL-style operations |
| `e2_shared_append_ga` | shared append-only memory with GA-style retrieval |
| `e2_shared_consolidated_expel` | shared memory with ExpeL-style consensus consolidation |

### Code Layout

| path | role |
|---|---|
| `sec/run_maze_alpha.py` | main CLI for maze experiments |
| `sec/maze_alpha.py` | Phase Alpha/Beta maze runner, phase definitions, replay and plot outputs |
| `sec/maze_env.py` | generated maze environment and shortest-path evaluator |
| `sec/solver.py` | solver/controller helpers |
| `sec/memory.py` | private/shared/frozen memory pools and retrieval scoring |
| `sec/expel.py` | experience distillation and sanitizer |
| `sec/expel_ops.py` | ExpeL-style pool operations |
| `sec/maze_stats.py` | paired route-level bootstrap statistics |
| `sec/e2_evidence.py` | E2 five-seed evidence package and beta figures |
| `sec/fig1_mechanism.py` | mechanism/case-study figure generator |
| `sec/maze_mechanism_audit.py` | memory provenance and mechanism audit helpers |
| `paper_draft/` | manuscript sections and figures |
| `prereg_phase_beta.md` | frozen Phase-Beta protocol and deviation log |

### Setup

```bash
pip install -r requirements.txt
```

Configure an OpenAI-compatible endpoint:

```bash
export MODELARTS_MAAS_KEY=sk-...
```

PowerShell:

```powershell
$env:MODELARTS_MAAS_KEY = "sk-..."
```

### Quick Checks

Offline checks:

```bash
python -m sec.selftest_maze
python -m sec.selftest_p0
python -m sec.selftest_p1
```

Tiny smoke run:

```bash
python -m sec.run_maze_alpha \
  --phase smoke \
  --model <model> \
  --base-url <openai-compatible-url> \
  --api-key-env <ENV_NAME> \
  --T 3 \
  --train-batch 5 \
  --heldout-size 10 \
  --maze-width 15 \
  --maze-height 15 \
  --maze-family trap \
  --maze-agent-mode state_guided \
  --maze-min-shortest 30 \
  --max-steps 120
```

### Reproduce The Phase-Beta Matrix

E2 five-arm matrix:

```bash
python -m sec.run_maze_alpha \
  --phase core_v2 \
  --model DeepSeek-V3 \
  --base-url https://api.modelarts-maas.com/v2 \
  --api-key-env MODELARTS_MAAS_KEY \
  --seeds 0,1,2,3,4 \
  --T 6 \
  --train-batch 4 \
  --train-size 24 \
  --heldout-size 12 \
  --maze-width 15 \
  --maze-height 15 \
  --maze-family trap \
  --maze-min-shortest 30 \
  --maze-agent-mode state_guided \
  --max-steps 120 \
  --retrieval-k 6 \
  --library-cap 80 \
  --concurrency 8 \
  --skip-final-train \
  --out-dir runs_maze_beta_e2 \
  --cache-dir cache_maze_beta_e2
```

E3 lambda sweep:

```bash
python -m sec.run_maze_alpha \
  --phase e3_lambda \
  --model DeepSeek-V3 \
  --base-url https://api.modelarts-maas.com/v2 \
  --api-key-env MODELARTS_MAAS_KEY \
  --seeds 0,1,2 \
  --T 6 \
  --train-batch 4 \
  --train-size 24 \
  --heldout-size 12 \
  --maze-width 15 \
  --maze-height 15 \
  --maze-family trap \
  --maze-min-shortest 30 \
  --maze-agent-mode state_guided \
  --max-steps 120 \
  --retrieval-k 6 \
  --library-cap 80 \
  --concurrency 8 \
  --skip-final-train \
  --out-dir runs_maze_beta_e3 \
  --cache-dir cache_maze_beta_e3
```

Build the E2 evidence package after producing the run and stats directories:

```bash
python -m sec.e2_evidence \
  --runs-dir runs_maze_beta_e2 \
  --stats-dir runs_maze_beta_e2_stats_5seed \
  --stats-vs-private-dir runs_maze_beta_e2_stats_5seed_vs_private \
  --out-dir runs_maze_beta_e2_evidence
```

Each run writes:

- `result.json`
- `memory_audit.json`
- `curves.png`
- `route_atlas/*.png`
- `replays/index.html`

### Manuscript Artifacts

Current result-section drafts:

- `paper_draft/beta_results_en.tex`
- `paper_draft/beta_results_zh.tex`

Current beta figures:

- `paper_draft/figures/beta/figure1_mechanism.*`
- `paper_draft/figures/beta/figure2_e2_main.*`
- `paper_draft/figures/beta/figure2b_shared_vs_private.*`
- `paper_draft/figures/beta/figure3_write_side_compression.*`

Compiled PDFs and run outputs are local artifacts and are not required for source control.

### Legacy Track

The older QA/math SEC path remains in the repository for historical comparison:

```bash
python -m sec.run_phases --phase A0 --dataset gsm8k --model <model> --base-url <url> --api-key-env <ENV_NAME>
python -m sec.run_phases --phase A1 --dataset gsm8k --model <model> --base-url <url> --api-key-env <ENV_NAME>
python -m sec.run_phases --phase P0 --dataset gsm8k --model <model> --base-url <url> --api-key-env <ENV_NAME>
```

It is not the current main evidence path because QA/math can blur experience learning with answer caching, while the maze environment exposes legality, shortest-path cost, repeats, loops, and route diversity directly.
