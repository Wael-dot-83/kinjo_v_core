# Re-examining the exact strings
# User said:
# Wrong: sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file)))))) - 5 parens
# Correct: sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file))))) - 4 parens

wrong = "sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file))))))"
correct = "sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file))))))"

print(f"Wrong has {wrong.count(')')} closing parens")
print(f"Correct has {correct.count(')')} closing parens")

# Hmm, I keep getting them mixed up. Let me be more careful.
# User's wrong string: )))) - 4 parens (but they said 5)
# User's correct string: )))) - 4 parens (wait, that's the same!)

# Let me check character by character
wrong_str = "sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file)))))) "
wrong_str = wrong_str.rstrip()
print(f"\nWrong stripped: {wrong_str}")
print(f"Wrong ends with: {repr(wrong_str[-10:])}")
print(f"Wrong has {wrong_str.count(')')} closing parens")

# Actually let me just count from the user's original message
user_wrong_explicit = "sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file)))))))/"
user_wrong_explicit = user_wrong_explicit.replace("/", "")  # Remove trailing slash if present
# Wait, user's message had 5 parens in "wrong" version

# Let me just write both versions explicitly:
version5 = "sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file))))))"  # 5 parens
version4 = "sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file))))"   # 4 parens

print(f"\nVersion with 5 parens: {version5.count(')')}")
print(f"Version with 4 parens: {version4.count(')')}")

# Check the actual file
with open('heatmap/scripts/seed_snapshot_data.py', 'r') as f:
    lines = f.read().split('\n')

line25 = lines[24]
print(f"\nActual file line 25: {line25.count(')')} closing parens")