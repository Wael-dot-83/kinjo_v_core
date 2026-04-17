#!/usr/bin/env python3
"""Fix corrupted Child fixtures in test_missing_endpoints.py"""
from datetime import date, timedelta

with open('tests/test_missing_endpoints.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix all Child fixtures to include date_of_birth
# Pattern 1: Already has gender but missing date_of_birth  
old_pattern1 = '''child = models.Child(
            first_name="Test",
            last_name="Child",
            parent_id=parent_profile.id,
            gender=models.Gender.MALE
        )'''
new_pattern1 = '''child = models.Child(
            first_name="Test",
            last_name="Child",
            parent_id=parent_profile.id,
            gender=models.Gender.MALE,
            date_of_birth=date.today() - timedelta(days=365 * 3)
        )'''

content = content.replace(old_pattern1, new_pattern1)

# Pattern 2: If there are any without gender
old_pattern2 = '''child = models.Child(
            first_name="Test",
            last_name="Child",
            parent_id=parent_profile.id
        )'''
new_pattern2 = '''child = models.Child(
            first_name="Test",
            last_name="Child",
            parent_id=parent_profile.id,
            gender=models.Gender.MALE,
            date_of_birth=date.today() - timedelta(days=365 * 3)
        )'''

content = content.replace(old_pattern2, new_pattern2)

with open('tests/test_missing_endpoints.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Fixed')
