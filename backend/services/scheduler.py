import os
import sys
import asyncio
import schedule
import time
import logging
import threading
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from buildingconnected_table_scraper import BuildingConnectedTableScraper
from scrapers.planhub import PlanHubScraper
from services.storage import save_leads, deduplicate_database

# Configure logger to show in console
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Global status tracking for API visibility
scraper_status = {
    "running": False,
    "last_run": None,
    "last_status": "idle",
    "last_error": None,
    "bc_leads_found": 0,
    "ph_leads_found": 0,
    "current_step": "idle"
}

def get_scraper_status():
    """Return current scraper status for API."""
    return scraper_status.copy()

async def run_agents():
    """Runs all scrapers and saves results."""
    global scraper_status

    scraper_status["running"] = True
    scraper_status["last_run"] = datetime.now().isoformat()
    scraper_status["last_error"] = None
    scraper_status["bc_leads_found"] = 0
    scraper_status["ph_leads_found"] = 0

    print("\n" + "="*60)
    print("  SCRAPER RUN STARTED")
    print("="*60)
    logger.info("Starting scheduled scraper run...")

    leads = []

    # Run BuildingConnected Table Scraper (extracts links only, no downloads)
    try:
        scraper_status["current_step"] = "BuildingConnected: Initializing..."
        print("\n[1/2] BuildingConnected Table Scraper")
        print("-" * 40)
        logger.info("Launching BuildingConnected Table Scraper...")

        bc_scraper = BuildingConnectedTableScraper()
        # include_details=True gets contact email and files link without downloading
        bc_leads = await bc_scraper.run(max_projects=None, include_details=True)

        scraper_status["bc_leads_found"] = len(bc_leads)
        print(f"\n[OK] BuildingConnected found {len(bc_leads)} leads")
        logger.info(f"BuildingConnected found {len(bc_leads)} leads")
        leads.extend(bc_leads)

    except Exception as e:
        scraper_status["last_error"] = f"BuildingConnected: {str(e)}"
        print(f"\n[ERROR] BuildingConnected Scraper failed: {e}")
        logger.error(f"BuildingConnected Scraper failed: {e}")
        import traceback
        traceback.print_exc()

    # Run PlanHub Scraper
    try:
        scraper_status["current_step"] = "PlanHub: Initializing..."
        print("\n[2/2] PlanHub Scraper")
        print("-" * 40)
        logger.info("Launching PlanHub Scraper...")

        ph_scraper = PlanHubScraper()
        ph_leads = await ph_scraper.run(max_projects=5)  # Max 5 from PlanHub

        scraper_status["ph_leads_found"] = len(ph_leads)
        print(f"\n[OK] PlanHub found {len(ph_leads)} leads")
        logger.info(f"PlanHub found {len(ph_leads)} leads")
        leads.extend(ph_leads)

    except Exception as e:
        error_msg = f"PlanHub: {str(e)}"
        if scraper_status["last_error"]:
            scraper_status["last_error"] += f"; {error_msg}"
        else:
            scraper_status["last_error"] = error_msg
        print(f"\n[ERROR] PlanHub Scraper failed: {e}")
        logger.error(f"PlanHub Scraper failed: {e}")
        import traceback
        traceback.print_exc()

    # Save aggregated results
    scraper_status["current_step"] = "Saving results..."
    if leads:
        new_count = save_leads(leads)
        print(f"\n[OK] Saved {new_count} new unique leads")
        logger.info(f"Run complete. Saved {new_count} new unique leads.")
        scraper_status["last_status"] = f"success: {new_count} new leads"
    else:
        print("\n[WARN] No leads found in this run")
        logger.info("Run complete. No leads found.")
        scraper_status["last_status"] = "completed: no new leads"

    scraper_status["running"] = False
    scraper_status["current_step"] = "idle"

    print("\n" + "="*60)
    print("  SCRAPER RUN COMPLETE")
    print(f"  BC: {scraper_status['bc_leads_found']} | PH: {scraper_status['ph_leads_found']}")
    print("="*60 + "\n")

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
