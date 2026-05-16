#!/bin/bash
# Run full test suite with coverage and duplication checks

# Run duplication and hygiene checks
./scripts/check_code_duplication.sh
if [ $? -ne 0 ]; then
  echo "Duplication/hygiene check failed."
  exit 1
fi

# Run tests with coverage
pytest -v --cov=. --cov-report=html
