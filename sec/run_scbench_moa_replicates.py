from __future__ import annotations

import argparse
import asyncio
import csv
import json
from pathlib import Path

from sec.run_scbench_moa_curve import layer_rows, run_arm
from sec.scbench_miniswe import load_local_env_value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the frozen SCBench MoA replication schedule."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("benchmarks/scbench/xjq_replication_config.json"),
    )
    parser.add_argument(
        "--run-root",
        type=Path,
        default=Path("runs_scbench_moa_xjq_replication"),
    )
    parser.add_argument("--timeout-sec", type=int, default=600)
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        metavar="REPLICATE:MODE",
        help="Run only a selected arm; may be repeated.",
    )
    parser.add_argument(
        "--replace-existing",
        action="store_true",
        help="Replace selected arms already present in the report.",
    )
    return parser.parse_args()


def write_report(
    run_root: Path,
    config: dict[str, object],
    config_path: Path,
    arms: list[dict[str, object]],
    rows: list[dict[str, object]],
) -> None:
    report = {
        "replication_config": config,
        "config_path": str(config_path),
        "arms": arms,
        "rows": rows,
    }
    (run_root / "replication_report.json").write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )
    if rows:
        with (run_root / "replication_report.csv").open(
            "w", newline="", encoding="utf-8"
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)


def import_existing_pilot(
    repo_root: Path,
    replicate: int,
    spec: dict[str, object],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    report_path = (repo_root / str(spec["report"])).resolve()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    arms: list[dict[str, object]] = []
    rows: list[dict[str, object]] = []
    arm_ids = report["arms"]
    for raw_mode in spec["mode_order"]:
        mode = str(raw_mode)
        arm_id = str(arm_ids[mode])
        arms.append(
            {
                "replicate": replicate,
                "mode": mode,
                "arm_id": arm_id,
                "source": "existing_pilot",
            }
        )
    for raw_row in report["rows"]:
        row = {"replicate": replicate, **raw_row}
        rows.append(row)
    return arms, rows


async def main_async(args: argparse.Namespace) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    config_path = (repo_root / args.config).resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config.get("status") != "engineering_replication_frozen_before_new_outcomes":
        raise RuntimeError("Replication config is not frozen")
    load_local_env_value(repo_root, "MODELARTS_MAAS_KEY")

    run_root = (repo_root / args.run_root).resolve()
    run_root.mkdir(parents=True, exist_ok=True)
    report_path = run_root / "replication_report.json"
    if report_path.is_file():
        existing_report = json.loads(report_path.read_text(encoding="utf-8"))
        arms = list(existing_report["arms"])
        rows = list(existing_report["rows"])
    else:
        arms = []
        rows = []

    selected = set(args.only)

    def arm_key(replicate: int, mode: str) -> str:
        return f"{replicate}:{mode}"

    def has_arm(replicate: int, mode: str) -> bool:
        return any(
            int(item["replicate"]) == replicate and str(item["mode"]) == mode
            for item in arms
        )

    def remove_arm(replicate: int, mode: str) -> None:
        arms[:] = [
            item
            for item in arms
            if not (
                int(item["replicate"]) == replicate
                and str(item["mode"]) == mode
            )
        ]
        rows[:] = [
            item
            for item in rows
            if not (
                int(item["replicate"]) == replicate
                and str(item["mode"]) == mode
            )
        ]

    replicate_specs = config["execution"]["replicates"]
    for raw_spec in replicate_specs:
        spec = dict(raw_spec)
        replicate = int(spec["replicate"])
        if spec["source"] == "existing_pilot":
            if not any(int(item["replicate"]) == replicate for item in arms):
                imported_arms, imported_rows = import_existing_pilot(
                    repo_root, replicate, spec
                )
                arms.extend(imported_arms)
                rows.extend(imported_rows)
                write_report(run_root, config, config_path, arms, rows)
            continue

        for raw_mode in spec["mode_order"]:
            mode = str(raw_mode)
            key = arm_key(replicate, mode)
            if selected and key not in selected:
                continue
            replacing = has_arm(replicate, mode)
            if replacing and not args.replace_existing:
                print(f"Skipping existing arm {key}", flush=True)
                continue
            if replacing:
                remove_arm(replicate, mode)
                write_report(run_root, config, config_path, arms, rows)
            print(
                f"Starting replicate {replicate}, arm {mode}",
                flush=True,
            )
            arm_id, result = await run_arm(
                repo_root=repo_root,
                run_root=run_root,
                pilot=config,
                mode=mode,
                timeout_sec=args.timeout_sec,
            )
            arms.append(
                {
                    "replicate": replicate,
                    "mode": mode,
                    "arm_id": arm_id,
                    "source": "replacement" if replacing else "new",
                }
            )
            for row in layer_rows(mode, arm_id, result):
                rows.append({"replicate": replicate, **row})
            write_report(run_root, config, config_path, arms, rows)
            print(
                f"Completed replicate {replicate}, arm {mode} ({arm_id})",
                flush=True,
            )

    print(
        json.dumps(
            {
                "report": str(run_root / "replication_report.json"),
                "csv": str(run_root / "replication_report.csv"),
                "completed_arms": len(arms),
                "rows": len(rows),
            },
            indent=2,
        )
    )


def main() -> None:
    asyncio.run(main_async(parse_args()))


if __name__ == "__main__":
    main()
