#!/bin/bash
# Run full test suite with coverage
pytest -v --cov=. --cov-report=html
