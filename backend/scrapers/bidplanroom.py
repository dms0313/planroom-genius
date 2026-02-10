"""
Bidplanroom.com scraper - deterministic browser automation.
"""
import os
import sys
import asyncio
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrapers.base_scraper import BaseScraper
from config import ScraperConfig

# Import Google Drive service
try:
    from services.google_drive import upload_and_cleanup, should_use_gdrive, is_authenticated, get_status
    GDRIVE_AVAILABLE = True
    print(f"[BPR] Google Drive module loaded. Available: {GDRIVE_AVAILABLE}")
except ImportError as e:
    GDRIVE_AVAILABLE = False
    print(f"[BPR] Google Drive module NOT available: {e}")

# Global log buffer that scheduler can access
_bpr_log_buffer = []

def get_bpr_logs():
    """Get and clear the log buffer."""
    global _bpr_log_buffer
    logs = _bpr_log_buffer.copy()
    _bpr_log_buffer = []
    return logs

def log_status(msg):
    """Log to both console and web UI."""
    global _bpr_log_buffer
    print(f"[BPR] {msg}", flush=True)
    _bpr_log_buffer.append(f"[BPR] {msg}")

    # Also try to add to scheduler's log
    try:
        from services.scheduler import add_to_log
        add_to_log(f"[BPR] {msg}")
    except:
        pass


class BidplanroomConfig(ScraperConfig):
    """Configuration for Bidplanroom scraper."""
    
    # URLs
    BASE_URL = "https://www.bidplanroom.com/"
    LOGIN_URL = "https://www.bidplanroom.com/"
    
    # Login credentials
    LOGIN_EMAIL = os.getenv("BIDPLANROOM_EMAIL", "dsullivan@marmicfire.com")
    LOGIN_PASSWORD = os.getenv("BIDPLANROOM_PW", "#pancakeNips1")
    
    # Login selectors
    LOGIN_EMAIL_SELECTOR = 'input[type="email"], input[name="email"], #email'
    LOGIN_PASSWORD_SELECTOR = 'input[type="password"], input[name="password"], #password'
    LOGIN_SUBMIT_SELECTOR = '#login-val-btn, button[type="submit"]'
    
    # Project list selectors
    PROJECT_TABLE_SELECTOR = '#invitations-container table tbody'
    PROJECT_ROW_SELECTOR = '#invitations-container table tbody tr'
    
    # Project info selectors (from user instructions)
    PROJECT_NAME_SELECTOR = '#page-top > div.content > div.workspace > div > div > div.tab-content > h2'
    PROJECT_LOCATION_SELECTOR = '#invitations-container > div > table > tbody > tr:nth-child(1) > td:nth-child(1) > div:nth-child(2)'
    DUE_DATE_SELECTOR = '#invitations-container > div > table > tbody > tr:nth-child(1) > td:nth-child(2) > div:nth-child(1)'
    
    # Project details selectors
    COMPANY_NAME_SELECTOR = '#project-info-container > div:nth-child(5) > div:nth-child(1) > div:nth-child(2) > div:nth-child(1) > b'
    CONTACT_NAME_SELECTOR = '#project-info-container > div:nth-child(5) > div:nth-child(1) > div:nth-child(2) > div:nth-child(3)'
    CONTACT_PHONE_SELECTOR = '#project-info-container > div:nth-child(5) > div:nth-child(1) > div:nth-child(1) > div:nth-child(4)'
    DESCRIPTION_SELECTOR = '#project-info-container > div:nth-child(5) > div:nth-child(1) > div:nth-child(6) > div'
    ADDENDUMS_SELECTOR = '#project-info-container > div:nth-child(5) > div:nth-child(2) > div.section-info > div > div:nth-child(2) > div'
    
    # View Plans selectors (Bluebeam viewer)
    VIEW_PLANS_SELECTOR = '#project-info-container > div:nth-child(4) > div > a:nth-child(1) > span'
    VIEW_PLANS_BTN_SELECTOR = '#launch-plans-btn > span'
    
    # Bluebeam download selectors
    SELECT_ALL_CHECKBOX_SELECTOR = '#applicationHost div.css-1s7evc label span svg path'
    DOWNLOAD_BUTTON_SELECTOR = 'div.css-1tepa3u-downloadButton button div'
    
    # Sprinkler keywords for filtering
    SPRINKLER_KEYWORDS = [
        'sprinkler', 'fire protection', 'fire alarm', 'fire suppression',
        'wet system', 'dry system', 'fppi', 'nfpa'
    ]


class BidplanroomScraper(BaseScraper):
    """
    Bidplanroom.com scraper using Playwright with deterministic navigation.

    Features:
    - Login handling with credentials
    - Project list navigation
    - Data extraction (name, location, date, contacts, description)
    - View Plans -> Bluebeam viewer -> Download files
    - Sprinkler keyword detection
    """

    def __init__(self):
        super().__init__(config=BidplanroomConfig())
        self.processed_ids = set()

    async def check_login_status(self):
        """
        Check if already logged in by looking for login form or dashboard elements.

        Returns:
            bool: True if logged in, False if needs login
        """
        try:
            # Check if login form is visible
            login_visible = await self.page.evaluate('''() => {
                const loginBtn = document.querySelector('#login-val-btn');
                const emailInput = document.querySelector('input[type="email"]');
                return !!(loginBtn || emailInput);
            }''')
            
            if login_visible:
                log_status("Login required")
                return False
            
            # Check if we see project content
            has_projects = await self.page.evaluate('''() => {
                return !!document.querySelector('#invitations-container') ||
                       !!document.querySelector('#project-info-container') ||
                       !!document.querySelector('.workspace');
            }''')
            
            if has_projects:
                log_status("Already logged in")
                return True
            
            return False
        except Exception as e:
            log_status(f"Could not determine login status: {e}")
            return False

    async def login(self):
        """
        Navigate to login page and authenticate.

        Returns:
            bool: True if login successful, False otherwise
        """
        log_status("Logging in to Bidplanroom...")

        try:
            # Navigate to base URL
            if not await self.navigate_with_retry(self.config.BASE_URL):
                return False
            
            await asyncio.sleep(2)

            # Fill email using JavaScript for robustness
            email_filled = await self.page.evaluate(f'''() => {{
                const inputs = document.querySelectorAll('input[type="email"], input[name="email"], input[placeholder*="email" i]');
                for (const input of inputs) {{
                    input.value = "{self.config.LOGIN_EMAIL}";
                    input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    return true;
                }}
                return false;
            }}''')
            
            if email_filled:
                log_status(f"   Entered email: {self.config.LOGIN_EMAIL}")
            else:
                log_status("   Could not find email input")
                return False

            # Fill password using JavaScript
            pw_filled = await self.page.evaluate(f'''() => {{
                const inputs = document.querySelectorAll('input[type="password"], input[name="password"]');
                for (const input of inputs) {{
                    input.value = "{self.config.LOGIN_PASSWORD}";
                    input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    return true;
                }}
                return false;
            }}''')
            
            if pw_filled:
                log_status("   Entered password")
            else:
                log_status("   Could not find password input")
                return False

            # Click login button using JavaScript text-based detection
            login_clicked = await self.page.evaluate('''() => {
                // Try specific ID first
                const loginBtn = document.querySelector('#login-val-btn');
                if (loginBtn) {
                    loginBtn.click();
                    return true;
                }
                
                // Fallback: find by text
                const btns = document.querySelectorAll('button, input[type="submit"], a.btn');
                for (const btn of btns) {
                    const text = (btn.textContent || btn.value || '').toLowerCase();
                    if (text.includes('log in') || text.includes('login') || text.includes('sign in')) {
                        btn.click();
                        return true;
                    }
                }
                return false;
            }''')
            
            if login_clicked:
                log_status("   Submitted login form")
            else:
                log_status("   Could not find login button")
                return False

            # Wait for navigation
            await asyncio.sleep(4)

            # Verify login success
            is_logged_in = await self.check_login_status()
            if is_logged_in or 'invitations' in self.page.url or 'project' in self.page.url:
                log_status("Login successful")
                return True
            else:
                log_status(f"Login may have failed (current URL: {self.page.url})")
                # Take debug screenshot
                try:
                    debug_path = os.path.join(self.download_dir, 'bpr_login_debug.png')
                    await self.page.screenshot(path=debug_path, full_page=True)
                    log_status(f"   Debug screenshot saved: {debug_path}")
                except:
                    pass
                return False

        except Exception as e:
            log_status(f"Login failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def get_project_rows(self):
        """
        Get project rows from the invitations table.

        Returns:
            list: List of project row dictionaries
        """
        try:
            log_status("Getting project rows...")
            await asyncio.sleep(2)
            
            # Extract all projects from the table using JavaScript
            projects = await self.page.evaluate('''() => {
                const rows = document.querySelectorAll('#invitations-container table tbody tr');
                const projects = [];
                
                rows.forEach((row, index) => {
                    const cells = row.querySelectorAll('td');
                    if (cells.length < 2) return;
                    
                    // Get location from first cell
                    const locationCell = cells[0];
                    const locationDiv = locationCell.querySelector('div:nth-child(2)');
                    const location = locationDiv ? locationDiv.textContent.trim() : '';
                    
                    // Get due date from second cell
                    const dateCell = cells[1];
                    const dateDiv = dateCell.querySelector('div:nth-child(1)');
                    const dueDate = dateDiv ? dateDiv.textContent.trim() : '';
                    
                    // Get project name (usually in the first cell as a link or strong text)
                    const nameLink = locationCell.querySelector('a, strong, b');
                    const name = nameLink ? nameLink.textContent.trim() : 
                                 (locationCell.textContent.split('\\n')[0] || '').trim();
                    
                    projects.push({
                        index: index,
                        name: name,
                        location: location,
                        due_date: dueDate
                    });
                });
                
                return projects;
            }''')
            
            log_status(f"Found {len(projects)} projects in table")
            return projects
            
        except Exception as e:
            log_status(f"Error getting project rows: {e}")
            return []

    async def click_project_row(self, project_index):
        """
        Click on a project row to open its details.
        
        Args:
            project_index: Index of the row in the table
            
        Returns:
            bool: True if clicked successfully
        """
        try:
            clicked = await self.page.evaluate(f'''() => {{
                const rows = document.querySelectorAll('#invitations-container table tbody tr');
                if (rows[{project_index}]) {{
                    rows[{project_index}].click();
                    return true;
                }}
                return false;
            }}''')
            return clicked
        except:
            return False

    async def extract_project_details(self):
        """
        Extract detailed information from the currently open project.

        Returns:
            dict: Project details
        """
        log_status("   Extracting project details...")
        
        details = {}
        
        try:
            await asyncio.sleep(2)  # Wait for details to load
            
            # Extract project name
            details['name'] = await self.page.evaluate('''() => {
                const h2 = document.querySelector('#page-top div.content div.workspace h2, .tab-content h2');
                return h2 ? h2.textContent.trim() : '';
            }''') or "N/A"
            
            # Extract company name
            details['company'] = await self.page.evaluate('''() => {
                const el = document.querySelector('#project-info-container div:nth-child(5) b');
                return el ? el.textContent.trim() : '';
            }''') or "N/A"
            
            # Extract contact name
            details['contact_name'] = await self.page.evaluate('''() => {
                const container = document.querySelector('#project-info-container');
                if (!container) return '';
                // Look for contact-like text near company info
                const divs = container.querySelectorAll('div');
                for (const div of divs) {
                    const text = div.textContent;
                    if (text && text.includes('Contact:')) {
                        return text.replace('Contact:', '').trim();
                    }
                }
                return '';
            }''') or "N/A"
            
            # Extract contact phone
            details['contact_phone'] = await self.page.evaluate('''() => {
                const container = document.querySelector('#project-info-container');
                if (!container) return '';
                // Look for phone patterns
                const text = container.textContent;
                const phoneMatch = text.match(/\\(?\\d{3}\\)?[\\s\\-\\.]*\\d{3}[\\s\\-\\.]*\\d{4}/);
                return phoneMatch ? phoneMatch[0] : '';
            }''') or ""
            
            # Extract contact email
            details['contact_email'] = await self.page.evaluate('''() => {
                const links = document.querySelectorAll('#project-info-container a[href^="mailto:"]');
                if (links.length > 0) {
                    return links[0].href.replace('mailto:', '');
                }
                // Fallback: look for email pattern
                const container = document.querySelector('#project-info-container');
                if (!container) return '';
                const text = container.textContent;
                const emailMatch = text.match(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}/);
                return emailMatch ? emailMatch[0] : '';
            }''') or ""
            
            # Extract description
            details['description'] = await self.page.evaluate('''() => {
                const el = document.querySelector('#project-info-container div:nth-child(5) div:nth-child(6)');
                return el ? el.textContent.trim() : '';
            }''') or ""
            
            # Check for sprinkler keywords
            full_text = f"{details['name']} {details['description']}".lower()
            details['sprinklered'] = any(kw.lower() in full_text for kw in self.config.SPRINKLER_KEYWORDS)
            
            log_status(f"   Name: {details['name'][:40]}...")
            log_status(f"   Company: {details['company']}")
            
            return details
            
        except Exception as e:
            log_status(f"   Error extracting details: {e}")
            return details

    async def download_project_files(self, lead):
        """
        Navigate to View Plans (Bluebeam viewer) and download files.

        Workflow:
        1. Click "View Plans" link
        2. Wait for Bluebeam viewer to load
        3. Click Select All checkbox
        4. Click Download button
        
        Args:
            lead: Lead dictionary to update with download info
            
        Returns:
            bool: True if download successful
        """
        log_status("   Downloading project files...")
        
        try:
            # Get files before download
            files_before = set(os.listdir(self.download_dir)) if os.path.exists(self.download_dir) else set()
            
            # Step 1: Click "View Plans" link
            view_plans_clicked = await self.page.evaluate('''() => {
                // Try specific selector
                const viewPlans = document.querySelector('#project-info-container div:nth-child(4) a span');
                if (viewPlans) {
                    viewPlans.click();
                    return true;
                }
                
                // Fallback: find by text
                const links = document.querySelectorAll('a');
                for (const link of links) {
                    const text = link.textContent.toLowerCase();
                    if (text.includes('view plans') || text.includes('plans')) {
                        link.click();
                        return true;
                    }
                }
                return false;
            }''')
            
            if not view_plans_clicked:
                log_status("   Could not find View Plans link")
                return False
            
            log_status("   Clicked View Plans, waiting for Bluebeam viewer...")
            await asyncio.sleep(3)
            
            # Step 2: Check if we need to click another button (launch-plans-btn)
            launch_btn_clicked = await self.page.evaluate('''() => {
                const launchBtn = document.querySelector('#launch-plans-btn');
                if (launchBtn) {
                    launchBtn.click();
                    return true;
                }
                return false;
            }''')
            
            if launch_btn_clicked:
                log_status("   Clicked launch plans button")
                await asyncio.sleep(5)  # Bluebeam viewer takes time to load
            
            # Step 3: Wait for Bluebeam/applicationHost to load
            await asyncio.sleep(5)
            
            # Step 4: Click Select All checkbox
            select_clicked = await self.page.evaluate('''() => {
                // Try to find checkbox in the Bluebeam viewer
                const checkbox = document.querySelector('#applicationHost label svg path, .css-1s7evc label');
                if (checkbox) {
                    checkbox.closest('label').click();
                    return true;
                }
                
                // Fallback: find "Select All" by text
                const labels = document.querySelectorAll('label');
                for (const label of labels) {
                    if (label.textContent.toLowerCase().includes('select all')) {
                        label.click();
                        return true;
                    }
                }
                return false;
            }''')
            
            if select_clicked:
                log_status("   Selected all files")
                await asyncio.sleep(1)
            else:
                log_status("   Could not find Select All checkbox")
            
            # Step 5: Click Download button
            download_clicked = await self.page.evaluate('''() => {
                // Try specific download button selector
                const downloadBtn = document.querySelector('.css-1tepa3u-downloadButton button, div[class*="downloadButton"] button');
                if (downloadBtn) {
                    downloadBtn.click();
                    return true;
                }
                
                // Fallback: find by text
                const btns = document.querySelectorAll('button');
                for (const btn of btns) {
                    const text = btn.textContent.toLowerCase();
                    if (text.includes('download')) {
                        btn.click();
                        return true;
                    }
                }
                return false;
            }''')
            
            if download_clicked:
                log_status("   Download initiated, waiting...")
                await asyncio.sleep(15)  # Wait for download
            else:
                log_status("   Could not find Download button")
                return False
            
            # Check for new files
            files_after = set(os.listdir(self.download_dir)) if os.path.exists(self.download_dir) else set()
            new_files = files_after - files_before
            
            if new_files:
                new_file = sorted(new_files, key=lambda f: os.path.getmtime(os.path.join(self.download_dir, f)))[-1]
                local_path = os.path.join(self.download_dir, new_file)
                log_status(f"   Downloaded: {new_file}")
                
                # Handle Google Drive upload (same as PlanHub)
                if GDRIVE_AVAILABLE and should_use_gdrive():
                    try:
                        log_status("   Uploading to Google Drive...")
                        project_name_clean = "".join(c for c in lead.get('name', 'project')[:50] if c.isalnum() or c in ' -_').strip()
                        gdrive_filename = f"{project_name_clean}_{new_file}"
                        
                        result = upload_and_cleanup(
                            local_path,
                            filename=gdrive_filename,
                            source='Bidplanroom',
                            delete_local=True
                        )
                        
                        if result:
                            lead['gdrive_file_id'] = result.get('file_id')
                            lead['gdrive_link'] = result.get('web_link')
                            lead['download_link'] = result.get('web_link')
                            lead['storage_type'] = 'gdrive'
                            log_status(f"   Uploaded to Google Drive")
                        else:
                            lead['local_file_path'] = f"/downloads/{new_file}"
                            lead['download_link'] = f"/downloads/{new_file}"
                            lead['storage_type'] = 'local'
                    except Exception as e:
                        log_status(f"   GDrive error: {e}")
                        lead['local_file_path'] = f"/downloads/{new_file}"
                        lead['download_link'] = f"/downloads/{new_file}"
                        lead['storage_type'] = 'local'
                else:
                    lead['local_file_path'] = f"/downloads/{new_file}"
                    lead['download_link'] = f"/downloads/{new_file}"
                    lead['storage_type'] = 'local'
                    log_status(f"   Saved locally: /downloads/{new_file}")
                
                return True
            else:
                log_status("   No new files detected")
                return False
            
        except Exception as e:
            log_status(f"   Download error: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def scrape_all_projects(self, max_projects=None):
        """
        Main scraping logic for Bidplanroom (Two-Pass).
        
        Pass 1: Extract basic info from table
        Pass 2: Click into each project, extract details, download files
        
        Args:
            max_projects: Maximum number of projects to scrape (None for all)
            
        Returns:
            list: List of scraped leads
        """
        log_status("Starting Bidplanroom scrape...")
        leads = []
        
        try:
            # Initialize browser
            await self.setup_browser()
            
            # Navigate and login
            if not await self.navigate_with_retry(self.config.BASE_URL):
                log_status("Failed to navigate to Bidplanroom")
                return leads
            
            # Check if login required
            if not await self.check_login_status():
                if not await self.login():
                    log_status("Login failed")
                    return leads
            
            # Get all projects from table
            projects = await self.get_project_rows()
            
            if max_projects:
                projects = projects[:max_projects]
            
            log_status(f"Processing {len(projects)} projects...")
            
            # Pass 2: Process each project
            for i, proj in enumerate(projects):
                log_status(f"\n[Pass 2] Project {i+1}/{len(projects)}: {proj.get('name', 'Unknown')[:30]}...")
                
                try:
                    # Click on the project row
                    if not await self.click_project_row(proj['index']):
                        log_status("   Could not click project row")
                        continue
                    
                    await asyncio.sleep(2)
                    
                    # Extract detailed info
                    details = await self.extract_project_details()
                    
                    # Build lead object
                    lead = {
                        'id': f"bidplanroom_{i}_{hash(details.get('name', '')) % 10000}",
                        'name': details.get('name') or proj.get('name', 'N/A'),
                        'company': details.get('company', 'N/A'),
                        'gc': details.get('company', 'N/A'),
                        'contact_name': details.get('contact_name', 'N/A'),
                        'contact_phone': details.get('contact_phone', ''),
                        'contact_email': details.get('contact_email', ''),
                        'location': proj.get('location', 'N/A'),
                        'bid_date': proj.get('due_date', 'N/A'),
                        'due_date': proj.get('due_date', 'N/A'),
                        'description': details.get('description', ''),
                        'sprinklered': details.get('sprinklered', False),
                        'site': 'Bidplanroom',
                        'source': 'Bidplanroom',
                        'url': self.page.url,
                        'extracted_at': datetime.now().isoformat(),
                        'files_link': None,
                        'download_link': None,
                        'local_file_path': None,
                    }
                    
                    # Download files
                    await self.download_project_files(lead)
                    
                    leads.append(lead)
                    log_status(f"   Added lead: {lead['name'][:30]}...")
                    
                    # Navigate back to list for next project
                    await self.page.go_back()
                    await asyncio.sleep(2)
                    
                except Exception as e:
                    log_status(f"   Error processing project: {e}")
                    continue
            
            log_status(f"\nBidplanroom scrape complete: {len(leads)} leads extracted")
            return leads
            
        except Exception as e:
            log_status(f"Scrape error: {e}")
            import traceback
            traceback.print_exc()
            return leads
        finally:
            await self.close_browser()


async def main():
    """Main entry point for standalone testing."""
    print("[BPR] Starting Bidplanroom scraper test...")
    
    scraper = BidplanroomScraper()
    leads = await scraper.scrape_all_projects(max_projects=3)
    
    print(f"\n[BPR] Scraped {len(leads)} leads:")
    for lead in leads:
        print(f"  - {lead['name'][:40]}: {lead['location']}")
    
    return leads


if __name__ == "__main__":
    asyncio.run(main())
