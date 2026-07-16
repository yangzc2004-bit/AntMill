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
    # Test 1: JSON structured data
    resp = requests.post(base, json={
        "command": "cat doc.json > out.txt",
        "files": {"doc.json": {"foo": [1, 2, 3], "bar": {"a": 1}}},
        "track": ["out.txt"]
    })
    print("Test 1 (JSON):", resp.status_code, resp.json())

    # Test 2: JSONL structured data
    resp = requests.post(base, json={
        "command": "wc -l events.jsonl",
        "files": {"events.jsonl": [{"id":1,"ok":True},{"id":2,"ok":False}]}
    })
    print("Test 2 (JSONL):", resp.status_code, resp.json())

    # Test 3: CSV structured data
    resp = requests.post(base, json={
        "command": "cat table.csv",
        "files": {"table.csv": [{"id":1}, {"name":"x"}]}
    })
    print("Test 3 (CSV):", resp.status_code, resp.json())

    # Test 4: Empty CSV (raw text)
    resp = requests.post(base, json={
        "command": "cat empty.csv",
        "files": {"empty.csv": ""}
    })
    print("Test 4 (Empty CSV text):", resp.status_code, resp.json())

    # Test 5: YAML structured data
    resp = requests.post(base, json={
        "command": "cat doc.yaml",
        "files": {"doc.yaml": {"foo": [1, 2, 3]}}
    })
    print("Test 5 (YAML):", resp.status_code, resp.json())

    # Test 6: Multiple compression extensions - should 400
    resp = requests.post(base, json={
        "command": "cat test.gz.bz2",
        "files": {"test.gz.bz2": "hello"}
    })
    print("Test 6 (Multiple compression):", resp.status_code, resp.json())

    # Test 7: GZ compressed JSON
    resp = requests.post(base, json={
        "command": "zcat data.json.gz",
        "files": {"data.json.gz": {"a": 1, "b": 2}}
    })
    print("Test 7 (JSON GZ):", resp.status_code, resp.json())

    # Test 8: CSV with list of rows format
    resp = requests.post(base, json={
        "command": "cat table.csv",
        "files": {"table.csv": {"id": [1, 2], "name": ["a", "b"]}}
    })
    print("Test 8 (CSV columns):", resp.status_code, resp.json())

finally:
    proc.terminate()
    proc.wait()
