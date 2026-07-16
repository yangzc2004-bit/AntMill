"""Script to reproduce the issue - test structured file support"""
import json, sys, httpx, time, subprocess

BASE = "http://127.0.0.1:8080"

def run_test(name, payload, expected_status=201, check_fn=None):
    r = httpx.post(f"{BASE}/v1/execute", json=payload, timeout=30)
    print(f"Test '{name}': status={r.status_code}")
    if r.status_code != expected_status:
        print(f"  FAILED: expected {expected_status}")
        print(f"  Response: {r.text[:500]}")
        return False
    if check_fn:
        try:
            check_fn(r.json())
            print(f"  PASSED")
            return True
        except AssertionError as e:
            print(f"  FAILED assertion: {e}")
            print(f"  Response: {json.dumps(r.json(), indent=2)[:500]}")
            return False
    print(f"  PASSED")
    return True

# Test 1: JSON object file
def check_json(r):
    assert r["stdout"] == '{"foo": [1, 2, 3], "bar": {"a": 1}}\n'
run_test("json object", {
    "command": "cat doc.json",
    "files": {"doc.json": {"foo": [1, 2, 3], "bar": {"a": 1}}},
})

# Test 2: JSONL file
def check_jsonl(r):
    assert r["stdout"] == "2 events.jsonl\n"
run_test("jsonl file", {
    "command": "wc -l events.jsonl",
    "files": {"events.jsonl": [{"id":1,"ok":True},{"id":2,"ok":False}]},
})

# Test 3: CSV file with list of rows
def check_csv_list(r):
    assert r["stdout"] == "id,name\n1,\n,x\n"
run_test("csv list of rows", {
    "command": "cat table.csv",
    "files": {"table.csv": [{"id":1}, {"name":"x"}]},
})

# Test 4: Empty CSV
def check_empty_csv(r):
    assert r["stdout"] == "\n"
run_test("empty csv", {
    "command": "cat empty.csv",
    "files": {"empty.csv": ""},
})

print("\nAll reproduce tests done.")
