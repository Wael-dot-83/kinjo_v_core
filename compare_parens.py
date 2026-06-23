import ast

# Current line in file
current_line = "sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file))))))"

# What user wants
user_correct = "sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file))))"

print(f"Current file line: {current_line}")
print(f"User wants: {user_correct}")
print(f"Current has {current_line.count(')')} parens")
print(f"User wants {user_correct.count(')')} parens")

# Check if user's version is syntactically correct
try:
    compile(user_correct, '<string>', 'exec')
    print("\nUser's version is syntactically correct")
except SyntaxError as e:
    print(f"\nUser's version has syntax error: {e}")

# Check if current is syntactically correct
try:
    compile(current_line, '<string>', 'exec')
    print("Current version is syntactically correct")
except SyntaxError as e:
    print(f"Current version has syntax error: {e}")