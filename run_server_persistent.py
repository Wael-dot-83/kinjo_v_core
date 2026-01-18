"""
Persistent server startup script for Windows
"""
import subprocess
import sys
import time

def run_server():
    """Run the FastAPI server and restart if it crashes"""
    while True:
        try:
            print("[*] Starting KInJo server...")
            result = subprocess.run(
                [sys.executable, "-m", "uvicorn", "main:app", 
                 "--host", "127.0.0.1", "--port", "8000"],
                cwd=r"e:\KInjov2"
            )
            if result.returncode == 0:
                print("[*] Server exited normally")
                break
            else:
                print(f"[!] Server exited with code {result.returncode}, restarting in 5 seconds...")
                time.sleep(5)
        except KeyboardInterrupt:
            print("[*] Server stopped by user")
            break
        except Exception as e:
            print(f"[!] Error: {e}, restarting in 5 seconds...")
            time.sleep(5)

if __name__ == "__main__":
    run_server()
