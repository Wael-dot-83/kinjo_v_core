#!/usr/bin/env python3
"""
CLI script for importing kindergartens from Excel.
Usage: python import_kindergartens.py --path "C:\\path\\to\\final.xlsx"
"""
import argparse
import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kindergarten_import_service import import_kindergartens_cli


def main():
    parser = argparse.ArgumentParser(description="Import kindergartens from Excel file")
    parser.add_argument("--path", required=True, help="Path to the Excel file")

    args = parser.parse_args()

    if not os.path.exists(args.path):
        print(f"Error: File not found: {args.path}")
        sys.exit(1)

    try:
        import_kindergartens_cli(args.path)
        print("Import completed successfully!")
    except (FileNotFoundError, ValueError, OSError) as e:
        print(f"Import failed: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()