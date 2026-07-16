import argparse
import glob
import os
import shutil
import statistics
import subprocess
import tempfile
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# Global stats storage
execution_stats = {
    "runs": [],
    "count": 0,
}

def round3(value):
    """Round to 3 decimal places."""
    if value is None:
        return None
    return round(value, 3)

def make_error_response(status_code, message, code):
    return JSONResponse(
        status_code=status_code,
        content={"error": message, "code": code},
        media_type="application/json",
    )

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = FastAPI(lifespan=lifespan)

@app.post("/v1/execute")
async def execute(request: Request):
    try:
        body = await request.json()
    except Exception:
        return make_error_response(400, "Invalid JSON body", "INVALID_JSON")

    # Validate command
    command = body.get("command")
    if not isinstance(command, str) or not command.strip():
        return make_error_response(400, "Missing or invalid required field: command", "MISSING_REQUIRED_FIELD")

    # Get optional fields
    env = body.get("env", {})
    if env is None:
        env = {}
    if not isinstance(env, dict):
        return make_error_response(400, "Invalid field: env must be an object", "INVALID_FIELD_TYPE")
    for k, v in env.items():
        if not isinstance(v, str):
            return make_error_response(400, f"Invalid env value for key {k}: must be string", "INVALID_FIELD_TYPE")

    files = body.get("files", {})
    if files is None:
        files = {}
    if not isinstance(files, dict):
        return make_error_response(400, "Invalid field: files must be an object", "INVALID_FIELD_TYPE")
    for k, v in files.items():
        if not isinstance(v, str):
            return make_error_response(400, f"Invalid files value for key {k}: must be string", "INVALID_FIELD_TYPE")

    stdin = body.get("stdin", "")
    if stdin is None:
        stdin = ""
    if isinstance(stdin, list):
        stdin = "\n".join(stdin)
    elif not isinstance(stdin, str):
        return make_error_response(400, "Invalid field: stdin must be a string or array", "INVALID_FIELD_TYPE")

    timeout = body.get("timeout", 10)
    if timeout is None:
        timeout = 10
    if not isinstance(timeout, (int, float)) or timeout <= 0:
        return make_error_response(400, "Invalid field: timeout must be a positive number", "INVALID_FIELD_TYPE")

    # Validate track
    track = body.get("track")
    if track is not None:
        if not isinstance(track, list):
            return make_error_response(400, "Invalid field: track must be an array", "INVALID_FIELD_TYPE")
        for i, pattern in enumerate(track):
            if not isinstance(pattern, str):
                return make_error_response(400, f"Invalid track pattern at index {i}: must be a string", "INVALID_FIELD_TYPE")

    run_id = str(uuid.uuid4())

    # Create temp directory and write files
    tmpdir = tempfile.mkdtemp()
    try:
        for fname, fcontent in files.items():
            fpath = os.path.join(tmpdir, fname)
            parent = os.path.dirname(fpath)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(fcontent)

        # Prepare environment
        run_env = os.environ.copy()
        run_env.update(env)

        start_time = time.perf_counter()
        timed_out = False
        exit_code = 0
        stdout = ""
        stderr = ""

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
                stdout, stderr = proc.communicate(input=stdin, timeout=timeout)
                exit_code = proc.returncode
            except subprocess.TimeoutExpired:
                timed_out = True
                exit_code = -1
                # Record duration at timeout point
                end_time = time.perf_counter()
                duration = round3(end_time - start_time)
                # Kill the process and clean up
                proc.kill()
                try:
                    proc.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    proc.terminate()
                    try:
                        proc.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        pass
                # Update stats
                execution_stats["count"] += 1
                execution_stats["runs"].append(duration)

                # Handle tracked files even on timeout
                tracked_files = {}
                if track:
                    try:
                        matched_paths = set()
                        for pattern in track:
                            full_pattern = os.path.join(tmpdir, pattern)
                            matches = glob.glob(full_pattern, recursive=True)
                            for match in matches:
                                if os.path.isfile(match):
                                    rel_path = os.path.relpath(match, tmpdir)
                                    matched_paths.add(rel_path)
                        for rel_path in matched_paths:
                            full_path = os.path.join(tmpdir, rel_path)
                            try:
                                with open(full_path, "r", encoding="utf-8") as f:
                                    tracked_files[rel_path] = f.read()
                            except Exception:
                                pass
                    except Exception as e:
                        return make_error_response(500, f"Failed to resolve track patterns: {str(e)}", "TRACK_RESOLUTION_FAILED")

                response_body = {
                    "id": run_id,
                    "stdout": "",
                    "stderr": "",
                    "exit_code": -1,
                    "duration": duration,
                    "timed_out": True,
                }
                if track:
                    response_body["files"] = tracked_files

                return JSONResponse(
                    status_code=201,
                    content=response_body,
                    media_type="application/json",
                )
        except Exception as e:
            return make_error_response(500, f"Failed to execute command: {str(e)}", "EXECUTION_FAILED")
        finally:
            if not timed_out:
                end_time = time.perf_counter()
                duration = round3(end_time - start_time)

        # Update stats for non-timeout case
        execution_stats["count"] += 1
        execution_stats["runs"].append(duration)

        # Handle tracked files
        tracked_files = {}
        if track:
            try:
                matched_paths = set()
                for pattern in track:
                    full_pattern = os.path.join(tmpdir, pattern)
                    matches = glob.glob(full_pattern, recursive=True)
                    for match in matches:
                        if os.path.isfile(match):
                            rel_path = os.path.relpath(match, tmpdir)
                            matched_paths.add(rel_path)
                for rel_path in matched_paths:
                    full_path = os.path.join(tmpdir, rel_path)
                    try:
                        with open(full_path, "r", encoding="utf-8") as f:
                            tracked_files[rel_path] = f.read()
                    except Exception:
                        pass
            except Exception as e:
                return make_error_response(500, f"Failed to resolve track patterns: {str(e)}", "TRACK_RESOLUTION_FAILED")

        response_body = {
            "id": run_id,
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": exit_code,
            "duration": duration,
            "timed_out": timed_out,
        }
        if track:
            response_body["files"] = tracked_files

        return JSONResponse(
            status_code=201,
            content=response_body,
            media_type="application/json",
        )
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

@app.get("/v1/stats/execution")
async def get_stats():
    count = execution_stats["count"]
    runs = execution_stats["runs"]

    if count == 0:
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
            media_type="application/json",
        )

    return JSONResponse(
        status_code=200,
        content={
            "ran": count,
            "duration": {
                "average": round3(statistics.mean(runs)),
                "median": round3(statistics.median(runs)),
                "max": round3(max(runs)),
                "min": round3(min(runs)),
                "stddev": round3(statistics.stdev(runs)) if count > 1 else 0.0,
            },
        },
        media_type="application/json",
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return make_error_response(500, f"Internal server error: {str(exc)}", "INTERNAL_SERVER_ERROR")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--address", type=str, default="0.0.0.0")
    args = parser.parse_args()

    import uvicorn
    uvicorn.run(app, host=args.address, port=args.port)

if __name__ == "__main__":
    main()
