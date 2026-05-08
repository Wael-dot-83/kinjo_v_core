
import urllib.request
import time
import sys

print("Waiting for server...")
time.sleep(5)

try:
    print("Attempting connection to http://127.0.0.1:8000/docs")
    with urllib.request.urlopen("http://127.0.0.1:8000/docs") as response:
        print(f"Status Code: {response.getcode()}")
        content = response.read(100)
        print(f"Content Start: {content}")
        print("Connection Successful!")
except Exception as e:
    print(f"Connection Failed: {e}")
    sys.exit(1)
