# Exact count of parens on line 25
with open('heatmap/scripts/seed_snapshot_data.py', 'rb') as f:
    content = f.read()

lines = content.decode('utf-8').split('\n')
line25 = lines[24]

# Show exact ending
print(f"Line 25: {repr(line25)}")
print(f"Last 10 chars: {repr(line25[-10:])}")
print(f"Number of ')' in line: {line25.count(')')}")

# User's strings from the request
user_wrong = "sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file))))))"
user_correct = "sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file))))))"

print(f"\nUser 'wrong' string has {user_wrong.count(')')} ')' chars")
print(f"User 'correct' string has {user_correct.count(')')} ')' chars")

# My current line
print(f"\nMy line ends with: {repr(line25[-5:])}")