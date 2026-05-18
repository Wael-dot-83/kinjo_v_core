#!/usr/bin/env python3
"""
Test script for staff management functionality in kindergarten view
"""
import requests
import json
import sys

BASE_URL = "http://127.0.0.1:8001"

def test_staff_management():
    """Test staff management functionality"""
    print("Testing Staff Management Functionality...")

    # First, login to get token
    login_data = {
        "username": "admin",
        "password": "admin123"
    }

    try:
        response = requests.post(f"{BASE_URL}/api/auth/login", json=login_data)
        if response.status_code != 200:
            print("❌ Login failed")
            return False

        token = response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        print("✅ Login successful")

        # Get kindergartens to find one with staff
        response = requests.get(f"{BASE_URL}/api/kindergartens", headers=headers)
        if response.status_code != 200:
            print("❌ Failed to get kindergartens")
            return False

        kindergartens = response.json()
        if not kindergartens:
            print("❌ No kindergartens found")
            return False

        kindergarten_id = kindergartens[0]["id"]
        print(f"✅ Found kindergarten ID: {kindergarten_id}")

        # Get staff for the kindergarten
        response = requests.get(f"{BASE_URL}/api/users?kindergarten_id={kindergarten_id}", headers=headers)
        if response.status_code != 200:
            print("❌ Failed to get staff")
            return False

        staff = response.json()
        print(f"✅ Found {len(staff)} staff members")

        if staff:
            # Test editing a staff member
            staff_member = staff[0]
            staff_id = staff_member["id"]

            update_data = {
                "username": staff_member["username"],
                "email": staff_member["email"],
                "role": staff_member["role"],
                "status": "INACTIVE" if staff_member["status"] == "ACTIVE" else "ACTIVE"
            }

            response = requests.put(f"{BASE_URL}/api/users/{staff_id}", json=update_data, headers=headers)
            if response.status_code == 200:
                print("✅ Staff edit successful")
            else:
                print(f"❌ Staff edit failed: {response.status_code} - {response.text}")
                return False

            # Test password reset
            response = requests.post(f"{BASE_URL}/api/users/{staff_id}/admin-reset-password", headers=headers)
            if response.status_code == 200:
                print("✅ Password reset successful")
            else:
                print(f"❌ Password reset failed: {response.status_code} - {response.text}")
                return False

        print("✅ All staff management tests passed!")
        return True

    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        return False

if __name__ == "__main__":
    success = test_staff_management()
    sys.exit(0 if success else 1)