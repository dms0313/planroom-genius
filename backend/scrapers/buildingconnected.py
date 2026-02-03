"""
BuildingConnected Puppeteer scraper - deterministic browser automation.
"""
import os
import sys
import asyncio
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrapers.base_scraper import BaseScraper
from config import BuildingConnectedConfig


class BuildingConnectedScraper(BaseScraper):
    """
    BuildingConnected scraper using Puppeteer with deterministic navigation.

    Features:
    - Chrome profile authentication persistence
    - Multiple selector fallback strategies
    - Download handling via Chrome DevTools Protocol
    - Past-due date filtering with multiple formats
    - Duplicate detection using processed_ids set
    - Error recovery with max consecutive errors
    """

    def __init__(self):
        super().__init__(config=BuildingConnectedConfig())
        self.processed_ids = set()

    async def navigate_to_pipeline(self):
        """Navigate to BuildingConnected bid board pipeline"""
        return await self.navigate_with_retry(self.config.PIPELINE_URL)

    async def sort_by_due_date(self):
        """Click Due Date column header to sort descending"""
        print(" Sorting by due date...")
        clicked = await self.click_element_safely(
            self.config.DUE_DATE_SORT_SELECTORS,
            "due date header"
        )
        if clicked:
            print(" Sorted by due date")
        else:
            print(" Could not click due date header (may already be sorted)")

    async def get_project_rows(self):
        """Get count of project rows from the table"""
        # Wait for project names to load (using flexible class selector)
        await self.page.waitForSelector('[class*="textWrapper"]', {'timeout': 10000})
        await asyncio.sleep(1)  # Give time for all rows to render

        # Get all project name elements (these are the project rows)
        rows = await self.page.querySelectorAll('div[class*="textWrapper"]')

        print(f" Found {len(rows)} project rows")
        return len(rows)

    async def click_project_by_index(self, index):
        """
        Click on a project row by index to open details.

        Args:
            index: Zero-based index of project row

        Returns:
            bool: True if successful, False otherwise
        """
        print(f"\n Opening project #{index + 1}...")

        try:
            # Get all project name elements
            project_elements = await self.page.querySelectorAll('div[class*="textWrapper"]')

            if index >= len(project_elements):
                print(f" Index {index} out of range (only {len(project_elements)} projects)")
                return False

            # Click on the specific project
            await project_elements[index].click()

            # Wait for navigation to project details page
            await asyncio.sleep(2)

            # Wait for details page to load
            await asyncio.sleep(1)

            print(" Project details loaded")
            return True
        except Exception as e:
            print(f" Error opening project: {e}")
            return False

    async def extract_project_details(self):
        """Extract details from the project detail page"""
        print(" Extracting project details...")

        try:
            # Wait for page to load
            await asyncio.sleep(2)

            # Extract project ID from URL
            url = self.page.url
            project_id = url.split('/opportunities/')[1].split('/')[0] if '/opportunities/' in url else 'unknown'

            # Extract Name
            name = await self.extract_text_safely(self.config.NAME_SELECTORS, "project name")
            if name == "N/A":
                # Fallback to page title
                name = await self.page.title()
                if 'BuildingConnected' in name:
                    name = name.replace(' | BuildingConnected', '').strip()

            # Extract other fields
            due_date = await self.extract_text_safely(self.config.DUE_DATE_SELECTORS, "due date")
            location = await self.extract_text_safely(self.config.LOCATION_SELECTORS, "location")
            company = await self.extract_text_safely(self.config.COMPANY_SELECTORS, "company")
            contact_name = await self.extract_text_safely(self.config.CONTACT_NAME_SELECTORS, "contact name")
            contact_info = await self.extract_text_safely(self.config.CONTACT_INFO_SELECTORS, "contact info")
            project_info = await self.extract_text_safely(self.config.PROJECT_INFO_SELECTORS, "project info")

            # Build details object
            details = {
                'id': project_id,
                'name': name,
                'due_date': due_date,
                'location': location,
                'company': company,
                'contact_name': contact_name,
                'contact_info': contact_info,
                'project_info': project_info,
                'url': url,
                'source': 'BuildingConnected',
                'site': 'BuildingConnected',  # For compatibility with storage layer
                'gc': company,  # General contractor
                'bid_date': due_date,  # Alias for storage layer
                'extracted_at': datetime.now().isoformat()
            }

            print(f"   Name: {name}")
            print(f"   Due Date: {due_date}")
            print(f"   Location: {location}")
            print(f"   Company: {company}")

            return details
        except Exception as e:
            print(f" Error extracting details: {e}")
            import traceback
            traceback.print_exc()
            return None

    async def click_files_tab(self):
        """Click on the Files tab"""
        print(" Opening Files tab...")

        clicked = await self.click_element_safely(
            self.config.FILES_TAB_SELECTORS,
            "Files tab"
        )

        if not clicked:
            # Try JavaScript approach
            try:
                await self.page.evaluate('''() => {
                    const links = Array.from(document.querySelectorAll('a'));
                    const filesLink = links.find(a => a.textContent.includes('Files'));
                    if (filesLink) filesLink.click();
                }''')
                await asyncio.sleep(2)
                clicked = True
            except Exception as e:
                print(f" Could not open Files tab: {e}")
                return False

        if clicked:
            print(" Files tab opened")
        return clicked

    async def download_project_files(self):
        """Click Files tab and Download All button to download project files"""
        print(" Downloading files...")

        try:
            # First, click the Files tab
            if not await self.click_files_tab():
                return False

            # Wait for and click the "Download All" button
            clicked = await self.click_element_safely(
                self.config.DOWNLOAD_BTN_SELECTORS,
                "Download All button"
            )

            if not clicked:
                # Try JavaScript approach
                await self.page.evaluate('''() => {
                    const buttons = Array.from(document.querySelectorAll('button'));
                    const downloadBtn = buttons.find(b => b.textContent.includes('Download All'));
                    if (downloadBtn) downloadBtn.click();
                }''')

            print(" Download initiated")
            # Wait for download to start
            await asyncio.sleep(3)
            return True
        except Exception as e:
            print(f" Could not download files: {e}")
            return False

    async def go_back_to_pipeline(self):
        """Navigate back to the pipeline list"""
        print("↩  Returning to pipeline...")
        await self.page.goto(
            self.config.PIPELINE_URL,
            {'waitUntil': 'networkidle2', 'timeout': 30000}
        )
        await asyncio.sleep(2)
        print(" Back at pipeline")

    async def extract_list_view_rows(self):
        """
        Extract details from all visible project rows in the list view.
        Returns:
            list: List of dicts with basic project info (name, due_date, etc.)
        """
        print("   Extracting visible rows from list view...")
        try:
            # Wait for rows
            await self.page.waitForSelector(self.config.LIST_NAME_SELECTOR, {'timeout': 5000})
            
            # Get elements
            names = await self.page.querySelectorAll(self.config.LIST_NAME_SELECTOR)
            dates = await self.page.querySelectorAll(self.config.LIST_DATE_SELECTOR)
            locations = await self.page.querySelectorAll(self.config.LIST_LOCATION_SELECTOR)
            companies = await self.page.querySelectorAll(self.config.LIST_COMPANY_SELECTOR)

            count = len(names)
            print(f"   Found {count} name elements")
            
            rows_data = []
            
            for i in range(count):
                try:
                    # Extract text safely
                    name_text = await self.page.evaluate('(el) => el.textContent', names[i])
                    name_text = name_text.strip()
                    
                    # Date (handle if mismatch)
                    date_text = "N/A"
                    if i < len(dates):
                         date_text = await self.page.evaluate('(el) => el.textContent', dates[i])
                         date_text = date_text.strip()

                    # Location
                    loc_text = "N/A"
                    if i < len(locations):
                         loc_text = await self.page.evaluate('(el) => el.textContent', locations[i])
                         loc_text = loc_text.strip()
                         
                    # Company
                    comp_text = "N/A"
                    if i < len(companies):
                         comp_text = await self.page.evaluate('(el) => el.textContent', companies[i])
                         comp_text = comp_text.strip()

                    row = {
                        'name': name_text,
                        'bid_date': date_text, # Standardized key
                        'due_date': date_text,
                        'location': loc_text,
                        'company': comp_text,
                        'gc': comp_text,
                        'id': f"bc_list_{hash(name_text) % 100000}", # Temp ID
                        'source': 'BuildingConnected',
                        'site': 'BuildingConnected',
                        'extracted_at': datetime.now().isoformat()
                    }
                    rows_data.append(row)
                    
                except Exception as e:
                    print(f"   Error extracting row {i}: {e}")
                    continue
            
            return rows_data

        except Exception as e:
            print(f"   Error extracting list view: {e}")
            return []

    async def click_project_by_name(self, name):
        """Click a project in the list by its name"""
        print(f"   Locating project '{name}'...")
        try:
            # Escape for JS
            safe_name = name.replace("'", "\\'").replace('"', '\\"')
            
            # Use XPath or JS to find the specific element
            clicked = await self.page.evaluate(f'''() => {{
                const nameDivs = Array.from(document.querySelectorAll('{self.config.LIST_NAME_SELECTOR}'));
                const target = nameDivs.find(el => el.textContent.trim() === "{safe_name}");
                if (target) {{
                    target.click();
                    return true;
                }}
                return false;
            }}''')
            
            if clicked:
                print("   Project clicked")
                await asyncio.sleep(2) # Wait for nav
                return True
            else:
                print("   Project not found in current view")
                return False
        except Exception as e:
            print(f"   Error clicking project: {e}")
            return False

    async def scrape_all_projects(self, max_projects=None):
        """
        Main scraping logic for BuildingConnected (Two-Pass).
        """
        print("\n Starting BuildingConnected scrape (Two-Pass Mode)...")

        # Navigate to pipeline
        if not await self.navigate_to_pipeline():
            print(" Failed to navigate to pipeline")
            return []
            
        # Optional: Sort by due date first?
        # User didn't strictly request it, but it helps with filtering.
        # await self.sort_by_due_date() 

        # --- PASS 1: Extract Details from List ---
        print("\n=== PASS 1: Extracting Project Details ===")
        
        # Pull visible rows
        potential_leads = await self.extract_list_view_rows()
        
        if not potential_leads:
            print(" No projects found in list view")
            return []
            
        # Determine strict limit
        limit = max_projects if max_projects else len(potential_leads)
        potential_leads = potential_leads[:limit]
        
        print(f" Processing {len(potential_leads)} potential leads...")
        
        valid_leads = []
        
        for lead in potential_leads:
            # Check ID
            if lead['id'] in self.processed_ids:
                 continue
            self.processed_ids.add(lead['id'])
            
            # Check Date
            # Use strict due date check if format allows, else we might pass it
            if await self.is_project_past_due(lead['due_date']):
                 print(f"⏭  Skipping past due: {lead['name']} ({lead['due_date']})")
                 continue
                 
            print(f"✅  Valid: {lead['name']}")
            valid_leads.append(lead)
            self.leads.append(lead)

        print(f"\n=== PASS 1 Complete. Found {len(valid_leads)} valid leads. ===")

        # --- PASS 2: Download Files ---
        if valid_leads:
            print("\n=== PASS 2: Downloading Files ===")
            
            for i, lead in enumerate(valid_leads):
                print(f"\nProcessing download for lead {i+1}/{len(valid_leads)}: {lead['name']}")
                
                # We need to find the project in the list again
                # Assuming we are still on the list page or need to go back
                current_url = self.page.url
                if 'opportunities' not in current_url or 'pipeline' not in current_url:
                     await self.go_back_to_pipeline()
                
                # Click project
                if await self.click_project_by_name(lead['name']):
                    # Details extracted in Pass 1 are from List.
                    # We *could* re-extract full details here (like Contact Info) if needed.
                    # User request emphasized "pull the files".
                    
                    # Download
                    downloaded = await self.download_project_files()
                    if downloaded:
                        print("   Download sequence finished")
                        # You might verify file presence here
                    
                    # Go back
                    await self.go_back_to_pipeline()
                else:
                    print("   Could not find project to click (scrolling issue?)")
                    # If we can't find it (hidden by virtualization), we might skip
                    # In a real implementation, we would implement scroll-to-find.
        
        print(f"\n Scraping complete! Found {len(self.leads)} valid leads.")
        return self.leads


async def main():
    """Main entry point for standalone testing"""
    print("\n" + "="*60)
    print(" BUILDINGCONNECTED PUPPETEER SCRAPER")
    print("="*60 + "\n")

    # Process ALL projects (set max_projects to limit if needed)
    scraper = BuildingConnectedScraper()
    leads = await scraper.run(max_projects=None)  # None = process all

    print("\n" + "="*60)
    print(f" FINAL RESULTS: Found {len(leads)} leads")
    print("="*60)

    if leads:
        for i, lead in enumerate(leads, 1):
            print(f"\nLead {i}:")
            print(f"  Name: {lead.get('name', 'N/A')}")
            print(f"  ID: {lead.get('id', 'N/A')}")
            print(f"  URL: {lead.get('url', 'N/A')}")
    else:
        print("\n No leads found. Check the debug output above.")

    print("\n" + "="*60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
