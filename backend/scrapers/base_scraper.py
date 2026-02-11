"""
Base scraper class with common functionality for all Puppeteer scrapers.
"""
import os
import sys
import asyncio
import json
import warnings
from datetime import datetime, date
from pyppeteer import launch
from pathlib import Path
from abc import ABC, abstractmethod

# Suppress pyppeteer cleanup warnings
warnings.filterwarnings('ignore', category=RuntimeWarning, message='.*coroutine.*never awaited.*')

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import ScraperConfig, DATE_FORMATS


class BaseScraper(ABC):
    """
    Abstract base class for all Puppeteer-based scrapers.

    Provides common functionality:
    - Browser initialization with Chrome profile
    - Safe text extraction with fallback selectors
    - Date parsing and validation
    - Past-due date checking
    - Navigation utilities with retry logic
    - Error recovery patterns
    - Results saving
    """

    def __init__(self, config=None):
        """
        Initialize scraper with configuration.

        Args:
            config: Configuration class (defaults to ScraperConfig)
        """
        self.config = config or ScraperConfig()
        self.browser = None
        self.page = None
        self.leads = []
        self.download_dir = self.config.DOWNLOAD_DIR

        # Ensure download directory exists
        os.makedirs(self.download_dir, exist_ok=True)

    def find_chrome_executable(self):
        """
        Find Chrome executable on the system.

        Returns:
            str: Path to Chrome executable or None if not found
        """
        import platform

        system = platform.system()
        possible_paths = []

        if system == 'Windows':
            possible_paths = [
                r'C:\Program Files\Google\Chrome\Application\chrome.exe',
                r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
                os.path.expanduser(r'~\AppData\Local\Google\Chrome\Application\chrome.exe'),
            ]
        elif system == 'Darwin':  # macOS
            possible_paths = [
                '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
            ]
        elif system == 'Linux':
            # Comprehensive Linux/Raspberry Pi paths
            possible_paths = [
                '/usr/bin/chromium-browser',      # Debian/Ubuntu/Raspberry Pi OS
                '/usr/bin/chromium',              # Arch/Fedora
                '/usr/bin/google-chrome',         # Google Chrome
                '/usr/bin/google-chrome-stable',  # Google Chrome stable
                '/snap/bin/chromium',             # Snap installation
                '/usr/lib/chromium-browser/chromium-browser',  # Alternative location
                '/usr/lib/chromium/chromium',     # Alternative location
            ]

        for path in possible_paths:
            if os.path.exists(path):
                return path

        return None

    async def setup_browser(self):
        """Initialize browser with profile and settings"""
        # Find Chrome executable
        chrome_path = self.find_chrome_executable()
        if not chrome_path:
            print("WARNING: Chrome not found in standard locations. Attempting default...")
            chrome_path = None  # Let pyppeteer try to find it
        else:
            print(f"[OK] Found Chrome at: {chrome_path}")

        # CLEANUP: Kill stale Chrome processes and remove SingletonLock
        # This is critical for headless mode stability on Windows
        try:
            # Kill ONLY the specific chrome processes for this user data dir
            if os.name == 'nt':
                # Use PowerShell to find processes with the specific user data directory in command line
                user_data_dir_name = os.path.basename(self.config.CHROME_USER_DATA_DIR)
                ps_cmd = (
                    f"Get-CimInstance Win32_Process | "
                    f"Where-Object {{ $_.Name -eq 'chrome.exe' -and $_.CommandLine -like '*{user_data_dir_name}*' }} | "
                    f"Stop-Process -Force"
                )
                subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True)
                await asyncio.sleep(1) # Wait for release
            
            # Remove SingletonLock if it exists
            lock_file = os.path.join(self.config.CHROME_USER_DATA_DIR, 'SingletonLock')
            if os.path.exists(lock_file):
                try:
                    os.remove(lock_file)
                    print(f" Removed stale lock file: {lock_file}")
                except Exception as e:
                    print(f" Warning: Could not remove lock file: {e}")
        except Exception as e:
            print(f" Cleanup warning: {e}")

        print(f"\n======== CHROME PROFILE CONFIG ========")
        print(f"User Data Dir:   {self.config.CHROME_USER_DATA_DIR}")
        print(f"Profile Name:    {self.config.CHROME_PROFILE_NAME}")
        print(f"Headless:        {self.config.HEADLESS}")
        print(f"Chrome Path:     {chrome_path or 'Auto-detect'}")
        print("=======================================\n")

        # Launch browser with profile
        launch_options = {
            'headless': self.config.HEADLESS,
            'userDataDir': self.config.CHROME_USER_DATA_DIR,
            'args': [
                f'--profile-directory={self.config.CHROME_PROFILE_NAME}',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-blink-features=AutomationControlled',
                '--disable-gpu',
                '--disable-software-rasterizer',
                '--disable-features=VizDisplayCompositor',
                '--mute-audio',
            ],
        }

        # Only set executablePath if we found Chrome
        if chrome_path:
            launch_options['executablePath'] = chrome_path

        # Retry launch logic
        for attempt in range(3):
            try:
                self.browser = await launch(**launch_options)
                break
            except Exception as e:
                print(f"   Browser launch failed (attempt {attempt+1}/3): {e}")
                if attempt == 2:
                    raise
                await asyncio.sleep(2)

        self.page = await self.browser.newPage()

        # Set viewport
        await self.page.setViewport({
            'width': self.config.VIEWPORT_WIDTH,
            'height': self.config.VIEWPORT_HEIGHT
        })

        # Set download behavior
        await self.page._client.send('Page.setDownloadBehavior', {
            'behavior': 'allow',
            'downloadPath': self.download_dir
        })

        print(" Browser initialized")

    async def navigate_with_retry(self, url, max_retries=3, wait_until='networkidle2'):
        """
        Navigate to URL with retry logic.

        Args:
            url: URL to navigate to
            max_retries: Maximum number of retry attempts
            wait_until: Pyppeteer wait condition ('networkidle2', 'load', etc.)

        Returns:
            bool: True if navigation successful, False otherwise
        """
        for attempt in range(max_retries):
            try:
                print(f" Navigating to {url}{'...' if attempt == 0 else f' (retry {attempt})...'}")
                await self.page.goto(
                    url,
                    {'waitUntil': wait_until, 'timeout': self.config.NAVIGATION_TIMEOUT}
                )
                await asyncio.sleep(self.config.DELAY_AFTER_NAVIGATION)
                print(" Navigation successful")
                return True
            except Exception as e:
                print(f" Navigation failed (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt == max_retries - 1:
                    print(f" Failed to navigate to {url} after {max_retries} attempts")
                    return False
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
        return False

    async def extract_text_safely(self, selectors, field_name="field"):
        """
        Try multiple selectors and return text content.

        Args:
            selectors: List of CSS selectors to try
            field_name: Name of field for logging

        Returns:
            str: Extracted text or "N/A" if not found
        """
        for selector in selectors:
            try:
                element = await self.page.querySelector(selector)
                if element:
                    text = await self.page.evaluate('(element) => element.textContent', element)
                    if text and text.strip():
                        return text.strip()
            except Exception:
                continue
        print(f"   Could not extract {field_name}")
        return "N/A"

    async def extract_text_with_js(self, js_selector, field_name="field"):
        """
        Extract text using JavaScript evaluation.

        Args:
            js_selector: JavaScript code to find element (should return element)
            field_name: Name of field for logging

        Returns:
            str: Extracted text or "N/A" if not found
        """
        try:
            text = await self.page.evaluate(js_selector)
            if text and text.strip():
                return text.strip()
        except Exception as e:
            print(f"   Could not extract {field_name}: {e}")
        return "N/A"

    async def click_element_safely(self, selectors, field_name="element"):
        """
        Try to click element using multiple selector strategies.

        Args:
            selectors: List of selectors to try (CSS or text/)
            field_name: Name of element for logging

        Returns:
            bool: True if clicked successfully, False otherwise
        """
        for selector in selectors:
            try:
                if selector.startswith('text/'):
                    # Text-based selector
                    text = selector.split('text/')[1]
                    await self.page.evaluate(f'''() => {{
                        const elements = Array.from(document.querySelectorAll('*'));
                        const element = elements.find(el => el.textContent.includes('{text}'));
                        if (element) element.click();
                    }}''')
                else:
                    # CSS selector
                    await self.page.click(selector, {'timeout': self.config.SELECTOR_TIMEOUT})

                await asyncio.sleep(self.config.DELAY_AFTER_CLICK)
                return True
            except Exception:
                continue

        print(f"   Could not click {field_name}")
        return False

    async def wait_for_selector_safely(self, selector, timeout=None):
        """
        Wait for selector with timeout.

        Args:
            selector: CSS selector to wait for
            timeout: Timeout in milliseconds (defaults to config)

        Returns:
            bool: True if element found, False otherwise
        """
        timeout = timeout or self.config.SELECTOR_TIMEOUT
        try:
            await self.page.waitForSelector(selector, {'timeout': timeout})
            return True
        except Exception as e:
            print(f"   Selector not found: {selector} ({e})")
            # Take debug screenshot
            try:
                debug_path = os.path.join(self.download_dir, 'debug_selector_fail.png')
                await self.page.screenshot({'path': debug_path, 'fullPage': True})
                print(f"   Saved debug screenshot to: {debug_path}")
            except:
                pass
            return False

    def parse_date(self, date_str):
        """
        Parse date string into date object.

        Args:
            date_str: Date string to parse

        Returns:
            date: Parsed date object or None if parsing failed
        """
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
        """
        Check if project is past due by comparing due date with today.

        Args:
            due_date_str: Date string to check

        Returns:
            bool: True if past due, False otherwise
        """
        try:
            if not due_date_str or due_date_str == "N/A":
                # If no due date, assume it's valid
                return False

            today = date.today()
            parsed_date = self.parse_date(due_date_str)

            if parsed_date:
                is_past_due = parsed_date < today
                if is_past_due:
                    print(f"  ⏰ Past due: {due_date_str} (today: {today})")
                return is_past_due
            else:
                # If can't parse, assume it's valid
                return False

        except Exception as e:
            print(f" Error checking due date: {e}")
            return False

    async def save_results(self, output_file=None):
        """
        Save leads to JSON file.

        Args:
            output_file: Path to output file (defaults to config DB_FILE)
        """
        output_file = output_file or self.config.DB_FILE

        # Load existing leads if any
        existing_leads = []
        if os.path.exists(output_file):
            try:
                with open(output_file, 'r') as f:
                    existing_leads = json.load(f)
            except:
                existing_leads = []

        # Merge with new leads (avoiding duplicates by ID)
        existing_ids = {lead.get('id') for lead in existing_leads}
        new_leads = [lead for lead in self.leads if lead.get('id') not in existing_ids]

        all_leads = existing_leads + new_leads

        with open(output_file, 'w') as f:
            json.dump(all_leads, f, indent=2)

        print(f"\n Saved {len(new_leads)} new leads to {output_file}")
        print(f" Total leads in database: {len(all_leads)}")

    async def close_browser(self):
        """Close browser gracefully"""
        if self.browser:
            try:
                await self.browser.close()
                print("\n Browser closed")
            except Exception:
                pass  # Ignore cleanup errors

    @abstractmethod
    async def scrape_all_projects(self, max_projects=None):
        """
        Main scraping logic - to be implemented by subclasses.

        Args:
            max_projects: Maximum number of projects to scrape

        Returns:
            list: List of lead dictionaries
        """
        pass

    async def run(self, max_projects=None):
        """
        Run the full scraping workflow.

        Args:
            max_projects: Maximum number of projects to process (None = all projects)

        Returns:
            List of lead dictionaries
        """
        try:
            await self.setup_browser()
            await self.scrape_all_projects(max_projects)
            await self.save_results()
            return self.leads
        except Exception as e:
            print(f" Fatal error: {e}")
            import traceback
            traceback.print_exc()
            # Take critical error screenshot
            if self.page:
                try:
                    debug_path = os.path.join(self.download_dir, 'fatal_error.png')
                    await self.page.screenshot({'path': debug_path, 'fullPage': True})
                    print(f"   Saved fatal error screenshot to: {debug_path}")
                except:
                    pass
            return []
        finally:
            await self.close_browser()
