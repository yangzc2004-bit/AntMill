import requests
import subprocess
import time
import sys
import json

proc = subprocess.Popen([sys.executable, "execution_server.py", "--port", "9999"])
time.sleep(2)

base = "http://127.0.0.1:9999/v1/execute"

try:
    # Example 1 from spec
    resp = requests.post(base, json={
        "command": "cat doc.json > out.txt",
        "files": {
            "doc.json": {"foo": [1, 2, 3], "bar": {"a": 1}}
        },
        "track": ["out.txt"]
    })
    data = resp.json()
    assert data["stdout"] == ""
    assert data["stderr"] == ""
    assert data["exit_code"] == 0
    # The content should be the JSON serialization (no trailing newline from cat)
    assert json.loads(data["files"]["out.txt"]) == {"foo": [1, 2, 3], "bar": {"a": 1}}
    print("PASS: Example 1")

    # Example 2 from spec
    resp = requests.post(base, json={
        "command": "wc -l events.jsonl",
        "files": {
            "events.jsonl": [{"id":1,"ok":True},{"id":2,"ok":False}]
        }
    })
    data = resp.json()
    assert data["stdout"] == "2 events.jsonl\n"
    print("PASS: Example 2")

    # Example 3 from spec
    resp = requests.post(base, json={
        "command": "cat table.csv",
        "files": {
            "table.csv": [{"id":1}, {"name":"x"}]
        }
    })
    data = resp.json()
    assert data["stdout"] == "id,name\n1,\n,x\n"
    print("PASS: Example 3")

    # Example 4 from spec - empty string in CSV should be raw text
    resp = requests.post(base, json={
        "command": "cat empty.csv",
        "files": {
            "empty.csv": ""
        }
    })
    data = resp.json()
    # cat of empty file produces empty output
    assert data["stdout"] == ""
    print("PASS: Example 4")

    print("\nAll spec examples passed!")

finally:
    proc.terminate()
    proc.wait()
