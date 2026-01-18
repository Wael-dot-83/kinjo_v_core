#!/usr/bin/env python3
"""
Simple server runner that keeps running
"""
import subprocess
import sys
import signal
import time

def signal_handler(signum, frame):
    print("Received signal, shutting down...")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

if __name__ == "__main__":
    while True:
        try:
            print("Starting KinJo server...")
            # Run uvicorn
            result = subprocess.run([
                sys.executable, "-m", "uvicorn", "main:app",
                "--host", "127.0.0.1", "--port", "8000"
            ], cwd=r"e:\KInjov2")
            if result.returncode == 0:
                print("Server exited normally")
                break
            else:
                print(f"Server exited with code {result.returncode}, restarting...")
                time.sleep(2)
        except KeyboardInterrupt:
            print("Server stopped by user")
            break
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(2)