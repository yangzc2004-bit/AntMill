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


def is_numeric_value(value):
    """Check if value can be parsed as a number (int or float)."""
    try:
        float(value)
        return True
    except (ValueError, TypeError):
        return False


def parse_filter_value(value_str):
    """Parse a filter value string to a comparable type."""
    try:
        # Try int first
        if re.fullmatch(r"-?\d+", value_str):
            return int(value_str)
        # Try float
        if re.fullmatch(r"-?\d+\.\d+", value_str):
            return float(value_str)
    except (ValueError, TypeError):
        pass
    return value_str


def apply_filter(row_value, comparator, filter_value):
    """Apply a single filter comparison. Returns True if row matches."""
    if comparator == "exact":
        # Case-sensitive string equality
        return str(row_value) == str(filter_value)
    elif comparator == "contains":
        # Case-sensitive substring
        return str(filter_value) in str(row_value)
    elif comparator == "less":
        # Numeric strict less
        # Non-numeric stored values are not matched
        if not isinstance(row_value, (int, float)):
            return False
        try:
            filter_num = float(filter_value)
            return float(row_value) < filter_num
        except (ValueError, TypeError):
            return False
    elif comparator == "greater":
        # Numeric strict greater
        # Non-numeric stored values are not matched
        if not isinstance(row_value, (int, float)):
            return False
        try:
            filter_num = float(filter_value)
            return float(row_value) > filter_num
        except (ValueError, TypeError):
            return False
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

    # Parse and validate filters
    # Filter format: <column>__<comparator>=<value>
    # Valid comparators: exact, contains, less, greater
    # Control params (starting with _) are not filters
    # Params without _ and without __ are ignored as filters
    filters = []
    seen_filter_keys = set()
    
    for key in request.args.keys():
        # Skip control parameters
        if key.startswith("_"):
            continue
        
        # Check for duplicate filter keys
        if key in seen_filter_keys:
            return jsonify({"ok": False, "error": f"Duplicate filter key: {key}"}), 400
        seen_filter_keys.add(key)
        
        # Parse filter key
        if "__" not in key:
            # Not a filter, ignore
            continue
        
        parts = key.split("__", 1)
        if len(parts) != 2:
            continue
            
        column_name, comparator = parts
        
        # Empty column name is invalid
        if not column_name:
            return jsonify({"ok": False, "error": f"Unknown filter column: {column_name}"}), 400
        
        # Validate comparator
        valid_comparators = ("exact", "contains", "less", "greater")
        if comparator not in valid_comparators:
            return jsonify({"ok": False, "error": f"Invalid comparator: {comparator}"}), 400
        
        # Validate column exists
        if column_name not in columns:
            return jsonify({"ok": False, "error": f"Unknown filter column: {column_name}"}), 400
        
        # Get filter value(s) - should be exactly one since we check duplicates
        values = request.args.getlist(key)
        if len(values) > 1:
            return jsonify({"ok": False, "error": f"Duplicate filter key: {key}"}), 400
        
        filter_value = values[0]
        
        # For less/greater, validate filter value is numeric
        if comparator in ("less", "greater"):
            if not is_numeric_value(filter_value):
                return jsonify({"ok": False, "error": f"Comparator target not numeric: {key}"}), 400
        
        filters.append((column_name, comparator, filter_value))
    
    # Check for query timeout (5 seconds)
    if time.perf_counter() - start_time > 5:
        return jsonify({"ok": False, "error": "Query timeout"}), 400

    # Build list of (original_rowid, row_data) tuples to track original row numbers
    # Original rowid is 1-based index in the source file
    indexed_rows = [(i + 1, row) for i, row in enumerate(rows)]

    # Apply filters (before sorting)
    for column_name, comparator, filter_value in filters:
        col_idx = columns.index(column_name)
        indexed_rows = [
            (rowid, row) for rowid, row in indexed_rows
            if apply_filter(row[col_idx], comparator, filter_value)
        ]

    # Check for query timeout after filtering
    if time.perf_counter() - start_time > 5:
        return jsonify({"ok": False, "error": "Query timeout"}), 400

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
