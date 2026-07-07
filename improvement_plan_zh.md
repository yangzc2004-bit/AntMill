# AntMill 长期改进计划：从机制雏形到可投稿实验系统

状态：研究路线文档（2026-07）。
依据：对分支 `codex/maze-alpha-strategy-degradation`（HEAD `3541406`）的代码级审查，
包括 `sec/maze_alpha.py`、`sec/expel.py`、`sec/memory.py`、`sec/fusion.py`、`sec/llm.py`、
全部 T=3 / T=5 run 数据（`result.json`、per-seed CSV、memory pool 实际内容）和
`paper_draft/figures/` 五张图。文中每一条对现状的断言都在这些文件里核实过，不是印象判断。

---

## 一、整体判断

先把话说明白：这个项目不需要推倒重来，但也远没有到"再多跑几组实验就能投"的程度。
你们现在拥有的是一台好显微镜和一份错误的样本制备流程。

**真资产**（这些东西大多数做 MAS 失败研究的组都没有，要守住）：

- 环境仪表化：BFS 最短路径仅研究者可见、撞墙阻止并记录、带 goal-progress 豁免的
  loop 检测、全量轨迹落盘（`sec/maze_env.py`）。"无报错的合法低效"在这里是可精确测量的。
- 配对评测设计：同一批 fixed heldout 迷宫跨所有条件复用，天然支持配对统计。
- provenance / audit 管线：经验条目带来源轨迹质量元数据，"文本正确但来源轨迹低效"
  是全项目最有原创性的机制观察。
- case study 图（`targeted_t5_case.png`）：同迷宫同 agent，67 步 / 79 步 / 148 步对比，
  几乎可以直接进论文第一页。

**真债务**（四笔，每一笔都足以让一个认真的审稿人拒稿）：

1. **写入内生性缺失**：direct/oracle 条件的"经验"是 `_direct_insight` /
   `_route_avoid_insight`（`sec/maze_alpha.py:913-939`）里研究者手写的固定模板，
   LLM 不参与写入。目前论文的主退化证据建立在"给 agent 塞一条我们自己写的贪心提示"上。
2. **正反馈通道不存在**：检索 query 是常量字符串（`_agent_query`），检索只按词面相似度
   排序（`memory.py:29`），votes 和 retrieval_count 不进入排序。论文声称的
   "写入→检索→复用→共识强化"的放大环，代码里只实现了"写入→注入 prompt"这一段。
3. **cache 把静态重放伪装成动力学**：LLM cache key 不含轮次盐（`llm.py:94`），
   相同 prompt 跨轮返回相同结果。frozen 的"跨轮稳定"是逐字节重放；T=5 shared_direct
   的 t=1,2,3 三行数字完全相同，t=4 的"崩溃"是 memory pool 从 1 条变 3 条之后的
   单次 12-route 测量。
4. **统计量不设防**：heldout=3 张迷宫 × 4 agents = 每轮 12 条路线；batch_M=1；
   T=3 三个 seed、T=5 单 seed；shared_direct 在 seed1 完全不退化（success 1.0）。

由此得出本计划的总纲：**先做一次"机制忠实化 + 统计工业化"的改造，再重跑一切**。
工作量分布大约是：40% 工程与统计管线，40% 实验重跑，20% 论文与图的重写。

以及一条纪律，从今天起执行：**在 P0 和 P1 完成之前，不许再跑任何新的大规模实验，
不许再往论文正文里加任何新数字。** 现在多跑的每一个 run 都是将来要扔掉的 run；
现在多写的每一段结果都是将来要撤回的结果。pilot 阶段的探索自由到此为止。

---

## 二、当前结果的可信度清单

在规划未来之前，先诚实地给现有结果分类。这份清单同时回答"哪些数字还不可信、为什么"。

**不能再引用的（作废）**：

- direct / oracle 两个条件的全部结果与排序 —— 写入内容是手写模板；且 seed0/seed1 下
  shared_oracle 与 shared_direct 的逐轮数据完全相同（同模板→同 prompt→同 cache 命中），
  它们在多数 seed 下根本不是两个条件。
- `mechanism_scatter.png` 的 r=0.66 相关 —— retrieval concentration 定义为
  `max(count)/total`，pool=1 时恒为 1.0，reviewer pool=8、k=6 时恒约 0.2。
  这个相关是五个条件的簇间分离，不是剂量-反应。
- frozen 的"跨轮稳定性"、T=5 的"渐进退化曲线"、t=4 的"崩溃" —— 全部是 cache
  重放或单次测量（见上文债务 3）。
- T=3 矩阵的条件间排序 —— heldout=3 之下，任何一个条件换一批 heldout 都可能翻转。

**方向可信、证据强度不足的（保留假设地位，重跑后再定）**：

- shared reviewer 短链改善、长链回退的形态。
- "文本正确 ≠ 来源优质"的 provenance 观察（reviewer-write 部分成立，
  direct/oracle 部分作废）。
- reviewer-write 经验文本总体是抽象策略而非坐标/路线缓存（已实测 pool 内容确认，
  但 sanitizer 有漏洞：3 个方向词的固定序列漏网）。

**完全可信、直接复用的**：

- 环境语义、指标定义、配对 heldout 设计、audit schema、replay/atlas 工具链。

**一个必须正视的反向证据**：现有数据里，退化组的 route diversity 更高
（direct 0.277 / oracle 0.236 > frozen 0.177），改善组最低（reviewer 0.139）。
"路径同质化"目前被自己的数据反证——因为 visited-cell Jaccard 与效率天然混淆。
这决定了后文叙事修订里同质化 claim 必须降级。

---

## 三、P0：地基修复 —— 让后续每一个数字都可辩护

这一层全部是工程和统计，没有一个 LLM token 的开销，却决定之后所有实验的成色。
先做它们的理由很简单：**这些问题不修，跑得越多，废弃得越多。**

**T0.1 —— LLM cache 加盐。**
solver 调用的 cache key 加入 `(t, task_id, agent_id)`；reviewer 蒸馏调用保留原 cache
以省钱。解决的问题：轮次动态目前是重放，frozen/静态池条件的曲线不含任何信息。
完成后的可信度增量：每一轮成为独立样本，"随轮变化"第一次成为真实测量；
frozen 曲线的波动变成天然的噪声底，反而帮你标定效应量的下限。

**T0.2 —— 统计管线。**
实现同迷宫配对 bootstrap（条件间对比在同一 heldout 迷宫上做差再重采样）、95% CI、
per-seed 全量展示（均值旁边永远放逐 seed 散点）。成功与失败分离报告：
成功路线的 excess steps 单列，失败率单列——现在 `cost_ratio` 把失败惩罚
（180/30≈6）混进均值，T=5 direct 的 cost 4.135 有一半来自 success=0.5。
可信度增量：审稿人最容易写的一句拒稿理由"no error bars, n=12"直接消失。

**T0.3 —— 机制指标重定义。**
废弃 `max/total` 版 retrieval concentration，换成三件：pool 熵 / effective rank、
逐条 memory 的 retrieval share 时间序列（rich-get-richer 曲线的原始数据）、
efficiency-conditional diversity（只在成功且 cost 低于阈值的路线间算重合，
拆掉多样性与效率的混淆）。同时把已实现却从未上报的 `mas_antmill_rate`
（loop 且路线重合的联合签名，`maze_alpha.py:777`）纳入标准输出。
可信度增量：机制变量从"定义假象"变成可随时间演化、可被条件操纵的真实观测。

**T0.4 —— sanitizer 收紧。**
`looks_over_specific`（`sec/expel.py:69`）的方向序列阈值从 ≥4 收到 ≥2 个有序方向词
（实测已有 "down then left then up" 漏网进入 reviewer pool）；sanitizer 触发时
从"替换为 fallback 模板"改为"丢弃并计数"，新增 `sanitizer_reject_rate` 指标——
替换制意味着研究者手写文本可以混进 reviewer pool 并累积 votes，这是第二个
潜在的"自己造靶"入口。可信度增量：可以在论文里放一句硬话
"经验池中不存在任何研究者书写的文本"，并给出审计证据。

**T0.5 —— 命名与文档诚实化。**
`debate_rounds=1` 时修订循环不执行，agents 从不看到 peer 提案，全文停用 "MAD" 称谓，
改为 "independent solvers with shared experiential memory"；direct/oracle 改名
`scripted-injection`，在所有文档、代码注释、图例中统一，并明确其角色是
"可控注入上界对照"。论文 tex 冻结：在新数据出来前只删不加。
可信度增量：审稿人查代码时发现的每一处"名不副实"都会折算成对其余所有主张的怀疑，
这一条是在还清信誉债。

---

## 四、P1：经验机制忠实化 —— 对齐 ExpeL / Generative Agents，而不是自造

这是你最关心的方向，先把原则钉死：**审稿人要求的是机制设计点的忠实
（design-point fidelity），不是代码库的出身。** 自己写代码不是画靶子；
自己发明机制设计点才是。当前仓库的问题恰恰是后者：对比蒸馏（`distill_expel_insights`）
方向是对的，但 ExpeL 的两个灵魂组件被换成了自制品——

- ExpeL 的 insight 池演化由 **LLM 自主发出 ADD / EDIT / UPVOTE / DOWNVOTE 操作**，
  reviewer 看得到现有池再决策；你们的 `fusion._apply_insight` 是代码写死的
  相似度合并加 support_count 公式，LLM 从不看到池子。"共识强化"这个词
  在你们代码里没有忠实载体。
- ExpeL 的检索是**按当前任务 embedding 做 top-k**；你们的检索 query 是常量字符串。
  "检索复用"这个词同样没有载体。

于是任务如下：

**T1.1 —— LLM-issued 操作集。**
重写共享池更新：reviewer prompt 给出现有 insight 池（带编号与票数）+ 新一批轨迹，
输出严格 JSON 的操作列表 `[{op: ADD|EDIT|UPVOTE|DOWNVOTE, target_id, text}]`，
代码只执行不决策（sanitizer 作为执行前过滤，触发即丢弃该操作并计数）。
ExpeL 原文 prompt 是公开的，直接搬，改动仅限于领域名词。
为什么优先：这是"共识驱动的经验强化"从叙事变成被试机制的那一步——
UPVOTE 谁、EDIT 成什么，正是你要研究的正反馈的发生位置。
可信度增量：related work 里可以写"我们的写入机制即 ExpeL 操作集的多 agent 扩展"，
"自造经验机制"的攻击面消失。

**T1.2 —— 任务条件化检索。**
query 从常量字符串换成当前 episode 的局部观测摘要（起点-终点相对方位、迷宫尺寸、
最近若干步的状态特征），embedding 用 `metrics.hashing_embedding` 起步、
投稿前换 sentence-transformer 复核一遍结论不变；k 沿用 ExpeL published 值。
为什么优先：没有任务条件化，检索集中度永远是 pool 大小的函数，
机制变量无从谈起。可信度增量：检索行为第一次可以随任务、随池内容变化，
"哪些经验被反复选中"成为系统的内生输出。

**T1.3 —— GA-style 检索打分与 λ 旋钮。**
检索分数 = relevance + λ·importance + recency，其中 importance 由票数/使用量驱动。
这不是自造：Generative Agents（Park et al., 2023）的 memory stream 检索
就是 relevance + importance + recency 三项加权，你只是把 importance 的来源
接到共识票数上，并把 λ 做成可扫的正反馈强度旋钮。
为什么优先：λ 剂量-反应是这篇论文能否称为机制论文的分水岭——
"退化随反馈强度单调增强"是比任何条件间对比都硬的证据形式。
可信度增量：正反馈从被声称变成被操纵。

**T1.4 —— Reflexion 重试（降级为可选消融）。**
ExpeL 原始经验收集带失败重试以产生 success/fail 对比对。完整复刻成本高，
允许降级：主实验不带重试，附录用小规模消融证明"带不带重试不改变退化方向"。
优先级低于 T1.1-T1.3，但 fidelity table 里必须如实标注此偏离。

**T1.5 —— fidelity table。**
论文与 README 各放一张表：组件 | 原方法出处（ExpeL/GA/ECL）| 我们的实例化 |
偏离及理由。这张表是防御工事：主动声明偏离，永远好过被审稿人发现偏离。

---

## 五、P2：分歧策略如何入池 —— 锚定主流，不发明融合

先给判断，这个判断本身就是你论文 related work 的一段：
**主流系统里不存在"分歧策略的显式冲突消解"。** 已发表的共享经验机制只有两类模式：

- **模式 A：append + retrieve。** 各 agent 的反思直接进池，分歧不融合，
  由检索打分裁决谁被复用。Generative Agents 的 memory stream、
  各类 RAG-style agent memory、Voyager 的 skill library 都属此类。
- **模式 B：LLM consolidation。** 一个 reviewer/LLM 看批量轨迹与现有池，
  做增删改与投票，分歧被相似度合并和票数**压掉**而非消解。
  ExpeL 操作集、ChatDev 的 Experiential Co-Learning（把历史轨迹蒸馏成
  shortcut 经验共享）、MetaGPT 的消息池（弱化版）属此类。

这对你是好消息：不需要发明融合机制然后攻击它——
**"主流机制不消解分歧，只做相似合并与投票强化"本身就是被研究的漏洞。**
发明一个复杂融合方法再证明它有问题，才是真正的画靶子。

**T2.1 —— 实现 `shared_append_ga` 条件**：每 agent 的 LLM 反思直接入池，
GA-style 打分检索（含 λ）。这是模式 A 的忠实实例。

**T2.2 —— 实现 `shared_consolidated_expel` 条件**：跨 agent 批量走 T1.1 的操作集，
多个 agent 产生相似 insight 时由 LLM 决定 UPVOTE——这就是"共识写入"的有出处版本，
彻底替换现在的 direct/oracle 硬编码条件。

**T2.3 —— 分歧观测指标（观测，不是机制）**：入池前 insight 冲突率
（do/avoid 语义对立对的比例）、池内共存矛盾对计数、矛盾对中被高频检索一方的
来源质量。这些指标让"分歧被票数压掉之后发生了什么"变得可见，
是机制章节的新素材，而不是新发明的融合算法。

---

## 六、P3：harness 判断 —— 保留自建，外部实锤补一发

你的倾向（保留自建 harness）是对的，三个理由，写进论文的实验设置一节：

1. AutoGen / CAMEL / LangGraph / CrewAI 是**编排层**，没有一个自带
   "共识驱动的共享经验记忆"作为核心机制。迁移过去，共享 memory 仍然要自己实现，
   忠实度问题一分没解决，只是给自制机制套了主流外壳。
2. 迁移的真实代价是失掉最值钱的资产：确定性 cache、逐步 trace、replay/atlas、
   provenance audit。机制研究需要显微镜，通用框架是手术台。
3. 先例充分：MAD 复现质疑类、memory poisoning 类工作（如 AgentPoison）
   都是自建忠实实例 + 声明设计点来源，没有谁被要求跑在某框架上。
   你们自己 `experiment_architecture.md` 第 0 节的 "faithful before broken" 
   就是正确标准，照它执行。

但"主流系统确实存在此问题"的外部效度证据要补一发，放泛化章节，控制范围：

**T3.1 —— ChatDev ECL 外部复现（case 级）。**
在 Experiential Co-Learning 的公开代码与任务上测退化签名（重复动作率、
成本随共享经验积累的变化、经验检索集中）。3-5 个任务的 case 级证据即可，
不追求统计功效——它的作用是把"主流系统实锤"这句话从推测变成引用自己的实验。
时点：放在核心矩阵出信号之后，与 bridge 任务合并考虑优先级。

**T3.2 —— 工业形态备选。**
若 ECL 集成受阻，退而求其次：AutoGen 或 LangGraph + Mem0/LangMem 共享记忆，
作为 bridge task 的载体顺带完成，一石二鸟。

---

## 七、P4：实验重跑 —— gate 化排序，每一步有判决规则

所有实验统一设置：15×15 trap、`min_shortest>=30`、`state_guided`、max_steps 120、
batch_M=4（现在每轮只用 1 张训练迷宫写经验，太薄）、cache 按 T0.1 加盐。
排序原则：**每个实验是下一个实验的 gate，gate 不过就停下来想，不许硬跑。**

**E1 —— 单智能体 ExpeL 校准（RQ1 gate）。**
条件：single no-mem vs single reviewer（忠实化后的 T1.1+T1.2 版本），
T=4、heldout=12、seeds 0-2。现在 `runs_maze_alpha_single_*` 全是设置不一的
pilot，多个 run success_final=0.000，蓝图自设的 Stage-1 gate 从未干净通过。
判决：经验条件相对 no-mem 在成功条件 excess steps 或 success 上有可测变化
（不必是改善，但必须可测且方向稳定）。不过 gate 的含义是经验根本没被行为采纳，
后续一切退化实验无从谈起——先查注入格式与依从性，再考虑换 solver 模型。

**E2 —— 核心五臂矩阵。**
条件：MAS no-memory / frozen / private / shared_append_ga(λ=0) /
shared_consolidated_expel。T=6、heldout=12、seeds 0-4。
这里补上从未进过报告矩阵的 MAS no-memory 基线（RQ2）。
量级估算：12 迷宫 × 4 agents × 6 轮 ≈ 288 routes/条件/seed，均步约 80
→ 约 2.3 万次 solver 调用/条件/seed；5 条件 × 5 seeds ≈ 58 万次调用，
DeepSeek-V3 价位数十美元量级，可行。先跑 seeds 0-2 做方向 gate，再补 3-4。
判决：shared 两臂相对 private/frozen 的配对 CI。

**E3 —— λ 剂量-反应（本计划的头条实验）。**
shared_append_ga，λ ∈ {0, 0.5, 1}，其余同 E2，seeds 0-4。
支持主线的形态：excess steps / loop / `mas_antmill_rate` 随 λ 单调上升，
pool 熵随 λ 单调下降，且 λ=0 与 private 无显著差异（说明害处来自反馈而非共享本身）。
这张剂量-反应图是 Figure 3 的灵魂，也是"正反馈放大"命题的直接检验。

**E4 —— long-chain stress。**
T=10，三臂：frozen / shared_consolidated / shared_append(λ=1)，seeds 0-2。
检验 reviewer 形态条件的"晚期回退"是否真实存在——这是现有数据里唯一的
内生退化信号，值得单独验证，但必须排在 E2/E3 之后：短链上都立不住的效应，
长链上的形态没有解释力。

**E5 —— scripted-injection 上界对照（低成本，随 E2 顺带）。**
保留原 direct 模板作为"单条集中经验的最大破坏力"标定，1-2 seeds 即可。
它的论文角色从主结果降为机制标尺。

**E6 —— bridge MVP（gate: E2 或 E3 出信号才启动）。**
in-repo 确定性 tool-API 微基准：8-12 个 API 的模拟工具任务，脚本可算
最小调用数（cost ratio 的精确类比物），复用全部 audit/replay 管线。
10 任务 × 3 条件（frozen / private / shared λ=1）× T=4 × 3 seeds。
目标只要一句话："迷宫里的集中-低效耦合在工具任务上方向一致"。
MiniWoB 与 ECL 复现排在它之后。

**离线分析（零 token 成本，与 E1 并行）**：用现有 trace 跑依从性分析——
action 与 `suggested_action` 的偏离率在有/无 memory 注入下的对比。
这是对"退化只是 controller 指令与经验文本打架"这一攻击的直接回应，
数据已经全在 `result.json` 的 trace 里。

---

## 八、P5：论文叙事与图 —— 跟着证据升降级

**必须降级的 claim**：

- "路径同质化"：现有数据反向（退化组更发散）。除非 λ regime 下出现
  "同质且低效"，否则从核心主张降为讨论，主张收缩为
  "低效 + 循环 + 检索集中"三件套。宁少一个 claim，不留被自己数据反证的 claim。
- "共识驱动"：在 T1.1 落地之前，代码里没有共识机制，这个词暂时不许出现在
  贡献句里；忠实化后凭 UPVOTE 数据恢复。
- direct/oracle 的"崩溃"叙事：整体改写为 scripted-injection 上界标定。

**保留并强化的 claim**：

- "无报错的合法低效循环"——环境证据扎实，case study 支撑。
- "文本正确 ≠ 来源优质"——provenance 审计的原创观察，
  用 T0.4 之后的 reviewer/consolidated 数据重建。

**必须新增的机制证据（对应三张缺失的图）**：

- λ 剂量-反应曲线（E3 产出）——新 Figure 3a。
- 逐条 memory retrieval share 随轮次的 rich-get-richer 轨迹（T0.3 产出）——Figure 3b。
- insight 效用探针：取 top-5 高检索经验，单条注入 single-agent 跑 heldout，
  测每条的因果 Δcost——把"文本正确但有害"从相关升级为因果，Figure 3c 或表。

**图的重组**：

- Figure 1 = 机制示意图（write→pool→retrieve→inject→behavior→write 的环，
  标出 λ 加权位置；目前完全缺失，必须新画）+ 环境示意 + 现有 case study 三联图。
  case study 是 motivation，放第一页，不单独成图。
- Figure 2 = 主结果：以 `full_matrix_curves.png` 为底重构，砍到 4 panel
  （成功条件 excess steps、loop、`mas_antmill_rate`、success），
  换新五臂矩阵，带跨 seed CI。Memory size 移补充材料。
- Figure 3 = 机制三联（上述新增证据）。现版 `mechanism_scatter.png`
  （跨条件相关）废弃，不修，不复用。

---

## 九、P6：转向预案 —— 主线跑不出来怎么办

go/no-go 决策点设在 E2+E3 完成时。判决树如下，现在写下来，到时候不许临场改标准：

**情形一：shared 两臂内生退化成立（≥4/5 seeds 配对 CI 不含 0）。**
按原主线走，E4/E6 补长链与外部效度，正常成文。

**情形二：只有 λ 高时退化，λ=0 与 private 无差异。**
这不是失败，这是更精确的论文："退化不是共享经验的固有属性，而是
使用量加权检索强度的函数"。主张收窄为 dose-response，标题与贡献句改写，
机制论文的身份反而更纯粹。我判断这是最可能的结局，而且是可以接受的好结局。

**情形三：λ=1 也不退化，退化只出现在 scripted-injection。**
诚实结论是"内生共享经验相当鲁棒，退化需要外源集中注入"。两条转向路，
优先级如下：

1. **边界分析论文（首选）**："什么时候共享经验有害"。三个有真实部署意义的
   压力变量，逐一测哪个触发内生退化：capacity pressure（library_cap 压到 4-8，
   淘汰与合并自然造成集中，所有真实系统都有容量约束）、任务异质性
   （train 混入不同 family 的迷宫，经验跨情境误迁移）、horizon（T 拉长）。
   B 节列的全部资产——仪表、配对设计、audit——在这条路上一分不损。
2. **mitigation / audit 论文（作为叠加，不作为独立替代）**：provenance-aware
   retrieval、单条经验检索支配度上限、池多样性正则。注意：mitigation 只有在
   "有病可治"时才有意义，所以它只能叠加在情形一/二或边界分析的阳性结果上，
   单独成文的风险是"解一个不存在的问题"。

**任何情形下都不做的事**：为了出效应去调 solver prompt、调 sanitizer 松紧、
挑 seed。所有阈值和判决规则在 E2 启动前写进 prereg 文档
（`prereg_phase_minus1_0.md` 旁边新开一份 `prereg_phase_beta.md`）。

---

## 十、两周启动方案

目标：两周结束时拿到三样东西——统计上站得住的核心矩阵初版、
λ 剂量-反应的第一张图、以及一份写好判决规则的 prereg。

**第 1-2 天（纯工程）**：T0.1 cache 加盐；T0.4 sanitizer 收紧；
T0.3 指标重定义落进 `maze_batch_metrics` 与 audit 输出；T0.5 全局改名。
每项都有离线自测（对旧 run 数据重算指标，确认管线正确）。

**第 3-4 天（忠实化核心）**：T1.1 LLM 操作集 + T1.2 任务条件化检索 +
T1.3 λ 打分。用 9×9 smoke 迷宫各跑一个 5 分钟 sanity run，
确认操作 JSON 可解析率与检索随任务变化。

**第 5 天（写 prereg + 离线分析）**：`prereg_phase_beta.md` 固化 E1-E4 的
条件、样本量、判决规则；同时跑依从性离线分析（现有 trace，零成本），
提前拿到回应"controller 混淆"攻击的弹药。

**第 6-8 天（E1 gate + E2 前三 seed）**：先跑 E1 单智能体校准，过 gate 后
立即铺 E2 的 seeds 0-2。每天检查 partial.json，方向异常立刻停，不烧预算。

**第 9-11 天（E3 λ 扫描）**：E2 方向确认后跑 λ ∈ {0, 0.5, 1} × seeds 0-2。
这三天结束时你应该第一次看到（或看不到）剂量-反应——这是整个项目的
第一个真判决时刻。

**第 12-14 天（统计定稿 + 决策）**：补 E2/E3 的 seeds 3-4（若方向成立）；
出配对 bootstrap 全表与 Figure 2/3 草图；对照第九节判决树写一页
go/no-go 备忘录，决定走主线、收窄为 dose-response，还是启动边界分析预案。

---

## 尾注：三条纪律

1. **没有 gate 的实验不跑。** 每个 run 启动前能说出"它的判决规则是什么、
   失败了下一步是什么"，说不出就不跑。
2. **每个 claim 对应一个可点开的 artifact。** 论文里每句结果陈述，
   都要能指到 `result.json` / CSV / 图的具体位置；做不到的句子删掉。
3. **per-seed 永远展示。** 均值曲线旁边永远放逐 seed 的散点或细线。
   这个项目已经吃过一次"效应由单个 seed 驱动"的亏，不吃第二次。

这个项目值得做完。环境和审计管线是真资产，问题集中在写入内生性与
正反馈实例化两处，都在两周到一个月的射程之内。但从现在起，
它必须按可投稿系统的标准运转，而不是按 pilot 的标准。
