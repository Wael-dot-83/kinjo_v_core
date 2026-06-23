"""Find all blue elements on the public /dashboard page."""
import asyncio, sys
sys.stdout.reconfigure(encoding="utf-8")
from playwright.async_api import async_playwright

BASE = "http://127.0.0.1:8000"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await ctx.new_page()

        # Login as regular user or admin
        await page.goto(f"{BASE}/login", wait_until="domcontentloaded")
        await page.fill("input[name='username']", "admin")
        await page.fill("input[name='password']", "Admin@1234")
        await page.click("button[type='submit']")
        await page.wait_for_load_state("networkidle")
        print(f"Logged in. URL: {page.url}")

        await page.goto(f"{BASE}/dashboard", wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
        await page.screenshot(path=r"d:\Final Version\scripts\screenshots\dashboard_user.png", full_page=False)

        # Collect all CSS files loaded
        css_links = await page.evaluate("""() =>
            [...document.querySelectorAll('link[rel=stylesheet]')].map(l => l.href)
        """)
        print("\\nCSS files loaded:")
        for c in css_links:
            print(f"  {c}")

        blue_elements = await page.evaluate("""() => {
            const found = [];
            const blueRgbs = [
                'rgb(37, 99, 235)', 'rgb(13, 110, 253)',
                'rgb(59, 130, 246)', 'rgb(29, 78, 216)', 'rgb(30, 64, 175)',
                'rgb(0, 123, 255)', 'rgb(23, 162, 184)',
            ];
            document.querySelectorAll('*').forEach(el => {
                const rect = el.getBoundingClientRect();
                if (rect.width === 0 || rect.height === 0) return;
                const style = getComputedStyle(el);
                const bg = style.backgroundColor;
                const color = style.color;
                for (const blue of blueRgbs) {
                    if (bg === blue || color === blue) {
                        found.push({
                            tag: el.tagName,
                            classes: el.className?.slice(0, 80),
                            id: el.id,
                            text: el.textContent?.trim()?.slice(0, 50),
                            bg: bg !== 'rgba(0, 0, 0, 0)' ? bg : null,
                            color,
                            which: blue
                        });
                        break;
                    }
                }
            });
            return found;
        }""")
        print(f"\\nBlue elements on /dashboard: {len(blue_elements)}")
        for b in blue_elements:
            print(f"  {b}")

        # Also check what template is serving this page
        page_html_snippet = await page.evaluate("() => document.querySelector('body')?.className")
        print(f"\\nBody classes: {page_html_snippet}")

        await browser.close()

asyncio.run(main())
