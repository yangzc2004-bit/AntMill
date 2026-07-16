import json
import time
import sys
import httpx

BASE = "http://127.0.0.1:8080"

def test():
    client = httpx.Client(timeout=30)
    
    # Test 1: minimal echo
    r = client.post(f"{BASE}/v1/execute", json={"command": "echo Hello, world!"})
    print("Test 1 status:", r.status_code)
    data = r.json()
    assert r.status_code == 201
    assert data["stdout"] == "Hello, world!\n"
    assert data["exit_code"] == 0
    assert data["timed_out"] == False
    assert len(data["id"]) > 0
    assert isinstance(data["duration"], (int, float))
    print("Test 1 PASSED")
    
    # Test 2: with files and stdin array
    r = client.post(f"{BASE}/v1/execute", json={
        "command": "cat input.txt",
        "files": {"input.txt": "Hello from file"},
        "stdin": [],
        "timeout": 5
    })
    print("Test 2 status:", r.status_code)
    data = r.json()
    assert r.status_code == 201
    assert data["stdout"] == "Hello from file"
    assert data["exit_code"] == 0
    print("Test 2 PASSED")
    
    # Test 3: timeout
    r = client.post(f"{BASE}/v1/execute", json={
        "command": "sleep 3",
        "timeout": 1
    })
    print("Test 3 status:", r.status_code)
    data = r.json()
    assert r.status_code == 201
    assert data["exit_code"] == -1
    assert data["timed_out"] == True
    assert data["duration"] >= 1.0  # Should be at least 1s
    print("Test 3 PASSED")
    
    # Test 4: stdin as array
    r = client.post(f"{BASE}/v1/execute", json={
        "command": "cat -",
        "stdin": ["line1", "line2"]
    })
    print("Test 4 status:", r.status_code)
    data = r.json()
    assert r.status_code == 201
    assert data["stdout"] == "line1\nline2"
    print("Test 4 PASSED")
    
    # Test 5: stdin as string
    r = client.post(f"{BASE}/v1/execute", json={
        "command": "cat -",
        "stdin": "hello\nworld"
    })
    print("Test 5 status:", r.status_code)
    data = r.json()
    assert r.status_code == 201
    assert data["stdout"] == "hello\nworld"
    print("Test 5 PASSED")
    
    # Test 6: stats after runs
    r = client.get(f"{BASE}/v1/stats/execution")
    print("Test 6 status:", r.status_code)
    data = r.json()
    assert r.status_code == 200
    assert data["ran"] >= 5
    assert data["duration"]["average"] is not None
    assert data["duration"]["median"] is not None
    assert data["duration"]["max"] is not None
    assert data["duration"]["min"] is not None
    assert data["duration"]["stddev"] is not None
    print("Test 6 PASSED")
    
    # Test 7: error handling - missing command
    r = client.post(f"{BASE}/v1/execute", json={})
    print("Test 7 status:", r.status_code)
    data = r.json()
    assert r.status_code == 400
    assert "error" in data
    print("Test 7 PASSED")
    
    # Test 8: error handling - empty command
    r = client.post(f"{BASE}/v1/execute", json={"command": ""})
    print("Test 8 status:", r.status_code)
    assert r.status_code == 400
    print("Test 8 PASSED")
    
    # Test 9: error handling - non-positive timeout
    r = client.post(f"{BASE}/v1/execute", json={"command": "echo hi", "timeout": -1})
    print("Test 9 status:", r.status_code)
    assert r.status_code == 400
    print("Test 9 PASSED")
    
    # Test 10: env injection
    r = client.post(f"{BASE}/v1/execute", json={
        "command": "echo $MY_VAR",
        "env": {"MY_VAR": "test_value"}
    })
    print("Test 10 status:", r.status_code)
    data = r.json()
    assert r.status_code == 201
    assert data["stdout"] == "test_value\n"
    print("Test 10 PASSED")
    
    # Test 11: stats with no runs (reset between? - can't reset, but verify stats object structure)
    # Just check that stats works
    print("All tests passed!")

if __name__ == "__main__":
    test()
