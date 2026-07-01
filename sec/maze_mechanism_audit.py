from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


DEFAULT_RUNS = {
    "frozen": "runs_maze_alpha_mas_frozen_h3_t3_seed2_v1_v3_c4/n4_gt_false_seed2_maze_mad_frozen_reviewer/result.json",
    "private_fixed": "runs_maze_alpha_mas_private_fixed_h3_t3_seed2_v1_v3_c4/n4_gt_false_seed2_maze_mad_private_reviewer/result.json",
    "shared_reviewer": "runs_maze_alpha_mas_shared_h3_t3_seed2_v1_v3_c4/n4_gt_false_seed2_maze_mad_shared_reviewer/result.json",
    "shared_direct": "runs_maze_alpha_mas_shared_direct_h3_t3_seed2_v1_v3_c4/n4_gt_false_seed2_maze_mad_shared_direct/result.json",
    "shared_oracle": "runs_maze_alpha_mas_shared_oracle_h3_t3_seed2_v1_v3_c4/n4_gt_false_seed2_maze_mad_shared_oracle/result.json",
}

CONDITION_ORDER = ["frozen", "private_fixed", "shared_reviewer", "shared_direct", "shared_oracle"]
CONDITION_COLORS = {
    "frozen": "#8a8f98",
    "private_fixed": "#4c78a8",
    "shared_reviewer": "#54a24b",
    "shared_direct": "#e45756",
    "shared_oracle": "#b279a2",
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit Maze Alpha mechanism examples.")
    parser.add_argument("--out-dir", default="./runs_maze_alpha_mechanism_audit_seed2")
    parser.add_argument(
        "--run",
        action="append",
        default=[],
        help="Optional condition=path/to/result.json. Defaults to the seed2 full matrix.",
    )
    parser.add_argument("--round", type=int, default=-1, help="Round to inspect. Defaults to the last round.")
    parser.add_argument("--task-id", default="", help="Heldout task id to inspect. Defaults to the strongest degradation case.")
    parser.add_argument("--agent-id", type=int, default=-1, help="Agent id to highlight. Defaults to worst direct/oracle agent.")
    return parser


def _load_runs(args: argparse.Namespace) -> dict[str, dict[str, Any]]:
    specs = {} if args.run else dict(DEFAULT_RUNS)
    for item in args.run:
        if "=" not in item:
            raise ValueError(f"--run must be condition=path, got {item!r}")
        label, path = item.split("=", 1)
        specs[label.strip()] = path.strip()

    runs: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    for condition, path in specs.items():
        p = Path(path)
        if not p.exists():
            missing.append(f"{condition}: {p}")
            continue
        runs[condition] = json.loads(p.read_text(encoding="utf-8"))
    if missing:
        raise FileNotFoundError("Missing result files:\n" + "\n".join(missing))
    return runs


def _last_round(result: dict[str, Any]) -> int:
    return max(int(record["t"]) for record in result.get("heldout_records", []))


def _record(result: dict[str, Any], t: int) -> dict[str, Any]:
    for record in result.get("heldout_records", []):
        if int(record["t"]) == t:
            return record
    raise KeyError(f"round {t} not found")


def _task_episode(result: dict[str, Any], t: int, task_id: str) -> dict[str, Any]:
    for episode in _record(result, t).get("episodes", []):
        if episode.get("task_id") == task_id:
            return episode
    raise KeyError(f"task {task_id!r} not found at round {t}")


def _agent(episode: dict[str, Any], agent_id: int) -> dict[str, Any]:
    for agent in episode.get("agents", []):
        if int(agent.get("agent_id", -1)) == agent_id:
            return agent
    raise KeyError(f"agent {agent_id} not found")


def _route(agent: dict[str, Any]) -> dict[str, Any]:
    return dict(agent.get("route") or {})


def _route_metric(agent: dict[str, Any], key: str, default: float = 0.0) -> float:
    value = _route(agent).get(key, default)
    return float(value) if value is not None else default


def _choose_case(runs: dict[str, dict[str, Any]], t: int, task_id: str, agent_id: int) -> tuple[str, int]:
    if task_id and agent_id >= 0:
        return task_id, agent_id
    frozen = runs["frozen"]
    candidates: list[tuple[float, str, int]] = []
    for risk_condition in ("shared_direct", "shared_oracle"):
        if risk_condition not in runs:
            continue
        for episode in _record(runs[risk_condition], t).get("episodes", []):
            if task_id and episode.get("task_id") != task_id:
                continue
            frozen_ep = _task_episode(frozen, t, str(episode.get("task_id")))
            for risk_agent in episode.get("agents", []):
                aid = int(risk_agent.get("agent_id", -1))
                if agent_id >= 0 and aid != agent_id:
                    continue
                try:
                    frozen_agent = _agent(frozen_ep, aid)
                except KeyError:
                    continue
                delta = _route_metric(risk_agent, "cost_ratio") - _route_metric(frozen_agent, "cost_ratio")
                loop_bonus = 0.5 if _route(risk_agent).get("looped") else 0.0
                candidates.append((delta + loop_bonus, str(episode.get("task_id")), aid))
    if not candidates:
        first = _record(frozen, t)["episodes"][0]
        return str(first["task_id"]), int(first["agents"][0]["agent_id"])
    _, chosen_task, chosen_agent = max(candidates, key=lambda item: item[0])
    return chosen_task, chosen_agent


def _summary_rows(runs: dict[str, dict[str, Any]], t: int, task_id: str, agent_id: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for condition in [c for c in CONDITION_ORDER if c in runs] + sorted(set(runs) - set(CONDITION_ORDER)):
        episode = _task_episode(runs[condition], t, task_id)
        agent = _agent(episode, agent_id)
        route = _route(agent)
        rows.append(
            {
                "condition": condition,
                "round": t,
                "task_id": task_id,
                "agent_id": agent_id,
                "success": route.get("success"),
                "steps": route.get("steps"),
                "shortest_path_length": route.get("shortest_path_length"),
                "cost_ratio": route.get("cost_ratio"),
                "excess_steps": route.get("excess_steps"),
                "looped": route.get("looped"),
                "revisit_max": route.get("revisit_max"),
                "stagnation_rate": route.get("stagnation_rate"),
                "retrieved_count": len(agent.get("retrieved") or []),
                "retrieved_texts": " | ".join(item.get("text", "") for item in (agent.get("retrieved") or [])),
            }
        )
    return rows


def _top_memories(runs: dict[str, dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for condition, result in runs.items():
        for item in result.get("memory_audit", {}).get("memory_items", []):
            sources = item.get("sources", [])
            source_costs = [float(src.get("quality", {}).get("cost_ratio", 0.0)) for src in sources]
            source_loops = [bool(src.get("quality", {}).get("looped")) for src in sources]
            rows.append(
                {
                    "condition": condition,
                    "retrieval_count": item.get("retrieval_count", 0),
                    "kind": item.get("kind", ""),
                    "source_count": len(sources),
                    "source_cost_max": max(source_costs) if source_costs else 0.0,
                    "source_loop_count": sum(1 for value in source_loops if value),
                    "text": item.get("text", ""),
                }
            )
    rows.sort(key=lambda row: (-int(row["retrieval_count"]), str(row["condition"])))
    return rows[:limit]


def _write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _plot_case(runs: dict[str, dict[str, Any]], t: int, task_id: str, agent_id: int, path: Path) -> None:
    import matplotlib.pyplot as plt

    labels = [c for c in CONDITION_ORDER if c in runs] + sorted(set(runs) - set(CONDITION_ORDER))
    cols = len(labels)
    fig, axes = plt.subplots(1, cols, figsize=(3.3 * cols, 3.9), squeeze=False)
    for ax, condition in zip(axes.flat, labels):
        episode = _task_episode(runs[condition], t, task_id)
        task = episode["task"]
        agent = _agent(episode, agent_id)
        route = _route(agent)
        for y, row in enumerate(task["grid"]):
            for x, cell in enumerate(row):
                if cell == "#":
                    ax.add_patch(plt.Rectangle((x, task["height"] - y - 1), 1, 1, color="#222222"))
        ax.scatter([task["start"][0] + 0.5], [task["height"] - task["start"][1] - 0.5], c="#0ea5e9", marker="s", s=36)
        ax.scatter([task["goal"][0] + 0.5], [task["height"] - task["goal"][1] - 0.5], c="#22c55e", marker="*", s=70)
        path_cells = route.get("path", [])
        if path_cells:
            xs = [cell[0] + 0.5 for cell in path_cells]
            ys = [task["height"] - cell[1] - 0.5 for cell in path_cells]
            ax.plot(xs, ys, color=CONDITION_COLORS.get(condition, "#111111"), linewidth=1.4, alpha=0.82)
            ax.scatter([xs[0]], [ys[0]], c="#0ea5e9", s=16)
            ax.scatter([xs[-1]], [ys[-1]], c="#22c55e", s=22)
        title = (
            f"{condition}\n"
            f"steps={route.get('steps')} cost={float(route.get('cost_ratio', 0.0)):.2f} "
            f"loop={route.get('looped')}"
        )
        ax.set_title(title, fontsize=9)
        ax.set_xlim(0, task["width"])
        ax.set_ylim(0, task["height"])
        ax.set_aspect("equal")
        ax.axis("off")
    fig.suptitle(f"{task_id}, round={t}, agent={agent_id}", fontsize=11)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _write_markdown(
    path: Path,
    *,
    t: int,
    task_id: str,
    agent_id: int,
    rows: list[dict[str, Any]],
    memories: list[dict[str, Any]],
) -> None:
    def fmt(value: Any) -> str:
        if isinstance(value, float):
            return f"{value:.3f}"
        return str(value)

    lines = [
        "# Maze Mechanism Audit",
        "",
        f"Case: `{task_id}`, round `{t}`, agent `{agent_id}`.",
        "",
        "## Route Comparison",
        "",
        "| condition | success | steps | shortest | cost | excess | looped | revisit_max | stagnation | retrieved |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row["condition"]),
                    fmt(row["success"]),
                    fmt(row["steps"]),
                    fmt(row["shortest_path_length"]),
                    fmt(row["cost_ratio"]),
                    fmt(row["excess_steps"]),
                    fmt(row["looped"]),
                    fmt(row["revisit_max"]),
                    fmt(row["stagnation_rate"]),
                    fmt(row["retrieved_count"]),
                ]
            )
            + " |"
        )
    lines += [
        "",
        "## Retrieved Experience In This Case",
        "",
    ]
    for row in rows:
        texts = row.get("retrieved_texts") or ""
        lines.append(f"- `{row['condition']}`: {texts if texts else '(none)'}")
    lines += [
        "",
        "## Top Retrieved Memories",
        "",
        "| condition | retrievals | sources | max source cost | source loops | text |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for row in memories:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row["condition"]),
                    fmt(row["retrieval_count"]),
                    fmt(row["source_count"]),
                    fmt(row["source_cost_max"]),
                    fmt(row["source_loop_count"]),
                    str(row["text"]).replace("|", "/"),
                ]
            )
            + " |"
        )
    lines += [
        "",
        "## Figure",
        "",
        "![Mechanism case](mechanism_case.png)",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = _parser().parse_args()
    runs = _load_runs(args)
    t = args.round if args.round >= 0 else _last_round(next(iter(runs.values())))
    task_id, agent_id = _choose_case(runs, t, args.task_id, args.agent_id)
    out_dir = Path(args.out_dir)
    rows = _summary_rows(runs, t, task_id, agent_id)
    memories = _top_memories(runs)
    _write_csv(rows, out_dir / "case_routes.csv")
    _write_csv(memories, out_dir / "top_memories.csv")
    _plot_case(runs, t, task_id, agent_id, out_dir / "mechanism_case.png")
    _write_markdown(out_dir / "mechanism_audit.md", t=t, task_id=task_id, agent_id=agent_id, rows=rows, memories=memories)
    print(f"wrote {out_dir.resolve()}")


if __name__ == "__main__":
    main()
