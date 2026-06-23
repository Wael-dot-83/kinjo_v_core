user_wrong = "sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file)))))))/"  # 5 parens + trailing
user_wrong = user_wrong[:-1]  # Remove trailing char to get exact
print(f"User said is WRONG ({user_wrong.count(')')} parens): {user_wrong}")

user_correct = "sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file))))))"  # 4 parens
print(f"User wants CORRECT ({user_correct.count(')')} parens): {user_correct}")

# Current file
with open('heatmap/scripts/seed_snapshot_data.py', 'r') as f:
    content = f.read()
    
lines = content.split('\n')
line25 = lines[24]
print(f"\nActual file ({line25.count(')')} parens): {line25}")