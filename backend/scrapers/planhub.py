"""
PlanHub Puppeteer scraper - deterministic browser automation.
"""
import os
import sys
import asyncio
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrapers.base_scraper import BaseScraper
from config import PlanHubConfig

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


class PlanHubScraper(BaseScraper):
    """
    PlanHub scraper using Puppeteer with deterministic navigation.

    Features:
    - Login handling with credentials from environment
    - Uses saved search "Daniel's Filter" for filtering
    - Past-due filtering using date comparison
    - Sprinkler keyword detection in project descriptions
    - Two-pass extraction: metadata first, then file downloads
    - Deduplication using processed_ids set
    """

    def __init__(self):
        super().__init__(config=PlanHubConfig())
        self.processed_ids = set()
        # Override viewport for PlanHub to ensure elements are visible
        self.config.VIEWPORT_WIDTH = 1920
        self.config.VIEWPORT_HEIGHT = 1080

    async def check_login_status(self):
        """
        Check if already logged in by looking for redirect or login elements.

        Returns:
            bool: True if logged in, False if needs login
        """
        try:
            # Check if we're on the project list page already
            current_url = self.page.url
            if 'supplier.planhub.com/project/list' in current_url:
                print(" Already logged in")
                return True

            # Check for login form elements
            login_form = await self.page.querySelector(self.config.LOGIN_EMAIL_SELECTOR)
            if login_form:
                print(" Login required")
                return False

            # Default to logged in
            return True
        except Exception as e:
            print(f" Could not determine login status: {e}")
            return False

    async def login(self):
        """
        Navigate to login page and authenticate.

        Returns:
            bool: True if login successful, False otherwise
        """
        print(" Logging in to PlanHub...")

        # Check credentials
        if not self.config.LOGIN_EMAIL or not self.config.LOGIN_PASSWORD:
            print(" Missing login credentials (PLANHUB_LOGIN/PLANHUB_PW)")
            return False

        # Navigate to login page
        if not await self.navigate_with_retry(self.config.LOGIN_URL):
            return False

        try:
            # Wait for login form
            await self.wait_for_selector_safely(self.config.LOGIN_EMAIL_SELECTOR)

            # Fill email
            await self.page.type(self.config.LOGIN_EMAIL_SELECTOR, self.config.LOGIN_EMAIL)
            print(f"   Entered email: {self.config.LOGIN_EMAIL}")

            # Fill password
            await self.page.type(self.config.LOGIN_PASSWORD_SELECTOR, self.config.LOGIN_PASSWORD)
            print("   Entered password")

            # Click submit button
            await self.page.click(self.config.LOGIN_SUBMIT_SELECTOR)
            print("   Submitted login form")

            # Wait for navigation
            await asyncio.sleep(3)

            # Verify login success
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
        """
        Navigate to project list page.

        Returns:
            bool: True if successful, False otherwise
        """
        print("[PH] Navigating to project list...")

        # Navigate to project list
        if not await self.navigate_with_retry(self.config.PROJECT_LIST_URL):
            return False

        # Check current URL
        current_url = self.page.url
        print(f"[PH] Current URL: {current_url}")

        # Check if login required
        if not await self.check_login_status():
            if not await self.login():
                return False
            # Navigate back to project list after login
            if not await self.navigate_with_retry(self.config.PROJECT_LIST_URL):
                return False

        return True

    async def apply_filters(self):
        """
        Load saved search filter "Daniel's Filter" instead of manually setting filters.

        Returns:
            bool: True if successful, False otherwise
        """
        print("[PH] Loading saved search filter...")

        try:
            # Wait for page to load
            await asyncio.sleep(2)

            # Click "View Saved Searches" button
            print("[PH]    Clicking 'View Saved Searches' button...")
            saved_searches_btn_selector = '#cdk-accordion-child-1 > div > div > planhub-persist-filters-actions > section > div > planhub-button:nth-child(4) > button'

            try:
                saved_searches_btn = await self.page.querySelector(saved_searches_btn_selector)
                if saved_searches_btn:
                    await saved_searches_btn.click()
                    print("[PH]      Button clicked")
                    await asyncio.sleep(1.5)
                else:
                    print("[PH]      Button not found - trying alternate selector...")
                    # Try clicking by text
                    await self.page.evaluate('''() => {
                        const btns = Array.from(document.querySelectorAll('button'));
                        const btn = btns.find(b => b.textContent.includes('Saved') || b.textContent.includes('View'));
                        if (btn) btn.click();
                    }''')
                    await asyncio.sleep(1.5)
            except Exception as e:
                print(f"[PH]      Could not click saved searches button: {e}")
                return False

            # Select "Daniel's Filter"
            print("[PH]    Selecting 'Daniel's Filter'...")
            daniels_filter_selector = '#modal-content > planhub-project-manage-filters-modal > div.table-container > table > tbody > tr > td.mat-cell.cdk-cell.cdk-column-name.mat-column-name.ng-star-inserted'

            try:
                daniels_filter = await self.page.querySelector(daniels_filter_selector)
                if daniels_filter:
                    await daniels_filter.click()
                    print("[PH]      Daniel's Filter selected")
                    await asyncio.sleep(2)

                    # Click outside to close modal and trigger refresh
                    await self.page.evaluate('() => document.body.click()')
                    print("[PH]      Waiting for results to update...")
                    await asyncio.sleep(3)
                else:
                    print("[PH]      Daniel's Filter not found - trying by text...")
                    # Try finding by text content
                    found = await self.page.evaluate('''() => {
                        const cells = Array.from(document.querySelectorAll('td'));
                        const cell = cells.find(c => c.textContent.includes("Daniel"));
                        if (cell) { cell.click(); return true; }
                        return false;
                    }''')
                    if found:
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
        """
        Get project rows from the table using precise selectors.

        Returns:
            list: List of project row elements
        """
        try:
            # Wait for table to load
            print("[PH] Waiting for project table...")
            table_selector = 'planhub-project-table table tbody'
            await self.wait_for_selector_safely(table_selector, timeout=15000)

            # Auto-scroll to load more projects
            print("[PH] Auto-scrolling to load projects...")
            previous_height = 0
            for _ in range(5): # Scroll 5 times or until no new content
                await self.page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                await asyncio.sleep(2)
                new_height = await self.page.evaluate('document.body.scrollHeight')
                if new_height == previous_height:
                    break
                previous_height = new_height
            
            # Get all project rows - use precise selector
            row_selector = 'planhub-project-table table tbody tr.mat-row'
            rows = await self.page.querySelectorAll(row_selector)

            print(f"[PH] Found {len(rows)} project rows")
            return rows
        except Exception as e:
            print(f"[PH] Could not get project rows: {e}")
            # Take debug screenshot
            try:
                debug_path = os.path.join(self.download_dir, 'ph_no_rows_debug.png')
                await self.page.screenshot({'path': debug_path, 'fullPage': True})
                print(f"[PH] Saved debug screenshot to: {debug_path}")
            except:
                pass
            return []

    async def check_sprinkler_keywords(self, text):
        """
        Check if text contains sprinkler-related keywords.

        Args:
            text: Text to search for keywords

        Returns:
            bool: True if sprinkler keywords found
        """
        if not text:
            return False

        text_lower = text.lower()
        for keyword in self.config.SPRINKLER_KEYWORDS:
            if keyword.lower() in text_lower:
                print(f"     Found sprinkler keyword: '{keyword}'")
                return True
        return False

    async def extract_project_details(self, row_element, index):
        """
        Extract details from a project row using precise selectors.

        Args:
            row_element: Pyppeteer element handle for the row
            index: Row index for ID generation

        Returns:
            dict: Project details or None if extraction failed
        """
        print(f"[PH]    Extracting project {index + 1}...")

        try:
            project_name = "N/A"
            bid_date = "N/A"
            location = "N/A"

            # Extract Project Name - td.mat-column-project_name span
            name_selectors = [
                'td.mat-column-project_name div span',
                'td.mat-column-project_name span',
                'td.cdk-column-project_name span',
            ]
            for selector in name_selectors:
                try:
                    name_elem = await row_element.querySelector(selector)
                    if name_elem:
                        text = await self.page.evaluate('(el) => el.textContent', name_elem)
                        if text and text.strip():
                            project_name = text.strip()
                            break
                except:
                    continue

            # Extract Bid Date - td.mat-column-bid_due_date
            date_selectors = [
                'td.mat-column-bid_due_date',
                'td.cdk-column-bid_due_date',
            ]
            for selector in date_selectors:
                try:
                    date_elem = await row_element.querySelector(selector)
                    if date_elem:
                        text = await self.page.evaluate('(el) => el.textContent', date_elem)
                        if text and text.strip():
                            bid_date = text.strip()
                            break
                except:
                    continue

            # Extract Location - td.mat-column-location span
            loc_selectors = [
                'td.mat-column-location span',
                'td.cdk-column-location span',
                'td.mat-column-location',
            ]
            for selector in loc_selectors:
                try:
                    loc_elem = await row_element.querySelector(selector)
                    if loc_elem:
                        text = await self.page.evaluate('(el) => el.textContent', loc_elem)
                        if text and text.strip():
                            location = text.strip()
                            break
                except:
                    continue

            # Get full row text for sprinkler keyword check
            row_text = await self.page.evaluate('(el) => el.textContent', row_element)
            sprinklered = await self.check_sprinkler_keywords(row_text)

            # Generate unique ID
            project_id = f"planhub_{index}_{hash(project_name) % 10000}"

            # Build details object
            details = {
                'id': project_id,
                'name': project_name,
                'gc': "N/A",  # Will be extracted from detail page
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

    async def download_files_for_lead(self, lead, row_element=None):
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
                # Construct expected filename same as we do during upload
                project_name_clean = "".join(c for c in lead['name'][:60] if c.isalnum() or c in ' -_').strip()
                # We assume .zip since PlanHub is almost always a zip, but if it varies we might miss it.
                # However, this is a safe optimization.
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
                    
                    # Still populate GC info if possible
                    await self.extract_gc_info(lead)
                    return True
                else:
                    print("[PH]    File not found in Drive, proceeding with download.")
            except Exception as e:
                print(f"[PH]    Error in Drive pre-check: {e}")

        try:
            # Extract project URL from the row and navigate directly
            print("[PH]    Extracting project URL from row...")

            project_url = None
            safe_name = lead['name'].replace('"', '\\"').replace("'", "\\'")

            # Try to extract project URL/ID from the row
            if row_element:
                project_url = await self.page.evaluate('''(row) => {
                    // Look for any link in the row that points to project details
                    const links = row.querySelectorAll('a[href*="/project/"]');
                    for (const link of links) {
                        const href = link.getAttribute('href');
                        if (href && !href.includes('/list')) {
                            return href.startsWith('http') ? href : 'https://supplier.planhub.com' + href;
                        }
                    }
                    // Look for data attributes with project ID
                    const projectId = row.getAttribute('data-project-id') ||
                                      row.querySelector('[data-project-id]')?.getAttribute('data-project-id') ||
                                      row.getAttribute('data-id');
                    if (projectId) {
                        return `https://supplier.planhub.com/project/${projectId}`;
                    }
                    // Look for routerLink attribute
                    const routerLink = row.querySelector('[routerlink*="/project/"]');
                    if (routerLink) {
                        const rl = routerLink.getAttribute('routerlink');
                        return rl.startsWith('http') ? rl : 'https://supplier.planhub.com' + rl;
                    }
                    return null;
                }''', row_element)

            # Fallback: search all rows by project name
            if not project_url:
                project_url = await self.page.evaluate(f'''() => {{
                    const rows = document.querySelectorAll('planhub-project-table tbody tr');
                    for (const row of rows) {{
                        if (row.textContent.includes("{safe_name}")) {{
                            // Look for link
                            const links = row.querySelectorAll('a[href*="/project/"]');
                            for (const link of links) {{
                                const href = link.getAttribute('href');
                                if (href && !href.includes('/list')) {{
                                    return href.startsWith('http') ? href : 'https://supplier.planhub.com' + href;
                                }}
                            }}
                            // Look for data-project-id
                            const projectId = row.getAttribute('data-project-id') ||
                                              row.querySelector('[data-project-id]')?.getAttribute('data-project-id');
                            if (projectId) {{
                                return `https://supplier.planhub.com/project/${{projectId}}`;
                            }}
                        }}
                    }}
                    return null;
                }}''')

            # Last fallback: Look in the entire page for project links matching the name
            if not project_url:
                project_url = await self.page.evaluate(f'''() => {{
                    // Find any anchor that contains the project name and links to /project/
                    const allLinks = document.querySelectorAll('a[href*="/project/"]');
                    for (const link of allLinks) {{
                        if (link.textContent.includes("{safe_name}") && !link.href.includes('/list')) {{
                            return link.href;
                        }}
                    }}
                    // Try to find project ID from Angular state or window object
                    if (window.__PLANHUB_PROJECTS__) {{
                        for (const p of window.__PLANHUB_PROJECTS__) {{
                            if (p.name && p.name.includes("{safe_name}")) {{
                                return `https://supplier.planhub.com/project/${{p.id}}`;
                            }}
                        }}
                    }}
                    return null;
                }}''')

            if project_url:
                print(f"[PH]    Found project URL: {project_url}")
                await self.page.goto(project_url, {'waitUntil': 'networkidle2', 'timeout': 30000})
                await asyncio.sleep(2)
            else:
                print("[PH]    Could not extract project URL, trying click fallback...")
                # Click fallback
                clicked = await self.page.evaluate(f'''() => {{
                    const rows = document.querySelectorAll('planhub-project-table tbody tr');
                    for (const row of rows) {{
                        if (row.textContent.includes("{safe_name}")) {{
                            const nameCell = row.querySelector('td.mat-column-project_name span, .project-name');
                            if (nameCell) nameCell.click();
                            else row.click();
                            return true;
                        }}
                    }}
                    return false;
                }}''')
                if not clicked:
                    print("[PH]    Could not find project row")
                    return False
                await asyncio.sleep(3)

            # Verify we're on details page
            print("[PH]    Verifying details page loaded...")
            current_url = self.page.url
            print(f"[PH]    Current URL: {current_url}")

            details_selector = 'app-project-details-v2'
            try:
                await self.page.waitForSelector(details_selector, {'timeout': 10000})
                print("[PH]    Details page loaded")
            except:
                # Check URL as fallback
                if '/project/' in current_url and '/list' not in current_url:
                    print("[PH]    URL indicates details page, continuing...")
                    await asyncio.sleep(2)
                else:
                    print("[PH]    Details page did not load, taking screenshot...")
                    try:
                        debug_path = os.path.join(self.download_dir, 'ph_details_fail.png')
                        await self.page.screenshot({'path': debug_path, 'fullPage': True})
                    except:
                        pass
                    return False

            # Extract full address
            address_selector = 'app-project-details-overview div.project-details div.description'
            try:
                addr_elem = await self.page.querySelector(address_selector)
                if addr_elem:
                    addr_text = await self.page.evaluate('(el) => el.textContent', addr_elem)
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
                    desc_elem = await self.page.querySelector(desc_selector)
                    if desc_elem:
                        desc_text = await self.page.evaluate('(el) => el.textContent', desc_elem)
                        if desc_text and desc_text.strip():
                            lead['description'] = desc_text.strip()
                            print(f"[PH]    Description: {desc_text.strip()[:50]}...")
                            break
                except:
                    continue

            # If no description found, try to get it from the overview section
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

            # Click "Project Files" tab (Page 2 / Plans tab)
            # Updated XPath: /html/body/planhub-main/div/mat-sidenav-container/mat-sidenav-content/app-root/div/app-project-details/div/app-project-details-v2/div/div/div[2]/planhub-button-toggle/mat-button-toggle-group/mat-button-toggle[2]/button/span/div/span
            print("[PH]    Clicking Project Files tab (Page 2)...")
            files_tab_xpath = '/html/body/planhub-main/div/mat-sidenav-container/mat-sidenav-content/app-root/div/app-project-details/div/app-project-details-v2/div/div/div[2]/planhub-button-toggle/mat-button-toggle-group/mat-button-toggle[2]/button/span/div/span'
            files_tab_css_fallbacks = [
                'app-project-details-v2 planhub-button-toggle mat-button-toggle-group mat-button-toggle:nth-child(2) button',
                'mat-button-toggle-group mat-button-toggle:nth-of-type(2) button',
                '#mat-button-toggle-2-button',
            ]
            try:
                files_tab = None
                # Try XPath first
                files_tab_elements = await self.page.xpath(files_tab_xpath)
                if files_tab_elements:
                    files_tab = files_tab_elements[0]
                    print("[PH]    Found files tab via XPath")
                else:
                    # Fallback to CSS selectors
                    for css_sel in files_tab_css_fallbacks:
                        files_tab = await self.page.querySelector(css_sel)
                        if files_tab:
                            print(f"[PH]    Found files tab via CSS: {css_sel}")
                            break

                if files_tab:
                    await files_tab.click()
                    await asyncio.sleep(3)
                    print("[PH]    Files tab opened")
                else:
                    print("[PH]    Files tab not found with any selector")
                    try:
                        debug_path = os.path.join(self.download_dir, 'ph_files_tab_fail.png')
                        await self.page.screenshot({'path': debug_path, 'fullPage': True})
                    except:
                        pass
            except Exception as e:
                print(f"[PH]    Error clicking files tab: {e}")

            # Wait for file table to load
            print("[PH]    Waiting for file table to load...")
            await asyncio.sleep(2)

            # Check if there are files
            has_files = await self.page.evaluate("() => document.querySelectorAll('planhub-project-file-table tbody tr, planhub-project-file-table .file-row, planhub-project-file-table div[class*=file]').length > 0")
            if not has_files:
                print("[PH]    No files available for this project")
                return True

            # Click "Select All" checkbox
            # Updated XPath: /html/body/planhub-main/div/mat-sidenav-container/mat-sidenav-content/app-root/div/app-project-details/div/app-project-details-v2/div/div/div[2]/mat-card/planhub-project-file-table/div/div[1]/div/planhub-checkbox/mat-checkbox/label/span[1]/span[3]
            print("[PH]    Selecting all files...")
            select_all_xpath = '/html/body/planhub-main/div/mat-sidenav-container/mat-sidenav-content/app-root/div/app-project-details/div/app-project-details-v2/div/div/div[2]/mat-card/planhub-project-file-table/div/div[1]/div/planhub-checkbox/mat-checkbox/label/span[1]/span[3]'
            select_all_css_fallbacks = [
                'planhub-project-file-table planhub-checkbox mat-checkbox label',
                'planhub-project-file-table planhub-checkbox mat-checkbox',
                'planhub-project-file-table mat-checkbox label',
                '#mat-checkbox-1 label',
            ]
            try:
                select_all = None
                # Try XPath first
                select_all_elements = await self.page.xpath(select_all_xpath)
                if select_all_elements:
                    select_all = select_all_elements[0]
                    print("[PH]    Found Select All via XPath")
                else:
                    for css_sel in select_all_css_fallbacks:
                        select_all = await self.page.querySelector(css_sel)
                        if select_all:
                            print(f"[PH]    Found Select All via CSS: {css_sel}")
                            break

                if select_all:
                    await select_all.click()
                    await asyncio.sleep(1)
                    print("[PH]    All files selected")
                else:
                    print("[PH]    Select All checkbox not found")
            except Exception as e:
                print(f"[PH]    Error selecting files: {e}")

            # Click Download button
            # Updated XPath: /html/body/planhub-main/div/mat-sidenav-container/mat-sidenav-content/app-root/div/app-project-details/div/app-project-details-v2/div/div/div[2]/mat-card/planhub-project-file-table/div/div[1]/planhub-button/button/span[1]/span
            print("[PH]    Clicking Download...")
            download_btn_xpath = '/html/body/planhub-main/div/mat-sidenav-container/mat-sidenav-content/app-root/div/app-project-details/div/app-project-details-v2/div/div/div[2]/mat-card/planhub-project-file-table/div/div[1]/planhub-button/button/span[1]/span'
            download_btn_css_fallbacks = [
                'planhub-project-file-table planhub-button button',
                'planhub-project-file-table div planhub-button button',
            ]
            download_btn = None
            try:
                download_btn_elements = await self.page.xpath(download_btn_xpath)
                if download_btn_elements:
                    download_btn = download_btn_elements[0]
                    print("[PH]    Found Download button via XPath")
                else:
                    for css_sel in download_btn_css_fallbacks:
                        download_btn = await self.page.querySelector(css_sel)
                        if download_btn:
                            print(f"[PH]    Found Download button via CSS: {css_sel}")
                            break
            except Exception as e:
                print(f"[PH]    Error finding download button: {e}")

            download_btn_selector = 'planhub-project-file-table planhub-button button'

            # Get files before download
            files_before = set(os.listdir(self.download_dir)) if os.path.exists(self.download_dir) else set()

            try:
                # Use pre-located download_btn from XPath, fall back to CSS if needed
                if not download_btn:
                    download_btn = await self.page.querySelector(download_btn_selector)
                if download_btn:
                    await download_btn.click()
                    print("[PH]    Download initiated, waiting...")
                    await asyncio.sleep(10)
                else:
                    print("[PH]    Download button not found!")
                    try:
                        debug_path = os.path.join(self.download_dir, 'ph_download_btn_fail.png')
                        await self.page.screenshot({'path': debug_path, 'fullPage': True})
                    except:
                        pass
            except Exception as e:
                print(f"[PH]    Error clicking download: {e}")

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
                        # Create a stable, descriptive filename (no timestamp to prevent GDrive duplicates)
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
                            # Fallback to local storage
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
                    # Local storage only
                    web_path = f"/downloads/{new_file}"
                    lead['local_file_path'] = web_path
                    lead['downloaded_file'] = new_file
                    lead['download_link'] = web_path
                    lead['storage_type'] = 'local'
                    print(f"[PH]    Saved locally: {web_path}")
            else:
                print("[PH]    No new files detected")

            # Step 21: Click "General Contractors" tab
            await self.extract_gc_info(lead)

            return True

        except Exception as e:
            print(f"[PH]    Error in download process: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def extract_gc_info(self, lead):
        """
        Extract General Contractor information from the project details page.

        Steps 21-26:
        21. Click "General Contractors" tab
        22. Find company under "Preferred" badge
        23. Extract company name
        24. Extract contact name
        25. Extract phone number
        26. Extract email
        """
        print("[PH]    Extracting GC information...")

        try:
            # Step 21: Click "General Contractors" tab
            gc_tab_selector = '#mat-button-toggle-4-button'
            try:
                gc_tab = await self.page.querySelector(gc_tab_selector)
                if gc_tab:
                    await gc_tab.click()
                    await asyncio.sleep(2)
                    print("[PH]      GC tab opened")
                else:
                    # Try alternate selector
                    clicked = await self.page.evaluate('''() => {
                        const btns = Array.from(document.querySelectorAll('mat-button-toggle button'));
                        const btn = btns.find(b => b.textContent.includes('General') || b.textContent.includes('Contractor'));
                        if (btn) { btn.click(); return true; }
                        return false;
                    }''')
                    if clicked:
                        await asyncio.sleep(2)
                    else:
                        print("[PH]      GC tab not found")
                        return
            except Exception as e:
                print(f"[PH]      Error clicking GC tab: {e}")
                return

            # Step 22: Check for preferred badge and find GC card
            gc_card_selector = 'planhub-project-general-contractor-card'
            try:
                gc_cards = await self.page.querySelectorAll(gc_card_selector)
                if not gc_cards:
                    print("[PH]      No GC cards found")
                    return

                # Find the preferred GC (first card usually has preferred badge)
                preferred_card = None
                for card in gc_cards:
                    # Check if this card has the preferred badge
                    has_preferred = await self.page.evaluate('''(card) => {
                        const badge = card.querySelector('mat-icon');
                        return badge && (badge.textContent.includes('star') || card.textContent.includes('Preferred'));
                    }''', card)
                    if has_preferred:
                        preferred_card = card
                        break

                # If no preferred, use first card
                if not preferred_card and gc_cards:
                    preferred_card = gc_cards[0]

                if not preferred_card:
                    print("[PH]      No GC card to extract from")
                    return

                # Step 23: Extract company name
                company_name = await self.page.evaluate('''(card) => {
                    // Try to find name in standard locations
                    const nameEl = card.querySelector('.company-name') || 
                                   card.querySelector('mat-card-title') || 
                                   card.querySelector('.name');
                    
                    if (nameEl && nameEl.textContent.trim()) return nameEl.textContent.trim();
                    
                    // Fallback: iterate all elements and look for bold text which often is the name
                    const bolds = card.querySelectorAll('strong, b, .bold');
                    for (const b of bolds) {
                        if (b.textContent.length > 3) return b.textContent.trim();
                    }
                    
                    return null;
                }''', preferred_card)

                if company_name:
                    lead['gc'] = company_name
                    lead['company'] = company_name
                    print(f"[PH]      Company: {company_name}")

                # Step 24: Extract contact name
                contact_name = await self.page.evaluate('''(card) => {
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
                    // Fallback: second div often has contact name
                    if (divs.length >= 2) {
                        return divs[1].textContent.trim();
                    }
                    return null;
                }''', preferred_card)

                if contact_name:
                    lead['contact_name'] = contact_name
                    print(f"[PH]      Contact: {contact_name}")

                # Step 25: Extract phone number
                phone = await self.page.evaluate('''(card) => {
                    const anchors = card.querySelectorAll('planhub-anchor a, a[href^="tel:"]');
                    for (const a of anchors) {
                        const href = a.getAttribute('href') || '';
                        if (href.startsWith('tel:')) {
                            return href.replace('tel:', '').trim();
                        }
                        const text = a.textContent.trim();
                        if (text.match(/[\d\-\(\)\s]{10,}/)) {
                            return text;
                        }
                    }
                    // Fallback: look for phone pattern in text
                    const text = card.textContent;
                    const phoneMatch = text.match(/\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{4}/);
                    return phoneMatch ? phoneMatch[0] : null;
                }''', preferred_card)

                if phone:
                    lead['contact_phone'] = phone
                    print(f"[PH]      Phone: {phone}")

                # Step 26: Extract email
                email = await self.page.evaluate('''(card) => {
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
                    // Fallback: look for email pattern
                    const text = card.textContent;
                    const emailMatch = text.match(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/);
                    return emailMatch ? emailMatch[0] : null;
                }''', preferred_card)

                if email:
                    lead['contact_email'] = email
                    print(f"[PH]      Email: {email}")

                print("[PH]      GC info extraction complete")

            except Exception as e:
                print(f"[PH]      Error extracting GC info: {e}")
                import traceback
                traceback.print_exc()

        except Exception as e:
            print(f"[PH]    Error in GC extraction: {e}")

    async def scrape_all_projects(self, max_projects=None):
        """
        Main scraping logic for PlanHub (Two-Pass).
        """
        log_status("=" * 40)
        log_status("Starting PlanHub scrape")

        # Use config default if not specified
        if max_projects is None:
            max_projects = self.config.MAX_PROJECTS_DEFAULT

        # Navigate to projects
        if not await self.navigate_to_projects():
            log_status("Failed to navigate to projects")
            return []

        # Apply filters (load saved search)
        if not await self.apply_filters():
            log_status("Failed to apply filters, continuing anyway...")

        # --- PASS 1: Extract Details from Table ---
        log_status("=== PASS 1: Extracting Project Details ===")

        rows = await self.get_project_rows()
        if not rows:
            log_status("No project rows found")
            return []

        projects_to_process = min(len(rows), max_projects) if max_projects else len(rows)
        log_status(f"Processing {projects_to_process} of {len(rows)} rows...")

        valid_leads = []
        row_elements = []  # Store row elements for Pass 2

        for index in range(projects_to_process):
            try:
                # Extract details from row
                details = await self.extract_project_details(rows[index], index)

                if not details:
                    continue

                # ID Check
                if details['id'] in self.processed_ids:
                    log_status(f"Skipping duplicate: {details['id'][:20]}")
                    continue

                self.processed_ids.add(details['id'])

                # Past Due Check
                if await self.is_project_past_due(details.get('bid_date', '')):
                    log_status(f"Skipping past due: {details['name'][:30]}")
                    continue

                # Add to valid list
                log_status(f"Found: {details['name'][:40]}")
                valid_leads.append(details)
                row_elements.append(rows[index])
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

                # Download files (this also extracts full address)
                success = await self.download_files_for_lead(lead, row_element=row_elements[i])

                if success:
                    log_status(f"Completed download for project {i+1}")

                # Return to list for next item
                log_status("Returning to project list...")
                await self.navigate_to_projects()
                await asyncio.sleep(2)
                
                # Re-apply filters if needed (sometimes navigation resets them)
                # But usually "Saved Search" persists or we can just find by name in the default list 
                # if the name is unique enough.
                # Ideally we should ensure we are seeing the same list.
                
        log_status(f"SCRAPING COMPLETE - Total leads: {len(self.leads)}")
        return self.leads


async def main():
    """Main entry point for standalone testing"""
    print("\n" + "="*60)
    print(" PLANHUB PUPPETEER SCRAPER")
    print("="*60 + "\n")

    # Process up to 5 projects (PlanHub default)
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
        print("\n Note: PlanHub selectors may need adjustment based on actual UI.")
        print("   Use browser DevTools to inspect elements and update config.py selectors.")

    print("\n" + "="*60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
