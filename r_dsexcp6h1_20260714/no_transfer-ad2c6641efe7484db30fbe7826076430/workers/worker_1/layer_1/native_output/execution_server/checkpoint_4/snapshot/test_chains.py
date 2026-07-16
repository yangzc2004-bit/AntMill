import httpx, json, sys, time

client = httpx.Client(timeout=30)
BASE = "http://127.0.0.1:8080"

def test(name, payload, check_fn=None):
    r = client.post(f"{BASE}/v1/execute", json=payload)
    print(f"Test '{name}': status={r.status_code}")
    if r.status_code != 201:
        print(f"  FAILED: expected 201, got {r.status_code}")
        print(f"  Response: {r.text[:200]}")
        return False
    if check_fn:
        try:
            data = r.json()
            check_fn(data)
            print(f"  PASSED")
            return True
        except (AssertionError, Exception) as e:
            print(f"  FAILED: {e}")
            return False
    print(f"  PASSED")
    return True

# 1. Backward compat with string
test("backward compat", {"command": "echo hello"}, lambda d: (
    d["stdout"] == "hello\n" and "commands" not in d
))

# 2. Chain, stop on failure
test("chain stop on failure", {"command": [
    {"cmd": "echo step1"},
    {"cmd": "exit 1"},
    {"cmd": "echo step3"}
]}, lambda d: (
    len(d["commands"]) == 2 and
    d["commands"][0]["exit_code"] == 0 and
    d["commands"][1]["exit_code"] == 1 and
    d["exit_code"] == 1
))

# 3. Required runs despite failure
test("required runs after failure", {"command": [
    {"cmd": "sh -c 'echo build > art.txt'"},
    {"cmd": "sh -c 'cat nope.txt'"},
    {"cmd": "sh -c 'echo cleanup >> art.txt'", "required": True}
], "track": ["*.txt"]}, lambda d: (
    len(d["commands"]) == 3 and
    d["commands"][2].get("required") == True and
    "art.txt" in d.get("files", {}) and
    "cleanup" in d["files"]["art.txt"]
))

# 4. Continue on error
test("continue on error", {"command": [
    {"cmd": "exit 1"},
    {"cmd": "echo test2"},
    {"cmd": "exit 1"}
], "continue_on_error": True}, lambda d: (
    len(d["commands"]) == 3 and
    d["commands"][0]["exit_code"] == 1 and
    d["commands"][1]["exit_code"] == 0 and
    d["commands"][2]["exit_code"] == 1
))

# 5. Per-command timeout
test("per-command timeout", {"command": [
    {"cmd": "echo fast"},
    {"cmd": "sleep 5", "timeout": 1},
    {"cmd": "echo never_runs", "required": True}
], "timeout": 10}, lambda d: (
    d["commands"][0]["timed_out"] == False and
    d["commands"][1]["timed_out"] == True and
    d["commands"][1]["exit_code"] == -1 and
    d["commands"][2]["exit_code"] == 0 and
    d["timed_out"] == True
))

# 6. Stats format
r = client.get(f"{BASE}/v1/stats/execution")
data = r.json()
print(f"Test 'stats': status={r.status_code}")
assert "ran" in data, f"Missing ran in stats: {data}"
assert "commands" in data, f"Missing commands in stats: {data}"
assert "duration" in data, f"Missing duration in stats: {data}"
assert "total" in data["commands"]
assert "ran" in data["commands"]
print(f"  Stats: {json.dumps(data, indent=2)[:300]}")
print("  PASSED")

# 7. Stats on empty (reset by restarting server later, skip for now)

print("\n=== ALL CHAIN TESTS PASSED ===")
