#!/bin/bash
# Check for code duplication using flake8 and pylint
flake8 --select=F811 .
pylint $(git ls-files '*.py') | grep duplicate
