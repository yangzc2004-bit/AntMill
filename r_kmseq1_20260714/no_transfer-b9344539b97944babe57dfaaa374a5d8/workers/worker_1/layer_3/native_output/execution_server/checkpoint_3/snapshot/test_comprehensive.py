import requests
import subprocess
import time
import sys

proc = subprocess.Popen([sys.executable, "execution_server.py", "--port", "9999"])
time.sleep(2)

base = "http://127.0.0.1:9999/v1/execute"

try:
    # Backward compatibility: raw text files
    resp = requests.post(base, json={
        "command": "cat hello.txt",
        "files": {"hello.txt": "Hello World"}
    })
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}"
    assert resp.json()["stdout"] == "Hello World", f"Expected 'Hello World', got {repr(resp.json()['stdout'])}"
    print("PASS: Raw text file")

    # Backward compatibility: multiple files
    resp = requests.post(base, json={
        "command": "cat a.txt b.txt",
        "files": {"a.txt": "A", "b.txt": "B"}
    })
    assert resp.status_code == 201
    assert resp.json()["stdout"] == "AB"
    print("PASS: Multiple raw text files")

    # Backward compatibility: track files
    resp = requests.post(base, json={
        "command": "echo hi > out.txt",
        "files": {"in.txt": "input"},
        "track": ["out.txt"]
    })
    assert resp.status_code == 201
    assert resp.json()["files"] == {"out.txt": "hi\n"}
    print("PASS: Track files")

    # Backward compatibility: env vars
    resp = requests.post(base, json={
        "command": "echo $MY_VAR",
        "files": {},
        "env": {"MY_VAR": "hello"}
    })
    assert resp.status_code == 201
    assert resp.json()["stdout"] == "hello\n"
    print("PASS: Environment variables")

    # Backward compatibility: stdin
    resp = requests.post(base, json={
        "command": "cat",
        "files": {},
        "stdin": "hello\nworld"
    })
    assert resp.status_code == 201
    assert resp.json()["stdout"] == "hello\nworld"
    print("PASS: Stdin string")

    # Backward compatibility: stdin list
    resp = requests.post(base, json={
        "command": "cat",
        "files": {},
        "stdin": ["hello", "world"]
    })
    assert resp.status_code == 201
    assert resp.json()["stdout"] == "hello\nworld"
    print("PASS: Stdin list")

    # JSON structured
    resp = requests.post(base, json={
        "command": "cat doc.json",
        "files": {"doc.json": {"foo": [1, 2, 3]}}
    })
    assert resp.status_code == 201
    assert resp.json()["stdout"] == '{"foo": [1, 2, 3]}'
    print("PASS: JSON structured")

    # JSONL structured
    resp = requests.post(base, json={
        "command": "cat doc.jsonl",
        "files": {"doc.jsonl": [{"a": 1}, {"b": 2}]}
    })
    assert resp.status_code == 201
    assert resp.json()['stdout'] == '{"a": 1}\n{"b": 2}\n'
    print("PASS: JSONL structured")

    # CSV list of rows
    resp = requests.post(base, json={
        "command": "cat doc.csv",
        "files": {"doc.csv": [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]}
    })
    assert resp.status_code == 201
    assert resp.json()["stdout"] == "id,name\n1,a\n2,b\n"
    print("PASS: CSV list of rows")

    # CSV dict of columns
    resp = requests.post(base, json={
        "command": "cat doc.csv",
        "files": {"doc.csv": {"name": ["a", "b"], "id": [1, 2]}}
    })
    assert resp.status_code == 201
    assert resp.json()["stdout"] == "id,name\n1,a\n2,b\n"
    print("PASS: CSV dict of columns")

    # GZ compression
    resp = requests.post(base, json={
        "command": "python -m gzip -d doc.json.gz && cat doc.json",
        "files": {"doc.json.gz": {"foo": "bar"}}
    })
    assert resp.status_code == 201
    assert resp.json()["stdout"] == '{"foo": "bar"}'
    print("PASS: GZ compression")

    # Multiple compression error
    resp = requests.post(base, json={
        "command": "cat test.gz.bz2",
        "files": {"test.gz.bz2": "hello"}
    })
    assert resp.status_code == 400
    print("PASS: Multiple compression error")

    # Raw text with structured extension
    resp = requests.post(base, json={
        "command": "cat doc.json",
        "files": {"doc.json": "raw text"}
    })
    assert resp.status_code == 201
    assert resp.json()["stdout"] == "raw text"
    print("PASS: Raw text with structured extension")

    # Invalid structured data for extension
    resp = requests.post(base, json={
        "command": "cat doc.txt",
        "files": {"doc.txt": {"foo": 1}}
    })
    assert resp.status_code == 400
    print("PASS: Invalid structured data for extension")

    print("\nAll tests passed!")

finally:
    proc.terminate()
    proc.wait()
