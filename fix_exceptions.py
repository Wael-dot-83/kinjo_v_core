#!/usr/bin/env python3
"""
Script to systematically replace bare exception handlers with specific exception types and logging.

This script identifies patterns like:
    except SpecificError:
    except SpecificError as e:
    
And replaces them with specific exception types and proper logging.

Usage:
    python fix_exceptions.py --check    # Report issues
    python fix_exceptions.py --fix      # Apply fixes
"""

import os
import re
import sys
import argparse
from pathlib import Path
from typing import List, Tuple, Dict

# Python files to check
PYTHON_FILES_PATTERN = "*.py"
EXCLUDE_DIRS = {".git", "__pycache__", ".pytest_cache", ".venv", "venv", "node_modules"}

# Patterns to fix
BARE_EXCEPTION_PATTERNS = [
    (r"except\s+Exception\s*:\s*\n\s+pass\s*\n", "bare_except_pass"),
    (r"except\s+Exception\s*:\s*\n\s+#", "bare_except_comment"),
    (r"except\s+Exception\s*:\s*\n\s+(?!logger|raise|return)", "bare_except_code"),
]

def find_python_files(root_dir: str) -> List[Path]:
    """Recursively find all Python files."""
    files = []
    root = Path(root_dir)
    for item in root.rglob("*.py"):
        # Skip excluded directories
        if any(excluded in item.parts for excluded in EXCLUDE_DIRS):
            continue
        files.append(item)
    return sorted(files)


def check_file_exceptions(file_path: Path) -> List[Dict]:
    """Check a file for bare exception handlers."""
    issues = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            lines = content.split("\n")
    except (OSError, UnicodeError):
        return issues

    # Simple regex to find bare exceptions
    pattern = r"except\s+(Exception|BaseException)\s*(\s+as\s+\w+)?:\s*$"
    for i, line in enumerate(lines, 1):
        if re.search(pattern, line):
            # Get context
            context_start = max(0, i - 3)
            context_end = min(len(lines), i + 3)
            context = lines[context_start:context_end]
            
            issues.append({
                "file": str(file_path),
                "line": i,
                "content": line.strip(),
                "context": context
            })

    return issues


def report_issues(all_issues: Dict[Path, List[Dict]]) -> None:
    """Report found issues."""
    total = sum(len(issues) for issues in all_issues.values())
    
    print(f"\n{'='*70}")
    print(f"Found {total} bare exception handler(s)")
    print(f"{'='*70}\n")
    
    for file_path, issues in sorted(all_issues.items()):
        if not issues:
            continue
        
        print(f"\n📄 {file_path.relative_to(Path.cwd())}")
        print(f"   ({len(issues)} issue(s))\n")
        
        for issue in issues:
            print(f"   Line {issue['line']}: {issue['content']}")
            print(f"   Context:")
            for ctx_line in issue['context']:
                print(f"      {ctx_line}")
            print()


def get_appropriate_exception_type(context_lines: List[str]) -> str:
    """Determine appropriate exception type based on context."""
    context = "\n".join(context_lines).lower()
    
    # Detect specific exception types
    if "sqlalchemy" in context or "database" in context or "query" in context:
        return "sqlalchemy.exc.SQLAlchemyError"
    elif "requests" in context or "http" in context or "response" in context:
        return "requests.RequestException"
    elif "json" in context:
        return "json.JSONDecodeError"
    elif "file" in context or "open" in context or "path" in context:
        return "OSError"
    elif "redis" in context or "cache" in context:
        return "redis.RedisError"
    else:
        return "Exception  # Replace with a context-specific exception type"


def generate_fix_suggestions(all_issues: Dict[Path, List[Dict]]) -> None:
    """Generate fix suggestions."""
    print(f"\n{'='*70}")
    print("FIX RECOMMENDATIONS")
    print(f"{'='*70}\n")
    
    summary = {
        "critical": 0,  # silently fails (pass)
        "high": 0,      # generic error handling
        "medium": 0     # has some handling
    }
    
    for file_path, issues in sorted(all_issues.items()):
        for issue in issues:
            next_line = ""
            context = issue['context']
            for i, ctx in enumerate(context):
                if str(issue['line']) in f"Line {issue['line']}":
                    if i + 1 < len(context):
                        next_line = context[i + 1].strip()
                        break
            
            if next_line == "pass":
                summary["critical"] += 1
                severity = "🔴 CRITICAL"
            elif not next_line or next_line.startswith("#"):
                summary["high"] += 1
                severity = "🟠 HIGH"
            else:
                summary["medium"] += 1
                severity = "🟡 MEDIUM"
            
            print(f"{severity} {file_path.relative_to(Path.cwd())}:{issue['line']}")
    
    print(f"\n\nSUMMARY:")
    print(f"  🔴 Critical (silent failures): {summary['critical']}")
    print(f"  🟠 High severity: {summary['high']}")
    print(f"  🟡 Medium severity: {summary['medium']}")


def main():
    parser = argparse.ArgumentParser(description="Fix bare exception handlers")
    parser.add_argument("--check", action="store_true", help="Check for issues only")
    parser.add_argument("--fix", action="store_true", help="Apply fixes")
    parser.add_argument("--dir", default=".", help="Root directory to scan")
    args = parser.parse_args()

    if not args.check and not args.fix:
        args.check = True  # Default to check mode

    print("🔍 Scanning Python files for bare exception handlers...")
    
    python_files = find_python_files(args.dir)
    print(f"Found {len(python_files)} Python files\n")

    all_issues: Dict[Path, List[Dict]] = {}
    for file_path in python_files:
        issues = check_file_exceptions(file_path)
        if issues:
            all_issues[file_path] = issues

    if not all_issues:
        print("✅ No bare exception handlers found!")
        return

    if args.check:
        report_issues(all_issues)
        generate_fix_suggestions(all_issues)
    
    if args.fix:
        print("\n⚠️  FIX MODE: To be implemented based on analysis")
        print("Manual review recommended for each fix\n")


if __name__ == "__main__":
    main()
