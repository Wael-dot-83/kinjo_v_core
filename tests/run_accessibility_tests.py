"""
KinJo Accessibility Testing Script
Run automated accessibility tests using axe-core via Selenium

Requirements:
    pip install selenium axe-selenium-python webdriver-manager

Usage:
    python tests/run_accessibility_tests.py
"""

import json
import sys
from datetime import datetime

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from webdriver_manager.chrome import ChromeDriverManager
    from axe_selenium_python import Axe
except ImportError as e:
    print("Missing dependencies. Install with:")
    print("  pip install selenium axe-selenium-python webdriver-manager")
    sys.exit(1)

BASE_URL = "http://127.0.0.1:8000"

# Pages to test
PAGES = [
    {"path": "/", "name": "Home/Login"},
    {"path": "/dashboard", "name": "Dashboard", "requires_auth": True},
    {"path": "/admin/kindergartens", "name": "Kindergartens Admin", "requires_auth": True},
    {"path": "/admin/users", "name": "Users Admin", "requires_auth": True},
    {"path": "/enrollments", "name": "Enrollments", "requires_auth": True},
]


def setup_driver():
    """Setup Chrome WebDriver with accessibility testing options"""
    options = Options()
    options.add_argument("--headless")  # Run without GUI
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    return driver


def login(driver, username="admin", password="admin123"):
    """Login to get authenticated session"""
    driver.get(f"{BASE_URL}/")

    try:
        # Wait for login form
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.NAME, "username"))
        )

        driver.find_element(By.NAME, "username").send_keys(username)
        driver.find_element(By.NAME, "password").send_keys(password)
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()

        # Wait for redirect to dashboard
        WebDriverWait(driver, 10).until(
            EC.url_contains("/dashboard")
        )
        print(f"  Logged in as {username}")
        return True
    except (RuntimeError, ValueError, TypeError, AttributeError, OSError) as e:
        print(f"  Login failed: {e}")
        return False


def run_axe_test(driver, page_name):
    """Run axe-core accessibility test on current page"""
    axe = Axe(driver)
    axe.inject()
    results = axe.run()

    violations = results.get("violations", [])
    passes = results.get("passes", [])

    return {
        "page": page_name,
        "url": driver.current_url,
        "violations": violations,
        "passes": len(passes),
        "violation_count": len(violations),
        "critical": len([v for v in violations if v.get("impact") == "critical"]),
        "serious": len([v for v in violations if v.get("impact") == "serious"]),
        "moderate": len([v for v in violations if v.get("impact") == "moderate"]),
        "minor": len([v for v in violations if v.get("impact") == "minor"]),
    }


def print_violation(violation):
    """Print a single violation in readable format"""
    impact = violation.get("impact", "unknown")
    impact_colors = {
        "critical": "\033[91m",  # Red
        "serious": "\033[93m",   # Yellow
        "moderate": "\033[94m",  # Blue
        "minor": "\033[90m",     # Gray
    }
    reset = "\033[0m"
    color = impact_colors.get(impact, "")

    print(f"  {color}[{impact.upper()}]{reset} {violation.get('description')}")
    print(f"    Rule: {violation.get('id')} - {violation.get('help')}")
    print(f"    Help: {violation.get('helpUrl')}")

    nodes = violation.get("nodes", [])[:3]  # Show first 3 affected elements
    for node in nodes:
        target = node.get("target", ["unknown"])[0]
        print(f"    Element: {target}")
    if len(violation.get("nodes", [])) > 3:
        print(f"    ... and {len(violation.get('nodes', [])) - 3} more elements")
    print()


def main():
    print("=" * 60)
    print("KinJo Accessibility Audit")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    print()

    driver = setup_driver()
    all_results = []
    logged_in = False

    try:
        for page in PAGES:
            print(f"Testing: {page['name']} ({page['path']})")

            # Login if needed
            if page.get("requires_auth") and not logged_in:
                print("  Authenticating...")
                logged_in = login(driver)
                if not logged_in:
                    print("  Skipping authenticated pages due to login failure")
                    continue

            # Navigate to page
            if page.get("requires_auth"):
                driver.get(f"{BASE_URL}{page['path']}")
            else:
                driver.get(f"{BASE_URL}{page['path']}")

            # Wait for page to load
            try:
                WebDriverWait(driver, 10).until(
                    lambda d: d.execute_script("return document.readyState") == "complete"
                )
            except:
                pass

            # Run accessibility test
            result = run_axe_test(driver, page["name"])
            all_results.append(result)

            print(f"  Passes: {result['passes']}, Violations: {result['violation_count']}")
            print(f"  Critical: {result['critical']}, Serious: {result['serious']}, Moderate: {result['moderate']}, Minor: {result['minor']}")
            print()

    finally:
        driver.quit()

    # Print detailed violations
    print("=" * 60)
    print("DETAILED VIOLATIONS")
    print("=" * 60)

    for result in all_results:
        if result["violations"]:
            print(f"\n{result['page']} ({result['url']})")
            print("-" * 40)
            for violation in result["violations"]:
                print_violation(violation)

    # Summary
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)

    total_violations = sum(r["violation_count"] for r in all_results)
    total_critical = sum(r["critical"] for r in all_results)
    total_serious = sum(r["serious"] for r in all_results)

    print(f"Pages tested: {len(all_results)}")
    print(f"Total violations: {total_violations}")
    print(f"  Critical: {total_critical}")
    print(f"  Serious: {total_serious}")

    # Save results to JSON
    report_path = "tests/accessibility_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "pages_tested": len(all_results),
                "total_violations": total_violations,
                "critical": total_critical,
                "serious": total_serious,
            },
            "results": all_results
        }, f, indent=2, ensure_ascii=False)

    print(f"\nFull report saved to: {report_path}")

    # Exit code based on critical/serious issues
    if total_critical > 0:
        print("\nâŒ FAILED: Critical accessibility issues found")
        return 1
    elif total_serious > 0:
        print("\nâš ï¸  WARNING: Serious accessibility issues found")
        return 0
    else:
        print("\nâœ… PASSED: No critical or serious accessibility issues")
        return 0


if __name__ == "__main__":
    sys.exit(main())

