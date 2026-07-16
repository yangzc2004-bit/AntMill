import argparse
import asyncio
import bz2
import csv
import gzip
import io
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

import yaml
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
import uvicorn
import wcmatch.glob as glob

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

def parse_filename(filename: str):
    """Parse filename to determine base extension and compression.
    Returns (base_ext, compression) or raises ValueError for invalid combinations.
    """
    parts = filename.split(".")
    # Valid compression extensions
    compressions = {"gz", "bz2"}
    # Valid base extensions for structured data
    structured_exts = {"json", "yaml", "yml", "jsonl", "ndjson", "csv", "tsv"}
    
    compression = None
    base_ext = None
    
    # Check last part
    if parts[-1] in compressions:
        compression = parts[-1]
        # Check second to last part
        if len(parts) >= 2 and parts[-2] in compressions:
            raise ValueError("Multiple compression extensions")
        if len(parts) >= 2 and parts[-2] in structured_exts:
            base_ext = parts[-2]
        elif len(parts) >= 2:
            # e.g. file.txt.gz - not a structured base ext
            base_ext = parts[-2]
    elif parts[-1] in structured_exts:
        base_ext = parts[-1]
    elif len(parts) >= 2 and parts[-1] in compressions:
        # Already handled above
        pass
    
    return base_ext, compression

def is_structured_ext(ext: Optional[str]) -> bool:
    if ext is None:
        return False
    return ext in {"json", "yaml", "yml", "jsonl", "ndjson", "csv", "tsv"}

def serialize_content(content: Any, base_ext: Optional[str], compression: Optional[str]) -> bytes:
    """Serialize content based on file extension and compression."""
    
    if base_ext == "json":
        text = json.dumps(content, ensure_ascii=False)
        data = text.encode("utf-8")
    elif base_ext in ("yaml", "yml"):
        text = yaml.dump(content, allow_unicode=True, sort_keys=False)
        data = text.encode("utf-8")
    elif base_ext in ("jsonl", "ndjson"):
        if isinstance(content, list):
            lines = [json.dumps(item, ensure_ascii=False) for item in content]
            text = "\n".join(lines)
            if text:
                text += "\n"
            data = text.encode("utf-8")
        else:
            # Single item
            text = json.dumps(content, ensure_ascii=False) + "\n"
            data = text.encode("utf-8")
    elif base_ext in ("csv", "tsv"):
        delimiter = "\t" if base_ext == "tsv" else ","
        
        # Handle empty content
        if content == "" or content == [] or content == {}:
            data = b"\n"
        elif isinstance(content, list):
            if len(content) == 0:
                data = b"\n"
            else:
                # Determine all columns by union of keys, sorted lexicographically
                all_keys = set()
                for row in content:
                    if isinstance(row, dict):
                        all_keys.update(row.keys())
                columns = sorted(all_keys)
                
                output = io.StringIO()
                writer = csv.DictWriter(output, fieldnames=columns, delimiter=delimiter, lineterminator="\n")
                writer.writeheader()
                for row in content:
                    if isinstance(row, dict):
                        writer.writerow(row)
                    else:
                        # Non-dict row: write as dict with single key? Or treat as value?
                        # Based on spec: valid formats are dict of columns or list of rows
                        # For list of rows, each row should be a dict
                        # If row is not a dict, we need to handle it somehow
                        # Let's create a row with the row value under... unclear. 
                        # Looking at examples: [{"id":1}, {"name":"x"}] -> id,name\n1,\n,x\n
                        # So each row is a dict, and missing columns are empty
                        pass
                text = output.getvalue()
                data = text.encode("utf-8")
        elif isinstance(content, dict):
            # Dict of columns: {"col1": [v1, v2], "col2": [v1, v2]}
            columns = sorted(content.keys())
            if len(columns) == 0:
                data = b"\n"
            else:
                # Determine number of rows
                num_rows = 0
                for col in columns:
                    if isinstance(content[col], list):
                        num_rows = max(num_rows, len(content[col]))
                
                output = io.StringIO()
                writer = csv.writer(output, delimiter=delimiter, lineterminator="\n")
                writer.writerow(columns)
                for i in range(num_rows):
                    row = []
                    for col in columns:
                        if isinstance(content[col], list) and i < len(content[col]):
                            row.append(content[col][i])
                        else:
                            row.append("")
                    writer.writerow(row)
                text = output.getvalue()
                data = text.encode("utf-8")
        else:
            # Fallback: treat as string
            text = str(content)
            data = text.encode("utf-8")
    else:
        # Raw text
        if isinstance(content, str):
            data = content.encode("utf-8")
        else:
            text = json.dumps(content, ensure_ascii=False)
            data = text.encode("utf-8")
    
    # Apply compression
    if compression == "gz":
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb") as f:
            f.write(data)
        data = buf.getvalue()
    elif compression == "bz2":
        data = bz2.compress(data)
    
    return data

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
        if not isinstance(k, str):
            return make_error("Invalid field: files keys must be strings", "INVALID_FILES", 400)
        # Values can be strings or structured data (dict/list)
        if not isinstance(v, (str, dict, list)):
            return make_error("Invalid field: files values must be strings or structured data", "INVALID_FILES", 400)
    
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
    
    # Validate track
    track = body.get("track")
    if track is not None:
        if not isinstance(track, list):
            return make_error("Invalid field: track must be an array", "INVALID_TRACK", 400)
        for pattern in track:
            if not isinstance(pattern, str):
                return make_error("Invalid field: track patterns must be strings", "INVALID_TRACK", 400)
    
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
            
            # Parse filename for extension and compression
            try:
                base_ext, compression = parse_filename(filename)
            except ValueError as e:
                return make_error(f"Invalid file: {str(e)}", "INVALID_FILE", 400)
            
            # Determine if we need structured serialization
            if isinstance(content, (dict, list)) and is_structured_ext(base_ext):
                data = serialize_content(content, base_ext, compression)
            elif isinstance(content, str):
                data = content.encode("utf-8")
                if compression:
                    if compression == "gz":
                        buf = io.BytesIO()
                        with gzip.GzipFile(fileobj=buf, mode="wb") as f:
                            f.write(data)
                        data = buf.getvalue()
                    elif compression == "bz2":
                        data = bz2.compress(data)
            else:
                # Structured content with non-structured extension, or other cases
                # Serialize as JSON string
                text = json.dumps(content, ensure_ascii=False)
                data = text.encode("utf-8")
                if compression:
                    if compression == "gz":
                        buf = io.BytesIO()
                        with gzip.GzipFile(fileobj=buf, mode="wb") as f:
                            f.write(data)
                        data = buf.getvalue()
                    elif compression == "bz2":
                        data = bz2.compress(data)
            
            # Create parent directories if needed
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, "wb") as f:
                f.write(data)
        
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
        
        # Build response
        response_content = {
            "id": run_id,
            "stdout": stdout_text,
            "stderr": stderr_text,
            "exit_code": exit_code,
            "duration": round3(duration),
            "timed_out": timed_out,
        }
        
        # Track files if requested
        if track:
            tracked_files = {}
            matched_paths = set()
            
            for pattern in track:
                # Use wcmatch.glob for POSIX glob matching with GLOBSTAR support
                # GLOBSTAR enables ** to match across directories
                # FORCEUNIX ensures POSIX-style matching
                matches = glob.glob(
                    pattern,
                    flags=glob.GLOBSTAR | glob.FORCEUNIX,
                    root_dir=work_dir
                )
                for match in matches:
                    # match is relative to root_dir
                    matched_paths.add(match)
            
            for rel_path in matched_paths:
                full_path = os.path.join(work_dir, rel_path)
                try:
                    with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                        tracked_files[rel_path] = f.read()
                except Exception:
                    # Skip files that can't be read
                    pass
            
            response_content["files"] = tracked_files
        
        return JSONResponse(
            status_code=201,
            content=response_content
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
