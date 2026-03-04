"""
Manual Login Script
Launches Chromium in HEADED (visible) mode so you can log in manually.
Cookies and sessions are saved to the persistent browser profile.

Usage (on Pi 5 with desktop GUI):
    cd ~/development/planroom-genius
    DISPLAY=:0 backend/venv/bin/python3 backend/manual_login.py
    DISPLAY=:0 backend/venv/bin/python3 backend/manual_login.py --isqft

Usage (on Windows):
    backend\\venv\\Scripts\\python.exe backend\\manual_login.py
    backend\\venv\\Scripts\\python.exe backend\\manual_login.py --isqft
"""
import asyncio
import base64
import json
import os
import sys
import platform
from datetime import datetime

# Ensure we can import from backend/
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import ScraperConfig, BuildingConnectedConfig, PlanHubConfig, IsqftConfig, IS_PI5
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

        # Clean up stale SingletonLock from previous crashes
        lock_file = os.path.join(profile_dir, "SingletonLock")
        if os.path.exists(lock_file):
            try:
                os.remove(lock_file)
                print(f"  Removed stale SingletonLock: {lock_file}")
            except OSError:
                pass

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
        print("  NOTE: Google Drive uses OAuth, not browser cookies.")
        print("  To connect Google Drive, use the dashboard or run:")
        print("    curl -X POST http://localhost:8000/gdrive/connect")
        print()

        input("  Press Enter here when done to close browser and save session...")

        await ctx.close()

    print()
    print("Session saved! Cookies are stored in the browser profile.")
    print("The scrapers will use these saved sessions automatically.")


async def manual_login_isqft():
    """
    Open iSqFt login page in a headed browser, intercept the JWT auth token
    from network responses after you log in, and save it to isqft_token.json.
    """
    cfg = IsqftConfig()
    profile_dir = cfg.CHROME_USER_DATA_DIR
    os.makedirs(profile_dir, exist_ok=True)

    chrome_path = find_chrome_executable()

    launch_args = [
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--disable-blink-features=AutomationControlled",
    ]

    print("=" * 60)
    print("  ISQFT MANUAL LOGIN — TOKEN CAPTURE")
    print("=" * 60)
    print()
    print(f"  Profile:    {profile_dir}")
    print(f"  Token file: {cfg.TOKEN_FILE}")
    print(f"  Login URL:  {cfg.LOGIN_URL}")
    if chrome_path:
        print(f"  Chrome:     {chrome_path}")
    else:
        print("  Chrome:     Playwright bundled")
    print()

    if platform.system() == "Linux" and not os.environ.get("DISPLAY"):
        print("WARNING: DISPLAY is not set.")
        print("Run with:  DISPLAY=:0 backend/venv/bin/python3 backend/manual_login.py --isqft")
        response = input("Continue anyway? (y/n): ").strip().lower()
        if response != "y":
            print("Cancelled.")
            return

    # Remove stale lock
    lock_file = os.path.join(profile_dir, "SingletonLock")
    if os.path.exists(lock_file):
        try:
            os.remove(lock_file)
        except OSError:
            pass

    captured_token = None

    def _decode_exp(token: str):
        try:
            parts = token.split(".")
            if len(parts) < 2:
                return None
            payload = parts[1]
            padding = 4 - len(payload) % 4
            if padding != 4:
                payload += "=" * padding
            claims = json.loads(base64.urlsafe_b64decode(payload))
            return claims.get("exp")
        except Exception:
            return None

    def _is_valid(token: str) -> bool:
        exp = _decode_exp(token)
        if exp is None:
            return False
        return exp > datetime.now().timestamp() + 300

    async with async_playwright() as pw:
        launch_kwargs = dict(
            user_data_dir=profile_dir,
            headless=False,
            args=launch_args,
            viewport={"width": 1280, "height": 720},
            ignore_https_errors=True,
        )
        if chrome_path:
            launch_kwargs["executable_path"] = chrome_path

        ctx = await pw.chromium.launch_persistent_context(**launch_kwargs)
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        async def on_response(response):
            nonlocal captured_token
            if captured_token:
                return

            # Check Authorization response header
            try:
                auth_header = response.headers.get("authorization", "")
                if auth_header.lower().startswith("bearer "):
                    candidate = auth_header[7:].strip()
                    if len(candidate) > 20 and _is_valid(candidate):
                        captured_token = candidate
                        print(f"\n  [+] Token captured from Authorization header!")
                        return
            except Exception:
                pass

            # Check JSON response body
            if "json" not in response.headers.get("content-type", ""):
                return
            try:
                body = await response.json()
            except Exception:
                return
            if not isinstance(body, dict):
                return

            for key in ("token", "accessToken", "jwt"):
                candidate = body.get(key)
                if candidate and isinstance(candidate, str) and len(candidate) > 20:
                    if _is_valid(candidate):
                        captured_token = candidate
                        print(f"\n  [+] Token captured from JSON key '{key}'!")
                        return

            data_obj = body.get("data")
            if isinstance(data_obj, dict):
                candidate = data_obj.get("token")
                if candidate and isinstance(candidate, str) and len(candidate) > 20:
                    if _is_valid(candidate):
                        captured_token = candidate
                        print(f"\n  [+] Token captured from JSON key 'data.token'!")
                        return

        page.on("response", on_response)

        print("  Opening iSqFt login page...")
        await page.goto(cfg.LOGIN_URL, wait_until="domcontentloaded", timeout=60000)

        print()
        print("-" * 60)
        print("  Log in to iSqFt in the browser window.")
        print("  The token will be captured automatically once you sign in.")
        print("  Then press Enter here to save and close.")
        print("-" * 60)
        print()

        input("  Press Enter after you have logged in successfully...")

        await ctx.close()

    if captured_token:
        try:
            with open(cfg.TOKEN_FILE, "w") as f:
                json.dump({
                    "token": captured_token,
                    "saved_at": datetime.now().isoformat(),
                }, f, indent=2)
            exp = _decode_exp(captured_token)
            exp_str = datetime.fromtimestamp(exp).isoformat() if exp else "unknown"
            print()
            print(f"  Token saved to: {cfg.TOKEN_FILE}")
            print(f"  Expires:        {exp_str}")
            print()
            print("  iSqFt scraper will use this token automatically.")
        except Exception as e:
            print(f"  ERROR saving token: {e}")
    else:
        print()
        print("  WARNING: No token was captured.")
        print("  Make sure you completed the login in the browser before pressing Enter.")


if __name__ == "__main__":
    if "--isqft" in sys.argv:
        asyncio.run(manual_login_isqft())
    else:
        asyncio.run(manual_login())
