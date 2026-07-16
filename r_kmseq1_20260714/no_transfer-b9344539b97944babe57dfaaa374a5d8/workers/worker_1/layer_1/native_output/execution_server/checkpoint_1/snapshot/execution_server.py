import argparse
import json
import math
import os
import signal
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
    sorted_durations = sorted(durations)
    total = sum(sorted_durations)
    average = total / n
    min_val = sorted_durations[0]
    max_val = sorted_durations[-1]
    
    if n % 2 == 1:
        median = sorted_durations[n // 2]
    else:
        median = (sorted_durations[n // 2 - 1] + sorted_durations[n // 2]) / 2.0
    
    if n > 1:
        variance = sum((d - average) ** 2 for d in sorted_durations) / n
        stddev = math.sqrt(variance)
    else:
        stddev = 0.0
    
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


@app.post("/v1/execute")
async def execute(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid JSON body", "code": "INVALID_JSON"},
        )
    
    # Validate command
    command = body.get("command")
    if not command or not isinstance(command, str) or not command.strip():
        return JSONResponse(
            status_code=400,
            content={"error": "Missing or invalid required field: command", "code": "INVALID_COMMAND"},
        )
    
    # Validate env
    env = body.get("env", {})
    if not isinstance(env, dict):
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid field: env must be an object", "code": "INVALID_ENV"},
        )
    for k, v in env.items():
        if not isinstance(k, str) or not isinstance(v, str):
            return JSONResponse(
                status_code=400,
                content={"error": "Invalid field: env keys and values must be strings", "code": "INVALID_ENV"},
            )
    
    # Validate files
    files = body.get("files", {})
    if not isinstance(files, dict):
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid field: files must be an object", "code": "INVALID_FILES"},
        )
    for k, v in files.items():
        if not isinstance(k, str) or not isinstance(v, str):
            return JSONResponse(
                status_code=400,
                content={"error": "Invalid field: files keys and values must be strings", "code": "INVALID_FILES"},
            )
    
    # Validate stdin
    stdin = body.get("stdin", "")
    if isinstance(stdin, list):
        if not all(isinstance(item, str) for item in stdin):
            return JSONResponse(
                status_code=400,
                content={"error": "Invalid field: stdin array must contain only strings", "code": "INVALID_STDIN"},
            )
        stdin_str = "\n".join(stdin)
    elif isinstance(stdin, str):
        stdin_str = stdin
    else:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid field: stdin must be a string or array of strings", "code": "INVALID_STDIN"},
        )
    
    # Validate timeout
    timeout = body.get("timeout", 10)
    if not isinstance(timeout, (int, float)) or timeout <= 0:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid field: timeout must be a positive number", "code": "INVALID_TIMEOUT"},
        )
    
    # Create temp working directory
    run_id = str(uuid.uuid4())
    start_time = time.time()
    
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
        
        try:
            # Use start_new_session=True to create a new process group so we can kill all children
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
                stdout, stderr = proc.communicate(input=stdin_str, timeout=timeout)
                exit_code = proc.returncode
                timed_out = False
            except subprocess.TimeoutExpired:
                # Kill the entire process group
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass
                proc.wait()
                stdout = ""
                stderr = ""
                exit_code = -1
                timed_out = True
            
            end_time = time.time()
            duration = end_time - start_time
            
            # Store duration for stats
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
            
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"error": f"Execution failed: {str(e)}", "code": "EXECUTION_ERROR"},
            )


@app.get("/v1/stats/execution")
async def get_stats():
    return JSONResponse(
        status_code=200,
        content=compute_stats(execution_stats),
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "code": "INTERNAL_ERROR"},
    )


def main():
    parser = argparse.ArgumentParser(description="Local runner execution server")
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on")
    parser.add_argument("--address", type=str, default="0.0.0.0", help="Address to bind to")
    args = parser.parse_args()
    
    uvicorn.run(app, host=args.address, port=args.port)


if __name__ == "__main__":
    main()
