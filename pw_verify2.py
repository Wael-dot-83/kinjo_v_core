import asyncio, sys, json, urllib.request, urllib.parse
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await ctx.new_page()

        data = urllib.parse.urlencode({"username":"admin","password":"Admin@1234","grant_type":"password"}).encode()
        req = urllib.request.Request("http://127.0.0.1:8000/token", data=data, headers={"Content-Type":"application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req) as resp:
            token = json.loads(resp.read())["access_token"]

        await ctx.add_cookies([{"name":"kinjo_token","value":token,"domain":"127.0.0.1","path":"/"}])
        await page.goto("http://127.0.0.1:8000/", wait_until="domcontentloaded")
        await page.evaluate(f'localStorage.setItem("kinjo_token", "{token}")')
        await page.goto("http://127.0.0.1:8000/admin/classification", wait_until="domcontentloaded")
        await page.wait_for_timeout(4000)

        # Check what governorate options are available
        gov_options = await page.locator("#governorateSelect option").all()
        for opt in gov_options:
            val = await opt.get_attribute("value")
            txt = await opt.inner_text()
            sys.stdout.buffer.write(f"GOV_OPT value={repr(val)} text={txt.encode('utf-8','replace')}\n".encode())

        # Select a specific governorate and apply filter
        await page.select_option("#governorateSelect", index=1)  # pick first real governorate
        selected_gov = await page.locator("#governorateSelect").input_value()
        sys.stdout.buffer.write(f"SELECTED_GOV: {selected_gov.encode('utf-8','replace')}\n".encode())

        await page.click("#applyClassificationFiltersBtn")
        await page.wait_for_timeout(3000)

        rows_after = await page.locator("#classificationTableBody tr").count()
        empty_vis = not await page.locator("#classificationEmpty").is_hidden()
        error_vis = not await page.locator("#classificationError").is_hidden()
        sys.stdout.buffer.write(f"ROWS_AFTER_FILTER={rows_after} EMPTY={empty_vis} ERROR={error_vis}\n".encode())

        for i in range(min(rows_after, 3)):
            txt = await page.locator("#classificationTableBody tr").nth(i).inner_text()
            sys.stdout.buffer.write(f"ROW{i}: {txt.encode('utf-8','replace')}\n".encode())

        # Screenshot with governorate filter applied
        await page.screenshot(path="d:/Final Version/screenshot_gov_filter.png", full_page=True)
        sys.stdout.buffer.write(b"SCREENSHOT2_SAVED\n")

        await browser.close()

asyncio.run(run())
