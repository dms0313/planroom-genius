"""
iSqFt scraper using direct REST API calls.

Auth token approach:
  - iSqFt returns a JWT (JSON Web Token) on login via a JSON response body.
  - The token is cached in isqft_token.json.  On expiry (checked by decoding
    the 'exp' claim without signature verification), Playwright is launched
    *once* to perform a browser login and intercept the token from either:
      (a) A JSON response body with keys 'token', 'accessToken', 'jwt', or
          nested 'data.token'; or
      (b) An Authorization response header.
  - After capture the browser is closed immediately and the token is saved to
    disk for future runs.
"""
import os
import sys
import json
import base64
import asyncio
import traceback
from datetime import datetime

import httpx

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import IsqftConfig, DATE_FORMATS

# Import Google Drive service
try:
    from services.google_drive import (
        upload_and_cleanup, should_use_gdrive, is_authenticated,
        get_status, check_file_exists,
    )
    GDRIVE_AVAILABLE = True
except ImportError:
    GDRIVE_AVAILABLE = False


# ---------------------------------------------------------------------------
# Logging (same interface the scheduler expects)
# ---------------------------------------------------------------------------
_isqft_log_buffer = []


def get_isqft_logs():
    """Get and clear the log buffer."""
    global _isqft_log_buffer
    logs = _isqft_log_buffer.copy()
    _isqft_log_buffer = []
    return logs


def log_status(msg):
    """Log to console and buffer (scheduler collector forwards to web UI)."""
    global _isqft_log_buffer
    print(f"[ISQFT] {msg}", flush=True)
    _isqft_log_buffer.append(f"[ISQFT] {msg}")


# ---------------------------------------------------------------------------
# IsqftAPIClient
# ---------------------------------------------------------------------------
class IsqftAPIClient:
    """Thin HTTP client for iSqFt's REST API."""

    def __init__(self, config: IsqftConfig):
        self.config = config
        self._token: str | None = None
        self._client: httpx.AsyncClient | None = None

    # -- lifecycle -----------------------------------------------------------

    async def open(self):
        self._client = httpx.AsyncClient(timeout=30, follow_redirects=True)

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    # -- auth headers --------------------------------------------------------

    def _headers(self):
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/144.0.0.0 Safari/537.36"
            ),
        }

    # -- token management ----------------------------------------------------

    @staticmethod
    def _decode_exp(token: str) -> int | None:
        """
        Decode the 'exp' claim from a JWT without verifying the signature.
        Returns the expiry Unix timestamp, or None if decoding fails.
        """
        try:
            parts = token.split(".")
            if len(parts) < 2:
                return None
            payload = parts[1]
            # JWT base64url padding
            padding = 4 - len(payload) % 4
            if padding != 4:
                payload += "=" * padding
            decoded = base64.urlsafe_b64decode(payload)
            claims = json.loads(decoded)
            return claims.get("exp")
        except Exception:
            return None

    def _is_token_valid(self, token: str) -> bool:
        """Return True if the token's exp claim is more than 300 seconds away."""
        exp = self._decode_exp(token)
        if exp is None:
            return False
        now = datetime.now().timestamp()
        return exp > now + 300

    def _load_cached_token(self) -> str | None:
        """Load token from disk cache, validate expiry, return or None."""
        if os.path.exists(self.config.TOKEN_FILE):
            try:
                with open(self.config.TOKEN_FILE, "r") as f:
                    data = json.load(f)
                token = data.get("token", "")
                if token and self._is_token_valid(token):
                    log_status("Loaded valid cached auth token from disk")
                    return token
                if token:
                    log_status("Cached auth token has expired or is near expiry")
            except Exception as e:
                log_status(f"Could not read token file: {e}")
        return None

    def _save_token(self, token: str):
        try:
            with open(self.config.TOKEN_FILE, "w") as f:
                json.dump({
                    "token": token,
                    "saved_at": datetime.now().isoformat(),
                }, f, indent=2)
            log_status("Saved auth token to disk")
        except Exception as e:
            log_status(f"Could not save token file: {e}")

    async def _obtain_token_via_browser(self) -> str | None:
        """
        Launch Playwright, log in at the iSqFt login URL, and intercept the
        auth token from JSON response bodies or Authorization response headers.

        Checks JSON body keys: 'token', 'accessToken', 'jwt', 'data.token'.
        Also checks the Authorization response header.
        Waits up to 20 seconds for a token to be captured after login.
        """
        log_status("Obtaining fresh auth token via browser login...")

        if not self.config.LOGIN_EMAIL or not self.config.LOGIN_PASSWORD:
            log_status("Missing ISQFT_LOGIN / ISQFT_PW credentials")
            return None

        captured_token = None

        try:
            from playwright.async_api import async_playwright

            pw = await async_playwright().start()

            chrome_path = self._find_chrome_executable()

            launch_args = [
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--disable-gpu",
                "--mute-audio",
            ]

            # Clean up stale SingletonLock from previous crashes
            lock_file = os.path.join(self.config.CHROME_USER_DATA_DIR, "SingletonLock")
            if os.path.exists(lock_file):
                try:
                    os.remove(lock_file)
                    log_status("Removed stale SingletonLock file")
                except OSError:
                    pass

            ctx = await pw.chromium.launch_persistent_context(
                user_data_dir=self.config.CHROME_USER_DATA_DIR,
                headless=self.config.HEADLESS,
                args=launch_args,
                executable_path=chrome_path,
                viewport={"width": 1280, "height": 720},
                ignore_https_errors=True,
            )

            page = ctx.pages[0] if ctx.pages else await ctx.new_page()

            # Intercept responses to capture token from JSON body or header
            async def _on_response(response):
                nonlocal captured_token
                if captured_token:
                    return
                # Check Authorization response header
                try:
                    auth_header = response.headers.get("authorization", "")
                    if auth_header.lower().startswith("bearer "):
                        candidate = auth_header[7:].strip()
                        if len(candidate) > 20 and self._is_token_valid(candidate):
                            captured_token = candidate
                            log_status("Intercepted token from Authorization response header")
                            return
                except Exception:
                    pass

                # Check JSON response body
                content_type = response.headers.get("content-type", "")
                if "json" not in content_type:
                    return
                try:
                    body = await response.json()
                except Exception:
                    return
                if not isinstance(body, dict):
                    return

                # Try known keys: token, accessToken, jwt
                for key in ("token", "accessToken", "jwt"):
                    candidate = body.get(key)
                    if candidate and isinstance(candidate, str) and len(candidate) > 20:
                        if self._is_token_valid(candidate):
                            captured_token = candidate
                            log_status(f"Intercepted token from response JSON key '{key}'")
                            return

                # Try nested data.token
                data_obj = body.get("data")
                if isinstance(data_obj, dict):
                    candidate = data_obj.get("token")
                    if candidate and isinstance(candidate, str) and len(candidate) > 20:
                        if self._is_token_valid(candidate):
                            captured_token = candidate
                            log_status("Intercepted token from response JSON key 'data.token'")
                            return

            page.on("response", _on_response)

            # Navigate to login page
            await page.goto(self.config.LOGIN_URL, wait_until="domcontentloaded", timeout=90000)
            await asyncio.sleep(2)

            # If already authenticated, a redirect may trigger API calls immediately
            if not captured_token:
                await asyncio.sleep(3)

            # Perform login if token not yet captured
            if not captured_token:
                log_status("Performing login...")
                try:
                    email_selector = 'input[type="email"], input[name="email"], input[id="email"], input[name="username"]'
                    pw_selector = 'input[type="password"], input[name="password"], input[id="password"]'
                    submit_selector = 'button[type="submit"], button:has-text("Sign In"), button:has-text("Log In"), button:has-text("Login")'

                    await page.wait_for_selector(email_selector, timeout=10000)
                    await page.fill(email_selector, self.config.LOGIN_EMAIL)
                    await page.fill(pw_selector, self.config.LOGIN_PASSWORD)
                    await page.click(submit_selector)
                    log_status("Submitted login form, waiting for token capture...")

                    # Wait up to 20 seconds for the token to be captured
                    for _ in range(20):
                        if captured_token:
                            break
                        await asyncio.sleep(1)
                except Exception as e:
                    log_status(f"Login form interaction failed: {e}")

            # Close browser
            try:
                await ctx.close()
            except Exception:
                pass
            try:
                await pw.stop()
            except Exception:
                pass

            if captured_token:
                log_status("Successfully obtained auth token")
            else:
                log_status("Failed to capture auth token from browser")

            return captured_token

        except Exception as e:
            log_status(f"Browser token capture failed: {e}")
            traceback.print_exc()
            return None

    def _find_chrome_executable(self):
        """Find Chrome executable on the system."""
        import platform
        system = platform.system()
        possible_paths = []

        if system == "Windows":
            possible_paths = [
                r"C:\Users\dms03\Development\planroom-genius\backend\chrome-win\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
            ]
        elif system == "Darwin":
            possible_paths = [
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            ]
        elif system == "Linux":
            possible_paths = [
                "/usr/bin/chromium-browser",
                "/usr/bin/chromium",
                "/usr/bin/google-chrome",
                "/usr/bin/google-chrome-stable",
            ]

        for path in possible_paths:
            if os.path.exists(path):
                return path
        return None

    async def ensure_auth(self) -> bool:
        """
        Make sure we have a valid auth token.
        Tries cached token first (JWT exp check), then falls back to browser login.
        """
        # Try cached token
        token = self._load_cached_token()
        if token:
            self._token = token
            return True

        # Obtain via browser
        token = await self._obtain_token_via_browser()
        if token:
            self._token = token
            self._save_token(token)
            return True

        log_status("Could not obtain valid auth token")
        return False

    # -- HTTP helpers --------------------------------------------------------

    async def _request(self, method, url, **kwargs):
        """
        Make an HTTP request with retry logic and automatic token refresh.
        Retries up to 3 times with exponential backoff.
        Re-authenticates on 401.
        Respects Retry-After header on 429.
        """
        for attempt in range(3):
            try:
                r = await self._client.request(
                    method, url, headers=self._headers(), **kwargs
                )

                # Token expired mid-run
                if r.status_code == 401 and attempt < 2:
                    log_status("Got 401 — refreshing auth token...")
                    token = await self._obtain_token_via_browser()
                    if token:
                        self._token = token
                        self._save_token(token)
                        continue
                    return None

                # Rate limited
                if r.status_code == 429:
                    retry_after = int(r.headers.get("Retry-After", 5))
                    log_status(f"Rate limited, waiting {retry_after}s...")
                    await asyncio.sleep(retry_after)
                    continue

                if r.status_code >= 400:
                    body_preview = r.text[:200] if r.text else "(empty)"
                    log_status(f"HTTP {r.status_code} for {method} {url}: {body_preview}")
                    if attempt < 2:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    return None

                return r.json()

            except httpx.TimeoutException:
                log_status(f"Timeout on {method} {url} (attempt {attempt + 1})")
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
            except Exception as e:
                log_status(f"Request error: {e}")
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)

        return None

    async def download_file(self, url: str, dest_dir: str, filename: str | None = None) -> str | None:
        """
        Stream-download a file from *url* into *dest_dir*.

        If *filename* is provided it is used as-is.  Otherwise the filename is
        derived from the Content-Disposition header, then from the URL path.

        Skips (returns None) if the downloaded content is fewer than 100 bytes,
        indicating an error page or empty response rather than a real file.

        Returns the local file path on success, None on failure.
        """
        os.makedirs(dest_dir, exist_ok=True)

        # Derive fallback filename from URL
        url_filename = url.split("/")[-1].split("?")[0] or "download"
        dest_filename = filename or url_filename

        try:
            async with self._client.stream(
                "GET", url, headers=self._headers(), follow_redirects=True
            ) as r:
                if r.status_code >= 400:
                    log_status(f"Download failed HTTP {r.status_code}: {url}")
                    return None

                # Content-Disposition overrides everything if no explicit filename given
                if not filename:
                    cd = r.headers.get("content-disposition", "")
                    if "filename=" in cd:
                        dest_filename = cd.split("filename=")[-1].strip('"; ')

                dest = os.path.join(dest_dir, dest_filename)
                data = b""
                async for chunk in r.aiter_bytes(8192):
                    data += chunk

                if len(data) < 100:
                    log_status(f"Skipped tiny response ({len(data)} bytes) for: {dest_filename}")
                    return None

                with open(dest, "wb") as f:
                    f.write(data)

                log_status(f"Downloaded: {dest_filename} ({len(data):,} bytes)")
                return dest

        except Exception as e:
            log_status(f"Download failed: {e}")
            return None
