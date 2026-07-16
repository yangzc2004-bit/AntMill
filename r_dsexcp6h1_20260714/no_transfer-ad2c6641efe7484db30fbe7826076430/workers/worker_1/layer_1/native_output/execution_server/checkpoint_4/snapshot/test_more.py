import httpx, json, sys

client = httpx.Client(timeout=30)
BASE = "http://127.0.0.1:8080"

# Test stdin only for first command
r = client.post(f"{BASE}/v1/execute", json={
    "command": [{"cmd": "cat -"}, {"cmd": "cat -"}, {"cmd": "cat -"}],
    "stdin": "hello_stdin"
})
data = r.json()
print(f"Test stdin chain: status={r.status_code}")
print(f"  cmd0 stdout: {repr(data['commands'][0]['stdout'])}")
print(f"  cmd1 stdout: {repr(data['commands'][1]['stdout'])}")
print(f"  cmd2 stdout: {repr(data['commands'][2]['stdout'])}")
assert data['commands'][0]['stdout'] == "hello_stdin", f"Expected hello_stdin, got {repr(data['commands'][0]['stdout'])}"
assert data['commands'][1]['stdout'] == "", f"Expected empty, got {repr(data['commands'][1]['stdout'])}"
assert data['commands'][2]['stdout'] == "", f"Expected empty, got {repr(data['commands'][2]['stdout'])}"
print("  PASSED")

# Test required stops after failure when next command is not required
r = client.post(f"{BASE}/v1/execute", json={
    "command": [
        {"cmd": "exit 1"},
        {"cmd": "echo should_not_run"}
    ]
})
data = r.json()
print(f"Test stop after failure: status={r.status_code}")
print(f"  commands count: {len(data['commands'])}")
assert len(data['commands']) == 1, f"Expected 1 command, got {len(data['commands'])}"
print("  PASSED")

# Test timed out with required following
r = client.post(f"{BASE}/v1/execute", json={
    "command": [
        {"cmd": "sleep 10", "timeout": 1},
        {"cmd": "must run", "required": True}
    ],
    "timeout": 5
})
data = r.json()
print(f"Test timeout then required: status={r.status_code}")
print(f"  commands count: {len(data['commands'])}")
print(f"  cmd0 exit_code: {data['commands'][0]['exit_code']}, timed_out: {data['commands'][0]['timed_out']}")
print(f"  cmd1 exit_code: {data['commands'][1]['exit_code']}, stdout: {repr(data['commands'][1]['stdout'])}")
assert len(data['commands']) == 2, f"Expected 2, got {len(data['commands'])}"
assert data['commands'][0]['timed_out'] == True
assert data['commands'][0]['exit_code'] == -1
assert data['commands'][1]['exit_code'] == 0
print("  PASSED")

# Test timed out with no required - should stop
r = client.post(f"{BASE}/v1/execute", json={
    "command": [
        {"cmd": "sleep 10", "timeout": 1},
        {"cmd": "echo should_not_run"}
    ],
    "timeout": 5
})
data = r.json()
print(f"Test timeout stops chain: status={r.status_code}")
print(f"  commands count: {len(data['commands'])}")
assert len(data['commands']) == 1, f"Expected 1, got {len(data['commands'])}"
print("  PASSED")

# Test stats initial state - kill server first and restart
print("\n=== ALL EXTRA TESTS PASSED ===")
