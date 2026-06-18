"""CSV helpers shared by admin-facing exports."""


def escape_csv_formula(value: object) -> str:
    """Escape spreadsheet formula injection prefixes in exported CSV cells."""
    text = "" if value is None else str(value)
    if text and text[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text
    return text
