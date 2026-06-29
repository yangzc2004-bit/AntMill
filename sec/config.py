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
    library_cap: int = 60

    # --- v2 (SEC / MAD) knobs; defaults preserve the original single-pass behavior ---
    debate_rounds: int = 1  # R; 1 = no debate (faithful single-pass), MAD arms set 3
    retrieval_k: int = 0  # 0 = inject whole library (legacy); >0 = ExpeL-style top-k retrieval
    memory_mode: str = "shared"  # none | private | shared | frozen
    anchor_rho: float = -1.0  # prob a train batch is labeled by gold; -1 = derive from use_ground_truth
    dataset: str = "hotpotqa"  # hotpotqa | gsm8k | math | musique | 2wikimultihop | tau_bench | swe_bench
    # --- agentic (multi-step) knobs; only used by the agentic episode runner ---
    max_steps: int = 10  # per-episode step cap; hitting it without done = non-termination
    loop_window: int = 3  # window for silent action-repetition (death-loop) detection

    concurrency: int = 8
    rate_limit_per_min: float = 0.0
    cache_dir: str = "./cache"
    out_dir: str = "./runs"

    max_tokens_solver: int = 384
    max_tokens_reviewer: int = 512
    max_tokens_self_eval: int = 160
    max_retries: int = 6
    request_timeout_sec: float = 45.0

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
            "hotpotqa", "gsm8k", "math", "musique", "2wikimultihop", "tau_bench", "swe_bench"
        }:
            raise ValueError(f"invalid dataset: {self.dataset!r}")
        if self.debate_rounds < 1:
            raise ValueError("debate_rounds must be >= 1.")

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
