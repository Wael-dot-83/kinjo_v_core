"""
Simple server startup script
"""
import uvicorn
import os

if __name__ == "__main__":
    # Disable file watching to prevent reload issues
    os.environ["UVICORN_DISABLE_FILE_WATCHING"] = "1"

    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8001,
        reload=False,  # Disable reload to prevent shutdown issues
        log_level="info",
        access_log=True
    )
