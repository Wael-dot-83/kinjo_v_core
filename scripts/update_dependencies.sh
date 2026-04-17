#!/bin/bash
# Update all Python dependencies and show outdated packages
pip list --outdated
pip install --upgrade -r requirements.txt
pip list --outdated
