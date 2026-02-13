"""
PlanHub scraper using Playwright for reliable browser automation.
"""
import os
import sys
import json
import asyncio
import platform
from datetime import datetime, date

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import PlanHubConfig, DATE_FORMATS

# Import Gemini browser helper
try:
    from scrapers.gemini_browser import GeminiBrowser, GEMINI_AVAILABLE
    print(f"[PH] Gemini browser module loaded. Available: {GEMINI_AVAILABLE}")
except ImportError as e:
    GEMINI_AVAILABLE = False
    GeminiBrowser = None
    print(f"[PH] Gemini browser NOT available: {e}")

# Import Google Drive service
try:
    from services.google_drive import upload_and_cleanup, should_use_gdrive, is_authenticated, get_status, check_file_exists
    GDRIVE_AVAILABLE = True
    print(f"[PH] Google Drive module loaded. Available: {GDRIVE_AVAILABLE}")
except ImportError as e:
    GDRIVE_AVAILABLE = False
    print(f"[PH] Google Drive module NOT available: {e}")

# Global log buffer that scheduler can access
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

    # Also try to add to scheduler's log
    try:
        from services.scheduler import add_to_log
        add_to_log(f"[PH] {msg}")
    except:
        pass


class PlanHubScraper:
    """
    PlanHub scraper using Playwright with deterministic navigation.

    Features:
    - Login handling with credentials from environment
    - Uses saved search "Daniel's Filter" for filtering
    - Past-due filtering using date comparison
    - Sprinkler keyword detection in project descriptions
    - Two-pass extraction: metadata first, then file downloads
    - Deduplication using processed_ids set
    """

    def __init__(self):
        self.config = PlanHubConfig()
        self.playwright = None
        self.browser_context = None
        self.page = None
        self.leads = []
        self.processed_ids = set()
        self.gemini_browser = None
        self.download_dir = self.config.DOWNLOAD_DIR

        # Use full desktop viewport for browsing
        self.config.VIEWPORT_WIDTH = 1920
        self.config.VIEWPORT_HEIGHT = 1080

        # Ensure download directory exists
        os.makedirs(self.download_dir, exist_ok=True)

    def _find_chrome_executable(self):
        """Find Chrome executable on the system."""
        system = platform.system()
        possible_paths = []

        if system == 'Windows':
            possible_paths = [
                r'C:\Users\dms03\Development\planroom-genius\backend\chrome-win\chrome.exe',
                r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
                os.path.expanduser(r'~\AppData\Local\Google\Chrome\Application\chrome.exe'),
            ]
        elif system == 'Darwin':
            possible_paths = [
                '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
            ]
        elif system == 'Linux':
            possible_paths = [
                '/usr/bin/chromium-browser',
                '/usr/bin/chromium',
                '/usr/bin/google-chrome',
                '/usr/bin/google-chrome-stable',
                '/snap/bin/chromium',
                '/usr/lib/chromium-browser/chromium-browser',
                '/usr/lib/chromium/chromium',
            ]

        for path in possible_paths:
            if os.path.exists(path):
                return path

        return None

    async def setup_browser(self):
        """Initialize Playwright browser with persistent profile."""
        from playwright.async_api import async_playwright

        self.playwright = await async_playwright().start()

        chrome_path = self._find_chrome_executable()
        if chrome_path:
            print(f"[OK] Found Chrome at: {chrome_path}")
        else:
            print("WARNING: Chrome not found, using Playwright bundled Chromium")

        print(f"\n======== CHROME PROFILE CONFIG ========")
        print(f"User Data Dir:   {self.config.CHROME_USER_DATA_DIR}")
        print(f"Headless:        {self.config.HEADLESS}")
        print(f"Chrome Path:     {chrome_path or 'Playwright default'}")
        print("=======================================\n")

        launch_args = [
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
            '--disable-blink-features=AutomationControlled',
            '--disable-gpu',
            '--disable-software-rasterizer',
            '--disable-features=VizDisplayCompositor',
            '--mute-audio',
        ]

        launch_kwargs = {
            'user_data_dir': self.config.CHROME_USER_DATA_DIR,
            'headless': self.config.HEADLESS,
            'args': launch_args,
            'viewport': {
                'width': self.config.VIEWPORT_WIDTH,
                'height': self.config.VIEWPORT_HEIGHT,
            },
            'accept_downloads': True,
            'ignore_https_errors': True,
        }

        if chrome_path:
            launch_kwargs['executable_path'] = chrome_path

        # Retry launch logic
        for attempt in range(3):
            try:
                self.browser_context = await self.playwright.chromium.launch_persistent_context(
                    **launch_kwargs
                )
                break
            except Exception as e:
                print(f"   Browser launch failed (attempt {attempt+1}/3): {e}")
                if attempt == 2:
                    raise
                await asyncio.sleep(2)

        # Use first page or create one
        if self.browser_context.pages:
            self.page = self.browser_context.pages[0]
        else:
            self.page = await self.browser_context.new_page()

        print(" Browser initialized (Playwright)")

    async def close_browser(self):
        """Close browser gracefully."""
        if self.browser_context:
            try:
                await self.browser_context.close()
                print("\n Browser closed")
            except Exception:
                pass
        if self.playwright:
            try:
                await self.playwright.stop()
            except Exception:
                pass

    def parse_date(self, date_str):
        """Parse date string into date object."""
        if not date_str or date_str == "N/A":
            return None

        for fmt in DATE_FORMATS:
            try:
                return datetime.strptime(date_str.strip(), fmt).date()
            except ValueError:
                continue

        print(f"   Could not parse date: {date_str}")
        return None

    async def is_project_past_due(self, due_date_str):
        """Check if project is past due."""
        try:
            if not due_date_str or due_date_str == "N/A":
                return False

            today = date.today()
            parsed_date = self.parse_date(due_date_str)

            if parsed_date:
                is_past_due = parsed_date < today
                if is_past_due:
                    print(f"  Past due: {due_date_str} (today: {today})")
                return is_past_due
            else:
                return False

        except Exception as e:
            print(f" Error checking due date: {e}")
            return False

    async def save_results(self, output_file=None):
        """Save leads to JSON file."""
        output_file = output_file or self.config.DB_FILE

        existing_leads = []
        if os.path.exists(output_file):
            try:
                with open(output_file, 'r') as f:
                    existing_leads = json.load(f)
            except:
                existing_leads = []

        existing_ids = {lead.get('id') for lead in existing_leads}
        new_leads = [lead for lead in self.leads if lead.get('id') not in existing_ids]

        all_leads = existing_leads + new_leads

        with open(output_file, 'w') as f:
            json.dump(all_leads, f, indent=2)

        print(f"\n Saved {len(new_leads)} new leads to {output_file}")
        print(f" Total leads in database: {len(all_leads)}")

    async def navigate_with_retry(self, url, max_retries=3):
        """Navigate to URL with retry logic."""
        for attempt in range(max_retries):
            try:
                print(f" Navigating to {url}{'...' if attempt == 0 else f' (retry {attempt})...'}")
                await self.page.goto(url, wait_until='networkidle', timeout=self.config.NAVIGATION_TIMEOUT)
                await asyncio.sleep(self.config.DELAY_AFTER_NAVIGATION)
                print(" Navigation successful")
                return True
            except Exception as e:
                print(f" Navigation failed (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt == max_retries - 1:
                    print(f" Failed to navigate to {url} after {max_retries} attempts")
                    return False
                await asyncio.sleep(2 ** attempt)
        return False

    async def check_login_status(self):
        """Check if already logged in."""
        try:
            current_url = self.page.url
            if 'supplier.planhub.com/project/list' in current_url:
                print(" Already logged in")
                return True

            login_form = await self.page.query_selector(self.config.LOGIN_EMAIL_SELECTOR)
            if login_form:
                print(" Login required")
                return False

            return True
        except Exception as e:
            print(f" Could not determine login status: {e}")
            return False

    async def login(self):
        """Navigate to login page and authenticate."""
        print(" Logging in to PlanHub...")

        if not self.config.LOGIN_EMAIL or not self.config.LOGIN_PASSWORD:
            print(" Missing login credentials (PLANHUB_LOGIN/PLANHUB_PW)")
            return False

        if not await self.navigate_with_retry(self.config.LOGIN_URL):
            return False

        try:
            # Wait for login form
            await self.page.wait_for_selector(self.config.LOGIN_EMAIL_SELECTOR, timeout=self.config.SELECTOR_TIMEOUT)

            # Fill email and password
            await self.page.fill(self.config.LOGIN_EMAIL_SELECTOR, self.config.LOGIN_EMAIL)
            print(f"   Entered email: {self.config.LOGIN_EMAIL}")

            await self.page.fill(self.config.LOGIN_PASSWORD_SELECTOR, self.config.LOGIN_PASSWORD)
            print("   Entered password")

            # Click submit button
            await self.page.click(self.config.LOGIN_SUBMIT_SELECTOR)
            print("   Submitted login form")

            await asyncio.sleep(3)

            current_url = self.page.url
            if 'planhub.com' in current_url and 'signin' not in current_url:
                print(" Login successful")
                return True
            else:
                print(f" Login may have failed (current URL: {current_url})")
                return False

        except Exception as e:
            print(f" Login failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def navigate_to_projects(self):
        """Navigate to project list page."""
        print("[PH] Navigating to project list...")

        if not await self.navigate_with_retry(self.config.PROJECT_LIST_URL):
            return False

        current_url = self.page.url
        print(f"[PH] Current URL: {current_url}")

        if not await self.check_login_status():
            if not await self.login():
                return False
            if not await self.navigate_with_retry(self.config.PROJECT_LIST_URL):
                return False

        return True

    async def apply_filters(self):
        """Load saved search filter 'Daniel's Filter'."""
        print("[PH] Loading saved search filter...")

        try:
            await asyncio.sleep(2)

            # Click "View Saved Searches" button
            print("[PH]    Clicking 'View Saved Searches' button...")
            saved_searches_btn_selector = '#cdk-accordion-child-1 > div > div > planhub-persist-filters-actions > section > div > planhub-button:nth-child(4) > button'

            try:
                btn = self.page.locator(saved_searches_btn_selector)
                if await btn.count() > 0:
                    await btn.click()
                    print("[PH]      Button clicked")
                    await asyncio.sleep(1.5)
                else:
                    print("[PH]      Button not found - trying by text...")
                    await self.page.get_by_role("button", name="Saved").or_(
                        self.page.get_by_role("button", name="View")
                    ).first.click()
                    await asyncio.sleep(1.5)
            except Exception as e:
                print(f"[PH]      Could not click saved searches button: {e}")
                return False

            # Select "Daniel's Filter"
            print("[PH]    Selecting 'Daniel's Filter'...")
            daniels_filter_selector = '#modal-content > planhub-project-manage-filters-modal > div.table-container > table > tbody > tr > td.mat-cell.cdk-cell.cdk-column-name.mat-column-name.ng-star-inserted'

            try:
                cell = self.page.locator(daniels_filter_selector)
                if await cell.count() > 0:
                    await cell.click()
                    print("[PH]      Daniel's Filter selected")
                    await asyncio.sleep(2)

                    # Click outside to close modal
                    await self.page.locator('body').click(position={'x': 0, 'y': 0})
                    print("[PH]      Waiting for results to update...")
                    await asyncio.sleep(3)
                else:
                    print("[PH]      Daniel's Filter not found - trying by text...")
                    daniel_cell = self.page.locator('td').filter(has_text="Daniel")
                    if await daniel_cell.count() > 0:
                        await daniel_cell.first.click()
                        print("[PH]      Found and clicked by text")
                        await asyncio.sleep(3)
                    else:
                        print("[PH]      Could not find Daniel's Filter")
                        return False
            except Exception as e:
                print(f"[PH]      Could not select Daniel's Filter: {e}")
                return False

            print("[PH] Saved search filter applied successfully")
            return True

        except Exception as e:
            print(f"[PH] Error applying filters: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def get_project_rows(self):
        """Get project rows from the table."""
        try:
            print("[PH] Waiting for project table...")
            table_selector = 'planhub-project-table table tbody'
            await self.page.wait_for_selector(table_selector, timeout=15000)

            # Auto-scroll to load more projects
            print("[PH] Auto-scrolling to load projects...")
            previous_height = 0
            for _ in range(5):
                await self.page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                await asyncio.sleep(2)
                new_height = await self.page.evaluate('document.body.scrollHeight')
                if new_height == previous_height:
                    break
                previous_height = new_height

            row_selector = 'planhub-project-table table tbody tr.mat-row'
            rows = self.page.locator(row_selector)
            count = await rows.count()

            print(f"[PH] Found {count} project rows")
            return rows
        except Exception as e:
            print(f"[PH] Could not get project rows: {e}")
            try:
                debug_path = os.path.join(self.download_dir, 'ph_no_rows_debug.png')
                await self.page.screenshot(path=debug_path, full_page=True)
                print(f"[PH] Saved debug screenshot to: {debug_path}")
            except:
                pass
            return None

    async def check_sprinkler_keywords(self, text):
        """Check if text contains sprinkler-related keywords."""
        if not text:
            return False

        text_lower = text.lower()
        for keyword in self.config.SPRINKLER_KEYWORDS:
            if keyword.lower() in text_lower:
                print(f"     Found sprinkler keyword: '{keyword}'")
                return True
        return False

    async def extract_project_details(self, row_locator, index):
        """Extract details from a project row using Playwright locators."""
        print(f"[PH]    Extracting project {index + 1}...")

        try:
            project_name = "N/A"
            bid_date = "N/A"
            location = "N/A"

            # Extract Project Name
            name_selectors = [
                'td.mat-column-project_name div span',
                'td.mat-column-project_name span',
                'td.cdk-column-project_name span',
            ]
            for selector in name_selectors:
                try:
                    name_loc = row_locator.locator(selector)
                    if await name_loc.count() > 0:
                        text = await name_loc.first.text_content()
                        if text and text.strip():
                            project_name = text.strip()
                            break
                except:
                    continue

            # Extract Bid Date
            date_selectors = [
                'td.mat-column-bid_due_date',
                'td.cdk-column-bid_due_date',
            ]
            for selector in date_selectors:
                try:
                    date_loc = row_locator.locator(selector)
                    if await date_loc.count() > 0:
                        text = await date_loc.first.text_content()
                        if text and text.strip():
                            bid_date = text.strip()
                            break
                except:
                    continue

            # Extract Location
            loc_selectors = [
                'td.mat-column-location span',
                'td.cdk-column-location span',
                'td.mat-column-location',
            ]
            for selector in loc_selectors:
                try:
                    loc_loc = row_locator.locator(selector)
                    if await loc_loc.count() > 0:
                        text = await loc_loc.first.text_content()
                        if text and text.strip():
                            location = text.strip()
                            break
                except:
                    continue

            # Get full row text for sprinkler keyword check
            row_text = await row_locator.text_content()
            sprinklered = await self.check_sprinkler_keywords(row_text)

            # Generate unique ID
            project_id = f"planhub_{index}_{hash(project_name) % 10000}"

            details = {
                'id': project_id,
                'name': project_name,
                'gc': "N/A",
                'company': "N/A",
                'contact_name': "N/A",
                'bid_date': bid_date,
                'due_date': bid_date,
                'site': 'PlanHub',
                'source': 'PlanHub',
                'sprinklered': sprinklered,
                'location': location,
                'city': location.split(',')[0].strip() if ',' in location else location,
                'state': location.split(',')[1].strip() if ',' in location else "N/A",
                'trade': self.config.TRADE_FILTER,
                'url': self.config.PROJECT_LIST_URL,
                'extracted_at': datetime.now().isoformat(),
                'files_link': None,
                'download_link': None,
                'local_file_path': None,
            }

            print(f"[PH]      Name: {project_name[:40]}...")
            print(f"[PH]      Bid Date: {bid_date}")
            print(f"[PH]      Location: {location}")

            return details

        except Exception as e:
            print(f"[PH]      Error extracting details: {e}")
            import traceback
            traceback.print_exc()
            return None

    async def _click_row_and_open_details(self, lead):
        """
        Click a project row and navigate to its details page.
        Uses Playwright's built-in waiting and locator strategies.

        Returns:
            bool: True if successfully navigated to details page.
        """
        project_name = lead['name']
        print(f"[PH]    Clicking project row for: {project_name[:40]}...")

        # Strategy 1: Click the row by matching text content
        row_clicked = False
        try:
            row = self.page.locator('planhub-project-table table tbody tr.mat-row').filter(has_text=project_name)
            if await row.count() > 0:
                # Click the project name cell specifically
                name_cell = row.first.locator('td.mat-column-project_name')
                if await name_cell.count() > 0:
                    await name_cell.click()
                else:
                    await row.first.click()
                row_clicked = True
                print("[PH]    Clicked row via Playwright locator")
        except Exception as e:
            print(f"[PH]    Row locator click failed: {e}")

        # Strategy 2: JS fallback
        if not row_clicked:
            safe_name = project_name.replace('"', '\\"').replace("'", "\\'")
            row_clicked = await self.page.evaluate(f'''() => {{
                const rows = document.querySelectorAll('planhub-project-table tbody tr');
                for (const row of rows) {{
                    if (row.textContent.includes("{safe_name}")) {{
                        const nameCell = row.querySelector('td.mat-column-project_name') || row.querySelector('td:first-child');
                        if (nameCell) nameCell.click();
                        else row.click();
                        return true;
                    }}
                }}
                return false;
            }}''')
            if row_clicked:
                print("[PH]    Clicked row via JS fallback")
            else:
                print("[PH]    Could not find row to click")
                return False

        await asyncio.sleep(2)

        # Check if we went straight to details (unlikely but check)
        current_url = self.page.url
        if '/project/' in current_url and '/list' not in current_url:
            print("[PH]    Direct navigation to details page")
            return True

        # Wait for quick view panel to appear
        print("[PH]    Waiting for quick view panel...")
        try:
            await self.page.locator('planhub-project-quick-view').wait_for(timeout=5000)
            print("[PH]    Quick view panel detected")
        except:
            print("[PH]    Quick view panel not detected, continuing anyway...")

        # Strategy A: Click "View Project Details" using the exact config CSS selector
        try:
            details_btn = self.page.locator(self.config.MORE_DETAILS_BTN_FULL)
            if await details_btn.count() > 0:
                await details_btn.click()
                print("[PH]    Clicked 'More Details' button via config selector")
                try:
                    await self.page.wait_for_url('**/project/**', timeout=8000)
                except:
                    await asyncio.sleep(3)
                current_url = self.page.url
                if '/project/' in current_url and '/list' not in current_url:
                    return True
        except Exception as e:
            print(f"[PH]    Config selector failed: {e}")

        # Strategy B: Click the button scoped within the quick view panel
        try:
            quick_view = self.page.locator('planhub-project-quick-view')
            view_btn = quick_view.locator('button').filter(has_text='View Project Details')
            if await view_btn.count() > 0:
                await view_btn.first.click()
                print("[PH]    Clicked 'View Project Details' via scoped panel locator")
                try:
                    await self.page.wait_for_url('**/project/**', timeout=8000)
                except:
                    await asyncio.sleep(3)
                current_url = self.page.url
                if '/project/' in current_url and '/list' not in current_url:
                    return True
        except Exception as e:
            print(f"[PH]    Scoped panel locator failed: {e}")

        # Strategy C: Click using broad Playwright text locator (get_by_role for precision)
        try:
            view_btn = self.page.get_by_role('button', name='View Project Details')
            if await view_btn.count() > 0:
                await view_btn.first.click()
                print("[PH]    Clicked 'View Project Details' via role locator")
                try:
                    await self.page.wait_for_url('**/project/**', timeout=8000)
                except:
                    await asyncio.sleep(3)
                current_url = self.page.url
                if '/project/' in current_url and '/list' not in current_url:
                    return True
        except Exception as e:
            print(f"[PH]    Role locator failed: {e}")

        # Strategy D: Find project detail link via JS and navigate directly
        try:
            nav_result = await self.page.evaluate('''() => {
                const allLinks = document.querySelectorAll('a');
                for (const link of allLinks) {
                    const href = link.getAttribute('href') || '';
                    const fullHref = link.href || '';
                    const match = href.match(/\\/project\\/([a-zA-Z0-9_-]+)/) ||
                                  fullHref.match(/\\/project\\/([a-zA-Z0-9_-]+)/);
                    if (match && match[1] !== 'list') {
                        return fullHref || href;
                    }
                }
                const routerEls = document.querySelectorAll('[routerLink]');
                for (const el of routerEls) {
                    const rl = el.getAttribute('routerLink') || '';
                    const match = rl.match(/\\/project\\/([a-zA-Z0-9_-]+)/);
                    if (match && match[1] !== 'list') {
                        return rl;
                    }
                }
                return null;
            }''')

            if nav_result:
                project_url = nav_result
                if project_url.startswith('/'):
                    project_url = f"https://supplier.planhub.com{project_url}"
                print(f"[PH]    Navigating to extracted URL: {project_url}")
                await self.page.goto(project_url, wait_until='domcontentloaded', timeout=30000)
                await asyncio.sleep(3)
                current_url = self.page.url
                if '/project/' in current_url and '/list' not in current_url:
                    return True
        except Exception as e:
            print(f"[PH]    JS URL extraction failed: {e}")

        # Strategy E: Gemini vision as last resort
        if self.gemini_browser:
            print("[PH]    All strategies failed, trying Gemini vision...")
            await self.gemini_browser.find_and_click(
                "the 'View Project Details' link or button in the quick view panel on the right side of the screen"
            )
            await asyncio.sleep(3)
            current_url = self.page.url
            if '/project/' in current_url and '/list' not in current_url:
                return True

        print("[PH]    Could not navigate to project details page")
        try:
            debug_path = os.path.join(self.download_dir, 'ph_nav_fail.png')
            await self.page.screenshot(path=debug_path, full_page=True)
            print(f"[PH]    Saved debug screenshot: {debug_path}")
        except:
            pass
        return False

    async def download_files_for_lead(self, lead):
        """
        Click row to open details, extract full address, download files.

        Workflow:
        1. Click project row to open details
        2. Extract full address
        3. Click 'Project Files' tab
        4. Click 'Select All'
        5. Click 'Download Files'
        """
        print(f"\n[PH] [Pass 2] Processing: {lead['name'][:40]}...")

        # PRE-CHECK: Check if file already exists in Google Drive
        if GDRIVE_AVAILABLE and should_use_gdrive():
            try:
                project_name_clean = "".join(c for c in lead['name'][:60] if c.isalnum() or c in ' -_').strip()
                expected_filename = f"{project_name_clean}.zip"

                print(f"[PH]    Checking for existing file in Drive: {expected_filename}...")
                existing = check_file_exists(expected_filename, source='PlanHub')

                if existing:
                    print(f"[PH]    Found existing file in Drive! Skipping download.")
                    lead['gdrive_file_id'] = existing.get('file_id')
                    lead['gdrive_link'] = existing.get('web_link')
                    lead['gdrive_download_link'] = existing.get('download_link')
                    lead['download_link'] = existing.get('web_link')
                    lead['storage_type'] = 'gdrive'

                    await self.extract_gc_info(lead)
                    return True
                else:
                    print("[PH]    File not found in Drive, proceeding with download.")
            except Exception as e:
                print(f"[PH]    Error in Drive pre-check: {e}")

        try:
            # Initialize Gemini browser if not already done
            if not self.gemini_browser and GEMINI_AVAILABLE and GeminiBrowser:
                self.gemini_browser = GeminiBrowser(self.page)
                print("[PH]    Initialized Gemini AI browser")

            # Step 1: Click row and navigate to details
            if not await self._click_row_and_open_details(lead):
                return False

            print("[PH]    Successfully navigated to details page")

            # Wait for details page content
            try:
                await self.page.wait_for_selector('app-project-details-v2', timeout=10000)
            except:
                await asyncio.sleep(2)

            # Extract full address
            try:
                addr_loc = self.page.locator('app-project-details-overview div.project-details div.description')
                if await addr_loc.count() > 0:
                    addr_text = await addr_loc.first.text_content()
                    if addr_text:
                        lead['full_address'] = addr_text.strip()
                        print(f"[PH]    Address: {addr_text.strip()[:50]}...")
            except:
                pass

            # Extract project description
            description_selectors = [
                '#project-info-container > div:nth-child(5) > div:nth-child(1) > div:nth-child(6) > div',
                'app-project-details-overview div.project-description',
                'app-project-details-overview .description-text',
                'app-project-details-overview .project-info .description',
                '.project-details .scope',
                '.project-details .notes'
            ]
            for desc_selector in description_selectors:
                try:
                    desc_loc = self.page.locator(desc_selector)
                    if await desc_loc.count() > 0:
                        desc_text = await desc_loc.first.text_content()
                        if desc_text and desc_text.strip():
                            lead['description'] = desc_text.strip()
                            print(f"[PH]    Description: {desc_text.strip()[:50]}...")
                            break
                except:
                    continue

            # Fallback: overview section for description
            if not lead.get('description'):
                try:
                    overview_text = await self.page.evaluate('''() => {
                        const overview = document.querySelector('app-project-details-overview');
                        if (!overview) return null;
                        const wrappers = overview.querySelectorAll('.wrapper, .project-details');
                        let text = '';
                        for (const wrapper of wrappers) {
                            const descriptions = wrapper.querySelectorAll('.description');
                            for (const desc of descriptions) {
                                if (desc.textContent.length > 50) {
                                    text += desc.textContent.trim() + ' ';
                                }
                            }
                        }
                        return text.trim() || null;
                    }''')
                    if overview_text:
                        lead['description'] = overview_text
                        print(f"[PH]    Description (from overview): {overview_text[:50]}...")
                except:
                    pass

            # Click "Project Files" tab
            print("[PH]    Clicking Project Files tab...")
            files_tab_clicked = False

            # Try Playwright text/role locators first
            try:
                files_tab = self.page.get_by_role("button", name="Project Files").or_(
                    self.page.get_by_text("Project Files", exact=True)
                )
                if await files_tab.count() > 0:
                    await files_tab.first.click()
                    await asyncio.sleep(2)
                    files_tab_clicked = True
                    print("[PH]    Files tab clicked via Playwright locator")
            except:
                pass

            # CSS fallbacks
            if not files_tab_clicked:
                files_tab_css_fallbacks = [
                    self.config.PROJECT_FILES_TAB,
                    'app-project-details-v2 planhub-button-toggle mat-button-toggle-group mat-button-toggle:nth-child(2) button',
                    'mat-button-toggle-group mat-button-toggle:nth-of-type(2) button',
                    '#mat-button-toggle-2-button',
                ]
                for css_sel in files_tab_css_fallbacks:
                    try:
                        tab_loc = self.page.locator(css_sel)
                        if await tab_loc.count() > 0:
                            await tab_loc.first.click()
                            await asyncio.sleep(2)
                            files_tab_clicked = True
                            print(f"[PH]    Files tab clicked via CSS: {css_sel}")
                            break
                    except:
                        continue

            # Gemini fallback
            if not files_tab_clicked and self.gemini_browser:
                files_tab_clicked = await self.gemini_browser.find_and_click(
                    "the 'Project Files' tab or 'Files' tab button (it's usually the second tab)"
                )
                if files_tab_clicked:
                    await asyncio.sleep(2)
                    print("[PH]    Files tab clicked via Gemini")

            if not files_tab_clicked:
                print("[PH]    Could not click Files tab")

            # Wait for file table
            print("[PH]    Waiting for file table to load...")
            await asyncio.sleep(2)

            # Check if there are files
            has_files = await self.page.evaluate(
                "() => document.querySelectorAll('planhub-project-file-table tbody tr, planhub-project-file-table .file-row, planhub-project-file-table div[class*=file]').length > 0"
            )
            if not has_files:
                print("[PH]    No files available for this project")
                await self.extract_gc_info(lead)
                return True

            # Click "Select All" checkbox
            print("[PH]    Selecting all files...")
            select_all_clicked = False

            select_all_css = [
                self.config.SELECT_ALL_FILES_CHECKBOX,
                'planhub-project-file-table planhub-checkbox mat-checkbox label',
                'planhub-project-file-table mat-checkbox label',
            ]
            for css_sel in select_all_css:
                try:
                    cb_loc = self.page.locator(css_sel)
                    if await cb_loc.count() > 0:
                        await cb_loc.first.click()
                        await asyncio.sleep(1)
                        select_all_clicked = True
                        print(f"[PH]    Select All clicked via CSS")
                        break
                except:
                    continue

            if not select_all_clicked and self.gemini_browser:
                select_all_clicked = await self.gemini_browser.find_and_click(
                    "the 'Select All' checkbox at the top of the file list"
                )
                if select_all_clicked:
                    await asyncio.sleep(1)
                    print("[PH]    Select All clicked via Gemini")

            # Get files before download
            files_before = set(os.listdir(self.download_dir)) if os.path.exists(self.download_dir) else set()

            # Click Download button
            print("[PH]    Clicking Download button...")
            download_clicked = False

            download_css = [
                self.config.DOWNLOAD_FILES_BTN,
                'planhub-project-file-table planhub-button button',
                'planhub-project-file-table div planhub-button button',
            ]
            for css_sel in download_css:
                try:
                    dl_loc = self.page.locator(css_sel)
                    if await dl_loc.count() > 0:
                        await dl_loc.first.click()
                        print("[PH]    Download clicked via CSS, waiting...")
                        await asyncio.sleep(10)
                        download_clicked = True
                        break
                except:
                    continue

            if not download_clicked and self.gemini_browser:
                download_clicked = await self.gemini_browser.find_and_click(
                    "the 'Download' button (it downloads the selected files)"
                )
                if download_clicked:
                    print("[PH]    Download clicked via Gemini, waiting...")
                    await asyncio.sleep(10)

            if not download_clicked:
                print("[PH]    Could not click Download button")
                try:
                    debug_path = os.path.join(self.download_dir, 'ph_download_fail.png')
                    await self.page.screenshot(path=debug_path, full_page=True)
                except:
                    pass

            # Check for new files
            files_after = set(os.listdir(self.download_dir)) if os.path.exists(self.download_dir) else set()
            new_files = files_after - files_before

            if new_files:
                new_file = sorted(new_files, key=lambda f: os.path.getmtime(os.path.join(self.download_dir, f)))[-1]
                local_path = os.path.join(self.download_dir, new_file)
                print(f"[PH]    Downloaded: {new_file}")

                # Try to upload to Google Drive
                if GDRIVE_AVAILABLE:
                    gdrive_status = get_status()
                    print(f"[PH]    Google Drive status: {gdrive_status}")

                    use_gdrive = should_use_gdrive()
                    if not use_gdrive and gdrive_status.get('configured') and not gdrive_status.get('authenticated'):
                        print("[PH]    Google Drive configured but not authenticated - attempting auth...")
                        try:
                            from services.google_drive import authenticate
                            creds = authenticate()
                            if creds:
                                print("[PH]    Google Drive authentication successful!")
                                use_gdrive = True
                            else:
                                print("[PH]    Google Drive authentication failed")
                        except Exception as auth_err:
                            print(f"[PH]    Google Drive auth error: {auth_err}")
                else:
                    use_gdrive = False
                    print("[PH]    Google Drive not available")

                if use_gdrive:
                    try:
                        project_name_clean = "".join(c for c in lead['name'][:60] if c.isalnum() or c in ' -_').strip()
                        ext = os.path.splitext(new_file)[1] or '.zip'
                        gdrive_filename = f"{project_name_clean}{ext}"

                        result = upload_and_cleanup(
                            local_path,
                            filename=gdrive_filename,
                            source='PlanHub',
                            delete_local=True
                        )

                        if result:
                            lead['gdrive_file_id'] = result.get('file_id')
                            lead['gdrive_link'] = result.get('web_link')
                            lead['gdrive_download_link'] = result.get('download_link')
                            lead['download_link'] = result.get('web_link')
                            lead['storage_type'] = 'gdrive'
                            print(f"[PH]    SUCCESS! Uploaded to Google Drive: {result.get('web_link', '')[:60]}...")
                        else:
                            print("[PH]    Google Drive upload failed, keeping local file")
                            web_path = f"/downloads/{new_file}"
                            lead['local_file_path'] = web_path
                            lead['download_link'] = web_path
                            lead['storage_type'] = 'local'
                    except Exception as e:
                        print(f"[PH]    Google Drive error: {e}, keeping local file")
                        import traceback
                        traceback.print_exc()
                        web_path = f"/downloads/{new_file}"
                        lead['local_file_path'] = web_path
                        lead['download_link'] = web_path
                        lead['storage_type'] = 'local'
                else:
                    web_path = f"/downloads/{new_file}"
                    lead['local_file_path'] = web_path
                    lead['downloaded_file'] = new_file
                    lead['download_link'] = web_path
                    lead['storage_type'] = 'local'
                    print(f"[PH]    Saved locally: {web_path}")
            else:
                print("[PH]    No new files detected")

            # Extract GC info
            await self.extract_gc_info(lead)

            return True

        except Exception as e:
            print(f"[PH]    Error in download process: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def extract_gc_info(self, lead):
        """Extract General Contractor information from the project details page."""
        print("[PH]    Extracting GC information...")

        try:
            # Click "General Contractors" tab
            gc_tab_clicked = False

            # Try by button text first
            try:
                gc_btn = self.page.get_by_role("button", name="General Contractors").or_(
                    self.page.get_by_text("General Contractors", exact=False)
                )
                if await gc_btn.count() > 0:
                    await gc_btn.first.click()
                    await asyncio.sleep(2)
                    gc_tab_clicked = True
                    print("[PH]      GC tab opened via text locator")
            except:
                pass

            if not gc_tab_clicked:
                try:
                    gc_tab = self.page.locator('#mat-button-toggle-4-button')
                    if await gc_tab.count() > 0:
                        await gc_tab.click()
                        await asyncio.sleep(2)
                        gc_tab_clicked = True
                        print("[PH]      GC tab opened via ID")
                except:
                    pass

            if not gc_tab_clicked:
                clicked = await self.page.evaluate('''() => {
                    const btns = Array.from(document.querySelectorAll('mat-button-toggle button'));
                    const btn = btns.find(b => b.textContent.includes('General') || b.textContent.includes('Contractor'));
                    if (btn) { btn.click(); return true; }
                    return false;
                }''')
                if clicked:
                    await asyncio.sleep(2)
                    gc_tab_clicked = True
                else:
                    print("[PH]      GC tab not found")
                    return

            # Find GC cards
            gc_card_selector = 'planhub-project-general-contractor-card'
            gc_cards = self.page.locator(gc_card_selector)
            card_count = await gc_cards.count()

            if card_count == 0:
                print("[PH]      No GC cards found")
                return

            # Find preferred GC card (or use first)
            preferred_index = 0
            for i in range(card_count):
                card = gc_cards.nth(i)
                has_preferred = await card.evaluate('''(card) => {
                    const badge = card.querySelector('mat-icon');
                    return badge && (badge.textContent.includes('star') || card.textContent.includes('Preferred'));
                }''')
                if has_preferred:
                    preferred_index = i
                    break

            preferred_card = gc_cards.nth(preferred_index)

            # Extract company name
            company_name = await preferred_card.evaluate('''(card) => {
                const nameEl = card.querySelector('.company-name') ||
                               card.querySelector('mat-card-title') ||
                               card.querySelector('.name');
                if (nameEl && nameEl.textContent.trim()) return nameEl.textContent.trim();
                const bolds = card.querySelectorAll('strong, b, .bold');
                for (const b of bolds) {
                    if (b.textContent.length > 3) return b.textContent.trim();
                }
                return null;
            }''')

            if company_name:
                lead['gc'] = company_name
                lead['company'] = company_name
                print(f"[PH]      Company: {company_name}")

            # Extract contact name
            contact_name = await preferred_card.evaluate('''(card) => {
                const content = card.querySelector('mat-card-content');
                if (!content) return null;
                const divs = content.querySelectorAll('div.content > div');
                for (const div of divs) {
                    const icon = div.querySelector('mat-icon');
                    if (icon && (icon.textContent.includes('person') || icon.textContent.includes('account'))) {
                        const text = div.textContent.replace(icon.textContent, '').trim();
                        if (text) return text;
                    }
                }
                if (divs.length >= 2) {
                    return divs[1].textContent.trim();
                }
                return null;
            }''')

            if contact_name:
                lead['contact_name'] = contact_name
                print(f"[PH]      Contact: {contact_name}")

            # Extract phone number
            phone = await preferred_card.evaluate('''(card) => {
                const anchors = card.querySelectorAll('planhub-anchor a, a[href^="tel:"]');
                for (const a of anchors) {
                    const href = a.getAttribute('href') || '';
                    if (href.startsWith('tel:')) {
                        return href.replace('tel:', '').trim();
                    }
                    const text = a.textContent.trim();
                    if (text.match(/[\\d\\-\\(\\)\\s]{10,}/)) {
                        return text;
                    }
                }
                const text = card.textContent;
                const phoneMatch = text.match(/\\(?\\d{3}\\)?[\\s\\-]?\\d{3}[\\s\\-]?\\d{4}/);
                return phoneMatch ? phoneMatch[0] : null;
            }''')

            if phone:
                lead['contact_phone'] = phone
                print(f"[PH]      Phone: {phone}")

            # Extract email
            email = await preferred_card.evaluate('''(card) => {
                const anchors = card.querySelectorAll('planhub-anchor a, a[href^="mailto:"]');
                for (const a of anchors) {
                    const href = a.getAttribute('href') || '';
                    if (href.startsWith('mailto:')) {
                        return href.replace('mailto:', '').trim();
                    }
                    const text = a.textContent.trim();
                    if (text.includes('@')) {
                        return text;
                    }
                }
                const text = card.textContent;
                const emailMatch = text.match(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}/);
                return emailMatch ? emailMatch[0] : null;
            }''')

            if email:
                lead['contact_email'] = email
                print(f"[PH]      Email: {email}")

            print("[PH]      GC info extraction complete")

        except Exception as e:
            print(f"[PH]    Error in GC extraction: {e}")
            import traceback
            traceback.print_exc()

    async def scrape_all_projects(self, max_projects=None):
        """Main scraping logic for PlanHub (Two-Pass)."""
        log_status("=" * 40)
        log_status("Starting PlanHub scrape")

        if max_projects is None:
            max_projects = self.config.MAX_PROJECTS_DEFAULT

        # Navigate to projects
        if not await self.navigate_to_projects():
            log_status("Failed to navigate to projects")
            return []

        # Apply filters
        if not await self.apply_filters():
            log_status("Failed to apply filters, continuing anyway...")

        # --- PASS 1: Extract Details from Table ---
        log_status("=== PASS 1: Extracting Project Details ===")

        rows = await self.get_project_rows()
        if rows is None:
            log_status("No project rows found")
            return []

        row_count = await rows.count()
        projects_to_process = min(row_count, max_projects) if max_projects else row_count
        log_status(f"Processing {projects_to_process} of {row_count} rows...")

        valid_leads = []

        for index in range(projects_to_process):
            try:
                row_locator = rows.nth(index)
                details = await self.extract_project_details(row_locator, index)

                if not details:
                    continue

                if details['id'] in self.processed_ids:
                    log_status(f"Skipping duplicate: {details['id'][:20]}")
                    continue

                self.processed_ids.add(details['id'])

                if await self.is_project_past_due(details.get('bid_date', '')):
                    log_status(f"Skipping past due: {details['name'][:30]}")
                    continue

                log_status(f"Found: {details['name'][:40]}")
                valid_leads.append(details)
                self.leads.append(details)

            except Exception as e:
                log_status(f"Error extracting row {index}: {e}")
                continue

        log_status(f"=== PASS 1 Complete: Found {len(valid_leads)} valid leads ===")

        # --- PASS 2: Click into each project for details & files ---
        if valid_leads:
            log_status("=== PASS 2: Extracting Details & Files ===")
            for i, lead in enumerate(valid_leads):
                log_status(f"Processing {i+1}/{len(valid_leads)}: {lead.get('name', '')[:30]}")

                success = await self.download_files_for_lead(lead)

                if success:
                    log_status(f"Completed download for project {i+1}")

                # Return to list for next item
                log_status("Returning to project list...")
                await self.navigate_to_projects()
                await asyncio.sleep(2)

        log_status(f"SCRAPING COMPLETE - Total leads: {len(self.leads)}")
        return self.leads

    async def run(self, max_projects=None):
        """Run the full scraping workflow."""
        try:
            await self.setup_browser()
            await self.scrape_all_projects(max_projects)
            await self.save_results()
            return self.leads
        except Exception as e:
            print(f" Fatal error: {e}")
            import traceback
            traceback.print_exc()
            if self.page:
                try:
                    debug_path = os.path.join(self.download_dir, 'fatal_error.png')
                    await self.page.screenshot(path=debug_path, full_page=True)
                    print(f"   Saved fatal error screenshot to: {debug_path}")
                except:
                    pass
            return []
        finally:
            await self.close_browser()


async def main():
    """Main entry point for standalone testing"""
    print("\n" + "="*60)
    print(" PLANHUB PLAYWRIGHT SCRAPER")
    print("="*60 + "\n")

    scraper = PlanHubScraper()
    leads = await scraper.run(max_projects=5)

    print("\n" + "="*60)
    print(f" FINAL RESULTS: Found {len(leads)} leads")
    print("="*60)

    if leads:
        for i, lead in enumerate(leads, 1):
            print(f"\nLead {i}:")
            print(f"  Name: {lead.get('name', 'N/A')}")
            print(f"  GC: {lead.get('gc', 'N/A')}")
            print(f"  Bid Date: {lead.get('bid_date', 'N/A')}")
            print(f"  Sprinklered: {lead.get('sprinklered', False)}")
    else:
        print("\n No leads found. Check the debug output above.")

    print("\n" + "="*60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
