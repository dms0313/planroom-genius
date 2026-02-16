"""
Bidplanroom.com scraper using Playwright browser automation.

This site is server-rendered HTML (Bootstrap + jQuery) with no REST API.
Authentication goes through ConstructConnect SSO.  We use Playwright with
a persistent browser profile so login cookies survive across runs.

The invitation table at #invitations-container holds all active projects.
For each row we click into the project detail page, extract info, attempt
to download plans via the Bluebeam viewer, then navigate back.
"""
import os
import sys
import json
import asyncio
import platform
import traceback
from datetime import datetime, date

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
_bpr_log_buffer = []


def get_bpr_logs():
    """Get and clear the log buffer."""
    global _bpr_log_buffer
    logs = _bpr_log_buffer.copy()
    _bpr_log_buffer = []
    return logs


def log_status(msg):
    """Log to console and buffer (scheduler collector forwards to web UI)."""
    global _bpr_log_buffer
    print(f"[BPR] {msg}", flush=True)
    _bpr_log_buffer.append(f"[BPR] {msg}")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
class BidplanroomConfig:
    """Configuration for Bidplanroom scraper."""

    BASE_URL = "https://www.bidplanroom.com/"
    LOGIN_EMAIL = os.getenv("BIDPLANROOM_EMAIL", "dsullivan@marmicfire.com")
    LOGIN_PASSWORD = os.getenv("BIDPLANROOM_PW", "#pancakeNips1")

    SPRINKLER_KEYWORDS = [
        "sprinkler", "fire protection", "fire alarm", "fire suppression",
        "wet system", "dry system", "fppi", "nfpa",
    ]

    DOWNLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "downloads")


# ---------------------------------------------------------------------------
# BidplanroomScraper
# ---------------------------------------------------------------------------
class BidplanroomScraper:
    """
    Bidplanroom scraper using Playwright with persistent browser context.

    Public interface (unchanged from Pyppeteer version):
        - BidplanroomScraper()
        - await scraper.scrape_all_projects(max_projects=10) -> list[dict]
        - scraper.leads  (used on timeout fallback)
    """

    def __init__(self):
        self.config = BidplanroomConfig()
        self.leads = []
        self.processed_ids = set()
        self.download_dir = self.config.DOWNLOAD_DIR
        os.makedirs(self.download_dir, exist_ok=True)

        self._pw = None
        self._ctx = None
        self._page = None

    # -- browser lifecycle ---------------------------------------------------

    async def _setup_browser(self):
        """Launch Playwright with persistent context."""
        from playwright.async_api import async_playwright

        self._pw = await async_playwright().start()

        playwright_profile = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "playwright_profile",
        )

        chrome_path = self._find_chrome_executable()

        log_status(f"Launching browser (profile: {playwright_profile})")

        self._ctx = await self._pw.chromium.launch_persistent_context(
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
            viewport={"width": 1280, "height": 720},
            accept_downloads=True,
            downloads_path=self.download_dir,
            ignore_https_errors=True,
            ignore_default_args=["--enable-automation"],
        )

        self._page = self._ctx.pages[0] if self._ctx.pages else await self._ctx.new_page()
        log_status("Browser initialized")

    async def _close_browser(self):
        """Shut down browser."""
        try:
            if self._ctx:
                await self._ctx.close()
        except Exception:
            pass
        try:
            if self._pw:
                await self._pw.stop()
        except Exception:
            pass
        self._ctx = None
        self._pw = None
        self._page = None

    def _find_chrome_executable(self):
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
        for p in possible_paths:
            if os.path.exists(p):
                return p
        return None

    # -- helpers -------------------------------------------------------------

    def parse_date(self, date_str):
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

    # -- login ---------------------------------------------------------------

    async def _check_login_status(self):
        """Check if already logged in by looking for dashboard elements."""
        try:
            has_projects = await self._page.evaluate("""() => {
                return !!document.querySelector('#invitations-container') ||
                       !!document.querySelector('#project-info-container') ||
                       !!document.querySelector('.workspace');
            }""")
            if has_projects:
                log_status("Already logged in")
                return True

            login_visible = await self._page.evaluate("""() => {
                const loginBtn = document.querySelector('#login-val-btn');
                const emailInput = document.querySelector('input[type="email"]');
                return !!(loginBtn || emailInput);
            }""")
            if login_visible:
                log_status("Login required")
                return False

            return False
        except Exception as e:
            log_status(f"Could not determine login status: {e}")
            return False

    async def _login(self):
        """Perform login via the Bidplanroom login form."""
        log_status("Logging in to Bidplanroom...")

        try:
            await self._page.goto(self.config.BASE_URL, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(2)

            # Fill email
            email_filled = await self._page.evaluate(f"""() => {{
                const inputs = document.querySelectorAll(
                    'input[type="email"], input[name="email"], input[placeholder*="email" i]'
                );
                for (const input of inputs) {{
                    input.value = "{self.config.LOGIN_EMAIL}";
                    input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    return true;
                }}
                return false;
            }}""")

            if not email_filled:
                log_status("Could not find email input")
                return False
            log_status(f"Entered email: {self.config.LOGIN_EMAIL}")

            # Fill password
            pw_filled = await self._page.evaluate(f"""() => {{
                const inputs = document.querySelectorAll(
                    'input[type="password"], input[name="password"]'
                );
                for (const input of inputs) {{
                    input.value = "{self.config.LOGIN_PASSWORD}";
                    input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    return true;
                }}
                return false;
            }}""")

            if not pw_filled:
                log_status("Could not find password input")
                return False
            log_status("Entered password")

            # Click login button
            login_clicked = await self._page.evaluate("""() => {
                const loginBtn = document.querySelector('#login-val-btn');
                if (loginBtn) { loginBtn.click(); return true; }
                const btns = document.querySelectorAll('button, input[type="submit"], a.btn');
                for (const btn of btns) {
                    const text = (btn.textContent || btn.value || '').toLowerCase();
                    if (text.includes('log in') || text.includes('login') || text.includes('sign in')) {
                        btn.click();
                        return true;
                    }
                }
                return false;
            }""")

            if not login_clicked:
                log_status("Could not find login button")
                return False
            log_status("Submitted login form")

            # Wait for navigation
            await asyncio.sleep(4)

            # Verify
            is_logged_in = await self._check_login_status()
            if is_logged_in or "invitations" in self._page.url or "project" in self._page.url:
                log_status("Login successful")
                return True

            log_status(f"Login may have failed (URL: {self._page.url})")
            return False

        except Exception as e:
            log_status(f"Login failed: {e}")
            traceback.print_exc()
            return False

    # -- project extraction --------------------------------------------------

    async def _get_project_rows(self):
        """Extract all project rows from the invitations table."""
        try:
            log_status("Getting project rows...")
            await asyncio.sleep(2)

            projects = await self._page.evaluate("""() => {
                const rows = document.querySelectorAll('#invitations-container table tbody tr');
                const projects = [];

                rows.forEach((row, index) => {
                    const cells = row.querySelectorAll('td');
                    if (cells.length < 2) return;

                    // First cell: project name + location
                    const firstCell = cells[0];
                    const nameEl = firstCell.querySelector('a, strong, b, div:first-child');
                    const name = nameEl ? nameEl.textContent.trim() :
                                 (firstCell.textContent.split('\\n')[0] || '').trim();

                    const locationDiv = firstCell.querySelector('div:nth-child(2)');
                    const location = locationDiv ? locationDiv.textContent.trim() : '';

                    // Second cell: due date
                    const dateCell = cells[1];
                    const dateDiv = dateCell.querySelector('div:first-child');
                    const dueDate = dateDiv ? dateDiv.textContent.trim() : dateCell.textContent.trim();

                    if (!name) return;

                    projects.push({
                        index: index,
                        name: name,
                        location: location,
                        due_date: dueDate
                    });
                });

                return projects;
            }""")

            log_status(f"Found {len(projects)} projects in table")
            return projects

        except Exception as e:
            log_status(f"Error getting project rows: {e}")
            return []

    async def _click_project_row(self, project_index):
        """Click on a project row by index."""
        try:
            clicked = await self._page.evaluate(f"""() => {{
                const rows = document.querySelectorAll('#invitations-container table tbody tr');
                if (rows[{project_index}]) {{
                    rows[{project_index}].click();
                    return true;
                }}
                return false;
            }}""")
            return clicked
        except Exception:
            return False

    async def _extract_project_details(self):
        """Extract detailed info from the currently open project page."""
        log_status("  Extracting project details...")

        details = {}

        try:
            await asyncio.sleep(2)

            details = await self._page.evaluate("""() => {
                const result = {};

                // Name
                const h2 = document.querySelector(
                    '#page-top div.content div.workspace h2, .tab-content h2'
                );
                result.name = h2 ? h2.textContent.trim() : '';

                // Company
                const companyEl = document.querySelector(
                    '#project-info-container div:nth-child(5) b'
                );
                result.company = companyEl ? companyEl.textContent.trim() : '';

                // Contact name - look for "Contact:" text
                const container = document.querySelector('#project-info-container');
                result.contact_name = '';
                result.contact_phone = '';
                result.contact_email = '';
                result.description = '';

                if (container) {
                    const text = container.textContent;

                    // Phone
                    const phoneMatch = text.match(
                        /\\(?\\d{3}\\)?[\\s\\-\\.]*\\d{3}[\\s\\-\\.]*\\d{4}/
                    );
                    if (phoneMatch) result.contact_phone = phoneMatch[0];

                    // Email
                    const emailLinks = container.querySelectorAll('a[href^="mailto:"]');
                    if (emailLinks.length > 0) {
                        result.contact_email = emailLinks[0].href.replace('mailto:', '');
                    } else {
                        const emailMatch = text.match(
                            /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}/
                        );
                        if (emailMatch) result.contact_email = emailMatch[0];
                    }

                    // Description - typically in div:nth-child(6)
                    const descEl = container.querySelector(
                        'div:nth-child(5) div:nth-child(6), div:nth-child(5) div:nth-child(1) div:nth-child(6) div'
                    );
                    if (descEl) result.description = descEl.textContent.trim();

                    // Contact name
                    const divs = container.querySelectorAll('div');
                    for (const div of divs) {
                        const t = div.textContent;
                        if (t && t.includes('Contact:')) {
                            result.contact_name = t.replace('Contact:', '').trim();
                            break;
                        }
                    }
                }

                return result;
            }""")

            log_status(f"  Name: {details.get('name', 'N/A')[:40]}")
            log_status(f"  Company: {details.get('company', 'N/A')}")
            return details

        except Exception as e:
            log_status(f"  Error extracting details: {e}")
            return details

    async def _download_project_files(self, lead):
        """Navigate to View Plans -> Bluebeam viewer -> Download."""
        log_status("  Downloading project files...")

        try:
            files_before = set(os.listdir(self.download_dir)) if os.path.exists(self.download_dir) else set()

            # Step 1: Click "View Plans" link on the project details page
            view_plans_clicked = await self._page.evaluate("""() => {
                const el = document.querySelector(
                    '#project-info-container > div:nth-child(4) > div > div > a:nth-child(1) > span'
                );
                if (el) { el.click(); return true; }
                const links = document.querySelectorAll('a');
                for (const link of links) {
                    const text = link.textContent.toLowerCase();
                    if (text.includes('view plans')) {
                        link.click();
                        return true;
                    }
                }
                return false;
            }""")

            if not view_plans_clicked:
                log_status("  Could not find View Plans link")
                return False

            log_status("  Clicked View Plans, waiting for viewer...")
            await asyncio.sleep(3)

            # Step 2: Click "Open Project Plan Folder" — this opens a new tab with the Bluebeam viewer
            viewer_page = None
            try:
                async with self._ctx.expect_page(timeout=15000) as new_page_info:
                    launch_clicked = await self._page.evaluate("""() => {
                        const el = document.querySelector('#launch-plans-btn > span');
                        if (el) { el.click(); return true; }
                        const btn = document.querySelector('#launch-plans-btn');
                        if (btn) { btn.click(); return true; }
                        return false;
                    }""")
                    if not launch_clicked:
                        log_status("  Could not find Open Project Plan Folder button")
                        return False
                viewer_page = await new_page_info.value
                log_status("  Opened Bluebeam viewer in new tab")
            except Exception:
                # Fallback: check if a new page already appeared
                pages = self._ctx.pages
                if len(pages) > 1:
                    viewer_page = pages[-1]
                    log_status("  Found Bluebeam viewer tab")
                else:
                    log_status("  No new tab opened for viewer, trying current page")
                    viewer_page = self._page

            # Wait for the Bluebeam viewer app to load
            try:
                await viewer_page.wait_for_selector('#applicationHost', timeout=20000)
                log_status("  Bluebeam viewer loaded")
            except Exception:
                log_status("  Waiting extra time for viewer to load...")
                await asyncio.sleep(10)

            # Step 3: Click Select All checkbox
            select_clicked = await viewer_page.evaluate("""() => {
                const el = document.querySelector(
                    '#applicationHost > div > div.css-13bog6r-shell > div.css-anjy84-content > div > div.css-ndbj9-container > div > div.css-1s7evc > label > label > input'
                );
                if (el) { el.click(); return true; }
                // Fallback: find any checkbox-like input inside #applicationHost
                const cb = document.querySelector('#applicationHost label input[type="checkbox"]');
                if (cb) { cb.click(); return true; }
                const labels = document.querySelectorAll('#applicationHost label');
                for (const label of labels) {
                    if (label.textContent.toLowerCase().includes('select all')) {
                        label.click();
                        return true;
                    }
                }
                return false;
            }""")

            if select_clicked:
                log_status("  Selected all files")
                await asyncio.sleep(1)
            else:
                log_status("  Could not find Select All checkbox")

            # Step 4: Click Download button
            download_clicked = await viewer_page.evaluate("""() => {
                const el = document.querySelector(
                    '#applicationHost > div > div.css-13bog6r-shell > div.css-anjy84-content > div > div:nth-child(7) > div.css-1c7oem8 > div > div > div.css-1tepa3u-downloadButton > button > div'
                );
                if (el) { el.click(); return true; }
                // Fallback: find download button inside #applicationHost
                const dlBtn = document.querySelector(
                    '#applicationHost [class*="downloadButton"] button'
                );
                if (dlBtn) { dlBtn.click(); return true; }
                const btns = document.querySelectorAll('#applicationHost button');
                for (const btn of btns) {
                    if (btn.textContent.toLowerCase().includes('download')) {
                        btn.click();
                        return true;
                    }
                }
                return false;
            }""")

            if download_clicked:
                log_status("  Download initiated, waiting...")
                await asyncio.sleep(15)
            else:
                log_status("  Could not find Download button")
                # Close the viewer tab if it's separate
                if viewer_page != self._page:
                    await viewer_page.close()
                return False

            # Close the viewer tab now that download has started
            if viewer_page != self._page:
                await viewer_page.close()

            # Check for new files
            files_after = set(os.listdir(self.download_dir)) if os.path.exists(self.download_dir) else set()
            new_files = files_after - files_before

            if new_files:
                new_file = sorted(
                    new_files,
                    key=lambda f: os.path.getmtime(os.path.join(self.download_dir, f)),
                )[-1]
                local_path = os.path.join(self.download_dir, new_file)
                log_status(f"  Downloaded: {new_file}")

                # Build a clean project name for folder/file naming
                project_name_clean = "".join(
                    c for c in lead.get("name", "project")[:50]
                    if c.isalnum() or c in " -_"
                ).strip()

                # Ensure filename has an extension (browser UUIDs often lack one)
                _, ext = os.path.splitext(new_file)
                if not ext:
                    ext = ".zip"  # default to .zip for Bluebeam viewer downloads
                gdrive_filename = f"{project_name_clean}{ext}"

                # Google Drive upload
                if GDRIVE_AVAILABLE and should_use_gdrive():
                    try:
                        result = upload_and_cleanup(
                            local_path,
                            filename=gdrive_filename,
                            source="Bidplanroom",
                            delete_local=True,
                        )

                        if result:
                            lead["gdrive_file_id"] = result.get("file_id")
                            lead["gdrive_link"] = result.get("web_link")
                            lead["gdrive_download_link"] = result.get("download_link")
                            lead["download_link"] = result.get("web_link")
                            lead["storage_type"] = "gdrive"
                            log_status("  Uploaded to Google Drive")
                        else:
                            lead["local_file_path"] = f"/downloads/{new_file}"
                            lead["download_link"] = f"/downloads/{new_file}"
                            lead["storage_type"] = "local"
                    except Exception as e:
                        log_status(f"  GDrive error: {e}")
                        lead["local_file_path"] = f"/downloads/{new_file}"
                        lead["download_link"] = f"/downloads/{new_file}"
                        lead["storage_type"] = "local"
                else:
                    lead["local_file_path"] = f"/downloads/{new_file}"
                    lead["download_link"] = f"/downloads/{new_file}"
                    lead["storage_type"] = "local"
                    log_status(f"  Saved locally: /downloads/{new_file}")

                return True
            else:
                log_status("  No new files detected")
                return False

        except Exception as e:
            log_status(f"  Download error: {e}")
            return False

    # -- main scraping -------------------------------------------------------

    async def scrape_all_projects(self, max_projects=None):
        """
        Main scraping logic for Bidplanroom.

        Args:
            max_projects: Maximum number of projects to scrape (None for all)

        Returns:
            list: List of scraped leads
        """
        log_status("=" * 40)
        log_status("Starting Bidplanroom scrape")

        try:
            # 1. Setup browser
            await self._setup_browser()

            # 2. Navigate and login
            await self._page.goto(
                self.config.BASE_URL,
                wait_until="domcontentloaded",
                timeout=60000,
            )
            await asyncio.sleep(2)

            if not await self._check_login_status():
                if not await self._login():
                    log_status("Login failed - aborting")
                    return self.leads

            # 3. Get project rows
            projects = await self._get_project_rows()

            if max_projects:
                projects = projects[:max_projects]

            if not projects:
                log_status("No projects found in table")
                return self.leads

            log_status(f"Processing {len(projects)} projects...")

            # 4. Process each project
            for i, proj in enumerate(projects):
                proj_name = proj.get("name", "Unknown")[:30]
                log_status(f"\n[{i+1}/{len(projects)}] {proj_name}...")

                try:
                    # Skip past-due
                    if self._is_past_due(proj.get("due_date", "")):
                        log_status(f"  Skipping past-due: {proj_name}")
                        continue

                    # Click into project
                    if not await self._click_project_row(proj["index"]):
                        log_status("  Could not click project row")
                        continue

                    await asyncio.sleep(2)

                    # Extract details
                    details = await self._extract_project_details()

                    # Check sprinkler keywords
                    full_text = f"{details.get('name', '')} {details.get('description', '')}".lower()
                    sprinklered = any(kw in full_text for kw in self.config.SPRINKLER_KEYWORDS)

                    # Build lead
                    lead = {
                        "id": f"bidplanroom_{proj['index']}_{hash(details.get('name', '')) % 10000}",
                        "name": details.get("name") or proj.get("name", "N/A"),
                        "company": details.get("company", "N/A"),
                        "gc": details.get("company", "N/A"),
                        "contact_name": details.get("contact_name", "N/A"),
                        "contact_phone": details.get("contact_phone", ""),
                        "contact_email": details.get("contact_email", ""),
                        "location": proj.get("location", "N/A"),
                        "bid_date": proj.get("due_date", "N/A"),
                        "due_date": proj.get("due_date", "N/A"),
                        "description": details.get("description", ""),
                        "sprinklered": sprinklered,
                        "site": "Bidplanroom",
                        "source": "Bidplanroom",
                        "url": self._page.url,
                        "extracted_at": datetime.now().isoformat(),
                        "files_link": None,
                        "download_link": None,
                        "local_file_path": None,
                    }

                    # Download files
                    await self._download_project_files(lead)

                    self.leads.append(lead)
                    log_status(f"  Added lead: {lead['name'][:30]}")

                    # Navigate back
                    await self._page.go_back()
                    await asyncio.sleep(2)

                except Exception as e:
                    log_status(f"  Error processing project: {e}")
                    # Try to navigate back to base
                    try:
                        await self._page.goto(
                            self.config.BASE_URL,
                            wait_until="domcontentloaded",
                            timeout=30000,
                        )
                        await asyncio.sleep(2)
                    except Exception:
                        pass
                    continue

            log_status(f"\nBidplanroom scrape complete: {len(self.leads)} leads")
            return self.leads

        except Exception as e:
            log_status(f"Scrape error: {e}")
            traceback.print_exc()
            return self.leads
        finally:
            await self._close_browser()


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------
async def main():
    print("[BPR] Starting Bidplanroom scraper test...")

    scraper = BidplanroomScraper()
    leads = await scraper.scrape_all_projects(max_projects=3)

    print(f"\n[BPR] Scraped {len(leads)} leads:")
    for lead in leads:
        print(f"  - {lead['name'][:40]}: {lead['location']}")

    return leads


if __name__ == "__main__":
    asyncio.run(main())
