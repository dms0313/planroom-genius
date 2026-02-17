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

# Configure logging — forcibly cap the root logger to one StreamHandler.
# On the Pi the module can be double-imported (as `api` AND `backend.api`)
# and uvicorn adds its own handlers, causing every line to print N times.
_root = logging.getLogger()
_root.setLevel(logging.INFO)
_stream_handlers = [h for h in _root.handlers if isinstance(h, logging.StreamHandler)]
if len(_stream_handlers) > 1:
    # Keep only the first StreamHandler, remove the rest
    for h in _stream_handlers[1:]:
        _root.removeHandler(h)
elif not _stream_handlers:
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

# Mount takeoff static files (CSS, JS)
TAKEOFF_STATIC_DIR = os.path.join(os.path.dirname(__file__), 'takeoff', 'static')
if os.path.exists(TAKEOFF_STATIC_DIR):
    app.mount("/takeoff/static", StaticFiles(directory=TAKEOFF_STATIC_DIR), name="takeoff_static")

# Include takeoff router for Fire Alarm Takeoff Assistant
try:
    from backend.takeoff.routes import router as takeoff_router
    app.include_router(takeoff_router)
    logger.info("✅ Takeoff router loaded successfully")
except Exception as e:
    import traceback
    traceback.print_exc()
    logger.warning(f"⚠️ Could not load takeoff router: {e}")

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "online",
        "service": "Planroom Genius API",
        "version": "2.0.0",
        "automation": "Puppeteer-based deterministic scrapers"
    }

@app.get("/settings/scrapers")
async def get_settings():
    """Get scraper enable/disable settings."""
    from backend.services.scheduler import get_scraper_settings
    return get_scraper_settings()

@app.post("/settings/scrapers")
async def update_settings(settings: dict):
    """Update scraper settings."""
    from backend.services.scheduler import update_scraper_settings
    return update_scraper_settings(settings)

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
async def sync_leads(background_tasks: BackgroundTasks, settings: dict = None):
    """
    Triggers the Puppeteer scraper scan in the background.
    Optional 'settings' dict can override default scraper settings.
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

    background_tasks.add_task(run_agents, runtime_settings=settings)
    return {"status": "accepted", "message": "Scan triggered in background"}

@app.post("/stop-scan")
async def stop_scan():
    """
    Stops the currently running scraper scan.
    """
    from backend.services.scheduler import stop_agents
    
    stopped = stop_agents()
    if stopped:
        return {"status": "success", "message": "Stop signal sent to scrapers"}
    else:
        return {"status": "ignored", "message": "No scan currently running"}

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

@app.post("/system/pick-folder")
async def pick_folder_dialog():
    """
    Open a system folder picker dialog on the host machine.
    Returns the selected path or null if cancelled.
    """
    from backend.services.gui_utils import pick_folder
    import asyncio
    
    # Run in a separate thread to avoid blocking the event loop
    loop = asyncio.get_event_loop()
    path = await loop.run_in_executor(None, pick_folder)
    
    if path:
        return {"path": path}
    return {"path": None}

@app.post("/open-folder")
async def open_folder_endpoint(payload: dict):
    """
    Open a local folder on the host machine.
    """
    from backend.services.gui_utils import open_folder
    path = payload.get("path")
    if not path:
        raise HTTPException(status_code=400, detail="Path required")
    
    success = open_folder(path)
    if not success:
        raise HTTPException(status_code=404, detail="Folder not found or could not be opened")
    return {"status": "success"}

@app.post("/knowledge/scan/{lead_id}")
async def manual_knowledge_scan(lead_id: str, background_tasks: BackgroundTasks):
    """
    Manually trigger AI knowledge scan for a specific lead.
    Useful for debugging or re-scanning a project.
    """
    from backend.services.knowledge import scan_local_downloads
    
    # Run in background
    background_tasks.add_task(scan_local_downloads, lead_id=lead_id, force_rescan=True)
    return {"status": "accepted", "message": f"Scan triggered for lead {lead_id}"}


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
            "files_link", "download_link", "url",
            "highlight", "strikethrough",  # Row styling fields
            "hidden", "comments", "short_comment", "tags"  # New management fields
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


# ==================== Knowledge Scan Endpoints ====================

@app.post("/knowledge/scan")
async def knowledge_scan(background_tasks: BackgroundTasks, force: bool = False):
    """
    Trigger Knowledge scan over all local downloads.
    
    Args:
        force: If true, clear cache and rescan ALL projects (use ?force=true)
    """
    from backend.services.knowledge import scan_local_downloads, get_status

    status = get_status()
    if status["running"]:
        return {"status": "already_running", "details": status}

    background_tasks.add_task(scan_local_downloads, None, force)
    message = "Knowledge scan started (force rescan)" if force else "Knowledge scan started"
    return {"status": "accepted", "message": message, "force": force}


@app.post("/knowledge/scan/{lead_id}")
async def knowledge_scan_single(lead_id: str, background_tasks: BackgroundTasks):
    """Rescan a single project (bypasses cache)."""
    from backend.services.knowledge import scan_local_downloads, get_status

    status = get_status()
    if status["running"]:
        return {"status": "already_running", "details": status}

    background_tasks.add_task(scan_local_downloads, lead_id)
    return {"status": "accepted", "message": f"Knowledge scan started for {lead_id}"}


@app.get("/knowledge/status")
async def knowledge_status():
    from backend.services.knowledge import get_status
    return get_status()


@app.get("/knowledge/files/{lead_id}")
async def knowledge_files(lead_id: str):
    """List all PDFs for a project with classification and thumbnails."""
    from backend.services.knowledge import list_project_files
    return list_project_files(lead_id)


@app.post("/knowledge/files/{lead_id}/override")
async def knowledge_file_override(lead_id: str, body: dict):
    """Manually set a file's classification (plan/spec/other)."""
    from backend.services.knowledge import set_file_override

    rel_path = body.get("rel_path")
    classification = body.get("classification")
    if not rel_path or classification not in ("plan", "spec", "other"):
        raise HTTPException(status_code=400, detail="rel_path and classification (plan/spec/other) required")

    ok = set_file_override(lead_id, rel_path, classification)
    if not ok:
        raise HTTPException(status_code=404, detail="Lead or folder not found")
    return {"status": "success"}


@app.get("/knowledge/thumbnail/{lead_id}")
async def knowledge_thumbnail(lead_id: str):
    """Return just the first-page thumbnail for a lead's first PDF."""
    from backend.services.knowledge import get_title_thumbnail
    return get_title_thumbnail(lead_id)


@app.get("/knowledge/ranking")
async def knowledge_ranking():
    """Get all scanned projects ranked by bid chance and scope score."""
    from backend.services.knowledge import rank_all_projects
    return {"ranking": rank_all_projects()}


# ==================== Google Drive Endpoints ====================

@app.get("/gdrive/status")
async def get_gdrive_status():
    """Get Google Drive connection status."""
    try:
        from backend.services.google_drive import get_status, is_available

        if not is_available():
            return {
                "status": "unavailable",
                "message": "Google Drive API libraries not installed",
                "details": {
                    "available": False,
                    "configured": False,
                    "authenticated": False
                }
            }

        status = get_status()

        if status['authenticated']:
            return {
                "status": "connected",
                "message": "Google Drive is connected and ready",
                "details": status
            }
        elif status['configured']:
            return {
                "status": "not_authenticated",
                "message": "Google Drive is configured but needs authentication",
                "details": status
            }
        else:
            return {
                "status": "not_configured",
                "message": "Google Drive credentials not found",
                "details": status
            }
    except Exception as e:
        logger.error(f"Error checking Google Drive status: {e}")
        return {
            "status": "error",
            "message": str(e),
            "details": None
        }


@app.post("/gdrive/connect")
async def connect_gdrive():
    """
    Initiate Google Drive OAuth flow.
    This will open a browser window for authentication.
    """
    try:
        from backend.services.google_drive import authenticate, is_available, is_configured

        if not is_available():
            raise HTTPException(
                status_code=400,
                detail="Google Drive API libraries not installed. Run: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib"
            )

        if not is_configured():
            raise HTTPException(
                status_code=400,
                detail="credentials.json not found in backend directory. Please download OAuth credentials from Google Cloud Console."
            )

        # This will open browser for OAuth consent
        logger.info("Starting Google Drive OAuth flow...")
        creds = authenticate(force_new=False)

        if creds:
            return {
                "status": "success",
                "message": "Google Drive connected successfully!"
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="OAuth flow failed. Please try again."
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Google Drive connection failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/gdrive/test")
async def test_gdrive():
    """Test Google Drive connection by listing files."""
    try:
        from backend.services.google_drive import test_connection, is_authenticated

        if not is_authenticated():
            raise HTTPException(
                status_code=400,
                detail="Google Drive not authenticated. Use /gdrive/connect first."
            )

        result = test_connection()

        if result['success']:
            return {
                "status": "success",
                "message": result['message'],
                "files": result.get('files', [])
            }
        else:
            raise HTTPException(status_code=500, detail=result.get('error', 'Unknown error'))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Google Drive test failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/open-folder")
async def open_local_folder(body: dict):
    """Open a local directory in the OS file explorer."""
    path = body.get("path")
    if not path:
        raise HTTPException(status_code=400, detail="Path is required")
    
    # Security check: ensure it's a valid directory
    if not os.path.isdir(path):
        raise HTTPException(status_code=404, detail="Directory not found on server")

    try:
        if sys.platform == 'win32':
            os.startfile(path)
        elif sys.platform == 'darwin':
            import subprocess
            subprocess.Popen(['open', path])
        else:
            import subprocess
            subprocess.Popen(['xdg-open', path])
        return {"status": "success", "message": f"Opened {path}"}
    except Exception as e:
        logger.error(f"Failed to open folder: {e}")
        raise HTTPException(status_code=500, detail=str(e))



@app.post("/browse-directory")
async def browse_directory(body: dict):
    """Browse local directories for folder picker."""
    path = body.get("path", "")

    # If no path provided, start at root (drives on Windows, home on Linux)
    if not path:
        if sys.platform == 'win32':
            import string
            drives = []
            for letter in string.ascii_uppercase:
                drive = f"{letter}:\\"
                if os.path.exists(drive):
                    drives.append({"name": drive, "path": drive, "is_dir": True})
            return {"current": "", "parent": None, "items": drives, "is_root": True}
        else:
            path = os.path.expanduser("~")

    path = os.path.normpath(path)

    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Path not found")
    if not os.path.isdir(path):
        raise HTTPException(status_code=400, detail="Path is not a directory")

    try:
        items = []
        for name in sorted(os.listdir(path)):
            full_path = os.path.join(path, name)
            if os.path.isdir(full_path) and not name.startswith('.'):
                items.append({"name": name, "path": full_path, "is_dir": True})

        parent = os.path.dirname(path)
        if parent == path:
            parent = None
        is_root = (sys.platform == 'win32' and len(path) <= 3) or path == '/'

        return {"current": path, "parent": parent, "items": items, "is_root": is_root}
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied")
    except Exception as e:
        logger.error(f"Failed to browse directory: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.on_event("startup")
def startup_event():
    """Start the scheduler on startup and deduplicate log handlers."""
    # Deduplicate root logger StreamHandlers (uvicorn, double-imports, etc.)
    root = logging.getLogger()
    seen = set()
    for h in list(root.handlers):
        key = (type(h), getattr(h, 'stream', None))
        if key in seen:
            root.removeHandler(h)
        else:
            seen.add(key)

    # Prevent uvicorn loggers from duplicating through propagation
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        logging.getLogger(name).propagate = False

    import threading
    from backend.services.scheduler import start_scheduler

    # Run scheduler in a separate daemon thread
    t = threading.Thread(target=start_scheduler, daemon=True)
    t.start()

if __name__ == "__main__":
    import uvicorn

    # Prevent duplicate log lines: tell uvicorn loggers not to propagate
    # to the root logger (which already has a handler from above).
    for _name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        logging.getLogger(_name).propagate = False

    logger.info("Starting Planroom Genius API server...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
