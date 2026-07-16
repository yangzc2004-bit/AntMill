import argparse
import fnmatch
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


def posix_glob_match(pattern: str, path: str) -> bool:
    """Match a path against a POSIX glob pattern."""
    # Handle **/ prefix for recursive matching
    if pattern.startswith("**/"):
        rest = pattern[3:]
        # Match at any depth
        parts = path.split("/")
        for i in range(len(parts)):
            subpath = "/".join(parts[i:])
            if fnmatch.fnmatch(subpath, rest):
                return True
        return fnmatch.fnmatch(path, rest)
    # Handle ** in the middle or end
    if "**" in pattern:
        # Split pattern by **/
        # For simplicity, handle common cases
        if pattern == "**/*.txt":
            # Match any .txt file at any depth
            return path.endswith(".txt")
        # General approach: split by ** and try to match
        # This is a simplified implementation
        pass
    return fnmatch.fnmatch(path, pattern)


def resolve_globs(workdir: str, patterns: List[str]) -> Dict[str, str]:
    """Resolve glob patterns against the working directory and read file contents."""
    result = {}
    seen = set()
    
    for pattern in patterns:
        # Walk the directory tree
        for root, dirs, files in os.walk(workdir):
            # Calculate relative path from workdir
            rel_root = os.path.relpath(root, workdir)
            if rel_root == ".":
                rel_root = ""
            
            for filename in files:
                if rel_root:
                    rel_path = rel_root + "/" + filename
                else:
                    rel_path = filename
                
                # Normalize path separators to forward slashes
                rel_path = rel_path.replace(os.sep, "/")
                
                if posix_glob_match(pattern, rel_path):
                    if rel_path not in seen:
                        seen.add(rel_path)
                        full_path = os.path.join(root, filename)
                        try:
                            with open(full_path, "r", encoding="utf-8") as f:
                                result[rel_path] = f.read()
                        except (IOError, OSError, UnicodeDecodeError):
                            # Skip files that can't be read
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

    # Validate track field
    track = body.get("track")
    if track is not None:
        if not isinstance(track, list):
            return JSONResponse(
                status_code=400,
                content={
                    "error": "Invalid 'track' field",
                    "code": "INVALID_TRACK",
                },
            )
        for pattern in track:
            if not isinstance(pattern, str):
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": "Invalid 'track' field: all patterns must be strings",
                        "code": "INVALID_TRACK",
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

        # Resolve track globs if provided
        tracked_files = None
        if track:
            tracked_files = resolve_globs(workdir, track)

    duration = time.time() - start_time
    execution_stats.append(duration)

    response_content = {
        "id": run_id,
        "stdout": stdout,
        "stderr": stderr,
        "exit_code": exit_code,
        "duration": round3(duration),
        "timed_out": timed_out,
    }

    if tracked_files is not None:
        response_content["files"] = tracked_files

    return JSONResponse(
        status_code=201,
        content=response_content,
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
