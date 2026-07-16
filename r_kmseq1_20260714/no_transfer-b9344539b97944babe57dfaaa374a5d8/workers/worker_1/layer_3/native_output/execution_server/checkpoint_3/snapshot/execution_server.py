import argparse
import bz2
import csv
import fnmatch
import gzip
import io
import json
import math
import os
import statistics
import subprocess
import tempfile
import time
import uuid
from typing import Any, Dict, List, Optional

import yaml
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
    avg = round3(statistics.mean(durations))
    med = round3(statistics.median(durations))
    max_val = round3(max(durations))
    min_val = round3(min(durations))
    if n > 1:
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


def resolve_globs(base_dir: str, patterns: List[str]) -> Dict[str, str]:
    """Resolve globs relative to base_dir and return {relative_path: content}."""
    result = {}
    seen = set()
    for pattern in patterns:
        # Use fnmatch and os.walk for POSIX glob semantics
        # Support **/ recursive glob
        if "**" in pattern:
            # Handle recursive globs
            # Split into prefix and suffix around **/
            parts = pattern.split("**/")
            prefix = parts[0]  # may be empty or contain a directory prefix
            suffix = parts[1] if len(parts) > 1 else ""
            # If prefix is non-empty, start from there; otherwise from base_dir
            if prefix:
                start_dir = os.path.join(base_dir, prefix)
                if not os.path.isdir(start_dir):
                    continue
            else:
                start_dir = base_dir
            # Walk recursively
            for root, dirs, files in os.walk(start_dir):
                for filename in files:
                    if fnmatch.fnmatch(filename, suffix):
                        full_path = os.path.join(root, filename)
                        rel_path = os.path.relpath(full_path, base_dir)
                        if rel_path not in seen:
                            seen.add(rel_path)
                            try:
                                with open(full_path, "r", encoding="utf-8") as f:
                                    result[rel_path] = f.read()
                            except Exception:
                                pass
        else:
            # Non-recursive glob
            # Split pattern into directory and file pattern
            if os.path.sep in pattern:
                dir_part, file_pattern = pattern.rsplit(os.path.sep, 1)
            else:
                dir_part = ""
                file_pattern = pattern
            search_dir = os.path.join(base_dir, dir_part) if dir_part else base_dir
            if not os.path.isdir(search_dir):
                continue
            for filename in os.listdir(search_dir):
                if fnmatch.fnmatch(filename, file_pattern):
                    full_path = os.path.join(search_dir, filename)
                    if os.path.isfile(full_path):
                        rel_path = os.path.relpath(full_path, base_dir)
                        if rel_path not in seen:
                            seen.add(rel_path)
                            try:
                                with open(full_path, "r", encoding="utf-8") as f:
                                    result[rel_path] = f.read()
                            except Exception:
                                pass
    return result


def parse_extension(filename: str):
    """Parse filename to determine base extension and compression.
    Returns (base_ext, compression) or raises ValueError for multiple compression extensions.
    """
    name = filename
    compression = None
    base_ext = None

    # Known compression extensions
    COMPRESSION_EXTS = {".gz", ".bz2"}
    # Known structured data base extensions
    STRUCTURED_EXTS = {".json", ".yaml", ".yml", ".jsonl", ".ndjson", ".csv", ".tsv"}

    while True:
        ext = os.path.splitext(name)[1].lower()
        if ext in COMPRESSION_EXTS:
            if compression is not None:
                raise ValueError("Multiple compression extensions")
            compression = ext
            name = os.path.splitext(name)[0]
        elif ext in STRUCTURED_EXTS:
            base_ext = ext
            break
        else:
            # Not a recognized structured or compression extension
            break

    return base_ext, compression


def serialize_structured_data(filename: str, data: Any) -> str:
    """Convert structured data to string content based on file extension.
    If data is a string, it is treated as raw text regardless of extension.
    """
    # If data is a string, always treat as raw text
    if isinstance(data, str):
        content = data
    else:
        base_ext, compression = parse_extension(filename)

        if base_ext is None:
            # Not a structured extension - data must be a string
            raise ValueError(f"File '{filename}' content must be a string")
        elif base_ext == ".json":
            content = json.dumps(data, ensure_ascii=False)
        elif base_ext in (".yaml", ".yml"):
            content = yaml.dump(data, allow_unicode=True, sort_keys=False)
        elif base_ext in (".jsonl", ".ndjson"):
            if isinstance(data, list):
                lines = []
                for item in data:
                    lines.append(json.dumps(item, ensure_ascii=False))
                content = "\n".join(lines) + "\n"
            else:
                raise ValueError(f"File '{filename}' content must be a list for JSONL/NDJSON")
        elif base_ext in (".csv", ".tsv"):
            delimiter = "\t" if base_ext == ".tsv" else ","
            if isinstance(data, list):
                # List of rows
                if not data:
                    content = ""
                else:
                    # Collect all unique keys, sorted lexicographically
                    all_keys = set()
                    for row in data:
                        if isinstance(row, dict):
                            all_keys.update(row.keys())
                    all_keys = sorted(all_keys)
                    output = io.StringIO()
                    writer = csv.DictWriter(output, fieldnames=all_keys, delimiter=delimiter, lineterminator="\n")
                    writer.writeheader()
                    for row in data:
                        if isinstance(row, dict):
                            writer.writerow(row)
                        else:
                            # If not a dict, write empty row or handle as needed
                            writer.writerow({})
                    content = output.getvalue()
            elif isinstance(data, dict):
                # Dict of columns
                if not data:
                    content = ""
                else:
                    # Sort columns lexicographically
                    columns = sorted(data.keys())
                    # Determine number of rows from first column
                    if not columns:
                        content = ""
                    else:
                        n_rows = len(data[columns[0]])
                        output = io.StringIO()
                        writer = csv.writer(output, delimiter=delimiter, lineterminator="\n")
                        writer.writerow(columns)
                        for i in range(n_rows):
                            row = []
                            for col in columns:
                                val = data[col][i] if i < len(data[col]) else ""
                                row.append(val)
                            writer.writerow(row)
                        content = output.getvalue()
            else:
                raise ValueError(f"File '{filename}' content must be a list or dict for CSV/TSV")
        else:
            # Should not reach here
            raise ValueError(f"File '{filename}' content must be a string")

    # Apply compression if needed
    _, compression = parse_extension(filename)
    if compression:
        if compression == ".gz":
            content_bytes = content.encode("utf-8")
            compressed = gzip.compress(content_bytes)
            return compressed  # type: ignore
        elif compression == ".bz2":
            content_bytes = content.encode("utf-8")
            compressed = bz2.compress(content_bytes)
            return compressed  # type: ignore

    return content


@app.post("/v1/execute")
async def execute(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={
                "error": "Invalid JSON body",
                "code": "MALFORMED_REQUEST",
            },
        )

    # Validate required fields
    if not isinstance(body, dict):
        return JSONResponse(
            status_code=400,
            content={
                "error": "Request body must be a JSON object",
                "code": "MALFORMED_REQUEST",
            },
        )

    command = body.get("command")
    if command is None or not isinstance(command, str) or command.strip() == "":
        return JSONResponse(
            status_code=400,
            content={
                "error": "Missing or invalid required field: command",
                "code": "INVALID_INPUT",
            },
        )

    env = body.get("env", {})
    if not isinstance(env, dict):
        return JSONResponse(
            status_code=400,
            content={
                "error": "Field 'env' must be an object",
                "code": "INVALID_INPUT",
            },
        )
    # Validate env values are strings
    for k, v in env.items():
        if not isinstance(v, str):
            return JSONResponse(
                status_code=400,
                content={
                    "error": f"Environment variable '{k}' must be a string",
                    "code": "INVALID_INPUT",
                },
            )

    files = body.get("files", {})
    if not isinstance(files, dict):
        return JSONResponse(
            status_code=400,
            content={
                "error": "Field 'files' must be an object",
                "code": "INVALID_INPUT",
            },
        )
    # Validate and convert file values
    converted_files = {}
    for k, v in files.items():
        try:
            content = serialize_structured_data(k, v)
            converted_files[k] = content
        except ValueError as e:
            return JSONResponse(
                status_code=400,
                content={
                    "error": str(e),
                    "code": "INVALID_INPUT",
                },
            )

    stdin = body.get("stdin", "")
    if isinstance(stdin, list):
        stdin_str = "\n".join(stdin)
    elif isinstance(stdin, str):
        stdin_str = stdin
    else:
        return JSONResponse(
            status_code=400,
            content={
                "error": "Field 'stdin' must be a string or array of strings",
                "code": "INVALID_INPUT",
            },
        )

    timeout = body.get("timeout", 10)
    if not isinstance(timeout, (int, float)) or timeout <= 0:
        return JSONResponse(
            status_code=400,
            content={
                "error": "Field 'timeout' must be a positive number",
                "code": "INVALID_INPUT",
            },
        )

    # Validate track field
    track = body.get("track")
    if track is not None:
        if not isinstance(track, list):
            return JSONResponse(
                status_code=400,
                content={
                    "error": "Field 'track' must be an array of strings",
                    "code": "INVALID_INPUT",
                },
            )
        for pattern in track:
            if not isinstance(pattern, str):
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": "Each item in 'track' must be a string",
                        "code": "INVALID_INPUT",
                    },
                )

    run_id = str(uuid.uuid4())

    # Create temp working directory
    with tempfile.TemporaryDirectory() as tmpdir:
        # Write files
        for filename, content in converted_files.items():
            filepath = os.path.join(tmpdir, filename)
            # Ensure parent directories exist
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            if isinstance(content, bytes):
                with open(filepath, "wb") as f:
                    f.write(content)
            else:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)

        # Prepare environment
        run_env = os.environ.copy()
        run_env.update(env)

        timed_out = False
        exit_code = 0
        stdout = ""
        stderr = ""

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
                exit_code = proc.returncode
            except subprocess.TimeoutExpired:
                timed_out = True
                # Measure duration at timeout detection
                duration = time.time() - start_time
                proc.kill()
                try:
                    stdout, stderr = proc.communicate(timeout=1)
                except Exception:
                    stdout = ""
                    stderr = ""
                exit_code = -1
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={
                    "error": f"Failed to execute command: {str(e)}",
                    "code": "EXECUTION_ERROR",
                },
            )

        if not timed_out:
            duration = time.time() - start_time

        # Resolve tracked files after command completes
        tracked_files = None
        if track:
            tracked_files = resolve_globs(tmpdir, track)

    duration_rounded = round3(duration)

    # Store duration for stats
    execution_stats.append(duration)

    response_body = {
        "id": run_id,
        "stdout": stdout,
        "stderr": stderr,
        "exit_code": exit_code,
        "duration": duration_rounded,
        "timed_out": timed_out,
    }

    if tracked_files is not None:
        response_body["files"] = tracked_files

    return JSONResponse(status_code=201, content=response_body)


@app.get("/v1/stats/execution")
async def get_stats():
    stats = compute_stats(execution_stats)
    return JSONResponse(status_code=200, content=stats)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "error": f"Internal server error: {str(exc)}",
            "code": "INTERNAL_ERROR",
        },
    )


def main():
    parser = argparse.ArgumentParser(description="Local runner execution server")
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on")
    parser.add_argument("--address", type=str, default="0.0.0.0", help="Address to bind to")
    args = parser.parse_args()

    uvicorn.run(app, host=args.address, port=args.port)


if __name__ == "__main__":
    main()
