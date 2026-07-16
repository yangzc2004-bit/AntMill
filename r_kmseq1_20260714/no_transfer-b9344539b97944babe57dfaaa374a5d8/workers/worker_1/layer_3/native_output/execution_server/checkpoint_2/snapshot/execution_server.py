import argparse
import fnmatch
import json
import math
import os
import statistics
import subprocess
import tempfile
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
import uvicorn

app = FastAPI()

# In-memory storage for execution stats
execution_stats: List[float] = []


def round3(value: float) -> float:
    return round(value, 3)


def compute_stats(durations: List[float]) -> Dict[str, Any]:
    if not durations:
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
    n = len(durations)
    avg = round3(statistics.mean(durations))
    med = round3(statistics.median(durations))
    max_val = round3(max(durations))
    min_val = round3(min(durations))
    if n > 1:
        stddev = round3(statistics.stdev(durations))
    else:
        stddev = 0.0
    return {
        "ran": n,
        "duration": {
            "average": avg,
            "median": med,
            "max": max_val,
            "min": min_val,
            "stddev": stddev,
        },
    }


def resolve_globs(base_dir: str, patterns: List[str]) -> Dict[str, str]:
    """Resolve globs relative to base_dir and return {relative_path: content}."""
    result = {}
    seen = set()
    for pattern in patterns:
        # Use fnmatch and os.walk for POSIX glob semantics
        # Support **/ recursive glob
        if "**" in pattern:
            # Handle recursive globs
            # Split into prefix and suffix around **/
            parts = pattern.split("**/")
            prefix = parts[0]  # may be empty or contain a directory prefix
            suffix = parts[1] if len(parts) > 1 else ""
            # If prefix is non-empty, start from there; otherwise from base_dir
            if prefix:
                start_dir = os.path.join(base_dir, prefix)
                if not os.path.isdir(start_dir):
                    continue
            else:
                start_dir = base_dir
            # Walk recursively
            for root, dirs, files in os.walk(start_dir):
                for filename in files:
                    if fnmatch.fnmatch(filename, suffix):
                        full_path = os.path.join(root, filename)
                        rel_path = os.path.relpath(full_path, base_dir)
                        if rel_path not in seen:
                            seen.add(rel_path)
                            try:
                                with open(full_path, "r", encoding="utf-8") as f:
                                    result[rel_path] = f.read()
                            except Exception:
                                pass
        else:
            # Non-recursive glob
            # Split pattern into directory and file pattern
            if os.path.sep in pattern:
                dir_part, file_pattern = pattern.rsplit(os.path.sep, 1)
            else:
                dir_part = ""
                file_pattern = pattern
            search_dir = os.path.join(base_dir, dir_part) if dir_part else base_dir
            if not os.path.isdir(search_dir):
                continue
            for filename in os.listdir(search_dir):
                if fnmatch.fnmatch(filename, file_pattern):
                    full_path = os.path.join(search_dir, filename)
                    if os.path.isfile(full_path):
                        rel_path = os.path.relpath(full_path, base_dir)
                        if rel_path not in seen:
                            seen.add(rel_path)
                            try:
                                with open(full_path, "r", encoding="utf-8") as f:
                                    result[rel_path] = f.read()
                            except Exception:
                                pass
    return result


@app.post("/v1/execute")
async def execute(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={
                "error": "Invalid JSON body",
                "code": "MALFORMED_REQUEST",
            },
        )

    # Validate required fields
    if not isinstance(body, dict):
        return JSONResponse(
            status_code=400,
            content={
                "error": "Request body must be a JSON object",
                "code": "MALFORMED_REQUEST",
            },
        )

    command = body.get("command")
    if command is None or not isinstance(command, str) or command.strip() == "":
        return JSONResponse(
            status_code=400,
            content={
                "error": "Missing or invalid required field: command",
                "code": "INVALID_INPUT",
            },
        )

    env = body.get("env", {})
    if not isinstance(env, dict):
        return JSONResponse(
            status_code=400,
            content={
                "error": "Field 'env' must be an object",
                "code": "INVALID_INPUT",
            },
        )
    # Validate env values are strings
    for k, v in env.items():
        if not isinstance(v, str):
            return JSONResponse(
                status_code=400,
                content={
                    "error": f"Environment variable '{k}' must be a string",
                    "code": "INVALID_INPUT",
                },
            )

    files = body.get("files", {})
    if not isinstance(files, dict):
        return JSONResponse(
            status_code=400,
            content={
                "error": "Field 'files' must be an object",
                "code": "INVALID_INPUT",
            },
        )
    # Validate file values are strings
    for k, v in files.items():
        if not isinstance(v, str):
            return JSONResponse(
                status_code=400,
                content={
                    "error": f"File '{k}' content must be a string",
                    "code": "INVALID_INPUT",
                },
            )

    stdin = body.get("stdin", "")
    if isinstance(stdin, list):
        stdin_str = "\n".join(stdin)
    elif isinstance(stdin, str):
        stdin_str = stdin
    else:
        return JSONResponse(
            status_code=400,
            content={
                "error": "Field 'stdin' must be a string or array of strings",
                "code": "INVALID_INPUT",
            },
        )

    timeout = body.get("timeout", 10)
    if not isinstance(timeout, (int, float)) or timeout <= 0:
        return JSONResponse(
            status_code=400,
            content={
                "error": "Field 'timeout' must be a positive number",
                "code": "INVALID_INPUT",
            },
        )

    # Validate track field
    track = body.get("track")
    if track is not None:
        if not isinstance(track, list):
            return JSONResponse(
                status_code=400,
                content={
                    "error": "Field 'track' must be an array of strings",
                    "code": "INVALID_INPUT",
                },
            )
        for pattern in track:
            if not isinstance(pattern, str):
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": "Each item in 'track' must be a string",
                        "code": "INVALID_INPUT",
                    },
                )

    run_id = str(uuid.uuid4())

    # Create temp working directory
    with tempfile.TemporaryDirectory() as tmpdir:
        # Write files
        for filename, content in files.items():
            filepath = os.path.join(tmpdir, filename)
            # Ensure parent directories exist
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)

        # Prepare environment
        run_env = os.environ.copy()
        run_env.update(env)

        timed_out = False
        exit_code = 0
        stdout = ""
        stderr = ""

        start_time = time.time()
        try:
            proc = subprocess.Popen(
                command,
                shell=True,
                cwd=tmpdir,
                env=run_env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                stdout, stderr = proc.communicate(input=stdin_str, timeout=timeout)
                exit_code = proc.returncode
            except subprocess.TimeoutExpired:
                timed_out = True
                # Measure duration at timeout detection
                duration = time.time() - start_time
                proc.kill()
                try:
                    stdout, stderr = proc.communicate(timeout=1)
                except Exception:
                    stdout = ""
                    stderr = ""
                exit_code = -1
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={
                    "error": f"Failed to execute command: {str(e)}",
                    "code": "EXECUTION_ERROR",
                },
            )

        if not timed_out:
            duration = time.time() - start_time

        # Resolve tracked files after command completes
        tracked_files = None
        if track:
            tracked_files = resolve_globs(tmpdir, track)

    duration_rounded = round3(duration)

    # Store duration for stats
    execution_stats.append(duration)

    response_body = {
        "id": run_id,
        "stdout": stdout,
        "stderr": stderr,
        "exit_code": exit_code,
        "duration": duration_rounded,
        "timed_out": timed_out,
    }

    if tracked_files is not None:
        response_body["files"] = tracked_files

    return JSONResponse(status_code=201, content=response_body)


@app.get("/v1/stats/execution")
async def get_stats():
    stats = compute_stats(execution_stats)
    return JSONResponse(status_code=200, content=stats)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "error": f"Internal server error: {str(exc)}",
            "code": "INTERNAL_ERROR",
        },
    )


def main():
    parser = argparse.ArgumentParser(description="Local runner execution server")
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on")
    parser.add_argument("--address", type=str, default="0.0.0.0", help="Address to bind to")
    args = parser.parse_args()

    uvicorn.run(app, host=args.address, port=args.port)


if __name__ == "__main__":
    main()
