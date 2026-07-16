import argparse
import asyncio
import bz2
import csv
import gzip
import io
import json
import math
import os
import statistics
import tempfile
import time
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
import uvicorn
from wcmatch import glob
import yaml

app = FastAPI()

# In-memory storage for execution stats
execution_stats: List[float] = []


def round3(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return round(value, 3)


def make_error_response(status_code: int, message: str, code: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": message, "code": code},
    )


def parse_file_extension(filename: str) -> Tuple[Optional[str], Optional[str], bool]:
    """
    Parse a filename to determine its base extension, compression, and validity.
    Returns (base_ext, compression, is_valid)
    - base_ext: the base extension like 'json', 'csv', etc.
    - compression: 'gz', 'bz2', or None
    - is_valid: False if multiple compression extensions (400 error)
    """
    name = filename.lower()
    parts = name.split('.')
    
    # No extension or just one part
    if len(parts) <= 1:
        return None, None, True
    
    # Check for compression from the end
    compression = None
    base_ext = None
    is_valid = True
    
    # Start from the end and work backwards
    ext_parts = parts[1:]  # skip the filename part
    
    # Check last part for compression
    if ext_parts[-1] in ('gz', 'bz2'):
        compression = ext_parts[-1]
        ext_parts = ext_parts[:-1]
        # Check if there's another compression extension
        if ext_parts and ext_parts[-1] in ('gz', 'bz2'):
            is_valid = False
    
    # The remaining last part is the base extension
    if ext_parts:
        base_ext = ext_parts[-1]
    
    return base_ext, compression, is_valid


def serialize_structured_data(filename: str, data: Any) -> str:
    """
    Serialize structured data based on file extension.
    Returns the serialized string content.
    """
    base_ext, compression, is_valid = parse_file_extension(filename)
    
    if not is_valid:
        raise ValueError("Multiple compression extensions")
    
    # Determine the content to write
    content = ""
    
    if base_ext in ('json',):
        if isinstance(data, str):
            # If data is already a string, treat as raw text
            content = data
        else:
            content = json.dumps(data, indent=None, separators=(', ', ': '), ensure_ascii=False)
            # Add trailing newline for JSON files
            content += "\n"
    elif base_ext in ('yaml', 'yml'):
        if isinstance(data, str):
            content = data
        else:
            content = yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)
    elif base_ext in ('jsonl', 'ndjson'):
        if isinstance(data, str):
            content = data
        else:
            lines = []
            if isinstance(data, list):
                for item in data:
                    lines.append(json.dumps(item, ensure_ascii=False))
            else:
                lines.append(json.dumps(data, ensure_ascii=False))
            content = "\n".join(lines)
            if content:
                content += "\n"
    elif base_ext in ('csv', 'tsv'):
        if isinstance(data, str):
            content = data
        else:
            # Valid formats are dict of columns or list of rows
            # Columns sorted lexicographically
            if isinstance(data, dict):
                # dict of columns
                columns = sorted(data.keys())
                if not columns:
                    content = ""
                else:
                    # Determine number of rows
                    num_rows = 0
                    for col in columns:
                        if isinstance(data[col], list):
                            num_rows = max(num_rows, len(data[col]))
                    
                    # Build rows
                    output = io.StringIO()
                    delimiter = '\t' if base_ext == 'tsv' else ','
                    writer = csv.writer(output, delimiter=delimiter, lineterminator='\n')
                    
                    # Header
                    writer.writerow(columns)
                    
                    # Data rows
                    for row_idx in range(num_rows):
                        row = []
                        for col in columns:
                            val = data[col][row_idx] if row_idx < len(data[col]) else ""
                            # Convert None to empty string
                            if val is None:
                                val = ""
                            row.append(val)
                        writer.writerow(row)
                    
                    content = output.getvalue()
            elif isinstance(data, list):
                # list of rows
                if not data:
                    content = ""
                else:
                    # Collect all unique keys from all rows
                    all_keys = set()
                    for row in data:
                        if isinstance(row, dict):
                            all_keys.update(row.keys())
                    columns = sorted(all_keys)
                    
                    output = io.StringIO()
                    delimiter = '\t' if base_ext == 'tsv' else ','
                    writer = csv.writer(output, delimiter=delimiter, lineterminator='\n')
                    
                    # Header
                    writer.writerow(columns)
                    
                    # Data rows
                    for row in data:
                        if isinstance(row, dict):
                            row_vals = []
                            for col in columns:
                                val = row.get(col, "")
                                if val is None:
                                    val = ""
                                row_vals.append(val)
                            writer.writerow(row_vals)
                        else:
                            # Single value row
                            writer.writerow([row])
                    
                    content = output.getvalue()
            else:
                # Single item, treat as one row
                output = io.StringIO()
                delimiter = '\t' if base_ext == 'tsv' else ','
                writer = csv.writer(output, delimiter=delimiter, lineterminator='\n')
                writer.writerow([data])
                content = output.getvalue()
    else:
        # Raw text for unsupported extensions
        if isinstance(data, str):
            content = data
        else:
            content = str(data)
    
    # Apply compression if needed
    if compression == 'gz':
        content_bytes = content.encode('utf-8')
        compressed = gzip.compress(content_bytes)
        # For compressed files, we need to write bytes
        # Use latin-1 to preserve byte values as string
        return compressed.decode('latin-1')
    elif compression == 'bz2':
        content_bytes = content.encode('utf-8')
        compressed = bz2.compress(content_bytes)
        return compressed.decode('latin-1')
    
    return content


def validate_execute_request(body: Dict[str, Any]) -> tuple:
    # Check command
    if "command" not in body:
        return None, make_error_response(400, "Missing required field: command", "MISSING_COMMAND")
    command = body["command"]
    if not isinstance(command, str) or not command.strip():
        return None, make_error_response(400, "command must be a non-empty string", "INVALID_COMMAND")

    # Check env
    env = body.get("env", {})
    if not isinstance(env, dict):
        return None, make_error_response(400, "env must be an object", "INVALID_ENV")
    for k, v in env.items():
        if not isinstance(k, str) or not isinstance(v, str):
            return None, make_error_response(400, "env keys and values must be strings", "INVALID_ENV")

    # Check files
    files = body.get("files", {})
    if not isinstance(files, dict):
        return None, make_error_response(400, "files must be an object", "INVALID_FILES")
    for k, v in files.items():
        if not isinstance(k, str):
            return None, make_error_response(400, "files keys must be strings", "INVALID_FILES")
        # Check for multiple compression extensions for ALL files
        _, _, is_valid = parse_file_extension(k)
        if not is_valid:
            return None, make_error_response(400, "Multiple compression extensions are not allowed", "INVALID_FILE_EXTENSION")

    # Check stdin
    stdin = body.get("stdin", "")
    if isinstance(stdin, list):
        for item in stdin:
            if not isinstance(item, str):
                return None, make_error_response(400, "stdin array items must be strings", "INVALID_STDIN")
        stdin_str = "\n".join(stdin)
    elif isinstance(stdin, str):
        stdin_str = stdin
    else:
        return None, make_error_response(400, "stdin must be a string or array of strings", "INVALID_STDIN")

    # Check timeout
    timeout = body.get("timeout", 10)
    if not isinstance(timeout, (int, float)) or timeout <= 0:
        return None, make_error_response(400, "timeout must be a number greater than 0", "INVALID_TIMEOUT")

    # Check track
    track = body.get("track", None)
    if track is not None:
        if not isinstance(track, list):
            return None, make_error_response(400, "track must be an array", "INVALID_TRACK")
        for item in track:
            if not isinstance(item, str):
                return None, make_error_response(400, "track items must be strings", "INVALID_TRACK")

    return {
        "command": command,
        "env": env,
        "files": files,
        "stdin": stdin_str,
        "timeout": timeout,
        "track": track,
    }, None


@app.post("/v1/execute")
async def execute(request: Request):
    try:
        body = await request.json()
    except Exception:
        return make_error_response(400, "Invalid JSON body", "INVALID_JSON")

    if not isinstance(body, dict):
        return make_error_response(400, "Request body must be a JSON object", "INVALID_BODY")

    validated, error = validate_execute_request(body)
    if error:
        return error

    run_id = str(uuid.uuid4())

    # Create temp working directory
    with tempfile.TemporaryDirectory() as tmpdir:
        # Write files
        for filename, content in validated["files"].items():
            filepath = os.path.join(tmpdir, filename)
            # Ensure parent directories exist
            os.makedirs(os.path.dirname(filepath) or tmpdir, exist_ok=True)
            
            # Determine if content is structured data or raw string
            if isinstance(content, str):
                file_content = content
                is_compressed = False
            else:
                # Serialize structured data
                try:
                    file_content = serialize_structured_data(filename, content)
                except ValueError as e:
                    return make_error_response(400, str(e), "SERIALIZATION_ERROR")
                
                # Check if compression was applied
                base_ext, compression, _ = parse_file_extension(filename)
                is_compressed = compression in ('gz', 'bz2')
            
            # Write file
            if is_compressed:
                # For compressed files, the content was encoded with latin-1
                # We need to write bytes
                with open(filepath, "wb") as f:
                    f.write(file_content.encode('latin-1'))
            else:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(file_content)

        # Prepare environment
        run_env = os.environ.copy()
        run_env.update(validated["env"])

        # Execute command
        start_time = time.time()
        try:
            proc = await asyncio.create_subprocess_shell(
                validated["command"],
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.PIPE,
                env=run_env,
                cwd=tmpdir,
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(input=validated["stdin"].encode("utf-8")),
                    timeout=validated["timeout"],
                )
                timed_out = False
                exit_code = proc.returncode
                if exit_code is None:
                    exit_code = -1
            except asyncio.TimeoutError:
                timed_out = True
                try:
                    proc.kill()
                    await proc.wait()
                except Exception:
                    pass
                stdout_bytes = b""
                stderr_bytes = b""
                exit_code = -1

        except Exception as e:
            return make_error_response(500, f"Failed to execute command: {str(e)}", "EXECUTION_FAILED")

        end_time = time.time()
        duration = end_time - start_time

        # Track files if requested
        tracked_files = None
        track = validated.get("track")
        if track is not None and len(track) > 0:
            tracked_files = {}
            matched_paths: Set[str] = set()
            for pattern in track:
                matches = glob.glob(
                    pattern,
                    root_dir=tmpdir,
                    flags=glob.GLOBSTAR,
                )
                for match in matches:
                    if match not in matched_paths:
                        matched_paths.add(match)
                        file_path = os.path.join(tmpdir, match)
                        # Only track files (not directories)
                        if os.path.isfile(file_path):
                            try:
                                # Check if file is compressed
                                base_ext, compression, _ = parse_file_extension(match)
                                if compression in ('gz', 'bz2'):
                                    # Read as bytes and decompress
                                    with open(file_path, "rb") as f:
                                        file_bytes = f.read()
                                    if compression == 'gz':
                                        decompressed = gzip.decompress(file_bytes)
                                    else:
                                        decompressed = bz2.decompress(file_bytes)
                                    tracked_files[match] = decompressed.decode('utf-8', errors='replace')
                                else:
                                    with open(file_path, "r", encoding="utf-8") as f:
                                        tracked_files[match] = f.read()
                            except Exception:
                                # Skip files that can't be read
                                pass

    # Decode outputs
    try:
        stdout = stdout_bytes.decode("utf-8", errors="replace")
    except Exception:
        stdout = ""

    try:
        stderr = stderr_bytes.decode("utf-8", errors="replace")
    except Exception:
        stderr = ""

    # Update stats
    execution_stats.append(duration)

    response_data = {
        "id": run_id,
        "stdout": stdout,
        "stderr": stderr,
        "exit_code": exit_code,
        "duration": round3(duration),
        "timed_out": timed_out,
    }

    if tracked_files is not None:
        response_data["files"] = tracked_files

    return JSONResponse(status_code=201, content=response_data)


@app.get("/v1/stats/execution")
async def get_stats():
    ran = len(execution_stats)
    if ran == 0:
        duration_stats = {
            "average": None,
            "median": None,
            "max": None,
            "min": None,
            "stddev": None,
        }
    else:
        durations = execution_stats
        avg = statistics.mean(durations)
        med = statistics.median(durations)
        max_d = max(durations)
        min_d = min(durations)
        if ran > 1:
            stddev = statistics.stdev(durations)
        else:
            stddev = 0.0

        duration_stats = {
            "average": round3(avg),
            "median": round3(med),
            "max": round3(max_d),
            "min": round3(min_d),
            "stddev": round3(stddev),
        }

    return JSONResponse(
        status_code=200,
        content={
            "ran": ran,
            "duration": duration_stats,
        },
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return make_error_response(500, "Internal server error", "INTERNAL_ERROR")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--address", type=str, default="0.0.0.0")
    args = parser.parse_args()

    uvicorn.run(app, host=args.address, port=args.port)


if __name__ == "__main__":
    main()
