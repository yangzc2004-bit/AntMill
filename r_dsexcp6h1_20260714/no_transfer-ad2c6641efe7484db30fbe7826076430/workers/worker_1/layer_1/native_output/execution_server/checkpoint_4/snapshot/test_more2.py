import httpx, json

client = httpx.Client(timeout=30)
BASE = "http://127.0.0.1:8080"

# Test timed out with required following, using proper command
r = client.post(f"{BASE}/v1/execute", json={
    "command": [
        {"cmd": "sleep 10", "timeout": 1},
        {"cmd": "echo 'never runs'", "required": True}
    ],
    "timeout": 5
})
data = r.json()
print(f"Test timeout then required: status={r.status_code}")
print(f"  commands count: {len(data['commands'])}")
print(f"  cmd0 exit_code: {data['commands'][0]['exit_code']}, timed_out: {data['commands'][0]['timed_out']}")
print(f"  cmd1 stdout: {repr(data['commands'][1]['stdout'])}, exit_code: {data['commands'][1]['exit_code']}")
assert len(data['commands']) == 2, f"Expected 2, got {len(data['commands'])}"
assert data['commands'][0]['timed_out'] == True
assert data['commands'][0]['exit_code'] == -1
assert data['commands'][1]['exit_code'] == 0
assert "never runs" in data['commands'][1]['stdout']
print("  PASSED")

# Test stats structure when empty (restart needed, skip)
# Test error handling: invalid timeout in command
r = client.post(f"{BASE}/v1/execute", json={
    "command": [{"cmd": "echo test", "timeout": -1}]
})
print(f"Test invalid command timeout: status={r.status_code}")
assert r.status_code == 400
print(f"  PASSED (400 error: {r.json()})")

# Test error: invalid required field
r = client.post(f"{BASE}/v1/execute", json={
    "command": [{"cmd": "echo test", "required": "yes"}]
})
print(f"Test invalid required: status={r.status_code}")
assert r.status_code == 400
print(f"  PASSED")

# Test error: empty command array
r = client.post(f"{BASE}/v1/execute", json={
    "command": []
})
print(f"Test empty array: status={r.status_code}")
assert r.status_code == 400
print(f"  PASSED")

# Test error: non-object in command array
r = client.post(f"{BASE}/v1/execute", json={
    "command": ["echo test"]
})
print(f"Test string in array: status={r.status_code}")
assert r.status_code == 400
print(f"  PASSED")

# Test error: missing cmd in command object
r = client.post(f"{BASE}/v1/execute", json={
    "command": [{"timeout": 5}]
})
print(f"Test missing cmd: status={r.status_code}")
assert r.status_code == 400
print(f"  PASSED")

# Test overall_exit_code with timed_out first then non-zero
r = client.post(f"{BASE}/v1/execute", json={
    "command": [
        {"cmd": "exit 1"},
        {"cmd": "exit 2", "required": True}
    ]
})
data = r.json()
print(f"Test exit code precedence: status={r.status_code}")
print(f"  overall exit_code: {data['exit_code']}")
print(f"  cmd0: {data['commands'][0]['exit_code']}, cmd1: {data['commands'][1]['exit_code']}")
assert data['exit_code'] == 1  # first non-zero is 1
assert len(data['commands']) == 2
print("  PASSED")

# Test overall_exit_code with timed_out
r = client.post(f"{BASE}/v1/execute", json={
    "command": [
        {"cmd": "sleep 10", "timeout": 1},
        {"cmd": "exit 2", "required": True}
    ]
})
data = r.json()
print(f"Test exit code with timeout: status={r.status_code}")
print(f"  overall exit_code: {data['exit_code']}")
print(f"  cmd0 exit_code: {data['commands'][0]['exit_code']} timed_out: {data['commands'][0]['timed_out']}")
print(f"  cmd1 exit_code: {data['commands'][1]['exit_code']}")
# First non-zero is -1 (timed_out), so overall should be -1
assert data['exit_code'] == -1, f"Expected -1, got {data['exit_code']}"
print("  PASSED")

# Test env and files with chains
r = client.post(f"{BASE}/v1/execute", json={
    "command": [
        {"cmd": "echo $MY_VAR"},
        {"cmd": "cat input.txt"}
    ],
    "env": {"MY_VAR": "chain_value"},
    "files": {"input.txt": "chain_file_content"}
})
data = r.json()
print(f"Test env/files with chain: status={r.status_code}")
print(f"  cmd0 stdout: {repr(data['commands'][0]['stdout'])}")
print(f"  cmd1 stdout: {repr(data['commands'][1]['stdout'])}")
assert "chain_value" in data['commands'][0]['stdout']
assert "chain_file_content" in data['commands'][1]['stdout']
print("  PASSED")

print("\n=== ALL EXTRA TESTS PASSED ===")
