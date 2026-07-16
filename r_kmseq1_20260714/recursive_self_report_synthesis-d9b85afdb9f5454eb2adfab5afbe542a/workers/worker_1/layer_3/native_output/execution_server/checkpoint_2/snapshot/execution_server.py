import argparse
import json
import os
import signal
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

# In-memory state for execution stats
execution_stats: List[float] = []


def round3(value: float) -> float:
    return round(value, 3)


def error_response(message: str, code: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        content={"error": message, "code": code},
        status_code=status_code,
        headers={"Content-Type": "application/json"},
    )


def validate_request(body: Any) -> tuple[Optional[dict], Optional[JSONResponse]]:
    if not isinstance(body, dict):
        return None, error_response("Request body must be a JSON object", "INVALID_REQUEST_BODY", 400)

    # command: required, non-empty string
    command = body.get("command")
    if command is None:
        return None, error_response("Missing required field: command", "MISSING_COMMAND", 400)
    if not isinstance(command, str) or not command.strip():
        return None, error_response("command must be a non-empty string", "INVALID_COMMAND", 400)

    # env: optional, default {}, must be dict[str, str]
    env = body.get("env", {})
    if not isinstance(env, dict):
        return None, error_response("env must be an object with string keys and values", "INVALID_ENV", 400)
    for k, v in env.items():
        if not isinstance(k, str) or not isinstance(v, str):
            return None, error_response("env must be an object with string keys and values", "INVALID_ENV", 400)

    # files: optional, default {}, must be dict[str, str]
    files = body.get("files", {})
    if not isinstance(files, dict):
        return None, error_response("files must be an object with string keys and values", "INVALID_FILES", 400)
    for k, v in files.items():
        if not isinstance(k, str) or not isinstance(v, str):
            return None, error_response("files must be an object with string keys and values", "INVALID_FILES", 400)

    # stdin: optional, default "", accept string or list of strings
    stdin = body.get("stdin", "")
    if isinstance(stdin, list):
        for item in stdin:
            if not isinstance(item, str):
                return None, error_response("stdin array must contain only strings", "INVALID_STDIN", 400)
        stdin = "\n".join(stdin)
    elif not isinstance(stdin, str):
        return None, error_response("stdin must be a string or array of strings", "INVALID_STDIN", 400)

    # timeout: optional, default 10, must be numeric > 0, exclude bool
    timeout = body.get("timeout", 10)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
        return None, error_response("timeout must be a positive number", "INVALID_TIMEOUT", 400)
    if timeout <= 0:
        return None, error_response("timeout must be a positive number", "INVALID_TIMEOUT", 400)

    # track: optional, default [], must be list of strings
    track = body.get("track", [])
    if not isinstance(track, list):
        return None, error_response("track must be a list of strings", "INVALID_TRACK", 400)
    for item in track:
        if not isinstance(item, str):
            return None, error_response("track must be a list of strings", "INVALID_TRACK", 400)

    return {
        "command": command,
        "env": env,
        "files": files,
        "stdin": stdin,
        "timeout": timeout,
        "track": track,
    }, None


@app.post("/v1/execute")
async def execute(request: Request):
    try:
        body = await request.json()
    except Exception:
        return error_response("Invalid JSON body", "INVALID_JSON", 400)

    validated, err = validate_request(body)
    if err is not None:
        return err

    command = validated["command"]
    env = validated["env"]
    files = validated["files"]
    stdin = validated["stdin"]
    timeout = validated["timeout"]
    track = validated["track"]

    run_id = str(uuid.uuid4())
    timed_out = False
    exit_code = 0
    stdout_data = ""
    stderr_data = ""

    with tempfile.TemporaryDirectory() as tmpdir:
        # Write files
        for rel_path, content in files.items():
            full_path = os.path.join(tmpdir, rel_path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)

        # Prepare environment
        run_env = os.environ.copy()
        run_env.update(env)

        start_time = time.time()
        proc = None
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
            stdout_data, stderr_data = proc.communicate(input=stdin, timeout=timeout)
            exit_code = proc.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
            exit_code = -1
            if proc is not None:
                try:
                    pgid = os.getpgid(proc.pid)
                    os.killpg(pgid, signal.SIGKILL)
                except (ProcessLookupError, OSError):
                    try:
                        proc.kill()
                    except Exception:
                        pass
                try:
                    stdout_data, stderr_data = proc.communicate(timeout=1)
                except Exception:
                    stdout_data = ""
                    stderr_data = ""
        except Exception as e:
            return error_response(f"Execution failed: {str(e)}", "EXECUTION_ERROR", 500)
        finally:
            end_time = time.time()
            if proc is not None and proc.poll() is None:
                try:
                    proc.kill()
                except Exception:
                    pass

        duration = end_time - start_time
        execution_stats.append(duration)

        # Handle track output files
        response_data = {
            "id": run_id,
            "stdout": stdout_data,
            "stderr": stderr_data,
            "exit_code": exit_code,
            "duration": round3(duration),
            "timed_out": timed_out,
        }

        if track:
            import glob
            seen = set()
            track_files = {}
            for pattern in track:
                matched = glob.glob(pattern, root_dir=tmpdir)
                for m in matched:
                    rel = m.replace(os.sep, "/")
                    if rel in seen:
                        continue
                    seen.add(rel)
                    full = os.path.join(tmpdir, m)
                    if os.path.isfile(full):
                        try:
                            with open(full, "r", encoding="utf-8") as f:
                                track_files[rel] = f.read()
                        except Exception:
                            pass
            response_data["files"] = track_files

    return JSONResponse(
        content=response_data,
        status_code=201,
        headers={"Content-Type": "application/json"},
    )


@app.get("/v1/stats/execution")
async def get_stats():
    if not execution_stats:
        return JSONResponse(
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
            status_code=200,
            headers={"Content-Type": "application/json"},
        )

    durations = execution_stats
    n = len(durations)
    avg = statistics.mean(durations)
    med = statistics.median(durations)
    mx = max(durations)
    mn = min(durations)
    if n >= 2:
        std = statistics.stdev(durations)
    else:
        std = 0.0

    return JSONResponse(
        content={
            "ran": n,
            "duration": {
                "average": round3(avg),
                "median": round3(med),
                "max": round3(mx),
                "min": round3(mn),
                "stddev": round3(std),
            },
        },
        status_code=200,
        headers={"Content-Type": "application/json"},
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--address", type=str, default="0.0.0.0")
    args = parser.parse_args()

    uvicorn.run(app, host=args.address, port=args.port, http="h11")


if __name__ == "__main__":
    main()
