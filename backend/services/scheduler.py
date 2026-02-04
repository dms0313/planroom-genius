import os
import sys
import asyncio
import schedule
import time
import logging
import threading
import traceback
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from buildingconnected_table_scraper import BuildingConnectedTableScraper
from scrapers.planhub import PlanHubScraper
from services.storage import save_leads, deduplicate_database

# Configure logger to show in console
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Add console handler if not present
if not logger.handlers:
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

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

# Status file for real-time monitoring
STATUS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'scraper_status.txt')
LOG_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'scraper_console.log')

# In-memory log buffer for API access
console_log_buffer = []
MAX_LOG_LINES = 500

def add_to_log(message):
    """Add message to in-memory log buffer."""
    global console_log_buffer
    timestamp = datetime.now().strftime("%H:%M:%S")
    line = f"[{timestamp}] {message}"
    console_log_buffer.append(line)

    # Keep buffer size limited
    if len(console_log_buffer) > MAX_LOG_LINES:
        console_log_buffer = console_log_buffer[-MAX_LOG_LINES:]

    # Also write to file
    try:
        with open(LOG_FILE, 'a') as f:
            f.write(line + "\n")
    except:
        pass

def get_console_logs(last_n=100):
    """Get recent console logs."""
    return console_log_buffer[-last_n:]

def clear_console_logs():
    """Clear the log buffer."""
    global console_log_buffer
    console_log_buffer = []
    try:
        with open(LOG_FILE, 'w') as f:
            f.write("")
    except:
        pass

def update_status(step, extra=""):
    """Update status and write to file for monitoring."""
    global scraper_status
    scraper_status["current_step"] = step
    timestamp = datetime.now().strftime("%H:%M:%S")
    status_line = f"[{timestamp}] {step}"
    if extra:
        status_line += f" - {extra}"
    print(status_line, flush=True)
    add_to_log(f"{step}" + (f" - {extra}" if extra else ""))

    # Write to status file
    try:
        with open(STATUS_FILE, 'a') as f:
            f.write(status_line + "\n")
    except:
        pass

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

    # Clear status file
    try:
        with open(STATUS_FILE, 'w') as f:
            f.write(f"=== Scraper Run Started: {datetime.now().isoformat()} ===\n")
    except:
        pass

    update_status("Starting scraper run")

    print("\n" + "="*60, flush=True)
    print("  SCRAPER RUN STARTED", flush=True)
    print("="*60, flush=True)
    logger.info("Starting scheduled scraper run...")
    sys.stdout.flush()

    leads = []

    # Run BuildingConnected Table Scraper (extracts links only, no downloads)
    try:
        update_status("BuildingConnected: Initializing browser")
        print("\n[1/2] BuildingConnected Table Scraper", flush=True)
        print("-" * 40, flush=True)
        logger.info("Launching BuildingConnected Table Scraper...")
        sys.stdout.flush()

        bc_scraper = BuildingConnectedTableScraper()
        # include_details=True gets contact email and files link without downloading
        # Add timeout to prevent hanging forever
        try:
            bc_leads = await asyncio.wait_for(
                bc_scraper.run(max_projects=None, include_details=True),
                timeout=600  # 10 minute timeout
            )
        except asyncio.TimeoutError:
            print("\n[TIMEOUT] BuildingConnected scraper timed out after 10 minutes", flush=True)
            logger.error("BuildingConnected scraper timed out")
            bc_leads = bc_scraper.leads if hasattr(bc_scraper, 'leads') else []

        scraper_status["bc_leads_found"] = len(bc_leads)
        update_status(f"BuildingConnected: Complete", f"Found {len(bc_leads)} leads")
        print(f"\n[OK] BuildingConnected found {len(bc_leads)} leads", flush=True)
        logger.info(f"BuildingConnected found {len(bc_leads)} leads")
        leads.extend(bc_leads)

    except Exception as e:
        scraper_status["last_error"] = f"BuildingConnected: {str(e)}"
        update_status(f"BuildingConnected: ERROR", str(e))
        print(f"\n[ERROR] BuildingConnected Scraper failed: {e}", flush=True)
        logger.error(f"BuildingConnected Scraper failed: {e}")
        traceback.print_exc()
        sys.stdout.flush()

    # Run PlanHub Scraper
    try:
        update_status("PlanHub: Initializing browser")
        print("\n[2/2] PlanHub Scraper", flush=True)
        print("-" * 40, flush=True)
        logger.info("Launching PlanHub Scraper...")
        sys.stdout.flush()

        ph_scraper = PlanHubScraper()
        # Add timeout to prevent hanging forever
        try:
            ph_leads = await asyncio.wait_for(
                ph_scraper.run(max_projects=5),  # Max 5 from PlanHub
                timeout=600  # 10 minute timeout
            )
        except asyncio.TimeoutError:
            print("\n[TIMEOUT] PlanHub scraper timed out after 10 minutes", flush=True)
            logger.error("PlanHub scraper timed out")
            ph_leads = ph_scraper.leads if hasattr(ph_scraper, 'leads') else []

        scraper_status["ph_leads_found"] = len(ph_leads)
        update_status(f"PlanHub: Complete", f"Found {len(ph_leads)} leads")
        print(f"\n[OK] PlanHub found {len(ph_leads)} leads", flush=True)
        logger.info(f"PlanHub found {len(ph_leads)} leads")
        leads.extend(ph_leads)

    except Exception as e:
        error_msg = f"PlanHub: {str(e)}"
        if scraper_status["last_error"]:
            scraper_status["last_error"] += f"; {error_msg}"
        else:
            scraper_status["last_error"] = error_msg
        update_status(f"PlanHub: ERROR", str(e))
        print(f"\n[ERROR] PlanHub Scraper failed: {e}", flush=True)
        logger.error(f"PlanHub Scraper failed: {e}")
        traceback.print_exc()
        sys.stdout.flush()

    # Save aggregated results
    update_status("Saving results to database")
    if leads:
        new_count = save_leads(leads)
        print(f"\n[OK] Saved {new_count} new unique leads", flush=True)
        logger.info(f"Run complete. Saved {new_count} new unique leads.")
        scraper_status["last_status"] = f"success: {new_count} new leads"
    else:
        print("\n[WARN] No leads found in this run", flush=True)
        logger.info("Run complete. No leads found.")
        scraper_status["last_status"] = "completed: no new leads"

    scraper_status["running"] = False
    scraper_status["current_step"] = "idle"
    update_status("Scraper run complete", f"BC: {scraper_status['bc_leads_found']} | PH: {scraper_status['ph_leads_found']}")

    print("\n" + "="*60, flush=True)
    print("  SCRAPER RUN COMPLETE", flush=True)
    print(f"  BC: {scraper_status['bc_leads_found']} | PH: {scraper_status['ph_leads_found']}", flush=True)
    print("="*60 + "\n", flush=True)

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
