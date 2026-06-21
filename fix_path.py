import re

with open('heatmap/scripts/seed_snapshot_data.py', 'r') as f:
    content = f.read()

# Show the exact content of line 25
lines = content.split('\n')
print(f"Line 25 before: {repr(lines[24])}")

# Fix the extra parenthesis - 5 closing parens to 4
# Count: insert(, dirname(, dirname(, dirname(, abspath() = 5 opens, 5 closes needed
# But we have 5 closes in the wrong place. Let me count more carefully:
# os.path.abspath(__file__) -> 2 closes
# os.path.dirname(...) -> 1 close = 3 total
# os.path.dirname(...) -> 1 close = 4 total
# sys.path.insert(0, ...) -> 1 close = 5 total
# So we need 5 closing parens total, but currently we have 5+ on the line.

old = 'sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file))))))'
new = 'sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file)))))'

content = content.replace(old, new)

with open('heatmap/scripts/seed_snapshot_data.py', 'w') as f:
    f.write(content)

print("Fixed!")