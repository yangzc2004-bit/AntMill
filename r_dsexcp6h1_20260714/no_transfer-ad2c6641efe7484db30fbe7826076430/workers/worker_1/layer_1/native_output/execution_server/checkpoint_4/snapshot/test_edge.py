import httpx
import time

BASE = "http://127.0.0.1:8080"
client = httpx.Client(timeout=30)

# Single run to test stats with n=1
r = client.post(f"{BASE}/v1/execute", json={"command": "echo single"})
print("Single run status:", r.status_code)
d1 = r.json()
print("Duration:", d1["duration"])

# Check stats
r = client.get(f"{BASE}/v1/stats/execution")
data = r.json()
print("Stats:", data)
assert data["ran"] == 1
assert data["duration"]["min"] == data["duration"]["max"]
assert data["duration"]["average"] == data["duration"]["min"]
assert data["duration"]["median"] == data["duration"]["min"]
assert data["duration"]["stddev"] == 0.0
print("Edge case tests PASSED")
