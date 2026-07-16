import argparse
import json
import math
import os
import signal
import statistics
import subprocess
import tempfile
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn


app = FastAPI()

# In-memory state for execution stats
execution_stats: List[float] = []


def round3(value: float) -> float:
    return round(value, 3)


def error_response(status_code: int, message: str, code: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": message, "code": code},
    )


def validate_request_body(body: Any) -> tuple:
    if not isinstance(body, dict):
        return None, error_response(400, "Request body must be a JSON object", "INVALID_BODY")
    
    # command: required, non-empty string
    command = body.get("command")
    if command is None:
        return None, error_response(400, "Missing required field 'command'", "MISSING_COMMAND")
    if not isinstance(command, str) or not command.strip():
        return None, error_response(400, "Field 'command' must be a non-empty string", "INVALID_COMMAND")
    
    # env: optional, default {}, must be dict[str, str]
    env = body.get("env", {})
    if not isinstance(env, dict):
        return None, error_response(400, "Field 'env' must be an object", "INVALID_ENV")
    for k, v in env.items():
        if not isinstance(k, str) or not isinstance(v, str):
            return None, error_response(400, "Field 'env' must be an object with string keys and values", "INVALID_ENV")
    
    # files: optional, default {}, must be dict
    files = body.get("files", {})
    if not isinstance(files, dict):
        return None, error_response(400, "Field 'files' must be an object", "INVALID_FILES")
    for k, v in files.items():
        if not isinstance(k, str) or not isinstance(v, str):
            return None, error_response(400, "Field 'files' must be an object with string keys and values", "INVALID_FILES")
    
    # stdin: optional, default "", accept string or list of strings
    stdin = body.get("stdin", "")
    if isinstance(stdin, list):
        for item in stdin:
            if not isinstance(item, str):
                return None, error_response(400, "Field 'stdin' array must contain only strings", "INVALID_STDIN")
        stdin = "\n".join(stdin)
    elif not isinstance(stdin, str):
        return None, error_response(400, "Field 'stdin' must be a string or an array of strings", "INVALID_STDIN")
    
    # timeout: optional, default 10, must be numeric > 0
    timeout = body.get("timeout", 10)
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool):
        return None, error_response(400, "Field 'timeout' must be a number", "INVALID_TIMEOUT")
    if timeout <= 0:
        return None, error_response(400, "Field 'timeout' must be greater than 0", "INVALID_TIMEOUT")
    
    return {
        "command": command,
        "env": env,
        "files": files,
        "stdin": stdin,
        "timeout": timeout,
    }, None


@app.post("/v1/execute")
async def execute(request: Request):
    try:
        body = await request.json()
    except Exception:
        return error_response(400, "Invalid JSON body", "INVALID_JSON")
    
    validated, error = validate_request_body(body)
    if error is not None:
        return error
    
    command = validated["command"]
    env = validated["env"]
    files = validated["files"]
    stdin = validated["stdin"]
    timeout = validated["timeout"]
    
    run_id = str(uuid.uuid4())
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Write files
        for rel_path, content in files.items():
            file_path = os.path.join(tmpdir, rel_path)
            parent_dir = os.path.dirname(file_path)
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
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
                exit_code = -1
                # Kill entire process tree
                try:
                    pgid = os.getpgid(proc.pid)
                    os.killpg(pgid, signal.SIGKILL)
                except (ProcessLookupError, OSError):
                    try:
                        proc.kill()
                    except (ProcessLookupError, OSError):
                        pass
                # Collect any remaining output
                try:
                    stdout_data, stderr_data = proc.communicate(timeout=1)
                except Exception:
                    stdout_data = ""
                    stderr_data = ""
        except Exception as e:
            return error_response(500, f"Failed to execute command: {str(e)}", "EXECUTION_ERROR")
        
        end_time = time.time()
        duration = end_time - start_time
        execution_stats.append(duration)
        
        response = {
            "id": run_id,
            "stdout": stdout_data,
            "stderr": stderr_data,
            "exit_code": exit_code,
            "duration": round3(duration),
            "timed_out": timed_out,
        }
        return JSONResponse(status_code=201, content=response)


@app.get("/v1/stats/execution")
async def get_stats():
    if not execution_stats:
        return JSONResponse(
            status_code=200,
            content={
                "ran": 0,
                "duration": {
                    "average": None,
                    "median": None,
                    "max": None,
                    "min": None,
                    "stddev": None,
                },
            },
        )
    
    durations = execution_stats
    n = len(durations)
    avg = statistics.mean(durations)
    med = statistics.median(durations)
    max_val = max(durations)
    min_val = min(durations)
    if n >= 2:
        stddev = statistics.stdev(durations)
    else:
        stddev = 0.0
    
    return JSONResponse(
        status_code=200,
        content={
            "ran": n,
            "duration": {
                "average": round3(avg),
                "median": round3(med),
                "max": round3(max_val),
                "min": round3(min_val),
                "stddev": round3(stddev),
            },
        },
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--address", type=str, default="0.0.0.0")
    args = parser.parse_args()
    
    uvicorn.run(app, host=args.address, port=args.port, http="h11")


if __name__ == "__main__":
    main()
