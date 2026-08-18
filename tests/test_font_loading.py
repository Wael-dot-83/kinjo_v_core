"""A page must actually load the typeface it asks for.

CSS fails soft. `font-family: "Noto Sans Arabic", -apple-system, ...` on a page
that never fetched Noto Sans Arabic does not error -- the browser quietly walks
to the next entry. The page looks fine to anyone who does not know what it was
supposed to look like, which is why this went unnoticed.

It was not a corner case. Before this gate, 91 of 92 rendered documents named a
primary family the document never loaded, in two distinct shapes:

  * 39 documents on the base.html shell -- login, register, forgot and reset
    password, MFA setup, the parent and supervisor modules, the public pages,
    403/404 and the KPI dashboard -- requested **Noto Sans Arabic** and loaded
    only Cairo and Inter. Arabic is this product's default language, so the
    default language of the login page was rendering in a system fallback.

  * 52 documents on the admin/manager shell requested **Cairo** (admin's
    --font-arabic led with it) and loaded Noto Sans Arabic. That one degraded
    politely, because Cairo's stack named Noto second, so it had been invisible
    for as long as it had existed.

Primary versus fallback
-----------------------
Only the FIRST real family in a stack has to be loaded. Later entries are
fallbacks and are supposed to be things the machine might already have --
`-apple-system`, `Segoe UI`, `Helvetica Neue`. Flagging those would be noise,
and a noisy gate gets deleted. `Fira Code` and `JetBrains Mono` sitting second
in a mono stack are fine; leading with them was not, because nothing loads them
and a developer with them installed then sees a different product from
everyone else.

A family is considered loaded if the document pulls it from Google Fonts or
declares an @font-face for it in a stylesheet it loads.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
CSS_DIR = ROOT / "static" / "css"

_EXTENDS = re.compile(r"""{%-?\s*extends\s+["']([^"']+)["']""")
_CSS_LINK = re.compile(r"""href=["']/static/css/([^"'?]+)""")
_GOOGLE = re.compile(r"fonts\.googleapis\.com/css2\?([^\"']+)")
_FONT_FACE = re.compile(r"""@font-face[^}]*font-family:\s*["']?([^;"'}]+)""")
_FONT_FAMILY = re.compile(r"font-family:\s*([^;}]+)")
_VAR = re.compile(r"var\((--[a-z0-9-]+)")
_TOKEN_DEF = re.compile(r"(?m)^\s*(--[a-z0-9-]+)\s*:\s*([^;]+);")

# Families a machine may reasonably already have, plus the CSS generics. These
# are legitimate as fallbacks and are never required to be fetched.
SYSTEM_OR_GENERIC = {
    "sans-serif", "serif", "monospace", "cursive", "fantasy",
    "system-ui", "ui-sans-serif", "ui-serif", "ui-monospace", "inherit",
    "-apple-system", "BlinkMacSystemFont", "Segoe UI", "Segoe UI Emoji",
    "Roboto", "Tahoma", "Arial", "Helvetica", "Helvetica Neue", "Verdana",
    "Courier New", "Consolas", "SFMono-Regular", "SF Mono", "Liberation Mono",
    "Menlo", "Monaco", "Apple Color Emoji", "Noto Color Emoji",
    # An icon font, loaded via its own vendored stylesheet rather than a family
    # request; it is checked by test_static_asset_integrity instead.
    "bootstrap-icons",
}


def _chain(path, seen=None):
    """Template source plus every ancestor it extends."""
    seen = seen or set()
    if path in seen or not path.is_file():
        return ""
    seen.add(path)
    text = path.read_text(encoding="utf-8", errors="replace")
    parent = _EXTENDS.search(text)
    if parent:
        text += _chain(TEMPLATES / parent.group(1), seen)
    return text


def _token_values():
    values = {}
    for f in sorted(CSS_DIR.glob("*.css")):
        for m in _TOKEN_DEF.finditer(f.read_text(encoding="utf-8", errors="replace")):
            values.setdefault(m.group(1), m.group(2).strip())
    return values


def google_families(html):
    """Families the document requests from Google Fonts."""
    families = set()
    for m in _GOOGLE.finditer(html):
        for part in m.group(1).split("&"):
            if part.startswith("family="):
                families.add(part[len("family="):].split(":")[0].replace("+", " "))
    return families


def primary_family(value, tokens, depth=0):
    """The first real family of a stack, resolving var() indirection."""
    value = value.strip()
    m = _VAR.match(value)
    if m and depth < 5 and m.group(1) in tokens:
        return primary_family(tokens[m.group(1)], tokens, depth + 1)
    for part in value.split(","):
        name = part.strip().strip("'\"").strip()
        if name and not name.startswith("var("):
            return name
    return None


def _documents():
    for path in sorted(TEMPLATES.rglob("*.html")):
        text = _chain(path)
        if "<html" not in text and "<!doctype" not in text.lower():
            continue
        sheets = list(dict.fromkeys(_CSS_LINK.findall(text)))
        if sheets:
            yield path, text, sheets


def test_every_document_loads_the_primary_families_it_uses():
    tokens = _token_values()
    offenders = []

    for path, html, sheets in _documents():
        available = google_families(html)
        wanted = set()
        for name in sheets:
            f = CSS_DIR / name
            if not f.is_file():
                continue
            css = f.read_text(encoding="utf-8", errors="replace")
            available.update(x.strip() for x in _FONT_FACE.findall(css))
            for m in _FONT_FAMILY.finditer(css):
                fam = primary_family(m.group(1), tokens)
                if fam and fam not in SYSTEM_OR_GENERIC:
                    wanted.add(fam)
        missing = sorted(f for f in wanted if f not in available)
        if missing:
            offenders.append(
                f"{path.relative_to(ROOT).as_posix()} leads with {', '.join(missing)} "
                f"but only loads {', '.join(sorted(available)) or 'nothing'}")

    assert not offenders, (
        "these documents name a primary typeface they never fetch, so the browser "
        "silently renders a fallback:\n  " + "\n  ".join(offenders))


def test_no_document_requests_the_same_family_twice():
    """One family, one request.

    Two <link>s naming the same family is the signature of a divergent loading
    path -- typically a shell and a page each bootstrapping their own fonts,
    which is how the weights drift apart and how a family ends up fetched under
    two different URLs.
    """
    offenders = []
    for path, html, _ in _documents():
        seen, dupes = set(), set()
        for m in _GOOGLE.finditer(html):
            for part in m.group(1).split("&"):
                if not part.startswith("family="):
                    continue
                fam = part[len("family="):].split(":")[0].replace("+", " ")
                (dupes if fam in seen else seen).add(fam)
        if dupes:
            offenders.append(f"{path.relative_to(ROOT).as_posix()}: {', '.join(sorted(dupes))}")
    assert not offenders, (
        "these documents request the same font family more than once; collapse "
        "them onto a single request:\n  " + "\n  ".join(offenders))


def test_the_app_shell_and_admin_shell_agree_on_arabic():
    """Arabic is the default language; the shells must not disagree about it.

    They did. base.html loaded Cairo while its stylesheets asked for Noto Sans
    Arabic, and admin_base.html loaded Noto Sans Arabic while admin's own
    --font-arabic asked for Cairo. Each shell was loading the other's face.
    """
    tokens = _token_values()
    canonical = primary_family("var(--kinjo-font-family-ar)", tokens)
    assert canonical == "Noto Sans Arabic", canonical

    for shell in ("base.html", "admin_base.html", "manager_base.html"):
        html = _chain(TEMPLATES / shell)
        assert canonical in google_families(html), (
            f"{shell} does not load {canonical}, the canonical Arabic face")

    # And admin's alias must not reintroduce a competing opinion.
    for alias in ("--font-arabic", "--font-family-ar"):
        assert primary_family(f"var({alias})", tokens) == canonical, (
            f"{alias} no longer resolves to the canonical Arabic stack")


# --------------------------------------------------------------------------
# Controls
# --------------------------------------------------------------------------

def test_control_primary_family_resolution():
    tokens = {"--a": 'var(--b)', "--b": '"Noto Sans Arabic", Tahoma, sans-serif'}
    assert primary_family("var(--a)", tokens) == "Noto Sans Arabic"
    assert primary_family("'Cairo', 'Noto Sans Arabic'", tokens) == "Cairo"
    assert primary_family("  inherit ", tokens) == "inherit"


def test_control_detects_an_unloaded_primary_family():
    """The defect this gate exists for, reproduced in miniature."""
    tokens = {"--stack": '"Noto Sans Arabic", -apple-system, sans-serif'}
    html = '<link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400&display=swap">'
    available = google_families(html)
    wanted = primary_family("var(--stack)", tokens)
    assert available == {"Cairo"}
    assert wanted == "Noto Sans Arabic"
    assert wanted not in available, "the gate would not have caught the real defect"


def test_control_accepts_an_unloaded_fallback():
    """Fallbacks are allowed to be absent -- otherwise the gate is noise."""
    tokens = {"--mono": 'ui-monospace, SFMono-Regular, "Fira Code", monospace'}
    assert primary_family("var(--mono)", tokens) in SYSTEM_OR_GENERIC


def test_control_detects_a_duplicate_family_request():
    html = ('<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400">'
            '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@700">')
    seen, dupes = set(), set()
    for m in _GOOGLE.finditer(html):
        for part in m.group(1).split("&"):
            if part.startswith("family="):
                fam = part[len("family="):].split(":")[0].replace("+", " ")
                (dupes if fam in seen else seen).add(fam)
    assert dupes == {"Inter"}
