import argparse
import os
import signal
import statistics
import subprocess
import tempfile
import time
import uuid
from typing import Any, Dict, List

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn

app = FastAPI()

# In-memory storage for execution stats
execution_stats: List[float] = []


def round3(value: float) -> float:
    return round(value, 3)


def generate_uuid() -> str:
    return str(uuid.uuid4())


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
    if n >= 2:
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


def kill_process_tree(proc):
    """Kill a process and all its children."""
    try:
        pgid = os.getpgid(proc.pid)
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, OSError):
        try:
            proc.kill()
        except ProcessLookupError:
            pass


@app.post("/v1/execute")
async def execute(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid JSON body", "code": "INVALID_JSON"},
        )

    # Validate required fields
    if not isinstance(body, dict):
        return JSONResponse(
            status_code=400,
            content={"error": "Request body must be a JSON object", "code": "INVALID_BODY_TYPE"},
        )

    command = body.get("command")
    if not command or not isinstance(command, str) or not command.strip():
        return JSONResponse(
            status_code=400,
            content={"error": "Missing or invalid required field: command", "code": "MISSING_COMMAND"},
        )

    env = body.get("env", {})
    if not isinstance(env, dict):
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid field: env must be an object", "code": "INVALID_ENV"},
        )

    files = body.get("files", {})
    if not isinstance(files, dict):
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid field: files must be an object", "code": "INVALID_FILES"},
        )

    stdin = body.get("stdin", "")
    if isinstance(stdin, list):
        stdin = "\n".join(stdin)
    elif not isinstance(stdin, str):
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid field: stdin must be a string or array of strings", "code": "INVALID_STDIN"},
        )

    timeout = body.get("timeout", 10)
    if not isinstance(timeout, (int, float)) or timeout <= 0:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid field: timeout must be a positive number", "code": "INVALID_TIMEOUT"},
        )

    run_id = generate_uuid()
    
    # Create temp working directory
    with tempfile.TemporaryDirectory() as tmpdir:
        # Write files
        for filename, content in files.items():
            filepath = os.path.join(tmpdir, filename)
            # Ensure parent directories exist
            parent = os.path.dirname(filepath)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)

        # Prepare environment
        run_env = os.environ.copy()
        run_env.update(env)

        start_time = time.time()
        timed_out = False
        exit_code = 0
        stdout_data = ""
        stderr_data = ""

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
                start_new_session=True,
            )
            try:
                stdout_data, stderr_data = proc.communicate(input=stdin, timeout=timeout)
                exit_code = proc.returncode
            except subprocess.TimeoutExpired:
                timed_out = True
                kill_process_tree(proc)
                # Try to collect any remaining output with a short timeout
                try:
                    stdout_data, stderr_data = proc.communicate(timeout=2)
                except subprocess.TimeoutExpired:
                    stdout_data, stderr_data = "", ""
                exit_code = -1
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"error": f"Failed to execute command: {str(e)}", "code": "EXECUTION_ERROR"},
            )

        duration = time.time() - start_time
        duration = round3(duration)

        # Store stat
        execution_stats.append(duration)

        response_data = {
            "id": run_id,
            "stdout": stdout_data,
            "stderr": stderr_data,
            "exit_code": exit_code,
            "duration": duration,
            "timed_out": timed_out,
        }

        return JSONResponse(status_code=201, content=response_data)


@app.get("/v1/stats/execution")
async def get_stats():
    stats = compute_stats(execution_stats)
    return JSONResponse(status_code=200, content=stats)


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"error": f"Internal server error: {str(exc)}", "code": "INTERNAL_ERROR"},
    )


def main():
    parser = argparse.ArgumentParser(description="Local runner execution server")
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on")
    parser.add_argument("--address", type=str, default="0.0.0.0", help="Address to bind to")
    args = parser.parse_args()

    uvicorn.run(app, host=args.address, port=args.port)


if __name__ == "__main__":
    main()
