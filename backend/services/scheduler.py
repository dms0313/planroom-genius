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
from scrapers.isqft import IsqftScraper
from scrapers.bidplanroom import BidplanroomScraper
from scrapers.loydbuildsbetter import LoydBuildsBetterScraper
from services.storage import save_leads, deduplicate_database
from services.cleanup import cleanup_expired_projects
from services.triage_agent import triage_projects

# Configure logger (propagates to root handler — don't add extra handlers)
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
    "bpr_leads_found": 0,
    "lbb_leads_found": 0,
    "isqft_leads_found": 0,
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

    try:
        with open(STATUS_FILE, 'a') as f:
            f.write(status_line + "\n")
    except:
        pass

# Settings file for persistence
SETTINGS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'scraper_settings.json')

# Default settings
DEFAULT_SETTINGS = {
    "planhub": True,
    "bidplanroom": True,
    "loydbuildsbetter": True,
    "buildingconnected": True,
    "isqft": True,
    "use_gdrive": True
}

def load_settings():
    """Load settings from file or return defaults."""
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r') as f:
                import json
                saved = json.load(f)
                # Merge with defaults to ensure all keys exist
                return {**DEFAULT_SETTINGS, **saved}
        except Exception as e:
            logger.error(f"Failed to load settings: {e}")
    return DEFAULT_SETTINGS.copy()

def save_settings(settings):
    """Save settings to file."""
    try:
        with open(SETTINGS_FILE, 'w') as f:
            import json
            json.dump(settings, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Failed to save settings: {e}")
        return False

def get_scraper_settings():
    """Return current settings."""
    return load_settings()

def update_scraper_settings(new_settings):
    """Update settings."""
    current = load_settings()
    current.update(new_settings)
    save_settings(current)
    return current

def get_scraper_status():
    """Return current scraper status for API."""
    status = scraper_status.copy()
    status['settings'] = get_scraper_settings()
    return status

def stop_agents():
    """Stop the running scraper/agent tasks."""
    global scraper_status
    if scraper_status["running"]:
        scraper_status["running"] = False
        update_status("Stopping...", "Cancellation requested")
        logger.info("Stop requested. Setting running flag to False.")
        
        # Also stop knowledge scanner
        from services.knowledge import stop_scan
        stop_scan()
        
        return True
    return False

async def run_agents(runtime_settings=None):
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
        # Run Triage Agent
        update_status("Running Triage Agent...")
        try:
            triaged_count = triage_projects()
            logger.info(f"Triaged {triaged_count} projects")
        except Exception as e:
            logger.error(f"Triage failed: {e}")

        # Run Knowledge Scanner
        update_status("Running Knowledge Scanner...")

    print("\n" + "="*60, flush=True)
    print("  SCRAPER RUN STARTED", flush=True)
    print("="*60, flush=True)
    logger.info("Starting scheduled scraper run...")
    sys.stdout.flush()

    leads = []



    # Run PlanHub Scraper
    # Use runtime settings if provided, otherwise load from file
    if runtime_settings:
        settings = {**load_settings(), **runtime_settings}
    else:
        settings = load_settings()
    
    if not scraper_status["running"]:
        logger.info("Scan stopped before PlanHub")
        return

    if settings.get("planhub", True):
        try:
            update_status("PlanHub: Initializing browser")
            print("\n[1/4] PlanHub Scraper", flush=True)
            print("-" * 40, flush=True)
            logger.info("Launching PlanHub Scraper...")
            sys.stdout.flush()

            ph_scraper = PlanHubScraper()

            # Start a background task to collect PH logs
            async def collect_ph_logs():
                from scrapers.planhub import get_ph_logs
                while scraper_status["running"]:
                    try:
                        ph_logs = get_ph_logs()
                        for log in ph_logs:
                            add_to_log(log)
                    except:
                        pass
                    await asyncio.sleep(0.5)

            ph_log_collector = asyncio.create_task(collect_ph_logs())

            # Add timeout to prevent hanging forever
            try:
                ph_leads = await asyncio.wait_for(
                    ph_scraper.run(max_projects=None, download_files=True),
                    timeout=900  # 15 minute timeout (downloads take longer)
                )
            except asyncio.TimeoutError:
                print("\n[TIMEOUT] PlanHub scraper timed out after 10 minutes", flush=True)
                logger.error("PlanHub scraper timed out")
                add_to_log("[PH] TIMEOUT after 10 minutes")
                ph_leads = ph_scraper.leads if hasattr(ph_scraper, 'leads') else []

            # Cancel log collector
            ph_log_collector.cancel()
            try:
                await ph_log_collector
            except asyncio.CancelledError:
                pass

            scraper_status["ph_leads_found"] = len(ph_leads)
            update_status(f"PlanHub: Complete", f"Found {len(ph_leads)} leads")
            print(f"\n[OK] PlanHub found {len(ph_leads)} leads", flush=True)
            logger.info(f"PlanHub found {len(ph_leads)} leads")
            leads.extend(ph_leads)
            
            # Incremental save
            logger.info(f"Saving {len(leads)} leads so far...")
            save_leads(leads)

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
    else:
        logger.info("PlanHub scraper disabled in settings")

    # Run Bidplanroom Scraper
    if not scraper_status["running"]:
        logger.info("Scan stopped before Bidplanroom")
        return

    if settings.get("bidplanroom", True):
        try:
            update_status("Bidplanroom: Initializing browser")
            print("\n[2/4] Bidplanroom Scraper", flush=True)
            print("-" * 40, flush=True)
            logger.info("Launching Bidplanroom Scraper...")
            sys.stdout.flush()

            bpr_scraper = BidplanroomScraper()

            # Start a background task to collect BPR logs
            async def collect_bpr_logs():
                from scrapers.bidplanroom import get_bpr_logs
                while scraper_status["running"]:
                    try:
                        bpr_logs = get_bpr_logs()
                        for log in bpr_logs:
                            add_to_log(log)
                    except:
                        pass
                    await asyncio.sleep(0.5)

            bpr_log_collector = asyncio.create_task(collect_bpr_logs())

            try:
                bpr_leads = await asyncio.wait_for(
                    bpr_scraper.scrape_all_projects(max_projects=10),
                    timeout=600  # 10 minute timeout
                )
            except asyncio.TimeoutError:
                print("\n[TIMEOUT] Bidplanroom scraper timed out after 10 minutes", flush=True)
                logger.error("Bidplanroom scraper timed out")
                add_to_log("[BPR] TIMEOUT after 10 minutes")
                bpr_leads = []

            # Cancel log collector
            bpr_log_collector.cancel()
            try:
                await bpr_log_collector
            except asyncio.CancelledError:
                pass

            scraper_status["bpr_leads_found"] = len(bpr_leads)
            update_status(f"Bidplanroom: Complete", f"Found {len(bpr_leads)} leads")
            print(f"\n[OK] Bidplanroom found {len(bpr_leads)} leads", flush=True)
            logger.info(f"Bidplanroom found {len(bpr_leads)} leads")
            leads.extend(bpr_leads)
            
            # Incremental save
            logger.info(f"Saving {len(leads)} leads so far...")
            save_leads(leads)

        except Exception as e:
            error_msg = f"Bidplanroom: {str(e)}"
            if scraper_status["last_error"]:
                scraper_status["last_error"] += f"; {error_msg}"
            else:
                scraper_status["last_error"] = error_msg
            update_status(f"Bidplanroom: ERROR", str(e))
            print(f"\n[ERROR] Bidplanroom Scraper failed: {e}", flush=True)
            logger.error(f"Bidplanroom Scraper failed: {e}")
            traceback.print_exc()
            sys.stdout.flush()
    else:
        logger.info("Bidplanroom scraper disabled in settings")

    # Run Loyd Builds Better Scraper
    if not scraper_status["running"]:
        logger.info("Scan stopped before LoydBuildsBetter")
        return

    if settings.get("loydbuildsbetter", True):
        try:
            update_status("LoydBuildsBetter: Initializing browser")
            print("\n[3/4] Loyd Builds Better Scraper", flush=True)
            print("-" * 40, flush=True)
            logger.info("Launching Loyd Builds Better Scraper...")
            sys.stdout.flush()

            lbb_scraper = LoydBuildsBetterScraper()

            # Start a background task to collect LBB logs
            async def collect_lbb_logs():
                from scrapers.loydbuildsbetter import get_lbb_logs
                while scraper_status["running"]:
                    try:
                        lbb_logs = get_lbb_logs()
                        for log in lbb_logs:
                            add_to_log(log)
                    except:
                        pass
                    await asyncio.sleep(0.5)

            lbb_log_collector = asyncio.create_task(collect_lbb_logs())

            try:
                lbb_leads = await asyncio.wait_for(
                    lbb_scraper.scrape_all_projects(max_projects=10),
                    timeout=600  # 10 minute timeout
                )
            except asyncio.TimeoutError:
                print("\n[TIMEOUT] LoydBuildsBetter scraper timed out after 10 minutes", flush=True)
                logger.error("LoydBuildsBetter scraper timed out")
                add_to_log("[LBB] TIMEOUT after 10 minutes")
                lbb_leads = []

            # Cancel log collector
            lbb_log_collector.cancel()
            try:
                await lbb_log_collector
            except asyncio.CancelledError:
                pass

            scraper_status["lbb_leads_found"] = len(lbb_leads)
            update_status(f"LoydBuildsBetter: Complete", f"Found {len(lbb_leads)} leads")
            print(f"\n[OK] LoydBuildsBetter found {len(lbb_leads)} leads", flush=True)
            logger.info(f"LoydBuildsBetter found {len(lbb_leads)} leads")
            leads.extend(lbb_leads)
            
            # Incremental save
            logger.info(f"Saving {len(leads)} leads so far...")
            save_leads(leads)

        except Exception as e:
            error_msg = f"LoydBuildsBetter: {str(e)}"
            if scraper_status["last_error"]:
                scraper_status["last_error"] += f"; {error_msg}"
            else:
                scraper_status["last_error"] = error_msg
            update_status(f"LoydBuildsBetter: ERROR", str(e))
            print(f"\n[ERROR] LoydBuildsBetter Scraper failed: {e}", flush=True)
            logger.error(f"LoydBuildsBetter Scraper failed: {e}")
            traceback.print_exc()
            sys.stdout.flush()
    else:
        logger.info("LoydBuildsBetter scraper disabled in settings")

    # Run BuildingConnected Scraper
    if not scraper_status["running"]:
        logger.info("Scan stopped before BuildingConnected")
        return

    if settings.get("buildingconnected", True):
        try:
            update_status("BuildingConnected: Initializing browser")
            print("\n[4/5] BuildingConnected Table Scraper", flush=True)
            print("-" * 40, flush=True)
            logger.info("Launching BuildingConnected Table Scraper...")
            sys.stdout.flush()

            bc_scraper = BuildingConnectedTableScraper()

            # Start a background task to collect BC logs
            async def collect_bc_logs():
                from buildingconnected_table_scraper import get_bc_logs
                while scraper_status["running"]:
                    try:
                        bc_logs = get_bc_logs()
                        for log in bc_logs:
                            add_to_log(log)
                    except:
                        pass
                    await asyncio.sleep(0.5)

            log_collector = asyncio.create_task(collect_bc_logs())

            # include_details=True gets contact email and files link
            # download_files=True downloads files and uploads to Google Drive
            # Add timeout to prevent hanging forever
            try:
                bc_leads = await asyncio.wait_for(
                    bc_scraper.run(max_projects=None, include_details=True, download_files=True),
                    timeout=900  # 15 minute timeout (downloads take longer)
                )
            except asyncio.TimeoutError:
                print("\n[TIMEOUT] BuildingConnected scraper timed out after 10 minutes", flush=True)
                logger.error("BuildingConnected scraper timed out")
                add_to_log("[BC] TIMEOUT after 10 minutes")
                bc_leads = bc_scraper.leads if hasattr(bc_scraper, 'leads') else []

            # Cancel log collector
            log_collector.cancel()
            try:
                await log_collector
            except asyncio.CancelledError:
                pass

            scraper_status["bc_leads_found"] = len(bc_leads)
            update_status(f"BuildingConnected: Complete", f"Found {len(bc_leads)} leads")
            print(f"\n[OK] BuildingConnected found {len(bc_leads)} leads", flush=True)
            logger.info(f"BuildingConnected found {len(bc_leads)} leads")
            leads.extend(bc_leads)
            # Final save happens below

        except Exception as e:
            scraper_status["last_error"] = f"BuildingConnected: {str(e)}"
            update_status(f"BuildingConnected: ERROR", str(e))
            print(f"\n[ERROR] BuildingConnected Scraper failed: {e}", flush=True)
            logger.error(f"BuildingConnected Scraper failed: {e}")
            traceback.print_exc()
            sys.stdout.flush()
    else:
        logger.info("BuildingConnected scraper disabled in settings")

    # Run iSqFt Scraper
    if not scraper_status["running"]:
        logger.info("Scan stopped before iSqFt")
        return

    if settings.get("isqft", True):
        try:
            update_status("iSqFt: Initializing")
            print("\n[5/5] iSqFt Scraper", flush=True)
            print("-" * 40, flush=True)
            logger.info("Launching iSqFt Scraper...")

            isqft_scraper = IsqftScraper()

            async def collect_isqft_logs():
                from scrapers.isqft import get_isqft_logs
                while scraper_status["running"]:
                    try:
                        for log in get_isqft_logs():
                            add_to_log(log)
                    except Exception:
                        pass
                    await asyncio.sleep(0.5)

            isqft_log_collector = asyncio.create_task(collect_isqft_logs())

            try:
                isqft_leads = await asyncio.wait_for(
                    isqft_scraper.run(max_projects=None, download_files=True),
                    timeout=900,
                )
            except asyncio.TimeoutError:
                logger.error("iSqFt scraper timed out")
                add_to_log("[ISQFT] TIMEOUT after 15 minutes")
                isqft_leads = isqft_scraper.leads if hasattr(isqft_scraper, "leads") else []

            isqft_log_collector.cancel()
            try:
                await isqft_log_collector
            except asyncio.CancelledError:
                pass

            scraper_status["isqft_leads_found"] = len(isqft_leads)
            update_status("iSqFt: Complete", f"Found {len(isqft_leads)} leads")
            print(f"\n[OK] iSqFt found {len(isqft_leads)} leads", flush=True)
            leads.extend(isqft_leads)

            # Incremental save
            save_leads(leads)

        except Exception as e:
            scraper_status["last_error"] = f"iSqFt: {str(e)}"
            update_status("iSqFt: ERROR", str(e))
            logger.error(f"iSqFt Scraper failed: {e}")
            traceback.print_exc()
    else:
        logger.info("iSqFt scraper disabled in settings")

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
    summary = f"BC: {scraper_status['bc_leads_found']} | PH: {scraper_status['ph_leads_found']} | BPR: {scraper_status['bpr_leads_found']} | LBB: {scraper_status['lbb_leads_found']} | iSqFt: {scraper_status['isqft_leads_found']}"
    update_status("Scraper run complete", summary)

    print("\n" + "="*60, flush=True)
    print("  SCRAPER RUN COMPLETE", flush=True)
    print(f"  {summary}", flush=True)
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
    
    # Schedule daily cleanup
    schedule.every().day.at("03:00").do(cleanup_expired_projects)
    
    # Run cleanup on startup
    logger.info("Running initial startup cleanup...")
    cleanup_expired_projects()

    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    # For testing, just run immediately
    logging.basicConfig(level=logging.INFO)
    run_async_agents()
