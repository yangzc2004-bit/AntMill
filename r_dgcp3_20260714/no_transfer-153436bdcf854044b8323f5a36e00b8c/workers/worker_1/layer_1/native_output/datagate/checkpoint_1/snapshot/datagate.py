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


@app.route("/datasets/<id>", methods=["GET", "OPTIONS"])
def get_dataset(id):
    if request.method == "OPTIONS":
        return _json_response({"ok": True})

    start = time.perf_counter()
    dataset = _datasets.get(id)
    if dataset is None:
        return _json_response({"ok": False, "error": "Dataset not found"}, 404)

    rows = dataset["rows"][:100]
    elapsed = (time.perf_counter() - start) * 1000

    return _json_response(
        {
            "ok": True,
            "columns": dataset["columns"],
            "rows": rows,
            "query_ms": round(elapsed, 1),
        }
    )


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
