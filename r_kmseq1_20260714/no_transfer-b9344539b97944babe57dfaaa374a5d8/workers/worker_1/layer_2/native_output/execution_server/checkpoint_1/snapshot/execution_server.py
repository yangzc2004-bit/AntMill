import argparse
import json
import math
import os
import subprocess
import sys
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


def round3(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
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
    sorted_durations = sorted(durations)
    total = sum(durations)
    average = total / n
    min_val = sorted_durations[0]
    max_val = sorted_durations[-1]

    if n % 2 == 1:
        median = sorted_durations[n // 2]
    else:
        median = (sorted_durations[n // 2 - 1] + sorted_durations[n // 2]) / 2

    if n == 1:
        stddev = 0.0
    else:
        variance = sum((d - average) ** 2 for d in durations) / n
        stddev = math.sqrt(variance)

    return {
        "ran": n,
        "duration": {
            "average": round3(average),
            "median": round3(median),
            "max": round3(max_val),
            "min": round3(min_val),
            "stddev": round3(stddev),
        },
    }


def make_error(message: str, code: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": message, "code": code},
    )


@app.post("/v1/execute")
async def execute(request: Request) -> Response:
    try:
        body = await request.json()
    except Exception:
        return make_error("Invalid JSON body", "INVALID_JSON", 400)

    # Validate command
    command = body.get("command")
    if not isinstance(command, str) or not command.strip():
        return make_error("Missing or invalid required field: command", "INVALID_COMMAND", 400)

    # Validate/parse optional fields
    env = body.get("env", {})
    if not isinstance(env, dict):
        return make_error("Invalid field: env must be an object", "INVALID_ENV", 400)
    # Ensure all env values are strings
    for k, v in env.items():
        if not isinstance(v, str):
            return make_error(f"Invalid env value for key {k}: must be a string", "INVALID_ENV_VALUE", 400)

    files = body.get("files", {})
    if not isinstance(files, dict):
        return make_error("Invalid field: files must be an object", "INVALID_FILES", 400)
    for k, v in files.items():
        if not isinstance(v, str):
            return make_error(f"Invalid file value for key {k}: must be a string", "INVALID_FILE_VALUE", 400)

    stdin_val = body.get("stdin", "")
    if isinstance(stdin_val, list):
        stdin_str = "\n".join(stdin_val)
    elif isinstance(stdin_val, str):
        stdin_str = stdin_val
    else:
        return make_error("Invalid field: stdin must be a string or array of strings", "INVALID_STDIN", 400)

    timeout = body.get("timeout", 10)
    if not isinstance(timeout, (int, float)) or timeout <= 0:
        return make_error("Invalid field: timeout must be a positive number", "INVALID_TIMEOUT", 400)

    # Create temporary working directory
    with tempfile.TemporaryDirectory() as tmpdir:
        # Write files
        for filename, content in files.items():
            # Prevent directory traversal
            safe_name = os.path.basename(filename)
            if not safe_name:
                continue
            filepath = os.path.join(tmpdir, safe_name)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)

        # Prepare environment
        run_env = os.environ.copy()
        run_env.update(env)

        # Execute command
        run_id = str(uuid.uuid4())
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
                end_time = time.time()
                duration = end_time - start_time
                timed_out = False
                exit_code = proc.returncode
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                end_time = time.time()
                duration = end_time - start_time
                timed_out = True
                exit_code = -1
                # Try to capture any output
                try:
                    stdout, stderr = proc.communicate(timeout=1)
                except Exception:
                    stdout = ""
                    stderr = ""

        except Exception as e:
            return make_error(f"Failed to execute command: {str(e)}", "EXECUTION_FAILED", 500)

        # Record stats
        execution_stats.append(duration)

        response_body = {
            "id": run_id,
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": exit_code,
            "duration": round3(duration),
            "timed_out": timed_out,
        }

        return JSONResponse(status_code=201, content=response_body)


@app.get("/v1/stats/execution")
async def get_stats() -> Response:
    stats = compute_stats(execution_stats)
    return JSONResponse(status_code=200, content=stats)


def main():
    parser = argparse.ArgumentParser(description="Local execution runner API")
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on")
    parser.add_argument("--address", type=str, default="0.0.0.0", help="Address to bind to")
    args = parser.parse_args()

    uvicorn.run(app, host=args.address, port=args.port)


if __name__ == "__main__":
    main()
