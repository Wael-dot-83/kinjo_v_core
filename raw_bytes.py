# Check exact bytes
with open('heatmap/scripts/seed_snapshot_data.py', 'rb') as f:
    content = f.read()

lines = content.decode('utf-8').split('\n')
line25 = lines[24]

# Show last 15 characters
print(f"Last 15 chars: {repr(line25[-15:])}")
print(f"Opening parens: {line25.count('(')}")
print(f"Closing parens: {line25.count(')')}")

# This should show us exactly what's there