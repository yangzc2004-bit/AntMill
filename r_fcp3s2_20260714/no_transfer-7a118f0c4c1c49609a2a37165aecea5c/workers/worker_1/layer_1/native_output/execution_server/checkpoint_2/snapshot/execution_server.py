import argparse
import asyncio
import json
import math
import os
import statistics
import tempfile
import time
import uuid
from typing import Any, Dict, List, Optional, Set

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
import uvicorn
from wcmatch import glob

app = FastAPI()

# In-memory storage for execution stats
execution_stats: List[float] = []


def round3(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return round(value, 3)


def make_error_response(status_code: int, message: str, code: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": message, "code": code},
    )


def validate_execute_request(body: Dict[str, Any]) -> tuple:
    # Check command
    if "command" not in body:
        return None, make_error_response(400, "Missing required field: command", "MISSING_COMMAND")
    command = body["command"]
    if not isinstance(command, str) or not command.strip():
        return None, make_error_response(400, "command must be a non-empty string", "INVALID_COMMAND")

    # Check env
    env = body.get("env", {})
    if not isinstance(env, dict):
        return None, make_error_response(400, "env must be an object", "INVALID_ENV")
    for k, v in env.items():
        if not isinstance(k, str) or not isinstance(v, str):
            return None, make_error_response(400, "env keys and values must be strings", "INVALID_ENV")

    # Check files
    files = body.get("files", {})
    if not isinstance(files, dict):
        return None, make_error_response(400, "files must be an object", "INVALID_FILES")
    for k, v in files.items():
        if not isinstance(k, str) or not isinstance(v, str):
            return None, make_error_response(400, "files keys and values must be strings", "INVALID_FILES")

    # Check stdin
    stdin = body.get("stdin", "")
    if isinstance(stdin, list):
        for item in stdin:
            if not isinstance(item, str):
                return None, make_error_response(400, "stdin array items must be strings", "INVALID_STDIN")
        stdin_str = "\n".join(stdin)
    elif isinstance(stdin, str):
        stdin_str = stdin
    else:
        return None, make_error_response(400, "stdin must be a string or array of strings", "INVALID_STDIN")

    # Check timeout
    timeout = body.get("timeout", 10)
    if not isinstance(timeout, (int, float)) or timeout <= 0:
        return None, make_error_response(400, "timeout must be a number greater than 0", "INVALID_TIMEOUT")

    # Check track
    track = body.get("track", None)
    if track is not None:
        if not isinstance(track, list):
            return None, make_error_response(400, "track must be an array", "INVALID_TRACK")
        for item in track:
            if not isinstance(item, str):
                return None, make_error_response(400, "track items must be strings", "INVALID_TRACK")

    return {
        "command": command,
        "env": env,
        "files": files,
        "stdin": stdin_str,
        "timeout": timeout,
        "track": track,
    }, None


@app.post("/v1/execute")
async def execute(request: Request):
    try:
        body = await request.json()
    except Exception:
        return make_error_response(400, "Invalid JSON body", "INVALID_JSON")

    if not isinstance(body, dict):
        return make_error_response(400, "Request body must be a JSON object", "INVALID_BODY")

    validated, error = validate_execute_request(body)
    if error:
        return error

    run_id = str(uuid.uuid4())

    # Create temp working directory
    with tempfile.TemporaryDirectory() as tmpdir:
        # Write files
        for filename, content in validated["files"].items():
            filepath = os.path.join(tmpdir, filename)
            # Ensure parent directories exist
            os.makedirs(os.path.dirname(filepath) or tmpdir, exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)

        # Prepare environment
        run_env = os.environ.copy()
        run_env.update(validated["env"])

        # Execute command
        start_time = time.time()
        try:
            proc = await asyncio.create_subprocess_shell(
                validated["command"],
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.PIPE,
                env=run_env,
                cwd=tmpdir,
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(input=validated["stdin"].encode("utf-8")),
                    timeout=validated["timeout"],
                )
                timed_out = False
                exit_code = proc.returncode
                if exit_code is None:
                    exit_code = -1
            except asyncio.TimeoutError:
                timed_out = True
                try:
                    proc.kill()
                    await proc.wait()
                except Exception:
                    pass
                stdout_bytes = b""
                stderr_bytes = b""
                exit_code = -1

        except Exception as e:
            return make_error_response(500, f"Failed to execute command: {str(e)}", "EXECUTION_FAILED")

        end_time = time.time()
        duration = end_time - start_time

        # Track files if requested
        tracked_files = None
        track = validated.get("track")
        if track is not None and len(track) > 0:
            tracked_files = {}
            matched_paths: Set[str] = set()
            for pattern in track:
                matches = glob.glob(
                    pattern,
                    root_dir=tmpdir,
                    flags=glob.GLOBSTAR,
                )
                for match in matches:
                    if match not in matched_paths:
                        matched_paths.add(match)
                        file_path = os.path.join(tmpdir, match)
                        # Only track files (not directories)
                        if os.path.isfile(file_path):
                            try:
                                with open(file_path, "r", encoding="utf-8") as f:
                                    tracked_files[match] = f.read()
                            except Exception:
                                # Skip files that can't be read
                                pass

    # Decode outputs
    try:
        stdout = stdout_bytes.decode("utf-8", errors="replace")
    except Exception:
        stdout = ""

    try:
        stderr = stderr_bytes.decode("utf-8", errors="replace")
    except Exception:
        stderr = ""

    # Update stats
    execution_stats.append(duration)

    response_data = {
        "id": run_id,
        "stdout": stdout,
        "stderr": stderr,
        "exit_code": exit_code,
        "duration": round3(duration),
        "timed_out": timed_out,
    }

    if tracked_files is not None:
        response_data["files"] = tracked_files

    return JSONResponse(status_code=201, content=response_data)


@app.get("/v1/stats/execution")
async def get_stats():
    ran = len(execution_stats)
    if ran == 0:
        duration_stats = {
            "average": None,
            "median": None,
            "max": None,
            "min": None,
            "stddev": None,
        }
    else:
        durations = execution_stats
        avg = statistics.mean(durations)
        med = statistics.median(durations)
        max_d = max(durations)
        min_d = min(durations)
        if ran > 1:
            stddev = statistics.stdev(durations)
        else:
            stddev = 0.0

        duration_stats = {
            "average": round3(avg),
            "median": round3(med),
            "max": round3(max_d),
            "min": round3(min_d),
            "stddev": round3(stddev),
        }

    return JSONResponse(
        status_code=200,
        content={
            "ran": ran,
            "duration": duration_stats,
        },
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return make_error_response(500, "Internal server error", "INTERNAL_ERROR")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--address", type=str, default="0.0.0.0")
    args = parser.parse_args()

    uvicorn.run(app, host=args.address, port=args.port)


if __name__ == "__main__":
    main()
