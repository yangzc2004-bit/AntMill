from __future__ import annotations

import asyncio
import os
import re

os.environ.setdefault("SEC_MOCK_KEY", "x")

from .config import Config
from .llm import LLMClient
from .memory import InsightMemory
from .metrics import answer_entropy, answer_match, joint_collapse, numeric_match
from .loop_v2 import run_one_v2


async def _mock_chat(self, messages, *, temp=0.0, model=None, max_tokens=None, tag=""):
    user = messages[-1]["content"]
    if tag == "reviewer":
        return (
            '[{"kind":"do","text":"Compare all candidate dates before committing to an answer."},'
            '{"kind":"avoid","text":"Do not commit before checking the provided evidence carefully."}]'
        )
    if tag == "self_eval":
        return '{"success": true, "confidence": 0.7, "reason": "consistent"}'
    match = re.search(r"SOLVER AGENT ID:\s*(\d+)", user)
    agent = int(match.group(1)) if match else 0
    qmatch = re.search(r"QUESTION:\n(.+)", user)
    question = qmatch.group(1).strip() if qmatch else ""
    option = "alpha" if (hash(question) + agent) % 2 == 0 else "beta"
    return f"Reasoning about {question[:12]}.\nFinal answer: {option}"


def _rows(prefix: str, n: int) -> list[dict[str, str]]:
    return [{"question": f"{prefix}_q{i}", "answer": "alpha", "context": ""} for i in range(n)]


def _base_cfg(**overrides):
    params = dict(
        api_key_env="SEC_MOCK_KEY",
        n_solvers=3,
        debate_rounds=2,
        retrieval_k=6,
        library_cap=50,
        max_tokens_solver=64,
        max_tokens_reviewer=64,
        max_tokens_self_eval=64,
        T=3,
        batch_M=2,
        n_train=6,
        heldout_size=4,
        cache_dir="./.sec_mock_cache",
        out_dir="./.sec_mock_runs",
    )
    params.update(overrides)
    return Config(**params)


def _pure_logic_checks() -> None:
    assert answer_entropy(["Final answer: a"] * 3) == 0.0
    assert abs(answer_entropy(["Final answer: a", "Final answer: b"]) - 1.0) < 1e-9
    assert 0.0 < answer_entropy(["Final answer: a", "Final answer: a", "Final answer: b"]) < 1.0

    # numeric / dataset-aware answer matching (GSM8K/MATH)
    assert numeric_match("Final answer: 42", "42")
    assert numeric_match("the total is $1,000", "1000")
    assert numeric_match("72.0", "72")
    assert not numeric_match("41", "42")
    assert answer_match("42", "42", "gsm8k")
    assert not answer_match("41", "42", "gsm8k")
    assert answer_match("Paris", "paris", "hotpotqa")  # exact-match path unchanged

    # anchor_rho derivation from use_ground_truth
    assert _base_cfg(use_ground_truth=True, memory_mode="shared", anchor_rho=-1.0).anchor_rho == 1.0
    assert _base_cfg(memory_mode="shared").anchor_rho == 0.0

    # memory routing / retrieval
    cfg = _base_cfg(memory_mode="shared", retrieval_k=2)
    mem = InsightMemory(cfg)
    distinct = [
        "verify both entities in comparison questions",
        "extract dates for chronology before responding",
        "ground claims in explicit provided evidence",
        "decompose multi hop queries into atomic steps",
        "double check capitalization of named tokens",
    ]
    for text in distinct:
        mem.apply_insight(0, {"kind": "do", "text": text}, support_count=3)
    assert mem.size() == 5, mem.size()  # lexically distinct -> no merge
    got = mem.retrieve(1, "compare two entities in a comparison question")
    assert len(got) == 2  # top-k honored, shared pool visible to any agent

    none_mem = InsightMemory(_base_cfg(memory_mode="none"))
    none_mem.apply_insight(0, {"kind": "do", "text": "ignored"}, support_count=3)
    assert none_mem.size() == 0 and none_mem.retrieve(0, "x") == []

    frozen = InsightMemory(_base_cfg(memory_mode="frozen"))
    frozen.apply_insight(0, {"kind": "do", "text": "accumulated but not injected aaaa"}, support_count=3)
    assert frozen.size() == 1 and frozen.retrieve(0, "accumulated") == []  # accumulates, never injects

    # joint collapse: rose then sustained drop, high consensus, halved diversity
    a = [0.3, 0.5, 0.7, 0.55, 0.54, 0.53, 0.52, 0.51]
    c = [0.6, 0.7, 0.75, 0.85, 0.86, 0.87, 0.88, 0.89]
    d = [0.8, 0.6, 0.4, 0.2, 0.18, 0.16, 0.15, 0.14]
    jc = joint_collapse(a, c, d, delta=0.10, k_persist=3, c_high=0.75, d_low_factor=0.5)
    assert jc["t_star"] == 3 and jc["collapsed_within_run"] is True
    print("pure-logic checks OK")


async def _pipeline_checks() -> None:
    original = LLMClient.chat
    LLMClient.chat = _mock_chat  # type: ignore[assignment]
    try:
        shared = await run_one_v2(_base_cfg(memory_mode="shared", anchor_rho=0.0), _rows("tr", 6), _rows("ho", 4))
        assert len(shared["log"]) == 3
        assert all("D_t" in row and "A_t" in row and "C_t" in row for row in shared["log"])
        assert shared["memory"]["size"] >= 1  # shared memory accumulated insights
        assert "collapse" in shared["summary"]

        nomem = await run_one_v2(_base_cfg(memory_mode="none"), _rows("tr", 6), _rows("ho", 4))
        assert nomem["memory"]["size"] == 0  # no memory ever written

        private = await run_one_v2(_base_cfg(memory_mode="private", anchor_rho=0.0), _rows("tr", 6), _rows("ho", 4))
        assert private["memory"]["size"] >= 1  # per-agent pools populated via self-reflection

        anchored = await run_one_v2(_base_cfg(memory_mode="shared", anchor_rho=1.0), _rows("tr", 6), _rows("ho", 4))
        assert len(anchored["log"]) == 3
    finally:
        LLMClient.chat = original  # type: ignore[assignment]
    print("pipeline checks OK")


def main() -> None:
    _pure_logic_checks()
    asyncio.run(_pipeline_checks())
    print("selftest_v2 OK")


if __name__ == "__main__":
    main()
