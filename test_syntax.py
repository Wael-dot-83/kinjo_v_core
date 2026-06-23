# Test if current file is syntactically correct
import ast

with open('heatmap/scripts/seed_snapshot_data.py', 'r') as f:
    content = f.read()

# Check syntax
try:
    ast.parse(content)
    print("File has valid Python syntax")
except SyntaxError as e:
    print(f"Syntax error on line {e.lineno}: {e.msg}")
    print(f"Text: {e.text}")

# Also check the parenthesis balance
lines = content.split('\n')
line25 = lines[24]
print(f"\nLine 25: {repr(line25)}")
print(f"Opening parens: {line25.count('(')}")
print(f"Closing parens: {line25.count(')')}")
print(f"Balance: {line25.count('(') - line25.count(')')}")