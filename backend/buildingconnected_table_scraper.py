"""
BuildingConnected scraper - Extract data from table view (faster approach)
Scrapes directly from the bid board table without clicking into each project
Uses Playwright for reliable browser automation.
"""
import os
import platform
import asyncio
import json
from datetime import datetime
from playwright.async_api import async_playwright

# Import shared config for cross-platform support
try:
    from config import ScraperConfig
except ImportError:
    ScraperConfig = None


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
        print("[BC] Navigating to pipeline...")
        try:
            await self.page.goto(
                'https://app.buildingconnected.com/opportunities/pipeline',
                wait_until='domcontentloaded',
                timeout=60000
            )
        except Exception as e:
            print(f"[BC] Navigation error: {e}")

        # Check if we're on the login page
        current_url = self.page.url
        print(f"[BC] Current URL: {current_url}")

        if 'login' in current_url or 'signin' in current_url:
            print("\n" + "="*50)
            print("[BC] LOGIN REQUIRED")
            print("="*50)
            print("[BC] Please log in to BuildingConnected in the browser window.")
            print("[BC] After logging in, the scraper will continue automatically.")
            print("="*50 + "\n")

            # Wait for user to log in (check every 3 seconds for up to 5 minutes)
            max_wait = 300  # 5 minutes
            waited = 0
            while waited < max_wait:
                await asyncio.sleep(3)
                waited += 3
                current_url = self.page.url
                if 'login' not in current_url and 'signin' not in current_url:
                    print(f"[BC] Login detected! Continuing...")
                    break
                if waited % 15 == 0:
                    print(f"[BC] Still waiting for login... ({waited}s)")

            # Check one more time
            current_url = self.page.url
            if 'login' in current_url or 'signin' in current_url:
                print("[BC] ERROR: Login timeout - please try again")
                raise Exception("Login timeout")

        print("[BC] Waiting for virtual table to load...")
        await asyncio.sleep(3)

        print("[BC] Pipeline loaded successfully")

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

        # Just get all rows - don't filter
        rows = await self.page.query_selector_all('.ReactVirtualized__Table__Grid > div > div')

        if not rows or len(rows) == 0:
            print("[BC] WARNING: No row elements found")
            return []

        print(f"[BC] Found {len(rows)} row elements")
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
        """Extract data from a single table row using JavaScript (Playwright)"""
        try:
            # Use JavaScript to extract all data at once - more reliable
            data = await row.evaluate('''(row) => {
                const result = {
                    name: '',
                    url: '',
                    bid_date: '',
                    bid_time: '',
                    city: '',
                    state: '',
                    company: '',
                    contact: ''
                };

                // Get project name from textWrapper
                const nameEl = row.querySelector('div[class*="textWrapper"]');
                if (nameEl) result.name = nameEl.textContent.trim();

                // Get URL from link
                const linkEl = row.querySelector('a');
                if (linkEl) result.url = linkEl.href;

                // Get all rowColumn divs
                const cols = row.querySelectorAll('div[class*="rowColumn"]');

                // Column index 2 = Due Date (0-indexed after name column which is special)
                if (cols.length > 1) {
                    const dateCol = cols[1];
                    const spans = dateCol.querySelectorAll('span');
                    if (spans.length > 0) result.bid_date = spans[0].textContent.trim();
                    if (spans.length > 1) result.bid_time = spans[1].textContent.trim();
                }

                // Column index 3 = Location
                if (cols.length > 2) {
                    const locCol = cols[2];
                    const divs = locCol.querySelectorAll('div[class*="EllipsifiedText"], div > div');
                    if (divs.length > 0) result.city = divs[0].textContent.trim();
                    if (divs.length > 1) result.state = divs[1].textContent.trim();
                }

                // Column index 4 = Company/Contact
                if (cols.length > 3) {
                    const compCol = cols[3];
                    const spans = compCol.querySelectorAll('span');
                    if (spans.length > 0) result.company = spans[0].textContent.trim();
                    if (spans.length > 1) result.contact = spans[1].textContent.trim();
                }

                return result;
            }''')

            # Check if we got a name
            if not data or not data.get('name'):
                return None

            name = data['name']
            url = data.get('url', 'N/A')
            bid_date = data.get('bid_date', 'N/A') or 'N/A'
            bid_time = data.get('bid_time', '')
            city = data.get('city', 'N/A') or 'N/A'
            state = data.get('state', 'N/A') or 'N/A'
            company = data.get('company', 'N/A') or 'N/A'
            contact_name = data.get('contact', 'N/A') or 'N/A'

            # Generate project ID from URL
            project_id = f'project_{index}'
            if url and '/opportunities/' in url:
                project_id = url.split('/opportunities/')[1].split('/')[0]

            location = f"{city}, {state}" if state != "N/A" else city

            print(f"[BC] {name[:35]:35} | {bid_date:12} | {city[:15]:15} | {company[:20]}")

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
                'files_link': None,
                'download_link': None,
            }

        except Exception as e:
            print(f"[BC] Error extracting row {index}: {e}")
            return None

    async def extract_detail_info(self, project_url):
        """Extract additional info by clicking on row to open side panel (Playwright)"""
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

            # Wait for side panel to load
            await asyncio.sleep(1)

            # Extract files count
            files_count_selectors = [
                'div[class*="quickLinksContainer"] a:nth-child(2) div[class*="number"]',
                'div[class*="quickLinksContainer"] div[class*="number"]',
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

            # Get files link
            files_link_selectors = [
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
                            detail_info['download_link'] = href
                            print(f"[BC]     Files link: {href[:50]}...")
                        break
                except:
                    continue

            # Extract full address
            address_selectors = [
                'div[class*="scrollY"] div[class*="value"] div span',
                'div[class*="hoverArea"] div[class*="value"] div span',
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

            return detail_info

        except Exception as e:
            print(f"[BC]     Error extracting detail info: {e}")
            return None

    async def download_files_for_project(self, project):
        """
        Download files for a specific project (Pass 2) using Playwright.
        """
        print(f"\n[BC] [Pass 2] Downloading files for: {project['name']}")

        try:
            if project['url'] == "N/A":
                print("[BC]    No URL available for this project")
                return False

            print(f"[BC]    Navigating to project: {project['url']}")
            await self.page.goto(project['url'], wait_until='domcontentloaded', timeout=30000)
            await asyncio.sleep(2)

            # Click Files tab
            print("[BC]    Clicking Files tab...")
            files_tab_selectors = [
                'a[href*="/files"]',
                '[data-testid="files-tab"]',
                'text=Files',
            ]

            clicked_files_tab = False
            for selector in files_tab_selectors:
                try:
                    files_tab = await self.page.query_selector(selector)
                    if files_tab:
                        await files_tab.click()
                        clicked_files_tab = True
                        print("[BC]    Files tab clicked")
                        break
                except:
                    continue

            if not clicked_files_tab:
                print("[BC]    Could not find Files tab")
                return False

            await asyncio.sleep(2)

            # Get files before download
            files_before = set(os.listdir(self.download_dir)) if os.path.exists(self.download_dir) else set()

            # Click Download All button
            print("[BC]    Clicking Download All button...")
            download_btn_selectors = [
                '[data-testid="download-all-bttn"]',
                'text=Download All',
                'button:has-text("Download")',
            ]

            clicked_download = False
            for selector in download_btn_selectors:
                try:
                    download_btn = await self.page.query_selector(selector)
                    if download_btn:
                        await download_btn.click()
                        clicked_download = True
                        print("[BC]    Download initiated")
                        break
                except:
                    continue

            if not clicked_download:
                print("[BC]    Could not find Download button")
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
        print("\n" + "="*50)
        print("[BC] Starting BuildingConnected scrape")
        print("="*50)
        print(f"[BC] Include details: {'Yes' if include_details else 'No'}")
        print(f"[BC] Download files: {'Yes' if download_files else 'No'}")
        print("[BC] Strategy: Pass 1 - Extract data, Pass 2 - Download files\n")

        await self.navigate_to_pipeline()
        await self.sort_by_due_date()

        # ====== PASS 1: Extract Project Data ======
        print("\n[BC] === PASS 1: Extracting Project Data ===")

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
                print(f"[BC] Found {len(rows)} visible row elements")

            # Debug logging every 5 scrolls
            if scroll_attempts > 0 and scroll_attempts % 5 == 0:
                print(f"\n[Scroll Batch {scroll_attempts}] Checking {len(rows)} visible rows...")

            # Process each visible row
            for idx, row in enumerate(rows):
                try:
                    # Extract row data directly
                    data = await self.extract_row_data(row, processed_count)
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

                    # Optionally get detail info
                    if include_details and data['url'] != "N/A":
                        print(f"[BC] [{processed_count + 1}] Getting details for: {data['name'][:40]}...")
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

        print(f"\n[BC] === PASS 1 Complete. Found {len(self.leads)} valid leads. ===")

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
    download_files = False   # Set to True to enable Pass 2 file downloads

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
