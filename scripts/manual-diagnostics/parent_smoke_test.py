import asyncio
from datetime import datetime, timedelta, timezone

import jwt
from playwright.async_api import async_playwright

SECRET_KEY = "ci-secret-key"

def create_token(username: str, role: str):
    expire = datetime.now(timezone.utc) + timedelta(minutes=60)
    to_encode = {"sub": username, "role": role, "exp": expire}
    return jwt.encode(to_encode, SECRET_KEY, algorithm="HS256")

async def run_tests():
    from database import SessionLocal
    from models import ParentProfile, User, UserRole
    db = SessionLocal()
    user = db.query(User).filter(User.role == UserRole.PARENT).first()
    if not user:
        user = User(username='parent_smoke', email='parent_smoke@kinjo.sa', hashed_password='hash', role=UserRole.PARENT)
        db.add(user)
        db.commit()
        db.refresh(user)
        profile = ParentProfile(id=user.id, user_id=user.id, first_name="Test", last_name="Parent")
        db.add(profile)
        db.commit()
        print("Created new parent user for smoke test")
    
    username = user.username
    role = user.role.value if hasattr(user.role, 'value') else user.role
    token = create_token(username, role)
    print(f"Got token for parent {username}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        await context.add_cookies([{
            "name": "kinjo_token",
            "value": token,
            "domain": "127.0.0.1",
            "path": "/"
        }])
        
        page = await context.new_page()
        
        errors = []
        page.on("pageerror", lambda err: errors.append(f"JS Error on {page.url}: {err}"))
        page.on("console", lambda msg: errors.append(f"Console {msg.type} on {page.url}: {msg.text}") if msg.type == 'error' else None)
        
        urls_to_test = [
            "/dashboard",
            "/parent/dashboard",
            "/parent/profile",
            "/parent/children",
            "/parent/enrollments",
            "/parent/attendance",
            "/my-reports",
            "/absence-requests",
            "/messages",
            "/notifications",
            "/enroll",
            "/enrollments/create"
        ]
        
        results = []
        
        for u in urls_to_test:
            url = f"http://127.0.0.1:8068{u}"
            try:
                resp = await page.goto(url, wait_until="networkidle", timeout=15000)
                status = resp.status if resp else "Unknown"
                
                # Check for window.api
                has_api = await page.evaluate("typeof window.api !== 'undefined'")
                
                results.append({
                    "url": u,
                    "status": status,
                    "has_api": has_api
                })
            except Exception as e:
                results.append({
                    "url": u,
                    "status": "Error",
                    "error": str(e)
                })
                
        await browser.close()
        
        for r in results:
            print(r)
        
        if errors:
            print("Errors encountered:")
            for e in errors:
                print(e)

if __name__ == "__main__":
    asyncio.run(run_tests())
