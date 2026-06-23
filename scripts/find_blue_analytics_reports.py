"""Find the blue element on analytics/reports page."""
import asyncio, sys
sys.stdout.reconfigure(encoding="utf-8")
from playwright.async_api import async_playwright

BASE = "http://127.0.0.1:8000"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await ctx.new_page()

        await page.goto(f"{BASE}/login", wait_until="domcontentloaded")
        await page.fill("input[name='username']", "admin")
        await page.fill("input[name='password']", "Admin@1234")
        await page.click("button[type='submit']")
        await page.wait_for_load_state("networkidle")

        await page.goto(f"{BASE}/admin/analytics/reports", wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)

        blue_elements = await page.evaluate("""() => {
            const found = [];
            const blueRgbs = [
                'rgb(37, 99, 235)', 'rgb(13, 110, 253)',
                'rgb(59, 130, 246)', 'rgb(29, 78, 216)', 'rgb(30, 64, 175)',
                'rgb(0, 123, 255)',
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
                            classes: el.className,
                            id: el.id,
                            text: el.textContent?.trim()?.slice(0, 50),
                            bg,
                            color,
                            which: blue
                        });
                        break;
                    }
                }
            });
            return found;
        }""")
        print(f"Blue elements on analytics/reports: {len(blue_elements)}")
        for b in blue_elements:
            print(f"  {b}")

        await browser.close()

asyncio.run(main())
