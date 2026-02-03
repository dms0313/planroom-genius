"""
BuildingConnected scraper - Extract data from table view (faster approach)
Scrapes directly from the bid board table without clicking into each project
"""
import os
import asyncio
import json
import warnings
from datetime import datetime
from pyppeteer import launch

# Suppress pyppeteer cleanup warnings
warnings.filterwarnings('ignore', category=RuntimeWarning, message='.*coroutine.*never awaited.*')


class BuildingConnectedTableScraper:
    """Scrape BuildingConnected data directly from table view"""

    def __init__(self):
        self.browser = None
        self.page = None
        self.leads = []
        self.download_dir = os.path.join(os.path.dirname(__file__), 'downloads')
        os.makedirs(self.download_dir, exist_ok=True)

    def find_chrome_executable(self):
        """Find Chrome executable on the system"""
        import platform
        system = platform.system()
        possible_paths = []

        if system == 'Windows':
            possible_paths = [
                r'C:\Program Files\Google\Chrome\Application\chrome.exe',
                r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
                os.path.expanduser(r'~\AppData\Local\Google\Chrome\Application\chrome.exe'),
            ]
        elif system == 'Darwin':
            possible_paths = ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome']
        elif system == 'Linux':
            possible_paths = ['/usr/bin/google-chrome', '/usr/bin/chromium']

        for path in possible_paths:
            if os.path.exists(path):
                return path
        return None

    async def setup_browser(self):
        """Initialize browser with profile"""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        chrome_user_data = os.path.join(
            script_dir,
            "planroom_agent_storage_browser-use-user-data-dir-persistent"
        )
        profile_name = "Profile 2"
        chrome_path = self.find_chrome_executable()

        if chrome_path:
            print(f"[OK] Found Chrome at: {chrome_path}")

        print(f"\n======== CHROME PROFILE CONFIG ========")
        print(f"User Data Dir:   {chrome_user_data}")
        print(f"Profile Name:    {profile_name}")
        print(f"Chrome Path:     {chrome_path or 'Auto-detect'}")
        print("=======================================\n")

        launch_options = {
            'headless': False,
            'userDataDir': chrome_user_data,
            'args': [
                f'--profile-directory={profile_name}',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-blink-features=AutomationControlled'
            ],
        }

        if chrome_path:
            launch_options['executablePath'] = chrome_path

        self.browser = await launch(**launch_options)
        self.page = await self.browser.newPage()
        # Increased viewport width to ensure company column is visible
        await self.page.setViewport({'width': 1920, 'height': 1080})

        print(" Browser initialized")

    async def navigate_to_pipeline(self):
        """Navigate to BuildingConnected bid board"""
        print(" Navigating to pipeline...")
        await self.page.goto(
            'https://app.buildingconnected.com/opportunities/pipeline',
            {'waitUntil': 'domcontentloaded', 'timeout': 60000}
        )
        print(" Waiting for virtual table to load...")
        await asyncio.sleep(3)  # Increased wait time for virtual table to fully load
        print(" Pipeline loaded")

    async def sort_by_due_date(self):
        """Click the due date column header to sort by due date (current projects first)"""
        try:
            # Look for the due date column header - it's usually the 3rd column
            date_header_selectors = [
                'div[class*="headerRow"] > div:nth-child(3)',
                'div[class*="ReactVirtualized__Table__headerRow"] > div:nth-child(3)',
            ]

            date_header = None
            for selector in date_header_selectors:
                try:
                    date_header = await self.page.querySelector(selector)
                    if date_header:
                        break
                except:
                    continue

            if date_header:
                await date_header.click()
                print(" Waiting for table to re-sort...")
                await asyncio.sleep(3)  # Increased wait time for virtual table to re-render after sort
                print(" Sorted by due date")
            else:
                print(" Could not sort - continuing")

        except Exception as e:
            print(f" Sort failed: {e}")

    async def get_visible_rows(self):
        """Get currently visible rows from the ReactVirtualized table"""
        # Wait for the table to load
        await self.page.waitForSelector('.ReactVirtualized__Grid', {'timeout': 10000})

        # Directly query for row elements in the virtual table
        # Pattern: .ReactVirtualized__Grid.ReactVirtualized__Table__Grid > div > div:nth-child(N) > div
        # We query for all direct row containers
        rows = await self.page.querySelectorAll(
            '.ReactVirtualized__Grid.ReactVirtualized__Table__Grid > div > div[style*="position"]'
        )

        if not rows or len(rows) == 0:
            # Fallback: try alternate selector pattern
            rows = await self.page.querySelectorAll(
                '.ReactVirtualized__Table__Grid > div > div'
            )

        if not rows or len(rows) == 0:
            print(" WARNING: No row elements found in virtual table")
            return []

        # Filter out header rows and empty rows
        valid_rows = []
        for row in rows:
            # Check if row has content (has a link to opportunity)
            has_link = await row.querySelector('a[href*="/opportunities/"]')
            if has_link:
                valid_rows.append(row)

        return valid_rows

    async def scroll_table(self, pixels=400):
        """Scroll the table down by specified pixels (reduced for better virtual rendering)"""
        await self.page.evaluate(f'''
            () => {{
                const grid = document.querySelector('.ReactVirtualized__Grid');
                if (grid) {{
                    grid.scrollTop += {pixels};
                }}
            }}
        ''')
        await asyncio.sleep(1.5)  # Increased wait time for virtual table to render new rows

    async def get_scroll_position(self):
        """Get current scroll position and max scroll"""
        return await self.page.evaluate('''
            () => {
                const grid = document.querySelector('.ReactVirtualized__Grid');
                if (grid) {
                    return {
                        scrollTop: grid.scrollTop,
                        scrollHeight: grid.scrollHeight,
                        clientHeight: grid.clientHeight
                    };
                }
                return null;
            }
        ''')

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

    async def extract_row_data(self, row, index):
        """Extract data from a single table row"""
        try:
            # Get all column elements within this row
            columns = await row.querySelectorAll('[class*="rowColumn"]')

            # Extract project name using the correct selector path
            name_selectors = [
                'div[class*="nameCellColumn"] div[class*="projectName"] div[class*="textWrapper"]',
                'div[class*="nameCellColumn"] div[class*="nameCell"] div[class*="textWrapper"]',
                '[class*="textWrapper"]',  # Fallback
            ]

            name = None
            for selector in name_selectors:
                name_elem = await row.querySelector(selector)
                if name_elem:
                    name = await self.page.evaluate('(el) => el.textContent', name_elem)
                    if name and name.strip():
                        name = name.strip()
                        break

            if not name:
                name = f"Project {index + 1}"

            # Extract from columns by index (if we have enough columns)
            bid_date = "N/A"
            location = "N/A"
            city = "N/A"
            state = "N/A"
            company = "N/A"
            contact_name = "N/A"
            expected_start = "N/A"

            if len(columns) > 2:
                # Column 2 (index 2) - Bid Date
                date_text = await self.page.evaluate('(el) => el.textContent', columns[2])
                if date_text:
                    bid_date = date_text.strip()

            if len(columns) > 3:
                # Column 3 (index 3) - Location (City, State)
                location_text = await self.page.evaluate('(el) => el.textContent', columns[3])
                if location_text:
                    location = location_text.strip()
                    # Try to parse city and state
                    # Format might be "CityState" or "City, State" or multiline
                    if ',' in location:
                        parts = location.split(',')
                        city = parts[0].strip()
                        state = parts[1].strip() if len(parts) > 1 else "N/A"
                    else:
                        # Might be on separate lines or concatenated
                        # Look for capital letter that starts state (assuming US states)
                        import re
                        match = re.search(r'([A-Z][a-z\s]+)([A-Z][a-z]+)$', location)
                        if match:
                            city = match.group(1).strip()
                            state = match.group(2).strip()
                        else:
                            city = location

            if len(columns) > 4:
                # Column 4 (index 4) - Company and Contact (in nested divs)
                # Structure: column > div[class*="right-"] > div:nth-child(1/2) > span
                try:
                    # Try specific selector structure first
                    company_elem = await row.querySelector('div:nth-child(5) div[class*="right-"] div:nth-child(1) span')
                    if company_elem:
                        company_text = await self.page.evaluate('(el) => el.textContent', company_elem)
                        if company_text:
                            company = company_text.strip()

                    contact_elem = await row.querySelector('div:nth-child(5) div[class*="right-"] div:nth-child(2) span')
                    if contact_elem:
                        contact_text = await self.page.evaluate('(el) => el.textContent', contact_elem)
                        if contact_text:
                            contact_name = contact_text.strip()
                except:
                    # Fallback to old method
                    company_text = await self.page.evaluate('(el) => el.textContent', columns[4])
                    if company_text:
                        lines = company_text.strip().split('\n')
                        if len(lines) >= 2:
                            company = lines[0].strip()
                            contact_name = lines[1].strip()
                        else:
                            company = company_text.strip()

            if len(columns) > 5:
                # Column 5 (index 5) - Expected Start
                start_text = await self.page.evaluate('(el) => el.textContent', columns[5])
                if start_text:
                    expected_start = start_text.strip()

            # Get the project URL
            link_elem = await row.querySelector('a[href*="/opportunities/"]')
            if link_elem:
                url = await self.page.evaluate('(el) => el.href', link_elem)
                project_id = url.split('/opportunities/')[1].split('/')[0] if '/opportunities/' in url else f'project_{index}'
            else:
                url = "N/A"
                project_id = f'project_{index}'

            return {
                'id': project_id,
                'name': name,
                'bid_date': bid_date,
                'due_date': bid_date,  # Alias
                'expected_start': expected_start,
                'location': location,
                'city': city,
                'state': state,
                'company': company,
                'gc': company,  # General contractor
                'contact_name': contact_name,
                'url': url,
                'source': 'BuildingConnected',
                'site': 'BuildingConnected',
                'extracted_at': datetime.now().isoformat(),
                # These will be filled in by detail view extraction
                'contact_email': None,
                'files_count': None,
                'has_new_files': False,
                'files_link': None,  # Link to files page (for downloading)
                'download_link': None,
            }

        except Exception as e:
            print(f"  Error extracting row {index}: {e}")
            return None

    async def extract_detail_info(self, project_url):
        """Extract additional info from project detail page"""
        try:
            # Navigate to project detail page (faster load)
            await self.page.goto(project_url, {'waitUntil': 'domcontentloaded', 'timeout': 30000})
            await asyncio.sleep(0.5)  # Reduced wait time

            detail_info = {
                'contact_email': None,
                'files_count': None,
                'has_new_files': False,
                'files_link': None,  # Link to files page
                'download_link': None,
            }

            # Extract contact email from quick links
            email_elem = await self.page.querySelector('div[class*="quickLinksContainer"] a:nth-child(2) div span')
            if email_elem:
                email = await self.page.evaluate('(el) => el.textContent', email_elem)
                detail_info['contact_email'] = email.strip() if email else None

            # Extract files count
            files_count_elem = await self.page.querySelector('div[class*="quickLinksContainer"] a:nth-child(2) div[class*="number"]')
            if files_count_elem:
                count_text = await self.page.evaluate('(el) => el.textContent', files_count_elem)
                try:
                    detail_info['files_count'] = int(count_text.strip())
                except:
                    detail_info['files_count'] = count_text.strip()

            # Check for new files badge
            new_badge_elem = await self.page.querySelector('div[class*="quickLinksContainer"] a:nth-child(2) div span')
            if new_badge_elem:
                badge_text = await self.page.evaluate('(el) => el.textContent', new_badge_elem)
                if badge_text and ('new' in badge_text.lower() or 'addendum' in badge_text.lower()):
                    detail_info['has_new_files'] = True

            # Get files page link (don't actually download, just get the link)
            try:
                # Get the href from the Files link in quick links
                files_link = await self.page.querySelector('div[class*="quickLinksContainer"] a:nth-child(2)')
                if files_link:
                    files_url = await self.page.evaluate('(el) => el.href', files_link)
                    if files_url:
                        # Store the files page URL - users can click this to download
                        detail_info['files_link'] = files_url
                        detail_info['download_link'] = files_url

            except Exception as e:
                print(f"    Could not get files link: {e}")

            return detail_info

        except Exception as e:
            print(f"    Error extracting detail info: {e}")
            return None

    async def download_files_for_project(self, project):
        """
        Download files for a specific project (Pass 2).

        Workflow:
        1. Navigate to project detail page
        2. Click Files tab
        3. Click Download All button
        4. Save files to download directory
        5. Return local file path
        """
        print(f"\n[Pass 2] Downloading files for: {project['name']}")

        try:
            # Navigate to project URL
            if project['url'] == "N/A":
                print("   No URL available for this project")
                return False

            print(f"   Navigating to project: {project['url']}")
            await self.page.goto(project['url'], {'waitUntil': 'domcontentloaded', 'timeout': 30000})
            await asyncio.sleep(2)

            # Click Files tab
            print("   Clicking Files tab...")
            files_tab_selectors = [
                'a[href*="/files"]',
                '[data-testid="files-tab"]',
                'div.Tabs___StyledDiv3-sc-v38ayv-2 a:nth-child(2)',
                'a:has-text("Files")',
            ]

            clicked_files_tab = False
            for selector in files_tab_selectors:
                try:
                    files_tab = await self.page.querySelector(selector)
                    if files_tab:
                        await files_tab.click()
                        clicked_files_tab = True
                        print("   Files tab clicked")
                        break
                except:
                    continue

            if not clicked_files_tab:
                print("   Could not find Files tab")
                return False

            await asyncio.sleep(2)

            # Get the starting file count in download directory
            download_dir = self.download_dir
            files_before = set(os.listdir(download_dir)) if os.path.exists(download_dir) else set()

            # Click Download All button
            print("   Clicking Download All button...")
            download_btn_selectors = [
                '[data-testid="download-all-bttn"]',
                'button:has-text("Download All")',
                'button[class*="download"]',
            ]

            clicked_download = False
            for selector in download_btn_selectors:
                try:
                    download_btn = await self.page.querySelector(selector)
                    if download_btn:
                        await download_btn.click()
                        clicked_download = True
                        print("   Download initiated")
                        break
                except:
                    continue

            if not clicked_download:
                print("   Could not find Download button")
                return False

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
                # Assuming downloads folder is served at /downloads
                web_path = f"/downloads/{new_file}"

                # Update project with local file path
                project['local_file_path'] = web_path
                project['downloaded_file'] = new_file
                print(f"   File downloaded: {new_file}")
                print(f"   Local path: {web_path}")
            else:
                print("   Warning: No new files detected in download directory")

            print("   Download complete")
            return True

        except Exception as e:
            print(f"   Error downloading files: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def scrape_all_projects(self, max_projects=None, include_details=False, download_files=False):
        """
        Scrape projects from table view using two-pass approach

        Args:
            max_projects: Max number to process (optional limit)
            include_details: If True, click into each project for contact email, files info (slower)
            download_files: If True, perform second pass to download files for all projects
        """
        print("\n Starting BuildingConnected scrape (Two-Pass Mode)...")
        print(f" Include details: {'Yes' if include_details else 'No'}")
        print(f" Download files: {'Yes' if download_files else 'No'}")
        print(" Strategy: Pass 1 - Extract data, Pass 2 - Download files\n")

        await self.navigate_to_pipeline()
        await self.sort_by_due_date()

        # ====== PASS 1: Extract Project Data ======
        print("\n=== PASS 1: Extracting Project Data ===")

        seen_ids = set()
        processed_count = 0
        scroll_attempts = 0
        max_scroll_attempts = 999999  # Effectively unlimited
        found_expired = False
        consecutive_no_new = 0
        consecutive_no_scroll = 0
        last_scroll_top = -1

        while not found_expired and scroll_attempts < max_scroll_attempts:
            # Get visible rows in current viewport
            rows = await self.get_visible_rows()
            new_projects_this_batch = 0

            if scroll_attempts == 0:
                print(f" Found {len(rows)} visible row elements")

            # Debug logging every 5 scrolls
            if scroll_attempts > 0 and scroll_attempts % 5 == 0:
                print(f"\n[Scroll Batch {scroll_attempts}] Checking {len(rows)} visible rows...")

            # Process each visible row
            for idx, row in enumerate(rows):
                try:
                    # Quick ID check to skip duplicates
                    link_elem = await row.querySelector('a[href*="/opportunities/"]')
                    if not link_elem:
                        if scroll_attempts == 0 and idx < 3:
                            print(f"  Row {idx}: No link found, skipping")
                        continue

                    url = await self.page.evaluate('(el) => el.href', link_elem)
                    project_id = url.split('/opportunities/')[1].split('/')[0] if '/opportunities/' in url else None

                    # Skip if already processed
                    if project_id in seen_ids:
                        continue

                    # Extract full row data
                    data = await self.extract_row_data(row, processed_count)
                    if not data:
                        continue

                    # Check if expired - SKIP expired projects instead of stopping
                    if self.is_project_expired(data['bid_date']):
                        print(f"⏭  Skipping expired project: {data['name'][:30]}... (Date: {data['bid_date']})")
                        seen_ids.add(data['id'])  # Mark as seen to avoid reprocessing
                        continue  # Skip this project but continue scrolling

                    # New project found!
                    seen_ids.add(data['id'])
                    new_projects_this_batch += 1

                    # Optionally get detail info
                    if include_details and data['url'] != "N/A":
                        print(f"[{processed_count + 1}] Getting details for: {data['name'][:40]}...")
                        detail_info = await self.extract_detail_info(data['url'])
                        if detail_info:
                            data.update(detail_info)
                        # Navigate back
                        await self.navigate_to_pipeline()
                        await self.sort_by_due_date()
                    else:
                        print(f"[{processed_count + 1}] {data['name'][:40]}... | {data['bid_date']} | {data['location']}")

                    self.leads.append(data)
                    processed_count += 1

                    # Max limit check removed - scrape unlimited projects until expired project found

                except Exception as e:
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
                    print(f" No new projects in batch (consecutive: {consecutive_no_new}) - Scroll: {int(current_scroll)}/{int(max_scroll)}")

                    # If no new projects for 20 consecutive batches, we're done (increased from 5 for more thorough scraping)
                    if consecutive_no_new >= 20:
                        print(" No new projects for 20 batches - end of table reached")
                        break
                else:
                    consecutive_no_new = 0
                    print(f" Found {new_projects_this_batch} new projects | Total: {processed_count} | Scroll: {int(current_scroll)}/{int(max_scroll)}")

                # Check if at bottom (with some tolerance)
                if current_scroll >= max_scroll - 10:
                    print(f" Reached bottom of table (scroll: {int(current_scroll)}/{int(max_scroll)})")
                    print(f" Total projects collected: {processed_count}")
                    break

                # Check if scroll position hasn't changed (wait a few attempts before giving up)
                if current_scroll == last_scroll_top:
                    consecutive_no_scroll += 1
                    print(f" Scroll position unchanged ({consecutive_no_scroll} times)")
                    if consecutive_no_scroll >= 10:
                        print(" Scroll not advancing - likely at end")
                        print(f" Total projects collected: {processed_count}")
                        break
                else:
                    consecutive_no_scroll = 0  # Reset counter when scroll advances
                    last_scroll_top = current_scroll

            # Scroll down (reduced pixels for better virtual table handling)
            await self.scroll_table(400)
            scroll_attempts += 1

            # Extra wait every 10 scrolls to let virtual table catch up
            if scroll_attempts % 10 == 0:
                print(f" Pausing to let virtual table render... (scroll attempt {scroll_attempts})")
                await asyncio.sleep(2)

        print(f"\n=== PASS 1 Complete. Found {len(self.leads)} valid leads. ===")

        # ====== PASS 2: Download Files ======
        if download_files and self.leads:
            print("\n=== PASS 2: Downloading Files ===")
            for i, project in enumerate(self.leads):
                print(f"\nProcessing download for project {i+1}/{len(self.leads)}...")
                success = await self.download_files_for_project(project)
                if success:
                    print(" Download completed")
                else:
                    print(" Download failed or skipped")

                # Return to pipeline for next project
                await self.navigate_to_pipeline()
                await asyncio.sleep(2)

        print(f"\n SCRAPING COMPLETE")
        print(f" Total leads found: {len(self.leads)}")
        print(f" Scroll attempts: {scroll_attempts}")
        return self.leads

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
            return self.leads
        except Exception as e:
            print(f" Fatal error: {e}")
            import traceback
            traceback.print_exc()
            return []
        finally:
            if self.browser:
                try:
                    await self.browser.close()
                    print("\n Browser closed")
                except:
                    pass


async def main():
    """Main entry point"""
    print("\n" + "="*60)
    print(" BUILDINGCONNECTED TABLE SCRAPER (Two-Pass)")
    print("="*60 + "\n")

    print("Choose mode:")
    print("1. FAST: Table data only (name, date, company, contact)")
    print("2. DETAILED: Include email and files info")
    print("3. FULL: Two-pass mode with file downloads")

    # Default to full two-pass mode with file downloads
    include_details = False  # Set to True for detailed mode
    download_files = True    # Set to True to enable Pass 2 file downloads

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
    asyncio.run(main())
