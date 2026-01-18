#!/usr/bin/env python3
"""
Server runner that keeps the server alive
"""
import subprocess
import sys
import time
import threading

def keep_alive():
    """Print something periodically to keep the process alive"""
    while True:
        time.sleep(10)
        print("Server is still running...")

def run_server():
    """Run the server"""
    try:
        # Start the keep-alive thread
        threading.Thread(target=keep_alive, daemon=True).start()

        print("Starting KinJo server...")
        # Run uvicorn
        result = subprocess.run([
            sys.executable, "-m", "uvicorn", "main:app",
            "--host", "127.0.0.1", "--port", "8000"
        ], cwd=r"e:\KInjov2")

        print(f"Server exited with code: {result.returncode}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    run_server()