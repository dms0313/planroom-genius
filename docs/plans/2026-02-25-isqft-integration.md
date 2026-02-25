# iSqFt Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add iSqFt as a fifth lead source that fetches bid board projects via REST API, downloads the combined plans PDF, and merges leads into `leads_db.json` on every scraper run.

**Architecture:** A new `IsqftScraper` class in `backend/scrapers/isqft.py` mirrors the PlanHub API-first pattern — it authenticates with a cached JWT, paginates `getBidBoardProjects`, fetches `projectDocumentList` per project to find the combined plans file, downloads it, then returns the lead list. The scheduler invokes it as step 5/5 identical to how it runs PlanHub.

**Tech Stack:** Python 3 · httpx (async HTTP) · Playwright (token re-login fallback) · same `save_leads` + Google Drive helpers already used by other scrapers

**Token notes:**
- `isqft-login-token.txt` is the API token format: HS256 JWT with 12-hour lifetime; `exp` is decoded directly without an API call
- `token.json` is a Firebase token used only in the browser login flow
- Cached token file: `backend/isqft_token.json` → `{"token": "...", "saved_at": "..."}`
- Playwright re-login intercepts the response containing the iSqFt JWT to refresh the cache

**API base URL:** iSqFt's internal REST API. During Playwright re-login the network interceptor logs the actual base URL (look for requests returning `{"success":true,"data":[...]}` pattern). Start with `https://net.isqft.com/api/v1` and adjust from intercepted traffic. The exact URL **must be verified on first run** — see Task 2.

---

### Task 1: Add `IsqftConfig` to `backend/config.py`

**Files:**
- Modify: `backend/config.py` (append after `PlanHubConfig`, before `DATE_FORMATS`)

**Step 1: Add the config class**

```python
class IsqftConfig(ScraperConfig):
    """iSqFt-specific configuration."""

    # URLs — verify API_BASE_URL by inspecting Playwright-intercepted network requests on first run
    LOGIN_URL = "https://www.isqft.com/login"
    API_BASE_URL = os.getenv("ISQFT_API_BASE_URL", "https://net.isqft.com/api/v1")

    # Auth token cache
    TOKEN_FILE = os.path.join(os.path.dirname(__file__), "isqft_token.json")

    # Credentials (set in .env)
    LOGIN_EMAIL = os.getenv("ISQFT_LOGIN") or os.getenv("SITE_LOGIN", "")
    LOGIN_PASSWORD = os.getenv("ISQFT_PW") or os.getenv("SITE_PW", "")

    # Scraping limits
    MAX_PROJECTS_DEFAULT = None  # None = all
```

**Step 2: Commit**

```bash
git add backend/config.py
git commit -m "feat(isqft): add IsqftConfig"
```

---

### Task 2: Create `backend/scrapers/isqft.py` — auth client

**Files:**
- Create: `backend/scrapers/isqft.py`

This task builds only the `IsqftAPIClient` class with token management and a single `_request` helper. No project-fetching logic yet.

**Step 1: Write the file**

```python
"""
iSqFt scraper using direct REST API calls.

Auth: 12-hour HS256 JWT stored in backend/isqft_token.json.
When expired, Playwright logs in and intercepts a fresh token.

API base URL is configured via ISQFT_API_BASE_URL env var (default:
https://net.isqft.com/api/v1). On first run, watch the log output for
"Intercepted token from <url>" — that URL reveals the actual base.
"""
import os
import sys
import json
import base64
import asyncio
import traceback
from datetime import datetime, date

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import IsqftConfig, DATE_FORMATS

try:
    from services.google_drive import (
        upload_and_cleanup, should_use_gdrive, is_authenticated,
        get_status, check_file_exists,
    )
    GDRIVE_AVAILABLE = True
except ImportError:
    GDRIVE_AVAILABLE = False

# ---------------------------------------------------------------------------
# Log buffer (same pattern as planhub.py)
# ---------------------------------------------------------------------------
_isqft_log_buffer = []


def get_isqft_logs():
    global _isqft_log_buffer
    logs = _isqft_log_buffer.copy()
    _isqft_log_buffer = []
    return logs


def log_status(msg):
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

    async def open(self):
        self._client = httpx.AsyncClient(timeout=30, follow_redirects=True)

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    # -- headers -------------------------------------------------------------

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Origin": "https://www.isqft.com",
            "Referer": "https://www.isqft.com/",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/144.0.0.0 Safari/537.36"
            ),
        }

    # -- token management ----------------------------------------------------

    @staticmethod
    def _decode_exp(token: str) -> int | None:
        """Return the `exp` Unix timestamp from a JWT without verifying signature."""
        try:
            parts = token.split(".")
            if len(parts) < 2:
                return None
            padding = 4 - len(parts[1]) % 4
            payload_bytes = base64.urlsafe_b64decode(parts[1] + "=" * padding)
            payload = json.loads(payload_bytes.decode("utf-8"))
            return int(payload.get("exp", 0))
        except Exception:
            return None

    def _is_token_valid(self, token: str) -> bool:
        """Return True if token exists and has > 5 minutes until expiry."""
        exp = self._decode_exp(token)
        if not exp:
            return False
        remaining = exp - int(datetime.now().timestamp())
        return remaining > 300  # 5-minute buffer

    def _load_cached_token(self) -> str | None:
        if os.path.exists(self.config.TOKEN_FILE):
            try:
                with open(self.config.TOKEN_FILE) as f:
                    data = json.load(f)
                token = data.get("token", "")
                if token and self._is_token_valid(token):
                    log_status("Loaded valid cached token")
                    return token
                log_status("Cached token expired or invalid")
            except Exception as e:
                log_status(f"Could not read token file: {e}")
        return None

    def _save_token(self, token: str):
        try:
            with open(self.config.TOKEN_FILE, "w") as f:
                json.dump({"token": token, "saved_at": datetime.now().isoformat()}, f, indent=2)
            log_status("Saved token to disk")
        except Exception as e:
            log_status(f"Could not save token: {e}")

    async def _obtain_token_via_browser(self) -> str | None:
        """Launch Playwright, log in to iSqFt, intercept the API JWT."""
        log_status("Obtaining fresh token via browser login...")

        if not self.config.LOGIN_EMAIL or not self.config.LOGIN_PASSWORD:
            log_status("Missing ISQFT_LOGIN / ISQFT_PW credentials in .env")
            return None

        captured_token = None

        try:
            from playwright.async_api import async_playwright

            pw = await async_playwright().start()
            chrome_path = self._find_chrome_executable()

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
            )

            page = ctx.pages[0] if ctx.pages else await ctx.new_page()

            # Intercept responses to capture the JWT
            # iSqFt returns the token in an Authorization response header or JSON body.
            # Watch for any response with a Bearer token or a JSON body containing a "token" key.
            async def on_response(response):
                nonlocal captured_token
                if captured_token:
                    return
                url = response.url.lower()
                # Look for auth/login endpoints
                if any(k in url for k in ("login", "auth", "token", "signin")):
                    try:
                        body = await response.json()
                        # Common patterns: {"token": "..."}, {"data": {"token": "..."}},
                        # {"accessToken": "..."}, {"jwt": "..."}
                        token = (
                            body.get("token")
                            or body.get("accessToken")
                            or body.get("jwt")
                            or (body.get("data") or {}).get("token")
                        )
                        if token and self._is_token_valid(str(token)):
                            log_status(f"Intercepted token from {response.url[:80]}")
                            captured_token = str(token)
                    except Exception:
                        pass
                # Also check Authorization header in responses
                auth_header = response.headers.get("authorization", "")
                if auth_header.startswith("Bearer ") and not captured_token:
                    candidate = auth_header[7:]
                    if self._is_token_valid(candidate):
                        log_status(f"Got Bearer token from response header: {response.url[:80]}")
                        captured_token = candidate

            page.on("response", on_response)

            log_status(f"Navigating to {self.config.LOGIN_URL}...")
            await page.goto(self.config.LOGIN_URL, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)

            # Fill email
            for sel in ['input[type="email"]', 'input[name="email"]', 'input[id*="email"]', 'input[placeholder*="email"]']:
                try:
                    el = await page.wait_for_selector(sel, timeout=3000)
                    if el:
                        await el.fill(self.config.LOGIN_EMAIL)
                        log_status("Filled email")
                        break
                except Exception:
                    continue

            # Fill password
            for sel in ['input[type="password"]', 'input[name="password"]', 'input[id*="pass"]']:
                try:
                    el = await page.wait_for_selector(sel, timeout=3000)
                    if el:
                        await el.fill(self.config.LOGIN_PASSWORD)
                        log_status("Filled password")
                        break
                except Exception:
                    continue

            # Submit
            for sel in ['button[type="submit"]', 'button:has-text("Sign In")', 'button:has-text("Log In")', 'input[type="submit"]']:
                try:
                    el = await page.wait_for_selector(sel, timeout=3000)
                    if el:
                        await el.click()
                        log_status("Clicked submit")
                        break
                except Exception:
                    continue

            # Wait for post-login navigation and token capture (up to 20s)
            for _ in range(20):
                if captured_token:
                    break
                await asyncio.sleep(1)

            await ctx.close()
            await pw.stop()

        except Exception as e:
            log_status(f"Browser login failed: {e}")
            traceback.print_exc()

        if not captured_token:
            log_status("WARNING: Could not capture token from browser login.")
            log_status("Check ISQFT_LOGIN / ISQFT_PW in .env and verify login URL.")
        return captured_token

    def _find_chrome_executable(self):
        import platform
        system = platform.system()
        if system == "Windows":
            paths = [
                r"C:\Users\dms03\Development\planroom-genius\backend\chrome-win\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
            ]
        elif system == "Darwin":
            paths = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
        else:
            paths = ["/usr/bin/chromium-browser", "/usr/bin/chromium", "/usr/bin/google-chrome"]
        for p in paths:
            if os.path.exists(p):
                return p
        return None

    async def ensure_auth(self) -> bool:
        token = self._load_cached_token()
        if token:
            self._token = token
            return True
        token = await self._obtain_token_via_browser()
        if token:
            self._token = token
            self._save_token(token)
            return True
        log_status("Could not obtain valid auth token")
        return False

    # -- HTTP helpers --------------------------------------------------------

    async def _request(self, method: str, url: str, **kwargs):
        """Make an authenticated request with retry and 401 re-auth."""
        for attempt in range(3):
            try:
                r = await self._client.request(method, url, headers=self._headers(), **kwargs)

                if r.status_code == 401 and attempt < 2:
                    log_status("Got 401 — refreshing token via browser...")
                    token = await self._obtain_token_via_browser()
                    if token:
                        self._token = token
                        self._save_token(token)
                        continue
                    return None

                if r.status_code == 429:
                    wait = int(r.headers.get("Retry-After", 5))
                    log_status(f"Rate limited, waiting {wait}s...")
                    await asyncio.sleep(wait)
                    continue

                if r.status_code >= 400:
                    log_status(f"HTTP {r.status_code} for {method} {url}: {r.text[:200]}")
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

    async def download_file(self, url: str, dest_dir: str, filename: str = "download.pdf") -> str | None:
        """Stream-download a file to dest_dir. Returns local path or None."""
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, filename)
        try:
            async with self._client.stream("GET", url, headers=self._headers(), follow_redirects=True) as r:
                if r.status_code >= 400:
                    log_status(f"Download failed: HTTP {r.status_code}")
                    return None
                cd = r.headers.get("content-disposition", "")
                if "filename=" in cd:
                    filename = cd.split("filename=")[-1].strip('" ')
                    dest = os.path.join(dest_dir, filename)
                with open(dest, "wb") as f:
                    async for chunk in r.aiter_bytes(8192):
                        f.write(chunk)
            size = os.path.getsize(dest)
            if size < 100:
                log_status(f"Downloaded file too small ({size} bytes) — skipping")
                os.remove(dest)
                return None
            log_status(f"Downloaded: {filename} ({size:,} bytes)")
            return dest
        except Exception as e:
            log_status(f"Download error: {e}")
            return None
```

**Step 2: Commit**

```bash
git add backend/scrapers/isqft.py
git commit -m "feat(isqft): IsqftAPIClient with JWT auth and Playwright fallback"
```

---

### Task 3: Add API methods — project list + document list

**Files:**
- Modify: `backend/scrapers/isqft.py` (append methods to `IsqftAPIClient`)

**Step 1: Add these methods inside `IsqftAPIClient` (before the closing of the class)**

```python
    # -- iSqFt API methods ---------------------------------------------------

    async def get_bid_board_projects(self) -> list:
        """
        Fetch all projects from the iSqFt bid board.

        iSqFt returns the full list in one call (no pagination needed in
        practice — the research sample has 13 rows and `total: 0` which means
        the API uses offset/limit only optionally).  We request a large limit
        and iterate if a `total` field suggests more pages.
        """
        url = f"{self.config.API_BASE_URL}/bidCenter/projects/getBidBoardProjects"
        # Body mirrors the pattern seen in research: filter by inbox segment,
        # no archived items.  Adjust if the API rejects unknown fields.
        payload = {
            "startIndex": 0,
            "numberOfRows": 200,
            "dataFilterValues": {},
        }
        all_projects = []
        start = 0
        page_size = 200

        while True:
            payload["startIndex"] = start
            data = await self._request("POST", url, json=payload)
            if not data:
                log_status(f"getBidBoardProjects returned None at offset {start}")
                break

            rows = data.get("data") or []
            if not isinstance(rows, list):
                log_status(f"Unexpected data shape: {type(rows)}")
                break

            all_projects.extend(rows)
            log_status(f"Fetched {len(rows)} projects (total so far: {len(all_projects)})")

            total = data.get("numberOfRows") or data.get("total") or 0
            if total and len(all_projects) < int(total) and len(rows) == page_size:
                start += page_size
                await asyncio.sleep(0.3)
            else:
                break

        return all_projects

    async def get_document_list(self, project_id: str, package_id: str) -> list:
        """
        Fetch the document tree for a project.
        Returns the flat list of leaf files (IsLeaf == 1).

        URL pattern is a best-guess from research — adjust if it returns 404.
        Common alternatives:
          /projects/{project_id}/documentlist
          /bidCenter/projects/{project_id}/documents
        """
        url = f"{self.config.API_BASE_URL}/projects/{project_id}/documentlist"
        params = {"packageId": package_id}
        data = await self._request("GET", url, params=params)
        if not data:
            # Try alternate URL pattern
            url2 = f"{self.config.API_BASE_URL}/bidCenter/projects/{project_id}/documents"
            data = await self._request("GET", url2, params=params)
        if not data:
            return []
        # data may be a list of root folders, or {"data": [...]}
        tree = data if isinstance(data, list) else (data.get("data") or [])
        return self._flatten_leaves(tree)

    def _flatten_leaves(self, nodes: list) -> list:
        """Recursively collect all IsLeaf == 1 nodes from the document tree."""
        leaves = []
        for node in nodes:
            if not isinstance(node, dict):
                continue
            if node.get("IsLeaf") == 1:
                leaves.append(node)
            children = node.get("Children") or []
            if children:
                leaves.extend(self._flatten_leaves(children))
        return leaves

    def find_combined_plans(self, leaves: list) -> dict | None:
        """
        Return the best single PDF to download:
        1. A file named exactly "Combined Plans.pdf" (DocumentType == Plans)
        2. Any Plans leaf whose DisplayName contains "combined"
        3. First Plans leaf (largest file by Size if multiple)
        """
        plans = [f for f in leaves if f.get("DocumentType") == "Plans" and f.get("IsAccessible")]
        if not plans:
            return None

        # Prefer pre-assembled combined file
        for f in plans:
            name = (f.get("DisplayName") or "").lower()
            if "combined" in name and name.endswith(".pdf"):
                return f

        # Fall back: largest plans PDF
        pdfs = [f for f in plans if (f.get("DisplayName") or "").lower().endswith(".pdf")]
        if pdfs:
            return max(pdfs, key=lambda x: x.get("Size", 0))

        return plans[0]

    def build_download_url(self, project_id: str, item_id: str) -> str:
        """
        Build the download URL for a document by ItemId.

        Best-guess pattern — if it returns 404, common alternatives:
          {base}/documents/{item_id}/download
          {base}/projects/{project_id}/documents/{item_id}/download
          {base}/bidCenter/documents/download?itemId={item_id}
        """
        return f"{self.config.API_BASE_URL}/projects/{project_id}/documents/{item_id}/download"
```

**Step 2: Commit**

```bash
git add backend/scrapers/isqft.py
git commit -m "feat(isqft): add getBidBoardProjects, getDocumentList, and download URL helpers"
```

---

### Task 4: Add `IsqftScraper` class (lead mapping + file download)

**Files:**
- Modify: `backend/scrapers/isqft.py` (append `IsqftScraper` class at module level, after `IsqftAPIClient`)

**Step 1: Append the scraper class**

```python
# ---------------------------------------------------------------------------
# IsqftScraper
# ---------------------------------------------------------------------------
class IsqftScraper:
    """
    iSqFt scraper — public interface matches PlanHub:
        scraper = IsqftScraper()
        leads = await scraper.run(max_projects=None, download_files=True)
    """

    def __init__(self):
        self.config = IsqftConfig()
        self.leads: list = []
        self.processed_ids: set = set()
        self.download_dir = self.config.DOWNLOAD_DIR
        os.makedirs(self.download_dir, exist_ok=True)
        self._api = IsqftAPIClient(self.config)

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _get(obj, *keys, default="N/A"):
        if not isinstance(obj, dict):
            return default
        for k in keys:
            v = obj.get(k)
            if v is not None and v != "":
                return v
        return default

    def _parse_date(self, date_str: str):
        if not date_str or date_str == "N/A":
            return None
        for fmt in DATE_FORMATS:
            try:
                return datetime.strptime(str(date_str).strip(), fmt).date()
            except ValueError:
                continue
        try:
            return datetime.fromisoformat(str(date_str).replace("Z", "+00:00")).date()
        except Exception:
            pass
        return None

    def _is_past_due(self, date_str: str) -> bool:
        parsed = self._parse_date(date_str)
        return bool(parsed and parsed < date.today())

    def _map_lead(self, proj: dict) -> dict:
        """Map a getBidBoardProjects item to the internal lead schema."""
        isqft_id = str(proj.get("isqftId") or proj.get("id") or "")
        lead_id = f"isqft_{isqft_id}"

        addr = proj.get("address") or {}
        city = addr.get("city") or ""
        state = addr.get("state") or ""
        zipcode = addr.get("zipcode") or ""
        addr_line = addr.get("addressLine1") or ""

        location = f"{city}, {state}" if city and state else (city or state or "N/A")
        full_address_parts = [p for p in [addr_line, city, state, zipcode] if p]
        full_address = ", ".join(full_address_parts) if full_address_parts else location

        bid_date = proj.get("bidDate") or "N/A"
        gc_company = proj.get("gcCompanyName") or "N/A"

        # Contact: from packageContactsNames (first entry)
        contact_names = proj.get("packageContactsNames") or []
        contact_name = contact_names[0] if contact_names else "N/A"

        return {
            "id": lead_id,
            "name": proj.get("title") or "Unknown",
            "gc": gc_company,
            "company": gc_company,
            "contact_name": contact_name,
            "contact_phone": "",
            "contact_email": "",
            "bid_date": bid_date,
            "due_date": bid_date,
            "site": "iSqFt",
            "source": "iSqFt",
            "sprinklered": False,
            "location": location,
            "city": city,
            "state": state,
            "full_address": full_address,
            "url": f"https://www.isqft.com/projects/{isqft_id}",
            "value": "",
            "project_type": "",
            "description": "",
            "extracted_at": datetime.now().isoformat(),
            "files_link": None,
            "download_link": None,
            "local_file_path": None,
            # iSqFt-specific extras
            "isqft_id": isqft_id,
            "isqft_package_id": str(proj.get("packageId") or ""),
            "isqft_document_count": proj.get("documentCount") or 0,
            "isqft_phase": proj.get("phaseStatus") or "",
            "isqft_is_rfq": bool(proj.get("isRfq")),
            "isqft_bid_board_status": proj.get("bidBoardStatus") or "",
            "isqft_document_status": proj.get("documentStatus") or "",
        }

    async def _handle_download(self, lead: dict):
        """Fetch document list, find combined plans PDF, download it."""
        isqft_id = lead.get("isqft_id", "")
        package_id = lead.get("isqft_package_id", "")
        if not isqft_id:
            return

        project_name_clean = "".join(
            c for c in lead["name"][:60] if c.isalnum() or c in " -_"
        ).strip()
        dest_dir = os.path.join(self.download_dir, project_name_clean)

        # Check Google Drive first
        if GDRIVE_AVAILABLE and should_use_gdrive():
            try:
                existing = check_file_exists(f"{project_name_clean}.pdf", source="iSqFt")
                if not existing:
                    existing = check_file_exists(f"{project_name_clean}.zip", source="iSqFt")
                if existing:
                    lead["gdrive_file_id"] = existing.get("file_id")
                    lead["gdrive_link"] = existing.get("web_link")
                    lead["download_link"] = existing.get("web_link")
                    lead["storage_type"] = "gdrive"
                    log_status(f"  -> Already in Google Drive")
                    return
            except Exception as e:
                log_status(f"  -> GDrive pre-check error: {e}")

        # Fetch document tree
        log_status(f"  -> Fetching document list for project {isqft_id}...")
        leaves = await self._api.get_document_list(isqft_id, package_id)
        if not leaves:
            log_status(f"  -> No accessible documents found")
            return

        target = self._api.find_combined_plans(leaves)
        if not target:
            log_status(f"  -> No Plans PDF found in document list")
            return

        item_id = str(target.get("ItemId") or "")
        filename = target.get("DisplayName") or f"{project_name_clean}.pdf"
        log_status(f"  -> Downloading '{filename}' (ItemId={item_id})...")

        download_url = self._api.build_download_url(isqft_id, item_id)
        local_path = await self._api.download_file(download_url, dest_dir, filename)

        if not local_path:
            log_status(f"  -> Download failed for {filename}")
            return

        web_path = f"/downloads/{project_name_clean}/{filename}"
        lead["local_file_path"] = web_path
        lead["download_link"] = web_path
        lead["storage_type"] = "local"

        # Upload to Google Drive
        if GDRIVE_AVAILABLE and should_use_gdrive():
            try:
                result = upload_and_cleanup(
                    local_path,
                    filename=f"{project_name_clean}.pdf",
                    source="iSqFt",
                    delete_local=True,
                )
                if result:
                    lead["gdrive_file_id"] = result.get("file_id")
                    lead["gdrive_link"] = result.get("web_link")
                    lead["gdrive_download_link"] = result.get("download_link")
                    lead["download_link"] = result.get("web_link")
                    lead["storage_type"] = "gdrive"
                    log_status(f"  -> Uploaded to Google Drive")
            except Exception as e:
                log_status(f"  -> Google Drive upload failed: {e}")

    # -- main ----------------------------------------------------------------

    async def scrape_all_projects(self, max_projects=None, download_files=False):
        log_status("=" * 40)
        log_status("Starting iSqFt scrape")

        if not await self._api.ensure_auth():
            log_status("Authentication failed — aborting")
            return []

        log_status("Fetching bid board projects...")
        all_projects = await self._api.get_bid_board_projects()
        log_status(f"Fetched {len(all_projects)} total projects from API")

        if max_projects:
            all_projects = all_projects[:max_projects]

        for i, proj in enumerate(all_projects):
            isqft_id = str(proj.get("isqftId") or proj.get("id") or i)
            lead_id = f"isqft_{isqft_id}"

            if lead_id in self.processed_ids:
                log_status(f"Skipping duplicate: {lead_id}")
                continue
            self.processed_ids.add(lead_id)

            # Skip archived
            if proj.get("isArchived"):
                log_status(f"Skipping archived: {proj.get('title', '')[:40]}")
                continue

            # Skip past-due
            bid_date_str = proj.get("bidDate") or ""
            if bid_date_str and self._is_past_due(bid_date_str):
                log_status(f"Skipping past-due: {proj.get('title', '')[:40]}")
                continue

            lead = self._map_lead(proj)
            name = lead["name"]
            log_status(f"[{i+1}/{len(all_projects)}] {name[:50]} | {lead['company']} | {lead['location']} | bid {lead['bid_date']}")

            if download_files:
                await self._handle_download(lead)
                await asyncio.sleep(0.5)

            self.leads.append(lead)

        log_status(f"COMPLETE — {len(self.leads)} leads")
        return self.leads

    async def save_results(self, output_file=None):
        from config import ScraperConfig
        output_file = output_file or ScraperConfig.DB_FILE
        existing = []
        if os.path.exists(output_file):
            try:
                with open(output_file) as f:
                    existing = json.load(f)
            except Exception:
                pass
        existing_ids = {l.get("id") for l in existing}
        new_leads = [l for l in self.leads if l.get("id") not in existing_ids]
        with open(output_file, "w") as f:
            json.dump(existing + new_leads, f, indent=2)
        log_status(f"Saved {len(new_leads)} new leads (total: {len(existing) + len(new_leads)})")

    async def run(self, max_projects=None, download_files=False):
        try:
            await self._api.open()
            await self.scrape_all_projects(max_projects, download_files)
            await self.save_results()
            return self.leads
        except Exception as e:
            log_status(f"Fatal error: {e}")
            traceback.print_exc()
            return self.leads
        finally:
            await self._api.close()
```

**Step 2: Commit**

```bash
git add backend/scrapers/isqft.py
git commit -m "feat(isqft): IsqftScraper with lead mapping, document download, GDrive upload"
```

---

### Task 5: Wire into `backend/services/scheduler.py`

**Files:**
- Modify: `backend/services/scheduler.py`

**Step 1: Add import at top of file (with other scraper imports, line ~17)**

```python
from scrapers.isqft import IsqftScraper
```

**Step 2: Add `isqft` to `scraper_status` dict (lines ~27-37)**

```python
    "isqft_leads_found": 0,
```

**Step 3: Add `isqft` to `DEFAULT_SETTINGS` (line ~100)**

```python
    "isqft": True,
```

**Step 4: Add iSqFt block after the BuildingConnected block (after line ~485, before "Save aggregated results")**

```python
    # Run iSqFt Scraper
    if not scraper_status["running"]:
        logger.info("Scan stopped before iSqFt")
        return

    if settings.get("isqft", True):
        try:
            update_status("iSqFt: Initializing")
            print("\n[5/5] iSqFt Scraper", flush=True)
            print("-" * 40, flush=True)
            logger.info("Launching iSqFt Scraper...")

            isqft_scraper = IsqftScraper()

            async def collect_isqft_logs():
                from scrapers.isqft import get_isqft_logs
                while scraper_status["running"]:
                    try:
                        for log in get_isqft_logs():
                            add_to_log(log)
                    except Exception:
                        pass
                    await asyncio.sleep(0.5)

            isqft_log_collector = asyncio.create_task(collect_isqft_logs())

            try:
                isqft_leads = await asyncio.wait_for(
                    isqft_scraper.run(max_projects=None, download_files=True),
                    timeout=900,
                )
            except asyncio.TimeoutError:
                logger.error("iSqFt scraper timed out")
                add_to_log("[ISQFT] TIMEOUT after 15 minutes")
                isqft_leads = isqft_scraper.leads if hasattr(isqft_scraper, "leads") else []

            isqft_log_collector.cancel()
            try:
                await isqft_log_collector
            except asyncio.CancelledError:
                pass

            scraper_status["isqft_leads_found"] = len(isqft_leads)
            update_status("iSqFt: Complete", f"Found {len(isqft_leads)} leads")
            print(f"\n[OK] iSqFt found {len(isqft_leads)} leads", flush=True)
            leads.extend(isqft_leads)

            # Incremental save
            save_leads(leads)

        except Exception as e:
            scraper_status["last_error"] = f"iSqFt: {str(e)}"
            update_status("iSqFt: ERROR", str(e))
            logger.error(f"iSqFt Scraper failed: {e}")
            traceback.print_exc()
    else:
        logger.info("iSqFt scraper disabled in settings")
```

**Step 5: Update the "[4/4]" log line in the BuildingConnected block to "[4/5]"** (minor label fix, line ~428)

**Step 6: Commit**

```bash
git add backend/services/scheduler.py
git commit -m "feat(isqft): wire IsqftScraper into scheduler as step 5/5"
```

---

### Task 6: Expose iSqFt in `backend/api.py` status endpoint

**Files:**
- Modify: `backend/api.py` (the `/status` endpoint, lines ~185-189)

**Step 1: Add `isqft` to the `leads_found` dict**

Find:
```python
        "leads_found": {
            "buildingconnected": status["bc_leads_found"],
            "planhub": status["ph_leads_found"]
        }
```

Replace with:
```python
        "leads_found": {
            "buildingconnected": status["bc_leads_found"],
            "planhub": status["ph_leads_found"],
            "isqft": status.get("isqft_leads_found", 0)
        }
```

**Step 2: Commit**

```bash
git add backend/api.py
git commit -m "feat(isqft): expose isqft lead count in /status endpoint"
```

---

### Task 7: Seed `backend/isqft_token.json` from research file

The `isqft-login-token.txt` in the repo root contains a recently-issued JWT that may still be valid. Seed it so the first scraper run doesn't need a browser login.

**Step 1: Run this one-time seed script**

```bash
cd /c/Users/dms03/Development/planroom-genius/backend
python3 -c "
import json
from datetime import datetime
token = open('../isqft/isqft-login-token.txt').read().strip()
with open('isqft_token.json', 'w') as f:
    json.dump({'token': token, 'saved_at': datetime.now().isoformat()}, f, indent=2)
print('Seeded isqft_token.json')
"
```

**Step 2: Verify the token's expiry**

```bash
python3 -c "
import json, base64
token = json.load(open('isqft_token.json'))['token']
parts = token.split('.')
payload = json.loads(base64.urlsafe_b64decode(parts[1] + '==').decode())
from datetime import datetime
exp = datetime.fromtimestamp(payload['exp'])
print('Token expires:', exp)
print('Valid:', exp > datetime.now())
"
```

Expected: if expired, the scraper will trigger a Playwright re-login automatically on first run.

**Step 3: Add `isqft_token.json` to `.gitignore`**

```bash
echo "backend/isqft_token.json" >> .gitignore
git add .gitignore
git commit -m "chore: ignore isqft_token.json (contains auth credentials)"
```

---

### Task 8: Add `.env` credentials

**Files:**
- Modify: `backend/.env` (or root `.env` — whichever the other scrapers use)

**Step 1: Add iSqFt credentials**

```
ISQFT_LOGIN=dsullivan@marmicfire.com
ISQFT_PW=<password>
```

Note: `ISQFT_LOGIN` falls back to `SITE_LOGIN` and `ISQFT_PW` falls back to `SITE_PW` (same env vars used by PlanHub), so if those are already set nothing extra is needed.

**Step 2: Confirm `.env` is in `.gitignore`** (it should already be)

---

### Task 9: First run verification

**Step 1: Run only the iSqFt scraper in isolation**

```bash
cd /c/Users/dms03/Development/planroom-genius/backend
python3 -c "
import asyncio
from scrapers.isqft import IsqftScraper

async def main():
    s = IsqftScraper()
    leads = await s.run(max_projects=3, download_files=False)
    print(f'Got {len(leads)} leads')
    for l in leads:
        print(l['id'], l['name'][:50], l['bid_date'])

asyncio.run(main())
"
```

**Expected:** 3 leads printed with `isqft_XXXXXXX` IDs.

**If you see HTTP 404 on the API calls:**
- The `API_BASE_URL` or endpoint path is wrong
- Watch the logs for "Intercepted token from <url>" during Playwright login — the URL prefix is your correct `API_BASE_URL`
- Update `IsqftConfig.API_BASE_URL` and/or the `get_bid_board_projects` / `get_document_list` URL strings in `isqft.py`
- Common alternative base URLs: `https://www.isqft.com/api`, `https://api.isqft.com/v1`, `https://net.isqft.com`

**If you see auth errors (401):**
- Token is expired and Playwright re-login is firing — verify `ISQFT_LOGIN` and `ISQFT_PW` in `.env`
- Check that the login interceptor catches the right response (look for "Intercepted token from" in logs)

**Step 2: Run with downloads**

```bash
python3 -c "
import asyncio
from scrapers.isqft import IsqftScraper

async def main():
    s = IsqftScraper()
    leads = await s.run(max_projects=2, download_files=True)
    for l in leads:
        print(l['id'], '| download:', l.get('download_link') or 'NONE')

asyncio.run(main())
"
```

**If document download returns 404:**
- The `build_download_url` pattern is wrong
- Intercept the actual download request in a browser DevTools session and match the URL pattern
- Update `build_download_url` in `isqft.py` accordingly

**Step 3: Commit any URL fixes found during testing**

```bash
git add backend/scrapers/isqft.py backend/config.py
git commit -m "fix(isqft): correct API base URL and endpoint paths from first-run testing"
```

---

### Task 10: Final commit + push

```bash
cd /c/Users/dms03/Development/planroom-genius
git push
```
