# 变更日志

## 未发布 - Phase Alpha 迷宫策略退化实验

### 新增

- 新增 MazeEval-style 可控迷宫 benchmark，用于研究经验共享多智能体系统中的策略退化现象。
- 新增 trap-family 迷宫生成、最短路径评估、局部观测、撞墙阻止、replay 数据记录和路线可视化支持。
- 新增单智能体与多智能体实验条件：
  - single no-memory baseline
  - single ExpeL-like reviewer-write memory
  - multi-agent no-memory baseline
  - private memory
  - shared reviewer memory
  - shared direct-vote memory
  - shared oracle memory
  - frozen shared memory
- 新增 `state_guided` 迷宫 agent 模式，支持局部状态记忆、已访问状态追踪、已尝试方向追踪、未尝试方向提示、回退候选和重复访问警告。
- 新增经验库审计机制，记录经验来源、检索次数、来源 episode、写入方式、质量元数据和受影响 episode。
- 新增机制分析指标：
  - success rate
  - actual steps
  - shortest-path-normalized cost ratio
  - excess steps
  - invalid move rate
  - loop rate
  - stagnation rate
  - revisit maximum
  - route diversity
  - retrieval concentration
- 新增机制审计与汇总工具，用于分析路线重叠、经验来源、检索集中度和 T=5 崩溃案例。
- 新增论文草稿配图，输出格式包括 PNG、SVG 和 PDF，位于 `paper_draft/figures/`。
- 新增可复现绘图脚本：`paper_draft/redraw_nature_figures.py`。
- 新增中英文 LaTeX 实验章节草稿：
  - `paper_draft/maze_experiment_section.tex`
  - `paper_draft/maze_experiment_section_zh.tex`

### 变更

- 将项目定位从通用 benchmark 评测调整为共享经验反馈循环的机制研究。
- 将核心命题从“错误经验污染”调整为“局部可行策略在共享经验正反馈中发生全局策略退化”。
- 使用可控迷宫家族作为 Phase Alpha 机制实验平台，替代此前更泛化的 benchmark 方向。
- 将主要观测终点从 success collapse 调整为 efficiency collapse、route homogenization 和 silent loop formation。
- 将 QA/math benchmark 移出主实验路径，因为这类任务容易把经验学习混淆为答案缓存。
- 将后续真实任务桥接方向定义为 tool-use 和 browser-style 任务，包括 MiniWoB、browser mini tasks 和 tau-bench-like tool tasks。
- 使用 Nature-style 科研作图流程重画论文配图，提升 panel 结构、字体、图例和机制证据表达。

### 当前实验状态

- 已完成初始单智能体和多智能体迷宫 pilot 实验。
- 已完成 T=5 targeted mechanism runs，用于观察更长反馈链下的行为变化。
- 已生成核心条件下的实验产物，包括 result summaries、memory audits、route atlases、replays 和 mechanism plots。
- 当前初步结果显示：shared active retrieval 可能在 success rate 仍然较高的情况下，提高 cost、降低 route diversity，并增加 repeated-state behavior。
- `stateful_dfs` 保留为 sanity upper-bound controller，不作为主实验 agent。

### 文档

- 新增或更新项目设计文档：
  - `maze_strategy_degradation_blueprint.md`
  - `experiment_architecture.md`
  - `prereg_phase_minus1_0.md`
  - `death_spiral_analogy.md`
- 新增论文草稿实验章节，覆盖以下内容：
  - benchmark motivation
  - single-agent ExpeL calibration
  - multi-agent memory conditions
  - frozen-memory control
  - reviewer-write 与 direct-vote write modes
  - mechanism metrics
  - real-task bridge plan

### 验证

- 已运行离线迷宫自测。
- 已运行 agentic/selftest 相关检查。
- 已使用 XeLaTeX 编译英文和中文 LaTeX 草稿。
- 已渲染编译后的 PDF 页面进行视觉检查。
- 已检查生成图在论文草稿中的版式、可读性、panel 间距和嵌入 PDF 后的显示效果。

### 后续工作

- 审查当前实验设计是否能够支撑核心主线，重点评估 shared memory、reviewer-write、direct-vote 和 frozen memory 等条件是否足够证明主流经验共享机制中的正反馈问题。
- 扩展 Phase Alpha 实验规模，覆盖更多 seeds、更大的 `T` 和更大的 heldout set，以获得更稳定的统计显著性。
- 稳定统计报告，包括 cost ratio、excess steps、loop rate、route diversity 和 retrieval concentration。
- 审计经验库条目，确保经验仍是抽象策略总结，而不是具体坐标、完整路线、固定动作序列或 maze id 缓存。
- 加强 private memory、shared memory、frozen memory、reviewer-write、oracle-write 和 direct-vote-write 条件之间的对比。
- 改进机制图和论文叙事，将当前结果进一步整理为正式论文中的 Figure 1、Figure 2 和 Figure 3 候选。
- 准备真实任务桥接，在迷宫机制证据稳定后优先接入 tool-use 或 browser-style benchmark，例如 MiniWoB、browser mini tasks 和 tau-bench-like tool tasks。
- 暂不优先接入 SWE-bench、QA 或 math benchmark，避免实验过早转向重型软件工程任务，或将经验学习混淆为答案缓存。
