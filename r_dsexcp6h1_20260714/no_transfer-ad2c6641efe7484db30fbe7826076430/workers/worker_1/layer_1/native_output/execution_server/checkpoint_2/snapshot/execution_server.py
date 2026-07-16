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

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()

# In-memory stats
_lock = threading.Lock()
_durations: List[float] = []
_run_count = 0


def _reset_stats():
    global _run_count, _durations
    with _lock:
        _run_count = 0
        _durations = []


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "code": "INTERNAL_ERROR",
        },
    )


@app.post("/v1/execute", status_code=201)
async def execute(request: Request):
    global _run_count, _durations
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

    # Validate command
    command = body.get("command")
    if not command or not isinstance(command, str) or command.strip() == "":
        return JSONResponse(
            status_code=400,
            content={
                "error": "command is required and must be a non-empty string",
                "code": "MISSING_COMMAND",
            },
        )

    # Optional fields
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
        if not isinstance(k, str) or not isinstance(v, str):
            return JSONResponse(
                status_code=400,
                content={
                    "error": "files keys and values must be strings",
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
        # Remove trailing newline added if list not empty
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

    # Create temporary working directory
    tmp_dir = tempfile.mkdtemp(prefix="execution_")
    try:
        # Write files
        for filename, content in files_dict.items():
            file_path = Path(tmp_dir) / filename
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")

        # Prepare environment
        proc_env = os.environ.copy()
        proc_env.update(env_dict)

        start_time = time.monotonic()
        timed_out = False
        exit_code = 0
        stdout_str = ""
        stderr_str = ""

        try:
            proc = subprocess.run(
                command,
                shell=True,
                cwd=tmp_dir,
                env=proc_env,
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
            # Try to get partial output
            if e.stdout:
                stdout_str = e.stdout.decode("utf-8")
            if e.stderr:
                stderr_str = e.stderr.decode("utf-8")
        except Exception:
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Failed to execute command",
                    "code": "EXECUTION_ERROR",
                },
            )

        duration = time.monotonic() - start_time
        duration_rounded = round(duration, 3)

        # Track files
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

        # Update stats
        with _lock:
            _run_count += 1
            _durations.append(duration)

        result = {
            "id": run_id,
            "stdout": stdout_str,
            "stderr": stderr_str,
            "exit_code": exit_code,
            "duration": duration_rounded,
            "timed_out": timed_out,
        }
        if track:
            result["files"] = tracked_files
        return result
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@app.get("/v1/stats/execution")
async def stats():
    global _run_count, _durations
    with _lock:
        count = _run_count
        durations_copy = list(_durations)

    if count == 0:
        return {
            "ran": 0,
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

    # Round to 3 decimal places
    avg = round(avg, 3)
    median = round(median, 3)
    max_d = round(max_d, 3)
    min_d = round(min_d, 3)
    stddev = round(stddev, 3)

    return {
        "ran": count,
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

    # Reset stats on server start
    _reset_stats()

    uvicorn.run(
        app,
        host=args.address,
        port=args.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
