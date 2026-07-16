import argparse
import csv
import glob
import gzip
import io
import json
import os
import shutil
import statistics
import subprocess
import tempfile
import time
import uuid
import bz2
from contextlib import asynccontextmanager

import yaml
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# Global stats storage
execution_stats = {
    "runs": [],
    "count": 0,
    "commands_total": 0,
    "commands_ran": 0,
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

def get_file_extension_info(fname):
    """Returns (base_ext, compression) based on filename."""
    parts = fname.lower().split(".")
    compression = None
    base_ext = None
    if len(parts) >= 2:
        last = parts[-1]
        if last in ("gz", "bz2"):
            compression = last
            if len(parts) >= 3:
                second_last = parts[-2]
                if second_last in ("gz", "bz2"):
                    raise ValueError("Multiple compression extensions")
                if second_last in ("json", "yaml", "yml", "jsonl", "ndjson", "csv", "tsv"):
                    base_ext = "." + second_last
                else:
                    base_ext = None
            else:
                base_ext = None
        elif last in ("json", "yaml", "yml", "jsonl", "ndjson", "csv", "tsv"):
            base_ext = "." + last
        else:
            base_ext = None
    return base_ext, compression

def serialize_structured_data(data, base_ext):
    """Serialize structured data to string based on file extension."""
    if base_ext == ".json":
        return json.dumps(data)
    elif base_ext in (".yaml", ".yml"):
        return yaml.dump(data, allow_unicode=True, sort_keys=False)
    elif base_ext in (".jsonl", ".ndjson"):
        if isinstance(data, list):
            lines = []
            for item in data:
                lines.append(json.dumps(item))
            return "\n".join(lines) + "\n"
        else:
            return json.dumps(data) + "\n"
    elif base_ext in (".csv", ".tsv"):
        if isinstance(data, list):
            if len(data) == 0:
                return "\n"
            all_keys = sorted(set().union(*(d.keys() for d in data if isinstance(d, dict))))
            delimiter = "\t" if base_ext == ".tsv" else ","
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=all_keys, lineterminator="\n", delimiter=delimiter)
            writer.writeheader()
            writer.writerows(data)
            result = output.getvalue()
            return result
        elif isinstance(data, dict):
            if len(data) == 0:
                return "\n"
            columns = sorted(data.keys())
            first_col = data[columns[0]]
            if isinstance(first_col, list):
                num_rows = len(first_col)
            else:
                num_rows = 1
            delimiter = "\t" if base_ext == ".tsv" else ","
            output = io.StringIO()
            writer = csv.writer(output, lineterminator="\n", delimiter=delimiter)
            writer.writerow(columns)
            for i in range(num_rows):
                row = []
                for col in columns:
                    val = data[col]
                    if isinstance(val, list):
                        row.append(val[i] if i < len(val) else "")
                    else:
                        row.append(val if i == 0 else "")
                writer.writerow(row)
            result = output.getvalue()
            return result
        else:
            return str(data) + "\n"
    else:
        return str(data)

def compress_data(content, compression):
    """Compress content string based on compression type."""
    encoded = content.encode("utf-8")
    if compression == "gz":
        return gzip.compress(encoded)
    elif compression == "bz2":
        return bz2.compress(encoded)
    else:
        return encoded

def write_file(fpath, data, base_ext, compression):
    """Write data to file, serializing if necessary."""
    if isinstance(data, str):
        content = data
    elif isinstance(data, (int, float, bool)):
        content = str(data)
    else:
        if base_ext is None:
            content = str(data)
        else:
            if isinstance(data, str) and data == "":
                if base_ext in (".csv", ".tsv", ".jsonl", ".ndjson"):
                    content = "\n"
                else:
                    content = serialize_structured_data(data, base_ext)
            else:
                content = serialize_structured_data(data, base_ext)
    compressed = compress_data(content, compression)
    with open(fpath, "wb") as f:
        f.write(compressed)

def is_valid_file_value(v):
    """Check if a value is valid for a file (string, dict, list, number, bool)."""
    return isinstance(v, (str, dict, list, int, float, bool))

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
    is_chain = isinstance(command, list)
    is_string = isinstance(command, str)

    if is_string:
        if not command.strip():
            return make_error_response(400, "Missing or invalid required field: command", "MISSING_REQUIRED_FIELD")
    elif is_chain:
        if len(command) == 0:
            return make_error_response(400, "Missing or invalid required field: command", "MISSING_REQUIRED_FIELD")
        for i, cmd_obj in enumerate(command):
            if not isinstance(cmd_obj, dict):
                return make_error_response(400, f"Invalid command at index {i}: must be an object", "INVALID_FIELD_TYPE")
            if "cmd" not in cmd_obj or not isinstance(cmd_obj.get("cmd"), str) or not cmd_obj.get("cmd").strip():
                return make_error_response(400, f"Missing or invalid required field: command[{i}].cmd", "MISSING_REQUIRED_FIELD")
            if "timeout" in cmd_obj:
                t = cmd_obj["timeout"]
                if t is not None and (not isinstance(t, (int, float)) or t <= 0):
                    return make_error_response(400, f"Invalid field: command[{i}].timeout must be a positive number", "INVALID_FIELD_TYPE")
            if "required" in cmd_obj:
                r = cmd_obj["required"]
                if not isinstance(r, bool):
                    return make_error_response(400, f"Invalid field: command[{i}].required must be a boolean", "INVALID_FIELD_TYPE")
    else:
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
        try:
            base_ext, compression = get_file_extension_info(k)
        except ValueError:
            return make_error_response(400, f"Invalid file name {k}: multiple compression extensions", "INVALID_FILE_NAME")
        if not is_valid_file_value(v):
            return make_error_response(400, f"Invalid files value for key {k}: must be string, object, array, number, or boolean", "INVALID_FIELD_TYPE")

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

    continue_on_error = body.get("continue_on_error", False)
    if not isinstance(continue_on_error, bool):
        return make_error_response(400, "Invalid field: continue_on_error must be a boolean", "INVALID_FIELD_TYPE")

    track = body.get("track")
    if track is not None:
        if not isinstance(track, list):
            return make_error_response(400, "Invalid field: track must be an array", "INVALID_FIELD_TYPE")
        for i, pattern in enumerate(track):
            if not isinstance(pattern, str):
                return make_error_response(400, f"Invalid track pattern at index {i}: must be a string", "INVALID_FIELD_TYPE")

    run_id = str(uuid.uuid4())

    tmpdir = tempfile.mkdtemp()
    try:
        for fname, fcontent in files.items():
            fpath = os.path.join(tmpdir, fname)
            parent = os.path.dirname(fpath)
            if parent:
                os.makedirs(parent, exist_ok=True)
            base_ext, compression = get_file_extension_info(fname)
            write_file(fpath, fcontent, base_ext, compression)

        run_env = os.environ.copy()
        run_env.update(env)

        if is_string:
            # Backward-compatible single command execution
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
                    end_time = time.perf_counter()
                    duration = round3(end_time - start_time)
                    proc.kill()
                    try:
                        proc.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        proc.terminate()
                        try:
                            proc.wait(timeout=1)
                        except subprocess.TimeoutExpired:
                            pass
                    execution_stats["count"] += 1
                    execution_stats["runs"].append(duration)
                    execution_stats["commands_total"] += 1
                    execution_stats["commands_ran"] += 1

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

            execution_stats["count"] += 1
            execution_stats["runs"].append(duration)
            execution_stats["commands_total"] += 1
            execution_stats["commands_ran"] += 1

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
        else:
            # Chain execution
            commands_results = []
            overall_start_time = time.perf_counter()
            overall_timed_out = False
            overall_exit_code = 0
            has_failed = False
            stdin_used = False

            for cmd_obj in command:
                cmd_str = cmd_obj["cmd"]
                cmd_timeout = cmd_obj.get("timeout", timeout)
                if cmd_timeout is None:
                    cmd_timeout = timeout
                cmd_required = cmd_obj.get("required", False)

                # Skip non-required commands if we have failed and not continuing
                if has_failed and not cmd_required and not continue_on_error:
                    continue

                cmd_start_time = time.perf_counter()
                cmd_timed_out = False
                cmd_exit_code = 0
                cmd_stdout = ""
                cmd_stderr = ""

                try:
                    proc = subprocess.Popen(
                        cmd_str,
                        shell=True,
                        cwd=tmpdir,
                        env=run_env,
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                    )
                    try:
                        if not stdin_used:
                            cmd_stdout, cmd_stderr = proc.communicate(input=stdin, timeout=cmd_timeout)
                            stdin_used = True
                        else:
                            cmd_stdout, cmd_stderr = proc.communicate(timeout=cmd_timeout)
                        cmd_exit_code = proc.returncode
                    except subprocess.TimeoutExpired:
                        cmd_timed_out = True
                        cmd_exit_code = -1
                        proc.kill()
                        try:
                            proc.wait(timeout=1)
                        except subprocess.TimeoutExpired:
                            proc.terminate()
                            try:
                                proc.wait(timeout=1)
                            except subprocess.TimeoutExpired:
                                pass
                except Exception as e:
                    return make_error_response(500, f"Failed to execute command: {str(e)}", "EXECUTION_FAILED")

                cmd_end_time = time.perf_counter()
                cmd_duration = round3(cmd_end_time - cmd_start_time)

                result = {
                    "cmd": cmd_str,
                    "stdout": cmd_stdout,
                    "stderr": cmd_stderr,
                    "exit_code": cmd_exit_code,
                    "duration": cmd_duration,
                    "timed_out": cmd_timed_out,
                }
                if cmd_required:
                    result["required"] = True

                commands_results.append(result)

                if cmd_timed_out:
                    overall_timed_out = True
                    has_failed = True
                    if overall_exit_code == 0:
                        overall_exit_code = -1
                elif cmd_exit_code != 0:
                    has_failed = True
                    if overall_exit_code == 0:
                        overall_exit_code = cmd_exit_code

            overall_end_time = time.perf_counter()
            overall_duration = round3(overall_end_time - overall_start_time)

            execution_stats["count"] += 1
            execution_stats["runs"].append(overall_duration)
            execution_stats["commands_total"] += len(command)
            execution_stats["commands_ran"] += len(commands_results)

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
                "commands": commands_results,
                "exit_code": overall_exit_code,
                "duration": overall_duration,
                "timed_out": overall_timed_out,
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
    commands_total = execution_stats["commands_total"]
    commands_ran = execution_stats["commands_ran"]

    if count == 0:
        return JSONResponse(
            status_code=200,
            content={
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
            },
            media_type="application/json",
        )

    # Calculate command durations from all runs
    command_durations = []
    for run in runs:
        command_durations.append(run)

    return JSONResponse(
        status_code=200,
        content={
            "ran": count,
            "commands": {
                "total": commands_total,
                "ran": commands_ran,
                "average": round3(commands_total / count) if count > 0 else None,
                "average_ran": round3(commands_ran / count) if count > 0 else None,
                "duration": {
                    "average": round3(statistics.mean(command_durations)),
                    "median": round3(statistics.median(command_durations)),
                    "max": round3(max(command_durations)),
                    "min": round3(min(command_durations)),
                    "stddev": round3(statistics.stdev(command_durations)) if len(command_durations) > 1 else 0.0,
                },
            },
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
