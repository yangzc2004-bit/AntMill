from __future__ import annotations

import math
import re
import string
from collections import defaultdict
from difflib import SequenceMatcher
from typing import Any

import numpy as np


_ARTICLES = re.compile(r"\b(a|an|the)\b", flags=re.IGNORECASE)
_FINAL_RE = re.compile(r"final\s*answer\s*:\s*(.+)", flags=re.IGNORECASE | re.DOTALL)


def normalize_answer(text: str) -> str:
    text = str(text).lower()
    text = "".join(ch for ch in text if ch not in set(string.punctuation))
    text = _ARTICLES.sub(" ", text)
    return " ".join(text.split())


def parse_final_answer(text: str) -> str:
    match = _FINAL_RE.search(str(text))
    if match:
        ans = match.group(1).strip()
        split = ans.splitlines()
        return split[0].strip() if split else ""
    lines = [line.strip() for line in str(text).splitlines() if line.strip()]
    return lines[-1] if lines else ""


def cluster_by_normalized_answer(answers: list[str]) -> list[dict[str, Any]]:
    clusters_by_norm: dict[str, dict[str, Any]] = {}
    ordered: list[dict[str, Any]] = []
    for idx, raw in enumerate(answers):
        final = parse_final_answer(raw)
        norm = normalize_answer(final)
        if norm not in clusters_by_norm:
            cluster = {"norm": norm, "answer": final, "indices": [], "trajectories": []}
            clusters_by_norm[norm] = cluster
            ordered.append(cluster)
        clusters_by_norm[norm]["indices"].append(idx)
        clusters_by_norm[norm]["trajectories"].append(raw)
    return ordered


def majority_cluster(answers: list[str]) -> dict[str, Any]:
    clusters = cluster_by_normalized_answer(answers)
    if not clusters:
        return {"norm": "", "answer": "", "indices": [], "trajectories": []}
    return max(clusters, key=lambda c: (len(c["indices"]), -c["indices"][0]))


def exact_match(prediction: str, gold: str) -> bool:
    return normalize_answer(prediction) == normalize_answer(gold)


_NUM_RE = re.compile(r"-?\$?\d[\d,]*\.?\d*%?")


def extract_number(text: str) -> float | None:
    """Last number-like token in `text`, tolerant of $, commas, and trailing %."""
    cands = _NUM_RE.findall(str(text))
    if not cands:
        return None
    token = cands[-1].replace("$", "").replace(",", "").rstrip("%")
    try:
        return float(token)
    except ValueError:
        return None


def numeric_match(prediction: str, gold: str) -> bool:
    """Numeric equality (GSM8K/MATH); falls back to normalized string match."""
    gp = extract_number(gold)
    pp = extract_number(prediction)
    if gp is None or pp is None:
        return normalize_answer(prediction) == normalize_answer(gold)
    return abs(gp - pp) < 1e-6


_NUMERIC_DATASETS = {"gsm8k", "math"}


def answer_match(prediction: str, gold: str, dataset: str = "hotpotqa") -> bool:
    """Dataset-aware answer matching: numeric for math, exact-match otherwise."""
    if dataset in _NUMERIC_DATASETS:
        return numeric_match(prediction, gold)
    return exact_match(prediction, gold)


def answer_entropy(answers: list[str]) -> float:
    """Normalized Shannon entropy over normalized-final-answer clusters; in [0, 1]."""
    n = len(answers)
    if n <= 1:
        return 0.0
    clusters = cluster_by_normalized_answer(answers)
    entropy = 0.0
    for cluster in clusters:
        p = len(cluster["indices"]) / n
        if p > 0:
            entropy -= p * math.log(p)
    return float(entropy / math.log(n))


def eval_metrics(items: list[dict[str, Any]], dataset: str = "hotpotqa") -> dict[str, float]:
    """Accuracy / consensus / gap plus the headline diversity D_t."""
    base = accuracy_consensus(items, dataset)
    if not items:
        base["D_t"] = 0.0
        return base
    base["D_t"] = float(np.mean([answer_entropy(item["answers"]) for item in items]))
    return base


def joint_collapse(
    a_list: list[float],
    c_list: list[float],
    d_list: list[float],
    *,
    delta: float = 0.10,
    k_persist: int = 5,
    c_high: float = 0.75,
    d_low_factor: float = 0.5,
) -> dict[str, Any]:
    """Per-run part of the pre-registered joint collapse test.

    Conditions (1)-(3): accuracy drop from running max sustained k rounds, high consensus, and
    diversity at least halved from round 0 over that window. Condition (4) (below the no-memory
    baseline) is a cross-arm check done at analysis time.
    """
    t_star = detect_collapse(a_list, delta=delta, k_persist=k_persist, rho_minrise=0.0)
    result: dict[str, Any] = {
        "t_star": t_star,
        "cond_accuracy_drop": t_star is not None,
        "cond_high_consensus": False,
        "cond_diversity_collapse": False,
        "collapsed_within_run": False,
    }
    if t_star is None:
        return result
    end = min(t_star + k_persist, len(a_list))
    c_window = c_list[t_star:end]
    d_window = d_list[t_star:end]
    c_mean = float(np.mean(c_window)) if c_window else 0.0
    d_mean = float(np.mean(d_window)) if d_window else 0.0
    d0 = d_list[0] if d_list else 0.0
    result["c_window_mean"] = c_mean
    result["d_window_mean"] = d_mean
    result["d0"] = d0
    result["cond_high_consensus"] = c_mean >= c_high
    result["cond_diversity_collapse"] = d0 > 0 and d_mean <= d_low_factor * d0
    result["collapsed_within_run"] = (
        result["cond_accuracy_drop"]
        and result["cond_high_consensus"]
        and result["cond_diversity_collapse"]
    )
    return result


def accuracy_consensus(items: list[dict[str, Any]], dataset: str = "hotpotqa") -> dict[str, float]:
    if not items:
        return {"A_t": 0.0, "C_t": 0.0, "G_t": 0.0}
    correct = []
    consensus = []
    for item in items:
        answers = item["answers"]
        majority = majority_cluster(answers)
        correct.append(1.0 if answer_match(majority["answer"], item["gold"], dataset) else 0.0)
        consensus.append(len(majority["indices"]) / max(len(answers), 1))
    a_t = float(np.mean(correct))
    c_t = float(np.mean(consensus))
    return {"A_t": a_t, "C_t": c_t, "G_t": c_t - a_t}


def similarity(a: str, b: str) -> float:
    na = normalize_answer(a)
    nb = normalize_answer(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    sa = set(na.split())
    sb = set(nb.split())
    jaccard = len(sa & sb) / max(len(sa | sb), 1)
    seq = SequenceMatcher(None, na, nb).ratio()
    return max(jaccard, seq)


def hashing_embedding(text: str, dim: int = 128) -> np.ndarray:
    vec = np.zeros(dim, dtype=float)
    for tok in normalize_answer(text).split():
        idx = hash(tok) % dim
        vec[idx] += 1.0
    norm = np.linalg.norm(vec)
    return vec / norm if norm else vec


def eff_rank(library: list[dict[str, Any]]) -> float:
    if len(library) < 2:
        return float(len(library))
    matrix = np.vstack([hashing_embedding(item.get("text", "")) for item in library])
    singular = np.linalg.svd(matrix, compute_uv=False)
    denom = float(np.sum(singular**2))
    if denom <= 0:
        return 0.0
    return float((np.sum(singular) ** 2) / denom)


def detect_collapse(
    a_list: list[float],
    *,
    delta: float = 0.10,
    k_persist: int = 5,
    rho_minrise: float = 0.05,
) -> int | None:
    if not a_list or max(a_list) - a_list[0] < rho_minrise:
        return None
    running_max = -math.inf
    for idx, value in enumerate(a_list):
        running_max = max(running_max, value)
        if value <= running_max - delta:
            end = idx + k_persist
            if end <= len(a_list) and all(v <= running_max - delta for v in a_list[idx:end]):
                return idx
    return None


def ews(series: list[float]) -> dict[str, Any]:
    try:
        values = np.asarray(series, dtype=float)
        if len(values) < 4:
            return {"error": "series too short"}
        window = max(3, len(values) // 3)
        rolling_var: list[float] = []
        rolling_ac1: list[float] = []
        for start in range(0, len(values) - window + 1):
            chunk = values[start : start + window]
            detrended = chunk - np.mean(chunk)
            rolling_var.append(float(np.var(detrended)))
            if len(chunk) > 1 and np.std(detrended[:-1]) > 0 and np.std(detrended[1:]) > 0:
                rolling_ac1.append(float(np.corrcoef(detrended[:-1], detrended[1:])[0, 1]))
            else:
                rolling_ac1.append(0.0)
        return {
            "window": window,
            "variance_last": rolling_var[-1],
            "lag1_autocorr_last": rolling_ac1[-1],
            "variance": rolling_var,
            "lag1_autocorr": rolling_ac1,
        }
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
