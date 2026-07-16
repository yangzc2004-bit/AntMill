import argparse
import asyncio
import json
import math
import os
import shutil
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
execution_stats = {
    "runs": [],
    "count": 0,
}

def round3(value: float) -> float:
    return round(value, 3)

def compute_stats() -> Dict[str, Any]:
    runs = execution_stats["runs"]
    count = len(runs)
    if count == 0:
        return {
            "ran": 0,
            "duration": {
                "average": None,
                "median": None,
                "max": None,
                "min": None,
                "stddev": None,
            }
        }
    
    durations = sorted(runs)
    total = sum(durations)
    average = total / count
    min_val = durations[0]
    max_val = durations[-1]
    
    # Median
    if count % 2 == 1:
        median = durations[count // 2]
    else:
        median = (durations[count // 2 - 1] + durations[count // 2]) / 2
    
    # Stddev
    variance = sum((d - average) ** 2 for d in durations) / count
    stddev = math.sqrt(variance)
    
    return {
        "ran": count,
        "duration": {
            "average": round3(average),
            "median": round3(median),
            "max": round3(max_val),
            "min": round3(min_val),
            "stddev": round3(stddev),
        }
    }

def make_error(message: str, code: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": message, "code": code}
    )

@app.post("/v1/execute")
async def execute(request: Request):
    try:
        body = await request.json()
    except Exception:
        return make_error("Invalid JSON body", "INVALID_JSON", 400)
    
    # Validate command
    command = body.get("command")
    if not isinstance(command, str) or not command.strip():
        return make_error("Missing or invalid required field: command", "INVALID_COMMAND", 400)
    
    # Validate env
    env = body.get("env", {})
    if not isinstance(env, dict):
        return make_error("Invalid field: env must be an object", "INVALID_ENV", 400)
    for k, v in env.items():
        if not isinstance(k, str) or not isinstance(v, str):
            return make_error("Invalid field: env keys and values must be strings", "INVALID_ENV", 400)
    
    # Validate files
    files = body.get("files", {})
    if not isinstance(files, dict):
        return make_error("Invalid field: files must be an object", "INVALID_FILES", 400)
    for k, v in files.items():
        if not isinstance(k, str) or not isinstance(v, str):
            return make_error("Invalid field: files keys and values must be strings", "INVALID_FILES", 400)
    
    # Validate stdin
    stdin = body.get("stdin", "")
    if isinstance(stdin, list):
        stdin_str = "\n".join(stdin)
    elif isinstance(stdin, str):
        stdin_str = stdin
    else:
        return make_error("Invalid field: stdin must be a string or array of strings", "INVALID_STDIN", 400)
    
    # Validate timeout
    timeout = body.get("timeout", 10)
    if not isinstance(timeout, (int, float)) or timeout <= 0:
        return make_error("Invalid field: timeout must be a positive number", "INVALID_TIMEOUT", 400)
    
    # Create temp working directory
    work_dir = tempfile.mkdtemp(prefix="exec_")
    try:
        # Write files
        for filename, content in files.items():
            # Prevent directory traversal
            safe_name = os.path.basename(filename)
            if safe_name != filename or filename.startswith("/") or ".." in filename:
                # Still try to handle relative paths safely
                filepath = os.path.join(work_dir, filename)
                realpath = os.path.realpath(filepath)
                if not realpath.startswith(os.path.realpath(work_dir) + os.sep) and realpath != os.path.realpath(work_dir):
                    return make_error(f"Invalid file path: {filename}", "INVALID_FILE_PATH", 400)
            else:
                filepath = os.path.join(work_dir, filename)
            
            # Create parent directories if needed
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
        
        # Prepare environment
        run_env = os.environ.copy()
        run_env.update(env)
        
        # Run command
        run_id = str(uuid.uuid4())
        start_time = time.time()
        
        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=work_dir,
            env=run_env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        
        try:
            stdout_data, stderr_data = await asyncio.wait_for(
                proc.communicate(stdin_str.encode("utf-8") if stdin_str else None),
                timeout=timeout,
            )
            end_time = time.time()
            duration = end_time - start_time
            
            stdout_text = stdout_data.decode("utf-8", errors="replace")
            stderr_text = stderr_data.decode("utf-8", errors="replace")
            exit_code = proc.returncode
            timed_out = False
            
        except asyncio.TimeoutError:
            # Process timed out - kill the process group
            end_time = time.time()
            duration = end_time - start_time
            
            # Try to kill the entire process group
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
            except Exception:
                pass
            
            # Wait for process to finish
            try:
                await asyncio.wait_for(proc.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                pass
            except Exception:
                pass
            
            stdout_text = ""
            stderr_text = ""
            exit_code = -1
            timed_out = True
        
        # Update stats
        execution_stats["runs"].append(duration)
        execution_stats["count"] += 1
        
        return JSONResponse(
            status_code=201,
            content={
                "id": run_id,
                "stdout": stdout_text,
                "stderr": stderr_text,
                "exit_code": exit_code,
                "duration": round3(duration),
                "timed_out": timed_out,
            }
        )
        
    except Exception as e:
        return make_error(f"Server error: {str(e)}", "INTERNAL_ERROR", 500)
    finally:
        # Clean up temp directory
        try:
            shutil.rmtree(work_dir, ignore_errors=True)
        except Exception:
            pass

@app.get("/v1/stats/execution")
async def get_stats():
    return JSONResponse(
        status_code=200,
        content=compute_stats()
    )

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--address", type=str, default="0.0.0.0")
    args = parser.parse_args()
    
    uvicorn.run(app, host=args.address, port=args.port)

if __name__ == "__main__":
    main()
