"""
BuildingConnected scraper using API interception + direct HTTP calls.

Replaces the Playwright DOM-automation approach with a hybrid strategy:
1. Launch Playwright ONCE to navigate to pipeline, intercepting API responses
   and extracting the JWT auth token from the `authorization` cookie.
2. Process the intercepted JSON pipeline data directly (no DOM scraping).
3. Use httpx with the captured JWT for follow-up API calls (details, files).

Auth token is cached in bc_token.json. When it expires, Playwright is
launched again to refresh it.
"""
import os
import sys
import json
import re
import asyncio
import platform
import traceback
from datetime import datetime, date

import httpx

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import ScraperConfig, DATE_FORMATS

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
_log_buffer = []


def get_bc_logs():
    """Get and clear the log buffer."""
    global _log_buffer
    logs = _log_buffer.copy()
    _log_buffer = []
    return logs


def log_status(msg):
    """Log to both console and web UI."""
    global _log_buffer
    print(f"[BC] {msg}", flush=True)
    _log_buffer.append(f"[BC] {msg}")
    try:
        from services.scheduler import add_to_log
        add_to_log(f"[BC] {msg}")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Debug helper
# ---------------------------------------------------------------------------
BC_DEBUG = os.getenv("BC_DEBUG", "").lower() in ("1", "true", "yes")


def _debug_dump(label, data):
    """When BC_DEBUG is set, write API response to disk."""
    if not BC_DEBUG:
        return
    debug_dir = os.path.join(os.path.dirname(__file__), "downloads")
    os.makedirs(debug_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(debug_dir, f"bc_debug_{label}_{ts}.json")
    try:
        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=str)
        log_status(f"DEBUG: saved {label} -> {path}")
    except Exception as e:
        log_status(f"DEBUG: could not save {label}: {e}")


# ---------------------------------------------------------------------------
# BCAPIClient
# ---------------------------------------------------------------------------
class BCAPIClient:
    """
    HTTP client for BuildingConnected API.

    Auth: JWT token extracted from the browser's `authorization` cookie.
    The token is cached to disk and validated before use.
    """

    PIPELINE_URL = "https://app.buildingconnected.com/opportunities/pipeline"
    API_BASE = "https://app.buildingconnected.com/api"

    def __init__(self):
        self._token: str | None = None
        self._client: httpx.AsyncClient | None = None
        self._pipeline_cache: list | None = None
        self.TOKEN_FILE = os.path.join(os.path.dirname(__file__), "bc_token.json")

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
            "accept": "application/json",
            "content-type": "application/json; charset=UTF-8",
            "origin": "https://app.buildingconnected.com",
            "referer": "https://app.buildingconnected.com/opportunities/pipeline",
            "x-requested-with": "XMLHttpRequest",
            "cookie": f"authorization={self._token}",
        }

    # -- token management ----------------------------------------------------

    def _load_cached_token(self) -> str | None:
        """Load JWT token from disk cache."""
        if os.path.exists(self.TOKEN_FILE):
            try:
                with open(self.TOKEN_FILE, "r") as f:
                    data = json.load(f)
                token = data.get("token", "")
                if token:
                    log_status("Loaded cached BC auth token from disk")
                    return token
            except Exception as e:
                log_status(f"Could not read BC token file: {e}")
        return None

    def _save_token(self, token: str):
        try:
            with open(self.TOKEN_FILE, "w") as f:
                json.dump({
                    "token": token,
                    "saved_at": datetime.now().isoformat(),
                }, f, indent=2)
            log_status("Saved BC auth token to disk")
        except Exception as e:
            log_status(f"Could not save BC token file: {e}")

    async def _validate_token(self, token: str) -> bool:
        """Check token validity by making a lightweight API call."""
        try:
            r = await self._client.get(
                f"{self.API_BASE}/me",
                headers={
                    "accept": "application/json",
                    "cookie": f"authorization={token}",
                    "x-requested-with": "XMLHttpRequest",
                },
            )
            if r.status_code == 200:
                log_status("BC auth token validated OK")
                return True
            log_status(f"BC token validation failed: HTTP {r.status_code}")
            return False
        except Exception as e:
            log_status(f"BC token validation error: {e}")
            return False

    async def _obtain_token_and_pipeline_via_browser(self):
        """
        Launch Playwright, navigate to the pipeline page, intercept all API
        responses, and extract:
        1. The JWT auth token from the `authorization` cookie
        2. The pipeline data from intercepted API responses

        Returns (token, pipeline_data) tuple.
        """
        log_status("Launching browser to obtain BC auth and pipeline data...")

        captured_token = None
        captured_responses = {}

        try:
            from playwright.async_api import async_playwright

            pw = await async_playwright().start()

            # Find Chrome
            chrome_path = self._find_chrome_executable()

            playwright_profile = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "playwright_profile",
            )

            # Clean up stale SingletonLock from previous crashes
            lock_file = os.path.join(playwright_profile, "SingletonLock")
            if os.path.exists(lock_file):
                try:
                    os.remove(lock_file)
                    log_status("Removed stale SingletonLock file")
                except OSError:
                    pass

            ctx = await pw.chromium.launch_persistent_context(
                user_data_dir=playwright_profile,
                headless=ScraperConfig.HEADLESS if ScraperConfig else True,
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--mute-audio",
                ],
                executable_path=chrome_path,
                viewport={"width": 1920, "height": 1080},
                ignore_https_errors=True,
                ignore_default_args=["--enable-automation"],
            )

            page = ctx.pages[0] if ctx.pages else await ctx.new_page()

            # Intercept API responses to capture pipeline data and file-related endpoints
            FILE_API_KEYWORDS = ("files", "download", "file-provider", "bid-package", "document")

            async def _on_response(response):
                nonlocal captured_responses
                url = response.url
                if "/api/" not in url:
                    return
                try:
                    path = url.split("/api/")[1].split("?")[0] if "/api/" in url else url

                    if response.status == 200:
                        ct = response.headers.get("content-type", "")
                        if "json" in ct:
                            body = await response.json()
                            captured_responses[path] = body
                            if BC_DEBUG:
                                log_status(f"DEBUG: intercepted /api/{path} ({type(body).__name__})")

                    # Always log file-related endpoints (even non-200) for discovery
                    if any(kw in path.lower() for kw in FILE_API_KEYWORDS):
                        log_status(f"[FILE-API] {response.status} /api/{path}")
                        if response.status == 200:
                            try:
                                body = await response.json()
                                _debug_dump(f"file_api_{path.replace('/', '_')}", body)
                            except Exception:
                                pass
                except Exception:
                    pass

            page.on("response", _on_response)

            # Navigate to pipeline
            log_status("Navigating to BC pipeline...")
            try:
                await page.goto(self.PIPELINE_URL, wait_until="domcontentloaded", timeout=60000)
            except Exception as e:
                log_status(f"Navigation warning: {e}")

            # Check if on login page
            current_url = page.url
            if "login" in current_url or "signin" in current_url:
                log_status("Login page detected - attempting auto-login...")
                await self._attempt_browser_login(page)
                await asyncio.sleep(3)

                # Navigate to pipeline again after login
                if "pipeline" not in page.url:
                    try:
                        await page.goto(self.PIPELINE_URL, wait_until="domcontentloaded", timeout=60000)
                    except Exception:
                        pass

            # Wait for API responses to arrive
            log_status("Waiting for pipeline data to load...")
            await asyncio.sleep(8)

            # Extract JWT token from cookies
            cookies = await ctx.cookies()
            for c in cookies:
                if c["name"] == "authorization" and c["value"].startswith("eyJ"):
                    captured_token = c["value"]
                    log_status("Extracted JWT from authorization cookie")
                    break

            # If no token from cookies, try from page JS
            if not captured_token:
                try:
                    token_from_js = await page.evaluate("""() => {
                        const cookies = document.cookie.split(';');
                        for (const c of cookies) {
                            const [name, ...vals] = c.trim().split('=');
                            if (name === 'authorization') return vals.join('=');
                        }
                        return null;
                    }""")
                    if token_from_js and token_from_js.startswith("eyJ"):
                        captured_token = token_from_js
                        log_status("Extracted JWT from document.cookie")
                except Exception:
                    pass

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
                log_status("Successfully obtained BC auth token")
            else:
                log_status("Failed to capture BC auth token")

            # Find the pipeline data in captured responses
            pipeline_data = self._extract_pipeline_from_responses(captured_responses)

            _debug_dump("intercepted_responses_keys", list(captured_responses.keys()))
            if pipeline_data:
                _debug_dump("pipeline_data", pipeline_data[:3] if isinstance(pipeline_data, list) else pipeline_data)
                log_status(f"Intercepted pipeline data: {len(pipeline_data) if isinstance(pipeline_data, list) else 'dict'}")

            return captured_token, pipeline_data

        except Exception as e:
            log_status(f"Browser session failed: {e}")
            traceback.print_exc()
            return None, None

    async def _attempt_browser_login(self, page):
        """Attempt auto-login on the Autodesk login page."""
        try:
            # Check for email field
            email_input = await page.query_selector('input[id="userName"]')
            if email_input:
                val = await email_input.get_attribute("value")
                if val:
                    log_status(f"Found pre-filled email: {val}")
                    next_btn = await page.query_selector('button[id="verify_user_btn"]')
                    if next_btn:
                        await next_btn.click()
                        await asyncio.sleep(5)

            sign_in_btn = await page.query_selector('button[id="btnSubmit"]')
            if sign_in_btn:
                log_status("Clicking Sign In...")
                await sign_in_btn.click()
                await asyncio.sleep(5)

            if "login" not in page.url and "signin" not in page.url:
                log_status("Auto-login successful")
                return True
        except Exception as e:
            log_status(f"Auto-login failed: {e}")
        return False

    def _extract_pipeline_from_responses(self, responses):
        """
        Find the pipeline/opportunities data among intercepted API responses.
        Looks for responses that contain lists of opportunity objects.
        """
        # Priority: look for known pipeline-related paths
        priority_paths = [
            "opportunities", "pipeline", "opportunity-links",
            "my-opportunities", "opportunities/pipeline",
        ]

        for path_part in priority_paths:
            for path, data in responses.items():
                if path_part in path.lower():
                    if isinstance(data, list) and data:
                        return data
                    if isinstance(data, dict):
                        # Look for list values inside the dict
                        for k, v in data.items():
                            if isinstance(v, list) and v and isinstance(v[0], dict):
                                return v

        # Fallback: find any response that looks like a list of opportunities
        for path, data in responses.items():
            if isinstance(data, list) and len(data) > 2:
                # Check if items look like opportunities (have name/id-like keys)
                if isinstance(data[0], dict):
                    keys = set(data[0].keys())
                    opportunity_keys = {"_id", "id", "name", "projectName", "dueDate", "bidsDueAt", "dateDue"}
                    if keys & opportunity_keys:
                        return data
            if isinstance(data, dict):
                for k, v in data.items():
                    if isinstance(v, list) and len(v) > 2 and isinstance(v[0], dict):
                        inner_keys = set(v[0].keys())
                        opportunity_keys = {"_id", "id", "name", "projectName", "dueDate", "bidsDueAt", "dateDue"}
                        if inner_keys & opportunity_keys:
                            return v

        log_status("Could not identify pipeline data in intercepted responses")
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
        """Make sure we have a valid auth token."""
        # Try cached token
        token = self._load_cached_token()
        if token and await self._validate_token(token):
            self._token = token
            return True

        # Obtain via browser
        token, pipeline_data = await self._obtain_token_and_pipeline_via_browser()
        if token:
            if await self._validate_token(token):
                self._token = token
                self._save_token(token)
                self._pipeline_cache = pipeline_data
                return True
            else:
                # Token didn't validate but we got it - save anyway
                self._token = token
                self._save_token(token)
                self._pipeline_cache = pipeline_data
                return True

        log_status("Could not obtain valid BC auth token")
        return False

    async def get_pipeline_via_browser(self):
        """
        If we already have a cached token but need pipeline data,
        launch browser to get the pipeline data.
        """
        if self._pipeline_cache:
            return self._pipeline_cache

        _, pipeline_data = await self._obtain_token_and_pipeline_via_browser()
        if pipeline_data:
            self._pipeline_cache = pipeline_data
        return pipeline_data

    # -- HTTP helpers --------------------------------------------------------

    async def _request(self, method, url, **kwargs):
        """Make an HTTP request with retry logic."""
        for attempt in range(3):
            try:
                r = await self._client.request(
                    method, url, headers=self._headers(), **kwargs
                )

                if r.status_code == 401 and attempt < 2:
                    log_status("Got 401 - refreshing BC auth token...")
                    token, _ = await self._obtain_token_and_pipeline_via_browser()
                    if token:
                        self._token = token
                        self._save_token(token)
                        continue
                    return None

                if r.status_code == 429:
                    retry_after = int(r.headers.get("Retry-After", 5))
                    log_status(f"Rate limited, waiting {retry_after}s...")
                    await asyncio.sleep(retry_after)
                    continue

                if r.status_code >= 400:
                    log_status(f"HTTP {r.status_code} for {method} {url}")
                    # Don't retry 404 (not found) or 403 (forbidden) — won't change
                    if r.status_code in (404, 403):
                        return None
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

    async def batch_get_opportunity_links(self, ids: list):
        """POST /api/opportunity-links:batch-get"""
        url = f"{self.API_BASE}/opportunity-links:batch-get"
        data = await self._request("POST", url, json=ids)
        _debug_dump("opportunity_links", data)
        return data

    async def get_opportunity_detail(self, opportunity_id: str):
        """GET /api/opportunities/{id}"""
        url = f"{self.API_BASE}/opportunities/{opportunity_id}"
        data = await self._request("GET", url)
        _debug_dump(f"opportunity_{opportunity_id}", data)
        return data

    async def get_opportunity_files(self, opportunity_id: str,
                                    file_providers: dict | None = None,
                                    extra_ids: set | None = None):
        """
        Try multiple API patterns to find downloadable files for an opportunity.

        The actual BC file response format is:
        {"items": [{"_id": "...", "name": "...", "type": "FILE"|"FOLDER",
                     "downloadUrl": "/_/download/file/{fileId}/rfps/{projectId}/..."}]}

        The correct endpoint is /api/opportunities/{opportunityId}/files but
        the opportunityId may differ from the pipeline _id. We try all known IDs.

        Args:
            opportunity_id: The primary BC opportunity/project ID.
            file_providers: Optional fileProviders dict from pipeline data.
            extra_ids: Additional IDs to try (from detail response, pipeline, etc).
        """
        # Collect all IDs that might be used in file API paths
        ids_to_try = set()
        ids_to_try.add(opportunity_id)
        if extra_ids:
            ids_to_try.update(extra_ids)

        if file_providers:
            for provider_key in ("bidPackage", "project", "addenda", "plans", "specs", "documents"):
                prov = file_providers.get(provider_key) or {}
                for id_key in ("rootId", "projectId", "folderId", "_id"):
                    val = prov.get(id_key)
                    if val:
                        ids_to_try.add(val)

        log_status(f"[FILES] Trying {len(ids_to_try)} candidate IDs")

        # The known working endpoint is /opportunities/{id}/files
        # Try this first for each ID, then fall back to other patterns
        endpoints = []
        for pid in ids_to_try:
            endpoints.append(f"/opportunities/{pid}/files")
        for pid in ids_to_try:
            endpoints.extend([
                f"/opportunities/{pid}/bid-packages",
                f"/opportunities/{pid}/documents",
                f"/rfps/{pid}/files",
            ])

        # Deduplicate while preserving order
        seen = set()
        unique_endpoints = []
        for ep in endpoints:
            if ep not in seen:
                seen.add(ep)
                unique_endpoints.append(ep)

        for path in unique_endpoints:
            url = f"{self.API_BASE}{path}"
            log_status(f"[FILES] Trying: {path}")
            data = await self._request("GET", url)
            if data:
                log_status(f"[FILES] Success: {path} -> {type(data).__name__}")
                _debug_dump(f"files_{opportunity_id}", data)
                return data
            else:
                log_status(f"[FILES] No data: {path}")

        log_status(f"[FILES] All endpoints exhausted for {opportunity_id}")
        return None

    def _download_headers(self):
        """Headers for file downloads (not JSON API calls)."""
        return {
            "accept": "*/*",
            "origin": "https://app.buildingconnected.com",
            "referer": "https://app.buildingconnected.com/opportunities/pipeline",
            "cookie": f"authorization={self._token}",
        }

    async def download_file(self, url: str, dest_dir: str) -> str | None:
        """Stream-download a file into dest_dir."""
        os.makedirs(dest_dir, exist_ok=True)

        filename = url.split("/")[-1].split("?")[0] or "download"

        for use_auth in (True, False):
            try:
                headers = self._download_headers() if use_auth else {}
                log_status(f"[DL] {'with' if use_auth else 'without'} auth: {url[:80]}")
                async with self._client.stream("GET", url, headers=headers, follow_redirects=True) as r:
                    if r.status_code >= 400:
                        log_status(f"[DL] HTTP {r.status_code} ({'auth' if use_auth else 'no-auth'})")
                        if use_auth:
                            continue
                        return None

                    cd = r.headers.get("content-disposition", "")
                    if "filename=" in cd:
                        filename = cd.split("filename=")[-1].strip('" ')

                    dest = os.path.join(dest_dir, filename)
                    total = 0
                    with open(dest, "wb") as f:
                        async for chunk in r.aiter_bytes(8192):
                            f.write(chunk)
                            total += len(chunk)

                    if total < 100:
                        log_status(f"[DL] File too small ({total} bytes), likely error page")
                        os.remove(dest)
                        if use_auth:
                            continue
                        return None

                    log_status(f"Downloaded: {filename} ({total:,} bytes)")
                    return dest
            except Exception as e:
                if use_auth:
                    log_status(f"[DL] Auth attempt failed: {e}")
                    continue
                log_status(f"Download failed: {e}")
                return None

        return None


# ---------------------------------------------------------------------------
# BuildingConnectedTableScraper
# ---------------------------------------------------------------------------
class BuildingConnectedTableScraper:
    """
    BuildingConnected scraper using API interception.

    Public interface (unchanged from DOM version):
        - BuildingConnectedTableScraper()
        - await scraper.run(max_projects=None, include_details=True, download_files=True) -> list[dict]
        - scraper.leads  (used on timeout fallback)
    """

    def __init__(self):
        self.leads = []
        self.processed_ids = set()
        self.download_dir = os.path.join(os.path.dirname(__file__), "downloads")
        os.makedirs(self.download_dir, exist_ok=True)
        self._api = BCAPIClient()

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

    @staticmethod
    def _strip_html(text):
        """Strip HTML tags and decode entities from a string."""
        if not text or not isinstance(text, str):
            return text or ""
        # Replace <br>, <br/>, <br /> with newlines
        text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
        # Replace block-level closing tags with newlines
        text = re.sub(r'</(?:div|p|li|tr|h[1-6])>', '\n', text, flags=re.IGNORECASE)
        # Strip all remaining HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        # Decode common HTML entities
        text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
        text = text.replace('&quot;', '"').replace('&#39;', "'").replace('&nbsp;', ' ')
        # Collapse multiple newlines
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

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

    # -- file handling -------------------------------------------------------

    async def _handle_files(self, lead, files_data):
        """Download files and optionally upload to Google Drive.

        Handles the BC file API response format:
        {"items": [{"name": "Plans", "type": "FOLDER", "downloadUrl": "/_/download/file/..."},
                    {"name": "Specs.pdf", "type": "FILE", "downloadUrl": "/_/download/file/..."}]}
        Download URLs may be relative (starting with /_/) and need the BC origin prepended.
        """
        if not files_data:
            return

        # Extract file list — BC returns {"items": [...]}
        file_list = []
        if isinstance(files_data, dict):
            file_list = (
                files_data.get("items")
                or files_data.get("files")
                or files_data.get("data")
                or []
            )
        elif isinstance(files_data, list):
            file_list = files_data

        if not isinstance(file_list, list) or not file_list:
            return

        BC_ORIGIN = "https://app.buildingconnected.com"

        # Pre-check Google Drive
        if GDRIVE_AVAILABLE and should_use_gdrive():
            try:
                project_name_clean = "".join(
                    c for c in lead["name"][:60] if c.isalnum() or c in " -_"
                ).strip()
                existing = check_file_exists(f"{project_name_clean}.zip", source="BuildingConnected")
                if not existing:
                    existing = check_file_exists(f"{project_name_clean}.pdf", source="BuildingConnected")
                if existing:
                    log_status("File already in Google Drive, skipping download")
                    lead["gdrive_file_id"] = existing.get("file_id")
                    lead["gdrive_link"] = existing.get("web_link")
                    lead["download_link"] = existing.get("web_link")
                    lead["storage_type"] = "gdrive"
                    return
            except Exception as e:
                log_status(f"GDrive pre-check error: {e}")

        # Collect all downloadable files (prefer actual FILEs over FOLDERs)
        downloadable = []
        for f in file_list:
            if not isinstance(f, dict):
                continue
            raw_url = (
                f.get("downloadUrl")
                or f.get("download_url")
                or f.get("url")
                or f.get("signedUrl")
                or f.get("location")
            )
            if not raw_url:
                continue

            # Convert relative URLs to absolute
            if raw_url.startswith("/_/") or raw_url.startswith("/api/"):
                raw_url = f"{BC_ORIGIN}{raw_url}"

            file_type = f.get("type", "FILE").upper()
            file_name = f.get("name", "download")
            file_size = f.get("size", 0)
            downloadable.append({
                "url": raw_url,
                "name": file_name,
                "type": file_type,
                "size": file_size,
            })

        if not downloadable:
            sample = file_list[0] if file_list else None
            if isinstance(sample, dict):
                log_status(f"[FILES] No download URL found. File keys: {list(sample.keys())}")
                _debug_dump("files_no_url", file_list[:3])
            else:
                log_status(f"[FILES] No download URL found. File type: {type(sample).__name__}")
            return

        # Sort: FILES first (actual documents), then FOLDERs (which download as zip)
        downloadable.sort(key=lambda x: (0 if x["type"] == "FILE" else 1, -x["size"]))

        log_status(f"[FILES] Found {len(downloadable)} downloadable items: "
                   + ", ".join(f'{d["name"]} ({d["type"]})' for d in downloadable[:5]))

        # Download the largest folder (contains all plans) or first file
        # Prefer the biggest folder since it likely contains plans/drawings
        best = None
        for d in downloadable:
            if d["type"] == "FOLDER" and d["size"] > 0:
                best = d
                break
        if not best:
            best = downloadable[0]

        download_url = best["url"]
        log_status(f"[FILES] Downloading '{best['name']}' ({best['size']:,} bytes) from: {download_url[:80]}...")
        local_path = await self._api.download_file(download_url, self.download_dir)
        if not local_path:
            return

        new_file = os.path.basename(local_path)

        # Upload to Google Drive if available
        use_gdrive = False
        if GDRIVE_AVAILABLE:
            try:
                use_gdrive = should_use_gdrive()
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
                    source="BuildingConnected",
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

    # -- main scraping -------------------------------------------------------

    async def scrape_all_projects(self, max_projects=None, include_details=True, download_files=True):
        """
        Fetch projects from BC pipeline and enrich each one.

        Args:
            max_projects: Max number of projects to process (None = all)
            include_details: Whether to fetch per-project details
            download_files: Whether to download project files
        """
        log_status("=" * 40)
        log_status("Starting BuildingConnected API scrape")

        # 1. Auth
        if not await self._api.ensure_auth():
            log_status("Failed to authenticate with BuildingConnected")
            return []

        # 2. Get pipeline data
        pipeline_data = self._api._pipeline_cache
        if not pipeline_data:
            log_status("No pipeline data from initial load, retrying...")
            pipeline_data = await self._api.get_pipeline_via_browser()

        if not pipeline_data:
            log_status("Could not get pipeline data. BC scrape aborted.")
            return []

        all_projects = pipeline_data if isinstance(pipeline_data, list) else []

        if max_projects:
            all_projects = all_projects[:max_projects]

        log_status(f"Processing {len(all_projects)} projects from pipeline")

        # 3. Process each project
        for i, proj in enumerate(all_projects):
            project_id = str(
                self._get(proj, "_id", "id", "opportunityId", "projectId", default=str(i))
            )

            lead_id = f"bc_{project_id}"
            if lead_id in self.processed_ids:
                log_status(f"Skipping duplicate: {lead_id}")
                continue
            self.processed_ids.add(lead_id)

            # Extract fields from the intercepted pipeline data
            name = self._get(
                proj, "name", "projectName", "title", "project_name",
                default="Unknown",
            )

            # Date handling - BC pipeline uses "dateDue"
            bid_date_str = self._get(
                proj, "dateDue", "bidsDueAt", "dueDate", "bid_date",
                "due_date", "bidDate", "bidDueDate",
                default="",
            )

            if bid_date_str and self._is_past_due(bid_date_str):
                log_status(f"Skipping past-due: {name[:40]}")
                continue

            # Location
            location_obj = proj.get("location") or proj.get("address") or {}
            if isinstance(location_obj, dict):
                city = self._get(location_obj, "city", default="")
                state = self._get(location_obj, "state", default="")
                full_address = self._get(location_obj, "complete", "formattedAddress", "address", default="")
                location = f"{city}, {state}" if city and state else (full_address or "N/A")
            elif isinstance(location_obj, str):
                location = location_obj
                city = ""
                state = ""
                full_address = location_obj
            else:
                location = "N/A"
                city = ""
                state = ""
                full_address = ""

            # Company / GC info — pipeline nests under client.company.name
            company_name = "N/A"
            contact_name = "N/A"
            contact_email = ""
            contact_phone = ""

            client_obj = proj.get("client") or {}
            if isinstance(client_obj, dict):
                # Company from client.company.name
                client_company = client_obj.get("company") or {}
                if isinstance(client_company, dict):
                    company_name = self._get(client_company, "name", "companyName", default="N/A")

                # Contact from client.lead
                client_lead = client_obj.get("lead") or {}
                if isinstance(client_lead, dict):
                    fn = client_lead.get("firstName", "")
                    ln = client_lead.get("lastName", "")
                    if fn or ln:
                        contact_name = f"{fn} {ln}".strip()
                    contact_email = self._get(client_lead, "email", default="")
                    contact_phone = self._get(client_lead, "phone", default="")

            # Fallback: try flat fields if client object didn't have data
            if company_name == "N/A":
                company_name = self._get(
                    proj, "companyName", "company", "gcCompanyName",
                    "publisherCompanyName",
                    default="N/A",
                )
            if contact_name == "N/A":
                contact_name = self._get(proj, "contactName", "contact_name", default="N/A")
            if not contact_email:
                contact_email = self._get(proj, "contactEmail", "contact_email", "email", default="")
            if not contact_phone:
                contact_phone = self._get(proj, "contactPhone", "contact_phone", "phone", default="")

            # Status
            status = self._get(proj, "status", "bidStatus", default="")

            # Debug: log what fields we extracted
            if i == 0:
                log_status(f"[DEBUG] First project keys: {list(proj.keys())[:15]}")
                log_status(f"[DEBUG] client obj: {type(client_obj).__name__}, keys={list(client_obj.keys()) if isinstance(client_obj, dict) else 'N/A'}")
                log_status(f"[DEBUG] company={company_name}, contact={contact_name}, email={contact_email}, due={bid_date_str[:20] if bid_date_str else 'NONE'}")

            log_status(f"[{i+1}/{len(all_projects)}] {name[:50]} | {company_name} | {location} | due {bid_date_str[:10] if bid_date_str else 'N/A'}")

            # Build lead
            lead = {
                "id": lead_id,
                "name": name,
                "gc": company_name,
                "company": company_name,
                "contact_name": contact_name,
                "contact_phone": contact_phone,
                "contact_email": contact_email,
                "bid_date": bid_date_str,
                "due_date": bid_date_str,
                "site": "BuildingConnected",
                "source": "BuildingConnected",
                "location": location,
                "city": city,
                "state": state,
                "full_address": full_address,
                "url": f"https://app.buildingconnected.com/opportunities/{project_id}/overview",
                "status": status,
                "extracted_at": datetime.now().isoformat(),
                "files_link": None,
                "download_link": None,
                "local_file_path": None,
            }

            # 4. Enrich with details if requested
            detail_data = None
            if include_details:
                detail_data = await self._api.get_opportunity_detail(project_id)
                if detail_data:
                    _debug_dump(f"detail_{project_id}", detail_data)
                    # Merge additional detail fields
                    det = detail_data if isinstance(detail_data, dict) else {}

                    # Description/scope (strip HTML tags from BC responses)
                    description = self._get(det, "description", "scope", "notes", "projectDescription", default="")
                    if description and description != "N/A":
                        lead["description"] = self._strip_html(description)

                    # Contact info from details (might be more complete)
                    if contact_name == "N/A":
                        # Try client.lead first (same structure as pipeline)
                        det_client = det.get("client") or {}
                        det_lead = det_client.get("lead") if isinstance(det_client, dict) else None
                        creator = det_lead or det.get("creator") or det.get("contact") or {}
                        if isinstance(creator, dict):
                            fn = creator.get("firstName", "")
                            ln = creator.get("lastName", "")
                            if fn or ln:
                                lead["contact_name"] = f"{fn} {ln}".strip()
                            if not contact_email:
                                lead["contact_email"] = self._get(creator, "email", default="")
                            if not contact_phone:
                                lead["contact_phone"] = self._get(creator, "phone", default="")
                        # Also try company from details
                        if lead.get("company", "N/A") == "N/A" or lead.get("gc", "N/A") == "N/A":
                            det_company = det_client.get("company") if isinstance(det_client, dict) else None
                            if isinstance(det_company, dict):
                                cname = self._get(det_company, "name", default="")
                                if cname:
                                    lead["company"] = cname
                                    lead["gc"] = cname

                    # More accurate location from details
                    if location == "N/A":
                        det_loc = det.get("location") or det.get("address") or {}
                        if isinstance(det_loc, dict):
                            det_city = self._get(det_loc, "city", default="")
                            det_state = self._get(det_loc, "state", default="")
                            if det_city or det_state:
                                lead["location"] = f"{det_city}, {det_state}".strip(", ")
                                lead["city"] = det_city
                                lead["state"] = det_state

                await asyncio.sleep(0.3)  # Polite delay

            # 5. Handle files if requested
            if download_files:
                # Extract fileProviders — prefer from detail response, fall back to pipeline
                file_providers = {}
                if include_details and detail_data and isinstance(detail_data, dict):
                    file_providers = detail_data.get("fileProviders") or {}
                if not file_providers:
                    file_providers = proj.get("fileProviders") or {}

                # The pipeline _id may differ from the opportunity ID the files
                # API expects. Collect all candidate IDs so get_opportunity_files
                # can try each one.
                extra_ids = set()
                extra_ids.add(project_id)
                # Detail response may have the real opportunity _id
                if include_details and detail_data and isinstance(detail_data, dict):
                    for key in ("_id", "id", "opportunityId", "opportunityLinkId"):
                        val = detail_data.get(key)
                        if val:
                            extra_ids.add(str(val))
                # Pipeline may have additional IDs
                for key in ("opportunityId", "opportunityLinkId", "projectId"):
                    val = proj.get(key)
                    if val:
                        extra_ids.add(str(val))

                if i == 0:
                    log_status(f"[DEBUG] fileProviders keys: {list(file_providers.keys()) if file_providers else 'NONE'}")
                    log_status(f"[DEBUG] candidate IDs for files: {extra_ids}")
                    _debug_dump(f"file_providers_{project_id}", file_providers)

                files_data = await self._api.get_opportunity_files(
                    project_id,
                    file_providers=file_providers if file_providers else None,
                    extra_ids=extra_ids,
                )
                if files_data:
                    await self._handle_files(lead, files_data)
                else:
                    log_status(f"  -> No files found for {name[:40]}")
                await asyncio.sleep(0.3)

            self.leads.append(lead)
            log_status(f"  -> Added: {name[:40]}")

        log_status(f"SCRAPING COMPLETE - Total leads: {len(self.leads)}")
        return self.leads

    # -- save results --------------------------------------------------------

    async def save_results(self, output_file=None):
        """Save leads to JSON file."""
        output_file = output_file or os.path.join(
            os.path.dirname(__file__), "leads_db.json"
        )

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

    async def run(self, max_projects=None, include_details=True, download_files=True):
        """Run the full scraping workflow."""
        try:
            await self._api.open()
            await self.scrape_all_projects(max_projects, include_details, download_files)
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
    print(" BUILDINGCONNECTED API SCRAPER")
    print("=" * 60 + "\n")

    scraper = BuildingConnectedTableScraper()
    leads = await scraper.run(max_projects=5, include_details=True, download_files=True)

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
            print(f"  Files: {lead.get('download_link', 'None')}")
    else:
        print("\n No leads found. Check the debug output above.")
        if not BC_DEBUG:
            print(" Tip: Run with BC_DEBUG=1 to save API responses to disk.")

    print("\n" + "=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
