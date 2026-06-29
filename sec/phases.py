from __future__ import annotations

from typing import Any

from .config import Config


# Faithful defaults shared by all Phase -1/0 arms (see prereg_phase_minus1_0.md, section 0).
FAITHFUL: dict[str, Any] = {
    "use_context": True,
    "max_context_chars": 12000,
    "max_tokens_solver": 1024,
    "max_tokens_reviewer": 1024,
    "max_tokens_self_eval": 512,
    "solver_temp": 0.7,  # same temperature across debate rounds; no late-round cooling
    "retrieval_k": 6,
    "library_cap": 200,
    "delta": 0.10,
    "k_persist": 5,
}


# Per-arm overrides. Model / endpoint / seed / dirs are supplied at run time by the user.
ARMS: dict[str, list[dict[str, Any]]] = {
    "A0": [
        {"run_id": "A0_single", "n_solvers": 1, "debate_rounds": 1, "memory_mode": "none",
         "T": 1, "batch_M": 0, "n_train": 0, "heldout_size": 200},
        {"run_id": "A0_mad", "n_solvers": 4, "debate_rounds": 3, "memory_mode": "none",
         "T": 1, "batch_M": 0, "n_train": 0, "heldout_size": 200},
    ],
    "A1": [
        {"run_id": "A1_mem", "n_solvers": 4, "debate_rounds": 3, "memory_mode": "shared",
         "anchor_rho": 1.0, "T": 5, "batch_M": 15, "n_train": 75, "heldout_size": 150},
        {"run_id": "A1_nomem", "n_solvers": 4, "debate_rounds": 3, "memory_mode": "none",
         "T": 5, "batch_M": 15, "n_train": 75, "heldout_size": 150},
    ],
    "P0": [
        {"run_id": "P0_collapse", "n_solvers": 4, "debate_rounds": 3, "memory_mode": "shared",
         "anchor_rho": 0.0, "T": 20, "batch_M": 15, "n_train": 300, "heldout_size": 100},
        {"run_id": "P0_nomem", "n_solvers": 4, "debate_rounds": 3, "memory_mode": "none",
         "T": 20, "batch_M": 15, "n_train": 300, "heldout_size": 100},
        {"run_id": "P0_anchor", "n_solvers": 4, "debate_rounds": 3, "memory_mode": "shared",
         "anchor_rho": 1.0, "T": 20, "batch_M": 15, "n_train": 300, "heldout_size": 100},
    ],
}


def build_phase(phase: str, common: dict[str, Any], seeds: list[int], **overrides: Any) -> list[Config]:
    """Build the Config list for a phase across seeds. ``common`` supplies model/endpoint/dirs."""
    if phase not in ARMS:
        raise ValueError(f"unknown phase {phase!r}; choose from {sorted(ARMS)}")
    configs: list[Config] = []
    for seed in seeds:
        for arm in ARMS[phase]:
            params: dict[str, Any] = {**FAITHFUL, **common, **arm, "seed": seed}
            params.update(overrides)
            # keep the global no-replacement invariant satisfied after any override
            if params.get("batch_M") and int(params.get("n_train") or 0) < params["batch_M"] * params["T"]:
                params["n_train"] = params["batch_M"] * params["T"]
            configs.append(Config(**params))
    return configs
