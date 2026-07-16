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

**2026-07-03 — E1 结果与 gate 规则缺口**

E1 按第 1 节命令原样跑完（9/9 arm-seed；中途因运行环境退出中断一次，
经带盐 cache 断点续跑完成，不影响样本）。判决：

- **三个主指标全部 CI 含 0**（两臂 vs no-mem，t=3，n_pairs=36；
  `runs_maze_beta_e1_stats/paired_stats.csv`）→ 按冻结条文为 **FAIL**。
- 警戒线未触发（reviewer_append success 均值差 −0.139 > −0.15）。
- 规定的依从性分析显示经验**没有被忽略**：reviewer_ops 臂在记忆激活后
  （t≥1 vs t=0）对 controller 建议动作的偏离率 +0.041 且三个 seed 全部同向
  （no-mem 基线漂移 −0.002）；配对终点上 reviewer_append 的 revisit_max
  显著下降（CI [−2.00, −0.14]），reviewer_ops 的 stagnation_rate 显著上升
  （CI [0.0003, 0.086]）。
- 机制健康：ops 臂 LLM 实际使用全部操作（每 seed 约 ADD 7–9 / UPVOTE 30–37 /
  DOWNVOTE 1–4 / EDIT 1–2），池收敛在 7–8 条；append 臂池 18–19 条、
  熵 0.87–0.98（λ=0 下无过早集中）；sanitizer 拒绝率 0.00。

**规则缺口**：条文只定义了"完全忽略 →（改注入格式）重跑一次"与"可测 → PASS"
两条路径，未预设"行为可测采纳、但三个主终点无显著变化"的情形。
本记录如实登记：E1 在冻结条文下 FAIL；经验采纳性（gate 的设计意图）
有跨 seed 一致的行为证据。是否进入 E2 由研究者决定并在此追加记录；
若进入，E2 判决规则不变。

**2026-07-03 — 研究者裁决**：基于采纳性证据进入 E2 gate（seeds 0-2），
E2 判决规则按第 2 节冻结条文执行，不变。

**2026-07-05 — E2 gate 判决（seeds 0-2，冻结规则原文执行）**

数据质量：15/15 arm-seed 完成，全部 `llm_error_count = 0`（韧性兜底未触发），
sanitizer 拒绝共 9 条，λ=0 下池熵 0.87–1.0。统计见
`runs_maze_beta_e2_stats/`（配对 bootstrap，t=5，n_pairs=144）。

**内生退化成立，由 `shared_consolidated_expel` 臂驱动**，冻结规则三条件全中：
(a) success_excess_steps 配对 CI [+3.19, +13.66] > 0；
(b) per-seed 同号 3/3（+7.71 / +7.83 / +9.58，跨 seed 高度一致）；
(c) looped 配对 CI [+0.035, +0.139] > 0。
另 success 配对差 −0.19（CI 不含 0，3/3 同号）。

其余臂：`shared_append_ga` 不满足规则（sxs 不显著，per-seed +−+）；
`private` 合并 sxs 显著但 per-seed +−+（seed1 反向），不构成一致退化；
`mas_nomem` vs frozen 各主指标≈无差异（RQ2：多智能体执行本身不病态；
frozen≈no-mem 亦确认存储无害，**注入是危害通道**）。
所有主动记忆臂 success 均显著下降（−0.16~−0.19，3/3 同号）——
"共识合并型共享记忆产生跨 seed 最稳定的退化"是本轮核心结论。
ant-mill 事件存在但稀少（consolidated 0.056 vs frozen 0.028，n 不足以判定）。

按第 2 节条文：方向成立 → 后续补 seeds {3,4}；按第 3 节：进入 E3 λ 剂量-反应 gate。

**2026-07-07 — E2 完整判决（5 seeds，冻结规则原文执行）：内生退化确立**

数据质量：25/25 arm 完成，全部 llm_error 占比 < 1%（0 个超阈）。统计见
`runs_maze_beta_e2_5seed_vs_frozen/`（n_pairs=240，success_excess_steps n=115–150）。

**shared_consolidated_expel 满足全部冻结判据**：
- success_excess_steps 配对 CI [+7.66, +16.02] > 0，per-seed **5/5 同号**
  （+7.7/+7.8/+9.6/+17.8/+18.5，且 seed3-4 效应更大）；
- looped CI [+0.092, +0.188] > 0，4/5 同号（1 个为 0）；
- success −0.171，CI 不含 0，5/5 同号。
→ **达成 §2 "内生退化成立"（≥4/5 同号）**。

对照臂：
- `mas_nomem` vs frozen：效率/success 无差异，looped +0.042（CI [0.008,0.075] 显著）
  → 多智能体执行本身不致效率退化，仅轻微 loop 上升（沿用 07-05 更正表述）。
- `shared_append` vs frozen：success 显著降（−0.121）但 sxs 不显著、looped 不显著、
  per-seed +−+++ → **未达退化判据**。
- `private` vs frozen：sxs 显著（+7.32）且 4/5 同号，success 显著降 5/5 →
  private 注入也退化，但效应弱于 consolidated。

**shared vs private（新增，seed3-4 后浮现的关键分离）**：shared_consolidated vs private
直接配对（n=240）——looped **+0.058，CI [+0.008, +0.113]，显著**；sxs/success 含 0。
即：**共识合并型共享记忆的循环退化显著强于私有记忆**（3 seed 时此对比全 null，
5 seed 后 loop 维度分离出来）。上一条 07-05 的 claim 限定据此**部分解除**：
shared 特异性在 loop 维度已获配对显著证据，但效率（sxs）维度仍不能声称 shared>private。

**综合结论（论文主线可写）**：单智能体无害（E1）→ 多智能体经验注入致退化，其中
LLM 共识合并写入产生跨 seed 最稳健、且循环维度上显著强于私有的退化（E2）→
退化不来自读端使用量加权（E3 负结果）而来自写端共识压缩（策略供给收窄 2–2.5×）。

**2026-07-06 — E3 gate 判决（seeds 0-2，冻结规则原文执行）：无剂量效应**

数据质量：9/9 arm-seed 完成，llm_error 合计 1（占比≈0，远低于 1% 阈值）。
统计见 `runs_maze_beta_e3_stats/`。判据逐条：
(a) λ=1 vs λ=0 的 sxs 配对 CI [−4.26, +7.61] 含 0 → 不成立；
    λ=0.5 vs λ=0 sxs [−0.34, +11.06] 含 0，success [−0.19, 0.00] 边界含 0；
    looped 两两均含 0 → **无剂量效应**；
(b) 末轮 retrieval_entropy_norm 均值 0.833 / 0.826 / 0.845（λ=0/0.5/1）非单调 → 不成立；
(c) 亦无反向剂量。**读端使用量加权正反馈假设在 append 机制上被判伪（负结果，保留）。**

**判决树缺口记录**：§3 的"无剂量效应 → 情形三"以 E2 亦无差异为前提，与实际
（E2 阳性）不符。组合立场：走 §5 情形一路径（主线 = consolidated 相对 frozen 的
稳健退化），λ 读端机制主张撤下，改为负结果消融。

**机制解释转移（基于既有数据的离线分析，无新实验）**：退化的集中通道在**写端**而非
读端——相同设置下，consolidated 的经验池收敛至 11–17 条、全轮次全任务实际注入的
不同经验仅 11–14 条（末轮 7–8 条覆盖全部 12 个任务），而 append 池达 cap 80、
实际注入 23–29 条。共识合并把整个种群的策略供给压缩约 2–2.5 倍。
另记录一个结构事实：shared 模式下同一任务的检索对所有 agent 恒等
（query 任务条件化但无 agent 分量），"跨 agent 检索趋同"在本设计中不可作为机制指标，
集中度必须按跨任务/跨轮口径度量。后续论文的 Fig 3 素材以写端压缩为主线。

**下一步（按 §2 条文）**：补 E2 seeds {3,4} 以完成 4/5 同号的完整判据；E4 探索性长链视预算。

**2026-07-05 — 对上一条判决记录的两处表述修正（复核后追加，不改判决本身）**

1. **claim 范围限定**：直接对比 shared_consolidated vs private（配对，t=5，
   `runs_maze_beta_e2_stats_vs_private/`）所有主指标 CI 均含 0
   （sxs −4.93，CI [−11.18, +1.35]；looped +0.049，CI [−0.007, +0.111]）。
   因此 E2 已确立的是 **"consolidated active memory 相对 frozen 退化"**（冻结规则
   本身就是 vs frozen），**尚未确立 "shared 显著坏于 private"**；shared 特异性目前
   只有跨 seed 稳定性差异（consolidated 3/3 同号 vs private/append 的 +−+）这一
   较弱形态的证据。shared-vs-private 分离押注于 E3 的 λ 杠杆与 seeds {3,4}。
   论文叙事在此之前不得声称"共享已被证明比私有更危险"。
2. **更正"mas_nomem 各主指标≈无差异"**：mas_nomem vs frozen 的 looped 实为
   +0.056（CI [0.014, 0.097]，显著）。准确表述：效率（sxs）与 success 无显著差异、
   loop 略高；总体不支持"多智能体执行本身导致效率退化"，但"完全无差异"不成立。

**2026-07-03 — 基础设施韧性补丁（工程性偏离，不改判决规则）**：E2 首次启动在
seed0 frozen 臂训练批被 ModelArts 内容过滤器（81011，输出侧）连续 403 六次击穿，
整个 run 崩溃。补丁：(a) `llm.py` 对内容过滤错误在重试时附加良性格式提示 nonce
（cache key 仍绑定原始请求）；(b) solver 单次调用最终失败降级为 `inspect` 一步，
reviewer 调用失败跳过该批写入——两者均计入 `llm_error_count` 与 audit `llm_errors`，
随结果一并报告。若任一 arm 的 llm_error 步数占比 > 1%，该 arm 数据作废重跑。
E2 经带盐 cache 断点续跑，已完成部分不受影响。

**2026-07-07 — E2 完整 5-seed 判决（seeds 0-4，冻结规则原文执行）：consolidated vs frozen 成立，shared-vs-private 仍需限界**

数据质量：25/25 arm-seed 完成，统计见 `runs_maze_beta_e2_stats_5seed/` 与
`runs_maze_beta_e2_stats_5seed_vs_private/`；证据包见 `runs_maze_beta_e2_evidence/`。

按 §2 冻结判据，`shared_consolidated_expel` 相对 `frozen` 的内生退化成立：
(a) `success_excess_steps` 配对差 +11.84，95% CI [+7.66, +16.02]，CI 全部 > 0；
(b) per-seed 方向为 4/5 同号变差：seed0 −0.81，seed1 +6.27，seed2 +8.23，
seed3 +9.30，seed4 +8.17；
(c) `looped` 配对差 +0.138，95% CI [+0.092, +0.188]，CI 全部 > 0。
辅助指标同向支持：`stagnation_rate` +0.093，CI [+0.076, +0.110]；
`revisit_max` +1.675，CI [+1.233, +2.125]；success −0.171，CI [−0.242, −0.100]。

claim 边界同步冻结：5-seed 后 `private` 相对 `frozen` 也在主效率终点上显著变差
（sxs +7.33，CI [+2.83, +11.90]；looped +0.079，CI [+0.037, +0.125]）。
因此宽口径风险是 active memory injection；`shared_consolidated_expel` 的特异性证据更窄。
`shared_consolidated_expel` 相对 `private` 尚未在主效率终点上显著更差
（sxs +0.87，CI [−4.29, +6.15]；cost_ratio +0.016，CI [−0.078, +0.113]；
success +0.004，CI [−0.071, +0.079]），但 `looped` 更高（+0.058，
CI [+0.008, +0.113]）。因此论文不得写成"shared memory 已被证明全面坏于 private"；
准确主张是：**consolidated active memory 相对 write-only/no-injection control 稳健退化，
shared-specific 风险目前主要体现为 loop 放大与写端策略供给压缩，而非主效率指标上的
shared-vs-private 全面分离。**

机制审计同步入档：`shared_consolidated` 平均实际注入的不同经验为 11.0 条，
`shared_append` 为 25.4 条，append/consolidated 比值为 2.31x；最终池大小范围分别为
consolidated 11–17 条、append 80 条。泄漏扫描未发现 maze id、具体坐标或长固定动作序列式
经验文本。E3 的 λ 读端剂量效应仍作为负结果保留；机制焦点维持在写端共识合并造成的
strategy-supply compression。

**2026-07-10 — E4 长反馈链 stress 结果（T=10，探索性，非 gate，按 §4 原文执行）**

数据质量：9/9 arm-seed 完成（frozen / shared_consolidated_expel / shared_append_lam1
× seeds 0-2），heldout=12。统计见 `runs_maze_beta_e4_stats_t3/`、`_t6/`、`_t9/`
（vs-frozen 配对，t=3/6/9 三个检查点）与本节内联的组内 last-3-vs-first-3（t∈{1,2,3}
对 t∈{7,8,9}，按 §4 原文）趋势计算。

*vs-frozen 配对差（t=3 → t=6 → t=9，全部 144 对）*：

- `consolidated`：success −0.174[−0.271,−0.076] → −0.146[−0.236,−0.056] → −0.257[−0.354,−0.160]，
  三个检查点 CI 全部 <0；looped +0.083[+0.021,+0.153] → +0.083[+0.021,+0.146] →
  +0.118[+0.049,+0.188]，CI 全部 >0；excess_steps 稳定在 +8.7~+9.4 区间，CI 全部 >0。
  末轮（t=9）是三个检查点中 success 差距最大、looped 差距最大的一点。
- `append_lam1`（shared append + GA λ=1）：success/looped 在三个检查点 CI 均含 0
  （与 frozen 无显著差异）；t=9 时 cost_ratio −0.129[−0.251,−0.007]、
  excess_steps −5.39[−9.95,−0.88]、revisit_max −0.438[−0.840,−0.028] 三者 CI 全部 <0，
  即长链末端 append 协议反而比 frozen 更省步——不是"无害"而是方向上略优。

*组内趋势（late−early，t∈{7,8,9} 减 t∈{1,2,3}，同 task_id/agent_id 配对，排除 t=0 暖启动轮）*：

- `frozen`：全部 6 个指标 CI 含 0（success +0.005[−0.044,+0.053]，looped +0.019[−0.012,+0.049]）——
  基线自身不随轮次漂移，confirm 稳定对照。
- `consolidated`：全部 6 个指标 CI 含 0（success −0.035[−0.090,+0.021]，
  looped +0.014[−0.039,+0.067]）——**组内自身趋势不显著**：vs-frozen 差距在 t=3 已经确立，
  t=9 末轮点估计更差但组内配对检验不足以判定"持续恶化"，只能判定"早期确立、末轮噪声内偏差"。
- `append_lam1`：cost_ratio −0.079[−0.154,−0.003]、excess_steps −3.50[−6.32,−0.69]、
  stagnation_rate −0.026[−0.039,−0.012]、revisit_max −0.340[−0.607,−0.069] 四项 CI 全部 <0
  ——append 协议在 T=10 内呈现**显著的组内自我改善趋势**（经验池持续增长、检索命中增多，
  越跑越省），与 consolidated 的"早锁定不改善"形成对照。

*consolidated 组内趋势的 per-seed 拆分*（success，late−early）：seed0 +0.083[0.000,+0.174]
（改善方向，CI 含 0 但下界=0，n=48）、seed1 −0.097[−0.188,−0.014]（唯一 CI 排除 0 的 seed，
组内下降显著）、seed2 −0.090[−0.194,+0.014]（下降方向但 CI 含 0，单 seed n=48 噪声大）。
seed2 的逐轮曲线本身是本次实验中最极端的单例：success 0.77→0.44→0.29→0.40→0.33→0.46→
0.60→0.44→0.25→0.17，looped 0.02→0.19→0.38→0.27→0.21→0.25→0.21→0.38→0.31→0.46，
接近单调滑向重度 ant-mill；seed0/seed1 则是围绕已确立差距的震荡，未见同等强度的单调滑坡。
**据纪律 3，此 per-seed 异质性本身即为发现**：consolidated 的长链风险不是所有实例同等速率
变化；均值同时掩盖了 seed1 的显著组内下降与 seed2 更极端、但组内 CI 仍含 0 的逐轮轨迹。

**结论（探索性，不进入 gate 判据）**：长反馈链（T=10 对比 E2/E3 的 T=6）下，
(1) consolidated vs frozen 的核心退化（success↓、looped↑）在长链上持续存在、不自愈，
末轮点估计甚至是全程最差点，但组内自身漂移检验不足以证明"持续加深"，更准确的描述是
"早期确立、总体高位持平；seed1 显著组内下降，seed2 轨迹最极端但其组内 CI 含 0"；
(2) append 协议不仅在长链上继续保持
无害，反而表现出显著的组内自我改善趋势，与"证据供给未被压缩的写协议能从更长的积累中
获益"这一写端机制假说方向一致；(3) 均值层面的"持平"掩盖了 seed 间分布形状的显著差异，
未来若做外部效度验证，应检验这种极端轨迹能否复现及其发生频率，而非仅报告均值是否变差。
