from __future__ import annotations

from .config import Config
from .fusion import _filter_reusable_insights
from .metrics import accuracy_consensus, detect_collapse, majority_cluster, normalize_answer, parse_final_answer


def main() -> None:
    assert normalize_answer("The, Quick!") == "quick"
    assert parse_final_answer("Reasoning.\nFinal answer: The Eiffel Tower") == "The Eiffel Tower"
    maj = majority_cluster(["Final answer: A", "Final answer: B", "Final answer: B", "Final answer: A"])
    assert maj["answer"] == "A"
    metrics = accuracy_consensus(
        [
            {"gold": "A", "answers": ["Final answer: A", "Final answer: B"]},
            {"gold": "C", "answers": ["Final answer: D", "Final answer: D"]},
        ]
    )
    assert metrics["A_t"] == 0.5
    assert metrics["C_t"] == 0.75
    assert detect_collapse([0.2, 0.35, 0.5, 0.38, 0.37, 0.36], delta=0.1, k_persist=2, rho_minrise=0.05) == 3
    assert detect_collapse([0.2, 0.3, 0.4, 0.5], delta=0.1, k_persist=2, rho_minrise=0.05) is None
    cfg = Config(batch_M=2, T=3, n_train=6)
    assert cfg.n_train == 6
    clusters = [{"answer": "Edward of Angouleme", "norm": "edward of angouleme", "indices": [0], "trajectories": []}]
    bad = [{"kind": "do", "text": "Prefer evidence-linked reasoning before answering Edward of Angouleme."}]
    good = [{"kind": "do", "text": "Ground the answer in explicit evidence from the provided context."}]
    assert _filter_reusable_insights(bad, "Who was Edward of Angouleme?", clusters) == []
    assert _filter_reusable_insights(good, "Who was Edward of Angouleme?", clusters) == good
    print("selftest OK")


if __name__ == "__main__":
    main()
