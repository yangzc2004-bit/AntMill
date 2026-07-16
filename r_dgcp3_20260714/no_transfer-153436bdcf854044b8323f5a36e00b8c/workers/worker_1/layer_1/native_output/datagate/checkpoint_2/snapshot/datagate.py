import csv
import hashlib
import io
import re
import sys
import time
import urllib.parse

import charset_normalizer
import httpx
from flask import Flask, jsonify, request

app = Flask(__name__)

# In-memory storage for datasets
_datasets = {}


def _deterministic_id(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _is_valid_url(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    return bool(parsed.scheme and parsed.netloc)


def _infer_delimiter(text: str) -> str:
    # Count occurrences in first few lines
    lines = text.splitlines()[:5]
    counts = {",": 0, ";": 0, "\t": 0}
    for line in lines:
        for delim in counts:
            counts[delim] += line.count(delim)
    # Pick delimiter with highest count, default to comma
    best = max(counts, key=counts.get)
    if counts[best] == 0:
        return ","
    return best


def _is_time_like(value: str) -> bool:
    # Time-like values: e.g. 08:30, 9:15, 12:00
    return bool(re.fullmatch(r"\d{1,2}:\d{2}", value.strip()))


def _infer_type(value: str):
    s = value.strip()
    if not s:
        return ""
    if _is_time_like(s):
        return s
    # Try integer
    try:
        return int(s)
    except ValueError:
        pass
    # Try float
    try:
        return float(s)
    except ValueError:
        pass
    # Return as string
    return s


def _parse_csv(text: str):
    delimiter = _infer_delimiter(text)
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows = list(reader)
    if len(rows) < 2:
        raise ValueError("CSV must have at least a header row and one data row")
    columns = rows[0]
    data = []
    for row in rows[1:]:
        # Pad or trim to match column count
        if len(row) < len(columns):
            row.extend([""] * (len(columns) - len(row)))
        elif len(row) > len(columns):
            row = row[: len(columns)]
        typed_row = [_infer_type(cell) for cell in row]
        data.append(typed_row)
    return columns, data


def _json_response(data, status=200):
    response = jsonify(data)
    response.status_code = status
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


@app.route("/convert", methods=["GET", "OPTIONS"])
def convert():
    if request.method == "OPTIONS":
        return _json_response({"ok": True})

    source = request.args.get("source")
    if not source:
        return _json_response({"ok": False, "error": "Missing source parameter"}, 400)

    if not _is_valid_url(source):
        return _json_response({"ok": False, "error": "Invalid URL"}, 400)

    charset = request.args.get("charset")

    try:
        with httpx.Client(follow_redirects=True, timeout=30) as client:
            resp = client.get(source)
            if resp.status_code >= 400:
                return _json_response(
                    {"ok": False, "error": "Source unreachable or remote HTTP error"}, 404
                )
            raw_bytes = resp.content
    except Exception:
        return _json_response(
            {"ok": False, "error": "Source unreachable or remote HTTP error"}, 404
        )

    # Decode bytes
    try:
        if charset:
            text = raw_bytes.decode(charset)
        else:
            detected = charset_normalizer.detect(raw_bytes)
            detected_encoding = detected.get("encoding") if detected else None
            if detected_encoding:
                text = raw_bytes.decode(detected_encoding)
            else:
                text = raw_bytes.decode("utf-8", errors="replace")
    except (LookupError, UnicodeDecodeError, ValueError):
        return _json_response(
            {"ok": False, "error": "Unsupported or malformed charset"}, 400
        )

    # Parse CSV
    try:
        columns, data = _parse_csv(text)
    except ValueError as e:
        return _json_response({"ok": False, "error": "Non-tabular content"}, 400)

    dataset_id = _deterministic_id(source)
    _datasets[dataset_id] = {"columns": columns, "rows": data}

    return _json_response(
        {"ok": True, "endpoint": f"/datasets/{dataset_id}"}
    )


def _is_positive_int(value):
    try:
        v = int(value)
        return v > 0
    except (ValueError, TypeError):
        return False


def _is_non_negative_int(value):
    try:
        v = int(value)
        return v >= 0
    except (ValueError, TypeError):
        return False


@app.route("/datasets/<id>", methods=["GET", "OPTIONS"])
def get_dataset(id):
    if request.method == "OPTIONS":
        return _json_response({"ok": True})

    start = time.perf_counter()
    dataset = _datasets.get(id)
    if dataset is None:
        return _json_response({"ok": False, "error": "Dataset not found"}, 404)

    columns = dataset["columns"]
    original_rows = dataset["rows"]  # original data
    total = len(original_rows)

    # Control parameters
    control_params = ["_size", "_offset", "_shape", "_sort", "_sort_desc", "_rowid", "_total"]

    # Check for repeated control parameters
    for param in control_params:
        values = request.args.getlist(param)
        if len(values) > 1:
            return _json_response({"ok": False, "error": f"Repeated parameter: {param}"}, 400)

    # Parse _size
    size_str = request.args.get("_size", "100")
    if not _is_positive_int(size_str):
        return _json_response({"ok": False, "error": "_size must be a positive integer"}, 400)
    size = int(size_str)

    # Parse _offset
    offset_str = request.args.get("_offset", "0")
    if not _is_non_negative_int(offset_str):
        return _json_response({"ok": False, "error": "_offset must be a non-negative integer"}, 400)
    offset = int(offset_str)

    # Parse _shape
    shape = request.args.get("_shape", "lists")
    if shape not in ("lists", "objects"):
        return _json_response({"ok": False, "error": "_shape must be 'lists' or 'objects'"}, 400)

    # Parse _sort and _sort_desc
    sort_col = request.args.get("_sort")
    sort_desc_col = request.args.get("_sort_desc")

    sort_col_to_use = None
    sort_desc = False

    if sort_desc_col is not None:
        if sort_desc_col == "":
            return _json_response({"ok": False, "error": "_sort_desc must be a valid column"}, 400)
        if sort_desc_col not in columns:
            return _json_response({"ok": False, "error": f"Unknown column: {sort_desc_col}"}, 400)
        sort_col_to_use = sort_desc_col
        sort_desc = True
    elif sort_col is not None:
        if sort_col == "":
            return _json_response({"ok": False, "error": "_sort must be a valid column"}, 400)
        if sort_col not in columns:
            return _json_response({"ok": False, "error": f"Unknown column: {sort_col}"}, 400)
        sort_col_to_use = sort_col

    # Parse _rowid
    rowid_toggle = request.args.get("_rowid")
    if rowid_toggle is not None and rowid_toggle != "hide":
        return _json_response({"ok": False, "error": "_rowid must be 'hide'"}, 400)

    # Parse _total
    total_toggle = request.args.get("_total")
    if total_toggle is not None and total_toggle != "hide":
        return _json_response({"ok": False, "error": "_total must be 'hide'"}, 400)

    # Prepare rows with original indices (1-based, accounting for header row)
    # Row 1 in the file is the first data row, so rowid = index + 1
    indexed_rows = [(i + 1, row) for i, row in enumerate(original_rows)]

    # Apply sorting - stable sort
    if sort_col_to_use is not None:
        col_idx = columns.index(sort_col_to_use)
        try:
            # Python's sort is stable
            indexed_rows.sort(key=lambda item: item[1][col_idx], reverse=sort_desc)
        except TypeError:
            return _json_response({"ok": False, "error": f"Cannot sort column {sort_col_to_use}: mixed types"}, 400)

    # Apply pagination
    paginated = indexed_rows[offset:offset + size] if size > 0 else indexed_rows[offset:]

    # Build response
    result = {
        "ok": True,
        "columns": columns,
        "query_ms": round((time.perf_counter() - start) * 1000, 1),
    }

    # Add total unless hidden
    if total_toggle != "hide":
        result["total"] = total

    # Build rows based on shape
    if shape == "objects":
        # rows is objects, includes rowid (unless hidden)
        result_rows = []
        for rowid, row in paginated:
            obj = {}
            for col, val in zip(columns, row):
                obj[col] = val
            if rowid_toggle != "hide":
                obj["rowid"] = rowid
            result_rows.append(obj)
        result["rows"] = result_rows
    else:
        # shape == lists (default)
        if rowid_toggle == "hide":
            # Just the data rows
            result["rows"] = [row for rowid, row in paginated]
        else:
            # Include rowid as first element in each row
            result["rows"] = [[rowid] + row for rowid, row in paginated]
            # Prepend "rowid" to columns
            result["columns"] = ["rowid"] + columns

    return _json_response(result)


@app.errorhandler(404)
def not_found(e):
    # Only return JSON for API routes; for others, still return JSON
    return _json_response({"ok": False, "error": "Not found"}, 404)


@app.route("/")
def index():
    return _json_response({"ok": False, "error": "Not found"}, 404)


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--address", type=str, default="127.0.0.1")
    parser.add_argument("command", choices=["start"])
    args = parser.parse_args()

    if args.command == "start":
        app.run(host=args.address, port=args.port, threaded=True)


if __name__ == "__main__":
    main()
