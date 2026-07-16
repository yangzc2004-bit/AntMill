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


@app.route("/datasets/<id>", methods=["GET"])
def get_dataset(id):
    if id not in datasets:
        return jsonify({"ok": False, "error": "Dataset not found"}), 404

    dataset = datasets[id]
    start_time = time.perf_counter()
    rows = dataset["rows"][:100]
    query_ms = (time.perf_counter() - start_time) * 1000

    return jsonify({
        "ok": True,
        "columns": dataset["columns"],
        "rows": rows,
        "query_ms": round(query_ms, 1)
    })


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
