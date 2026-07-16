import json
import requests
import subprocess
import time
import sys

# Start the server
proc = subprocess.Popen([sys.executable, "execution_server.py", "--port", "9999"])
time.sleep(2)

base = "http://127.0.0.1:9999/v1/execute"

try:
    # Test: TSV with list of rows
    resp = requests.post(base, json={
        "command": "cat table.tsv",
        "files": {"table.tsv": [{"id":1, "name":"a"}, {"id":2, "name":"b"}]}
    })
    print("Test TSV rows:", resp.status_code, repr(resp.json()["stdout"]))

    # Test: TSV with dict of columns
    resp = requests.post(base, json={
        "command": "cat table.tsv",
        "files": {"table.tsv": {"id": [1, 2], "name": ["a", "b"]}}
    })
    print("Test TSV columns:", resp.status_code, repr(resp.json()["stdout"]))

    # Test: JSONL empty list
    resp = requests.post(base, json={
        "command": "cat empty.jsonl",
        "files": {"empty.jsonl": []}
    })
    print("Test JSONL empty:", resp.status_code, repr(resp.json()["stdout"]))

    # Test: CSV empty list
    resp = requests.post(base, json={
        "command": "cat empty.csv",
        "files": {"empty.csv": []}
    })
    print("Test CSV empty list:", resp.status_code, repr(resp.json()["stdout"]))

    # Test: CSV empty dict
    resp = requests.post(base, json={
        "command": "cat empty.csv",
        "files": {"empty.csv": {}}
    })
    print("Test CSV empty dict:", resp.status_code, repr(resp.json()["stdout"]))

    # Test: BZ2 compression
    resp = requests.post(base, json={
        "command": "bzcat data.json.bz2",
        "files": {"data.json.bz2": {"a": 1, "b": 2}}
    })
    print("Test JSON BZ2:", resp.status_code, repr(resp.json()["stdout"]))

    # Test: CSV with string content (raw text)
    resp = requests.post(base, json={
        "command": "cat table.csv",
        "files": {"table.csv": "hello,world\n"}
    })
    print("Test CSV raw text:", resp.status_code, repr(resp.json()["stdout"]))

    # Test: .txt with structured data should fail
    resp = requests.post(base, json={
        "command": "cat doc.txt",
        "files": {"doc.txt": {"foo": 1}}
    })
    print("Test TXT structured fail:", resp.status_code, resp.json())

    # Test: JSON with string content (raw text)
    resp = requests.post(base, json={
        "command": "cat doc.json",
        "files": {"doc.json": "not json"}
    })
    print("Test JSON raw text:", resp.status_code, repr(resp.json()["stdout"]))

    # Test: YAML with string content (raw text)
    resp = requests.post(base, json={
        "command": "cat doc.yaml",
        "files": {"doc.yaml": "not yaml"}
    })
    print("Test YAML raw text:", resp.status_code, repr(resp.json()["stdout"]))

    # Test: ndjson extension
    resp = requests.post(base, json={
        "command": "cat doc.ndjson",
        "files": {"doc.ndjson": [{"a":1},{"b":2}]}
    })
    print("Test NDJSON:", resp.status_code, repr(resp.json()["stdout"]))

    # Test: JSONL with non-list should fail
    resp = requests.post(base, json={
        "command": "cat doc.jsonl",
        "files": {"doc.jsonl": {"a": 1}}
    })
    print("Test JSONL dict fail:", resp.status_code, resp.json())

    # Test: CSV with non-list non-dict should fail
    resp = requests.post(base, json={
        "command": "cat doc.csv",
        "files": {"doc.csv": 123}
    })
    print("Test CSV int fail:", resp.status_code, resp.json())

finally:
    proc.terminate()
    proc.wait()
