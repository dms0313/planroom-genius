"""
Loyd Builds Better scraper - deterministic browser automation.
URL: https://www.loydbuildsbetter.com/bids
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
    print(f"[LBB] Google Drive module loaded. Available: {GDRIVE_AVAILABLE}")
except ImportError as e:
    GDRIVE_AVAILABLE = False
    print(f"[LBB] Google Drive module NOT available: {e}")

# Global log buffer
_lbb_log_buffer = []

def get_lbb_logs():
    """Get and clear the log buffer."""
    global _lbb_log_buffer
    logs = _lbb_log_buffer.copy()
    _lbb_log_buffer = []
    return logs

def log_status(msg):
    """Log to both console and web UI."""
    global _lbb_log_buffer
    print(f"[LBB] {msg}", flush=True)
    _lbb_log_buffer.append(f"[LBB] {msg}")

    try:
        from services.scheduler import add_to_log
        add_to_log(f"[LBB] {msg}")
    except:
        pass


class LoydBuildsBetterConfig(ScraperConfig):
    """Configuration for Loyd Builds Better scraper."""
    
    # URLs - no login required (public site)
    BASE_URL = "https://www.loydbuildsbetter.com/bids"
    
    # Sprinkler keywords for filtering
    SPRINKLER_KEYWORDS = [
        'sprinkler', 'fire protection', 'fire alarm', 'fire suppression',
        'wet system', 'dry system', 'fppi', 'nfpa'
    ]


class LoydBuildsBetterScraper(BaseScraper):
    """
    Loyd Builds Better scraper using Playwright with deterministic navigation.

    Features:
    - Public site (no login required)
    - Extracts project info from block elements
    - Downloads documents via "VIEW DOCUMENTS" links
    - Text-based detection for robustness
    """

    def __init__(self):
        super().__init__(config=LoydBuildsBetterConfig())
        self.processed_ids = set()

    async def get_project_blocks(self):
        """
        Find all project blocks on the bids page.
        Uses text-based detection since block IDs are dynamic.
        """
        try:
            log_status("Finding project blocks...")
            await asyncio.sleep(5)  # Increased wait time
            
            # Take a debug screenshot always to verify page load
            debug_path = os.path.join(self.download_dir, 'lbb_debug_page.png')
            await self.page.screenshot({'path': debug_path, 'fullPage': True})
            log_status(f"Saved debug screenshot to {debug_path}")
            
            # Log page text explicitly to debug content
            page_text = await self.page.evaluate('() => document.body.innerText')
            log_status(f"Page text length: {len(page_text)}")
            log_status(f"First 500 chars: {page_text[:500].replace(chr(10), ' ')}")
            
            # Extract all projects using JavaScript
            projects = await self.page.evaluate('''() => {
                const projects = [];
                
                // Find all block divs that contain project info
                const blocks = document.querySelectorAll('div[id^="block-yui"], div.sqs-block');
                
                blocks.forEach((block, index) => {
                    const text = block.textContent || '';
                    
                    // Skip if doesn't look like a project block
                    // Relaxed check: just needs "VIEW" or "Document" or "Bid"
                    if (!text.includes('VIEW') && !text.includes('Document') && !text.includes('Bid')) return;
                    if (text.length < 50) return;
                    
                    // Try to find a header
                    const h3 = block.querySelector('h3 strong, h3, h2, h4');
                    const name = h3 ? h3.textContent.trim() : '';
                    
                    if (!name) return;
                    
                    // Extract other details
                    const p = block.querySelector('p');
                    let location = '';
                    let dueDate = '';
                    let contactEmail = '';
                    
                    if (p) {
                        const pText = p.textContent || '';
                        // Basic extraction logic...
                        const lines = pText.split('\\n').map(l => l.trim()).filter(l => l);
                        if (lines.length > 0) location = lines[0];
                        
                        const dueMatch = pText.match(/Due[:\\s]*([\\w\\s,]+\\d{4}|\\d{1,2}\\/\\d{1,2}\\/\\d{2,4})/i);
                        if (dueMatch) dueDate = dueMatch[1].trim();
                        
                        const emailLink = p.querySelector('a[href^="mailto:"]');
                        if (emailLink) contactEmail = emailLink.href.replace('mailto:', '');
                    }
                    
                    // Find VIEW link - relaxed selector
                    const viewLink = block.querySelector('a[href*="document"], a[href*="file"], a[href*="dropbox"], a[href*="drive"]');
                    const viewLinkText = viewLink ? viewLink.href : '';
                    
                    projects.push({
                        index: index,
                        blockId: block.id || `block_${index}`,
                        name: name,
                        location: location,
                        due_date: dueDate,
                        contact_email: contactEmail,
                        view_link: viewLinkText
                    });
                });
                
                return projects;
            }''')
            
            log_status(f"Found {len(projects)} project blocks")
            return projects
            
        except Exception as e:
            log_status(f"Error finding project blocks: {e}")
            return []

    async def click_view_documents(self, block_id):
        """
        Click the "VIEW DOCUMENTS" link for a project.
        
        Args:
            block_id: ID of the block element
            
        Returns:
            bool: True if clicked successfully
        """
        try:
            clicked = await self.page.evaluate(f'''() => {{
                // Find block by ID
                let block = document.getElementById("{block_id}");
                if (!block) {{
                    // Fallback: find by data attribute or index
                    const blocks = document.querySelectorAll('div[id^="block-yui"], div.sqs-block');
                    for (const b of blocks) {{
                        if (b.id === "{block_id}" || b.textContent.includes("VIEW")) {{
                            block = b;
                            break;
                        }}
                    }}
                }}
                
                if (!block) return false;
                
                // Find and click the VIEW DOCUMENTS link
                const links = block.querySelectorAll('a');
                for (const link of links) {{
                    const text = link.textContent.toLowerCase();
                    if (text.includes('view') && (text.includes('document') || text.includes('file'))) {{
                        link.click();
                        return true;
                    }}
                }}
                return false;
            }}''')
            return clicked
        except:
            return False

    async def download_documents(self, lead):
        """
        Download documents from the document viewer page.
        
        Args:
            lead: Lead dictionary to update
            
        Returns:
            bool: True if download successful
        """
        log_status("   Downloading documents...")
        
        try:
            await asyncio.sleep(3)  # Wait for viewer to load
            
            # Get files before download
            files_before = set(os.listdir(self.download_dir)) if os.path.exists(self.download_dir) else set()
            
            # Try to find and click download button
            download_clicked = await self.page.evaluate('''() => {
                // Look for download button in various forms
                const btns = document.querySelectorAll('button, a.download, [class*="download"]');
                for (const btn of btns) {
                    const text = (btn.textContent || '').toLowerCase();
                    const ariaLabel = (btn.getAttribute('aria-label') || '').toLowerCase();
                    
                    if (text.includes('download') || ariaLabel.includes('download')) {
                        btn.click();
                        return true;
                    }
                }
                
                // Fallback: look for download icon (SVG with download path)
                const icons = document.querySelectorAll('svg');
                for (const icon of icons) {
                    const parent = icon.closest('button, a');
                    if (parent && parent.textContent.toLowerCase().includes('download')) {
                        parent.click();
                        return true;
                    }
                }
                
                return false;
            }''')
            
            if download_clicked:
                log_status("   Download initiated, waiting...")
                await asyncio.sleep(15)
            else:
                log_status("   Could not find download button")
                return False
            
            # Check for new files
            files_after = set(os.listdir(self.download_dir)) if os.path.exists(self.download_dir) else set()
            new_files = files_after - files_before
            
            if new_files:
                new_file = sorted(new_files, key=lambda f: os.path.getmtime(os.path.join(self.download_dir, f)))[-1]
                local_path = os.path.join(self.download_dir, new_file)
                log_status(f"   Downloaded: {new_file}")
                
                # Handle Google Drive upload
                if GDRIVE_AVAILABLE and should_use_gdrive():
                    try:
                        log_status("   Uploading to Google Drive...")
                        project_name_clean = "".join(c for c in lead.get('name', 'project')[:50] if c.isalnum() or c in ' -_').strip()
                        gdrive_filename = f"{project_name_clean}_{new_file}"
                        
                        result = upload_and_cleanup(
                            local_path,
                            filename=gdrive_filename,
                            source='LoydBuildsBetter',
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
            return False

    async def scrape_all_projects(self, max_projects=None):
        """
        Main scraping logic for Loyd Builds Better.
        
        Args:
            max_projects: Maximum number of projects to scrape (None for all)
            
        Returns:
            list: List of scraped leads
        """
        log_status("Starting Loyd Builds Better scrape...")
        leads = []
        
        try:
            # Initialize browser
            await self.setup_browser()
            
            # Navigate to bids page (no login required)
            if not await self.navigate_with_retry(self.config.BASE_URL):
                log_status("Failed to navigate to Loyd Builds Better")
                return leads
            
            await asyncio.sleep(3)
            
            # Get all project blocks
            projects = await self.get_project_blocks()
            
            if max_projects:
                projects = projects[:max_projects]
            
            log_status(f"Processing {len(projects)} projects...")
            
            # Process each project
            for i, proj in enumerate(projects):
                log_status(f"\nProject {i+1}/{len(projects)}: {proj.get('name', 'Unknown')[:30]}...")
                
                try:
                    # Check for sprinkler keywords
                    full_text = f"{proj.get('name', '')} {proj.get('location', '')}".lower()
                    sprinklered = any(kw.lower() in full_text for kw in self.config.SPRINKLER_KEYWORDS)
                    
                    # Build lead object
                    lead = {
                        'id': f"loydbuildsbetter_{i}_{hash(proj.get('name', '')) % 10000}",
                        'name': proj.get('name', 'N/A'),
                        'company': 'Loyd Builds Better',  # GC is the site owner
                        'gc': 'Loyd Builds Better',
                        'contact_name': 'N/A',
                        'contact_phone': '',
                        'contact_email': proj.get('contact_email', ''),
                        'location': proj.get('location', 'N/A'),
                        'bid_date': proj.get('due_date', 'N/A'),
                        'due_date': proj.get('due_date', 'N/A'),
                        'description': '',
                        'sprinklered': sprinklered,
                        'site': 'LoydBuildsBetter',
                        'source': 'LoydBuildsBetter',
                        'url': self.config.BASE_URL,
                        'extracted_at': datetime.now().isoformat(),
                        'files_link': proj.get('view_link', ''),
                        'download_link': None,
                        'local_file_path': None,
                    }
                    
                    # Try to download documents if view link exists
                    if proj.get('view_link'):
                        lead['files_link'] = proj['view_link']
                        
                        # Click VIEW DOCUMENTS
                        if await self.click_view_documents(proj['blockId']):
                            await asyncio.sleep(2)
                            await self.download_documents(lead)
                            
                            # Navigate back
                            await self.page.go_back()
                            await asyncio.sleep(2)
                    
                    leads.append(lead)
                    log_status(f"   Added lead: {lead['name'][:30]}...")
                    
                except Exception as e:
                    log_status(f"   Error processing project: {e}")
                    continue
            
            log_status(f"\nLoyd Builds Better scrape complete: {len(leads)} leads extracted")
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
    print("[LBB] Starting Loyd Builds Better scraper test...")
    
    scraper = LoydBuildsBetterScraper()
    leads = await scraper.scrape_all_projects(max_projects=3)
    
    print(f"\n[LBB] Scraped {len(leads)} leads:")
    for lead in leads:
        print(f"  - {lead['name'][:40]}: {lead['location']}")
    
    return leads


if __name__ == "__main__":
    asyncio.run(main())
