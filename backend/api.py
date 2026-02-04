from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import sys
import asyncio
import os

# Ensure repository root is on sys.path so imports like `backend.services...` work
# when running this module directly (python backend/api.py)
REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# FIX: Force ProactorEventLoop on Windows for subprocess support (e.g. browser-use)
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Planroom Genius API",
    description="Automated planroom monitoring for fire alarm and low voltage leads using Puppeteer scrapers",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this to your React URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount downloads directory for file serving
DOWNLOADS_DIR = os.path.join(os.path.dirname(__file__), 'downloads')
os.makedirs(DOWNLOADS_DIR, exist_ok=True)
app.mount("/downloads", StaticFiles(directory=DOWNLOADS_DIR), name="downloads")

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "online",
        "service": "Planroom Genius API",
        "version": "2.0.0",
        "automation": "Puppeteer-based deterministic scrapers"
    }

@app.get("/leads")
async def get_leads():
    """Return stored leads, sorted by due date (current/future projects first)."""
    from backend.services.storage import load_leads
    from datetime import datetime

    leads = load_leads()

    # Sort by due date - current/future projects at top
    def get_sort_key(lead):
        """Parse date and return sort key (future dates first, then past dates)"""
        date_str = lead.get('bid_date') or lead.get('due_date') or ''
        if not date_str or date_str == 'N/A' or date_str == 'TBD':
            return (1, datetime.max)  # Put unknown dates at bottom

        # Try to parse the date
        from backend.config import DATE_FORMATS
        for fmt in DATE_FORMATS:
            try:
                parsed = datetime.strptime(date_str.strip(), fmt)
                today = datetime.now()

                # If date is in the future, sort by date ascending (nearest first)
                # If date is in the past, push to bottom
                if parsed.date() >= today.date():
                    return (0, parsed)  # Future/current - sort ascending
                else:
                    return (2, parsed)  # Past - at bottom, sorted descending
            except ValueError:
                continue

        # If we couldn't parse, put at bottom
        return (1, datetime.max)

    try:
        leads.sort(key=get_sort_key)
    except Exception as e:
        logger.warning(f"Could not sort leads by date: {e}")

    return {"leads": leads, "count": len(leads)}

@app.post("/sync-leads")
async def sync_leads(background_tasks: BackgroundTasks):
    """
    Triggers the Puppeteer scraper scan in the background.
    """
    from backend.services.scheduler import run_agents, get_scraper_status

    # Check if already running
    status = get_scraper_status()
    if status["running"]:
        return {
            "status": "already_running",
            "message": "Scraper is already running",
            "current_step": status["current_step"]
        }

    background_tasks.add_task(run_agents)
    return {"status": "accepted", "message": "Scan triggered in background"}

@app.get("/sync-leads")
async def sync_leads_info():
    """Helper to explain how to use the endpoint if accessed via GET."""
    return {"status": "info", "message": "This endpoint requires a POST request to trigger the scan."}

@app.get("/scraper-status")
async def get_scraper_status_endpoint():
    """Get current scraper status - useful for monitoring progress."""
    from backend.services.scheduler import get_scraper_status

    status = get_scraper_status()
    return {
        "running": status["running"],
        "current_step": status["current_step"],
        "last_run": status["last_run"],
        "last_status": status["last_status"],
        "last_error": status["last_error"],
        "leads_found": {
            "buildingconnected": status["bc_leads_found"],
            "planhub": status["ph_leads_found"]
        }
    }

@app.get("/console-logs")
async def get_console_logs_endpoint(lines: int = 100):
    """Get recent console logs for monitoring scraper progress."""
    from backend.services.scheduler import get_console_logs

    logs = get_console_logs(lines)
    return {
        "logs": logs,
        "count": len(logs)
    }

@app.delete("/console-logs")
async def clear_console_logs_endpoint():
    """Clear console logs."""
    from backend.services.scheduler import clear_console_logs

    clear_console_logs()
    return {"status": "cleared"}

@app.post("/clear-leads")
async def clear_leads():
    """Clear all leads from the database (creates backup first)."""
    from backend.services.storage import clear_all_leads

    try:
        count = clear_all_leads()
        return {
            "status": "success",
            "message": f"Cleared {count} leads from database",
            "count": count
        }
    except Exception as e:
        logger.error(f"Failed to clear leads: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/refresh-leads")
async def refresh_leads(background_tasks: BackgroundTasks):
    """Clear all leads and trigger a fresh scan."""
    from backend.services.storage import clear_all_leads
    from backend.services.scheduler import run_agents

    try:
        # Clear existing leads
        count = clear_all_leads()
        logger.info(f"Cleared {count} leads before refresh")

        # Trigger new scan in background
        background_tasks.add_task(run_agents)

        return {
            "status": "accepted",
            "message": f"Cleared {count} leads and started fresh scan",
            "cleared_count": count
        }
    except Exception as e:
        logger.error(f"Failed to refresh leads: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/deduplicate-leads")
async def deduplicate_leads():
    """Remove duplicate leads from the database by merging their information."""
    from backend.services.storage import deduplicate_database

    try:
        result = deduplicate_database()

        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])

        return {
            "status": "success",
            "message": f"Removed {result['removed']} duplicates",
            "original_count": result["original"],
            "deduplicated_count": result["deduplicated"],
            "removed_count": result["removed"]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to deduplicate leads: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/leads")
async def add_lead(lead: dict):
    """Add a new lead manually."""
    from backend.services.storage import load_leads, direct_save_leads
    from datetime import datetime
    import uuid

    try:
        leads = load_leads()

        # Generate unique ID
        new_id = f"manual_{uuid.uuid4().hex[:8]}"

        # Build lead object
        new_lead = {
            "id": new_id,
            "name": lead.get("name", "Untitled"),
            "company": lead.get("company", "N/A"),
            "gc": lead.get("gc", "N/A"),
            "contact_name": lead.get("contact_name", "N/A"),
            "contact_email": lead.get("contact_email", ""),
            "contact_phone": lead.get("contact_phone", ""),
            "location": lead.get("location", "N/A"),
            "full_address": lead.get("full_address", ""),
            "bid_date": lead.get("bid_date", "TBD"),
            "due_date": lead.get("bid_date", "TBD"),
            "description": lead.get("description", ""),
            "site": lead.get("site", "Manual Entry"),
            "source": "Manual Entry",
            "sprinklered": lead.get("sprinklered", False),
            "has_budget": lead.get("has_budget", False),
            "files_link": lead.get("files_link", ""),
            "download_link": lead.get("download_link", ""),
            "local_file_path": None,
            "url": lead.get("url", ""),
            "extracted_at": datetime.now().isoformat(),
            "created_manually": True
        }

        leads.append(new_lead)
        direct_save_leads(leads)

        return {"status": "success", "lead": new_lead}
    except Exception as e:
        logger.error(f"Failed to add lead: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/leads/{lead_id}")
async def update_lead(lead_id: str, lead_data: dict):
    """Update an existing lead."""
    from backend.services.storage import load_leads, direct_save_leads

    try:
        leads = load_leads()

        # Find the lead
        lead_index = None
        for i, lead in enumerate(leads):
            if lead.get("id") == lead_id:
                lead_index = i
                break

        if lead_index is None:
            raise HTTPException(status_code=404, detail="Lead not found")

        # Update fields
        updatable_fields = [
            "name", "company", "gc", "contact_name", "contact_email",
            "contact_phone", "location", "full_address", "bid_date",
            "description", "site", "sprinklered", "has_budget",
            "files_link", "download_link", "url"
        ]

        for field in updatable_fields:
            if field in lead_data:
                leads[lead_index][field] = lead_data[field]

        # Keep due_date in sync with bid_date
        if "bid_date" in lead_data:
            leads[lead_index]["due_date"] = lead_data["bid_date"]

        direct_save_leads(leads)

        return {"status": "success", "lead": leads[lead_index]}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update lead: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/leads/{lead_id}")
async def delete_lead(lead_id: str):
    """Delete a lead by ID."""
    from backend.services.storage import load_leads, direct_save_leads

    try:
        leads = load_leads()

        # Find and remove the lead
        original_count = len(leads)
        leads = [lead for lead in leads if lead.get("id") != lead_id]

        if len(leads) == original_count:
            raise HTTPException(status_code=404, detail="Lead not found")

        direct_save_leads(leads)

        return {"status": "success", "message": "Lead deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete lead: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.on_event("startup")
def startup_event():
    """Start the scheduler on startup."""
    import threading
    from backend.services.scheduler import start_scheduler
    
    # Run scheduler in a separate daemon thread
    t = threading.Thread(target=start_scheduler, daemon=True)
    t.start()

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting Planroom Genius API server...")
    uvicorn.run(app, host="0.0.0.0", port=8000)