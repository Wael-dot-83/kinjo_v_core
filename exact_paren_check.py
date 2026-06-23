# Check exact parenthesis count
with open('heatmap/scripts/seed_snapshot_data.py', 'r') as f:
    lines = f.read().split('\n')

line25 = lines[24]

# Count each paren type
opens = line25.count('(')
closes = line25.count(')')

print(f"Line 25: {repr(line25)}")
print(f"Opening parens: {opens}")
print(f"Closing parens: {closes}")
print(f"Balance: {opens - closes}")

# User's exact strings
user_wrong = "sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file))))))"
user_correct = "sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file))))"

print(f"\nUser wrong ({user_wrong.count(')')} parens): {user_wrong}")
print(f"User correct ({user_correct.count(')')} parens): {user_correct}")

# Check if line matches
if line25.rstrip() == user_wrong:
    print("File matches user's wrong string - needs to be changed to 4 parens")
elif line25.rstrip() == user_correct:
    print("File matches user's correct string - already fixed!")
else:
    print(f"File doesn't match either - current: {line25.count(')')} parens")