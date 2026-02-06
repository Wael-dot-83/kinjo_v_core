#!/bin/bash
# Pre-commit hook: run lint, format, and tests
black .
isort .
flake8 .
pylint $(git ls-files '*.py')
pytest
if [ $? -ne 0 ]; then
  echo "Pre-commit checks failed. Commit aborted."
  exit 1
fi
