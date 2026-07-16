import argparse
import csv
import hashlib
import io
import json
import re
import sys
import time
import urllib.parse
from typing import Optional

import charset_normalizer
import httpx
from flask import Flask, request, jsonify, Response

app = Flask(__name__)

# In-memory storage for datasets
datasets = {}


def detect_encoding(data: bytes) -> str:
    result = charset_normalizer.detect(data)
    encoding = result.get("encoding") if result else None
    if encoding:
        return encoding
    return "utf-8"


def infer_delimiter(text: str) -> str:
    first_line = text.split("\n")[0] if text else ""
    counts = {",": first_line.count(","), ";": first_line.count(";"), "\t": first_line.count("\t")}
    best = max(counts, key=counts.get)
    return best if counts[best] > 0 else ","


def is_valid_url(url: str) -> bool:
    try:
        parsed = urllib.parse.urlparse(url)
        return bool(parsed.scheme and parsed.netloc)
    except Exception:
        return False


def infer_type(value: str):
    value = value.strip()
    if value == "":
        return ""
    # Check integer
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    # Check decimal/float
    if re.fullmatch(r"-?\d+\.\d+", value):
        return float(value)
    # Time-like values remain text
    if re.fullmatch(r"\d{1,2}:\d{2}", value):
        return value
    # Default to string
    return value


def parse_csv(text: str) -> tuple:
    delimiter = infer_delimiter(text)
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows = list(reader)
    if len(rows) < 2:
        raise ValueError("CSV must have at least one header row and one data row")
    columns = rows[0]
    data_rows = []
    for row in rows[1:]:
        if not row or all(cell.strip() == "" for cell in row):
            continue
        data_rows.append([infer_type(cell) for cell in row])
    return columns, data_rows


def generate_id(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]


def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "*"
    return response


@app.after_request
def after_request(response):
    return add_cors_headers(response)


@app.route("/convert", methods=["GET"])
def convert():
    source = request.args.get("source")
    charset = request.args.get("charset")

    if not source:
        return jsonify({"ok": False, "error": "Missing source parameter"}), 400

    if not is_valid_url(source):
        return jsonify({"ok": False, "error": "Invalid URL"}), 400

    if charset:
        try:
            "test".encode("latin1").decode(charset)
        except (LookupError, UnicodeDecodeError):
            return jsonify({"ok": False, "error": "Unsupported or malformed charset"}), 400

    try:
        resp = httpx.get(source, follow_redirects=True, timeout=30)
        if resp.status_code >= 400:
            return jsonify({"ok": False, "error": "Source unreachable or remote HTTP error"}), 404
        data = resp.content
    except Exception:
        return jsonify({"ok": False, "error": "Source unreachable or remote HTTP error"}), 404

    if charset:
        try:
            text = data.decode(charset)
        except (UnicodeDecodeError, LookupError):
            return jsonify({"ok": False, "error": "Unsupported or malformed charset"}), 400
    else:
        detected = detect_encoding(data)
        text = data.decode(detected)

    try:
        columns, rows = parse_csv(text)
    except Exception:
        return jsonify({"ok": False, "error": "Non-tabular content"}), 400

    dataset_id = generate_id(source)
    datasets[dataset_id] = {"columns": columns, "rows": rows}

    return jsonify({"ok": True, "endpoint": f"/datasets/{dataset_id}"})


def is_positive_integer(value):
    """Check if value is a positive integer."""
    try:
        int_val = int(value)
        return int_val > 0 and str(int_val) == str(value)
    except (ValueError, TypeError):
        return False


def is_non_negative_integer(value):
    """Check if value is a non-negative integer."""
    try:
        int_val = int(value)
        return int_val >= 0 and str(int_val) == str(value)
    except (ValueError, TypeError):
        return False


@app.route("/datasets/<id>", methods=["GET"])
def get_dataset(id):
    if id not in datasets:
        return jsonify({"ok": False, "error": "Dataset not found"}), 404

    dataset = datasets[id]
    columns = dataset["columns"]
    rows = dataset["rows"]
    start_time = time.perf_counter()

    # Check for repeated control parameters
    control_params = ["_size", "_offset", "_shape", "_sort", "_sort_desc", "_rowid", "_total"]
    for param in control_params:
        values = request.args.getlist(param)
        if len(values) > 1:
            return jsonify({"ok": False, "error": f"Repeated control parameter: {param}"}), 400

    # Parse _size
    size_str = request.args.get("_size", "100")
    if not is_positive_integer(size_str):
        return jsonify({"ok": False, "error": "_size must be a positive integer"}), 400
    size = int(size_str)

    # Parse _offset
    offset_str = request.args.get("_offset", "0")
    if not is_non_negative_integer(offset_str):
        return jsonify({"ok": False, "error": "_offset must be a non-negative integer"}), 400
    offset = int(offset_str)

    # Parse _shape
    shape = request.args.get("_shape", "lists")
    if shape not in ("lists", "objects"):
        return jsonify({"ok": False, "error": "_shape must be 'lists' or 'objects'"}), 400

    # Parse _sort and _sort_desc
    sort_col = request.args.get("_sort")
    sort_desc_col = request.args.get("_sort_desc")

    if sort_col is not None and sort_col.strip() == "":
        return jsonify({"ok": False, "error": "_sort column cannot be empty"}), 400
    if sort_desc_col is not None and sort_desc_col.strip() == "":
        return jsonify({"ok": False, "error": "_sort_desc column cannot be empty"}), 400

    if sort_col is not None and sort_col not in columns:
        return jsonify({"ok": False, "error": f"Unknown _sort column: {sort_col}"}), 400
    if sort_desc_col is not None and sort_desc_col not in columns:
        return jsonify({"ok": False, "error": f"Unknown _sort_desc column: {sort_desc_col}"}), 400

    # Parse _rowid
    rowid_toggle = request.args.get("_rowid")
    if rowid_toggle is not None and rowid_toggle != "hide":
        return jsonify({"ok": False, "error": "_rowid must be 'hide'"}), 400

    # Parse _total
    total_toggle = request.args.get("_total")
    if total_toggle is not None and total_toggle != "hide":
        return jsonify({"ok": False, "error": "_total must be 'hide'"}), 400

    # Build list of (original_rowid, row_data) tuples to track original row numbers
    # Original rowid is 1-based index in the source file
    indexed_rows = [(i + 1, row) for i, row in enumerate(rows)]

    # Apply sorting (stable, before pagination)
    # If both _sort and _sort_desc present, _sort_desc wins
    if sort_desc_col is not None:
        col_idx = columns.index(sort_desc_col)
        # Sort descending, stable - Python's sort is stable
        indexed_rows = sorted(indexed_rows, key=lambda r: r[1][col_idx], reverse=True)
    elif sort_col is not None:
        col_idx = columns.index(sort_col)
        # Sort ascending, stable
        indexed_rows = sorted(indexed_rows, key=lambda r: r[1][col_idx])

    # Total before pagination
    total = len(indexed_rows)

    # Apply pagination
    paginated = indexed_rows[offset:offset + size] if size > 0 else indexed_rows[offset:offset]

    # Build response
    response = {
        "ok": True,
        "columns": columns,
        "query_ms": round((time.perf_counter() - start_time) * 1000, 1)
    }

    # Apply _shape
    if shape == "objects":
        # rows is objects with rowid
        object_rows = []
        for rowid, row in paginated:
            obj = {"rowid": rowid}
            for col, val in zip(columns, row):
                obj[col] = val
            object_rows.append(obj)
        response["rows"] = object_rows
    else:
        # lists shape (default)
        response["rows"] = [row for rowid, row in paginated]

    # Add total by default
    response["total"] = total

    # Apply visibility toggles
    if rowid_toggle == "hide":
        # For objects shape, remove rowid from each object
        if shape == "objects":
            for obj in response["rows"]:
                obj.pop("rowid", None)
    if total_toggle == "hide":
        response.pop("total", None)

    return jsonify(response)


@app.errorhandler(404)
def handle_404(e):
    if request.path.startswith("/datasets/") or request.path == "/convert":
        return jsonify({"ok": False, "error": "Not found"}), 404
    return jsonify({"ok": False, "error": "Not found"}), 404


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["start"])
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--address", default="127.0.0.1")
    args = parser.parse_args()

    if args.command == "start":
        app.run(host=args.address, port=args.port)


if __name__ == "__main__":
    main()
