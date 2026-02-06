#!/usr/bin/env python3
"""
Debug script for announcement messaging issue
"""
import requests
import json
from datetime import datetime

def debug_announcement():
    base_url = "http://127.0.0.1:8000"

    # Login as admin
    login_data = {
        "username": "admin",
        "password": "Admin123!"
    }

    print("🔐 Logging in as admin...")
    response = requests.post(f"{base_url}/token", data=login_data)
    if response.status_code != 200:
        print(f"❌ Login failed: {response.status_code} - {response.text}")
        return

    token_data = response.json()
    token = token_data.get("access_token")
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # Test announcement with detailed error logging
    announcement_data = {
        "message_type": "announcement",
        "subject": "Debug Announcement",
        "message_body": "This is a debug announcement.",
        "kindergarten_id": 5,
        "audience": {
            "roles": ["PARENT"],
            "users": []
        },
        "allow_replies": False
    }

    print("📢 Testing announcement...")
    response = requests.post(
        f"{base_url}/api/comm/messages",
        headers=headers,
        json=announcement_data
    )

    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")

    if response.status_code == 500:
        print("🔍 500 Error - checking server logs...")
        # Try to get more details from the server
        try:
            # Check if we can get any error details
            import subprocess
            result = subprocess.run(['python', '-c', '''
import logging
logging.basicConfig(level=logging.DEBUG)
try:
    from communication_service import _build_audience_recipients
    from database import get_db
    from sqlalchemy import text
    db = next(get_db())
    recipients = _build_audience_recipients(db, {"roles": ["PARENT"]}, 5)
    print(f"Audience recipients for KG 5: {recipients}")
    db.close()
except Exception as e:
    print(f"Error in audience building: {e}")
    import traceback
    traceback.print_exc()
'''], capture_output=True, text=True, timeout=10)
            print("Audience building test:")
            print(result.stdout)
            if result.stderr:
                print("Errors:", result.stderr)
        except Exception as e:
            print(f"Could not run debug test: {e}")

if __name__ == "__main__":
    print("🔧 Debugging KinJo Announcement Issue")
    print("=" * 50)

    # Check if server is running
    try:
        response = requests.get("http://127.0.0.1:8000/health", timeout=5)
        if response.status_code == 200:
            print("✅ Server is running")
            debug_announcement()
        else:
            print("❌ Server not responding")
    except requests.exceptions.RequestException:
        print("❌ Cannot connect to server. Please start the server first:")
        print("   python main.py")

    print("=" * 50)
    print("Debug completed!")