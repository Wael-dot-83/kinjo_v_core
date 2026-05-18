"""Legacy placeholder utility script.

This script intentionally does nothing. It exists to keep historical
references stable while remaining syntactically valid for global
compile checks.
"""

from pathlib import Path


def main() -> int:
    _ = Path(__file__).resolve()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
