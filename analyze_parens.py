import os.path

# Let's parse the expression to understand the correct count
# The expression is: sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Let me count manually:
# os.path.abspath(__file__) -> needs closing paren for abspath() -> 1
# os.path.dirname(...) -> needs closing paren for dirname -> 1 -> 2 total
# os.path.dirname(...) -> needs closing paren for dirname -> 1 -> 3 total
# os.path.dirname(...) -> needs closing paren for dirname -> 1 -> 4 total
# sys.path.insert(0, ...) -> needs closing paren for insert -> 1 -> 5 total

# So 5 closing parens are correct!

# But wait - the original file from user's request shows 5 parens already...
# Let me re-read what the user asked:

# User showed CURRENT (wrong): 5 closing parens
# User wants: 4 closing parens

# That seems backward - 5 is correct, 4 is wrong!

# Unless... the user meant something different. Let me check the actual file content
with open('heatmap/scripts/seed_snapshot_data.py', 'r') as f:
    lines = f.read().split('\n')
    line25 = lines[24]
    
print(f"Line 25: {repr(line25)}")
print(f"Opens: {line25.count('(')}")
print(f"Closes: {line25.count(')')}")

# Let's see what the file looks like now after my edits
# Maybe I already fixed it to 4 parens (which would be wrong)