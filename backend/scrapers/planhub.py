"""
PlanHub scraper using direct REST API calls.

Replaces the Playwright DOM-automation approach with HTTP requests to
PlanHub's internal API (https://api.planhub.com/api/v1/projects/).

Auth token is cached in planhub_token.json.  When it expires, Playwright
is launched *once* to log in and intercept a fresh token, then the browser
is closed immediately.
"""
import os
import sys
import json
import asyncio
import platform
import traceback
from datetime import datetime, date

import httpx

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import PlanHubConfig, DATE_FORMATS

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
_ph_log_buffer = []


def get_ph_logs():
    """Get and clear the log buffer."""
    global _ph_log_buffer
    logs = _ph_log_buffer.copy()
    _ph_log_buffer = []
    return logs


def log_status(msg):
    """Log to both console and web UI."""
    global _ph_log_buffer
    print(f"[PH] {msg}", flush=True)
    _ph_log_buffer.append(f"[PH] {msg}")
    try:
        from services.scheduler import add_to_log
        add_to_log(f"[PH] {msg}")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Debug helper
# ---------------------------------------------------------------------------
PLANHUB_DEBUG = os.getenv("PLANHUB_DEBUG", "").lower() in ("1", "true", "yes")


def _debug_dump(label, data):
    """When PLANHUB_DEBUG is set, write API response to disk."""
    if not PLANHUB_DEBUG:
        return
    debug_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "downloads")
    os.makedirs(debug_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(debug_dir, f"api_debug_{label}_{ts}.json")
    try:
        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=str)
        log_status(f"DEBUG: saved {label} -> {path}")
    except Exception as e:
        log_status(f"DEBUG: could not save {label}: {e}")


# ---------------------------------------------------------------------------
# PlanHubAPIClient
# ---------------------------------------------------------------------------
class PlanHubAPIClient:
    """Thin HTTP client for PlanHub's REST API."""

    def __init__(self, config: PlanHubConfig):
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
            "authorization": f"auth_token {self._token}",
            "accept": "application/json",
            "content-type": "application/json",
            "origin": "https://supplier.planhub.com",
            "referer": "https://supplier.planhub.com/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
        }

    # -- token management ----------------------------------------------------

    def _load_cached_token(self) -> str | None:
        """Load token from disk cache or env var override."""
        # Env var takes precedence
        if self.config.AUTH_TOKEN:
            return self.config.AUTH_TOKEN

        if os.path.exists(self.config.TOKEN_FILE):
            try:
                with open(self.config.TOKEN_FILE, "r") as f:
                    data = json.load(f)
                token = data.get("token", "")
                if token:
                    log_status("Loaded cached auth token from disk")
                    return token
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

    async def _validate_token(self, token: str) -> bool:
        """Lightweight check: fetch user filters to see if token works."""
        try:
            r = await self._client.get(
                f"{self.config.API_BASE_URL}/get-user-filters",
                headers={
                    "authorization": f"auth_token {token}",
                    "accept": "application/json",
                    "content-type": "application/json",
                    "origin": "https://supplier.planhub.com",
                    "referer": "https://supplier.planhub.com/",
                    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
                    "sec-fetch-mode": "cors",
                    "sec-fetch-site": "same-site",
                },
            )
            if r.status_code == 200:
                log_status("Auth token validated OK")
                return True
            log_status(f"Token validation failed: HTTP {r.status_code}")
            return False
        except Exception as e:
            log_status(f"Token validation error: {e}")
            return False

    async def _obtain_token_via_browser(self) -> str | None:
        """
        Launch Playwright, log in at access.planhub.com, intercept the
        auth_token header from any outgoing API request, then close the
        browser immediately.
        """
        log_status("Obtaining fresh auth token via browser login...")

        if not self.config.LOGIN_EMAIL or not self.config.LOGIN_PASSWORD:
            log_status("Missing PLANHUB_LOGIN / PLANHUB_PW credentials")
            return None

        captured_token = None

        try:
            from playwright.async_api import async_playwright

            pw = await async_playwright().start()

            # Find Chrome
            chrome_path = self._find_chrome_executable()

            launch_args = [
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--disable-gpu",
                "--mute-audio",
            ]

            ctx = await pw.chromium.launch_persistent_context(
                user_data_dir=self.config.CHROME_USER_DATA_DIR,
                headless=self.config.HEADLESS,
                args=launch_args,
                executable_path=chrome_path,
                viewport={"width": 1280, "height": 720},
                ignore_https_errors=True,
            )

            page = ctx.pages[0] if ctx.pages else await ctx.new_page()

            # Intercept outgoing requests to capture the auth token
            def _on_request(request):
                nonlocal captured_token
                if captured_token:
                    return
                auth = request.headers.get("authorization", "")
                if auth.startswith("auth_token ") and len(auth) > 20:
                    captured_token = auth.replace("auth_token ", "").strip()
                    log_status("Intercepted auth token from browser request")

            page.on("request", _on_request)

            # Navigate to login
            await page.goto(self.config.LOGIN_URL, wait_until="domcontentloaded", timeout=90000)
            await asyncio.sleep(2)

            # Check if already logged in (cookie session)
            if not captured_token:
                # Try navigating to project list to trigger an API call
                await page.goto(self.config.PROJECT_LIST_URL, wait_until="domcontentloaded", timeout=90000)
                await asyncio.sleep(3)

            # If still no token, perform login
            if not captured_token:
                log_status("Performing login...")
                await page.goto(self.config.LOGIN_URL, wait_until="domcontentloaded", timeout=90000)
                await asyncio.sleep(2)

                try:
                    await page.wait_for_selector(
                        self.config.LOGIN_EMAIL_SELECTOR, timeout=10000
                    )
                    await page.fill(self.config.LOGIN_EMAIL_SELECTOR, self.config.LOGIN_EMAIL)
                    await page.fill(self.config.LOGIN_PASSWORD_SELECTOR, self.config.LOGIN_PASSWORD)
                    await page.click(self.config.LOGIN_SUBMIT_SELECTOR)
                    log_status("Submitted login form, waiting for redirect...")

                    # Wait for redirect after login
                    await asyncio.sleep(5)

                    # Navigate to project list to trigger API call
                    if not captured_token:
                        await page.goto(
                            self.config.PROJECT_LIST_URL,
                            wait_until="domcontentloaded",
                            timeout=90000,
                        )
                        await asyncio.sleep(5)
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
        Tries cached token first, then falls back to browser login.
        """
        # Try cached / env token
        token = self._load_cached_token()
        if token and await self._validate_token(token):
            self._token = token
            return True

        # Obtain via browser
        token = await self._obtain_token_via_browser()
        if token and await self._validate_token(token):
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

    # -- API methods ---------------------------------------------------------

    async def get_filtered_projects(self, page_num=0, limit=10):
        """POST /get-filtered-projects-multiple-keywords"""
        body = {
            "filters": {
                "assigned_team_members": [],
                "bid_due_date_range": None,
                "construction_types": [],
                "date_range": None,
                "delete": False,
                "filter_name": "Daniel's Filter",
                "filter_state": 0,
                "gc_company_ids": [],
                "id": self.config.FILTER_ID,
                "itb_type": None,
                "keywords": None,
                "location": {
                    "distance": self.config.LOCATION_RADIUS,
                    "zipcode": self.config.LOCATION_ZIP,
                },
                "project_name": None,
                "project_status": None,
                "project_types": [],
                "sectors": [],
                "regions": [],
                "states": [],
                "sub_construction_types": [],
                "sub_trades": self.config.SUB_TRADES,
                "zones": [],
                "counties": [],
            },
            "status": "active",
            "page": page_num,
            "limit": limit,
            "order_by": "bid_due_date",
            "direction": "desc",
            "project_search": None,
            "project_file_search": None,
            "project_location_search": None,
            "leads_states": None,
            "leads_status": None,
            "show_hidden": None,
        }
        url = f"{self.config.API_BASE_URL}/get-filtered-projects-multiple-keywords"
        data = await self._request("POST", url, json=body)
        _debug_dump(f"projects_page{page_num}", data)
        return data

    async def get_project_details(self, project_id):
        """GET /{id}/get-details"""
        url = f"{self.config.API_BASE_URL}/{project_id}/get-details"
        data = await self._request("GET", url)
        _debug_dump(f"details_{project_id}", data)
        return data

    async def get_project_gc(self, project_id):
        """GET /{id}/get-gc"""
        url = f"{self.config.API_BASE_URL}/{project_id}/get-gc"
        data = await self._request("GET", url)
        _debug_dump(f"gc_{project_id}", data)
        return data

    async def get_project_files(self, project_id):
        """GET /{id}/get-files"""
        url = f"{self.config.API_BASE_URL}/{project_id}/get-files"
        data = await self._request("GET", url)
        _debug_dump(f"files_{project_id}", data)
        return data

    async def download_file(self, url: str, dest_dir: str) -> str | None:
        """
        Stream-download a file from *url* into *dest_dir*.
        Returns the local file path on success, None on failure.
        Tries with auth header first, then without.
        """
        os.makedirs(dest_dir, exist_ok=True)

        # Derive filename from URL or Content-Disposition
        filename = url.split("/")[-1].split("?")[0] or "download"

        for use_auth in (True, False):
            try:
                headers = self._headers() if use_auth else {}
                async with self._client.stream("GET", url, headers=headers, follow_redirects=True) as r:
                    if r.status_code >= 400:
                        if use_auth:
                            continue
                        return None

                    # Try Content-Disposition for filename
                    cd = r.headers.get("content-disposition", "")
                    if "filename=" in cd:
                        filename = cd.split("filename=")[-1].strip('" ')

                    dest = os.path.join(dest_dir, filename)
                    with open(dest, "wb") as f:
                        async for chunk in r.aiter_bytes(8192):
                            f.write(chunk)

                    log_status(f"Downloaded: {filename}")
                    return dest
            except Exception as e:
                if use_auth:
                    continue
                log_status(f"Download failed: {e}")
                return None

        return None


# ---------------------------------------------------------------------------
# PlanHubScraper
# ---------------------------------------------------------------------------
class PlanHubScraper:
    """
    PlanHub scraper using direct API calls.

    Public interface (unchanged from DOM version):
        - PlanHubScraper()
        - await scraper.run(max_projects=None) -> list[dict]
        - scraper.leads  (used on timeout fallback)
    """

    def __init__(self):
        self.config = PlanHubConfig()
        self.leads = []
        self.processed_ids = set()
        self.download_dir = self.config.DOWNLOAD_DIR
        os.makedirs(self.download_dir, exist_ok=True)
        self._api = PlanHubAPIClient(self.config)

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _get(obj, *keys, default="N/A"):
        """Safely extract a value from a dict, trying multiple key names."""
        if not isinstance(obj, dict):
            return default
        for k in keys:
            v = obj.get(k)
            if v is not None and v != "":
                return v
        return default

    def parse_date(self, date_str):
        if not date_str or date_str == "N/A":
            return None
        for fmt in DATE_FORMATS:
            try:
                return datetime.strptime(str(date_str).strip(), fmt).date()
            except ValueError:
                continue
        # Try ISO format
        try:
            return datetime.fromisoformat(str(date_str).replace("Z", "+00:00")).date()
        except Exception:
            pass
        return None

    def _is_past_due(self, date_str):
        parsed = self.parse_date(date_str)
        if parsed and parsed < date.today():
            return True
        return False

    def _check_sprinkler(self, text):
        if not text:
            return False
        text_lower = text.lower()
        return any(kw in text_lower for kw in self.config.SPRINKLER_KEYWORDS)

    # -- file handling -------------------------------------------------------

    async def _handle_files(self, lead, files_data):
        """Download files and optionally upload to Google Drive."""
        if not files_data:
            return

        # files_data could be a list or a dict with a list inside
        file_list = files_data if isinstance(files_data, list) else files_data.get("files", files_data.get("data", []))
        if not isinstance(file_list, list) or not file_list:
            return

        # Pre-check: does file already exist in Google Drive?
        if GDRIVE_AVAILABLE and should_use_gdrive():
            try:
                project_name_clean = "".join(
                    c for c in lead["name"][:60] if c.isalnum() or c in " -_"
                ).strip()
                existing = check_file_exists(f"{project_name_clean}.zip", source="PlanHub")
                if not existing:
                    existing = check_file_exists(f"{project_name_clean}.pdf", source="PlanHub")
                if existing:
                    log_status(f"File already in Google Drive, skipping download")
                    lead["gdrive_file_id"] = existing.get("file_id")
                    lead["gdrive_link"] = existing.get("web_link")
                    lead["gdrive_download_link"] = existing.get("download_link")
                    lead["download_link"] = existing.get("web_link")
                    lead["storage_type"] = "gdrive"
                    return
            except Exception as e:
                log_status(f"GDrive pre-check error: {e}")

        # Pick the best download URL from the file list
        download_url = None
        for f in file_list:
            if isinstance(f, dict):
                download_url = (
                    f.get("download_url")
                    or f.get("downloadUrl")
                    or f.get("download_link")
                    or f.get("url")
                    or f.get("file_url")
                    or f.get("fileUrl")
                )
                if download_url:
                    break

        if not download_url:
            log_status("No downloadable file URL found")
            return

        local_path = await self._api.download_file(download_url, self.download_dir)
        if not local_path:
            return

        new_file = os.path.basename(local_path)

        # Upload to Google Drive if available
        use_gdrive = False
        if GDRIVE_AVAILABLE:
            try:
                use_gdrive = should_use_gdrive()
                if not use_gdrive:
                    gdrive_status = get_status()
                    if gdrive_status.get("configured") and not gdrive_status.get("authenticated"):
                        from services.google_drive import authenticate
                        if authenticate():
                            use_gdrive = True
            except Exception:
                pass

        if use_gdrive:
            try:
                project_name_clean = "".join(
                    c for c in lead["name"][:60] if c.isalnum() or c in " -_"
                ).strip()
                ext = os.path.splitext(new_file)[1] or ".zip"
                gdrive_filename = f"{project_name_clean}{ext}"

                result = upload_and_cleanup(
                    local_path,
                    filename=gdrive_filename,
                    source="PlanHub",
                    delete_local=True,
                )
                if result:
                    lead["gdrive_file_id"] = result.get("file_id")
                    lead["gdrive_link"] = result.get("web_link")
                    lead["gdrive_download_link"] = result.get("download_link")
                    lead["download_link"] = result.get("web_link")
                    lead["storage_type"] = "gdrive"
                    log_status(f"Uploaded to Google Drive: {gdrive_filename}")
                    return
            except Exception as e:
                log_status(f"Google Drive upload failed: {e}")

        # Fall back to local storage
        web_path = f"/downloads/{new_file}"
        lead["local_file_path"] = web_path
        lead["download_link"] = web_path
        lead["storage_type"] = "local"
        log_status(f"Saved locally: {web_path}")

    # -- browser file download ------------------------------------------------

    async def download_project_files(self, leads: list):
        """
        Download project files via Playwright browser for each lead.

        PlanHub's file API returns 404, so we navigate to the project page
        in a real browser and use the download UI.
        """
        if not leads:
            return

        leads_to_download = []
        for lead in leads:
            # Skip if already have files from this run
            if lead.get("download_link") or lead.get("local_file_path") or lead.get("gdrive_link"):
                continue
            # Check Google Drive for existing file
            if GDRIVE_AVAILABLE and should_use_gdrive():
                try:
                    project_name_clean = "".join(
                        c for c in lead.get("name", "")[:60] if c.isalnum() or c in " -_"
                    ).strip()
                    if project_name_clean:
                        existing = check_file_exists(f"{project_name_clean}.zip", source="PlanHub")
                        if not existing:
                            existing = check_file_exists(f"{project_name_clean}.pdf", source="PlanHub")
                        if existing:
                            log_status(f"  File already in Google Drive: {project_name_clean}")
                            lead["gdrive_file_id"] = existing.get("file_id")
                            lead["gdrive_link"] = existing.get("web_link")
                            lead["gdrive_download_link"] = existing.get("download_link")
                            lead["download_link"] = existing.get("web_link")
                            lead["storage_type"] = "gdrive"
                            continue
                except Exception as e:
                    log_status(f"  GDrive pre-check error: {e}")
            leads_to_download.append(lead)
        if not leads_to_download:
            log_status("All leads already have files, skipping browser download")
            return

        log_status(f"Downloading files for {len(leads_to_download)} projects via browser...")

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            log_status("Playwright not installed, skipping file downloads")
            return

        pw = None
        ctx = None
        try:
            pw = await async_playwright().start()
            chrome_path = self._api._find_chrome_executable()

            ctx = await pw.chromium.launch_persistent_context(
                user_data_dir=self.config.CHROME_USER_DATA_DIR,
                headless=self.config.HEADLESS,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-gpu",
                    "--mute-audio",
                ],
                executable_path=chrome_path,
                viewport={"width": 1280, "height": 900},
                ignore_https_errors=True,
                accept_downloads=True,
            )

            page = ctx.pages[0] if ctx.pages else await ctx.new_page()

            for i, lead in enumerate(leads_to_download):
                project_id = lead["id"].replace("planhub_", "")
                project_name = lead.get("name", "Unknown")[:50]
                log_status(f"[{i+1}/{len(leads_to_download)}] Downloading files: {project_name}")

                try:
                    await self._download_single_project_files(page, lead, project_id)
                except Exception as e:
                    log_status(f"  -> File download failed for {project_name}: {e}")

                await asyncio.sleep(1)  # Polite delay between projects

        except Exception as e:
            log_status(f"Browser file download session failed: {e}")
            traceback.print_exc()
        finally:
            if ctx:
                try:
                    await ctx.close()
                except Exception:
                    pass
            if pw:
                try:
                    await pw.stop()
                except Exception:
                    pass

    async def _download_single_project_files(self, page, lead, project_id):
        """Navigate to a single project page and download its files.

        Uses multiple strategies since PlanHub doesn't always trigger a
        standard browser download event:
        1. Intercept file/download URLs from network responses
        2. Try Playwright expect_download (short timeout)
        3. Capture new tabs/popups that may contain the file
        4. Fall back to downloading intercepted URLs directly via httpx
        """
        project_url = f"https://supplier.planhub.com/project/{project_id}"

        # Set up network interception to capture file-related URLs
        captured_file_urls = []
        FILE_CONTENT_TYPES = ("application/pdf", "application/zip", "application/octet-stream",
                              "application/x-zip", "application/x-download")
        # Only intercept responses from relevant domains (PlanHub, cloud storage, CDNs)
        ALLOWED_DOMAINS = ("planhub.com", "amazonaws.com", "blob.core.windows.net",
                           "storage.googleapis.com", "cloudfront.net", "akamaized.net")
        BLOCKED_DOMAINS = ("google-analytics", "googleadservices", "doubleclick",
                           "googlesyndication", "facebook", "hotjar", "sentry",
                           "segment.io", "mixpanel", "amplitude", "intercom")

        async def _on_response(response):
            url = response.url
            try:
                lower_url = url.lower()

                # Skip tracking/ad domains
                if any(bd in lower_url for bd in BLOCKED_DOMAINS):
                    return

                ct = response.headers.get("content-type", "")
                cd = response.headers.get("content-disposition", "")

                # Only check file content-types from relevant domains
                is_relevant = any(ad in lower_url for ad in ALLOWED_DOMAINS)

                if is_relevant and (any(ft in ct for ft in FILE_CONTENT_TYPES) or "attachment" in cd):
                    captured_file_urls.append(url)
                    log_status(f"  -> [NET] File response: {url[:80]} ({ct})")

                # Only check JSON responses from PlanHub API for download URLs
                if response.status == 200 and "json" in ct and "planhub.com" in lower_url:
                    try:
                        body = await response.json()
                        if isinstance(body, dict):
                            for key in ("download_url", "downloadUrl", "file_url",
                                        "signed_url", "signedUrl", "download_link"):
                                val = body.get(key)
                                if val and isinstance(val, str) and val.startswith("http"):
                                    captured_file_urls.append(val)
                                    log_status(f"  -> [NET] Found URL in JSON '{key}': {val[:80]}")
                        elif isinstance(body, list):
                            for item in body[:10]:
                                if isinstance(item, dict):
                                    for key in ("download_url", "downloadUrl", "file_url",
                                                "signed_url", "signedUrl"):
                                        val = item.get(key)
                                        if val and isinstance(val, str) and val.startswith("http"):
                                            captured_file_urls.append(val)
                    except Exception:
                        pass

                # Capture file-extension URLs only from relevant domains
                if is_relevant and any(ext in lower_url for ext in (".pdf", ".zip", ".dwg", ".dwf")):
                    if url not in captured_file_urls:
                        captured_file_urls.append(url)
                        log_status(f"  -> [NET] File URL pattern: {url[:80]}")

            except Exception:
                pass

        page.on("response", _on_response)

        # Also capture new tabs/popups (some sites open files in new tabs)
        new_pages = []

        def _on_popup(popup_page):
            new_pages.append(popup_page)
            log_status(f"  -> [POPUP] New tab opened: {popup_page.url[:80]}")

        page.context.on("page", _on_popup)

        try:
            try:
                await page.goto(project_url, wait_until="domcontentloaded", timeout=30000)
            except Exception as e:
                log_status(f"  -> Navigation failed: {e}")
                return

            await asyncio.sleep(2)

            # Click on Files tab if present
            files_tab_clicked = False
            for selector in [
                self.config.PROJECT_FILES_TAB,
                'button:has-text("Files")',
                'a:has-text("Files")',
                '[role="tab"]:has-text("Files")',
                'mat-button-toggle:has-text("Files")',
                'span:has-text("Files")',
            ]:
                try:
                    el = await page.wait_for_selector(selector, timeout=3000)
                    if el:
                        await el.click()
                        files_tab_clicked = True
                        log_status("  -> Clicked Files tab")
                        await asyncio.sleep(2)
                        break
                except Exception:
                    continue

            if not files_tab_clicked:
                log_status("  -> Could not find Files tab, trying page as-is")

            # Try "Select All" checkbox if present
            for selector in [
                self.config.SELECT_ALL_FILES_CHECKBOX,
                'mat-checkbox:has-text("Select")',
                'input[type="checkbox"][aria-label*="select"]',
                '.mat-checkbox-inner-container',
            ]:
                try:
                    el = await page.wait_for_selector(selector, timeout=2000)
                    if el:
                        await el.click()
                        log_status("  -> Clicked Select All")
                        await asyncio.sleep(1)
                        break
                except Exception:
                    continue

            # --- Two-step PlanHub download flow ---
            # Step A: Click the initial "Download" button to start server-side file prep
            # Step B: Wait for "Download Now" button to appear, then click it
            download_started = False

            # Step A: Click initial Download button
            initial_download_clicked = False
            download_selectors = [
                self.config.DOWNLOAD_FILES_BTN,
                'button:has-text("Download")',
                'planhub-button:has-text("Download")',
                'a:has-text("Download")',
                'button[mattooltip*="Download"]',
                '[aria-label*="download"]',
            ]

            for selector in download_selectors:
                try:
                    el = await page.wait_for_selector(selector, timeout=2000)
                    if el:
                        await el.click()
                        initial_download_clicked = True
                        log_status("  -> Clicked Download (server preparing files...)")
                        break
                except Exception:
                    continue

            if not initial_download_clicked:
                log_status("  -> Could not find initial Download button")

            # Step B: Wait for "Download Now" button and click it
            if initial_download_clicked:
                download_now_selectors = [
                    'button[qa-locator="button-download-now"]',
                    'planhub-button#right-button button',
                    'button:has-text("Download Now")',
                    'planhub-button:has-text("Download Now")',
                    '#right-button button',
                    'button.btn-primary:has-text("Download")',
                ]

                # Server needs time to prepare files — poll for up to 90 seconds
                log_status("  -> Waiting for server to prepare files...")
                download_now_el = None
                for wait_attempt in range(18):  # 18 * 5s = 90s max
                    for selector in download_now_selectors:
                        try:
                            download_now_el = await page.wait_for_selector(
                                selector, timeout=5000
                            )
                            if download_now_el:
                                # Verify it's actually the "Download Now" button
                                text = await download_now_el.inner_text()
                                if "download" in text.lower().strip():
                                    log_status(f"  -> Found 'Download Now' button (after ~{wait_attempt * 5}s)")
                                    break
                                download_now_el = None
                        except Exception:
                            continue
                    if download_now_el:
                        break
                    # Log progress every 15 seconds
                    if wait_attempt > 0 and wait_attempt % 3 == 0:
                        log_status(f"  -> Still waiting for server... ({wait_attempt * 5}s)")

                if download_now_el:
                    # PlanHub typically opens the file in a new tab (S3 URL)
                    # rather than triggering a browser download event.
                    # Strategy: click, then quickly check popups + network captures.

                    # Wait for loading spinner overlay to disappear before clicking.
                    # PlanHub uses a cdk-overlay-backdrop that blocks pointer events.
                    spinner_selectors = [
                        '.loading-spinner-backdrop',
                        '.cdk-overlay-backdrop-showing',
                        '.cdk-overlay-backdrop',
                    ]
                    for ss in spinner_selectors:
                        try:
                            await page.wait_for_selector(
                                ss, state='hidden', timeout=120000
                            )
                            log_status("  -> Loading spinner cleared")
                            break
                        except Exception:
                            continue
                    await asyncio.sleep(1)

                    # Clear any stale popups from earlier
                    new_pages.clear()

                    # Try expect_download with SHORT timeout (PlanHub rarely triggers it)
                    try:
                        async with page.expect_download(timeout=8000) as download_info:
                            try:
                                await download_now_el.click(timeout=10000)
                            except Exception:
                                # Force click if overlay still blocks
                                log_status("  -> Overlay still blocking, force-clicking...")
                                await download_now_el.click(force=True)
                            log_status("  -> Clicked 'Download Now'...")

                        download = await download_info.value
                        dest_path = await self._save_playwright_download(download, lead)
                        if dest_path:
                            download_started = True
                    except Exception:
                        # Expected: PlanHub opens file in a new tab, not a download
                        log_status("  -> No browser download event (checking popups & network)...")

                    # Check for new tabs/popups with S3 or file URLs
                    if not download_started:
                        # Give the popup a moment to open
                        await asyncio.sleep(2)
                        for np in new_pages:
                            try:
                                np_url = np.url
                                log_status(f"  -> Popup tab: {np_url[:100]}")
                                # Accept any S3, storage, or file-extension URLs
                                if any(d in np_url.lower() for d in (
                                    "s3.amazonaws.com", "s3.us-", "blob.core",
                                    "storage.googleapis", "cloudfront",
                                    ".pdf", ".zip", ".dwg",
                                )):
                                    dest_path = await self._download_captured_url(np_url, lead)
                                    if dest_path:
                                        download_started = True
                                await np.close()
                            except Exception:
                                pass
                            if download_started:
                                break

                    # Check captured network URLs
                    if not download_started and captured_file_urls:
                        log_status(f"  -> Trying {len(captured_file_urls)} captured URLs...")
                        for cap_url in captured_file_urls:
                            dest_path = await self._download_captured_url(cap_url, lead)
                            if dest_path:
                                download_started = True
                                break
                else:
                    log_status("  -> 'Download Now' button never appeared (server timeout?)")

            # Fallback: try individual file links on the page
            if not download_started:
                log_status("  -> Trying individual file download links...")
                file_links = await page.query_selector_all(
                    'a[href*=".pdf"], a[href*=".zip"], a[download], '
                    'a[href*="download"], a[href*="file"]'
                )
                for link in file_links[:5]:
                    try:
                        href = await link.get_attribute("href")
                        if href and href.startswith("http"):
                            log_status(f"  -> Found file link: {href[:80]}")
                            dest_path = await self._download_captured_url(href, lead)
                            if dest_path:
                                download_started = True
                                break
                    except Exception:
                        continue

            if not download_started:
                log_status(f"  -> Could not download files for project {project_id}")

        finally:
            # Clean up event listeners
            page.remove_listener("response", _on_response)
            page.context.remove_listener("page", _on_popup)

    async def _save_playwright_download(self, download, lead) -> str | None:
        """Save a Playwright Download object to disk and update the lead."""
        try:
            project_name_clean = "".join(
                c for c in lead["name"][:60] if c.isalnum() or c in " -_"
            ).strip()
            project_dir = os.path.join(self.download_dir, project_name_clean)
            os.makedirs(project_dir, exist_ok=True)

            suggested = download.suggested_filename or "download.pdf"
            dest_path = os.path.join(project_dir, suggested)
            await download.save_as(dest_path)

            file_size = os.path.getsize(dest_path) if os.path.exists(dest_path) else 0
            log_status(f"  -> Downloaded: {suggested} ({file_size:,} bytes)")

            if file_size < 100:
                log_status(f"  -> File too small ({file_size} bytes), likely an error page")
                os.remove(dest_path)
                return None

            lead["local_file_path"] = f"/downloads/{project_name_clean}/{suggested}"
            lead["download_link"] = lead["local_file_path"]
            lead["storage_type"] = "local"

            await self._upload_to_gdrive(lead, dest_path, project_name_clean, suggested)
            return dest_path
        except Exception as e:
            log_status(f"  -> Failed to save download: {e}")
            return None

    async def _download_captured_url(self, url: str, lead) -> str | None:
        """Download a file from a captured URL using httpx and update the lead."""
        try:
            project_name_clean = "".join(
                c for c in lead["name"][:60] if c.isalnum() or c in " -_"
            ).strip()
            project_dir = os.path.join(self.download_dir, project_name_clean)
            os.makedirs(project_dir, exist_ok=True)

            # Derive filename from URL
            filename = url.split("/")[-1].split("?")[0] or "download"
            if not any(filename.lower().endswith(ext) for ext in (".pdf", ".zip", ".dwg", ".dwf", ".doc", ".docx", ".xls", ".xlsx")):
                filename = f"{filename}.pdf"

            log_status(f"  -> Downloading via HTTP: {url[:80]}...")

            # Try with auth first, then without
            dest_path = await self._api.download_file(url, project_dir)
            if not dest_path:
                # Try without auth using a fresh client
                async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
                    async with client.stream("GET", url) as r:
                        if r.status_code >= 400:
                            log_status(f"  -> HTTP {r.status_code} downloading {url[:60]}")
                            return None

                        cd = r.headers.get("content-disposition", "")
                        if "filename=" in cd:
                            filename = cd.split("filename=")[-1].strip('" ')

                        dest_path = os.path.join(project_dir, filename)
                        with open(dest_path, "wb") as f:
                            async for chunk in r.aiter_bytes(8192):
                                f.write(chunk)

            if not dest_path or not os.path.exists(dest_path):
                return None

            file_size = os.path.getsize(dest_path)
            if file_size < 100:
                log_status(f"  -> File too small ({file_size} bytes), likely error")
                os.remove(dest_path)
                return None

            actual_filename = os.path.basename(dest_path)
            log_status(f"  -> Saved: {actual_filename} ({file_size:,} bytes)")

            lead["local_file_path"] = f"/downloads/{project_name_clean}/{actual_filename}"
            lead["download_link"] = lead["local_file_path"]
            lead["storage_type"] = "local"

            await self._upload_to_gdrive(lead, dest_path, project_name_clean, actual_filename)
            return dest_path
        except Exception as e:
            log_status(f"  -> HTTP download failed: {e}")
            return None

    async def _upload_to_gdrive(self, lead, local_path, project_name_clean, filename):
        """Upload a downloaded file to Google Drive if available."""
        if not GDRIVE_AVAILABLE:
            return
        try:
            if not should_use_gdrive():
                return
        except Exception:
            return

        try:
            # Check if already uploaded
            existing = check_file_exists(filename, source="PlanHub")
            if existing:
                lead["gdrive_file_id"] = existing.get("file_id")
                lead["gdrive_link"] = existing.get("web_link")
                lead["download_link"] = existing.get("web_link")
                lead["storage_type"] = "gdrive"
                log_status(f"  -> Already in Google Drive")
                return

            ext = os.path.splitext(filename)[1] or ".zip"
            gdrive_filename = f"{project_name_clean}{ext}"

            result = upload_and_cleanup(
                local_path,
                filename=gdrive_filename,
                source="PlanHub",
                delete_local=True,
            )
            if result:
                lead["gdrive_file_id"] = result.get("file_id")
                lead["gdrive_link"] = result.get("web_link")
                lead["gdrive_download_link"] = result.get("download_link")
                lead["download_link"] = result.get("web_link")
                lead["storage_type"] = "gdrive"
                log_status(f"  -> Uploaded to Google Drive: {gdrive_filename}")
        except Exception as e:
            log_status(f"  -> Google Drive upload failed: {e}")

    # -- main scraping -------------------------------------------------------

    async def scrape_all_projects(self, max_projects=None):
        """Fetch projects from PlanHub API and enrich each one."""
        log_status("=" * 40)
        log_status("Starting PlanHub API scrape")

        if max_projects is None:
            max_projects = self.config.MAX_PROJECTS_DEFAULT

        # 1. Auth
        if not await self._api.ensure_auth():
            log_status("Failed to authenticate with PlanHub API")
            return []

        # 2. Paginate project list
        log_status("Fetching project list...")
        all_projects = []
        page_num = 0
        page_size = 25

        while True:
            data = await self._api.get_filtered_projects(page_num, page_size)
            if not data:
                log_status(f"No data returned for page {page_num} (response was None/empty)")
                break

            # Debug: log response structure
            if page_num == 0:
                if isinstance(data, dict):
                    log_status(f"API response keys: {list(data.keys())}")
                    result = data.get("result")
                    if isinstance(result, dict):
                        log_status(f"result keys: {list(result.keys())}, total_projects: {result.get('total_projects')}")
                else:
                    log_status(f"API response type: {type(data).__name__}")

            # Response is {"result": {"total_projects": N, "projects": [...]}}
            # Unwrap the "result" envelope if present
            inner = data.get("result", data) if isinstance(data, dict) else data

            projects = None
            if isinstance(inner, dict):
                projects = (
                    inner.get("projects")
                    or inner.get("data")
                    or inner.get("results")
                    or inner.get("items")
                )
            if not projects and isinstance(inner, list):
                projects = inner
            if not projects and isinstance(data, dict):
                # Last resort: find any list in the response
                for v in data.values():
                    if isinstance(v, dict):
                        for vv in v.values():
                            if isinstance(vv, list) and vv:
                                projects = vv
                                break
                    if isinstance(v, list) and v:
                        projects = v
                        break
            if not projects:
                log_status(f"No projects found on page {page_num}")
                break

            all_projects.extend(projects)
            log_status(f"Page {page_num}: got {len(projects)} projects (total: {len(all_projects)})")

            # Check if we have enough
            if max_projects and len(all_projects) >= max_projects:
                all_projects = all_projects[:max_projects]
                break

            # Check if there are more pages
            total = None
            if isinstance(inner, dict):
                total = inner.get("total_projects") or inner.get("total") or inner.get("totalCount")
            if total is None and isinstance(data, dict):
                total = data.get("total") or data.get("totalCount") or data.get("total_count")
            if total is not None and len(all_projects) >= int(total):
                break

            # If we got fewer than requested, we're on the last page
            if len(projects) < page_size:
                break

            page_num += 1
            await asyncio.sleep(0.3)

        log_status(f"Fetched {len(all_projects)} total projects from API")

        if not all_projects:
            return []

        # 3. Process each project from list data
        log_status("Processing projects from API response...")

        for i, proj in enumerate(all_projects):
            project_id = str(
                proj.get("id")
                or proj.get("project_id")
                or proj.get("projectId")
                or proj.get("_id")
                or i
            )
            project_name = (
                proj.get("project_name")
                or proj.get("name")
                or proj.get("title")
                or "Unknown"
            )

            lead_id = f"planhub_{project_id}"
            if lead_id in self.processed_ids:
                log_status(f"Skipping duplicate: {lead_id}")
                continue
            self.processed_ids.add(lead_id)

            # Quick past-due check from list data
            bid_date_str = (
                proj.get("bid_due_date")
                or proj.get("bid_date")
                or proj.get("bidDueDate")
                or ""
            )
            if bid_date_str and self._is_past_due(bid_date_str):
                log_status(f"Skipping past-due: {project_name[:40]}")
                continue

            log_status(f"[{i+1}/{len(all_projects)}] Processing: {project_name[:50]}")

            # --- Extract all data from the project list item directly ---
            # (Per-project enrichment endpoints return 404, but the list has everything)
            name = self._get(proj, "name", "project_name", "title", default=project_name)
            description = self._get(proj, "desc", "description", "scope", "notes", default="")
            city = self._get(proj, "city", "project_city", default="")
            state = self._get(proj, "state", "province", "project_state", default="")
            zip_code = self._get(proj, "zip", "zipcode", default="")
            bid_date = self._get(
                proj, "bid_due_date", "bid_date", "bidDueDate", "due_date",
                default=bid_date_str or "N/A",
            )
            project_value = self._get(proj, "value", "project_value", "estimated_value", default="")
            project_url = self._get(proj, "url", "project_url", default="")
            construction_type = self._get(proj, "construction_types", "construction_type", default="")
            building_use = self._get(proj, "building_use", "project_type", default="")

            location = f"{city}, {state}" if city and state and city != "N/A" and state != "N/A" else (city or state or "N/A")

            # Full address
            parts = [p for p in [city, state, zip_code] if p and p != "N/A"]
            full_address = ", ".join(parts) if parts else location

            # Sprinkler check
            sprinklered = self._check_sprinkler(description) or self._check_sprinkler(name)

            # GC info — extract from general_contractors array in the list item
            gc_company = "N/A"
            contact_name = "N/A"
            contact_phone = ""
            contact_email = ""
            gc_list = proj.get("general_contractors") or []
            if isinstance(gc_list, list) and gc_list:
                gc = gc_list[0]
                gc_company = self._get(gc, "name", "company_name", "company", default="N/A")
                contact_name = self._get(gc, "contact_name", "contact", "full_name", default="N/A")
                contact_phone = self._get(gc, "phone", "contact_phone", default="")
                contact_email = self._get(gc, "email", "contact_email", default="")

            # Build URL
            if not project_url or project_url == "N/A":
                project_url = f"https://supplier.planhub.com/project/{project_id}"

            # Build type string from construction_types + building_use
            type_parts = [p for p in [construction_type, building_use] if p and p != "N/A"]
            project_type = " / ".join(type_parts) if type_parts else ""

            lead = {
                "id": lead_id,
                "name": name,
                "gc": gc_company,
                "company": gc_company,
                "contact_name": contact_name,
                "contact_phone": contact_phone,
                "contact_email": contact_email,
                "bid_date": bid_date,
                "due_date": bid_date,
                "site": "PlanHub",
                "source": "PlanHub",
                "sprinklered": sprinklered,
                "location": location,
                "city": city if city and city != "N/A" else (location.split(",")[0].strip() if "," in location else location),
                "state": state if state and state != "N/A" else (location.split(",")[1].strip() if "," in location else "N/A"),
                "trade": self.config.TRADE_FILTER,
                "description": description if description != "N/A" else "",
                "full_address": full_address,
                "url": project_url,
                "value": project_value if project_value != "N/A" else "",
                "project_type": project_type,
                "extracted_at": datetime.now().isoformat(),
                "files_link": None,
                "download_link": None,
                "local_file_path": None,
            }

            self.leads.append(lead)
            log_status(f"  -> {name[:40]} | {gc_company} | {location} | bid {bid_date}")

        log_status(f"SCRAPING COMPLETE - Total leads: {len(self.leads)}")
        return self.leads

    # -- save results --------------------------------------------------------

    async def save_results(self, output_file=None):
        """Save leads to JSON file (same pattern as DOM version)."""
        output_file = output_file or self.config.DB_FILE

        existing_leads = []
        if os.path.exists(output_file):
            try:
                with open(output_file, "r") as f:
                    existing_leads = json.load(f)
            except Exception:
                existing_leads = []

        existing_ids = {lead.get("id") for lead in existing_leads}
        new_leads = [lead for lead in self.leads if lead.get("id") not in existing_ids]

        all_leads = existing_leads + new_leads

        with open(output_file, "w") as f:
            json.dump(all_leads, f, indent=2)

        log_status(f"Saved {len(new_leads)} new leads to {output_file}")
        log_status(f"Total leads in database: {len(all_leads)}")

    # -- public entry point --------------------------------------------------

    async def run(self, max_projects=None, download_files=False):
        """Run the full scraping workflow.

        Args:
            max_projects: Max number of projects to scrape (None = all).
            download_files: Whether to download project files via browser.
        """
        try:
            await self._api.open()
            await self.scrape_all_projects(max_projects)
            if download_files and self.leads:
                await self.download_project_files(self.leads)
            await self.save_results()
            return self.leads
        except Exception as e:
            log_status(f"Fatal error: {e}")
            traceback.print_exc()
            return self.leads
        finally:
            await self._api.close()


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------
async def main():
    print("\n" + "=" * 60)
    print(" PLANHUB API SCRAPER")
    print("=" * 60 + "\n")

    scraper = PlanHubScraper()
    leads = await scraper.run(max_projects=5)

    print("\n" + "=" * 60)
    print(f" FINAL RESULTS: Found {len(leads)} leads")
    print("=" * 60)

    if leads:
        for i, lead in enumerate(leads, 1):
            print(f"\nLead {i}:")
            print(f"  Name: {lead.get('name', 'N/A')}")
            print(f"  GC: {lead.get('gc', 'N/A')}")
            print(f"  Bid Date: {lead.get('bid_date', 'N/A')}")
            print(f"  Location: {lead.get('location', 'N/A')}")
            print(f"  Sprinklered: {lead.get('sprinklered', False)}")
            print(f"  Files: {lead.get('download_link', 'None')}")
    else:
        print("\n No leads found. Check the debug output above.")
        if not PLANHUB_DEBUG:
            print(" Tip: Run with PLANHUB_DEBUG=1 to save API responses to disk.")

    print("\n" + "=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
