"""
Loyd Builds Better scraper - Playwright-based browser automation.
URL: https://www.loydbuildsbetter.com/bids

Squarespace site behind a paywall/login. Requires Squarespace member login
to access the bids page. Extracts project listings from the bids page and
follows document links (Dropbox, Google Drive, direct).
"""
import os
import sys
import asyncio
import platform
import re
from datetime import datetime, date

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import ScraperConfig, DATE_FORMATS

# Import Google Drive service
try:
    from services.google_drive import upload_and_cleanup, should_use_gdrive, is_authenticated, get_status
    GDRIVE_AVAILABLE = True
    print(f"[LBB] Google Drive module loaded. Available: {GDRIVE_AVAILABLE}")
except ImportError as e:
    GDRIVE_AVAILABLE = False
    print(f"[LBB] Google Drive module NOT available: {e}")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

_lbb_log_buffer = []


def get_lbb_logs():
    """Get and clear the log buffer."""
    global _lbb_log_buffer
    logs = _lbb_log_buffer.copy()
    _lbb_log_buffer = []
    return logs


def log_status(msg):
    """Log to both console and web UI."""
    global _lbb_log_buffer
    print(f"[LBB] {msg}", flush=True)
    _lbb_log_buffer.append(f"[LBB] {msg}")
    try:
        from services.scheduler import add_to_log
        add_to_log(f"[LBB] {msg}")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

class LoydBuildsBetterConfig(ScraperConfig):
    """Configuration for Loyd Builds Better scraper."""

    BASE_URL = "https://www.loydbuildsbetter.com/bids"

    # Login credentials (Squarespace member login)
    LOGIN_EMAIL = os.getenv("LOYD_LOGIN") or os.getenv("SITE_LOGIN", "")
    LOGIN_PASSWORD = os.getenv("LOYD_PW") or os.getenv("SITE_PW", "")

    # Squarespace login selectors (from browser DevTools)
    PAYWALL_LOGIN_BTN = "#sqs-paywall-page-root > button"
    LOGIN_EMAIL_SELECTOR = "#login-email"
    LOGIN_PASSWORD_SELECTOR = "#login-password"
    LOGIN_SUBMIT_SELECTOR = "#user-account-login-root > div > div > form > button > span"

    SPRINKLER_KEYWORDS = [
        'sprinkler', 'fire protection', 'fire alarm', 'fire suppression',
        'wet system', 'dry system', 'fppi', 'nfpa',
    ]


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------

class LoydBuildsBetterScraper:
    """
    Loyd Builds Better scraper using Playwright with persistent browser context.

    Features:
      - Public site (no login required)
      - Extracts project info from Squarespace block elements
      - Follows external document links (Dropbox, Google Drive, direct)
      - Playwright download handling for file acquisition
    """

    def __init__(self):
        self.config = LoydBuildsBetterConfig()
        self.leads = []
        self.download_dir = self.config.DOWNLOAD_DIR
        os.makedirs(self.download_dir, exist_ok=True)

        # Browser state
        self._playwright = None
        self._browser_context = None
        self._page = None

    # ------------------------------------------------------------------
    # Browser lifecycle
    # ------------------------------------------------------------------

    async def _launch_browser(self):
        """Launch Playwright persistent browser context."""
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()

        profile_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'playwright_profile',
        )
        os.makedirs(profile_dir, exist_ok=True)

        launch_args = [
            '--disable-blink-features=AutomationControlled',
            '--disable-dev-shm-usage',
            '--no-sandbox',
        ]
        # Add Pi-optimized browser args if on Pi 5
        pi_args = self.config.get_browser_args()
        if pi_args:
            launch_args = list(set(launch_args + pi_args))

        log_status(f"Launching browser (headless={self.config.HEADLESS})")

        launch_kwargs = dict(
            user_data_dir=profile_dir,
            headless=self.config.HEADLESS,
            args=launch_args,
            viewport={'width': self.config.VIEWPORT_WIDTH, 'height': self.config.VIEWPORT_HEIGHT},
            accept_downloads=True,
            ignore_https_errors=True,
        )
        chrome_path = self.config.get_chromium_executable()
        if chrome_path:
            launch_kwargs['executable_path'] = chrome_path

        self._browser_context = await self._playwright.chromium.launch_persistent_context(
            **launch_kwargs,
        )

        # Use existing page or create one
        if self._browser_context.pages:
            self._page = self._browser_context.pages[0]
        else:
            self._page = await self._browser_context.new_page()

        log_status("Browser launched")

    async def _close_browser(self):
        """Close browser gracefully."""
        try:
            if self._browser_context:
                await self._browser_context.close()
        except Exception:
            pass
        try:
            if self._playwright:
                await self._playwright.stop()
        except Exception:
            pass
        self._browser_context = None
        self._playwright = None
        self._page = None

    # ------------------------------------------------------------------
    # Navigation & Login
    # ------------------------------------------------------------------

    async def _navigate(self, url, max_retries=3):
        """Navigate to URL with retry logic."""
        for attempt in range(max_retries):
            try:
                log_status(f"Navigating to {url}" + (f" (retry {attempt})" if attempt else ""))
                await self._page.goto(url, wait_until='networkidle', timeout=60000)
                await asyncio.sleep(2)
                return True
            except Exception as e:
                log_status(f"Navigation failed (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt == max_retries - 1:
                    return False
                await asyncio.sleep(2 ** attempt)
        return False

    async def _is_paywall(self):
        """Check if the current page is behind the Squarespace paywall."""
        try:
            paywall = await self._page.query_selector(self.config.PAYWALL_LOGIN_BTN)
            if paywall:
                return True
            # Also check for common paywall indicators
            url = self._page.url
            if "/account/" in url or "login" in url:
                return True
            # Check page text for paywall message
            text = await self._page.evaluate('() => document.body.innerText')
            if "log in" in text.lower()[:500] and "member" in text.lower()[:500]:
                return True
        except Exception:
            pass
        return False

    async def _login(self):
        """
        Log in via the Squarespace member paywall.

        Steps:
        1. Click "Log in" button on the paywall page
        2. Fill email and password
        3. Click "Sign In"
        4. Wait for redirect back to bids page
        """
        if not self.config.LOGIN_EMAIL or not self.config.LOGIN_PASSWORD:
            log_status("No LOYD_LOGIN / LOYD_PW credentials configured")
            return False

        log_status("Paywall detected — logging in...")

        try:
            # Step 1: Click "Log in" button on paywall
            login_btn = await self._page.query_selector(self.config.PAYWALL_LOGIN_BTN)
            if login_btn:
                await login_btn.click()
                log_status("Clicked paywall 'Log in' button")
                await asyncio.sleep(3)
            else:
                # Maybe we're already on the login form
                log_status("No paywall button found, checking for login form...")

            # Step 2: Fill email
            try:
                await self._page.wait_for_selector(
                    self.config.LOGIN_EMAIL_SELECTOR, timeout=10000
                )
                await self._page.fill(self.config.LOGIN_EMAIL_SELECTOR, self.config.LOGIN_EMAIL)
                log_status(f"Entered email: {self.config.LOGIN_EMAIL}")
            except Exception as e:
                log_status(f"Could not fill email field: {e}")
                return False

            # Step 3: Fill password
            try:
                await self._page.fill(self.config.LOGIN_PASSWORD_SELECTOR, self.config.LOGIN_PASSWORD)
                log_status("Entered password")
            except Exception as e:
                log_status(f"Could not fill password field: {e}")
                return False

            # Step 4: Click Sign In
            await asyncio.sleep(0.5)
            try:
                submit = await self._page.wait_for_selector(
                    self.config.LOGIN_SUBMIT_SELECTOR, timeout=5000
                )
                if submit:
                    await submit.click()
                    log_status("Clicked 'Sign In'")
                else:
                    # Fallback: try pressing Enter
                    await self._page.keyboard.press("Enter")
                    log_status("Pressed Enter to submit")
            except Exception:
                # Fallback: press Enter in the password field
                await self._page.keyboard.press("Enter")
                log_status("Pressed Enter to submit (fallback)")

            # Wait for login to complete and page to redirect
            await asyncio.sleep(5)

            # Check if we're past the paywall
            current_url = self._page.url
            log_status(f"Post-login URL: {current_url}")

            if await self._is_paywall():
                log_status("Still on paywall after login attempt — login may have failed")
                # Take debug screenshot
                try:
                    debug_path = os.path.join(self.download_dir, 'lbb_login_failed.png')
                    await self._page.screenshot(path=debug_path)
                    log_status(f"Saved login debug screenshot: {debug_path}")
                except Exception:
                    pass
                return False

            log_status("Login successful!")
            return True

        except Exception as e:
            log_status(f"Login error: {e}")
            return False

    # ------------------------------------------------------------------
    # Project extraction
    # ------------------------------------------------------------------

    async def _extract_projects(self):
        """
        Extract project listings from the Squarespace bids page.

        The page uses Squarespace block elements. Each project typically has:
          - A heading (h2/h3/h4) with the project name
          - Paragraph text with location, dates, contact info
          - Links to external document hosting (Dropbox, Google Drive, etc.)

        Returns:
            list[dict]: Extracted project data
        """
        log_status("Extracting project blocks...")
        await asyncio.sleep(3)

        # Debug screenshot
        try:
            debug_path = os.path.join(self.download_dir, 'lbb_debug_page.png')
            await self._page.screenshot(path=debug_path, full_page=True)
            log_status(f"Saved debug screenshot to {debug_path}")
        except Exception as e:
            log_status(f"Screenshot failed: {e}")

        # Log page text for debugging
        try:
            page_text = await self._page.evaluate('() => document.body.innerText')
            log_status(f"Page text length: {len(page_text)}")
            log_status(f"First 500 chars: {page_text[:500].replace(chr(10), ' ')}")
        except Exception:
            pass

        # Extract projects via JavaScript
        projects = await self._page.evaluate(r'''() => {
            const results = [];

            // Squarespace uses yui-prefixed block IDs or sqs-block classes
            const blocks = document.querySelectorAll(
                'div[id^="block-yui"], div.sqs-block, div[class*="sqs-block"]'
            );

            blocks.forEach((block, index) => {
                const text = block.textContent || '';

                // Must contain view/document/bid keywords and be substantial
                const hasKeyword = /view|document|bid|plan|drawing/i.test(text);
                if (!hasKeyword || text.length < 50) return;

                // Find a heading element for the project name
                const heading = block.querySelector('h2 strong, h3 strong, h4 strong, h2, h3, h4');
                const name = heading ? heading.textContent.trim() : '';
                if (!name || name.length < 3) return;

                // Extract paragraph details
                let location = '';
                let dueDate = '';
                let contactEmail = '';
                let description = '';

                const paragraphs = block.querySelectorAll('p');
                const allParagraphText = [];

                paragraphs.forEach(p => {
                    const pText = (p.textContent || '').trim();
                    if (!pText) return;
                    allParagraphText.push(pText);

                    // Due date patterns
                    const duePatterns = [
                        /(?:due|bid\s*(?:date|due)?)\s*[:]\s*(.+?)(?:\n|$)/i,
                        /(\d{1,2}\/\d{1,2}\/\d{2,4})/,
                        /(\w+\s+\d{1,2},?\s+\d{4})/,
                    ];
                    if (!dueDate) {
                        for (const pat of duePatterns) {
                            const m = pText.match(pat);
                            if (m) { dueDate = m[1].trim(); break; }
                        }
                    }

                    // Email from mailto link
                    if (!contactEmail) {
                        const emailLink = p.querySelector('a[href^="mailto:"]');
                        if (emailLink) {
                            contactEmail = emailLink.href.replace('mailto:', '').split('?')[0];
                        }
                    }

                    // Location heuristic: line containing city/state pattern
                    if (!location) {
                        const locMatch = pText.match(/([A-Z][\w\s]+,\s*[A-Z]{2}(?:\s+\d{5})?)/);
                        if (locMatch) location = locMatch[1].trim();
                    }
                });

                // Fallback location: first short paragraph line
                if (!location && allParagraphText.length > 0) {
                    const firstLine = allParagraphText[0].split('\n')[0].trim();
                    if (firstLine.length < 100 && firstLine.length > 3) {
                        location = firstLine;
                    }
                }

                description = allParagraphText.join(' ').substring(0, 500);

                // Find document links (Dropbox, Google Drive, direct file links, etc.)
                const links = block.querySelectorAll('a[href]');
                const docLinks = [];
                let primaryLink = '';

                links.forEach(a => {
                    const href = a.href || '';
                    const linkText = (a.textContent || '').toLowerCase();
                    const isDocLink = (
                        /dropbox|drive\.google|docs\.google|sharepoint|box\.com|onedrive/i.test(href) ||
                        /\.pdf|\.zip|\.dwg|\.rvt/i.test(href) ||
                        /view|document|download|plan|file|drawing/i.test(linkText)
                    );
                    if (isDocLink && href.startsWith('http')) {
                        docLinks.push(href);
                        if (!primaryLink) primaryLink = href;
                    }
                });

                results.push({
                    index: index,
                    blockId: block.id || 'block_' + index,
                    name: name,
                    location: location,
                    due_date: dueDate,
                    contact_email: contactEmail,
                    description: description,
                    doc_links: docLinks,
                    primary_link: primaryLink,
                });
            });

            return results;
        }''')

        log_status(f"Found {len(projects)} project blocks")
        return projects or []

    # ------------------------------------------------------------------
    # Date helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_date(date_str):
        """Parse a date string using known formats."""
        if not date_str or date_str == 'N/A':
            return None
        for fmt in DATE_FORMATS:
            try:
                return datetime.strptime(date_str.strip(), fmt).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _is_past_due(date_str):
        """Check whether a project's due date is in the past."""
        parsed = LoydBuildsBetterScraper._parse_date(date_str)
        if parsed:
            return parsed < date.today()
        return False

    # ------------------------------------------------------------------
    # Document downloading
    # ------------------------------------------------------------------

    async def _download_from_link(self, url, lead):
        """
        Download documents from an external link.

        Handles:
          - Direct file URLs (.pdf, .zip, etc.)
          - Dropbox shared links (append ?dl=1 for direct download)
          - Google Drive links (follow to download)
          - Other links (navigate and look for download buttons)

        Args:
            url: Document URL to download from
            lead: Lead dict to update with file info

        Returns:
            bool: True if download succeeded
        """
        if not url:
            return False

        log_status(f"   Downloading from: {url[:80]}...")

        try:
            files_before = set(os.listdir(self.download_dir)) if os.path.exists(self.download_dir) else set()

            # --- Direct file URL ---
            if re.search(r'\.(pdf|zip|rar|dwg|rvt|doc|docx|xls|xlsx)(\?|$)', url, re.I):
                log_status("   Direct file link detected")
                try:
                    async with self._page.expect_download(timeout=60000) as dl_info:
                        await self._page.evaluate(f'() => {{ window.location.href = "{url}"; }}')
                    download = await dl_info.value
                    dest = os.path.join(self.download_dir, download.suggested_filename or 'download')
                    await download.save_as(dest)
                    return await self._handle_downloaded_file(dest, lead)
                except Exception as e:
                    log_status(f"   Direct download failed: {e}")

            # --- Dropbox ---
            if 'dropbox.com' in url:
                # Force direct download
                dl_url = re.sub(r'[?&]dl=0', '', url)
                dl_url += ('&' if '?' in dl_url else '?') + 'dl=1'
                log_status("   Dropbox link - forcing direct download")
                try:
                    async with self._page.expect_download(timeout=60000) as dl_info:
                        await self._page.evaluate(f'() => {{ window.location.href = "{dl_url}"; }}')
                    download = await dl_info.value
                    dest = os.path.join(self.download_dir, download.suggested_filename or 'dropbox_download')
                    await download.save_as(dest)
                    return await self._handle_downloaded_file(dest, lead)
                except Exception as e:
                    log_status(f"   Dropbox download failed: {e}")

            # --- Google Drive ---
            if 'drive.google.com' in url or 'docs.google.com' in url:
                log_status("   Google Drive link - storing link directly")
                lead['files_link'] = url
                lead['download_link'] = url
                lead['storage_type'] = 'external_link'
                return True

            # --- Generic: open page and look for download button ---
            log_status("   Opening link to find download button...")
            new_page = await self._browser_context.new_page()
            try:
                await new_page.goto(url, wait_until='domcontentloaded', timeout=30000)
                await asyncio.sleep(3)

                # Try clicking a download button
                download_clicked = await new_page.evaluate(r'''() => {
                    const btns = document.querySelectorAll('button, a, [role="button"]');
                    for (const btn of btns) {
                        const text = (btn.textContent || '').toLowerCase();
                        const ariaLabel = (btn.getAttribute('aria-label') || '').toLowerCase();
                        if (text.includes('download') || ariaLabel.includes('download')) {
                            btn.click();
                            return true;
                        }
                    }
                    return false;
                }''')

                if download_clicked:
                    log_status("   Download button clicked, waiting for file...")
                    await asyncio.sleep(15)

                    # Check for new files
                    files_after = set(os.listdir(self.download_dir))
                    new_files = files_after - files_before
                    if new_files:
                        newest = sorted(new_files, key=lambda f: os.path.getmtime(
                            os.path.join(self.download_dir, f)))[-1]
                        dest = os.path.join(self.download_dir, newest)
                        return await self._handle_downloaded_file(dest, lead)
                else:
                    log_status("   No download button found - storing link")
                    lead['files_link'] = url
                    lead['download_link'] = url
                    lead['storage_type'] = 'external_link'
                    return True

            except Exception as e:
                log_status(f"   Page navigation failed: {e}")
                lead['files_link'] = url
                lead['download_link'] = url
                lead['storage_type'] = 'external_link'
                return True
            finally:
                await new_page.close()

        except Exception as e:
            log_status(f"   Download error: {e}")
            # Still store the link even if download failed
            if url:
                lead['files_link'] = url
                lead['download_link'] = url
                lead['storage_type'] = 'external_link'
            return False

        return False

    async def _handle_downloaded_file(self, local_path, lead):
        """
        Process a downloaded file: upload to Google Drive or store locally.

        Args:
            local_path: Path to the downloaded file
            lead: Lead dict to update

        Returns:
            bool: True if handled successfully
        """
        filename = os.path.basename(local_path)
        log_status(f"   Downloaded: {filename}")

        if GDRIVE_AVAILABLE and should_use_gdrive():
            try:
                log_status("   Uploading to Google Drive...")
                name_clean = "".join(
                    c for c in lead.get('name', 'project')[:50]
                    if c.isalnum() or c in ' -_'
                ).strip()
                gdrive_filename = f"{name_clean}_{filename}" if name_clean else filename

                result = upload_and_cleanup(
                    local_path,
                    filename=gdrive_filename,
                    source='LoydBuildsBetter',
                    delete_local=True,
                )
                if result:
                    lead['gdrive_file_id'] = result.get('file_id')
                    lead['gdrive_link'] = result.get('web_link')
                    lead['download_link'] = result.get('web_link')
                    lead['storage_type'] = 'gdrive'
                    log_status("   Uploaded to Google Drive")
                    return True
            except Exception as e:
                log_status(f"   GDrive upload error: {e}")

        # Fallback: local storage
        lead['local_file_path'] = f"/downloads/{filename}"
        lead['download_link'] = f"/downloads/{filename}"
        lead['storage_type'] = 'local'
        log_status(f"   Saved locally: /downloads/{filename}")
        return True

    # ------------------------------------------------------------------
    # Main scrape
    # ------------------------------------------------------------------

    async def scrape_all_projects(self, max_projects=None):
        """
        Main scraping logic for Loyd Builds Better.

        Args:
            max_projects: Maximum number of projects to scrape (None = all)

        Returns:
            list[dict]: Scraped leads
        """
        log_status("Starting Loyd Builds Better scrape...")
        self.leads = []

        try:
            await self._launch_browser()

            # Navigate to bids page
            if not await self._navigate(self.config.BASE_URL):
                log_status("Failed to navigate to Loyd Builds Better")
                return self.leads

            # Check for paywall/login requirement
            if await self._is_paywall():
                success = await self._login()
                if not success:
                    log_status("Could not log in to Loyd Builds Better — aborting")
                    return self.leads

                # Re-navigate to bids page after login
                if not await self._navigate(self.config.BASE_URL):
                    log_status("Failed to navigate to bids page after login")
                    return self.leads

                # Check paywall again
                if await self._is_paywall():
                    log_status("Still behind paywall after login — aborting")
                    return self.leads

            # Extract project blocks
            projects = await self._extract_projects()

            if max_projects:
                projects = projects[:max_projects]

            log_status(f"Processing {len(projects)} projects...")

            for i, proj in enumerate(projects):
                proj_name = proj.get('name', 'Unknown')[:40]
                log_status(f"Project {i + 1}/{len(projects)}: {proj_name}")

                try:
                    due_date_str = proj.get('due_date', '')

                    # Skip past-due projects
                    if self._is_past_due(due_date_str):
                        log_status(f"   Skipping past-due project: {due_date_str}")
                        continue

                    # Check for sprinkler keywords
                    full_text = ' '.join([
                        proj.get('name', ''),
                        proj.get('location', ''),
                        proj.get('description', ''),
                    ]).lower()
                    sprinklered = any(kw.lower() in full_text for kw in self.config.SPRINKLER_KEYWORDS)

                    # Build lead
                    name = proj.get('name', 'N/A')
                    lead = {
                        'id': f"loydbuildsbetter_{hash(name) % 100000}",
                        'name': name,
                        'company': 'Loyd Builds Better',
                        'gc': 'Loyd Builds Better',
                        'contact_name': 'N/A',
                        'contact_phone': '',
                        'contact_email': proj.get('contact_email', ''),
                        'location': proj.get('location', 'N/A'),
                        'bid_date': due_date_str or 'N/A',
                        'due_date': due_date_str or 'N/A',
                        'description': proj.get('description', ''),
                        'sprinklered': sprinklered,
                        'site': 'LoydBuildsBetter',
                        'source': 'LoydBuildsBetter',
                        'url': self.config.BASE_URL,
                        'extracted_at': datetime.now().isoformat(),
                        'files_link': proj.get('primary_link', ''),
                        'download_link': None,
                        'local_file_path': None,
                        'storage_type': None,
                    }

                    # Download documents from the primary link
                    primary = proj.get('primary_link', '')
                    if primary:
                        await self._download_from_link(primary, lead)

                    # If there are additional doc links, store them
                    doc_links = proj.get('doc_links', [])
                    if len(doc_links) > 1:
                        lead['additional_doc_links'] = doc_links[1:]

                    self.leads.append(lead)
                    log_status(f"   Added lead: {lead['name'][:40]}")

                except Exception as e:
                    log_status(f"   Error processing project: {e}")
                    continue

                # Small delay between projects
                await asyncio.sleep(0.5)

            log_status(f"Loyd Builds Better scrape complete: {len(self.leads)} leads extracted")
            return self.leads

        except Exception as e:
            log_status(f"Scrape error: {e}")
            import traceback
            traceback.print_exc()
            return self.leads
        finally:
            await self._close_browser()


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------

async def main():
    """Main entry point for standalone testing."""
    print("[LBB] Starting Loyd Builds Better scraper test...")
    scraper = LoydBuildsBetterScraper()
    leads = await scraper.scrape_all_projects(max_projects=3)

    print(f"\n[LBB] Scraped {len(leads)} leads:")
    for lead in leads:
        print(f"  - {lead['name'][:40]}: {lead['location']}")

    return leads


if __name__ == "__main__":
    asyncio.run(main())
