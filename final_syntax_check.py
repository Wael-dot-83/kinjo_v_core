import ast

with open('heatmap/scripts/seed_snapshot_data.py', 'r') as f:
    content = f.read()

try:
    ast.parse(content)
    print("PASS: File has valid Python syntax")
except SyntaxError as e:
    print(f"FAIL: Syntax error - {e}")