#!/usr/bin/env python3
"""
Test script for the new announcement messaging system
"""
import requests
import json
from datetime import datetime

# Test the messaging system
def test_messaging():
    base_url = "http://127.0.0.1:8000"

    # First, login as admin to get token
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
    if not token:
        print("❌ No access token received")
        return

    print("✅ Login successful")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # Test sending an announcement
    announcement_data = {
        "message_type": "announcement",
        "subject": "Test Announcement",
        "message_body": "This is a test announcement to all parents in the kindergarten.",
        "kindergarten_id": 5,  # KG 5 has accepted enrollments
        "audience": {
            "roles": ["PARENT"],
            "users": []
        },
        "allow_replies": False
    }

    print("📢 Sending announcement...")
    response = requests.post(
        f"{base_url}/api/comm/messages",
        headers=headers,
        json=announcement_data
    )

    if response.status_code == 201:
        print("✅ Announcement sent successfully!")
        message_data = response.json()
        print(f"Message ID: {message_data.get('id')}")
        print(f"Thread Type: {message_data.get('thread_type')}")
        print(f"Allow Replies: {message_data.get('allow_replies')}")
    else:
        print(f"❌ Failed to send announcement: {response.status_code} - {response.text}")

    # Test sending a direct message
    direct_data = {
        "message_type": "direct",
        "subject": "Test Direct Message",
        "message_body": "This is a test direct message.",
        "recipient_id": 2  # manager1
    }

    print("💬 Sending direct message...")
    response = requests.post(
        f"{base_url}/api/comm/messages",
        headers=headers,
        json=direct_data
    )

    if response.status_code == 201:
        print("✅ Direct message sent successfully!")
        message_data = response.json()
        print(f"Message ID: {message_data.get('id')}")
        print(f"Thread Type: {message_data.get('thread_type')}")
        print(f"Allow Replies: {message_data.get('allow_replies')}")
    else:
        print(f"❌ Failed to send direct message: {response.status_code} - {response.text}")

    # Test listing messages
    print("📋 Listing messages...")
    response = requests.get(
        f"{base_url}/api/comm/messages",
        headers=headers
    )

    if response.status_code == 200:
        messages = response.json()
        print(f"✅ Found {messages.get('total', 0)} messages")
        if messages.get('items'):
            for msg in messages['items'][:3]:  # Show first 3
                print(f"  - {msg['subject'][:50]}... ({msg['thread_type']})")
    else:
        print(f"❌ Failed to list messages: {response.status_code} - {response.text}")

if __name__ == "__main__":
    print("🧪 Testing KinJo Messaging System")
    print("=" * 50)

    # Check if server is running
    try:
        response = requests.get("http://127.0.0.1:8000/health", timeout=5)
        if response.status_code == 200:
            print("✅ Server is running")
            test_messaging()
        else:
            print("❌ Server not responding")
    except requests.exceptions.RequestException:
        print("❌ Cannot connect to server. Please start the server first:")
        print("   python main.py")

    print("=" * 50)
    print("Test completed!")