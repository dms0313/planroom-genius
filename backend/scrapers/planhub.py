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
    - Filter application: ZIP 64030, 100 mile radius, Fire Alarm trade
    - Past-due filtering using date comparison
    - Sprinkler keyword detection in project descriptions
    - Max 5 projects per run (configurable)
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
        print(" Navigating to project list...")

        # Navigate to project list
        if not await self.navigate_with_retry(self.config.PROJECT_LIST_URL):
            return False

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
        Apply location, radius, region, and trade filters.

        Returns:
            bool: True if successful, False otherwise
        """
        print(" Applying filters...")

        try:
            # Wait for page to load
            await asyncio.sleep(2)

            # Apply Location/ZIP filter
            print(f"   Setting location: {self.config.LOCATION_ZIP}")
            try:
                # Try to find and fill location input
                location_input = await self.page.querySelector(self.config.LOCATION_INPUT_SELECTOR)
                if location_input:
                    await self.page.evaluate(
                        f'(el) => el.value = "{self.config.LOCATION_ZIP}"',
                        location_input
                    )
                    await self.page.type(self.config.LOCATION_INPUT_SELECTOR, '')  # Trigger change event
                    print(f"     Location set to {self.config.LOCATION_ZIP}")

                    # Click outside to trigger auto-refresh
                    await self.page.evaluate('() => document.body.click()')
                    await asyncio.sleep(2)  # Wait for page to refresh
                else:
                    print("     Location input not found (may need selector update)")
            except Exception as e:
                print(f"     Could not set location: {e}")

            await asyncio.sleep(1)

            # Apply Distance filter (125 miles)
            print(f"   Setting distance: {self.config.LOCATION_RADIUS} miles")
            try:
                # Click distance dropdown
                distance_dropdown = await self.page.querySelector(self.config.DISTANCE_FILTER_DROPDOWN)
                if distance_dropdown:
                    await distance_dropdown.click()
                    await asyncio.sleep(1)

                    # Click 125 miles option
                    distance_option = await self.page.querySelector(self.config.DISTANCE_125MI_SELECTOR)
                    if distance_option:
                        await distance_option.click()
                        print(f"     Distance set to {self.config.LOCATION_RADIUS} miles")

                        # Click outside to trigger auto-refresh
                        await asyncio.sleep(0.5)
                        await self.page.evaluate('() => document.body.click()')
                        print("     Waiting for page to auto-refresh...")
                        await asyncio.sleep(3)  # Wait for page to refresh
                    else:
                        print("     125 miles option not found")
                else:
                    print("     Distance dropdown not found")
            except Exception as e:
                print(f"     Could not set distance: {e}")

            await asyncio.sleep(1)

            # Apply Region filters (Missouri and Kansas)
            print(f"   Setting regions: {', '.join(self.config.REGIONS)}")
            try:
                # Click region filter dropdown
                region_dropdown = await self.page.querySelector(self.config.REGION_FILTER_DROPDOWN)
                if region_dropdown:
                    await region_dropdown.click()
                    await asyncio.sleep(1)

                    # Select Missouri
                    missouri_checkbox = await self.page.querySelector(self.config.MISSOURI_CHECKBOX)
                    if missouri_checkbox:
                        await missouri_checkbox.click()
                        print("     Missouri selected")
                    else:
                        print("     Missouri checkbox not found")

                    await asyncio.sleep(0.5)

                    # Select Iowa/Kansas/Nebraska (which includes Kansas)
                    kansas_checkbox = await self.page.querySelector(self.config.IOWA_KANSAS_NEBRASKA_CHECKBOX)
                    if kansas_checkbox:
                        await kansas_checkbox.click()
                        print("     Iowa/Kansas/Nebraska selected")
                    else:
                        print("     Iowa/Kansas/Nebraska checkbox not found")

                    await asyncio.sleep(0.5)

                    # Click outside dropdown to close it and trigger auto-refresh
                    await self.page.evaluate('() => document.body.click()')
                    print("     Waiting for page to auto-refresh...")
                    await asyncio.sleep(3)  # Wait for page to refresh with new region filters
                else:
                    print("     Region dropdown not found")
            except Exception as e:
                print(f"     Could not set regions: {e}")

            await asyncio.sleep(1)

            # Apply Trade filter
            print(f"   Setting trade: {self.config.TRADE_FILTER}")
            try:
                trade_input = await self.page.querySelector(self.config.TRADE_INPUT_SELECTOR)
                if trade_input:
                    # Check if it's a select or input
                    tag_name = await self.page.evaluate('(el) => el.tagName', trade_input)
                    if tag_name.lower() == 'select':
                        await self.page.select(self.config.TRADE_INPUT_SELECTOR, self.config.TRADE_FILTER)
                    else:
                        await self.page.type(self.config.TRADE_INPUT_SELECTOR, self.config.TRADE_FILTER)
                    print(f"     Trade set to {self.config.TRADE_FILTER}")

                    # Click outside to trigger auto-refresh
                    await asyncio.sleep(0.5)
                    await self.page.evaluate('() => document.body.click()')
                    print("     Waiting for page to auto-refresh...")
                    await asyncio.sleep(3)  # Wait for page to refresh
                else:
                    print("     Trade input not found (may need selector update)")
            except Exception as e:
                print(f"     Could not set trade: {e}")

            await asyncio.sleep(2)

            print(" Filters applied successfully - page should be refreshed with new results")
            return True

        except Exception as e:
            print(f" Error applying filters: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def get_project_rows(self):
        """
        Get project rows from the table.

        Returns:
            list: List of project row elements
        """
        try:
            # Wait for table to load
            await self.wait_for_selector_safely(self.config.PROJECT_TABLE_SELECTOR)

            # Get all project rows
            rows = await self.page.querySelectorAll(self.config.PROJECT_ROW_SELECTOR)

            print(f" Found {len(rows)} project rows")
            return rows
        except Exception as e:
            print(f" Could not get project rows: {e}")
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
        Extract details from a project row.

        Args:
            row_element: Pyppeteer element handle for the row
            index: Row index for ID generation

        Returns:
            dict: Project details or None if extraction failed
        """
        print(f"   Extracting project {index + 1} details...")

        try:
            # Extract text content from row
            row_text = await self.page.evaluate('(el) => el.textContent', row_element)

            if not row_text or not row_text.strip():
                print("     Empty row, skipping")
                return None

            # For now, we'll extract basic info from the row text
            # This will need to be refined based on actual HTML structure
            # Ideally, we'd use specific cell selectors

            # Try to extract cells from row
            cells = await row_element.querySelectorAll('td, [role="cell"]')

            project_name = "N/A"
            gc = "N/A"
            bid_date = "N/A"

            # Extract from cells (adjust indices based on actual table structure)
            if len(cells) >= 3:
                project_name = await self.page.evaluate('(el) => el.textContent', cells[0])
                project_name = project_name.strip() if project_name else "N/A"

                gc = await self.page.evaluate('(el) => el.textContent', cells[1])
                gc = gc.strip() if gc else "N/A"

                bid_date = await self.page.evaluate('(el) => el.textContent', cells[2])
                bid_date = bid_date.strip() if bid_date else "N/A"
            else:
                # Fallback to row text parsing
                print("     Could not find cells, using row text")
                project_name = row_text[:100]  # First 100 chars as name

            # Check for sprinkler keywords in full row text
            sprinklered = await self.check_sprinkler_keywords(row_text)

            # Generate unique ID
            project_id = f"planhub_{index}_{hash(project_name) % 10000}"

            # Build details object
            details = {
                'id': project_id,
                'name': project_name,
                'gc': gc,
                'bid_date': bid_date,
                'due_date': bid_date,  # Alias
                'site': 'PlanHub',
                'source': 'PlanHub',
                'sprinklered': sprinklered,
                'location': f"ZIP {self.config.LOCATION_ZIP}, {self.config.LOCATION_RADIUS}mi radius",
                'trade': self.config.TRADE_FILTER,
                'url': self.config.PROJECT_LIST_URL,
                'extracted_at': datetime.now().isoformat()
            }

            print(f"     Name: {project_name}")
            print(f"     GC: {gc}")
            print(f"     Bid Date: {bid_date}")
            print(f"     Sprinklered: {sprinklered}")

            return details

        except Exception as e:
            print(f"     Error extracting details: {e}")
            import traceback
            traceback.print_exc()
            return None

    async def download_files_for_lead(self, lead):
        """
        Perform deep navigation to download files for a specific lead.
        
        Workflow:
        1. Find project in list (by name)
        2. Click project -> Open Quick View
        3. Click 'More Project Detail' -> Full Page
        4. Click 'Project Files' tab
        5. Click 'Select All'
        6. Click 'Download Files'
        """
        print(f"\n[Pass 2] Downloading files for: {lead['name']}")
        
        try:
            # Ensure we are on the list page
            if 'project/list' not in self.page.url:
                 await self.navigate_to_projects()
                 await asyncio.sleep(2)

            # 1. Find and click project in list
            # We use a text-based finder since indices might shift if list updates
            print(f"   Locating project '{lead['name']}'...")
            
            # Escape quotes in name for XPath
            safe_name = lead['name'].replace('"', '\\"')
            
            # XPath to find div containing text
            # We look for the row/cell containing the name
            project_found = await self.page.evaluate(f'''() => {{
                const elements = Array.from(document.querySelectorAll('td, span, div'));
                const target = elements.find(el => el.textContent.trim() === "{safe_name}");
                if (target) {{
                    target.click();
                    return true;
                }}
                return false;
            }}''')
            
            if not project_found:
                print("   Could not find project in list (rendering issue?)")
                return False

            print("   Project clicked, waiting for Quick View...")
            await asyncio.sleep(self.config.DELAY_AFTER_CLICK)
            
            # 2. Click "More Project Detail"
            print("   Clicking 'More Project Detail'...")
            await self.wait_for_selector_safely(self.config.MORE_DETAILS_BTN_FULL)
            await self.click_element_safely([self.config.MORE_DETAILS_BTN_FULL], "More Project Detail Button")
            await asyncio.sleep(3) # Wait for navigation

            # 3. Click "Project Files" tab
            print("   Clicking 'Project Files' tab...")
            await self.wait_for_selector_safely(self.config.PROJECT_FILES_TAB)
            await self.click_element_safely([self.config.PROJECT_FILES_TAB], "Project Files Tab")
            await asyncio.sleep(2)

            # 4. Select All Files
            print("   Selecting all files...")
            # Check if there are files first
            has_files = await self.page.evaluate("() => document.querySelectorAll('planhub-project-file-table tr').length > 0")
            if not has_files:
                print("   No files table found.")
                return True # Not an error, just no files

            await self.click_element_safely([self.config.SELECT_ALL_FILES_CHECKBOX], "Select All Checkbox")
            await asyncio.sleep(1)

            # 5. Download
            print("   Clicking Download...")

            # Get the starting file count in download directory
            download_dir = self.download_dir
            files_before = set(os.listdir(download_dir)) if os.path.exists(download_dir) else set()

            await self.click_element_safely([self.config.DOWNLOAD_FILES_BTN], "Download Button")

            # Wait for download to complete
            print("   Waiting for download to complete...")
            await asyncio.sleep(10)

            # Check for new files
            files_after = set(os.listdir(download_dir)) if os.path.exists(download_dir) else set()
            new_files = files_after - files_before

            if new_files:
                # Get the most recent file (likely the downloaded zip)
                new_file = sorted(new_files, key=lambda f: os.path.getmtime(os.path.join(download_dir, f)))[-1]
                local_path = os.path.join(download_dir, new_file)

                # Create a web-accessible path
                web_path = f"/downloads/{new_file}"

                # Update lead with local file path
                lead['local_file_path'] = web_path
                lead['downloaded_file'] = new_file
                print(f"   File downloaded: {new_file}")
                print(f"   Local path: {web_path}")
            else:
                print("   Warning: No new files detected in download directory")

            return True

        except Exception as e:
            print(f"   Error downloading files: {e}")
            return False

    async def scrape_all_projects(self, max_projects=None):
        """
        Main scraping logic for PlanHub (Two-Pass).
        """
        print("\n Starting PlanHub scrape (Two-Pass Mode)...")

        # Use config default if not specified
        if max_projects is None:
            max_projects = self.config.MAX_PROJECTS_DEFAULT

        # Navigate to projects
        if not await self.navigate_to_projects():
            print(" Failed to navigate to projects")
            return []

        # Apply filters
        if not await self.apply_filters():
            print(" Failed to apply filters, continuing anyway...")

        # --- PASS 1: Extract Details ---
        print("\n=== PASS 1: Extracting Project Details ===")
        
        rows = await self.get_project_rows()
        if not rows:
            print(" No project rows found")
            return []

        projects_to_process = min(len(rows), max_projects) if max_projects else len(rows)
        print(f" Found {len(rows)} rows. Processing top {projects_to_process}...")

        valid_leads = []
        processed_count = 0

        for index in range(projects_to_process):
            try:
                # Re-fetch rows in each iteration to avoid stale elements if DOM updates
                # However, PlanHub list is usually static. We'll use the cached list 'rows' 
                # effectively if we assume no re-renders. 
                # To be safe, we re-query if we were clicking, but here we are just reading.
                
                # Extract details
                details = await self.extract_project_details(rows[index], index)

                if not details:
                    continue

                # ID Check
                if details['id'] in self.processed_ids:
                    print(f"⏭  Already processed project {details['id']}, skipping")
                    continue
                
                self.processed_ids.add(details['id'])

                # Past Due Check
                if await self.is_project_past_due(details.get('bid_date', '')):
                    print("⏭  Skipping past due project")
                    continue
                
                # Add to valid list
                print(f"✅  Valid Project: {details['name']}")
                valid_leads.append(details)
                self.leads.append(details) # Add to main list to return
                processed_count += 1

            except Exception as e:
                print(f" Error extracting row {index}: {e}")
                continue

        print(f"\n=== PASS 1 Complete. Found {len(valid_leads)} valid leads. ===")
        
        # --- PASS 2: Download Files ---
        if valid_leads:
            print("\n=== PASS 2: Downloading Files ===")
            for i, lead in enumerate(valid_leads):
                print(f"\nProcessing download for lead {i+1}/{len(valid_leads)}...")
                success = await self.download_files_for_lead(lead)
                if success:
                    print(" Download sequence completed.")
                
                # Return to list for next item
                # Only need to navigate if we actually left the page
                if success: 
                     print(" Returning to project list...")
                     await self.navigate_to_projects()
                     await asyncio.sleep(2) # Wait for reload
                     # Note: We might need to re-apply filters if they don't persist
                     # But we'll rely on PlanHub session for now or just simple text find functionality
                     # If the list order changes, 'find by text' is robust.
        
        print(f"\n Scraping complete! Found {len(self.leads)} valid leads.")
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
