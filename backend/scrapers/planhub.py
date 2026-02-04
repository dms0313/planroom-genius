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

        try:
            # Click the row to open project details
            if row_element:
                print("[PH]    Clicking row to open details...")
                await row_element.click()
            else:
                # Fallback: find by name
                safe_name = lead['name'].replace('"', '\\"').replace("'", "\\'")
                clicked = await self.page.evaluate(f'''() => {{
                    const rows = document.querySelectorAll('planhub-project-table tbody tr');
                    for (const row of rows) {{
                        if (row.textContent.includes("{safe_name}")) {{
                            row.click();
                            return true;
                        }}
                    }}
                    return false;
                }}''')
                if not clicked:
                    print("[PH]    Could not find project row")
                    return False

            # Wait for details page to load
            print("[PH]    Waiting for details page...")
            await asyncio.sleep(3)

            # Verify we're on details page
            details_selector = 'app-project-details-v2'
            try:
                await self.page.waitForSelector(details_selector, {'timeout': 10000})
                print("[PH]    Details page loaded")
            except:
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

            # Click "Project Files" tab
            print("[PH]    Clicking Project Files tab...")
            files_tab_selector = '#mat-button-toggle-2-button'
            try:
                files_tab = await self.page.querySelector(files_tab_selector)
                if files_tab:
                    await files_tab.click()
                    await asyncio.sleep(2)
                    print("[PH]    Files tab opened")
                else:
                    print("[PH]    Files tab not found")
            except Exception as e:
                print(f"[PH]    Error clicking files tab: {e}")

            # Check if there are files
            has_files = await self.page.evaluate("() => document.querySelectorAll('planhub-project-file-table tbody tr').length > 0")
            if not has_files:
                print("[PH]    No files available for this project")
                return True

            # Click "Select All" checkbox
            print("[PH]    Selecting all files...")
            select_all_selector = '#mat-checkbox-1 label span.mat-checkbox-inner-container'
            try:
                select_all = await self.page.querySelector(select_all_selector)
                if select_all:
                    await select_all.click()
                    await asyncio.sleep(1)
            except Exception as e:
                print(f"[PH]    Error selecting files: {e}")

            # Click Download button
            print("[PH]    Clicking Download...")
            download_btn_selector = 'planhub-project-file-table planhub-button button'

            # Get files before download
            files_before = set(os.listdir(self.download_dir)) if os.path.exists(self.download_dir) else set()

            try:
                download_btn = await self.page.querySelector(download_btn_selector)
                if download_btn:
                    await download_btn.click()
                    print("[PH]    Download initiated, waiting...")
                    await asyncio.sleep(10)
            except Exception as e:
                print(f"[PH]    Error clicking download: {e}")

            # Check for new files
            files_after = set(os.listdir(self.download_dir)) if os.path.exists(self.download_dir) else set()
            new_files = files_after - files_before

            if new_files:
                new_file = sorted(new_files, key=lambda f: os.path.getmtime(os.path.join(self.download_dir, f)))[-1]
                web_path = f"/downloads/{new_file}"
                lead['local_file_path'] = web_path
                lead['downloaded_file'] = new_file
                print(f"[PH]    Downloaded: {new_file}")
            else:
                print("[PH]    No new files detected")

            return True

        except Exception as e:
            print(f"[PH]    Error in download process: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def scrape_all_projects(self, max_projects=None):
        """
        Main scraping logic for PlanHub (Two-Pass).
        """
        print("\n" + "="*50)
        print("[PH] Starting PlanHub scrape")
        print("="*50)

        # Use config default if not specified
        if max_projects is None:
            max_projects = self.config.MAX_PROJECTS_DEFAULT

        # Navigate to projects
        if not await self.navigate_to_projects():
            print("[PH] Failed to navigate to projects")
            return []

        # Apply filters (load saved search)
        if not await self.apply_filters():
            print("[PH] Failed to apply filters, continuing anyway...")

        # --- PASS 1: Extract Details from Table ---
        print("\n[PH] === PASS 1: Extracting Project Details ===")

        rows = await self.get_project_rows()
        if not rows:
            print("[PH] No project rows found")
            return []

        projects_to_process = min(len(rows), max_projects) if max_projects else len(rows)
        print(f"[PH] Processing {projects_to_process} of {len(rows)} rows...")

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
                    print(f"[PH]    Skipping duplicate: {details['id']}")
                    continue

                self.processed_ids.add(details['id'])

                # Past Due Check
                if await self.is_project_past_due(details.get('bid_date', '')):
                    print(f"[PH]    Skipping past due: {details['name'][:30]}...")
                    continue

                # Add to valid list
                print(f"[PH]    Valid: {details['name'][:40]}...")
                valid_leads.append(details)
                row_elements.append(rows[index])
                self.leads.append(details)

            except Exception as e:
                print(f"[PH] Error extracting row {index}: {e}")
                continue

        print(f"\n[PH] === PASS 1 Complete. Found {len(valid_leads)} valid leads. ===")

        # --- PASS 2: Click into each project for details & files ---
        if valid_leads:
            print("\n[PH] === PASS 2: Extracting Details & Files ===")
            for i, (lead, row_elem) in enumerate(zip(valid_leads, row_elements)):
                print(f"\n[PH] Processing {i+1}/{len(valid_leads)}...")

                # Download files (this also extracts full address)
                success = await self.download_files_for_lead(lead, row_elem)

                if success:
                    print("[PH]    Completed")

                # Return to list for next item
                print("[PH]    Returning to project list...")
                await self.navigate_to_projects()
                await asyncio.sleep(2)

                # Re-fetch rows since DOM may have changed
                rows = await self.get_project_rows()
                if i + 1 < len(valid_leads) and i + 1 < len(rows):
                    row_elements[i + 1] = rows[min(i + 1, len(rows) - 1)]

        print(f"\n[PH] Scraping complete! Found {len(self.leads)} valid leads.")
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
