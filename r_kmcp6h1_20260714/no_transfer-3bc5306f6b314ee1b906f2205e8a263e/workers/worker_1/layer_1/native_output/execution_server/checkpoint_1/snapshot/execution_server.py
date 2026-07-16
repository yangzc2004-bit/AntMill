import argparse
import os
import signal
import statistics
import subprocess
import tempfile
import time
import uuid
from typing import Any, Dict, List, Optional

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()

# In-memory storage for execution stats
execution_stats: List[float] = []


def round3(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return round(value, 3)


def compute_stats() -> Dict[str, Any]:
    if not execution_stats:
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
    durations = execution_stats
    avg = statistics.mean(durations)
    med = statistics.median(durations)
    max_val = max(durations)
    min_val = min(durations)
    stddev = statistics.stdev(durations) if len(durations) > 1 else 0.0
    return {
        "ran": len(durations),
        "duration": {
            "average": round3(avg),
            "median": round3(med),
            "max": round3(max_val),
            "min": round3(min_val),
            "stddev": round3(stddev),
        },
    }


@app.post("/v1/execute")
async def execute(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={
                "error": "Invalid JSON body",
                "code": "INVALID_JSON",
            },
        )

    # Validate command
    command = body.get("command")
    if not isinstance(command, str) or not command.strip():
        return JSONResponse(
            status_code=400,
            content={
                "error": "Missing or invalid 'command' field",
                "code": "MISSING_COMMAND",
            },
        )

    # Parse optional fields
    env = body.get("env", {})
    if not isinstance(env, dict):
        return JSONResponse(
            status_code=400,
            content={
                "error": "Invalid 'env' field",
                "code": "INVALID_ENV",
            },
        )

    files = body.get("files", {})
    if not isinstance(files, dict):
        return JSONResponse(
            status_code=400,
            content={
                "error": "Invalid 'files' field",
                "code": "INVALID_FILES",
            },
        )

    stdin = body.get("stdin", "")
    if isinstance(stdin, list):
        stdin = "\n".join(stdin)
    elif not isinstance(stdin, str):
        return JSONResponse(
            status_code=400,
            content={
                "error": "Invalid 'stdin' field",
                "code": "INVALID_STDIN",
            },
        )

    timeout = body.get("timeout", 10)
    if not isinstance(timeout, (int, float)) or timeout <= 0:
        return JSONResponse(
            status_code=400,
            content={
                "error": "Invalid 'timeout' field",
                "code": "INVALID_TIMEOUT",
            },
        )

    run_id = str(uuid.uuid4())
    start_time = time.time()

    # Create a temporary working directory
    with tempfile.TemporaryDirectory() as workdir:
        # Write files
        for filename, content in files.items():
            filepath = os.path.join(workdir, filename)
            # Ensure parent directories exist
            parent = os.path.dirname(filepath)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)

        # Prepare environment
        run_env = os.environ.copy()
        run_env.update(env)

        try:
            proc = subprocess.Popen(
                command,
                shell=True,
                cwd=workdir,
                env=run_env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
            )
            try:
                stdout, stderr = proc.communicate(input=stdin, timeout=timeout)
                exit_code = proc.returncode
                timed_out = False
            except subprocess.TimeoutExpired:
                # Kill the entire process group
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass
                try:
                    stdout, stderr = proc.communicate(timeout=2)
                except subprocess.TimeoutExpired:
                    stdout, stderr = "", ""
                exit_code = -1
                timed_out = True
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={
                    "error": f"Failed to execute command: {str(e)}",
                    "code": "EXECUTION_ERROR",
                },
            )

    duration = time.time() - start_time
    execution_stats.append(duration)

    return JSONResponse(
        status_code=201,
        content={
            "id": run_id,
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": exit_code,
            "duration": round3(duration),
            "timed_out": timed_out,
        },
    )


@app.get("/v1/stats/execution")
async def get_stats():
    return JSONResponse(
        status_code=200,
        content=compute_stats(),
    )


def main():
    parser = argparse.ArgumentParser(description="Local Runner Execution Server")
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on")
    parser.add_argument("--address", type=str, default="0.0.0.0", help="Address to bind to")
    args = parser.parse_args()

    uvicorn.run(app, host=args.address, port=args.port)


if __name__ == "__main__":
    main()
