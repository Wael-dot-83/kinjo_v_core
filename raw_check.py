with open('heatmap/scripts/seed_snapshot_data.py', 'rb') as f:
    content = f.read()

lines = content.decode('utf-8').split('\n')
line25 = lines[24]

# Show each character in the last 10 positions
print("Characters at end of line 25:")
for i, c in enumerate(line25[-10:]):
    print(f"  pos {len(line25)-10+i}: {repr(c)}")

print(f"\nTotal '(' in line 25: {line25.count('(')}")
print(f"Total ')' in line 25: {line25.count(')')}")

# Check if the user's strings match
user_wrong = "sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file))))))"
user_correct = "sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file))))"

print(f"\nUser wrong: {repr(user_wrong)}")
print(f"Current file: {repr(line25)}")
print(f"Match wrong: {line25 == user_wrong}")
print(f"Match correct: {line25 == user_correct}")