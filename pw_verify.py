import asyncio, sys, json, urllib.request, urllib.parse
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await ctx.new_page()

        errors = []
        page.on("console", lambda msg: errors.append(f"[{msg.type}] {msg.text}") if msg.type in ("error","warning") else None)

        # Get JWT token via API
        data = urllib.parse.urlencode({"username":"admin","password":"Admin@1234","grant_type":"password"}).encode()
        req = urllib.request.Request("http://127.0.0.1:8000/token", data=data, headers={"Content-Type":"application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req) as resp:
            token_data = json.loads(resp.read())
        token = token_data["access_token"]

        # Set kinjo_token cookie directly (that's what the server reads for page auth)
        await ctx.add_cookies([{
            "name": "kinjo_token",
            "value": token,
            "domain": "127.0.0.1",
            "path": "/"
        }])
        # Also set in localStorage for API calls
        await page.goto("http://127.0.0.1:8000/", wait_until="domcontentloaded")
        await page.evaluate(f'localStorage.setItem("kinjo_token", "{token}")')

        # Navigate to classification page
        await page.goto("http://127.0.0.1:8000/admin/classification", wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)
        
        url = page.url
        sys.stdout.buffer.write(f"URL: {url}\n".encode())

        await page.screenshot(path="d:/Final Version/screenshot_classification.png", full_page=True)
        sys.stdout.buffer.write(b"SCREENSHOT_SAVED\n")

        gov_count = await page.locator("#governorateSelect option").count()
        level_count = await page.locator("#levelSelect option").count()
        row_count = await page.locator("#classificationTableBody tr").count()
        loading_vis = not await page.locator("#classificationLoading").is_hidden()
        error_vis = not await page.locator("#classificationError").is_hidden()
        empty_vis = not await page.locator("#classificationEmpty").is_hidden()

        sys.stdout.buffer.write(f"GOV_OPTS={gov_count} LEVEL_OPTS={level_count} ROWS={row_count}\n".encode())
        sys.stdout.buffer.write(f"LOADING={loading_vis} ERROR={error_vis} EMPTY={empty_vis}\n".encode())

        if error_vis:
            err = await page.locator("#classificationError").inner_text()
            sys.stdout.buffer.write(b"ERROR_TEXT: " + err.encode("utf-8","replace") + b"\n")

        # Get all table row text
        for i in range(min(row_count, 5)):
            txt = await page.locator("#classificationTableBody tr").nth(i).inner_text()
            sys.stdout.buffer.write(f"ROW{i}: ".encode() + txt.encode("utf-8","replace") + b"\n")

        sys.stdout.buffer.write(f"CONSOLE_ERR_COUNT={len([e for e in errors if 'error' in e.lower()])}\n".encode())
        for e in errors[:8]:
            sys.stdout.buffer.write(b"  ERR: " + e.encode("utf-8","replace") + b"\n")

        await browser.close()

asyncio.run(run())
