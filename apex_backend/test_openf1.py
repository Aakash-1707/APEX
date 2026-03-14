import httpx
import json

url = "https://api.openf1.org/v1/meetings"
params = {"year": 2026}
resp = httpx.get(url, params=params)
print(f"Status: {resp.status_code}")
try:
    data = resp.json()
    print(f"Type: {type(data)}")
    if isinstance(data, list):
        print(f"Count: {len(data)}")
        if len(data) > 0:
            print(f"First item keys: {data[0].keys()}")
    else:
        print(f"Data: {data}")
except Exception as e:
    print(f"Error: {e}")
