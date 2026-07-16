#!/usr/bin/env python3
"""Execution server: local runner web API for internal CI."""

import argparse
import json
import math
import os
import shutil
import signal
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import gzip
import bz2
import csv
import io
import yaml

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()

# In-memory stats
_lock = threading.Lock()
_durations: List[float] = []
_run_count = 0
_total_commands = 0
_ran_commands = 0
_command_durations: List[float] = []


def _reset_stats():
    global _run_count, _durations, _total_commands, _ran_commands, _command_durations
    with _lock:
        _run_count = 0
        _durations = []
        _total_commands = 0
        _ran_commands = 0
        _command_durations = []


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "code": "INTERNAL_ERROR",
        },
    )


# ---------------------------------------------------------------------------
# Structured file format helpers
# ---------------------------------------------------------------------------

_COMPRESSION_EXTS = {".gz", ".bz2"}
_BASE_FORMAT_EXTS = {".json", ".yaml", ".yml", ".jsonl", ".ndjson", ".csv", ".tsv"}


def _has_multiple_compression(filename: str) -> bool:
    lower = filename.lower()
    count = lower.count(".gz") + lower.count(".bz2")
    return count > 1


def _get_base_extension(filename: str) -> str:
    path = Path(filename.lower())
    suffixes = path.suffixes
    result_suffixes = []
    for s in reversed(suffixes):
        if s in _COMPRESSION_EXTS:
            continue
        result_suffixes.insert(0, s)
    if result_suffixes:
        return result_suffixes[-1]
    return ""


def _is_structured_ext(ext: str) -> bool:
    return ext in _BASE_FORMAT_EXTS


def _write_structured_file(file_path: Path, value: Any, filename: str) -> None:
    lower = filename.lower()
    base_ext = _get_base_extension(filename)
    is_gz = lower.endswith(".gz")
    is_bz2 = lower.endswith(".bz2")
    content = _format_value(value, base_ext)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    if is_gz:
        import gzip
        with gzip.open(file_path, "wt", encoding="utf-8") as f:
            f.write(content)
    elif is_bz2:
        import bz2
        with bz2.open(file_path, "wt", encoding="utf-8") as f:
            f.write(content)
    else:
        file_path.write_text(content, encoding="utf-8")


def _format_value(value: Any, base_ext: str) -> str:
    if base_ext == ".json":
        return json.dumps(value, separators=(",", ":"), ensure_ascii=False) + "\n"
    if base_ext in (".yaml", ".yml"):
        return yaml.dump(value, default_flow_style=False, allow_unicode=True)
    if base_ext in (".jsonl", ".ndjson"):
        if isinstance(value, list):
            lines = [json.dumps(item, separators=(",", ":"), ensure_ascii=False) for item in value]
            return "\n".join(lines) + ("\n" if lines else "")
        return json.dumps(value, separators=(",", ":"), ensure_ascii=False) + "\n"
    if base_ext == ".csv":
        return _format_tabular(value, ",")
    if base_ext == ".tsv":
        return _format_tabular(value, "\t")
    if isinstance(value, str):
        return value
    return str(value)


def _format_tabular(value: Any, delimiter: str) -> str:
    output = io.StringIO()
    if isinstance(value, list):
        if not value:
            return "\n"
        all_keys = set()
        for row in value:
            if isinstance(row, dict):
                all_keys.update(row.keys())
        sorted_keys = sorted(all_keys)
        writer = csv.writer(output, delimiter=delimiter, lineterminator="\n")
        if sorted_keys:
            writer.writerow(sorted_keys)
            for row in value:
                if isinstance(row, dict):
                    writer.writerow([str(row.get(k, "")) if row.get(k) is not None else "" for k in sorted_keys])
                else:
                    writer.writerow([str(row)])
        else:
            output.write("\n")
    elif isinstance(value, dict):
        if not value:
            return "\n"
        sorted_keys = sorted(value.keys())
        max_rows = max((len(v) if isinstance(v, (list, tuple)) else 0) for v in value.values())
        writer = csv.writer(output, delimiter=delimiter, lineterminator="\n")
        writer.writerow(sorted_keys)
        for i in range(max_rows):
            row = []
            for k in sorted_keys:
                col = value[k]
                if isinstance(col, (list, tuple)) and i < len(col):
                    val = col[i]
                    row.append(str(val) if val is not None else "")
                else:
                    row.append("")
            writer.writerow(row)
    elif isinstance(value, str):
        if value == "":
            output.write("\n")
        else:
            output.write(value)
    else:
        output.write(str(value))
    return output.getvalue()


def _execute_single_command(cmd: str, cwd: str, env: dict, stdin_str: str, timeout: float):
    start_time = time.monotonic()
    timed_out = False
    exit_code = 0
    stdout_str = ""
    stderr_str = ""
    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            cwd=cwd,
            env=env,
            input=stdin_str.encode("utf-8") if stdin_str else None,
            capture_output=True,
            timeout=timeout,
        )
        stdout_str = proc.stdout.decode("utf-8")
        stderr_str = proc.stderr.decode("utf-8")
        exit_code = proc.returncode
    except subprocess.TimeoutExpired as e:
        timed_out = True
        exit_code = -1
        if e.stdout:
            stdout_str = e.stdout.decode("utf-8")
        if e.stderr:
            stderr_str = e.stderr.decode("utf-8")
    except Exception:
        raise
    duration = time.monotonic() - start_time
    duration_rounded = round(duration, 3)
    return {
        "exit_code": exit_code,
        "stdout": stdout_str,
        "stderr": stderr_str,
        "duration": duration_rounded,
        "timed_out": timed_out,
    }


@app.post("/v1/execute", status_code=201)
async def execute(request: Request):
    global _run_count, _durations, _total_commands, _ran_commands, _command_durations
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JSONResponse(
            status_code=400,
            content={
                "error": "Invalid JSON body",
                "code": "INVALID_JSON",
            },
        )
    if not isinstance(body, dict):
        return JSONResponse(
            status_code=400,
            content={
                "error": "Body must be a JSON object",
                "code": "INVALID_BODY",
            },
        )

    command = body.get("command")
    if command is None:
        return JSONResponse(
            status_code=400,
            content={
                "error": "command is required",
                "code": "MISSING_COMMAND",
            },
        )

    is_chained = isinstance(command, list)

    if is_chained:
        if len(command) == 0:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "command array must not be empty",
                    "code": "INVALID_COMMAND",
                },
            )
        for i, cmd_obj in enumerate(command):
            if not isinstance(cmd_obj, dict):
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": f"command[{i}] must be an object",
                        "code": "INVALID_COMMAND",
                    },
                )
            if "cmd" not in cmd_obj or not isinstance(cmd_obj["cmd"], str) or cmd_obj["cmd"].strip() == "":
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": f"command[{i}].cmd is required and must be a non-empty string",
                        "code": "MISSING_COMMAND",
                    },
                )
    else:
        if not isinstance(command, str) or command.strip() == "":
            return JSONResponse(
                status_code=400,
                content={
                    "error": "command is required and must be a non-empty string",
                    "code": "MISSING_COMMAND",
                },
            )

    env_dict: Dict[str, str] = body.get("env", {})
    if not isinstance(env_dict, dict):
        return JSONResponse(
            status_code=400,
            content={
                "error": "env must be an object",
                "code": "INVALID_ENV",
            },
        )
    for k, v in env_dict.items():
        if not isinstance(k, str) or not isinstance(v, str):
            return JSONResponse(
                status_code=400,
                content={
                    "error": "env keys and values must be strings",
                    "code": "INVALID_ENV",
                },
            )

    files_dict: Dict[str, str] = body.get("files", {})
    if not isinstance(files_dict, dict):
        return JSONResponse(
            status_code=400,
            content={
                "error": "files must be an object",
                "code": "INVALID_FILES",
            },
        )
    for k, v in files_dict.items():
        if not isinstance(k, str):
            return JSONResponse(
                status_code=400,
                content={
                    "error": "files keys must be strings",
                    "code": "INVALID_FILES",
                },
            )
        if _has_multiple_compression(k):
            return JSONResponse(
                status_code=400,
                content={
                    "error": "Multiple compression extensions are not allowed",
                    "code": "INVALID_FILES",
                },
            )

    stdin_input = body.get("stdin", "")
    if isinstance(stdin_input, list):
        stdin_str = ""
        for item in stdin_input:
            if not isinstance(item, str):
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": "stdin array items must be strings",
                        "code": "INVALID_STDIN",
                    },
                )
            stdin_str += item + "\n"
        if stdin_input:
            stdin_str = stdin_str.rstrip("\n")
    elif isinstance(stdin_input, str):
        stdin_str = stdin_input
    else:
        return JSONResponse(
            status_code=400,
            content={
                "error": "stdin must be a string or array of strings",
                "code": "INVALID_STDIN",
            },
        )

    timeout = body.get("timeout", 10)
    if not isinstance(timeout, (int, float)) or timeout <= 0:
        return JSONResponse(
            status_code=400,
            content={
                "error": "timeout must be a positive number",
                "code": "INVALID_TIMEOUT",
            },
        )

    continue_on_error = body.get("continue_on_error", False)
    if not isinstance(continue_on_error, bool):
        return JSONResponse(
            status_code=400,
            content={
                "error": "continue_on_error must be a boolean",
                "code": "INVALID_CONTINUE_ON_ERROR",
            },
        )

    track = body.get("track", None)
    if track is not None:
        if not isinstance(track, list) or not all(isinstance(g, str) for g in track):
            return JSONResponse(
                status_code=400,
                content={
                    "error": "track must be an array of strings",
                    "code": "INVALID_TRACK",
                },
            )

    run_id = str(uuid.uuid4())

    tmp_dir = tempfile.mkdtemp(prefix="execution_")
    try:
        for filename, content in files_dict.items():
            file_path = Path(tmp_dir) / filename
            _write_structured_file(file_path, content, filename)

        proc_env = os.environ.copy()
        proc_env.update(env_dict)

        if not is_chained:
            start_time = time.monotonic()
            result = _execute_single_command(
                command, tmp_dir, proc_env, stdin_str, timeout
            )
            duration = time.monotonic() - start_time
            duration_rounded = round(duration, 3)

            tracked_files = {}
            if track:
                tmp_path = Path(tmp_dir)
                for pattern in track:
                    for matched_path in tmp_path.glob(pattern):
                        if matched_path.is_file():
                            try:
                                rel_path = str(matched_path.relative_to(tmp_path))
                                content_text = matched_path.read_text(encoding="utf-8")
                            except Exception:
                                continue
                            tracked_files[rel_path] = content_text

            with _lock:
                _run_count += 1
                _durations.append(duration)
                _total_commands += 1
                _ran_commands += 1
                _command_durations.append(duration)

            result_data = {
                "id": run_id,
                "stdout": result["stdout"],
                "stderr": result["stderr"],
                "exit_code": result["exit_code"],
                "duration": duration_rounded,
                "timed_out": result["timed_out"],
            }
            if track:
                result_data["files"] = tracked_files
            return result_data

        else:
            commands_results = []
            overall_exit_code = 0
            overall_timed_out = False
            overall_duration = 0.0
            stop_execution = False
            first_stdin = stdin_str

            for i, cmd_obj in enumerate(command):
                if stop_execution:
                    break

                cmd = cmd_obj["cmd"]
                cmd_timeout = cmd_obj.get("timeout", timeout)
                if not isinstance(cmd_timeout, (int, float)) or cmd_timeout <= 0:
                    return JSONResponse(
                        status_code=400,
                        content={
                            "error": f"command[{i}].timeout must be a positive number",
                            "code": "INVALID_TIMEOUT",
                        },
                    )
                required = cmd_obj.get("required", False)
                if not isinstance(required, bool):
                    return JSONResponse(
                        status_code=400,
                        content={
                            "error": f"command[{i}].required must be a boolean",
                            "code": "INVALID_REQUIRED",
                        },
                    )

                cmd_stdin = first_stdin if i == 0 else ""

                cmd_result = _execute_single_command(
                    cmd, tmp_dir, proc_env, cmd_stdin, cmd_timeout
                )

                cmd_entry = {
                    "cmd": cmd,
                    "stdout": cmd_result["stdout"],
                    "stderr": cmd_result["stderr"],
                    "exit_code": cmd_result["exit_code"],
                    "duration": cmd_result["duration"],
                    "timed_out": cmd_result["timed_out"],
                }
                if required:
                    cmd_entry["required"] = True

                commands_results.append(cmd_entry)
                overall_duration += cmd_result["duration"]

                with _lock:
                    _total_commands += 1
                    _ran_commands += 1
                    _command_durations.append(cmd_result["duration"])

                if cmd_result["timed_out"]:
                    overall_timed_out = True

                if cmd_result["exit_code"] != 0:
                    if cmd_result["timed_out"]:
                        if overall_exit_code == 0:
                            overall_exit_code = -1
                    else:
                        if overall_exit_code == 0:
                            overall_exit_code = cmd_result["exit_code"]

                if cmd_result["exit_code"] != 0 and not cmd_result["timed_out"]:
                    if not continue_on_error and not required:
                        remaining_have_required = False
                        for j in range(i + 1, len(command)):
                            if command[j].get("required", False):
                                remaining_have_required = True
                                break
                        if not remaining_have_required:
                            stop_execution = True
                elif cmd_result["timed_out"]:
                    if not continue_on_error and not required:
                        remaining_have_required = False
                        for j in range(i + 1, len(command)):
                            if command[j].get("required", False):
                                remaining_have_required = True
                                break
                        if not remaining_have_required:
                            stop_execution = True

            tracked_files = {}
            if track:
                tmp_path = Path(tmp_dir)
                for pattern in track:
                    for matched_path in tmp_path.glob(pattern):
                        if matched_path.is_file():
                            try:
                                rel_path = str(matched_path.relative_to(tmp_path))
                                content_text = matched_path.read_text(encoding="utf-8")
                            except Exception:
                                continue
                            tracked_files[rel_path] = content_text

            with _lock:
                _run_count += 1
                _durations.append(overall_duration)

            overall_duration_rounded = round(overall_duration, 3)

            result_data = {
                "id": run_id,
                "commands": commands_results,
                "exit_code": overall_exit_code,
                "duration": overall_duration_rounded,
                "timed_out": overall_timed_out,
            }
            if track:
                result_data["files"] = tracked_files
            return result_data
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@app.get("/v1/stats/execution")
async def stats():
    global _run_count, _durations, _total_commands, _ran_commands, _command_durations
    with _lock:
        count = _run_count
        durations_copy = list(_durations)
        cmd_count = _total_commands
        cmd_ran = _ran_commands
        cmd_durations_copy = list(_command_durations)

    if count == 0:
        return {
            "ran": 0,
            "commands": {
                "total": 0,
                "ran": 0,
                "average": None,
                "average_ran": None,
                "duration": {
                    "average": None,
                    "median": None,
                    "max": None,
                    "min": None,
                    "stddev": None,
                },
            },
            "duration": {
                "average": None,
                "median": None,
                "max": None,
                "min": None,
                "stddev": None,
            },
        }

    durations_sorted = sorted(durations_copy)
    avg = sum(durations_sorted) / count
    median = statistics.median(durations_sorted)
    max_d = max(durations_sorted)
    min_d = min(durations_sorted)
    if count >= 2:
        stddev = statistics.stdev(durations_sorted)
    else:
        stddev = 0.0

    avg = round(avg, 3)
    median = round(median, 3)
    max_d = round(max_d, 3)
    min_d = round(min_d, 3)
    stddev = round(stddev, 3)

    # Command-level stats
    cmd_durations_sorted = sorted(cmd_durations_copy)
    if cmd_ran > 0:
        cmd_avg = sum(cmd_durations_sorted) / len(cmd_durations_sorted)
        cmd_median = statistics.median(cmd_durations_sorted)
        cmd_max = max(cmd_durations_sorted)
        cmd_min = min(cmd_durations_sorted)
        if len(cmd_durations_sorted) >= 2:
            cmd_stddev = statistics.stdev(cmd_durations_sorted)
        else:
            cmd_stddev = 0.0
    else:
        cmd_avg = None
        cmd_median = None
        cmd_max = None
        cmd_min = None
        cmd_stddev = None

    if cmd_avg is not None:
        cmd_avg = round(cmd_avg, 3)
        cmd_median = round(cmd_median, 3)
        cmd_max = round(cmd_max, 3)
        cmd_min = round(cmd_min, 3)
        cmd_stddev = round(cmd_stddev, 3)

    cmd_average = round(cmd_count / count, 3) if count > 0 else None
    cmd_average_ran = round(cmd_ran / count, 3) if count > 0 else None

    return {
        "ran": count,
        "commands": {
            "total": cmd_count,
            "ran": cmd_ran,
            "average": cmd_average,
            "average_ran": cmd_average_ran,
            "duration": {
                "average": cmd_avg,
                "median": cmd_median,
                "max": cmd_max,
                "min": cmd_min,
                "stddev": cmd_stddev,
            },
        },
        "duration": {
            "average": avg,
            "median": median,
            "max": max_d,
            "min": min_d,
            "stddev": stddev,
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Execution server")
    parser.add_argument(
        "--port", type=int, default=8080, help="Port to listen on (default: 8080)"
    )
    parser.add_argument(
        "--address", type=str, default="0.0.0.0", help="Address to bind (default: 0.0.0.0)"
    )
    args = parser.parse_args()
    _reset_stats()
    uvicorn.run(
        app,
        host=args.address,
        port=args.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
