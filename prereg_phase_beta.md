# Phase Beta 预注册：忠实经验机制下的策略退化实验（E1–E4）

状态：**预注册（判决规则冻结）**。本文档在任何 E1–E4 数据产生之前写定。
数据出来后，本文档只允许追加"偏离记录"小节，不允许修改判决规则、阈值或主指标。
机制实现见 `sec/expel_ops.py`、`sec/memory.py`（P1 commits `a0c2d84`、`f28f415`），
可信度地基见 P0 commits（cache 盐、配对统计、指标重定义、sanitizer、命名）。

冻结日期：2026-07-02。

---

## 0. 共享设置（所有实验统一，不随结果调整）

- 迷宫：`15x15 trap`，`min_shortest >= 30`；train / heldout 按 seed 固定生成。
- Agent：`state_guided`，`max_steps = 120`，`solver_temp = 0.7`，`max_tokens_solver = 256`。
- 记忆：`retrieval_k = 6`，`library_cap = 80`，检索打分 `ga`（E3 之外统一 `ga_lambda = 0`，
  `ga_recency = 0`），写入协议按条件臂定义。
- 每轮训练批 `batch_M = 4`，`--skip-final-train`（末轮只评不写）。
- 模型：`DeepSeek-V3`（`https://api.modelarts-maas.com/v2`，env `MODELARTS_MAAS_KEY`）。
- cache：solver 调用带 `(run_id, seed, t, task, agent, step)` 盐；轮次间、条件间互为独立样本。
- 统计：一律用 `python -m sec.maze_stats` 的同迷宫配对 bootstrap（10k 重采样，95% CI），
  **任何均值结论必须与 per-seed 表同时呈现**；显著 = CI 不含 0。
- 经验审计：`sanitizer_reject_rate`、pool 熵、逐条 retrieval share 随每次 run 落盘；
  经验池中不允许出现研究者书写文本（P0 保证）。

主指标（预注册，全部 route 级配对）：

1. `success_excess_steps`（仅成功路线的超额步数；效率主终点）
2. `loop_rate`
3. `mas_antmill_rate`（多智能体实验；loop 且路线重合的联合签名）

辅助指标（解释用，不作判决）：`success`、`retrieval_entropy_norm`、`memory_effective_size`、
逐条 retrieval share 时序、`route_diversity_efficient`、`stagnation_rate`、`revisit_max`。

---

## 1. E1 —— 单智能体校准 gate

**问题**：在引入共享之前，忠实化后的经验学习是否可测？

条件臂（phase `e1_gate`）：

- `e1_single_nomem`：无记忆基线。
- `e1_single_reviewer_ops`：ExpeL 操作集写入（mode B），GA 检索 λ=0。
- `e1_single_reviewer_append`：append 写入（mode A），GA 检索 λ=0。

规模：seeds {0,1,2}，T=4，heldout=12，train 16（4/轮）。

启动命令（记录在案）：

```
python -m sec.run_maze_alpha --phase e1_gate \
  --model DeepSeek-V3 --base-url https://api.modelarts-maas.com/v2 --api-key-env MODELARTS_MAAS_KEY \
  --seeds 0,1,2 --T 4 --train-batch 4 --train-size 16 --heldout-size 12 \
  --maze-width 15 --maze-height 15 --maze-family trap --maze-min-shortest 30 \
  --maze-agent-mode state_guided --max-steps 120 --retrieval-k 6 --library-cap 80 \
  --concurrency 8 --skip-final-train \
  --out-dir runs_maze_beta_e1 --cache-dir cache_maze_beta_e1
```

**判决规则（gate）**：对每个经验臂 vs `e1_single_nomem`，在末轮（t=3）做配对检验。

- **PASS**：至少一个经验臂满足——`success_excess_steps`、`success`、`loop_rate`
  三者中至少一个的 95% CI 不含 0，且该指标的 per-seed 均值差在 ≥2/3 个 seed 上同号。
  （方向不限：可测的恶化同样过 gate——gate 检验的是"经验被行为采纳"，不是"经验有益"。）
- **警戒**：任一经验臂 `success` 的配对均值差 < −0.15 → 过 gate 也必须先做依从性分析再进 E2。
- **FAIL**（两臂全部无可测效应）：跑依从性离线分析（action 对 `suggested_action` 的偏离率、
  检索文本与所选动作的一致性，用现有 trace，零成本）。若经验被完全忽略 → 只允许调整
  **注入格式**（prompt 中经验块的位置/呈现），重跑 E1 一次；再 FAIL → 停止，
  按第 5 节判决树进入方向评估。**不允许**为出效应调 solver prompt 的策略指令、
  sanitizer 松紧或 seeds。

预算估计：3 臂 × 3 seeds × ~60 routes × ~70 步 ≈ 3.8 万次 solver 调用（数美元量级，
concurrency 8 下约 2–4 小时）。

---

## 2. E2 —— 核心五臂矩阵

条件臂（phase `core_v2`）：

- `e2_mas_nomem`：4 solver，无记忆（RQ2 基线）。
- `e2_frozen_reviewer`：只写不读（存储-注入隔离）。
- `e2_private_reviewer`：私有池 + ExpeL 操作集。
- `e2_shared_append_ga`：共享池 + append（mode A），λ=0。
- `e2_shared_consolidated_expel`：共享池 + ExpeL 操作集（mode B），λ=0。

规模：先跑 seeds {0,1,2} 作方向 gate，方向一致再补 {3,4}；T=6，heldout=12，train 24（4/轮）。

**判决规则**（基线 = frozen；`e2_mas_nomem` 作次级对照）：

- **内生退化成立**：任一共享臂 vs frozen，`success_excess_steps` 的配对 CI > 0，
  且 per-seed 同号 ≥4/5（gate 阶段 ≥3/3），且 `loop_rate` 或 `mas_antmill_rate`
  至少一个 CI > 0。
- **内生改善成立**：同上，方向取反。
- **无差异**：所有共享臂 vs frozen 与 vs private 的主指标 CI 全部含 0。
- gate 阶段（3 seeds）若五臂全部无差异且效应量点估计 < 5 excess steps，跳过 seeds {3,4}，
  直接进入 E3（λ 才是本命题的真正杠杆）。

---

## 3. E3 —— λ 剂量-反应（头条实验）

条件臂（phase `e3_lambda`）：`e2_shared_append_ga` 架构上 λ ∈ {0, 0.5, 1.0}。

规模：seeds {0,1,2} gate，成立后补 {3,4}；T=6，heldout=12。

**判决规则**：

- **剂量-反应成立**：λ=1 vs λ=0 的 `success_excess_steps` 配对 CI > 0；λ=0.5 的点估计
  落在两端点之间（允许 CI 重叠）；且 `retrieval_entropy_norm` 末轮均值随 λ 单调下降。
- **反向剂量**（λ 越大越好）：同样是可发表的机制结果，主张改写为
  "使用量加权强化在此环境为正向筛选"，进入第 5 节情形二′。
- **无剂量效应**：λ 三点主指标两两 CI 全部含 0 → 情形三。

---

## 4. E4 —— 长反馈链 stress（探索性，非 gate）

T=10，臂：`e2_frozen_reviewer` / `e2_shared_consolidated_expel` / `e3_append_lam1`，
seeds {0,1,2}，heldout=12。报告全轮曲线与"末 3 轮 vs 前 3 轮（t≥1）"的配对差。
探索性分析，不设通过/失败阈值；结果只用于长链形态描述与后续 prereg。

---

## 5. 判决树（预先写定，禁止临场更改）

- **情形一：E2 内生退化成立** → 原主线成文；E4 补长链、桥接任务补外部效度。
- **情形二：仅 E3 λ>0 时退化（E2 λ=0 无差异）** → 主张收窄为
  "退化不是共享经验的固有属性，而是使用量加权检索强度的函数"；标题与贡献句改写为
  dose-response 论文。
- **情形二′：λ 反向（强化改善行为）** → "共识强化在可审计经验池上是正向筛选"，
  与 provenance 审计合并成 analysis 论文。
- **情形三：E2、E3 均无差异** → 依次执行：
  1. capacity-pressure 追加实验（library_cap ∈ {4, 8}，其余同 E2 共享臂，seeds 0-2）——
     容量约束下的淘汰与合并是否自然造成集中与退化；
  2. 若仍无 → 边界分析论文（"何时共享经验有害"：容量、任务异质性、horizon 三变量），
     或将机制主战场移至工具桥接域。scripted-injection 上界对照继续作为机制标尺保留。

**全程纪律**：不为出效应调 solver prompt、sanitizer、seed；每个 claim 对应可点开的
artifact；per-seed 永远展示。

## 6. 偏离记录（数据产生后只许追加）

（暂无）
