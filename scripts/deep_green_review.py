"""
Deep green review — every accessible page.
Checks: (1) no blue, (2) primary brand green IS present, (3) screenshots.
"""
import asyncio, sys, os
sys.stdout.reconfigure(encoding="utf-8")
from playwright.async_api import async_playwright

BASE = "http://127.0.0.1:8000"
OUT  = r"d:\Final Version\scripts\screenshots\deep"

BRAND_GREEN   = "rgb(31, 94, 71)"    # #1F5E47
MEDIUM_GREEN  = "rgb(47, 125, 98)"   # #2F7D62
DARK_GREEN    = "rgb(22, 61, 46)"    # #163d2e

BLUE_RGBS = [
    "rgb(37, 99, 235)",   # #2563eb
    "rgb(13, 110, 253)",  # #0d6efd
    "rgb(59, 130, 246)",  # #3b82f6
    "rgb(29, 78, 216)",   # #1d4ed8
    "rgb(30, 64, 175)",   # #1e40af
    "rgb(0, 123, 255)",   # #007bff
    "rgb(23, 162, 184)",  # #17a2b8 info-blue
]

BLUE_BG_PARTIAL = [
    "rgba(13, 110, 253",
    "rgba(37, 99, 235",
    "rgba(59, 130, 246",
]

# Script that scans for blue and reports green presence
SCAN_JS = """() => {
    const blueRgbs = """ + str(BLUE_RGBS) + """;
    const brandGreen = '""" + BRAND_GREEN + """';
    const medGreen   = '""" + MEDIUM_GREEN + """';
    const darkGreen  = '""" + DARK_GREEN + """';

    let blues = [];
    let hasGreen = false;
    let greenElements = [];

    document.querySelectorAll('*').forEach(el => {
        const rect = el.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) return;
        const s = getComputedStyle(el);
        const bg = s.backgroundColor;
        const color = s.color;

        // Check for blue
        for (const b of blueRgbs) {
            if (bg === b || color === b) {
                blues.push({
                    tag: el.tagName,
                    cls: (el.className||'').slice(0, 60),
                    id: el.id,
                    text: (el.textContent||'').trim().slice(0, 40),
                    bg: bg !== 'rgba(0, 0, 0, 0)' ? bg : null,
                    color
                });
                break;
            }
        }

        // Check for brand green presence
        if (bg === brandGreen || bg === medGreen || bg === darkGreen) {
            hasGreen = true;
            greenElements.push({
                tag: el.tagName,
                cls: (el.className||'').slice(0, 60),
                bg
            });
        }
    });

    return { blues: blues.slice(0, 30), hasGreen, greenCount: greenElements.length,
             greenSamples: greenElements.slice(0, 5) };
}"""

async def scan_page(page, url, name):
    try:
        resp = await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(2000)
        status = resp.status if resp else "?"
        final_url = page.url

        await page.screenshot(
            path=os.path.join(OUT, f"{name}.png"),
            full_page=False,
            clip={"x": 0, "y": 0, "width": 1440, "height": 900}
        )

        result = await page.evaluate(SCAN_JS)

        # Check CSS vars
        bs_primary    = await page.evaluate("() => getComputedStyle(document.documentElement).getPropertyValue('--bs-primary').trim()")
        kinjo_primary = await page.evaluate("() => getComputedStyle(document.documentElement).getPropertyValue('--kinjo-primary').trim()")

        # Check buttons
        btn_color = await page.evaluate("""() => {
            const btn = document.querySelector('.btn-primary, button.btn-primary');
            if (!btn) return null;
            return getComputedStyle(btn).backgroundColor;
        }""")

        # Check navbar/sidebar background
        nav_bg = await page.evaluate("""() => {
            const n = document.querySelector('.kinjo-navbar, .navbar, .admin-sidebar, .sidebar');
            return n ? getComputedStyle(n).backgroundColor : null;
        }""")

        # Check links
        link_color = await page.evaluate("""() => {
            const a = document.querySelector('a:not(.btn):not([class*="btn"])');
            return a ? getComputedStyle(a).color : null;
        }""")

        blue_count = len(result['blues'])
        green_ok = result['hasGreen']

        # Determine navbar is green
        nav_green = nav_bg and ("31, 94, 71" in nav_bg or "47, 125, 98" in nav_bg or "22, 61, 46" in nav_bg)

        return {
            "name": name,
            "url": url,
            "final_url": final_url,
            "status": status,
            "blues": result['blues'],
            "blue_count": blue_count,
            "has_green": green_ok,
            "green_count": result['greenCount'],
            "green_samples": result['greenSamples'],
            "bs_primary": bs_primary,
            "kinjo_primary": kinjo_primary,
            "btn_color": btn_color,
            "nav_bg": nav_bg,
            "nav_green": nav_green,
            "link_color": link_color,
        }
    except Exception as ex:
        return {"name": name, "url": url, "error": str(ex)[:120],
                "blue_count": -1, "has_green": False, "nav_green": False}


async def main():
    os.makedirs(OUT, exist_ok=True)

    PUBLIC_PAGES = [
        ("home",           "/"),
        ("login",          "/login"),
        ("register",       "/register"),
        ("about",          "/about"),
        ("services",       "/services"),
        ("faq",            "/faq"),
        ("contact",        "/contact"),
        ("privacy",        "/privacy"),
        ("terms",          "/terms"),
        ("forgot_pw",      "/forgot-password"),
    ]

    ADMIN_PAGES = [
        ("adm_dashboard",       "/admin/dashboard"),
        ("adm_analytics",       "/admin/analytics"),
        ("adm_governance",      "/admin/governance-reports"),
        ("adm_heatmap",         "/admin/heatmap"),
        ("adm_users",           "/admin/users"),
        ("adm_classification",  "/admin/classification"),
        ("adm_audit",           "/admin/audit-logs"),
        ("adm_reports",         "/admin/analytics/reports"),
        ("adm_incidents",       "/admin/reports/incidents"),
        ("adm_messages",        "/admin/messages"),
        ("adm_settings",        "/admin/settings"),
        ("adm_profile",         "/admin/profile"),
        ("adm_safety",          "/admin/safety-analytics"),
        ("adm_import_logs",     "/admin/import-logs"),
    ]

    USER_PAGES = [
        ("user_dashboard",  "/dashboard"),
        ("kindergartens",   "/kindergartens"),
    ]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        # ── PUBLIC (no auth) ────────────────────────────────────────────────
        print("\n=== PUBLIC PAGES (unauthenticated) ===")
        ctx_pub = await browser.new_context(viewport={"width": 1440, "height": 900})
        page_pub = await ctx_pub.new_page()

        pub_results = []
        for name, path in PUBLIC_PAGES:
            r = await scan_page(page_pub, BASE + path, "pub_" + name)
            pub_results.append(r)
            blue_icon = "✅" if r["blue_count"] == 0 else f"❌{r['blue_count']}"
            green_icon = "🟢" if r.get("has_green") else "⚪"
            nav_icon = "🟢nav" if r.get("nav_green") else "⚪nav"
            err = r.get("error", "")
            print(f"  {name:<20} blue={blue_icon}  green={green_icon}  {nav_icon}  bs={r.get('bs_primary','?')[:10]}  {err}")
        await ctx_pub.close()

        # ── ADMIN (authenticated) ───────────────────────────────────────────
        print("\n=== ADMIN PAGES (as admin) ===")
        ctx_adm = await browser.new_context(viewport={"width": 1440, "height": 900})
        page_adm = await ctx_adm.new_page()

        await page_adm.goto(f"{BASE}/login", wait_until="domcontentloaded")
        await page_adm.fill("input[name='username']", "admin")
        await page_adm.fill("input[name='password']", "Admin@1234")
        await page_adm.click("button[type='submit']")
        await page_adm.wait_for_load_state("networkidle")
        print(f"  Logged in as admin. URL: {page_adm.url}")

        adm_results = []
        for name, path in ADMIN_PAGES:
            r = await scan_page(page_adm, BASE + path, "adm_" + name)
            adm_results.append(r)
            blue_icon = "✅" if r["blue_count"] == 0 else f"❌{r['blue_count']}"
            green_icon = "🟢" if r.get("has_green") else "⚪"
            nav_icon = "🟢nav" if r.get("nav_green") else "⚪nav"
            err = r.get("error", "")
            print(f"  {name:<22} blue={blue_icon}  green={green_icon}  {nav_icon}  btn={str(r.get('btn_color','?'))[:25]}  {err}")
        await ctx_adm.close()

        # ── USER DASHBOARD (authenticated) ─────────────────────────────────
        print("\n=== USER PAGES (as admin/manager) ===")
        ctx_usr = await browser.new_context(viewport={"width": 1440, "height": 900})
        page_usr = await ctx_usr.new_page()

        await page_usr.goto(f"{BASE}/login", wait_until="domcontentloaded")
        await page_usr.fill("input[name='username']", "admin")
        await page_usr.fill("input[name='password']", "Admin@1234")
        await page_usr.click("button[type='submit']")
        await page_usr.wait_for_load_state("networkidle")

        usr_results = []
        for name, path in USER_PAGES:
            r = await scan_page(page_usr, BASE + path, "usr_" + name)
            usr_results.append(r)
            blue_icon = "✅" if r["blue_count"] == 0 else f"❌{r['blue_count']}"
            green_icon = "🟢" if r.get("has_green") else "⚪"
            nav_icon = "🟢nav" if r.get("nav_green") else "⚪nav"
            err = r.get("error", "")
            print(f"  {name:<22} blue={blue_icon}  green={green_icon}  {nav_icon}  btn={str(r.get('btn_color','?'))[:25]}  {err}")
        await ctx_usr.close()

        # ── SUMMARY ─────────────────────────────────────────────────────────
        all_results = pub_results + adm_results + usr_results
        total_pages = len(all_results)
        total_blue = sum(r["blue_count"] for r in all_results if r.get("blue_count", 0) >= 0)
        pages_with_blue = sum(1 for r in all_results if r.get("blue_count", 0) > 0)
        pages_with_green = sum(1 for r in all_results if r.get("has_green"))
        pages_with_green_nav = sum(1 for r in all_results if r.get("nav_green"))
        error_pages = [r for r in all_results if r.get("error")]

        print(f"\n{'='*60}")
        print(f"SUMMARY — {total_pages} pages checked")
        print(f"  Blue elements total:    {total_blue}  (pages with blue: {pages_with_blue})")
        print(f"  Pages with green bg:    {pages_with_green}/{total_pages}")
        print(f"  Pages with green nav:   {pages_with_green_nav}/{total_pages}")
        print(f"  Error pages:            {len(error_pages)}")
        print(f"  Screenshots:            {OUT}")
        print()

        # Report any remaining blues in detail
        for r in all_results:
            if r.get("blue_count", 0) > 0:
                print(f"\n  BLUES on {r['name']}:")
                for b in r.get("blues", []):
                    print(f"    {b}")

        # Report pages with no green (might indicate CSS not loading)
        no_green = [r["name"] for r in all_results if not r.get("has_green") and not r.get("error")]
        if no_green:
            print(f"\n  Pages with NO green bg found: {no_green}")

        await browser.close()

asyncio.run(main())
