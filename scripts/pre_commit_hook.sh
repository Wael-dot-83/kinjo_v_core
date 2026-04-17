#!/bin/bash
# Pre-commit hook: run lint, format, tests, duplication, and hygiene checks

# Hygiene checks: fail on forbidden files
forbidden_patterns=("*.bak" "*.backup" "*.diff" "*.old" "*.copy" "*.db")
for pattern in "${forbidden_patterns[@]}"; do
  if git diff --cached --name-only | grep -q "$pattern"; then
    echo "Error: Attempting to commit forbidden file type: $pattern"
    echo "Do not commit backup files or extra DB files."
    exit 1
  fi
done

# Specific check for DB files (allow only kinjo_dev.db)
if git diff --cached --name-only | grep "\.db$" | grep -v "kinjo_dev.db"; then
  echo "Error: Attempting to commit unauthorized DB file."
  echo "Only kinjo_dev.db is allowed."
  exit 1
fi

# Run duplication check
./scripts/check_code_duplication.sh
if [ $? -ne 0 ]; then
  echo "Duplication check failed. Commit aborted."
  exit 1
fi

# Existing checks
black .
isort .
flake8 .
pylint $(git ls-files '*.py')
pytest
if [ $? -ne 0 ]; then
  echo "Pre-commit checks failed. Commit aborted."
  exit 1
fi
