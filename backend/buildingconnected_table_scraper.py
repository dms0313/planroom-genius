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
                    let link = row.querySelector('a[href*="/opportunities/"]');
                    if (!link) link = nameCol.querySelector('a');
                    if (link) {
                        result.url = link.href;
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
                    const anyLink = row.querySelector('a');
                    if (anyLink && anyLink.href && anyLink.href.includes('buildingconnected')) {
                        result.url = anyLink.href;
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
                        await row.click()
                        await asyncio.sleep(2)  # Wait for panel to open
                        clicked_successfully = True
                except Exception as click_err:
                    # Element detached or other error - continue with basic data
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

            # Generate project ID from URL
            project_id = f'project_{index}'
            if url and '/opportunities/' in url:
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
            print(f"[BC] Error extracting row {index}: {e}")
            return None

    async def extract_detail_info(self, project_url):
        """Extract additional info from the project detail page (after navigation)"""
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

            # Construct files link from project URL
            # URL format: https://app.buildingconnected.com/opportunities/PROJECT_ID/details
            # Files URL: https://app.buildingconnected.com/opportunities/PROJECT_ID/files
            if project_url and '/opportunities/' in project_url:
                base_url = project_url.split('/opportunities/')[0]
                project_id = project_url.split('/opportunities/')[1].split('/')[0]
                files_url = f"{base_url}/opportunities/{project_id}/files"
                detail_info['files_link'] = files_url
                detail_info['download_link'] = files_url

            # Extract files count from quick links
            files_count_selectors = [
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

            # Get files link from page if we don't have it yet (fallback)
            if not detail_info['files_link']:
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
            print("[BC]    Waiting for download to complete...")
            await asyncio.sleep(10)

            # Check for new files
            files_after = set(os.listdir(self.download_dir)) if os.path.exists(self.download_dir) else set()
            new_files = files_after - files_before

            if new_files:
                # Get the most recent file (likely the downloaded zip)
                new_file = sorted(new_files, key=lambda f: os.path.getmtime(os.path.join(self.download_dir, f)))[-1]
                local_path = os.path.join(self.download_dir, new_file)

                # Create a web-accessible path
                # Assuming downloads folder is served at /downloads
                web_path = f"/downloads/{new_file}"

                # Update project with local file path
                project['local_file_path'] = web_path
                project['downloaded_file'] = new_file
                print(f"[BC]    File downloaded: {new_file}")
                print(f"[BC]    Local path: {web_path}")
            else:
                print("[BC]    Warning: No new files detected in download directory")

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
        print("\n" + "="*50)
        print("[BC] Starting BuildingConnected scrape")
        print("="*50)
        print(f"[BC] Include details: {'Yes' if include_details else 'No'}")
        print(f"[BC] Download files: {'Yes' if download_files else 'No'}")
        print("[BC] Strategy: Pass 1 - Extract table data, Pass 2 - Get details, Pass 3 - Download files\n")

        await self.navigate_to_pipeline()
        await self.sort_by_due_date()

        # ====== PASS 1: Extract ALL Project Data from Table (with row clicks for URL) ======
        print("\n[BC] === PASS 1: Extracting Table Data (clicking rows for URLs) ===")

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
                    # Extract row data from table (clicking disabled - causes element detachment issues)
                    data = await self.extract_row_data(row, processed_count, click_for_url=False)
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

                    self.leads.append(data)
                    processed_count += 1

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
                    print(f"[BC] No new projects in batch (consecutive: {consecutive_no_new}) - Scroll: {int(current_scroll)}/{int(max_scroll)}")

                    # If no new projects for 20 consecutive batches, we're done
                    if consecutive_no_new >= 20:
                        print("[BC] No new projects for 20 batches - end of table reached")
                        break
                else:
                    consecutive_no_new = 0
                    print(f"[BC] Found {new_projects_this_batch} new projects | Total: {processed_count} | Scroll: {int(current_scroll)}/{int(max_scroll)}")

                # Check if at bottom (with some tolerance)
                if current_scroll >= max_scroll - 10:
                    print(f"[BC] Reached bottom of table (scroll: {int(current_scroll)}/{int(max_scroll)})")
                    print(f"[BC] Total projects collected: {processed_count}")
                    break

                # Check if scroll position hasn't changed
                if current_scroll == last_scroll_top:
                    consecutive_no_scroll += 1
                    print(f"[BC] Scroll position unchanged ({consecutive_no_scroll} times)")
                    if consecutive_no_scroll >= 10:
                        print("[BC] Scroll not advancing - likely at end")
                        print(f"[BC] Total projects collected: {processed_count}")
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

        print(f"\n[BC] === PASS 1 Complete. Found {len(self.leads)} projects. ===")

        # ====== PASS 2: Get Details (files link, contact email) ======
        if include_details and self.leads:
            print(f"\n[BC] === PASS 2: Getting Details for {len(self.leads)} projects ===")
            for i, project in enumerate(self.leads):
                if project.get('url') and project['url'] != "N/A":
                    print(f"[BC] [{i+1}/{len(self.leads)}] Getting details for: {project['name'][:40]}...")
                    try:
                        # Navigate to project page
                        await self.page.goto(project['url'], wait_until='domcontentloaded', timeout=30000)
                        await asyncio.sleep(2)

                        # Extract details from the project page
                        detail_info = await self.extract_detail_info(project['url'])
                        if detail_info:
                            project.update(detail_info)
                            if detail_info.get('files_link'):
                                print(f"[BC]     Files link: {detail_info['files_link'][:60]}...")
                    except Exception as e:
                        print(f"[BC]     Error getting details: {e}")
                else:
                    print(f"[BC] [{i+1}/{len(self.leads)}] Skipping (no URL): {project['name'][:40]}...")

            print(f"\n[BC] === PASS 2 Complete. ===")

        # ====== PASS 3: Download Files ======
        if download_files and self.leads:
            print(f"\n[BC] === PASS 3: Downloading Files for {len(self.leads)} projects ===")
            for i, project in enumerate(self.leads):
                print(f"\n[BC] [{i+1}/{len(self.leads)}] Downloading files for: {project['name'][:40]}...")
                success = await self.download_files_for_project(project)
                if success:
                    print("[BC]     Download completed")
                else:
                    print("[BC]     Download failed or skipped")

            print(f"\n[BC] === PASS 3 Complete. ===")

        print(f"\n[BC] SCRAPING COMPLETE")
        print(f"[BC] Total leads found: {len(self.leads)}")
        print(f"[BC] Scroll attempts: {scroll_attempts}")
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
