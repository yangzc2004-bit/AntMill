# Reproducibility Checklist Evidence

Status: **checklist_provisional**
Questions: **31**

| question | answer | evidence |
|---|---|---|
| Includes a conceptual outline and/or pseudocode description of AI methods introduced | yes | Figure 1a and the Methods section define the write, retrieve, inject, and evaluate loop. |
| Clearly delineates statements that are opinions, hypothesis, and speculation from objective facts and results | yes | Preregistered gates, exploratory analyses, candidate mechanisms, and limitations are labeled separately. |
| Provides well-marked pedagogical references for less-familiar readers to gain background necessary to replicate the paper | yes | Related Work and Table 1 connect each memory operation and retrieval component to its source family. |
| Does this paper make theoretical contributions? | no | The contribution is empirical and methodological rather than theorem-based. |
| All assumptions and restrictions are stated clearly and formally | yes | The controlled protocol, scope restrictions, operational endpoints, and claim boundaries are explicit. |
| All novel claims are stated formally (e.g., in theorem statements) | no | The paper makes empirical claims and no theorem claims. |
| Proofs of all novel claims are included | no | No theoretical proof claims are made. |
| Proof sketches or intuitions are given for complex and/or novel results | no | No theoretical proof result requires a proof sketch. |
| Appropriate citations to theoretical tools used are given | partial | Statistical procedures are fully specified in the artifact; the paper does not rely on a novel theoretical tool. |
| All theoretical claims are demonstrated empirically to hold | NA | The paper makes no theoretical claims. |
| All experimental code used to eliminate or disprove claims is included | yes | The anonymized artifact includes runners, controls, sensitivity analyses, decision gates, and negative-result code. |
| Does this paper rely on one or more datasets? | yes | The study uses generated trap-maze instances and public MiniWoB task families. |
| A motivation is given for why the experiments are conducted on the selected datasets | yes | The maze provides exact route ground truth; MiniWoB provides a controlled browser-interaction boundary. |
| All novel datasets introduced in this paper are included in a data appendix | yes | Generated instances, split seeds, per-route records, and task manifests are included in the artifact. |
| All novel datasets introduced in this paper will be made publicly available upon publication of the paper with a license that allows free usage for research purposes | partial | The artifact is prepared for release; the final repository license remains to be selected by the authors. |
| All datasets drawn from the existing literature (potentially including authors' own previously published work) are accompanied by appropriate citations | yes | MiniWoB is cited through World of Bits and its BrowserGym execution layer. |
| All datasets drawn from the existing literature (potentially including authors' own previously published work) are publicly available | yes | MiniWoB and BrowserGym are publicly available. |
| All datasets that are not publicly available are described in detail, with explanation why publicly available alternatives are not scientifically satisficing | NA | No external non-public dataset is used. |
| Does this paper include computational experiments? | yes | The paper reports preregistered maze and browser-agent experiments. |
| This paper states the number and range of values tried per (hyper-) parameter during development of the paper, along with the criterion used for selecting the final parameter setting | partial | Frozen configurations and the prespecified sensitivity ranges are reported; some early calibration details remain artifact-only. |
| Any code required for pre-processing data is included in the appendix | yes | Maze generation, BrowserGym observation normalization, sanitization, and analysis code are included. |
| All source code required for conducting and analyzing the experiments is included in a code appendix | yes | The artifact includes experiment runners, memory protocols, statistics, evidence gates, and manuscript generators. |
| All source code required for conducting and analyzing the experiments will be made publicly available upon publication of the paper with a license that allows free usage for research purposes | partial | The code is release-ready; the final public repository license remains to be selected by the authors. |
| All source code implementing new methods have comments detailing the implementation, with references to the paper where each step comes from | partial | Non-obvious operations are documented and provenance is recorded, but not every implementation line has a paper cross-reference. |
| If an algorithm depends on randomness, then the method used for setting seeds is described in a way sufficient to allow replication of results | yes | Seed lists, deterministic task salts, split generation, and per-run manifests are frozen; the evidence gate validates every completed formal configuration and sibling manifest. |
| This paper specifies the computing infrastructure used for running experiments (hardware and software), including GPU/CPU models; amount of memory; operating system; names and versions of relevant software libraries and frameworks | partial | Local OS, CPU, memory, Python, BrowserGym, Playwright, the pinned MiniWoB++ commit, immutable browser version, executable and runtime-tree SHA-256 hashes, registered-task count, and package versions are recorded from formal run manifests; hosted LLM provider hardware is not disclosed. |
| This paper formally describes evaluation metrics used and explains the motivation for choosing these metrics | yes | Success, failure-penalized cost, loop, stagnation, and retrieval-diversity metrics are operationally defined. |
| This paper states the number of algorithm runs used to compute each reported result | yes | Seeds, route pairs, task families, rounds, and run counts accompany each result table and caption. |
| Analysis of experiments goes beyond single-dimensional summaries of performance (e.g., average; median) to include measures of variation, confidence, or other distributional information | yes | Hierarchical seed-clustered paired-bootstrap intervals, every per-seed effect, sign consistency, and MiniWoB task-family heterogeneity are reported. |
| The significance of any improvement or decrease in performance is judged using appropriate statistical tests (e.g., Wilcoxon signed-rank) | yes | Prespecified seed-clustered paired bootstrap confidence intervals and manipulation gates determine detected effects. |
| This paper lists all final (hyper-)parameters used for each model/algorithm in the paper's experiments | yes | Frozen configs, prompts, model settings, sensitivity values, and run manifests are included; supplement data-quality tables report all-run configuration, sibling-manifest, and exact cross-run environment validation. |
