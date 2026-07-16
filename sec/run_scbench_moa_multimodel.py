from __future__ import annotations

import argparse
import asyncio
import csv
import json
from pathlib import Path

from sec.run_scbench_moa_curve import layer_rows, run_arm


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the frozen GLM/Kimi SCBench MoA contrast."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(
            "benchmarks/scbench/multimodel_contrast_config.json"
        ),
    )
    parser.add_argument(
        "--run-root",
        type=Path,
        default=Path("runs_scbench_moa_multimodel_contrast"),
    )
    parser.add_argument(
        "--stage",
        choices=("initial", "additional", "all"),
        default="initial",
    )
    parser.add_argument(
        "--only-model",
        action="append",
        default=[],
        help="Run only the selected model; may be repeated.",
    )
    parser.add_argument("--timeout-sec", type=int, default=900)
    return parser.parse_args()


def write_report(
    run_root: Path,
    config: dict[str, object],
    config_path: Path,
    arms: list[dict[str, object]],
    rows: list[dict[str, object]],
) -> None:
    report = {
        "contrast_config": config,
        "config_path": str(config_path),
        "arms": arms,
        "rows": rows,
    }
    (run_root / "contrast_report.json").write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )
    if rows:
        with (run_root / "contrast_report.csv").open(
            "w", newline="", encoding="utf-8"
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)


async def main_async(args: argparse.Namespace) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    config_path = (repo_root / args.config).resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if (
        config.get("status")
        != "engineering_multimodel_contrast_frozen_before_outcomes"
    ):
        raise RuntimeError("Multimodel contrast config is not frozen")
    run_root = (repo_root / args.run_root).resolve()
    run_root.mkdir(parents=True, exist_ok=True)
    report_path = run_root / "contrast_report.json"
    if report_path.is_file():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        arms = list(report["arms"])
        rows = list(report["rows"])
    else:
        arms = []
        rows = []

    def has_arm(model: str, replicate: int, mode: str) -> bool:
        return any(
            str(item["model"]) == model
            and int(item["replicate"]) == replicate
            and str(item["mode"]) == mode
            for item in arms
        )

    for raw_model_spec in config["models"]:
        model_spec = dict(raw_model_spec)
        model = str(model_spec["model"])
        if args.only_model and model not in set(args.only_model):
            continue
        arm_config = {**config, "model": model}
        for raw_replicate_spec in model_spec["replicates"]:
            replicate_spec = dict(raw_replicate_spec)
            replicate = int(replicate_spec["replicate"])
            if args.stage == "initial" and replicate != 1:
                continue
            if args.stage == "additional" and replicate == 1:
                continue
            for raw_mode in replicate_spec["mode_order"]:
                mode = str(raw_mode)
                if has_arm(model, replicate, mode):
                    print(
                        f"Skipping existing {model} replicate "
                        f"{replicate} {mode}",
                        flush=True,
                    )
                    continue
                print(
                    f"Starting {model} replicate {replicate} arm {mode}",
                    flush=True,
                )
                arm_id, result = await run_arm(
                    repo_root=repo_root,
                    run_root=run_root,
                    pilot=arm_config,
                    mode=mode,
                    timeout_sec=args.timeout_sec,
                )
                arms.append(
                    {
                        "model": model,
                        "replicate": replicate,
                        "mode": mode,
                        "arm_id": arm_id,
                    }
                )
                for row in layer_rows(mode, arm_id, result):
                    rows.append(
                        {
                            "model": model,
                            "replicate": replicate,
                            **row,
                        }
                    )
                write_report(run_root, config, config_path, arms, rows)
                print(
                    f"Completed {model} replicate {replicate} "
                    f"arm {mode} ({arm_id})",
                    flush=True,
                )

    print(
        json.dumps(
            {
                "report": str(report_path),
                "csv": str(run_root / "contrast_report.csv"),
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
