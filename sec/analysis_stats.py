from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from .metrics import ews


# ---------------------------------------------------------------------------
# loading
# ---------------------------------------------------------------------------

def load_runs(out_dir: str | Path) -> dict[str, dict[int, dict[str, Any]]]:
    """Index result.json files by run_id then seed."""
    runs: dict[str, dict[int, dict[str, Any]]] = {}
    for path in sorted(Path(out_dir).glob("*/result.json")):
        result = json.loads(path.read_text(encoding="utf-8"))
        cfg = result.get("config", {})
        run_id = str(cfg.get("run_id", path.parent.name))
        seed = int(cfg.get("seed", 0))
        runs.setdefault(run_id, {})[seed] = result
    return runs


def _final_correct(result: dict[str, Any]) -> dict[str, int]:
    return {row["question"]: int(row["correct"]) for row in result.get("final_eval", [])}


# ---------------------------------------------------------------------------
# paired bootstrap (pair on (seed, question) shared by both arms)
# ---------------------------------------------------------------------------

def paired_bootstrap(
    arm_a: dict[int, dict[str, Any]],
    arm_b: dict[int, dict[str, Any]],
    *,
    n_boot: int = 10000,
    rng_seed: int = 0,
) -> dict[str, Any]:
    diffs: list[float] = []
    for seed in sorted(set(arm_a) & set(arm_b)):
        ca = _final_correct(arm_a[seed])
        cb = _final_correct(arm_b[seed])
        for q in set(ca) & set(cb):
            diffs.append(ca[q] - cb[q])
    if not diffs:
        return {"n_pairs": 0, "mean_diff": 0.0, "ci_lo": 0.0, "ci_hi": 0.0}
    arr = np.asarray(diffs, dtype=float)
    rng = np.random.default_rng(rng_seed)
    idx = rng.integers(0, len(arr), size=(n_boot, len(arr)))
    boot = arr[idx].mean(axis=1)
    return {
        "n_pairs": len(arr),
        "mean_diff": float(arr.mean()),
        "ci_lo": float(np.percentile(boot, 2.5)),
        "ci_hi": float(np.percentile(boot, 97.5)),
    }


def gain_test(
    arm_a: dict[int, dict[str, Any]],
    arm_b: dict[int, dict[str, Any]],
    threshold: float,
) -> dict[str, Any]:
    """arm_a - arm_b final accuracy gain vs a pre-registered threshold with CI excluding 0."""
    bs = paired_bootstrap(arm_a, arm_b)
    passed_threshold = bs["mean_diff"] >= threshold
    passed_ci = bs["ci_lo"] > 0.0
    return {**bs, "threshold": threshold, "passed_threshold": passed_threshold,
            "passed_ci": passed_ci, "passed": passed_threshold and passed_ci}


# ---------------------------------------------------------------------------
# collapse existence
# ---------------------------------------------------------------------------

def collapsed_fraction(arm: dict[int, dict[str, Any]]) -> float:
    if not arm:
        return 0.0
    flags = [bool(r["summary"]["collapse"]["collapsed_within_run"]) for r in arm.values()]
    return sum(flags) / len(flags)


def existence_proof(
    runs: dict[str, dict[int, dict[str, Any]]],
    *,
    collapse_id: str = "P0_collapse",
    nomem_id: str = "P0_nomem",
    anchor_id: str = "P0_anchor",
    below_baseline_margin: float = 0.05,
) -> dict[str, Any]:
    collapse = runs.get(collapse_id, {})
    nomem = runs.get(nomem_id, {})
    anchor = runs.get(anchor_id, {})

    collapse_frac = collapsed_fraction(collapse)
    nomem_frac = collapsed_fraction(nomem)
    anchor_frac = collapsed_fraction(anchor)

    # condition (4): nomem final accuracy exceeds collapse by >= margin, CI excludes 0
    below = paired_bootstrap(nomem, collapse)
    below_passed = below["mean_diff"] >= below_baseline_margin and below["ci_lo"] > 0.0

    passed = (
        collapse_frac >= 0.5
        and nomem_frac < 0.5
        and anchor_frac < 0.5
        and below_passed
    )
    return {
        "collapse_collapsed_fraction": collapse_frac,
        "nomem_collapsed_fraction": nomem_frac,
        "anchor_collapsed_fraction": anchor_frac,
        "below_baseline": {**below, "margin": below_baseline_margin, "passed": below_passed},
        "passed": passed,
    }


# ---------------------------------------------------------------------------
# early-warning signals (Kendall trend test, no scipy dependency)
# ---------------------------------------------------------------------------

def kendall_tau(values: list[float]) -> tuple[float, float]:
    """Kendall rank correlation of a series vs its (increasing) index, with normal-approx p."""
    n = len(values)
    if n < 4:
        return 0.0, 1.0
    concordant = discordant = 0
    for i in range(n):
        for j in range(i + 1, n):
            d = values[j] - values[i]
            if d > 0:
                concordant += 1
            elif d < 0:
                discordant += 1
    denom = 0.5 * n * (n - 1)
    tau = (concordant - discordant) / denom if denom else 0.0
    var = (2.0 * (2 * n + 5)) / (9.0 * n * (n - 1))
    z = tau / math.sqrt(var) if var > 0 else 0.0
    p = math.erfc(abs(z) / math.sqrt(2.0))  # two-sided
    return tau, p


def ews_test_arm(arm: dict[int, dict[str, Any]], *, series: str = "D_t", alpha: float = 0.05) -> dict[str, Any]:
    """For collapsing seeds, test rising variance / lag-1 autocorr trend before t* on `series`."""
    confirmed_seeds = 0
    tested_seeds = 0
    details: list[dict[str, Any]] = []
    for seed, result in sorted(arm.items()):
        collapse = result["summary"]["collapse"]
        t_star = collapse.get("t_star")
        log = result["log"]
        if t_star is None or t_star < 6:
            continue
        window = [float(row[series]) for row in log[:t_star]]
        ews_out = ews(window)
        if "error" in ews_out:
            continue
        tested_seeds += 1
        tau_var, p_var = kendall_tau(ews_out["variance"])
        tau_ac, p_ac = kendall_tau(ews_out["lag1_autocorr"])
        ok = (tau_var > 0 and p_var < alpha) or (tau_ac > 0 and p_ac < alpha)
        confirmed_seeds += int(ok)
        details.append({"seed": seed, "t_star": t_star, "tau_var": tau_var, "p_var": p_var,
                        "tau_ac": tau_ac, "p_ac": p_ac, "confirmed": ok})
    return {
        "series": series,
        "tested_seeds": tested_seeds,
        "confirmed_seeds": confirmed_seeds,
        "confirmed": tested_seeds > 0 and confirmed_seeds / tested_seeds >= 0.5,
        "details": details,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _fmt_gain(name: str, g: dict[str, Any]) -> str:
    return (f"{name}: mean_diff={g['mean_diff']:+.3f} "
            f"CI[{g['ci_lo']:+.3f},{g['ci_hi']:+.3f}] n={g['n_pairs']} "
            f"thr>={g['threshold']:.2f} -> {'PASS' if g['passed'] else 'FAIL'}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Pre-registered cross-arm judgments for SEC phases.")
    parser.add_argument("--out-dir", default="./runs_v2")
    parser.add_argument("--phase", choices=["A0", "A1", "P0"], required=True)
    args = parser.parse_args()

    runs = load_runs(args.out_dir)
    print(f"loaded run_ids: {sorted(runs)}")

    if args.phase == "A0":
        g = gain_test(runs.get("A0_mad", {}), runs.get("A0_single", {}), threshold=0.03)
        print(_fmt_gain("A0 MAD gain (mad - single)", g))
        print(f"GATE A0: {'PASS - proceed' if g['passed'] else 'FAIL - fix MAD instantiation'}")
    elif args.phase == "A1":
        g = gain_test(runs.get("A1_mem", {}), runs.get("A1_nomem", {}), threshold=0.02)
        print(_fmt_gain("A1 experiential gain (mem - nomem)", g))
        print(f"GATE A1: {'PASS - proceed' if g['passed'] else 'FAIL - fix memory or switch dataset'}")
    else:
        ep = existence_proof(runs)
        print(f"collapse collapsed in {ep['collapse_collapsed_fraction']:.0%} of seeds")
        print(f"nomem   collapsed in {ep['nomem_collapsed_fraction']:.0%} of seeds")
        print(f"anchor  collapsed in {ep['anchor_collapsed_fraction']:.0%} of seeds")
        b = ep["below_baseline"]
        print(f"below-baseline (nomem - collapse): mean={b['mean_diff']:+.3f} "
              f"CI[{b['ci_lo']:+.3f},{b['ci_hi']:+.3f}] margin>={b['margin']:.2f} "
              f"-> {'PASS' if b['passed'] else 'FAIL'}")
        for series in ("D_t", "G_t"):
            e = ews_test_arm(runs.get("P0_collapse", {}), series=series)
            print(f"EWS on {series}: confirmed {e['confirmed_seeds']}/{e['tested_seeds']} seeds "
                  f"-> {'CONFIRMED' if e['confirmed'] else 'not confirmed'}")
        print(f"EXISTENCE PROOF: {'PASS' if ep['passed'] else 'FAIL'}")


if __name__ == "__main__":
    main()
