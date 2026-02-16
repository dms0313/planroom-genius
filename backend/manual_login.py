"""
Manual Login Script
Launches Chromium in HEADED (visible) mode so you can log in manually.
Cookies and sessions are saved to the persistent browser profile.

Usage (on Pi 5 with desktop GUI):
    cd ~/development/planroom-genius
    DISPLAY=:0 backend/venv/bin/python3 backend/manual_login.py

Usage (on Windows):
    backend\\venv\\Scripts\\python.exe backend\\manual_login.py
"""
import asyncio
import os
import sys
import platform

# Ensure we can import from backend/
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import ScraperConfig, BuildingConnectedConfig, PlanHubConfig, IS_PI5
from playwright.async_api import async_playwright


def find_chrome_executable():
    """Find Chrome/Chromium executable on the system."""
    system = platform.system()
    if system == "Windows":
        possible = [
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "chrome-win", "chrome.exe"),
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
        ]
    elif system == "Linux":
        possible = [
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
        ]
    else:
        possible = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]

    for path in possible:
        if os.path.exists(path):
            return path
    return None


async def manual_login():
    # Determine profile directory
    profile_dir = ScraperConfig.CHROME_USER_DATA_DIR
    os.makedirs(profile_dir, exist_ok=True)

    # Find Chrome
    chrome_path = find_chrome_executable()

    # Browser args - minimal for headed mode (need GPU for visible window)
    launch_args = [
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
    ]

    print("=" * 60)
    print("  MANUAL LOGIN SESSION")
    print("=" * 60)
    print()
    print(f"  Profile: {profile_dir}")
    if chrome_path:
        print(f"  Chrome:  {chrome_path}")
    else:
        print("  Chrome:  Playwright bundled")
    print(f"  DISPLAY: {os.environ.get('DISPLAY', 'NOT SET')}")
    print()

    # Check DISPLAY on Linux
    if platform.system() == "Linux" and not os.environ.get("DISPLAY"):
        print("WARNING: DISPLAY is not set. The browser window won't be visible.")
        print("If you're using the Pi desktop, run with:")
        print("    DISPLAY=:0 backend/venv/bin/python3 backend/manual_login.py")
        print()
        response = input("Continue anyway? (y/n): ").strip().lower()
        if response != "y":
            print("Cancelled.")
            return

    async with async_playwright() as pw:
        launch_kwargs = dict(
            user_data_dir=profile_dir,
            headless=False,  # ALWAYS headed for manual login
            args=launch_args,
            viewport={"width": 1280, "height": 720},
            ignore_https_errors=True,
        )
        if chrome_path:
            launch_kwargs["executable_path"] = chrome_path

        ctx = await pw.chromium.launch_persistent_context(**launch_kwargs)

        # Get or create first page
        if ctx.pages:
            page1 = ctx.pages[0]
        else:
            page1 = await ctx.new_page()

        # Open BuildingConnected
        print(f"  Opening BuildingConnected: {BuildingConnectedConfig.PIPELINE_URL}")
        await page1.goto(BuildingConnectedConfig.PIPELINE_URL, wait_until="domcontentloaded")

        # Open PlanHub in a new tab
        page2 = await ctx.new_page()
        print(f"  Opening PlanHub: {PlanHubConfig.LOGIN_URL}")
        await page2.goto(PlanHubConfig.LOGIN_URL, wait_until="domcontentloaded")

        # Open Bidplanroom in a new tab
        page3 = await ctx.new_page()
        bidplanroom_url = "https://www.bidplanroom.com/"
        print(f"  Opening Bidplanroom: {bidplanroom_url}")
        await page3.goto(bidplanroom_url, wait_until="domcontentloaded")

        # Open Loyd Builds Better in a new tab
        page4 = await ctx.new_page()
        lbb_url = "https://www.loydbuildsbetter.com/bids"
        print(f"  Opening Loyd Builds Better: {lbb_url}")
        await page4.goto(lbb_url, wait_until="domcontentloaded")

        print()
        print("-" * 60)
        print("  Browser is OPEN with all 4 planroom sites.")
        print("  Log in to each site manually.")
        print("  Cookies will be saved to the persistent profile.")
        print("-" * 60)
        print()

        input("  Press Enter here when done to close browser and save session...")

        await ctx.close()

    print()
    print("Session saved! Cookies are stored in the browser profile.")
    print("The scrapers will use these saved sessions automatically.")


if __name__ == "__main__":
    asyncio.run(manual_login())
