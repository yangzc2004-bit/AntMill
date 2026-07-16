from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Config:
    model: str = "deepseek-v4-flash"
    base_url: str = "https://api.deepseek.com/v1"
    api_key_env: str = "DEEPSEEK_API_KEY"

    embed_model: str = "hashing"
    n_solvers: int = 4
    use_ground_truth: bool = False
    mu: float = 0.65
    similarity_threshold: float = 0.80
    use_context: bool = True
    max_context_chars: int = 12000

    batch_M: int = 20
    n_train: int | None = None
    heldout_size: int = 50
    T: int = 25
    seed: int = 0
    solver_temp: float = 0.8
    reviewer_temp: float = 0.2
    library_cap: int = 60

    # --- v2 (SEC) knobs; defaults preserve the original single-pass behavior ---
    # NOTE: with debate_rounds=1 agents never see peer proposals; multi-agent arms
    # are then "independent solvers with shared experiential memory", not debate.
    debate_rounds: int = 1  # R; 1 = no debate (single-pass); >=2 enables peer-visible revision
    retrieval_k: int = 0  # 0 = inject whole library (legacy); >0 = ExpeL-style top-k retrieval
    memory_mode: str = "shared"  # none | private | shared | frozen
    anchor_rho: float = -1.0  # prob a train batch is labeled by gold; -1 = derive from use_ground_truth
    dataset: str = "hotpotqa"  # hotpotqa | gsm8k | math | musique | 2wikimultihop | tau_bench | swe_bench
    # --- agentic (multi-step) knobs; only used by the agentic episode runner ---
    max_steps: int = 10  # per-episode step cap; hitting it without done = non-termination
    loop_window: int = 3  # window for silent action-repetition (death-loop) detection
    maze_width: int = 9
    maze_height: int = 9
    maze_family: str = "trap"
    maze_agent_mode: str = "prompt_only"  # prompt_only | state_guided | stateful_dfs | oracle_dfs
    maze_min_shortest: int = 0
    maze_max_shortest: int = 0
    # reviewer | scripted | scripted_gated | self_eval | none.
    # "scripted" / "scripted_gated" inject fixed researcher-written strategy templates
    # (upper-bound injection controls, NOT learned experience). Legacy names
    # "direct" / "oracle" are accepted and canonicalized in __post_init__.
    maze_write_mode: str = "reviewer"
    maze_eval_feedback: bool = False  # expose success/cost summaries to the reviewer, never to solvers
    skip_final_train: bool = False  # skip train/write after the final evaluation round

    # --- P1/P2 experiential-memory design points (ExpeL / Generative-Agents faithful) ---
    # distill   = contrastive distill + code-side similarity merge (legacy P0 behavior)
    # expel_ops = LLM-issued ADD/EDIT/UPVOTE/DOWNVOTE over the visible pool (ExpeL-faithful,
    #             mode B: LLM consolidation)
    # append    = per-agent reflections appended without consolidation (mode A: append+retrieve,
    #             Generative-Agents style); independent re-derivation of a similar lesson counts
    #             as agreement and upvotes the existing item
    memory_write_protocol: str = "distill"
    append_dedup: bool = True
    tie_rule: str = "reverse_lexical"
    # similarity = lexical top-k against the query (legacy)
    # ga         = min-max normalized relevance + ga_lambda*importance + ga_recency*recency
    #              (Generative-Agents-style scoring; importance = consensus votes)
    # ga_mmr     = GA ranking with greedy maximum-marginal-relevance reranking, retaining
    #              lexical/semantic diversity among the injected top-k items
    retrieval_scoring: str = "similarity"
    ga_lambda: float = 1.0  # importance weight; the positive-feedback strength dial
    ga_recency: float = 0.0  # recency weight (Generative-Agents faithful = 1.0)
    mmr_relevance_weight: float = 0.70  # 1 = pure GA relevance; lower favors diversity
    max_reviewer_ops: int = 6
    # standard           = retrieve from the live active pool only
    # archive_rescue     = legacy additive active top-k plus archive top-k
    # archive_joint_topk = jointly rank live and archived candidates under one total top-k
    # budgeted_append    = append writes stay unchanged, but solver reads are limited to a persistent yoked whitelist
    memory_read_protocol: str = "standard"
    archive_retrieval_k: int = 6
    budget_schedule_name: str = ""

    concurrency: int = 8
    rate_limit_per_min: float = 0.0
    cache_policy: str = "read_write"  # read_write | off
    cache_dir: str = "./cache"
    out_dir: str = "./runs"

    max_tokens_solver: int = 384
    max_tokens_reviewer: int = 512
    max_tokens_self_eval: int = 160
    max_retries: int = 6
    request_timeout_sec: float = 45.0
    disable_thinking: bool = False
    llm_extra_body: dict[str, Any] = field(default_factory=dict)

    delta: float = 0.10
    k_persist: int = 5
    rho_minrise: float = 0.05

    run_id: str = ""
    notes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.n_train is None:
            self.n_train = self.batch_M * self.T
        if self.n_train < self.batch_M * self.T:
            raise ValueError("n_train must be >= batch_M * T for global sampling without replacement.")
        if self.anchor_rho < 0.0:
            self.anchor_rho = 1.0 if self.use_ground_truth else 0.0
        if not 0.0 <= self.anchor_rho <= 1.0:
            raise ValueError("anchor_rho must be in [0, 1].")
        if self.memory_mode not in {"none", "private", "shared", "frozen"}:
            raise ValueError(f"invalid memory_mode: {self.memory_mode!r}")
        if self.dataset not in {
            "hotpotqa", "gsm8k", "math", "musique", "2wikimultihop",
            "tau_bench", "tau2_bench", "swe_bench", "miniwob"
        }:
            raise ValueError(f"invalid dataset: {self.dataset!r}")
        if self.debate_rounds < 1:
            raise ValueError("debate_rounds must be >= 1.")
        if self.maze_width < 5 or self.maze_height < 5:
            raise ValueError("maze_width and maze_height must be >= 5.")
        if self.maze_width % 2 == 0 or self.maze_height % 2 == 0:
            raise ValueError("maze_width and maze_height must be odd for the built-in maze generator.")
        if self.maze_agent_mode not in {"prompt_only", "state_guided", "stateful_dfs", "oracle_dfs"}:
            raise ValueError(f"invalid maze_agent_mode: {self.maze_agent_mode!r}")
        if self.maze_min_shortest < 0 or self.maze_max_shortest < 0:
            raise ValueError("maze_min_shortest and maze_max_shortest must be non-negative.")
        if self.maze_max_shortest and self.maze_max_shortest < self.maze_min_shortest:
            raise ValueError("maze_max_shortest must be >= maze_min_shortest when set.")
        if self.memory_write_protocol not in {"distill", "expel_ops", "append"}:
            raise ValueError(f"invalid memory_write_protocol: {self.memory_write_protocol!r}")
        if self.tie_rule not in {"reverse_lexical", "oldest_evicted_recency_retaining"}:
            raise ValueError(f"invalid tie_rule: {self.tie_rule!r}")
        if self.retrieval_scoring not in {"similarity", "ga", "ga_mmr"}:
            raise ValueError(f"invalid retrieval_scoring: {self.retrieval_scoring!r}")
        if self.ga_lambda < 0.0 or self.ga_recency < 0.0:
            raise ValueError("ga_lambda and ga_recency must be non-negative.")
        if not 0.0 <= self.mmr_relevance_weight <= 1.0:
            raise ValueError("mmr_relevance_weight must be in [0, 1].")
        if not 1 <= self.max_reviewer_ops <= 12:
            raise ValueError("max_reviewer_ops must be in [1, 12].")
        if self.memory_read_protocol not in {
            "standard", "archive_rescue", "archive_joint_topk", "budgeted_append"
        }:
            raise ValueError(f"invalid memory_read_protocol: {self.memory_read_protocol!r}")
        if self.archive_retrieval_k < 0:
            raise ValueError("archive_retrieval_k must be non-negative.")
        if self.budget_schedule_name and self.budget_schedule_name != "gamma_consolidated_active_cummax":
            raise ValueError(f"invalid budget_schedule_name: {self.budget_schedule_name!r}")
        if self.cache_policy not in {"read_write", "off"}:
            raise ValueError(f"invalid cache_policy: {self.cache_policy!r}")
        if not isinstance(self.llm_extra_body, dict):
            raise ValueError("llm_extra_body must be a dictionary.")
        legacy_write_modes = {"direct": "scripted", "oracle": "scripted_gated"}
        if self.maze_write_mode in legacy_write_modes:
            canonical = legacy_write_modes[self.maze_write_mode]
            self.notes.append(f"maze_write_mode {self.maze_write_mode!r} is deprecated; canonicalized to {canonical!r}")
            self.maze_write_mode = canonical
        if self.maze_write_mode not in {"reviewer", "scripted", "scripted_gated", "self_eval", "none"}:
            raise ValueError(f"invalid maze_write_mode: {self.maze_write_mode!r}")

    def cache_path(self) -> Path:
        return Path(self.cache_dir)

    def output_path(self) -> Path:
        return Path(self.out_dir)

    def to_public_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["api_key_env"] = self.api_key_env
        return data


def condition_name(cfg: Config) -> str:
    gt = "gt_true" if cfg.use_ground_truth else "gt_false"
    suffix = f"_{cfg.run_id}" if cfg.run_id else ""
    return f"n{cfg.n_solvers}_{gt}_seed{cfg.seed}{suffix}"


def mini_config(**overrides: Any) -> Config:
    params: dict[str, Any] = {
        "T": 3,
        "batch_M": 5,
        "heldout_size": 20,
        "n_train": 15,
        "n_solvers": 1,
        "use_ground_truth": False,
        "run_id": "mini",
    }
    params.update(overrides)
    return Config(**params)
