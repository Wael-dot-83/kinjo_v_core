wrong_str = "sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file))))))"
desired_str = "sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file))))"

print(f"Wrong string ({wrong_str.count(')')} parens): {wrong_str}")
print(f"Desired string ({desired_str.count(')')} parens): {desired_str}")

# Current file
with open('heatmap/scripts/seed_snapshot_data.py', 'r') as f:
    content = f.read()
    
lines = content.split('\n')
line25 = lines[24]
print(f"\nActual file ({line25.count(')')} parens): {line25}")

# Check syntax
import ast
try:
    ast.parse(content)
    print("\nFile syntax: VALID")
except SyntaxError as e:
    print(f"\nFile syntax: INVALID - {e}")