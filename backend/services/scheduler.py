import os
import sys
import asyncio
import schedule
import time
import logging
import threading

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Use the table scraper for faster, link-only extraction
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from buildingconnected_table_scraper import BuildingConnectedTableScraper
from scrapers.planhub import PlanHubScraper
from services.storage import save_leads, deduplicate_database

logger = logging.getLogger(__name__)

async def run_agents():
    """Runs all scrapers and saves results."""
    logger.info("⏰ Starting scheduled scraper run...")

    leads = []

    # Run BuildingConnected Table Scraper (extracts links only, no downloads)
    try:
        logger.info("🚀 Launching BuildingConnected Table Scraper...")
        bc_scraper = BuildingConnectedTableScraper()
        # include_details=True gets contact email and files link without downloading
        bc_leads = await bc_scraper.run(max_projects=None, include_details=True)
        logger.info(f"✅ BuildingConnected found {len(bc_leads)} leads")
        leads.extend(bc_leads)
    except Exception as e:
        logger.error(f"❌ BuildingConnected Scraper failed: {e}")

    # Run PlanHub Scraper
    try:
        logger.info("🚀 Launching PlanHub Scraper...")
        ph_scraper = PlanHubScraper()
        ph_leads = await ph_scraper.run(max_projects=5)  # Max 5 from PlanHub
        logger.info(f"✅ PlanHub found {len(ph_leads)} leads")
        leads.extend(ph_leads)
    except Exception as e:
        logger.error(f"❌ PlanHub Scraper failed: {e}")

    # Save aggregated results
    if leads:
        new_count = save_leads(leads)
        logger.info(f"💾 Run complete. Saved {new_count} new unique leads.")
    else:
        logger.info("⚠️ Run complete. No leads found.")

def run_async_agents():
    """Wrapper to run async function in non-async context (scheduler)."""
    asyncio.run(run_agents())

def start_scheduler():
    """Starts the scheduler in a separate thread."""
    # Schedule runs at 9:00 AM and 2:00 PM
    schedule.every().day.at("09:00").do(run_async_agents)
    schedule.every().day.at("14:00").do(run_async_agents)
    
    logger.info("📅 Scheduler started. Jobs scheduled for 09:00 and 14:00 daily.")
    
    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    # For testing, just run immediately
    logging.basicConfig(level=logging.INFO)
    run_async_agents()
