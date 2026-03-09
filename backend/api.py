from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import Response
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
            "planhub": status["ph_leads_found"],
            "bidplanroom": status.get("bpr_leads_found", 0),
            "loydbuilds": status.get("lbb_leads_found", 0),
            "isqft": status.get("isqft_leads_found", 0)
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
            "hidden", "comments", "short_comment", "tags",  # New management fields
            "qa_history"  # Q&A history
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


# ==================== Notion Integration ====================

NOTION_TOKEN = os.getenv("NOTION_TOKEN", "")
NOTION_DB_ID = os.getenv("NOTION_DB_ID", "22b30dfde2d780979c80c0e3e7af56f4")
NOTION_COMPANY_DB_ID = os.getenv("NOTION_COMPANY_DB_ID", "23030dfde2d7800eb347e6aedcdff420")
NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

# Known Building Type options in the Notion database
NOTION_BUILDING_TYPES = {
    "industrial": "Industrial/Warehouse",
    "warehouse": "Industrial/Warehouse",
    "healthcare": "Healthcare",
    "hospital": "Healthcare",
    "clinic": "Healthcare",
    "medical": "Healthcare",
    "school": "School",
    "education": "School",
    "university": "School",
    "college": "School",
    "retail": "Retail",
    "office": "Office",
    "hotel": "Hotel",
    "residential": "Residential",
    "apartment": "Residential",
    "multifamily": "Residential",
}

NOTION_PROJECT_TYPES = {
    "installation": "Installation",
    "install": "Installation",
    "parts": "Parts & Smarts",
    "smarts": "Parts & Smarts",
    "parts & smarts": "Parts & Smarts",
    "other": "Other",
}

NOTION_CONSTRUCTION_TYPES = [
    ("tenant improvement", "Tenant Improvement/Renovation"),
    ("tenant build", "Tenant Improvement/Renovation"),
    ("ti ", "Tenant Improvement/Renovation"),
    ("remodel", "Remodel / Renovation"),
    ("renovation", "Remodel / Renovation"),
    ("new construction", "New Construction"),
    ("new fire panel", "New Fire Panel"),
]

NOTION_SPECIAL_REQUIREMENTS = [
    ("tax exempt", "Tax Exempt"),
    ("prevailing wage", "Prevailing Wage"),
    ("bid bond", "Bid Bond"),
    ("buy american", "Buy American Build American"),
    ("baba", "Buy American Build American"),
]


def _notion_headers():
    return {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _match_building_type(text: str):
    """Map free-text building type to a known Notion select option."""
    if not text:
        return None
    lower = text.lower()
    for key, val in NOTION_BUILDING_TYPES.items():
        if key in lower:
            return val
    return None


def _match_project_type(text: str):
    """Map free-text project type to a known Notion select option."""
    if not text:
        return None
    lower = text.lower()
    for key, val in NOTION_PROJECT_TYPES.items():
        if key in lower:
            return val
    return None


def _match_construction_types(text: str):
    """Map free-text construction type to known Notion multi_select options."""
    if not text:
        return []
    lower = text.lower()
    matched = []
    for key, val in NOTION_CONSTRUCTION_TYPES:
        if key in lower and val not in matched:
            matched.append(val)
    return matched


def _match_special_requirements(lead: dict):
    """Extract special requirements from lead tags and knowledge fields."""
    matched = set()
    # Check tags
    tags = lead.get("tags") or []
    tag_labels = " ".join(t.get("label", "").lower() for t in tags)
    # Check knowledge deal breakers and description
    extra_text = " ".join(filter(None, [
        lead.get("description", ""),
        lead.get("knowledge_notes", ""),
        str(lead.get("knowledge_deal_breakers", "")),
    ])).lower()
    combined = tag_labels + " " + extra_text
    for key, val in NOTION_SPECIAL_REQUIREMENTS:
        if key in combined:
            matched.add(val)
    # Check if BABA tag is present
    if any(t.get("label", "").upper() == "BABA" for t in tags):
        matched.add("Buy American Build American")
    return list(matched)


def _search_company_in_notion(company_name: str):
    """Search the Notion Companies database for a matching company by name."""
    import requests as req
    if not company_name or company_name in ("N/A", ""):
        return None
    try:
        resp = req.post(
            f"{NOTION_API_BASE}/databases/{NOTION_COMPANY_DB_ID}/query",
            headers=_notion_headers(),
            json={
                "filter": {
                    "property": "Company Name",
                    "title": {"contains": company_name[:50]}
                },
                "page_size": 5,
            },
            timeout=10,
        )
        if resp.status_code == 200:
            results = resp.json().get("results", [])
            if results:
                return results[0]["id"]
    except Exception as e:
        logger.warning(f"Company search in Notion failed: {e}")
    return None


@app.post("/leads/{lead_id}/notion")
async def send_lead_to_notion(lead_id: str):
    """Send a lead to the Notion Open Quotes database."""
    import requests as req
    from backend.services.storage import load_leads

    leads = load_leads()
    lead = next((l for l in leads if l.get("id") == lead_id), None)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    # --- Build Notion properties ---
    properties = {}

    # Project Name (title)
    project_name = lead.get("name") or "Untitled Project"
    properties["Project Name"] = {
        "title": [{"text": {"content": project_name[:2000]}}]
    }

    # Due Date
    bid_date = lead.get("bid_date") or lead.get("due_date")
    if bid_date and bid_date not in ("N/A", "TBD", ""):
        from backend.config import DATE_FORMATS
        from datetime import datetime as _dt
        parsed_date = None
        # Try ISO format first (most scrapers store in this format)
        try:
            parsed_date = _dt.fromisoformat(str(bid_date).replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            pass
        if not parsed_date:
            for fmt in DATE_FORMATS:
                try:
                    parsed_date = _dt.strptime(str(bid_date).strip(), fmt)
                    break
                except (ValueError, AttributeError):
                    continue
        if parsed_date:
            properties["Due Date"] = {"date": {"start": parsed_date.strftime("%Y-%m-%d")}}

    # Project Address (place type) — requires lat/lon from geocoding
    address = lead.get("full_address") or lead.get("location") or ""
    if address and address not in ("N/A", ""):
        try:
            geo_resp = req.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": address, "format": "json", "limit": 1},
                headers={"User-Agent": "planroom-genius/1.0 (contact@marmicfire.com)"},
                timeout=5,
            )
            if geo_resp.status_code == 200:
                results = geo_resp.json()
                if results:
                    lat = float(results[0]["lat"])
                    lon = float(results[0]["lon"])
                    # query is the human-readable address shown in Notion
                    properties["Project Address"] = {
                        "place": {"lat": lat, "lon": lon, "query": address[:500]}
                    }
        except Exception as geo_err:
            logger.warning(f"Geocoding failed for '{address}': {geo_err}")

    # Company (relation)
    company_name = lead.get("company") or lead.get("gc") or ""
    company_page_id = _search_company_in_notion(company_name)
    if company_page_id:
        properties["Company"] = {"relation": [{"id": company_page_id}]}

    # Building Type (select) — from takeoff_snapshot or project_type field
    snap = lead.get("takeoff_snapshot") or {}
    pd = snap.get("project_details") or {}
    building_type_raw = (
        pd.get("building_type") or
        pd.get("occupancy_type") or
        lead.get("building_type") or ""
    )
    building_type_mapped = _match_building_type(building_type_raw)
    if building_type_mapped:
        properties["Building Type"] = {"select": {"name": building_type_mapped}}

    # Project Type (select)
    project_type_raw = (
        pd.get("project_type") or
        lead.get("project_type") or ""
    )
    project_type_mapped = _match_project_type(project_type_raw)
    if project_type_mapped:
        properties["Project Type"] = {"select": {"name": project_type_mapped}}

    # Construction Type (multi_select)
    construction_type_raw = (
        pd.get("construction_type") or
        lead.get("construction_type") or
        project_type_raw or ""
    )
    construction_types = _match_construction_types(construction_type_raw)
    if construction_types:
        properties["Construction Type"] = {
            "multi_select": [{"name": ct} for ct in construction_types]
        }

    # Special Requirements (multi_select)
    special_reqs = _match_special_requirements(lead)
    if special_reqs:
        properties["Special Requirements"] = {
            "multi_select": [{"name": sr} for sr in special_reqs]
        }

    # Status = "Active"
    properties["Status"] = {"status": {"name": "Active"}}

    # --- Build page body with contact/address info ---
    def _txt_block(text: str):
        return {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": text[:2000]}}]
            }
        }

    children = []
    address = lead.get("full_address") or lead.get("location") or ""
    contact_name = lead.get("contact_name") or ""
    contact_phone = lead.get("contact_phone") or ""
    contact_email = lead.get("contact_email") or ""
    company = lead.get("company") or lead.get("gc") or ""

    info_lines = []
    if address and address not in ("N/A", ""):
        info_lines.append(f"Address: {address}")
    if company and company not in ("N/A", ""):
        info_lines.append(f"Company: {company}")
    if contact_name and contact_name not in ("N/A", ""):
        info_lines.append(f"Contact: {contact_name}")
    if contact_phone:
        info_lines.append(f"Phone: {contact_phone}")
    if contact_email:
        info_lines.append(f"Email: {contact_email}")

    if info_lines:
        children.append({
            "object": "block",
            "type": "callout",
            "callout": {
                "rich_text": [{"type": "text", "text": {"content": "\n".join(info_lines)}}],
                "icon": {"type": "emoji", "emoji": "📋"},
                "color": "gray_background",
            }
        })

    # Notes from lead description
    notes = lead.get("knowledge_notes") or lead.get("description") or ""
    if notes:
        # Strip HTML tags simply
        import re as _re
        notes_clean = _re.sub(r'<[^>]+>', '', notes).strip()[:1900]
        if notes_clean:
            children.append(_txt_block(notes_clean))

    # --- Create the Notion page ---
    payload = {
        "parent": {"database_id": NOTION_DB_ID},
        "properties": properties,
    }
    if children:
        payload["children"] = children

    try:
        resp = req.post(
            f"{NOTION_API_BASE}/pages",
            headers=_notion_headers(),
            json=payload,
            timeout=15,
        )
        if resp.status_code in (200, 201):
            page = resp.json()
            page_url = page.get("url", "")
            logger.info(f"Created Notion page for lead {lead_id}: {page_url}")
            return {
                "status": "success",
                "notion_url": page_url,
                "notion_page_id": page.get("id"),
            }
        else:
            error_body = resp.json()
            msg = error_body.get("message", resp.text)
            logger.error(f"Notion API error for lead {lead_id}: {resp.status_code} {msg}")
            raise HTTPException(status_code=502, detail=f"Notion API error: {msg}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to send lead {lead_id} to Notion: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Project Q&A Endpoint ====================

@app.post("/leads/{lead_id}/ask")
async def ask_project_question(lead_id: str, body: dict):
    """Ask an AI question about a project's files."""
    from backend.services.knowledge import ask_project_question as _ask

    question = (body.get("question") or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question is required")

    try:
        answer, error = _ask(lead_id, question)
        if error:
            raise HTTPException(status_code=400, detail=error)

        # Return updated qa_history
        from backend.services.storage import load_leads
        leads = load_leads()
        lead = next((l for l in leads if l.get("id") == lead_id), None)
        qa_history = lead.get("qa_history", []) if lead else []

        return {"answer": answer, "qa_history": qa_history}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Q&A failed for {lead_id}: {e}")
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
async def knowledge_scan_single(lead_id: str, background_tasks: BackgroundTasks, thinking: bool = False):
    """Rescan a single project (bypasses cache). Use ?thinking=true for deep takeoff analysis."""
    from backend.services.knowledge import scan_local_downloads, run_deep_scan, get_status

    status = get_status()
    if status["running"]:
        return {"status": "already_running", "details": status}

    if thinking:
        background_tasks.add_task(run_deep_scan, lead_id)
        msg = f"Deep takeoff scan started for {lead_id}"
    else:
        background_tasks.add_task(scan_local_downloads, lead_id, force_rescan=True, thinking=False)
        msg = f"Knowledge scan started for {lead_id}"
    return {"status": "accepted", "message": msg}


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
    if not rel_path or classification not in ("plan", "spec", "other", "ignore"):
        raise HTTPException(status_code=400, detail="rel_path and classification (plan/spec/other/ignore) required")

    ok = set_file_override(lead_id, rel_path, classification)
    if not ok:
        raise HTTPException(status_code=404, detail="Lead or folder not found")
    return {"status": "success"}


@app.post("/knowledge/files/{lead_id}/override-batch")
async def knowledge_file_override_batch(lead_id: str, body: dict):
    """Batch-set file classifications for all files in a project."""
    from backend.services.knowledge import set_file_overrides_batch

    overrides = body.get("overrides")
    if not isinstance(overrides, dict) or not overrides:
        raise HTTPException(status_code=400, detail="overrides dict required")

    valid_classes = {"plan", "spec", "other", "ignore"}
    for rel_path, cls in overrides.items():
        if cls not in valid_classes:
            raise HTTPException(status_code=400, detail=f"Invalid classification '{cls}' for {rel_path}")

    ok = set_file_overrides_batch(lead_id, overrides)
    if not ok:
        raise HTTPException(status_code=404, detail="Lead or folder not found")
    return {"status": "success"}


@app.get("/knowledge/files/{lead_id}/view/{rel_path:path}")
async def knowledge_file_view(lead_id: str, rel_path: str, page: int = 0, dpi: int = 150):
    """Render a single PDF page as a PNG image for viewing."""
    from backend.services.knowledge import render_page_for_viewing
    import hashlib as _hl

    # Cap DPI to prevent abuse
    dpi = min(dpi, 300)
    png_bytes = render_page_for_viewing(lead_id, rel_path, page=page, dpi=dpi)
    if not png_bytes:
        raise HTTPException(status_code=404, detail="Page not found or render failed")
    etag = _hl.md5(png_bytes).hexdigest()
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={
            "Cache-Control": "public, max-age=86400",
            "ETag": f'"{etag}"',
        },
    )


@app.get("/knowledge/files/{lead_id}/pagecount/{rel_path:path}")
async def knowledge_file_pagecount(lead_id: str, rel_path: str):
    """Return page count for a PDF."""
    from backend.services.knowledge import get_page_count

    count = get_page_count(lead_id, rel_path)
    return {"pages": count}


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
    # Force exactly ONE StreamHandler on root logger.
    # Multiple sources (run.py basicConfig, uvicorn, double-imports) each add
    # handlers, causing every log line to print N times.
    root = logging.getLogger()
    stream_handlers = [h for h in root.handlers if isinstance(h, logging.StreamHandler)]
    if len(stream_handlers) > 1:
        keeper = stream_handlers[0]
        for h in stream_handlers[1:]:
            root.removeHandler(h)
        logger.info(f"Removed {len(stream_handlers) - 1} duplicate log handlers")

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
