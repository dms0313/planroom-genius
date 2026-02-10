"""
BuildingConnected scraper - Extract data from table view (faster approach)
Scrapes directly from the bid board table without clicking into each project
Uses Playwright for reliable browser automation.
"""
import os
import platform
import asyncio
import json
import sys
from datetime import datetime
from playwright.async_api import async_playwright

# Import shared config for cross-platform support
try:
    from config import ScraperConfig, GoogleDriveConfig
except ImportError:
    ScraperConfig = None
    GoogleDriveConfig = None

# Import Google Drive service
try:
    from services.google_drive import upload_and_cleanup, should_use_gdrive, is_authenticated, get_status, authenticate
    GDRIVE_AVAILABLE = True
    print(f"[BC] Google Drive module loaded. Available: {GDRIVE_AVAILABLE}")
except ImportError as e:
    GDRIVE_AVAILABLE = False
    print(f"[BC] Google Drive module NOT available: {e}")

# Global log buffer that scheduler can access
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

    # Also try to add to scheduler's log
    try:
        from services.scheduler import add_to_log
        add_to_log(f"[BC] {msg}")
    except:
        pass


class BuildingConnectedTableScraper:
    """Scrape BuildingConnected data directly from table view"""

    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.leads = []

        # Use shared config if available, otherwise use defaults
        if ScraperConfig:
            self.config = ScraperConfig()
            self.download_dir = self.config.DOWNLOAD_DIR
            self.chrome_user_data = self.config.CHROME_USER_DATA_DIR
            self.profile_name = self.config.CHROME_PROFILE_NAME
            self.headless = self.config.HEADLESS
        else:
            # Fallback defaults with platform detection
            self.download_dir = os.path.join(os.path.dirname(__file__), 'downloads')
            if platform.system() == 'Linux':
                # Linux / Raspberry Pi - use home directory detection (any username)
                home_dir = os.path.expanduser("~")
                self.chrome_user_data = os.getenv(
                    "CHROME_USER_DATA_DIR",
                    os.path.join(home_dir, ".config", "chromium")
                )
                self.profile_name = os.getenv("CHROME_PROFILE_NAME", "Default")
                self.headless = os.getenv("HEADLESS", "true").lower() == "true"
            else:
                # Windows / macOS defaults
                self.chrome_user_data = os.getenv(
                    "CHROME_USER_DATA_DIR",
                    os.path.join(
                        os.path.dirname(os.path.abspath(__file__)),
                        "planroom_agent_storage_browser-use-user-data-dir-persistent"
                    )
                )
                self.profile_name = os.getenv("CHROME_PROFILE_NAME", "Profile 2")
                self.headless = os.getenv("HEADLESS", "false").lower() == "true"

        os.makedirs(self.download_dir, exist_ok=True)

    async def setup_browser(self):
        """Initialize browser with Playwright"""
        # Use a Playwright-specific profile directory
        playwright_profile = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "playwright_profile"
        )

        print(f"\n======== BROWSER CONFIG (Playwright) ========")
        print(f"Platform:        {platform.system()} ({platform.machine()})")
        print(f"Profile Dir:     {playwright_profile}")
        print(f"Headless:        {self.headless}")
        print("==============================================\n")

        print("[BC] Starting Playwright...")
        self.playwright = await async_playwright().start()

        print("[BC] Launching browser...")

        # Use persistent context to maintain login session
        self.context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=playwright_profile,
            headless=self.headless,
            viewport={'width': 1920, 'height': 1080},
            accept_downloads=True,
            downloads_path=self.download_dir,
            args=[
                '--no-sandbox',
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
            ],
            ignore_default_args=['--enable-automation'],
        )

        # Get the first page or create one
        if self.context.pages:
            self.page = self.context.pages[0]
        else:
            self.page = await self.context.new_page()

        print("[BC] Browser initialized successfully")
        print("[BC] NOTE: If not logged in, you'll need to log in manually once.")

    async def navigate_to_pipeline(self):
        """Navigate to BuildingConnected bid board"""
        log_status("Navigating to pipeline...")
        try:
            await self.page.goto(
                'https://app.buildingconnected.com/opportunities/pipeline',
                wait_until='domcontentloaded',
                timeout=60000
            )
        except Exception as e:
            log_status(f"Navigation error: {e}")

        # Check if we're on the login page
        current_url = self.page.url
        log_status(f"Current URL: {current_url[:60]}...")

        if 'login' in current_url or 'signin' in current_url:
            log_status("=" * 40)
            log_status("LOGIN REQUIRED")
            log_status("Please log in to BuildingConnected in the browser window")
            log_status("=" * 40)

            # Wait for user to log in (check every 3 seconds for up to 5 minutes)
            max_wait = 300  # 5 minutes
            waited = 0
            while waited < max_wait:
                await asyncio.sleep(3)
                waited += 3
                current_url = self.page.url
                if 'login' not in current_url and 'signin' not in current_url:
                    log_status("Login detected! Continuing...")
                    break
                if waited % 15 == 0:
                    log_status(f"Still waiting for login... ({waited}s)")

            # Check one more time
            current_url = self.page.url
            if 'login' in current_url or 'signin' in current_url:
                log_status("ERROR: Login timeout - please try again")
                raise Exception("Login timeout")

        log_status("Waiting for virtual table to load...")
        await asyncio.sleep(3)

        log_status("Pipeline loaded successfully")

    async def sort_by_due_date(self):
        """Click the due date column header to sort by due date (current projects first)"""
        try:
            # Look for the due date column header - it's usually the 3rd column
            date_header_selectors = [
                'div[class*="headerRow"] > div:nth-child(3)',
                'div[class*="ReactVirtualized__Table__headerRow"] > div:nth-child(3)',
            ]

            for selector in date_header_selectors:
                try:
                    date_header = await self.page.query_selector(selector)
                    if date_header:
                        await date_header.click()
                        print("[BC] Waiting for table to re-sort...")
                        await asyncio.sleep(3)
                        print("[BC] Sorted by due date")
                        return
                except:
                    continue

            print("[BC] Could not sort - continuing")

        except Exception as e:
            print(f"[BC] Sort failed: {e}")

    async def get_visible_rows(self):
        """Get currently visible rows from the ReactVirtualized table"""
        # Wait for the table to load
        try:
            await self.page.wait_for_selector('.ReactVirtualized__Grid', timeout=10000)
            print("[BC] Found ReactVirtualized grid")
        except Exception as e:
            print(f"[BC] ERROR: Could not find ReactVirtualized grid: {e}")
            try:
                debug_path = os.path.join(self.download_dir, 'bc_no_grid_debug.png')
                await self.page.screenshot(path=debug_path, full_page=True)
                print(f"[BC] Saved debug screenshot to: {debug_path}")
            except:
                pass
            return []

        # Get rows - they are direct children of the scroll container
        rows = await self.page.query_selector_all('.ReactVirtualized__Table__Grid > div > div')

        if not rows or len(rows) == 0:
            print("[BC] WARNING: No row elements found")
            return []

        print(f"[BC] Found {len(rows)} rows")
        return rows

    async def scroll_table(self, pixels=400):
        """Scroll the table down by specified pixels"""
        await self.page.evaluate(f'''() => {{
            const grid = document.querySelector('.ReactVirtualized__Grid');
            if (grid) {{ grid.scrollTop += {pixels}; }}
        }}''')
        await asyncio.sleep(1.5)

    async def get_scroll_position(self):
        """Get current scroll position and max scroll"""
        return await self.page.evaluate('''() => {
            const grid = document.querySelector('.ReactVirtualized__Grid');
            if (grid) {
                return {
                    scrollTop: grid.scrollTop,
                    scrollHeight: grid.scrollHeight,
                    clientHeight: grid.clientHeight
                };
            }
            return null;
        }''')

    def _snapshot_download_dir(self):
        """Capture filenames and mtimes for download detection."""
        if not os.path.exists(self.download_dir):
            return {}
        snapshot = {}
        for name in os.listdir(self.download_dir):
            path = os.path.join(self.download_dir, name)
            if os.path.isfile(path):
                try:
                    snapshot[name] = os.path.getmtime(path)
                except Exception:
                    continue
        return snapshot

    def _pick_latest_download(self, before_snapshot, after_snapshot):
        """Pick newest file that is new or updated (handles overwrite)."""
        candidates = []
        for name, mtime in after_snapshot.items():
            if name.endswith(('.crdownload', '.tmp', '.part')):
                continue
            if name not in before_snapshot or mtime > before_snapshot.get(name, 0):
                candidates.append((name, mtime))
        if not candidates:
            return None
        candidates.sort(key=lambda x: x[1])
        return candidates[-1][0]

    def _rename_download(self, filename, project_name):
        """Rename downloaded file to a unique, project-specific filename."""
        old_path = os.path.join(self.download_dir, filename)
        if not os.path.exists(old_path):
            return filename, old_path

        safe_name = "".join(c for c in project_name[:60] if c.isalnum() or c in ' -_').strip()
        if not safe_name:
            safe_name = "project"
        # Remove timestamp to prevent duplicate uploads to GDrive
        # timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base, ext = os.path.splitext(filename)
        # Default to .zip if no extension (BuildingConnected always downloads ZIPs)
        if not ext:
            ext = '.zip'
        new_name = f"{safe_name}{ext}"
        new_path = os.path.join(self.download_dir, new_name)

        counter = 1
        while os.path.exists(new_path):
            new_name = f"{safe_name}_{counter}{ext}"
            new_path = os.path.join(self.download_dir, new_name)
            counter += 1

        try:
            os.rename(old_path, new_path)
            return new_name, new_path
        except Exception:
            return filename, old_path

    def _derive_project_url_from_href(self, href):
        if not href or '/opportunities/' not in href:
            return None, None
        project_id = href.split('/opportunities/')[1].split('/')[0]
        base_url = href.split('/opportunities/')[0]
        project_url = f"{base_url}/opportunities/{project_id}/details"
        return project_url, project_id

    async def get_sidebar_project_href(self):
        """Return a project-related href from the opened sidebar."""
        try:
            return await self.page.evaluate('''() => {
                const panel =
                    document.querySelector('div[class*="view__RootDiv"]') ||
                    document.querySelector('div[class*="quickLinksContainer"]')?.closest('div');
                if (!panel) return null;
                const filesLink = panel.querySelector('a[href^="/opportunities/"][href*="/files"]') ||
                                  panel.querySelector('a[href*="/opportunities/"][href*="/files"]');
                if (filesLink && filesLink.href) return filesLink.href;
                const detailLink = panel.querySelector('a[href^="/opportunities/"]') || panel.querySelector('a[href*="/opportunities/"]');
                if (detailLink && detailLink.href) return detailLink.href;
                return null;
            }''')
        except Exception:
            return None

    async def handle_large_file_prompt(self):
        """Handle 'large file size' confirmation modal and 'download started' popup if they appear."""
        try:
            # Use aggressive JavaScript-based popup dismissal that doesn't rely on specific selectors
            dismissed = await self.page.evaluate('''() => {
                // Helper to check if element is visible
                const isVisible = (el) => {
                    if (!el) return false;
                    const style = window.getComputedStyle(el);
                    return el.offsetParent !== null && 
                           style.display !== 'none' && 
                           style.visibility !== 'hidden' &&
                           style.opacity !== '0';
                };
                
                // Helper to find and click a button with matching text
                const clickButtonWithText = (container, textPatterns) => {
                    const buttons = container.querySelectorAll('button, [role="button"], div[class*="button"], span[class*="button"]');
                    for (const btn of buttons) {
                        const text = (btn.textContent || '').trim().toLowerCase();
                        for (const pattern of textPatterns) {
                            if (text.includes(pattern.toLowerCase())) {
                                btn.click();
                                return true;
                            }
                        }
                    }
                    return false;
                };
                
                // Strategy 1: Find any overlay/modal with confirm-like buttons
                // Look for high z-index elements that are likely modals
                const allDivs = Array.from(document.querySelectorAll('body > div'));
                const overlays = allDivs.filter(el => {
                    if (!isVisible(el)) return false;
                    const style = window.getComputedStyle(el);
                    const zIndex = parseInt(style.zIndex) || 0;
                    // Look for high z-index overlays (modals typically have z-index > 1000)
                    return zIndex > 100 || style.position === 'fixed' || style.position === 'absolute';
                });
                
                // Confirm button patterns to look for
                const confirmPatterns = ['ok, go for it', 'ok go for it', 'ok', 'continue', 'yes', 'confirm', 'proceed', 'download', 'got it', 'dismiss'];
                const dismissPatterns = ['close', 'x', '×', 'cancel', 'no thanks'];
                
                // Check each overlay for dismiss-able content
                for (const overlay of overlays) {
                    const text = (overlay.textContent || '').toLowerCase();
                    
                    // Check if this looks like a download/size warning popup
                    const isPopup = text.includes('download') || 
                                   text.includes('heads up') ||
                                   text.includes('large') ||
                                   text.includes('size') ||
                                   text.includes('lot of data') ||
                                   text.includes('started') ||
                                   text.includes('warning');
                    
                    if (isPopup) {
                        // Try to click confirm button first
                        if (clickButtonWithText(overlay, confirmPatterns)) {
                            return true;
                        }
                        // Try dismiss patterns as fallback
                        if (clickButtonWithText(overlay, dismissPatterns)) {
                            return true;
                        }
                        // Last resort: try clicking any button in the overlay
                        const anyButton = overlay.querySelector('button');
                        if (anyButton && isVisible(anyButton)) {
                            anyButton.click();
                            return true;
                        }
                    }
                }
                
                // Strategy 2: Specific text-based search across entire document
                const allButtons = Array.from(document.querySelectorAll('button, [role="button"]'));
                for (const btn of allButtons) {
                    if (!isVisible(btn)) continue;
                    const text = (btn.textContent || '').trim().toLowerCase();
                    // "OK, go for it!" is the specific BC button
                    if (text === 'ok, go for it!' || text.includes('go for it')) {
                        btn.click();
                        return true;
                    }
                }
                
                // Strategy 3: Find close/X buttons on visible overlays
                for (const overlay of overlays) {
                    const closeButtons = overlay.querySelectorAll('[aria-label*="close"], [aria-label*="Close"], [aria-label*="dismiss"]');
                    for (const closeBtn of closeButtons) {
                        if (isVisible(closeBtn)) {
                            closeBtn.click();
                            return true;
                        }
                    }
                    // Look for X button (often styled differently)
                    const xButtons = overlay.querySelectorAll('button');
                    for (const xBtn of xButtons) {
                        const text = (xBtn.textContent || '').trim();
                        if (text === '×' || text === 'x' || text === 'X' || text === '✕') {
                            xBtn.click();
                            return true;
                        }
                    }
                }
                
                return false;
            }''')
            
            if dismissed:
                print("[BC]    Popup dismissed via JavaScript")
                return True
            
            # Fallback: Try Playwright locators with various text patterns
            dismiss_locators = [
                self.page.get_by_text("OK, go for it!", exact=True),
                self.page.get_by_text("OK, go for it!"),
                self.page.get_by_role("button", name="OK, go for it!"),
                self.page.get_by_text("Got it"),
                self.page.get_by_text("Continue"),
                self.page.get_by_text("Dismiss"),
                self.page.locator('button:has-text("OK")'),
            ]
            
            for loc in dismiss_locators:
                try:
                    if await loc.count() > 0:
                        await loc.first.click(force=True, timeout=1000)
                        print("[BC]    Popup dismissed via locator")
                        return True
                except:
                    continue
            
            return False
        except Exception as e:
            print(f"[BC]    Popup handler error: {e}")
            return False
    
    async def start_popup_watcher(self):
        """Start a background task that continuously monitors and dismisses popups."""
        async def popup_watcher():
            while True:
                try:
                    await asyncio.sleep(0.5)  # Check every 500ms
                    if self.page and not self.page.is_closed():
                        await self.dismiss_any_popups()
                except Exception:
                    pass  # Silently continue if page is closed or error occurs
        
        self._popup_watcher_task = asyncio.create_task(popup_watcher())
    
    async def stop_popup_watcher(self):
        """Stop the background popup watcher."""
        if hasattr(self, '_popup_watcher_task'):
            self._popup_watcher_task.cancel()
            try:
                await self._popup_watcher_task
            except asyncio.CancelledError:
                pass
    
    async def dismiss_any_popups(self):
        """Quickly check for and dismiss any visible popups."""
        try:
            await self.page.evaluate('''() => {
                const isVisible = (el) => {
                    if (!el) return false;
                    const style = window.getComputedStyle(el);
                    return el.offsetParent !== null && 
                           style.display !== 'none' && 
                           style.visibility !== 'hidden';
                };
                
                // Look for overlay divs that might be popups
                const overlays = Array.from(document.querySelectorAll('body > div')).filter(el => {
                    if (!isVisible(el)) return false;
                    const style = window.getComputedStyle(el);
                    const zIndex = parseInt(style.zIndex) || 0;
                    return zIndex > 100;
                });
                
                const popupKeywords = ['download', 'heads up', 'large', 'size', 'warning', 'started', 'lot of data'];
                const confirmKeywords = ['ok', 'continue', 'yes', 'confirm', 'got it', 'dismiss', 'go for it'];
                
                for (const overlay of overlays) {
                    const text = (overlay.textContent || '').toLowerCase();
                    const isPopup = popupKeywords.some(kw => text.includes(kw));
                    
                    if (isPopup) {
                        const buttons = overlay.querySelectorAll('button, [role="button"]');
                        for (const btn of buttons) {
                            const btnText = (btn.textContent || '').toLowerCase();
                            if (confirmKeywords.some(kw => btnText.includes(kw))) {
                                btn.click();
                                return;
                            }
                        }
                        // Click first button as fallback
                        if (buttons.length > 0) {
                            buttons[0].click();
                            return;
                        }
                    }
                }
            }''')
        except:
            pass

    async def open_project_sidebar(self, project_name, max_scroll_attempts=25):
        """Open the project side panel by clicking the project name in the table."""
        try:
            await self.page.goto(
                'https://app.buildingconnected.com/opportunities/pipeline',
                wait_until='domcontentloaded',
                timeout=60000
            )
            await asyncio.sleep(2)
            await self.page.wait_for_selector('.ReactVirtualized__Grid', timeout=10000)
        except Exception as e:
            print(f"[BC]    Could not load pipeline for sidebar: {e}")
            return False

        # Reset scroll to top
        try:
            await self.page.evaluate('''() => {
                const grid = document.querySelector('.ReactVirtualized__Grid');
                if (grid) grid.scrollTop = 0;
            }''')
            await asyncio.sleep(0.5)
        except:
            pass

        name_snippet = (project_name or "").strip()[:24]
        if not name_snippet:
            return False

        for _ in range(max_scroll_attempts):
            clicked = await self.page.evaluate('''(name) => {
                const rows = document.querySelectorAll('.ReactVirtualized__Grid > div > div');
                for (const row of rows) {
                    const text = row.textContent || '';
                    if (text.includes(name)) {
                        const link =
                            row.querySelector('a.nameCell-0-1-308.sidePanelTextHighlight-0-1-314') ||
                            row.querySelector('a[href^="/opportunities/"]') ||
                            row.querySelector('a[href*="/opportunities/"]');
                        const nameEl =
                            row.querySelector('a > div.projectName-0-1-301.sidePanelTextHighlight-0-1-314') ||
                            row.querySelector('a > div[class*="projectName"]') ||
                            row.querySelector('div[class*="projectName"]');
                        if (link) {
                            link.click();
                            return true;
                        }
                        if (nameEl) {
                            nameEl.click();
                            return true;
                        }
                        row.click();
                        return true;
                    }
                }
                return false;
            }''', name_snippet)

            if clicked:
                try:
                    await self.page.wait_for_selector('div[class*="quickLinksContainer"]', timeout=8000)
                except:
                    pass
                return True

            # Scroll down to find the project
            await self.page.evaluate('''() => {
                const grid = document.querySelector('.ReactVirtualized__Grid');
                if (grid) grid.scrollTop += 350;
            }''')
            await asyncio.sleep(0.7)

        print(f"[BC]    Could not open sidebar for: {project_name[:40]}")
        return False

    async def open_sidebar_from_row(self, row):
        """Open the sidebar by clicking a link or project name within a row element."""
        try:
            # Prefer clicking the name/row to avoid full navigation
            name_el = await row.query_selector('div[class*="projectName"]')
            if name_el:
                await name_el.click()
            else:
                try:
                    await row.click()
                except:
                    # Last resort: click link but prevent navigation
                    link = await row.query_selector('a[href^="/opportunities/"], a[href*="/opportunities/"]')
                    if link:
                        await self.page.evaluate('''(el) => {
                            if (!el) return;
                            el.addEventListener('click', (e) => e.preventDefault(), { once: true });
                            el.click();
                        }''', link)

            try:
                await self.page.wait_for_selector('div[class*="quickLinksContainer"]', timeout=8000)
            except:
                pass
            # If navigation happened, avoid poisoning the table context
            if '/opportunities/pipeline' not in (self.page.url or ''):
                try:
                    await self.page.go_back()
                except:
                    pass
                return False
            return True
        except Exception:
            return False

    def is_project_expired(self, date_str):
        """Check if a project's bid date has passed"""
        if not date_str or date_str in ['N/A', 'TBD', 'Unknown']:
            return False

        try:
            from datetime import datetime
            # Try parsing common date formats
            for fmt in ['%m/%d/%Y', '%m/%d/%y', '%Y-%m-%d', '%b %d, %Y']:
                try:
                    bid_date = datetime.strptime(date_str.strip(), fmt)
                    today = datetime.now()
                    today = today.replace(hour=0, minute=0, second=0, microsecond=0)
                    return bid_date < today
                except ValueError:
                    continue
            return False
        except:
            return False

    async def extract_row_data(self, row, index, click_for_url=False):
        """Extract data from a single table row using JavaScript (Playwright)

        Args:
            row: The row element
            index: Row index for logging
            click_for_url: If True, click the row to reveal details panel and get URL
        """
        try:
            # Use JavaScript to extract all data at once using positional selectors
            # Based on BuildingConnected table structure (from user's CSS path):
            # Row > inner div wrapper > columns (div:nth-child(1), div:nth-child(2), etc.)
            # - Column 1: Name (with link)
            # - Column 2: Status/type
            # - Column 3: Due Date
            # - Column 4: Location
            # - Column 5: Company/Contact
            data = await row.evaluate('''(row) => {
                const result = {
                    name: '',
                    url: '',
                    bid_date: '',
                    bid_time: '',
                    city: '',
                    state: '',
                    company: '',
                    contact: '',
                    has_budget: false
                };

                // Row structure: row > div (wrapper) > div columns
                // Get the inner wrapper first
                let wrapper = row.querySelector(':scope > div');
                if (!wrapper) wrapper = row;

                // Get columns from the wrapper
                const cols = wrapper.querySelectorAll(':scope > div');

                // Column 1: Name and URL (has the link)
                if (cols.length > 0) {
                    const nameCol = cols[0];
                    // Get URL from any link in the row (search whole row, not just name col)
                    let link = row.querySelector('a[href^="/opportunities/"]');
                    if (!link) link = row.querySelector('a[href*="/opportunities/"]');
                    if (!link) link = nameCol.querySelector('a');
                    if (link) {
                        const href = link.getAttribute('href');
                        if (href) result.url = href;
                        // Name is typically in a span inside the link
                        const nameSpan = link.querySelector('span');
                        if (nameSpan) result.name = nameSpan.textContent.trim();
                    }
                    // Fallback: get name from textWrapper
                    if (!result.name) {
                        const textWrapper = row.querySelector('div[class*="textWrapper"]');
                        if (textWrapper) result.name = textWrapper.textContent.trim();
                    }
                    // Fallback: first span in name column
                    if (!result.name) {
                        const firstSpan = nameCol.querySelector('span');
                        if (firstSpan) result.name = firstSpan.textContent.trim();
                    }

                    // Check for "Budget" badge in the name column
                    // Selector: span.Badge or span with class containing "badge"
                    const badges = nameCol.querySelectorAll('span[class*="Badge"], span[class*="badge"]');
                    for (const badge of badges) {
                        const badgeText = badge.textContent.trim().toLowerCase();
                        if (badgeText === 'budget' || badgeText.includes('budget')) {
                            result.has_budget = true;
                            break;
                        }
                    }
                }

                // Fallback for URL: search anywhere in the row
                if (!result.url) {
                    const anyLink = row.querySelector('a[href^="/opportunities/"]') || row.querySelector('a');
                    if (anyLink) {
                        const href = anyLink.getAttribute('href');
                        if (href) result.url = href;
                    }
                }

                // Fallback: some elements use `to` attribute instead of href
                if (!result.url) {
                    const toEl = row.querySelector('[to^="/opportunities/"]');
                    if (toEl) {
                        const to = toEl.getAttribute('to');
                        if (to) result.url = to;
                    }
                }

                // Debug: check what links exist
                const allLinks = row.querySelectorAll('a');
                result._linkCount = allLinks.length;
                if (allLinks.length > 0) {
                    result._firstLinkHref = allLinks[0].href || allLinks[0].getAttribute('href') || 'no-href';
                }

                // Column 3: Due Date (index 2)
                if (cols.length > 2) {
                    const dateCol = cols[2];
                    const spans = dateCol.querySelectorAll('span');
                    if (spans.length > 0) {
                        result.bid_date = spans[0].textContent.trim();
                        if (spans.length > 1) result.bid_time = spans[1].textContent.trim();
                    }
                }

                // Column 4: Location (index 3)
                if (cols.length > 3) {
                    const locCol = cols[3];
                    // Location has city and state - try to find them separately
                    // First try nested divs
                    const innerDivs = locCol.querySelectorAll('div');
                    let foundCity = false;
                    for (const div of innerDivs) {
                        const text = div.textContent.trim();
                        // Skip empty or if it contains other nested content
                        if (!text || div.querySelector('div')) continue;
                        if (!foundCity) {
                            result.city = text;
                            foundCity = true;
                        } else {
                            result.state = text;
                            break;
                        }
                    }
                    // Fallback: try spans
                    if (!result.city) {
                        const spans = locCol.querySelectorAll('span');
                        if (spans.length >= 2) {
                            result.city = spans[0].textContent.trim();
                            result.state = spans[1].textContent.trim();
                        } else if (spans.length === 1) {
                            // Try to split "City, State" or "CityState"
                            const text = spans[0].textContent.trim();
                            const match = text.match(/^(.+?),?\s*([A-Z]{2}|[A-Z][a-z]+)$/);
                            if (match) {
                                result.city = match[1].trim();
                                result.state = match[2].trim();
                            } else {
                                result.city = text;
                            }
                        }
                    }
                }

                // Column 5: Company/Contact (index 4)
                // Based on user's selector: div:nth-child(5) > div > div.right-... > div:nth-child(1) > span
                if (cols.length > 4) {
                    const compCol = cols[4];
                    // Company name is in: div > div[class*="right"] > div:nth-child(1) > span
                    const rightDiv = compCol.querySelector('div[class*="right"]');
                    if (rightDiv) {
                        const companySpan = rightDiv.querySelector('div:nth-child(1) > span');
                        if (companySpan) result.company = companySpan.textContent.trim();
                        // Contact is in div:nth-child(2) > span
                        const contactSpan = rightDiv.querySelector('div:nth-child(2) > span');
                        if (contactSpan) result.contact = contactSpan.textContent.trim();
                    }
                    // Fallback: try getting spans directly
                    if (!result.company) {
                        const spans = compCol.querySelectorAll('span');
                        if (spans.length >= 2) {
                            result.company = spans[0].textContent.trim();
                            result.contact = spans[1].textContent.trim();
                        } else if (spans.length === 1) {
                            result.company = spans[0].textContent.trim();
                        }
                    }
                }

                // Debug: count columns found and show structure
                result._colCount = cols.length;
                result._hasWrapper = wrapper !== row;
                result._rowClasses = row.className || '';
                result._hasLink = !!row.querySelector('a');

                return result;
            }''')

            # Debug: log first few extractions
            if index < 3:
                col_count = data.get('_colCount', 0)
                link_count = data.get('_linkCount', 0)
                first_link = data.get('_firstLinkHref', 'none')[:60]
                print(f"[BC] DEBUG row {index}: cols={col_count}, links={link_count}")
                print(f"[BC]   first_link: {first_link}")
                print(f"[BC]   name='{data.get('name', '')[:30]}' url='{data.get('url', '')[:50]}'")

            # Check if we got a name
            if not data or not data.get('name'):
                return None

            name = data['name']
            url = data.get('url', '')
            bid_date = data.get('bid_date', 'N/A') or 'N/A'
            bid_time = data.get('bid_time', '')
            city = data.get('city', 'N/A') or 'N/A'
            state = data.get('state', 'N/A') or 'N/A'
            company = data.get('company', 'N/A') or 'N/A'
            contact_name = data.get('contact', 'N/A') or 'N/A'
            has_budget = data.get('has_budget', False)

            # If we need to click the row to get the URL
            if click_for_url and not url:
                clicked_successfully = False
                try:
                    # Check if element is still attached before clicking
                    is_attached = await row.evaluate('(el) => el.isConnected')
                    if is_attached:
                        # Click the row to open details panel
                        log_status(f"Clicking row {index} to get URL...")
                        await row.click()
                        await asyncio.sleep(2.5)  # Wait for panel to open
                        clicked_successfully = True
                except Exception as click_err:
                    log_status(f"Click failed for row {index}: {click_err}")
                    pass

                # Only try to extract URL if we clicked successfully
                if not clicked_successfully:
                    pass  # Skip URL extraction, we still have the basic data
                else:
                    # Debug: check what's in the DOM after clicking
                    panel_debug = await self.page.evaluate('''() => {
                        const result = {
                            allLinks: [],
                            panelExists: false,
                            moreDetailsBtn: null,
                            panelClasses: '',
                            panelLinks: []
                        };

                        // Check for any panel/drawer that appeared - try more selectors
                        // IMPORTANT: Avoid matching row elements with "sidePanel" in class name
                        const panelSelectors = [
                            // Look for actual panel containers (usually have overlay/drawer/panel in class)
                            'div[class*="PreviewPanel"]',
                            'div[class*="DetailDrawer"]',
                            'div[class*="slideOut"]',
                            'div[class*="rightPanel"]',
                            'div[class*="detailsPanel"]',
                            'div[class*="opportunityDetail"]',
                            'div[class*="quickLinksContainer"]',  // The quick links section
                            // Try finding by structure - panels typically have fixed/absolute positioning
                            'div[class*="Overlay"] > div',
                            'div[class*="Modal"] > div',
                        ];

                        let panel = null;
                        for (const selector of panelSelectors) {
                            panel = document.querySelector(selector);
                            if (panel) {
                                result.panelClasses = selector + ' -> ' + (panel.className || '').substring(0, 50);
                                break;
                            }
                        }
                        result.panelExists = !!panel;

                        if (panel) {
                            // Get links specifically from the panel
                            const panelLinks = panel.querySelectorAll('a');
                            for (const link of panelLinks) {
                                if (link.href) result.panelLinks.push(link.href.substring(0, 80));
                            }
                        }

                        // Find all links with "opportunities" in href (from whole page)
                        const links = document.querySelectorAll('a[href*="/opportunities/"]');
                        for (const link of links) {
                            result.allLinks.push(link.href);
                        }

                        // Look for "More Project Details" text
                        const allButtons = document.querySelectorAll('button, a');
                        for (const btn of allButtons) {
                            if (btn.textContent && btn.textContent.includes('More Project Details')) {
                                result.moreDetailsBtn = btn.href || btn.getAttribute('href') || 'found-but-no-href';
                            }
                        }

                        return result;
                    }''')

                    if index < 3:  # Debug first 3 rows
                        print(f"[BC]   Panel debug: panel={panel_debug.get('panelExists')}, pageLinks={len(panel_debug.get('allLinks', []))}, panelLinks={len(panel_debug.get('panelLinks', []))}")
                        print(f"[BC]   Panel class: {panel_debug.get('panelClasses', 'none')[:60]}")
                        if panel_debug.get('panelLinks'):
                            print(f"[BC]   Panel link[0]: {panel_debug['panelLinks'][0][:60]}...")
                        elif panel_debug.get('allLinks'):
                            print(f"[BC]   Page link[0]: {panel_debug['allLinks'][0][:60]}...")

                    # Try to get URL from the PANEL (not the table rows)
                    # The panel is the side drawer that opens when you click a row
                    url_info = await self.page.evaluate('''() => {
                        // Look for the side panel/drawer that contains project details
                        // It typically has classes like slidePanel, drawer, or similar
                        const panel = document.querySelector(
                            'div[class*="slidePanel"], div[class*="drawer"], div[class*="sidePanel"], ' +
                            'div[class*="DetailPanel"], div[class*="quickView"], div[class*="projectDetail"]'
                        );

                        if (panel) {
                            // Find the "More Project Details" button/link in the panel
                            const moreDetailsBtn = panel.querySelector('a[href*="/opportunities/"][href*="/details"]');
                            if (moreDetailsBtn) return { url: moreDetailsBtn.href, source: 'panelDetailsLink' };

                            // Try quickLinks in the panel
                            const quickLink = panel.querySelector('div[class*="quickLinks"] a[href*="/opportunities/"]');
                            if (quickLink) return { url: quickLink.href, source: 'panelQuickLink' };

                            // Find any opportunity link in the panel
                            const panelLink = panel.querySelector('a[href*="/opportunities/"]');
                            if (panelLink) return { url: panelLink.href, source: 'panelOppLink' };
                        }

                        // Fallback: look for highlighted/selected row link
                        const selectedRow = document.querySelector('div[class*="selected"], div[class*="highlighted"], div[class*="active"]');
                        if (selectedRow) {
                            const rowLink = selectedRow.querySelector('a[href*="/opportunities/"]');
                            if (rowLink) return { url: rowLink.href, source: 'selectedRowLink' };
                        }

                        // Last resort: find a link with /details in the path
                        const detailsLink = document.querySelector('a[href*="/opportunities/"][href*="/details"]');
                        if (detailsLink) return { url: detailsLink.href, source: 'detailsLink' };

                        return null;
                    }''')

                    if url_info and url_info.get('url'):
                        url = url_info['url']
                        print(f"[BC]   Got URL ({url_info.get('source')}): {url[:50]}...")

            # Normalize URL (relative -> absolute) and generate project ID
            project_id = f'project_{index}'
            if url and '/opportunities/' in url:
                if url.startswith('/'):
                    url = f"https://app.buildingconnected.com{url}"
                project_id = url.split('/opportunities/')[1].split('/')[0]

            # Set url to N/A if empty
            if not url:
                url = 'N/A'

            # Format location properly (avoid duplication)
            if city != "N/A" and state != "N/A":
                location = f"{city}, {state}"
            elif city != "N/A":
                location = city
            else:
                location = "N/A"

            budget_indicator = " [BUDGET]" if has_budget else ""
            print(f"[BC] {name[:35]:35} | {bid_date:12} | {city[:15]:15} | {company[:20]}{budget_indicator}")

            return {
                'id': project_id,
                'name': name,
                'bid_date': bid_date,
                'bid_time': bid_time,
                'due_date': bid_date,
                'location': location,
                'city': city,
                'state': state,
                'company': company,
                'gc': company,
                'contact_name': contact_name,
                'url': url,
                'source': 'BuildingConnected',
                'site': 'BuildingConnected',
                'extracted_at': datetime.now().isoformat(),
                'contact_email': None,
                'files_count': None,
                'has_new_files': False,
                'has_budget': has_budget,
                'files_link': None,
                'download_link': None,
            }

        except Exception as e:
            msg = str(e)
            print(f"[BC] Error extracting row {index}: {e}")
            if "Execution context was destroyed" in msg:
                return {"__context_destroyed": True}
            return None

    async def extract_detail_info(self, project, sidebar_opened=False):
        """Extract additional info from the project side panel or detail page."""
        try:
            detail_info = {
                'contact_email': None,
                'contact_phone': None,
                'full_address': None,
                'description': None,
                'files_count': None,
                'has_new_files': False,
                'files_link': None,
                'download_link': None,
            }

            project_url = project.get('url') if isinstance(project, dict) else None
            project_name = project.get('name') if isinstance(project, dict) else None

            # Prefer side panel (per instructions)
            if not sidebar_opened and project_name:
                sidebar_opened = await self.open_project_sidebar(project_name)

            # Fallback: navigate to project URL if sidebar not available
            if not sidebar_opened and project_url and project_url != "N/A":
                try:
                    await self.page.goto(project_url, wait_until='domcontentloaded', timeout=30000)
                    await asyncio.sleep(2)
                except Exception as nav_err:
                    print(f"[BC]     Detail nav failed: {nav_err}")

            # Construct files link from project URL as a fallback (do not use as download link)
            if project_url and '/opportunities/' in project_url:
                base_url = project_url.split('/opportunities/')[0]
                project_id = project_url.split('/opportunities/')[1].split('/')[0]
                detail_info['files_link'] = f"{base_url}/opportunities/{project_id}/files"

            # Extract files count from quick links
            files_count_selectors = [
                '#main > div > div.styled__StyledRoot-sc-1lsmkna-0.frwmPl > div.styled__StyledLayoutContainer-sc-1lsmkna-1.dRXrjH > div.styled__StyledMain-sc-1lsmkna-3.dFaUcj > div > div.styled__StyledPageContent-j773fv-3.tRbST > div > div > div > div > div.bidBoardBeta-0-1-210 > div.view__RootDiv-sc-1inb5pz-0.cVxFi > div > div.scrollY-0-1-387.flexCol-0-1-380 > div.quickLinksContainer-0-1-419 > a:nth-child(2) > div > div.number-0-1-420',
                'div[class*="quickLinksContainer"] a:nth-child(2) div[class*="number"]',
                'div[class*="quickLinksContainer"] div[class*="number"]',
                'a[href*="/files"] div[class*="number"]',
            ]
            for selector in files_count_selectors:
                try:
                    count_elem = await self.page.query_selector(selector)
                    if count_elem:
                        text = await count_elem.text_content()
                        if text:
                            try:
                                detail_info['files_count'] = int(text.strip())
                            except:
                                detail_info['files_count'] = text.strip()
                        break
                except:
                    continue

            # Check for "New" badge on files
            new_badge_selectors = [
                'div[class*="quickLinksContainer"] a:nth-child(2) span span',
                'div[class*="quickLinksContainer"] a:nth-child(2) div span',
                'a[href*="/files"] span span',
            ]
            for selector in new_badge_selectors:
                try:
                    badge_elem = await self.page.query_selector(selector)
                    if badge_elem:
                        text = await badge_elem.text_content()
                        if text and ('new' in text.lower() or 'addendum' in text.lower()):
                            detail_info['has_new_files'] = True
                        break
                except:
                    continue

            # Get files link from page if we don't have it yet (sidebar quick link)
            if not detail_info['files_link']:
                files_link_selectors = [
                    '#main > div > div.styled__StyledRoot-sc-1lsmkna-0.frwmPl > div.styled__StyledLayoutContainer-sc-1lsmkna-1.dRXrjH > div.styled__StyledMain-sc-1lsmkna-3.dFaUcj > div > div.styled__StyledPageContent-j773fv-3.tRbST > div > div > div > div > div.bidBoardBeta-0-1-210 > div.view__RootDiv-sc-1inb5pz-0.cVxFi > div > div.scrollY-0-1-387.flexCol-0-1-380 > div.quickLinksContainer-0-1-419 > a:nth-child(2)',
                    'div[class*="quickLinksContainer"] a:nth-child(2)',
                    'a[href*="/files"]',
                ]
                for selector in files_link_selectors:
                    try:
                        link_elem = await self.page.query_selector(selector)
                        if link_elem:
                            href = await link_elem.get_attribute('href')
                            if href:
                                if href.startswith('/'):
                                    href = f"https://app.buildingconnected.com{href}"
                                detail_info['files_link'] = href
                            break
                    except:
                        continue

            # Extract contact email
            email_selectors = [
                'a[href^="mailto:"]',
                'div[class*="contactInfo"] a[href^="mailto:"]',
            ]
            for selector in email_selectors:
                try:
                    email_elem = await self.page.query_selector(selector)
                    if email_elem:
                        href = await email_elem.get_attribute('href')
                        if href and href.startswith('mailto:'):
                            detail_info['contact_email'] = href.replace('mailto:', '')
                        break
                except:
                    continue

            # Extract full address
            address_selectors = [
                'main > div > div.styled__StyledRoot-sc-1lsmkna-0.frwmPl > div.styled__StyledLayoutContainer-sc-1lsmkna-1.dRXrjH > div.styled__StyledMain-sc-1lsmkna-3.dFaUcj > div > div.styled__StyledPageContent-j773fv-3.tRbST > div > div > div > div > div.bidBoardBeta-0-1-85 > div.view__RootDiv-sc-1inb5pz-0.cVxFi > div > div.scrollY-0-1-291.flexCol-0-1-284 > div:nth-child(10) > div:nth-child(2) > div:nth-child(7) > div.hoverArea-0-1-405.rightSideFlex-0-1-409 > div.value-0-1-410 > div > span',
                'div[class*="scrollY"] div[class*="value"] div span',
                'div[class*="hoverArea"] div[class*="value"] div span',
                'div[class*="locationWrapper"] span',
            ]
            for selector in address_selectors:
                try:
                    addr_elem = await self.page.query_selector(selector)
                    if addr_elem:
                        text = await addr_elem.text_content()
                        if text and text.strip():
                            detail_info['full_address'] = text.strip()
                        break
                except:
                    continue

            # Extract project description (side panel)
            description_selectors = [
                '#main > div > div.styled__StyledRoot-sc-1lsmkna-0.frwmPl > div.styled__StyledLayoutContainer-sc-1lsmkna-1.dRXrjH > div.styled__StyledMain-sc-1lsmkna-3.dFaUcj > div > div.styled__StyledPageContent-j773fv-3.tRbST > div > div > div > div > div.bidBoardBeta-0-1-85 > div.view__RootDiv-sc-1inb5pz-0.cVxFi > div > div.scrollY-0-1-291.flexCol-0-1-284 > div:nth-child(10) > div:nth-child(2) > div:nth-child(9) > div.hoverArea-0-1-405 > div.value-0-1-410 > div > div > div > div > div > div > div > div > div:nth-child(1) > div > span > span',
                'div[class*="scrollY"] div[class*="value"] span',
                'div[class*="description"] span',
            ]
            for selector in description_selectors:
                try:
                    desc_elem = await self.page.query_selector(selector)
                    if desc_elem:
                        text = await desc_elem.text_content()
                        if text and text.strip():
                            detail_info['description'] = text.strip()
                            break
                except:
                    continue

            return detail_info

        except Exception as e:
            print(f"[BC]     Error extracting detail info: {e}")
            return None

    async def download_files_for_project(self, project, sidebar_opened=False):
        """
        Download files for a specific project (Pass 2) using Playwright.
        """
        print(f"\n[BC] [Pass 2] Downloading files for: {project['name']}")

        try:
            if not project.get('name'):
                print("[BC]    Project missing name; cannot open sidebar")
                return False

            # Open side panel by clicking project name, then click Files quick link
            if not sidebar_opened:
                print("[BC]    Opening project sidebar...")
                opened = await self.open_project_sidebar(project['name'])
                if not opened:
                    print("[BC]    Could not open project sidebar")
                    return False

            print("[BC]    Clicking Files link in sidebar...")
            
            # First try JavaScript-based detection for Files link
            files_link_result = await self.page.evaluate('''() => {
                const isVisible = (el) => {
                    if (!el) return false;
                    const style = window.getComputedStyle(el);
                    return el.offsetParent !== null && 
                           style.display !== 'none' && 
                           style.visibility !== 'hidden';
                };
                
                // Find all links
                const links = Array.from(document.querySelectorAll('a'));
                
                for (const link of links) {
                    if (!isVisible(link)) continue;
                    const text = (link.textContent || '').trim().toLowerCase();
                    const href = link.getAttribute('href') || '';
                    
                    // Match "Files" link
                    if (text === 'files' || href.includes('/files')) {
                        const fullHref = href.startsWith('/') 
                            ? 'https://app.buildingconnected.com' + href 
                            : href;
                        link.click();
                        return { clicked: true, href: fullHref };
                    }
                }
                
                return { clicked: false, href: null };
            }''')
            
            clicked_files_link = files_link_result.get('clicked', False)
            if files_link_result.get('href'):
                project['files_link'] = files_link_result['href']
                print(f"[BC]    Files link found: {files_link_result['href'][:60]}...")
            
            if not clicked_files_link:
                # Fallback to CSS selectors
                files_link_selectors = [
                    'div[class*="quickLinksContainer"] a:nth-child(2)',
                    'a[href*="/files"]',
                    'text=Files',
                ]

                for selector in files_link_selectors:
                    try:
                        link_elem = await self.page.query_selector(selector)
                        if link_elem:
                            href = await link_elem.get_attribute('href')
                            if href:
                                if href.startswith('/'):
                                    href = f"https://app.buildingconnected.com{href}"
                                project['files_link'] = href
                            await link_elem.click()
                            clicked_files_link = True
                            break
                    except:
                        continue

            if not clicked_files_link:
                print("[BC]    Could not find Files link in sidebar")
                return False

            try:
                await self.page.wait_for_url("**/files", timeout=10000)
            except:
                pass
            await asyncio.sleep(2)

            # Snapshot before download (for fallback detection)
            files_before = self._snapshot_download_dir()

            # Click Download All button using robust JavaScript detection
            print("[BC]    Clicking Download All button...")
            
            # First try JavaScript-based detection (most robust)
            clicked_download = await self.page.evaluate('''() => {
                const isVisible = (el) => {
                    if (!el) return false;
                    const style = window.getComputedStyle(el);
                    return el.offsetParent !== null && 
                           style.display !== 'none' && 
                           style.visibility !== 'hidden' &&
                           style.opacity !== '0';
                };
                
                // Find all buttons and clickable elements
                const candidates = Array.from(document.querySelectorAll('button, [role="button"], a[class*="button"], div[class*="button"]'));
                
                for (const el of candidates) {
                    if (!isVisible(el)) continue;
                    const text = (el.textContent || '').trim().toLowerCase();
                    const ariaLabel = (el.getAttribute('aria-label') || '').toLowerCase();
                    
                    // Match "Download All" or "Download" buttons
                    if (text === 'download all' || text === 'download' || 
                        ariaLabel.includes('download all') || ariaLabel.includes('download')) {
                        el.click();
                        return true;
                    }
                }
                
                // Also check for download icons with nearby download text
                const svgs = Array.from(document.querySelectorAll('svg'));
                for (const svg of svgs) {
                    const parent = svg.closest('button, [role="button"], a');
                    if (parent && isVisible(parent)) {
                        const text = (parent.textContent || '').toLowerCase();
                        if (text.includes('download')) {
                            parent.click();
                            return true;
                        }
                    }
                }
                
                return false;
            }''')
            
            download = None
            if not clicked_download:
                # Fallback: try CSS selectors
                download_btn_selectors = [
                    '[data-testid="download-all-bttn"]',
                    'button:has-text("Download All")',
                    'button:has-text("Download")',
                    'text=Download All',
                ]
                
                for selector in download_btn_selectors:
                    try:
                        download_btn = await self.page.query_selector(selector)
                        if download_btn:
                            try:
                                async with self.page.expect_download(timeout=20000) as download_info:
                                    await download_btn.click()
                                download = await download_info.value
                                clicked_download = True
                                print("[BC]    Download initiated (captured)")
                                break
                            except Exception:
                                await download_btn.click()
                                clicked_download = True
                                print("[BC]    Download initiated")
                                break
                    except:
                        continue
            else:
                print("[BC]    Download button clicked via JavaScript")

            if not clicked_download:
                print("[BC]    Could not find Download button")
                return False

            # Handle any popups that appear (large file confirmation, download started, etc.)
            # Try multiple times with short delays since popups may appear after a moment
            for attempt in range(5):
                await asyncio.sleep(0.5)
                prompt_clicked = await self.handle_large_file_prompt()
                if prompt_clicked:
                    print(f"[BC]    Popup dismissed (attempt {attempt + 1})")
                    # After dismissing, try to capture the download if we didn't have one
                    if not download:
                        try:
                            download = await self.page.wait_for_event("download", timeout=5000)
                            print("[BC]    Download captured after popup dismiss")
                        except Exception:
                            pass
                    break
            
            # Additional popup check and wait for download
            if not download:
                try:
                    # Give more time for download to start
                    download = await self.page.wait_for_event("download", timeout=15000)
                except Exception:
                    # One more popup check
                    await self.handle_large_file_prompt()
                    await asyncio.sleep(1)
                    try:
                        download = await self.page.wait_for_event("download", timeout=10000)
                    except Exception:
                        download = None

            # Wait for download to complete
            print("[BC]    Waiting for download to complete...")
            await asyncio.sleep(5)

            local_path = None
            new_file = None
            if download:
                try:
                    suggested = download.suggested_filename
                    target_path = os.path.join(self.download_dir, suggested)
                    await download.save_as(target_path)
                    new_file = suggested
                    local_path = target_path
                except Exception:
                    local_path = await download.path()
                    if local_path:
                        new_file = os.path.basename(local_path)

            if not new_file:
                # Fallback: detect from directory changes
                await asyncio.sleep(5)
                files_after = self._snapshot_download_dir()
                new_file = self._pick_latest_download(files_before, files_after)
                if new_file:
                    local_path = os.path.join(self.download_dir, new_file)

            if new_file and local_path:
                # Rename to unique project-specific filename
                new_file, local_path = self._rename_download(new_file, project['name'])
                print(f"[BC]    File downloaded: {new_file}")

                # Try to upload to Google Drive
                if GDRIVE_AVAILABLE:
                    gdrive_status = get_status()
                    print(f"[BC]    Google Drive status: {gdrive_status}")

                    # Check if we should use Google Drive
                    use_gdrive = should_use_gdrive()
                    if not use_gdrive and gdrive_status.get('configured') and not gdrive_status.get('authenticated'):
                        print("[BC]    Google Drive configured but not authenticated - attempting auth...")
                        try:
                            from services.google_drive import authenticate
                            creds = authenticate()
                            if creds:
                                print("[BC]    Google Drive authentication successful!")
                                use_gdrive = True
                            else:
                                print("[BC]    Google Drive authentication failed")
                        except Exception as auth_err:
                            print(f"[BC]    Google Drive auth error: {auth_err}")
                else:
                    use_gdrive = False
                    print("[BC]    Google Drive not available")

                if use_gdrive:
                    try:
                        print("[BC]    Uploading to Google Drive...")
                        # Use the renamed local filename (already includes project + timestamp)
                        gdrive_filename = new_file

                        result = upload_and_cleanup(
                            local_path,
                            filename=gdrive_filename,
                            source='BuildingConnected',
                            delete_local=True
                        )

                        if result:
                            project['gdrive_file_id'] = result.get('file_id')
                            project['gdrive_link'] = result.get('web_link')
                            project['gdrive_download_link'] = result.get('download_link')
                            project['download_link'] = result.get('web_link')
                            project['storage_type'] = 'gdrive'
                            print(f"[BC]    SUCCESS! Uploaded to Google Drive: {result.get('web_link', '')[:60]}...")
                        else:
                            # Fallback to local storage
                            print("[BC]    Google Drive upload failed, keeping local file")
                            web_path = f"/downloads/{new_file}"
                            project['local_file_path'] = web_path
                            project['download_link'] = web_path
                            project['storage_type'] = 'local'
                    except Exception as e:
                        print(f"[BC]    Google Drive error: {e}, keeping local file")
                        import traceback
                        traceback.print_exc()
                        web_path = f"/downloads/{new_file}"
                        project['local_file_path'] = web_path
                        project['download_link'] = web_path
                        project['storage_type'] = 'local'
                else:
                    # Local storage only
                    web_path = f"/downloads/{new_file}"
                    project['local_file_path'] = web_path
                    project['downloaded_file'] = new_file
                    project['download_link'] = web_path
                    project['storage_type'] = 'local'
                    print(f"[BC]    Saved locally: {web_path}")
            else:
                print("[BC]    Warning: No new files detected or updated in download directory")

            print("[BC]    Download complete")
            return True

        except Exception as e:
            print(f"[BC]    Error downloading files: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def scrape_all_projects(self, max_projects=None, include_details=False, download_files=False):
        """
        Scrape projects from table view using multi-pass approach

        Args:
            max_projects: Max number to process (optional limit)
            include_details: If True, get contact email and files link in a separate pass (slower)
            download_files: If True, perform another pass to download files for all projects
        """
        log_status("=" * 40)
        log_status("Starting BuildingConnected scrape")
        log_status(f"Include details: {'Yes' if include_details else 'No'}")
        log_status(f"Download files: {'Yes' if download_files else 'No'}")

        await self.navigate_to_pipeline()
        await self.sort_by_due_date()

        # ====== PASS 1: Extract ALL Project Data from Table (with row clicks for URL) ======
        log_status("=== SINGLE PASS: Extracting Table Data + Details ===")

        seen_ids = set()
        processed_count = 0
        scroll_attempts = 0
        max_scroll_attempts = 999999  # Effectively unlimited
        found_expired = False
        consecutive_no_new = 0
        consecutive_no_scroll = 0
        last_scroll_top = -1

        context_resets = 0
        while not found_expired and scroll_attempts < max_scroll_attempts:
            # Get visible rows in current viewport
            rows = await self.get_visible_rows()
            new_projects_this_batch = 0

            if scroll_attempts == 0:
                log_status(f"Found {len(rows)} visible row elements")

            # Debug logging every 5 scrolls
            if scroll_attempts > 0 and scroll_attempts % 5 == 0:
                log_status(f"Scroll batch {scroll_attempts}: checking {len(rows)} rows, total collected: {processed_count}")

            # Process each visible row
            reset_rows = False
            for idx, row in enumerate(rows):
                try:
                    # Extract row data from table
                    # Enable clicking for first batch to get URLs, then rely on URL patterns
                    should_click = (scroll_attempts == 0 and idx < 5)  # Click first 5 rows to establish pattern
                    data = await self.extract_row_data(row, processed_count, click_for_url=should_click)
                    if data and data.get("__context_destroyed"):
                        log_status("Execution context reset detected - reloading pipeline and retrying rows")
                        context_resets += 1
                        if context_resets > 3:
                            log_status("Too many context resets; aborting to avoid loop")
                            return self.leads
                        await self.navigate_to_pipeline()
                        await self.sort_by_due_date()
                        reset_rows = True
                        break
                    if not data:
                        continue

                    # Skip if already processed
                    if data['id'] in seen_ids:
                        continue

                    # Check if expired
                    if self.is_project_expired(data['bid_date']):
                        print(f"[BC] Skipping expired: {data['name'][:30]}... ({data['bid_date']})")
                        seen_ids.add(data['id'])
                        continue

                    # New project found!
                    seen_ids.add(data['id'])
                    new_projects_this_batch += 1

                    # Just log it - NO DETAILS YET (will get in Pass 2)
                    print(f"[BC] [{processed_count + 1}] {data['name'][:40]}... | {data['bid_date']} | {data['location']}")

                    # Open sidebar from this row and extract details immediately (single pass)
                    sidebar_opened = await self.open_sidebar_from_row(row)
                    detail_info = await self.extract_detail_info(data, sidebar_opened=sidebar_opened)
                    if detail_info:
                        data.update(detail_info)

                    # Optional download in same pass
                    if download_files:
                        await self.download_files_for_project(data, sidebar_opened=sidebar_opened)

                    self.leads.append(data)
                    processed_count += 1

                except Exception as e:
                    continue
            if reset_rows:
                continue

            # Break if expired found
            if found_expired:
                break

            # Check scroll position
            scroll_info = await self.get_scroll_position()
            if scroll_info:
                current_scroll = scroll_info['scrollTop']
                max_scroll = scroll_info['scrollHeight'] - scroll_info['clientHeight']

                # Check if we found new projects this batch
                if new_projects_this_batch == 0:
                    consecutive_no_new += 1
                    if consecutive_no_new % 5 == 0:
                        log_status(f"No new projects for {consecutive_no_new} batches - Scroll: {int(current_scroll)}/{int(max_scroll)}")

                    # If no new projects for 20 consecutive batches, we're done
                    if consecutive_no_new >= 20:
                        log_status("No new projects for 20 batches - end of table reached")
                        break
                else:
                    consecutive_no_new = 0
                    if new_projects_this_batch > 0:
                        log_status(f"Found {new_projects_this_batch} new | Total: {processed_count} | Scroll: {int(current_scroll)}/{int(max_scroll)}")

                # Check if at bottom (with some tolerance)
                if current_scroll >= max_scroll - 10:
                    log_status(f"Reached bottom of table | Total: {processed_count}")
                    break

                # Check if scroll position hasn't changed
                if current_scroll == last_scroll_top:
                    consecutive_no_scroll += 1
                    if consecutive_no_scroll >= 10:
                        log_status(f"Scroll not advancing - likely at end | Total: {processed_count}")
                        break
                else:
                    consecutive_no_scroll = 0
                    last_scroll_top = current_scroll

            # Scroll down
            await self.scroll_table(400)
            scroll_attempts += 1

            # Extra wait every 10 scrolls
            if scroll_attempts % 10 == 0:
                print(f"[BC] Pausing to let virtual table render... (scroll attempt {scroll_attempts})")
                await asyncio.sleep(2)

        log_status(f"=== SINGLE PASS Complete: Found {len(self.leads)} projects ===")

        log_status(f"SCRAPING COMPLETE - Total leads: {len(self.leads)}")
        return self.leads

    def _unzip_downloads(self):
        """Unzip all .zip files in the download directory and move zips into extracted folders."""
        try:
            import zipfile
            zips = [f for f in os.listdir(self.download_dir) if f.lower().endswith('.zip')]
            if not zips:
                return
            for zip_name in zips:
                zip_path = os.path.join(self.download_dir, zip_name)
                base_name = os.path.splitext(zip_name)[0]
                extract_dir = os.path.join(self.download_dir, base_name)
                try:
                    if not os.path.exists(extract_dir):
                        os.makedirs(extract_dir, exist_ok=True)
                        with zipfile.ZipFile(zip_path, 'r') as zf:
                            zf.extractall(extract_dir)
                    # Move original zip into extracted folder to prevent re-unzips
                    target_zip_path = os.path.join(extract_dir, zip_name)
                    if not os.path.exists(target_zip_path):
                        os.replace(zip_path, target_zip_path)
                except Exception as e:
                    print(f"[BC]    Unzip failed for {zip_name}: {e}")
        except Exception as e:
            print(f"[BC]    Unzip step failed: {e}")

    async def save_results(self):
        """Save leads to JSON and automatically remove duplicates"""
        output_file = os.path.join(os.path.dirname(__file__), 'leads_db.json')

        existing_leads = []
        if os.path.exists(output_file):
            try:
                with open(output_file, 'r') as f:
                    existing_leads = json.load(f)
            except:
                pass

        existing_ids = {lead.get('id') for lead in existing_leads}
        new_leads = [lead for lead in self.leads if lead.get('id') not in existing_ids]

        all_leads = existing_leads + new_leads

        with open(output_file, 'w') as f:
            json.dump(all_leads, f, indent=2)

        print(f"\n Saved {len(new_leads)} new leads to {output_file}")
        print(f" Total leads in database: {len(all_leads)}")

        # Automatically remove duplicates
        print("\n Removing duplicates...")
        try:
            from services.storage import deduplicate_database
            removed_count = deduplicate_database()
            print(f" Removed {removed_count} duplicate leads")
        except Exception as e:
            print(f" Warning: Could not deduplicate: {e}")

    async def run(self, max_projects=None, include_details=False, download_files=False):
        """
        Run the scraper

        Args:
            max_projects: Max number to scrape
            include_details: If True, get contact email and files info (slower)
            download_files: If True, download files for all projects (Pass 2)
        """
        try:
            await self.setup_browser()
            await self.scrape_all_projects(max_projects, include_details, download_files)
            await self.save_results()
            # Unzip downloaded archives after scraping
            self._unzip_downloads()
            return self.leads
        except asyncio.CancelledError:
            print("\n[BC] Run cancelled (likely shutdown or Ctrl+C).")
            return []
        except KeyboardInterrupt:
            print("\n[BC] Run interrupted by user.")
            return []
        except Exception as e:
            print(f"\n[BC] FATAL ERROR: {e}")
            if self.page:
                try:
                    print(f"[BC] Current URL at crash: {self.page.url}")
                    debug_path = os.path.join(self.download_dir, 'bc_fatal_error.png')
                    await self.page.screenshot(path=debug_path, full_page=True)
                    print(f"[BC] Saved debug screenshot to: {debug_path}")
                except:
                    pass
            import traceback
            traceback.print_exc()
            return []
        finally:
            # Close Playwright properly
            if self.context:
                try:
                    await self.context.close()
                except:
                    pass
            if self.playwright:
                try:
                    await self.playwright.stop()
                except:
                    pass
            print("\n[BC] Browser closed")


async def main():
    """Main entry point"""
    print("\n" + "="*60)
    print(" BUILDINGCONNECTED TABLE SCRAPER (Two-Pass)")
    print("="*60 + "\n")

    print("Choose mode:")
    print("1. FAST: Table data only (name, date, company, contact)")
    print("2. DETAILED: Include email and files info (DEFAULT)")
    print("3. FULL: Two-pass mode with file downloads")

    # Default to detailed mode to get files links
    include_details = True   # Extract email and files links from detail pages
    download_files = True   # Set to True to enable Pass 2 file downloads

    scraper = BuildingConnectedTableScraper()
    leads = await scraper.run(max_projects=None, include_details=include_details, download_files=download_files)

    print("\n" + "="*60)
    print(f" FINAL RESULTS: Found {len(leads)} leads")
    print("="*60)

    if leads:
        print("\nSample leads:")
        for i, lead in enumerate(leads[:3], 1):
            print(f"\nLead {i}:")
            print(f"  Name: {lead.get('name')}")
            print(f"  Company: {lead.get('company')}")
            print(f"  Contact: {lead.get('contact_name')}")
            print(f"  Date: {lead.get('bid_date')}")
            print(f"  Location: {lead.get('location')}")
            if include_details:
                print(f"  Email: {lead.get('contact_email')}")
                print(f"  Files: {lead.get('files_count')}")
                print(f"  New Files: {lead.get('has_new_files')}")
                if lead.get('files_link'):
                    print(f"  Download Link: {lead.get('files_link')}")
    else:
        print("\n No leads found.")

    print("\n" + "="*60 + "\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except asyncio.CancelledError:
        print("[BC] Cancelled during shutdown.")
    except KeyboardInterrupt:
        print("[BC] Interrupted by user.")
