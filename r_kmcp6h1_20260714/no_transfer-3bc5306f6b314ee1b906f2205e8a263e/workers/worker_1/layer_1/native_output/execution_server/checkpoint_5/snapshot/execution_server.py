import argparse
import bz2
import csv
import fnmatch
import gzip
import io
import json
import os
import signal
import statistics
import subprocess
import tempfile
import time
import uuid
from typing import Any, Dict, List, Optional

import uvicorn
import yaml
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()

# In-memory storage for execution stats
execution_stats: List[float] = []
command_stats: List[float] = []
command_counts: List[int] = []  # number of commands that actually ran per execution


def round3(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return round(value, 3)


def compute_duration_stats(durations: List[float]) -> Dict[str, Any]:
    if not durations:
        return {
            "average": None,
            "median": None,
            "max": None,
            "min": None,
            "stddev": None,
        }
    avg = statistics.mean(durations)
    med = statistics.median(durations)
    max_val = max(durations)
    min_val = min(durations)
    stddev = statistics.stdev(durations) if len(durations) > 1 else 0.0
    return {
        "average": round3(avg),
        "median": round3(med),
        "max": round3(max_val),
        "min": round3(min_val),
        "stddev": round3(stddev),
    }


def compute_stats() -> Dict[str, Any]:
    if not execution_stats:
        return {
            "ran": 0,
            "commands": {
                "total": 0,
                "ran": 0,
                "average": None,
                "average_ran": None,
                "duration": {
                    "average": None,
                    "median": None,
                    "max": None,
                    "min": None,
                    "stddev": None,
                },
            },
            "duration": {
                "average": None,
                "median": None,
                "max": None,
                "min": None,
                "stddev": None,
            },
        }
    
    total_commands = sum(command_counts)
    ran_commands = len(command_stats)
    
    return {
        "ran": len(execution_stats),
        "commands": {
            "total": total_commands,
            "ran": ran_commands,
            "average": round3(total_commands / len(execution_stats)) if execution_stats else None,
            "average_ran": round3(ran_commands / len(execution_stats)) if execution_stats else None,
            "duration": compute_duration_stats(command_stats),
        },
        "duration": compute_duration_stats(execution_stats),
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
                            # Skip files that can not be read
                            pass
    
    return result


def parse_compression_extensions(filename: str) -> tuple:
    """
    Parse the filename to determine base extension and compression.
    Returns (base_ext, compression) where compression is None, 'gz', or 'bz2'.
    Raises ValueError for multiple compression extensions.
    """
    name, ext = os.path.splitext(filename)
    compression = None
    
    # Check for compression extensions
    if ext.lower() == '.gz':
        compression = 'gz'
        _, base_ext = os.path.splitext(name)
    elif ext.lower() == '.bz2':
        compression = 'bz2'
        _, base_ext = os.path.splitext(name)
    else:
        base_ext = ext
    
    # Check for multiple compression extensions
    if compression:
        remaining_name, remaining_ext = os.path.splitext(name)
        if remaining_ext.lower() in ('.gz', '.bz2'):
            raise ValueError("Multiple compression extensions")
    
    return base_ext.lower(), compression


def serialize_structured_data(filename: str, data: Any) -> str:
    """
    Serialize structured data based on file extension.
    Returns the serialized string content.
    """
    base_ext, compression = parse_compression_extensions(filename)
    
    # Determine the serialization format
    if base_ext in ('.json',):
        content = json.dumps(data, indent=None, separators=(',', ':'))
    elif base_ext in ('.yaml', '.yml'):
        content = yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)
    elif base_ext in ('.jsonl', '.ndjson'):
        lines = []
        for item in data:
            lines.append(json.dumps(item, separators=(',', ':')))
        content = '\n'.join(lines)
        if content:
            content += '\n'
    elif base_ext in ('.csv', '.tsv'):
        delimiter = '	' if base_ext == '.tsv' else ','
        content = serialize_csv_tsv(data, delimiter)
    else:
        # Not a recognized structured format, treat as raw text
        if isinstance(data, str):
            content = data
        else:
            content = json.dumps(data)
    
    # Apply compression if needed
    if compression == 'gz':
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode='wb') as f:
            f.write(content.encode('utf-8'))
        # For gzip, we need to write binary, but the current code writes text
        # We need to handle this at the write level
        return content  # Return raw content, compression handled at write time
    elif compression == 'bz2':
        # Same approach - return raw content, compression handled at write time
        return content
    
    return content


def serialize_csv_tsv(data: Any, delimiter: str = ',') -> str:
    """
    Serialize data to CSV/TSV format.
    Valid formats: dict of columns or list of rows.
    Columns are sorted lexicographically.
    """
    if not data:
        return ""
    
    # Handle dict of columns
    if isinstance(data, dict):
        # Dict of columns: {"col1": [1, 2], "col2": ["a", "b"]}
        columns = sorted(data.keys())
        # Determine the number of rows from the first column
        if not columns:
            return ""
        num_rows = len(data[columns[0]])
        
        output = io.StringIO()
        writer = csv.writer(output, delimiter=delimiter, lineterminator='\n')
        
        # Write header
        writer.writerow(columns)
        
        # Write rows
        for i in range(num_rows):
            row = []
            for col in columns:
                val = data[col][i] if i < len(data[col]) else ""
                if val is None:
                    val = ""
                row.append(val)
            writer.writerow(row)
        
        return output.getvalue()
    
    # Handle list of rows
    elif isinstance(data, list):
        if not data:
            return ""
        
        # Collect all unique keys from all rows
        all_keys = set()
        for row in data:
            if isinstance(row, dict):
                all_keys.update(row.keys())
        
        columns = sorted(all_keys)
        
        output = io.StringIO()
        writer = csv.writer(output, delimiter=delimiter, lineterminator='\n')
        
        # Write header
        writer.writerow(columns)
        
        # Write rows
        for row in data:
            if isinstance(row, dict):
                csv_row = []
                for col in columns:
                    val = row.get(col, "")
                    if val is None:
                        val = ""
                    csv_row.append(val)
                writer.writerow(csv_row)
            else:
                # Single value row
                writer.writerow([row])
        
        return output.getvalue()
    
    else:
        # Fallback for other types
        return str(data)


def write_file(filepath: str, content: str, compression: Optional[str] = None):
    """
    Write content to file, handling compression if needed.
    """
    if compression == 'gz':
        with gzip.open(filepath, 'wt', encoding='utf-8') as f:
            f.write(content)
    elif compression == 'bz2':
        with bz2.open(filepath, 'wt', encoding='utf-8') as f:
            f.write(content)
    else:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)


def run_command(cmd: str, workdir: str, env: Dict[str, str], stdin: str, timeout: float) -> Dict[str, Any]:
    """Run a single command and return the result."""
    cmd_start = time.time()
    try:
        proc = subprocess.Popen(
            cmd,
            shell=True,
            cwd=workdir,
            env=env,
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
        raise RuntimeError(f"Failed to execute command: {str(e)}")
    
    cmd_duration = time.time() - cmd_start
    return {
        "stdout": stdout,
        "stderr": stderr,
        "exit_code": exit_code,
        "duration": round3(cmd_duration),
        "timed_out": timed_out,
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

    # Validate command - can be string (backward compatible) or array of command objects
    command = body.get("command")
    is_chain = False
    commands = []
    
    if isinstance(command, str):
        if not command.strip():
            return JSONResponse(
                status_code=400,
                content={
                    "error": "Missing or invalid 'command' field",
                    "code": "MISSING_COMMAND",
                },
            )
        commands = [{"cmd": command}]
    elif isinstance(command, list):
        is_chain = True
        if not command:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "Missing or invalid 'command' field",
                    "code": "MISSING_COMMAND",
                },
            )
        for i, cmd_obj in enumerate(command):
            if not isinstance(cmd_obj, dict):
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": f"Invalid command at index {i}: must be an object",
                        "code": "INVALID_COMMAND",
                    },
                )
            cmd_str = cmd_obj.get("cmd")
            if not isinstance(cmd_str, str) or not cmd_str.strip():
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": f"Invalid 'cmd' field at index {i}",
                        "code": "INVALID_COMMAND",
                    },
                )
            cmd_entry = {"cmd": cmd_str}
            # Per-command timeout
            cmd_timeout = cmd_obj.get("timeout")
            if cmd_timeout is not None:
                if not isinstance(cmd_timeout, (int, float)) or cmd_timeout <= 0:
                    return JSONResponse(
                        status_code=400,
                        content={
                            "error": f"Invalid 'timeout' field at index {i}",
                            "code": "INVALID_TIMEOUT",
                        },
                    )
                cmd_entry["timeout"] = cmd_timeout
            # Required flag
            cmd_required = cmd_obj.get("required", False)
            if not isinstance(cmd_required, bool):
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": f"Invalid 'required' field at index {i}",
                        "code": "INVALID_REQUIRED",
                    },
                )
            cmd_entry["required"] = cmd_required
            commands.append(cmd_entry)
    else:
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

    default_timeout = body.get("timeout", 10)
    if not isinstance(default_timeout, (int, float)) or default_timeout <= 0:
        return JSONResponse(
            status_code=400,
            content={
                "error": "Invalid 'timeout' field",
                "code": "INVALID_TIMEOUT",
            },
        )

    continue_on_error = body.get("continue_on_error", False)
    if not isinstance(continue_on_error, bool):
        return JSONResponse(
            status_code=400,
            content={
                "error": "Invalid 'continue_on_error' field",
                "code": "INVALID_CONTINUE_ON_ERROR",
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
            
            try:
                if isinstance(content, str):
                    # Raw text - check if compression is needed
                    _, compression = parse_compression_extensions(filename)
                    write_file(filepath, content, compression)
                else:
                    # Structured data - serialize based on extension
                    base_ext, compression = parse_compression_extensions(filename)
                    serialized = serialize_structured_data(filename, content)
                    write_file(filepath, serialized, compression)
            except ValueError as e:
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": str(e),
                        "code": "INVALID_FILE_EXTENSION",
                    },
                )

        # Prepare environment
        run_env = os.environ.copy()
        run_env.update(env)

        # Execute commands
        results = []
        overall_exit_code = 0
        overall_timed_out = False
        total_duration = 0.0
        first_stdin = stdin  # Only first command gets stdin
        stdin_for_cmd = first_stdin
        
        for i, cmd_entry in enumerate(commands):
            cmd_str = cmd_entry["cmd"]
            cmd_timeout = cmd_entry.get("timeout", default_timeout)
            cmd_required = cmd_entry.get("required", False)
            
            # Determine if we should skip this command
            should_skip = False
            if i > 0 and overall_exit_code != 0 and not continue_on_error and not cmd_required:
                should_skip = True
            
            if should_skip:
                # Skip this command - do not include in results
                continue
            
            try:
                result = run_command(cmd_str, workdir, run_env, stdin_for_cmd, cmd_timeout)
            except RuntimeError as e:
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": str(e),
                        "code": "EXECUTION_ERROR",
                    },
                )
            
            # Only first command receives stdin
            stdin_for_cmd = ""
            
            # Build command result
            cmd_result = {
                "cmd": cmd_str,
                "stdout": result["stdout"],
                "stderr": result["stderr"],
                "exit_code": result["exit_code"],
                "duration": result["duration"],
                "timed_out": result["timed_out"],
            }
            if cmd_required:
                cmd_result["required"] = True
            
            results.append(cmd_result)
            
            # Update overall stats
            total_duration += result["duration"]
            if result["timed_out"]:
                overall_timed_out = True
            
            # Update overall exit code (first non-zero)
            if overall_exit_code == 0 and result["exit_code"] != 0:
                overall_exit_code = result["exit_code"]

        # Resolve track globs if provided
        tracked_files = None
        if track:
            tracked_files = resolve_globs(workdir, track)

    duration = time.time() - start_time
    execution_stats.append(duration)
    
    # Track command stats
    command_counts.append(len(commands))
    for r in results:
        command_stats.append(r["duration"])

    if is_chain:
        response_content = {
            "id": run_id,
            "commands": results,
            "exit_code": overall_exit_code,
            "duration": round3(total_duration),
            "timed_out": overall_timed_out,
        }
    else:
        # Backward compatible single command response
        if results:
            r = results[0]
            response_content = {
                "id": run_id,
                "stdout": r["stdout"],
                "stderr": r["stderr"],
                "exit_code": r["exit_code"],
                "duration": r["duration"],
                "timed_out": r["timed_out"],
            }
        else:
            response_content = {
                "id": run_id,
                "stdout": "",
                "stderr": "",
                "exit_code": 0,
                "duration": 0.0,
                "timed_out": False,
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

