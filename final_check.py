# Check the exact parentheses count
with open('heatmap/scripts/seed_snapshot_data.py', 'r') as f:
    lines = f.read().split('\n')

line25 = lines[24]
print(f"Line 25 raw: {line25}")
print(f"Last char: {repr(line25[-1])}")
print(f"Last 5 chars: {repr(line25[-5:])}")
print(f"Opening parens: {line25.count('(')}")
print(f"Closing parens: {line25.count(')')}")

# Check if syntactically correct
import ast
try:
    ast.parse(lines[0] + lines[1] + '...')  # Just check part of it
    # Full parse
    full_content = '\n'.join(lines)
    ast.parse(full_content)
    print("\nPASS: File has valid syntax")
except SyntaxError as e:
    print(f"\nFAIL: Syntax error - {e}")