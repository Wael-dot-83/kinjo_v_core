# Correct parenthesis count for the path line
# os.path.abspath(__file__) - 1 close paren
# os.path.dirname(...) - 3 more close parens
# sys.path.insert(0, ...) - 1 close paren
# Total: 5 close parens

correct_line = 'sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file)))))'
print(f"Correct line: {correct_line}")
print(f"Closing parens count: {correct_line.count(')')}")  # Should be 5

# What the user said was wrong (5 parens - extra)
wrong_line = 'sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file))))))'
print(f"\nWrong line (5 parens): {wrong_line}")
print(f"Closing parens count: {wrong_line.count(')')}")

# What the user wants (4 parens) - but this is actually incorrect!
user_wants = 'sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file))))'
print(f"\nUser wants (4 parens): {user_wants}")
print(f"Closing parens count: {user_wants.count(')')}")