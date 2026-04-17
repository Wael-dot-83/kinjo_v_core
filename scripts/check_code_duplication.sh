#!/bin/bash
# Check for code duplication using jscpd and other tools

# Run jscpd for duplication detection
npx jscpd --config .jscpd.json --reporters console
if [ $? -ne 0 ]; then
  echo "Duplication check failed."
  exit 1
fi

# Check for forbidden file patterns in repo
forbidden_files=$(find . -name "*.bak" -o -name "*.backup" -o -name "*.diff" -o -name "*.old" -o -name "*.copy" | grep -v archive/)
if [ -n "$forbidden_files" ]; then
  echo "Found forbidden backup files:"
  echo "$forbidden_files"
  exit 1
fi

# Check for extra DB files
extra_dbs=$(find . -name "*.db" | grep -v kinjo_dev.db)
if [ -n "$extra_dbs" ]; then
  echo "Found unauthorized DB files:"
  echo "$extra_dbs"
  exit 1
fi

# Existing checks
flake8 --select=F811 .
pylint $(git ls-files '*.py') | grep duplicate
