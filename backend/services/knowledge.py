"""
Knowledge Scanner - Analyzes downloaded construction PDFs for fire alarm scope.
Identifies plans/specs, extracts relevant pages, sends to Gemini for analysis.
"""
import os
import json
import base64
import glob
import hashlib
import zipfile
import logging
import re
import time
import random
from datetime import datetime

from backend.config import ScraperConfig
from backend.services.storage import load_leads, direct_save_leads

logger = logging.getLogger(__name__)

BACKEND_DIR = os.path.dirname(os.path.dirname(__file__))
CACHE_FILE = os.path.join(BACKEND_DIR, "knowledge_cache.json")
DOWNLOAD_DIR = ScraperConfig.DOWNLOAD_DIR

_status = {
    "running": False,
    "last_run": None,
    "last_error": None,
    "scanned": 0,
    "skipped": 0,
    "total": 0,
    "current_project": None,
}


def get_status():
    return dict(_status)


# ---------------------------------------------------------------------------
# Manufacturer compatibility
# ---------------------------------------------------------------------------

# Our compatible manufacturers (we can bid these)
COMPATIBLE_MANUFACTURERS = {
    "gamewell", "fci", "gamewell-fci", "firelite", "fire-lite", "fire lite",
    "silent knight", "silentknight",
}

# Incompatible manufacturers (existing-to-remain = can't bid)
INCOMPATIBLE_MANUFACTURERS = {
    "est", "edwards", "siemens", "simplex", "ge", "potter", "kidde",
    "notifier", "honeywell", "bosch", "hochiki", "mircom", "vigilant",
    "farenhyt", "autocall",
}


def _adjust_score_for_manufacturers(analysis):
    """Adjust scope_score based on manufacturer compatibility."""
    raw_mfrs = analysis.get("required_manufacturers") or []
    if not raw_mfrs:
        return

    normalized = [m.lower().strip() for m in raw_mfrs]

    has_compatible = any(
        any(cm in n for cm in COMPATIBLE_MANUFACTURERS) for n in normalized
    )
    has_incompatible = any(
        any(im in n for im in INCOMPATIBLE_MANUFACTURERS) for n in normalized
    )

    system_type = analysis.get("system_type", "unknown")
    score = analysis.get("scope_score", 0)

    # Case 1: Existing system with ONLY incompatible manufacturers — hard cap
    if system_type == "existing" and has_incompatible and not has_compatible:
        analysis["scope_score"] = min(score, 15)
        analysis["manufacturer_incompatible"] = True
        deal_breakers = list(analysis.get("deal_breakers") or [])
        deal_breakers.append(f"Incompatible existing system ({', '.join(raw_mfrs)})")
        analysis["deal_breakers"] = deal_breakers
        return

    # Case 2: Any compatible manufacturer listed — boost
    if has_compatible:
        analysis["scope_score"] = min(score + 10, 100)
        analysis["manufacturer_compatible"] = True

    # Case 3: Only one manufacturer listed and it's incompatible (any system type)
    if has_incompatible and not has_compatible:
        analysis["scope_score"] = max(score - 25, 0)
        analysis["manufacturer_incompatible"] = True


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _load_cache():
    if not os.path.exists(CACHE_FILE):
        return {}
    try:
        with open(CACHE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_cache(cache):
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(cache, f, indent=2)
    except Exception as e:
        logger.warning(f"Failed to save knowledge cache: {e}")


def _hash_dir(path):
    """SHA-256 of file names + sizes + mtimes for change detection."""
    h = hashlib.sha256()
    for root, _, files in os.walk(path):
        for name in sorted(files):
            p = os.path.join(root, name)
            try:
                st = os.stat(p)
            except Exception:
                continue
            rel = os.path.relpath(p, path)
            h.update(rel.encode("utf-8", errors="ignore"))
            h.update(str(st.st_size).encode())
            h.update(str(int(st.st_mtime)).encode())
    return h.hexdigest()


# ---------------------------------------------------------------------------
# ZIP extraction  (runs before scanning)
# ---------------------------------------------------------------------------

def unzip_all_downloads():
    """Extract all .zip files in the downloads directory. Move zips into extracted folders."""
    if not os.path.exists(DOWNLOAD_DIR):
        return

    zips = [f for f in os.listdir(DOWNLOAD_DIR)
            if f.lower().endswith(".zip") and os.path.isfile(os.path.join(DOWNLOAD_DIR, f))]

    for zip_name in zips:
        zip_path = os.path.join(DOWNLOAD_DIR, zip_name)
        base_name = os.path.splitext(zip_name)[0]
        extract_dir = os.path.join(DOWNLOAD_DIR, base_name)

        try:
            if not os.path.exists(extract_dir):
                os.makedirs(extract_dir, exist_ok=True)
                with zipfile.ZipFile(zip_path, "r") as zf:
                    zf.extractall(extract_dir)
                logger.info(f"Extracted: {zip_name}")

            # Move original zip inside extracted folder to prevent re-extraction
            target = os.path.join(extract_dir, zip_name)
            if not os.path.exists(target):
                os.replace(zip_path, target)

            # Handle nested zips inside the extracted folder
            _unzip_nested(extract_dir)
        except Exception as e:
            logger.warning(f"Unzip failed for {zip_name}: {e}")


def _unzip_nested(directory):
    """Recursively extract any .zip files found inside a directory."""
    for root, _, files in os.walk(directory):
        for f in files:
            if not f.lower().endswith(".zip"):
                continue
            zp = os.path.join(root, f)
            base = os.path.splitext(f)[0]
            dest = os.path.join(root, base)
            if os.path.exists(dest):
                continue  # already extracted
            try:
                os.makedirs(dest, exist_ok=True)
                with zipfile.ZipFile(zp, "r") as zf:
                    zf.extractall(dest)
                # move zip into extracted folder
                target = os.path.join(dest, f)
                if not os.path.exists(target):
                    os.replace(zp, target)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Google Drive file download (for projects stored in GDrive)
# ---------------------------------------------------------------------------

def download_gdrive_files_for_leads(leads):
    """
    Download files from Google Drive for leads that have gdrive_file_id.
    Only downloads if local folder doesn't already exist.
    Returns count of downloaded files.
    """
    try:
        from backend.services import google_drive
    except ImportError:
        logger.warning("Google Drive module not available")
        return 0

    if not google_drive.is_available() or not google_drive.is_authenticated():
        logger.info("Google Drive not available or not authenticated, skipping GDrive downloads")
        return 0

    downloaded = 0
    for lead in leads:
        gdrive_id = lead.get("gdrive_file_id")
        if not gdrive_id:
            continue

        lead_name = lead.get("name", "")
        if not lead_name:
            continue

        # Check if we already have a local folder for this lead
        existing_folder = _find_download_folder_for_lead(lead)
        if existing_folder and os.path.isdir(existing_folder):
            logger.debug(f"Local folder exists for '{lead_name}', skipping GDrive download")
            continue

        # Download from Google Drive
        logger.info(f"Downloading GDrive files for: {lead_name}")
        try:
            local_path = google_drive.download_file(gdrive_id, destination_dir=DOWNLOAD_DIR)
            if local_path:
                downloaded += 1
                logger.info(f"Downloaded: {local_path}")

                # Create a project-named folder for this lead
                project_name_clean = "".join(
                    c for c in lead_name[:60] if c.isalnum() or c in " -_"
                ).strip()
                project_folder = os.path.join(DOWNLOAD_DIR, project_name_clean) if project_name_clean else None

                if local_path.lower().endswith(".zip"):
                    # Extract ZIP into a project-named folder
                    extract_dir = project_folder or os.path.join(DOWNLOAD_DIR, os.path.splitext(os.path.basename(local_path))[0])
                    if not os.path.exists(extract_dir):
                        try:
                            os.makedirs(extract_dir, exist_ok=True)
                            with zipfile.ZipFile(local_path, "r") as zf:
                                zf.extractall(extract_dir)
                            logger.info(f"Extracted: {os.path.basename(local_path)}")
                            # Move zip into extracted folder
                            target = os.path.join(extract_dir, os.path.basename(local_path))
                            if not os.path.exists(target):
                                os.replace(local_path, target)
                            # Handle nested zips
                            _unzip_nested(extract_dir)
                        except Exception as e:
                            logger.warning(f"Failed to extract {local_path}: {e}")
                elif project_folder:
                    # Non-ZIP file (PDF, etc.) — move into a project-named folder
                    # so the knowledge scanner can find it as a directory target
                    try:
                        os.makedirs(project_folder, exist_ok=True)
                        target = os.path.join(project_folder, os.path.basename(local_path))
                        if not os.path.exists(target):
                            os.replace(local_path, target)
                        logger.info(f"Moved to project folder: {project_name_clean}/")
                    except Exception as e:
                        logger.warning(f"Failed to move file to project folder: {e}")
        except Exception as e:
            logger.warning(f"Failed to download GDrive file for '{lead_name}': {e}")

    return downloaded


# ---------------------------------------------------------------------------
# Lead ↔ folder matching
# ---------------------------------------------------------------------------

def _normalize(s):
    return "".join(c.lower() for c in (s or "") if c.isalnum())


def _match_lead_for_folder(leads, folder_name):
    target = _normalize(folder_name)
    if not target:
        return None
    for lead in leads:
        name = _normalize(lead.get("name"))
        if not name:
            continue
        if name in target or target in name:
            return lead
    return None


# ---------------------------------------------------------------------------
# PDF discovery & classification
# ---------------------------------------------------------------------------

def _find_pdfs(root_dir):
    pdfs = []
    for root, _, files in os.walk(root_dir):
        for f in files:
            if f.lower().endswith(".pdf"):
                pdfs.append(os.path.join(root, f))
    return pdfs


# Patterns for plan files
_PLAN_DIR_PATTERNS = re.compile(
    r"(plan|drawing|dwg|sheet|blueprint)", re.IGNORECASE
)
_PLAN_FILE_PATTERNS = re.compile(
    r"(plan|drawing|dwg|sheet|blueprint|E[\-_\s]?\d|FA[\-_\s]?\d|FP[\-_\s]?\d|M[\-_\s]?\d)", re.IGNORECASE
)

# Patterns for spec files
_SPEC_DIR_PATTERNS = re.compile(
    r"(spec|specification|project\s*manual|division|section)", re.IGNORECASE
)
_SPEC_FILE_PATTERNS = re.compile(
    r"(spec|specification|manual|division|section|vol)", re.IGNORECASE
)

# Patterns for addendum files
_ADDENDUM_PATTERNS = re.compile(
    r"(addend|addm|add[_\-\s]?\d|bulletin|revision|rev[_\-\s]?\d|asr|rfi)", re.IGNORECASE
)


# ---------------------------------------------------------------------------
# File Filtering Logic
# ---------------------------------------------------------------------------

def _should_skip_file(filename):
    """
    Return True if the file should be skipped based on its name/discipline.
    Filters out Architectural (A), Civil (C), Landscape (L), Structural (S), 
    and Demolition plans unless they explicitly mention Fire Alarm.
    """
    fname = filename.upper()
    
    # Always process if it looks like fire alarm explicitly
    # FA, FIRE, ALARM, or E/Electrical with Demo
    if any(kw in fname for kw in ["FIRE", "ALARM", "FA-", "FA_", " FA ", "FP-", "FP_"]):
        return False

    # Check for Electrical or Fire Protection prefixes - never skip
    cleaned = re.sub(r'^[\d.]+[\-_\s]*', '', fname) # Remove numbering prefix like 001- or 1.02_
    if re.match(r'^(E|FA|FP)[\-_\s]?\d', cleaned):
        return False

    # Skip specific disciplines if they don't have fire keywords
    # A=Arch, AD=Arch Demo, C=Civil, L=Landscape, S=Structural, P=Plumbing, M=Mechanical
    # Note: Sometimes Mechanical has duct detectors, but usually M-sheets are huge. 
    # Let's be conservative and skip major disciplines unless they have keywords.
    skip_prefixes = ["A", "AD", "C", "L", "S", "P", "I"] # I=Interiors
    
    for prefix in skip_prefixes:
        # Check if it starts with "A1", "A-1", "A 1", etc.
        if re.match(rf"^{prefix}[\-_\s]?\d", cleaned):
            return True
            
    # Skip explicit demolition unless it's electrical demo or fire alarm demo
    if "DEMO" in fname and "E" not in fname and "FA" not in fname:
        return True

    # Skip Civil/Structural/Landscape keywords explicitly
    skip_keywords = ["CIVIL", "LANDSCAPE", "STRUCTURAL", "IRRIGATION", "PLUMBING", "INTERIOR"]
    if any(kw in fname for kw in skip_keywords):
        return True

    return False


def _classify_pdfs(root_dir):
    """
    Classify PDFs into plans, specs, and other.
    Checks directory names first, then filenames, then first-page content.
    Returns (plan_files, spec_files, other_files).
    """
    pdfs = _find_pdfs(root_dir)
    if not pdfs:
        return [], [], []

    plan_files = []
    spec_files = []
    other_files = []

    for path in pdfs:
        rel = os.path.relpath(path, root_dir)
        parts = rel.replace("\\", "/").split("/")
        fname = parts[-1].lower()
        dirs = "/".join(parts[:-1]).lower()

        classified = False

        # 1) Check directory path
        if _PLAN_DIR_PATTERNS.search(dirs):
            plan_files.append(path)
            classified = True
        elif _SPEC_DIR_PATTERNS.search(dirs):
            spec_files.append(path)
            classified = True

        if classified:
            continue

        # 2) Check filename
        if _SPEC_FILE_PATTERNS.search(fname):
            spec_files.append(path)
        elif _PLAN_FILE_PATTERNS.search(fname):
            plan_files.append(path)
        else:
            other_files.append(path)

    # 3) If we found nothing classified, try first-page text heuristics on "other"
    if not plan_files and not spec_files and other_files:
        still_other = []
        for path in other_files:
            try:
                texts = _extract_page_texts(path, max_pages=2)
                first = " ".join(texts[:2]).lower()
                if any(kw in first for kw in ["specifications", "table of contents", "division", "section"]):
                    spec_files.append(path)
                elif any(kw in first for kw in ["drawing index", "sheet index", "plan", "electrical"]):
                    plan_files.append(path)
                else:
                    still_other.append(path)
            except Exception:
                still_other.append(path)
        other_files = still_other

    return plan_files, spec_files, other_files


def _detect_addendums(root_dir):
    """
    Detect addendum/bulletin/revision files in a project directory.
    Returns list of dicts with addendum info (filename, date_modified).
    """
    addendums = []
    for root, _, files in os.walk(root_dir):
        for f in files:
            fname = f.lower()
            if _ADDENDUM_PATTERNS.search(fname):
                path = os.path.join(root, f)
                try:
                    stat = os.stat(path)
                    mtime = datetime.fromtimestamp(stat.st_mtime).isoformat()
                except Exception:
                    mtime = None
                addendums.append({
                    "filename": f,
                    "path": os.path.relpath(path, root_dir),
                    "modified": mtime
                })
    # Sort by modification time (newest first)
    addendums.sort(key=lambda x: x.get("modified") or "", reverse=True)
    return addendums


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def _extract_page_texts(pdf_path, max_pages=None):
    try:
        import fitz
    except ImportError:
        logger.error("PyMuPDF (fitz) not installed. Run: pip install PyMuPDF")
        return []

    texts = []
    try:
        doc = fitz.open(pdf_path)
        limit = max_pages if max_pages else len(doc)
        for i in range(min(limit, len(doc))):
            texts.append(doc[i].get_text("text"))
        doc.close()
    except Exception as e:
        logger.warning(f"Failed to extract text from {pdf_path}: {e}")
    return texts


# ---------------------------------------------------------------------------
# Page selection – only send relevant pages to AI
# ---------------------------------------------------------------------------

_INCLUDE_KEYWORDS = [
    "fire alarm", "fire detection", "fire notification",
    "power plan", "power riser",
    "special systems", "special system",
    "general electrical notes", "electrical notes",
    "electrical general",
    "general hvac notes", "hvac notes", "mechanical notes",
    "code compliance", "code footprint", "life safety",
    "ibc", "nfpa",
    "duct detector", "fire smoke damper", "smoke damper",
    "smoke detector", "fire protection",
]

_EXCLUDE_KEYWORDS = [
    "lighting", "luminaire", "light fixture", "photometric",
    "fixture plan", "lighting plan", "site lighting",
    "panel schedule", "electrical schedule",
    "schematic", "riser diagram", "one-line", "one line",
]

# Sheet number patterns for electrical pages (E-101, FA-1, FP-2, etc.)
_ELEC_SHEET_RE = re.compile(
    r"\b(E[\-_]?\d|FA[\-_]?\d|FP[\-_]?\d|EG[\-_]?\d|EP[\-_]?\d|ES[\-_]?\d)\b",
    re.IGNORECASE,
)


def _select_relevant_pages(page_texts):
    """Pick pages relevant to fire alarm analysis. Returns sorted list of indices."""
    selected = set()

    # Always include first 3 pages (cover, index, general notes)
    for i in range(min(3, len(page_texts))):
        selected.add(i)

    for i, text in enumerate(page_texts):
        t = (text or "").lower()
        if not t.strip():
            continue

        # Check exclusions first
        if any(kw in t for kw in _EXCLUDE_KEYWORDS):
            # But still include if it also has fire alarm / duct detector content
            if not any(kw in t for kw in ["fire alarm", "duct detector", "smoke damper", "fire smoke damper"]):
                continue

        # Check inclusions
        if any(kw in t for kw in _INCLUDE_KEYWORDS):
            selected.add(i)

        # Check electrical sheet numbers
        if _ELEC_SHEET_RE.search(text or ""):
            selected.add(i)

    return sorted(selected)


# ---------------------------------------------------------------------------
# Image rendering (PyMuPDF)
# ---------------------------------------------------------------------------

def _render_pages(pdf_path, page_indices, dpi=150, as_jpeg=False):
    """Render specific pages to images. Returns list of {page_index, png_bytes, mime_type}.
    If as_jpeg=True, converts to JPEG for smaller payloads (no PIL needed)."""
    try:
        import fitz
    except ImportError:
        return []

    images = []
    try:
        doc = fitz.open(pdf_path)
        for idx in page_indices:
            if idx < 0 or idx >= len(doc):
                continue
            page = doc.load_page(idx)
            pix = page.get_pixmap(dpi=dpi)
            png_bytes = pix.tobytes("png")
            if as_jpeg:
                try:
                    from PIL import Image
                    import io
                    img = Image.open(io.BytesIO(png_bytes))
                    buf = io.BytesIO()
                    img.save(buf, format="JPEG", quality=60, optimize=True)
                    images.append({"page_index": idx, "png_bytes": buf.getvalue(), "mime_type": "image/jpeg"})
                except ImportError:
                    logger.warning("Pillow not installed, sending PNG to Gemini (install Pillow for smaller payloads)")
                    images.append({"page_index": idx, "png_bytes": png_bytes, "mime_type": "image/png"})
            else:
                images.append({"page_index": idx, "png_bytes": png_bytes, "mime_type": "image/png"})
        doc.close()
    except Exception as e:
        logger.warning(f"Render failed for {pdf_path}: {e}")
    return images


def render_first_page_thumbnail(pdf_path, dpi=72):
    """Render page 0 as a low-res thumbnail. Returns base64 PNG string or None."""
    imgs = _render_pages(pdf_path, [0], dpi=dpi)
    if imgs:
        return base64.b64encode(imgs[0]["png_bytes"]).decode("utf-8")
    return None


# ---------------------------------------------------------------------------
# Gemini AI analysis
# ---------------------------------------------------------------------------

_GEMINI_PROMPT = """You are an expert fire alarm preconstruction estimator.
Analyze these document pages AS A COMPLETE SET and return ONE project-level qualification assessment.
Do not output per-page results.

Return ONLY valid JSON with EXACTLY this schema:
{
  "requires_fire_alarm": true/false,
  "system_type": "new" | "existing" | "modification" | "unknown",
  "required_vendors": ["vendor1", "vendor2"],
  "required_manufacturers": ["mfr1", "mfr2"],
  "required_codes": ["NFPA 72-2019"],
  "deal_breakers": ["item1"],
  "bid_risk_flags": ["union-only", "proprietary vendor lock", "short timeline"],
  "scope_signals": {
    "new_install": true/false,
    "retrofit": true/false,
    "monitoring": true/false,
    "voice_evac": true/false,
    "duct_detectors": true/false,
    "access_control_interface": true/false
  },
  "evidence": [
    {
      "claim": "short statement of a qualification-relevant fact",
      "page_reference": "file/page reference if available",
      "quote": "short exact quote from documents"
    }
  ],
  "confidence_score": 0.0,
  "recommended_next_action": "bid" | "review" | "skip",
  "notes": "Brief qualification summary (2-4 sentences)",
  "scope_score": 0-100
}

Guidelines:
- Focus on qualification, bid viability, and risk (not just fire alarm detection).
- confidence_score must be 0.0 to 1.0 and reflect evidence quality and ambiguity.
- evidence must include concrete support for key conclusions; use [] if no reliable support found.
- bid_risk_flags should include known bid constraints (labor restrictions, proprietary requirements, compressed schedule, unusual coordination burden, etc.).
- scope_signals booleans should reflect whether each signal appears in plans/specs.
- recommended_next_action:
    * "bid" when scope is clear and winnable.
    * "review" when viable but uncertain/risky and needs human estimator review.
    * "skip" when poor fit, no FA scope, or hard constraints.
- required_manufacturers: Extract EXACT manufacturer names from plans/specs (e.g., "Gamewell-FCI", "EST", "Simplex", "Siemens"). Include the existing panel manufacturer if visible on plans.
- required_vendors/required_manufacturers/deal_breakers should remain concise factual lists.
- scope_score remains a 0-100 attractiveness score.

Return ONLY JSON, no markdown fences or extra text."""


def _default_analysis_result(notes=""):
    return {
        "requires_fire_alarm": False,
        "system_type": "unknown",
        "required_vendors": [],
        "required_manufacturers": [],
        "deal_breakers": [],
        "bid_risk_flags": [],
        "scope_signals": {
            "new_install": False,
            "retrofit": False,
            "monitoring": False,
            "voice_evac": False,
            "duct_detectors": False,
            "access_control_interface": False,
        },
        "evidence": [],
        "confidence_score": 0.0,
        "recommended_next_action": "review",
        "notes": notes,
        "scope_score": 0,
    }


def _normalize_analysis_result(raw, fallback_notes=""):
    """Backfill missing keys and sanitize malformed Gemini responses."""
    normalized = _default_analysis_result(notes=fallback_notes)
    if not isinstance(raw, dict):
        return normalized

    normalized["requires_fire_alarm"] = bool(raw.get("requires_fire_alarm", normalized["requires_fire_alarm"]))

    system_type = str(raw.get("system_type", normalized["system_type"]))
    if system_type in {"new", "existing", "modification", "unknown"}:
        normalized["system_type"] = system_type

    for key in ("required_vendors", "required_manufacturers", "deal_breakers", "bid_risk_flags"):
        value = raw.get(key)
        if isinstance(value, list):
            normalized[key] = [str(item).strip() for item in value if str(item).strip()]

    scope_signals = raw.get("scope_signals")
    if isinstance(scope_signals, dict):
        for signal in normalized["scope_signals"]:
            if signal in scope_signals:
                normalized["scope_signals"][signal] = bool(scope_signals.get(signal))

    evidence = raw.get("evidence")
    if isinstance(evidence, list):
        cleaned = []
        for item in evidence:
            if not isinstance(item, dict):
                continue
            cleaned.append({
                "claim": str(item.get("claim", "")).strip(),
                "page_reference": str(item.get("page_reference", "")).strip(),
                "quote": str(item.get("quote", "")).strip(),
            })
        normalized["evidence"] = cleaned

    confidence = raw.get("confidence_score")
    if isinstance(confidence, (int, float)):
        normalized["confidence_score"] = max(0.0, min(1.0, float(confidence)))

    action = str(raw.get("recommended_next_action", normalized["recommended_next_action"]))
    if action in {"bid", "review", "skip"}:
        normalized["recommended_next_action"] = action

    notes = raw.get("notes")
    if notes is not None:
        normalized["notes"] = str(notes)

    score = raw.get("scope_score")
    if isinstance(score, (int, float)):
        normalized["scope_score"] = max(0, min(100, int(score)))

    return normalized


def _normalize_claim_text(claim):
    return re.sub(r"\s+", " ", str(claim or "").strip().lower())


def _validate_analysis_claim_evidence(analysis):
    """Reject unsupported high-impact claims and capture validation warnings."""
    if not isinstance(analysis, dict):
        return analysis

    evidence = analysis.get("evidence")
    if not isinstance(evidence, dict):
        evidence = {}

    warnings = analysis.get("validation_warnings")
    if not isinstance(warnings, list):
        warnings = []

    claim_fields = ("required_vendors", "required_manufacturers", "required_codes", "deal_breakers")
    sanitized_evidence = {}

    for field in claim_fields:
        claims = analysis.get(field)
        if not isinstance(claims, list):
            claims = []

        field_evidence = evidence.get(field)
        if not isinstance(field_evidence, list):
            field_evidence = []

        valid_claims = []
        valid_evidence = []
        for claim in claims:
            normalized_claim = _normalize_claim_text(claim)
            if not normalized_claim:
                continue

            match = None
            for item in field_evidence:
                if not isinstance(item, dict):
                    continue
                ev_claim = _normalize_claim_text(item.get("claim"))
                page = item.get("page")
                quote = str(item.get("quote") or "").strip()
                if ev_claim != normalized_claim:
                    continue
                if not isinstance(page, int) or page < 1 or not quote:
                    continue
                match = {
                    "claim": str(claim).strip(),
                    "page": page,
                    "quote": quote[:200],
                }
                break

            if match:
                valid_claims.append(str(claim).strip())
                valid_evidence.append(match)
            else:
                warnings.append(f"Dropped {field} claim without evidence: {claim}")

        analysis[field] = valid_claims
        sanitized_evidence[field] = valid_evidence

    analysis["evidence"] = sanitized_evidence
    analysis["validation_warnings"] = warnings
    return analysis


def _call_gemini(images, context=""):
    api_key = os.getenv("GEMINI_API_KEY_PLANROOM_GENIUS", "").strip()
    if not api_key:
        logger.warning("GEMINI_API_KEY_PLANROOM_GENIUS not set, falling back to heuristic analysis")
        return None

    import requests as req

    parts = [{"text": _GEMINI_PROMPT + "\n\nProject context: " + context}]
    for img in images:
        b64 = base64.b64encode(img["png_bytes"]).decode("utf-8")
        mime = img.get("mime_type", "image/png")
        parts.append({
            "inlineData": {"mimeType": mime, "data": b64}
        })

    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {"temperature": 0.1},
    }

    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3-pro-preview:generateContent"
    
    max_retries = 5
    base_delay = 2.0

    for attempt in range(max_retries):
        try:
            res = req.post(url, params={"key": api_key}, json=payload, timeout=180)
            res.raise_for_status()
            data = res.json()
            # If successful, parse and return
            if "candidates" in data and data["candidates"]:
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                # Strip markdown fences if Gemini wraps them
                text = text.strip()
                if text.startswith("```"):
                    text = re.sub(r"^```(?:json)?\s*", "", text)
                    text = re.sub(r"\s*```$", "", text)
                try:
                    parsed = json.loads(text)
                    return _normalize_analysis_result(parsed)
                except json.JSONDecodeError:
                    logger.warning("Gemini returned non-JSON, using deterministic fallback structure")
                    return _normalize_analysis_result({}, fallback_notes=text)
            else:
                 logger.warning(f"Gemini response structure unexpected: {data}")
                 return _normalize_analysis_result({}, fallback_notes="Gemini response structure unexpected")

        except req.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                logger.warning(f"Gemini rate limit hit (429). Retrying in {delay:.2f}s... (Attempt {attempt+1}/{max_retries})")
                time.sleep(delay)
                continue
            else:
                logger.error(f"Gemini HTTP error: {e}")
                return _normalize_analysis_result({}, fallback_notes=f"Gemini HTTP error: {e}")
        except (req.exceptions.Timeout, req.exceptions.ConnectionError) as e:
            delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
            logger.warning(f"Gemini timeout/connection error. Retrying in {delay:.2f}s... (Attempt {attempt+1}/{max_retries}): {e}")
            time.sleep(delay)
            continue
        except Exception as e:
            logger.warning(f"Gemini call failed: {e}")
            return _normalize_analysis_result({}, fallback_notes=f"Gemini call failed: {e}")

    logger.error("Gemini failed after max retries.")
    return _normalize_analysis_result({}, fallback_notes="Gemini failed after retries")


def _heuristic_analysis(all_text):
    """Fallback analysis when Gemini is unavailable."""
    t = all_text.lower()
    requires = "fire alarm" in t or "fire detection" in t
    system_type = "unknown"
    vendors = []
    manufacturers = []
    breakers = []

    if "existing" in t and ("remain" in t or "as-is" in t):
        system_type = "existing"
    elif "new fire alarm" in t or "new system" in t:
        system_type = "new"
    elif "modify" in t or "modification" in t or "retrofit" in t:
        system_type = "modification"

    if "approved vendor" in t or "required vendor" in t:
        vendors.append("specified (see specs)")
    if "approved manufacturer" in t or "listed manufacturer" in t:
        manufacturers.append("specified (see specs)")
    if "no fire alarm" in t or "fire alarm not required" in t:
        requires = False

    score = 0
    if requires:
        score = 50
        if "fire alarm" in t:
            fa_count = t.count("fire alarm")
            score = min(90, 40 + fa_count * 5)
        if system_type == "existing":
            score = max(20, score - 20)

    return _normalize_analysis_result({
        "requires_fire_alarm": requires,
        "system_type": system_type,
        "required_vendors": vendors,
        "required_manufacturers": manufacturers,
        "required_codes": [],
        "deal_breakers": breakers,
        "evidence": {
            "required_vendors": [],
            "required_manufacturers": [],
            "required_codes": [],
            "deal_breakers": [],
        },
        "validation_warnings": [],
        "notes": "Heuristic analysis (Gemini API key not configured)",
        "scope_score": score,
    })


# ---------------------------------------------------------------------------
# Compute badges & bid chance
# ---------------------------------------------------------------------------

def _compute_badges(analysis):
    badges = []
    if not analysis.get("requires_fire_alarm"):
        badges.append("NO FA")
    st = analysis.get("system_type", "unknown")
    if st == "existing":
        badges.append("EXISTING")
    elif st == "new":
        badges.append("NEW SYSTEM")
    elif st == "modification":
        badges.append("MOD")
    if analysis.get("required_vendors"):
        badges.append("REQ VENDOR")
    if analysis.get("required_manufacturers"):
        badges.append("REQ MFR")
    if analysis.get("manufacturer_compatible"):
        badges.append("COMPAT MFR")
    if analysis.get("manufacturer_incompatible"):
        badges.append("INCOMPAT MFR")
    if analysis.get("deal_breakers"):
        badges.append("DEAL BREAKER")
    # Scope signal badges
    signals = analysis.get("scope_signals") or {}
    if signals.get("voice_evac"):
        badges.append("VOICE")
    if signals.get("monitoring"):
        badges.append("MONITORING")
    if signals.get("access_control_interface"):
        badges.append("ACCESS CTRL")
    return badges





# ---------------------------------------------------------------------------
# File listing with thumbnails (for Point-to-File UI)
# ---------------------------------------------------------------------------

def list_project_files(lead_id):
    """List all PDFs for a project with classification and thumbnail."""
    leads = load_leads()
    lead = None
    for l in leads:
        if l.get("id") == lead_id:
            lead = l
            break
    if not lead:
        return {"error": "Lead not found"}

    # Find matching download folder
    folder = _find_download_folder_for_lead(lead)
    if not folder:
        return {"error": "No download folder found", "files": []}

    plan_files, spec_files, other_files = _classify_pdfs(folder)
    cache = _load_cache()
    folder_name = os.path.basename(folder)
    overrides = cache.get(folder_name, {}).get("overrides", {})

    results = []
    for path in plan_files + spec_files + other_files:
        rel = os.path.relpath(path, folder)
        classification = "plan" if path in plan_files else ("spec" if path in spec_files else "other")

        # Check for manual override
        if rel in overrides:
            classification = overrides[rel]

        results.append({
            "filename": os.path.basename(path),
            "rel_path": rel,
            "classification": classification,
            "size_kb": round(os.path.getsize(path) / 1024),
        })

    # Include files that are overridden as "ignore" but weren't in the classification lists
    # (they may have been excluded by _apply_overrides during scanning)
    all_pdfs = _find_pdfs(folder)
    existing_rels = {r["rel_path"] for r in results}
    for path in all_pdfs:
        rel = os.path.relpath(path, folder)
        if rel not in existing_rels and overrides.get(rel) == "ignore":
            results.append({
                "filename": os.path.basename(path),
                "rel_path": rel,
                "classification": "ignore",
                "size_kb": round(os.path.getsize(path) / 1024),
            })

    return {"files": results, "folder": folder}


def render_page_for_viewing(lead_id, rel_path, page=0, dpi=150):
    """Render a single page of a PDF at viewable resolution. Returns PNG bytes or None."""
    try:
        import fitz
    except ImportError:
        logger.error("PyMuPDF (fitz) not installed")
        return None

    leads = load_leads()
    lead = next((l for l in leads if l.get("id") == lead_id), None)
    if not lead:
        return None

    folder = _find_download_folder_for_lead(lead)
    if not folder:
        return None

    pdf_path = os.path.join(folder, rel_path)
    if not os.path.isfile(pdf_path):
        return None

    try:
        doc = fitz.open(pdf_path)
        if page < 0 or page >= len(doc):
            doc.close()
            return None
        pix = doc.load_page(page).get_pixmap(dpi=dpi)
        png_bytes = pix.tobytes("png")
        doc.close()
        return png_bytes
    except Exception as e:
        logger.warning(f"Failed to render page {page} of {rel_path}: {e}")
        return None


def get_page_count(lead_id, rel_path):
    """Return total page count for a PDF."""
    try:
        import fitz
    except ImportError:
        return 0

    leads = load_leads()
    lead = next((l for l in leads if l.get("id") == lead_id), None)
    if not lead:
        return 0

    folder = _find_download_folder_for_lead(lead)
    if not folder:
        return 0

    pdf_path = os.path.join(folder, rel_path)
    if not os.path.isfile(pdf_path):
        return 0

    try:
        doc = fitz.open(pdf_path)
        count = len(doc)
        doc.close()
        return count
    except Exception:
        return 0


def get_title_thumbnail(lead_id):
    """Get first page thumbnail of the first PDF found for this lead."""
    leads = load_leads()
    lead = next((l for l in leads if l.get("id") == lead_id), None)
    if not lead:
        return {"thumbnail": None}
    folder = _find_download_folder_for_lead(lead)
    if not folder:
        return {"thumbnail": None}
    pdfs = sorted(glob.glob(os.path.join(folder, "**/*.pdf"), recursive=True))
    if not pdfs:
        return {"thumbnail": None}
    thumb = render_first_page_thumbnail(pdfs[0], dpi=72)
    return {"thumbnail": thumb}


def _find_download_folder_for_lead(lead):
    """Find the project folder (custom path or download dir)."""
    # 1. Start with custom user-provided link
    files_link = lead.get("files_link")
    files_link = files_link.strip() if files_link else ""
    if files_link and os.path.isdir(files_link):
        return files_link

    # 2. Check local_file_path (sometimes set by scrapers)
    local_path = lead.get("local_file_path")
    local_path = local_path.strip() if local_path else ""
    if local_path:
        # Check absolute
        if os.path.isdir(local_path):
            return local_path
        # Check relative to downloads
        full_path = os.path.join(DOWNLOAD_DIR, local_path)
        if os.path.isdir(full_path):
            return full_path

    # 3. Fallback: Search in DOWNLOAD_DIR by matching name
    if not os.path.exists(DOWNLOAD_DIR):
        return None
    lead_name = lead.get("name", "")
    if not lead_name:
        return None

    for name in os.listdir(DOWNLOAD_DIR):
        path = os.path.join(DOWNLOAD_DIR, name)
        if not os.path.isdir(path):
            continue
        # Normalize comparison
        n_name = _normalize(name)
        n_lead = _normalize(lead_name)
        if n_name and n_lead:
            if n_name in n_lead or n_lead in n_name:
                return path
    return None


def set_file_override(lead_id, rel_path, classification):
    """Manually set a file's classification (plan/spec/other)."""
    leads = load_leads()
    lead = None
    for l in leads:
        if l.get("id") == lead_id:
            lead = l
            break
    if not lead:
        return False

    folder = _find_download_folder_for_lead(lead)
    if not folder:
        return False

    folder_name = os.path.basename(folder)
    cache = _load_cache()
    entry = cache.setdefault(folder_name, {})
    overrides = entry.setdefault("overrides", {})
    overrides[rel_path] = classification
    # Clear signature to force rescan
    entry.pop("signature", None)
    _save_cache(cache)
    return True


def set_file_overrides_batch(lead_id, overrides_dict):
    """Batch-set file classifications. overrides_dict maps rel_path -> classification."""
    leads = load_leads()
    lead = None
    for l in leads:
        if l.get("id") == lead_id:
            lead = l
            break
    if not lead:
        return False

    folder = _find_download_folder_for_lead(lead)
    if not folder:
        return False

    folder_name = os.path.basename(folder)
    cache = _load_cache()
    entry = cache.setdefault(folder_name, {})
    overrides = entry.setdefault("overrides", {})
    overrides.update(overrides_dict)
    # Clear signature to force rescan
    entry.pop("signature", None)
    _save_cache(cache)
    return True


# ---------------------------------------------------------------------------
# Main scan
# ---------------------------------------------------------------------------

def _scan_project_folder(project_dir, cache, leads, folder_name=None, known_lead=None, force_rescan=False):
    """
    Core scanning logic for a single project folder.
    Returns True if scanned, False if skipped.
    """
    if not _status["running"]:
        return False

    if not folder_name:
        folder_name = os.path.basename(project_dir)

    # Match folder to lead to get metadata (and check priority)
    matched_lead = known_lead
    if not matched_lead:
        matched_lead = _match_lead_for_folder(leads, folder_name)

    # Priority check (skip Low priority unless forced or single-lead scan)
    # If known_lead is passed (single scan), we usually ignore priority
    if not known_lead:
        if matched_lead and matched_lead.get("priority") == "Low" and not force_rescan:
            logger.info(f"Skipping Low Priority project: {folder_name}")
            _status["skipped"] += 1
            return False

    # Check cache for skip
    signature = _hash_dir(project_dir)
    cache_entry = cache.get(folder_name, {})
    if not force_rescan and cache_entry.get("signature") == signature:
        _status["skipped"] += 1
        return False

    _status["current_project"] = folder_name
    logger.info(f"Knowledge scan: processing {folder_name}")

    # Classify PDFs
    plan_files, spec_files, other_files = _classify_pdfs(project_dir)

    # Apply manual overrides from cache
    overrides = cache.get(folder_name, {}).get("overrides", {})
    if overrides:
        plan_files, spec_files, other_files = _apply_overrides(
            project_dir, plan_files, spec_files, other_files, overrides
        )

    candidates = plan_files + spec_files
    if not candidates:
        candidates = other_files  # fallback: scan everything

    if not candidates:
        cache[folder_name] = {
            "signature": signature,
            "last_scan": datetime.now().isoformat(),
        }
        _status["skipped"] += 1
        return False

    # Collect selected pages/images across all candidate PDFs first,
    # then send one consolidated project-level Gemini request.
    project_images = []
    project_text_chunks = []
    project_context_files = []
    diagnostics = []

    for i, pdf_path in enumerate(candidates):
        if not _status["running"]:
            break

        filename = os.path.basename(pdf_path)

        # SKIP LOGIC: Filter out irrelevant disciplines and demo plans
        if _should_skip_file(filename):
            logger.info(f"Skipping irrelevant file: {filename}")
            continue

        _status["current_project"] = f"{folder_name} ({filename} - {i+1}/{len(candidates)})"
        logger.info(f"Collecting relevant pages from: {filename}")

        try:
            texts = _extract_page_texts(pdf_path)
            if not texts:
                diagnostics.append({"file": filename, "selected_pages": [], "reason": "no_text"})
                continue

            pages = _select_relevant_pages(texts)
            if not pages:
                diagnostics.append({"file": filename, "selected_pages": [], "reason": "no_relevant_pages"})
                continue

            # Collect text for fallback heuristic and context payload
            selected_text = "\n".join(texts[p] for p in pages if p < len(texts))
            project_text_chunks.append(selected_text)

            project_context_files.append({
                "file": os.path.relpath(pdf_path, project_dir),
                "page_indices": pages,
            })

            # Render selected pages as JPEG at low DPI for AI analysis
            images = _render_pages(pdf_path, pages, dpi=72, as_jpeg=True)
            for img in images:
                project_images.append({
                    "file": os.path.relpath(pdf_path, project_dir),
                    "page_index": img.get("page_index"),
                    "png_bytes": img.get("png_bytes"),
                })

            diagnostics.append({"file": filename, "selected_pages": pages, "reason": "included"})

        except Exception as e:
            logger.warning(f"Error collecting pages for {pdf_path}: {e}")
            diagnostics.append({"file": filename, "selected_pages": [], "reason": f"error: {e}"})

    project_context = {
        "project": folder_name,
        "files": project_context_files,
    }

    model_analysis = None
    if project_images:
        # Cap images by count and total payload size
        MAX_IMAGES = 20
        MAX_PAYLOAD_MB = 4
        if len(project_images) > MAX_IMAGES:
            logger.info(f"Capping images from {len(project_images)} to {MAX_IMAGES} for Gemini")
            project_images = project_images[:MAX_IMAGES]

        # Drop largest images first if payload exceeds limit
        total_bytes = sum(len(img["png_bytes"]) for img in project_images)
        if total_bytes > MAX_PAYLOAD_MB * 1024 * 1024:
            # Sort by size descending, drop biggest until under limit
            project_images.sort(key=lambda x: len(x["png_bytes"]), reverse=True)
            while project_images and total_bytes > MAX_PAYLOAD_MB * 1024 * 1024:
                dropped = project_images.pop(0)
                total_bytes -= len(dropped["png_bytes"])
                logger.info(f"Dropped large page (file={dropped['file']}, page={dropped['page_index']}, {len(dropped['png_bytes'])/1024:.0f}KB) to fit payload limit")
            # Re-sort by original order (file, page_index)
            project_images.sort(key=lambda x: (x["file"], x["page_index"]))

        total_bytes = sum(len(img["png_bytes"]) for img in project_images)
        logger.info(f"Sending {len(project_images)} pages to Gemini ({total_bytes / 1024 / 1024:.1f} MB)")

        # Single consolidated Gemini request for project-level decision.
        model_analysis = _call_gemini(project_images, json.dumps(project_context, separators=(",", ":")))

    heuristic_analysis = _heuristic_analysis("\n".join(project_text_chunks))
    aggregate = model_analysis or heuristic_analysis

    # Keep model-provided project score primary; fallback to heuristic score if missing.
    if not isinstance(aggregate.get("scope_score"), (int, float)):
        aggregate["scope_score"] = heuristic_analysis.get("scope_score", 0)

    # Ensure normalized output shape and include optional diagnostics only in notes.
    aggregate["requires_fire_alarm"] = bool(aggregate.get("requires_fire_alarm", heuristic_analysis.get("requires_fire_alarm", False)))
    aggregate["system_type"] = aggregate.get("system_type") or heuristic_analysis.get("system_type", "unknown")
    aggregate["required_vendors"] = list(aggregate.get("required_vendors") or heuristic_analysis.get("required_vendors") or [])
    aggregate["required_manufacturers"] = list(aggregate.get("required_manufacturers") or heuristic_analysis.get("required_manufacturers") or [])
    aggregate["deal_breakers"] = list(aggregate.get("deal_breakers") or heuristic_analysis.get("deal_breakers") or [])
    aggregate["required_codes"] = list(aggregate.get("required_codes") or heuristic_analysis.get("required_codes") or [])
    aggregate["evidence"] = aggregate.get("evidence") or heuristic_analysis.get("evidence") or []
    aggregate["validation_warnings"] = list(aggregate.get("validation_warnings") or heuristic_analysis.get("validation_warnings") or [])
    notes = aggregate.get("notes") or ""
    if isinstance(notes, list):
        notes = "\n".join(str(n) for n in notes)
    if diagnostics:
        notes = f"{notes}\n[diagnostics] files_processed={len(diagnostics)}, files_with_selected_pages={len(project_context_files)}".strip()
    aggregate["notes"] = [str(notes)] if notes else []
    aggregate["scope_score"] = int(aggregate.get("scope_score", 0))

    # Adjust score based on manufacturer compatibility
    _adjust_score_for_manufacturers(aggregate)

    # Match to lead and update (if not provided)
    lead = matched_lead
    if lead:
        badges = _compute_badges(aggregate)


        # Detect addendums
        addendums = _detect_addendums(project_dir)

        lead["knowledge_last_scanned"] = datetime.now().isoformat()
        lead["knowledge_requires_fire_alarm"] = aggregate["requires_fire_alarm"]
        lead["knowledge_system_type"] = aggregate["system_type"]
        lead["knowledge_required_vendors"] = list(set(aggregate["required_vendors"]))
        lead["knowledge_required_manufacturers"] = list(set(aggregate["required_manufacturers"]))
        lead["knowledge_required_codes"] = list(set(aggregate["required_codes"]))
        lead["knowledge_deal_breakers"] = list(set(aggregate["deal_breakers"]))
        lead["knowledge_evidence"] = aggregate["evidence"]
        lead["knowledge_validation_warnings"] = aggregate["validation_warnings"][:25]
        lead["knowledge_notes"] = "\n".join(aggregate["notes"])[:2000]
        lead["knowledge_score"] = aggregate["scope_score"]
        lead["knowledge_badges"] = badges
        lead["knowledge_scope_signals"] = aggregate.get("scope_signals") or {}
        lead["knowledge_bid_risk_flags"] = list(aggregate.get("bid_risk_flags") or [])

        lead["knowledge_addendums"] = addendums[:10]  # Limit to 10 most recent
        lead["knowledge_file_count"] = len(plan_files) + len(spec_files) + len(other_files)

    # Update cache
    cache[folder_name] = {
        "signature": signature,
        "last_scan": datetime.now().isoformat(),
        "plan_files": [os.path.relpath(f, project_dir) for f in plan_files],
        "spec_files": [os.path.relpath(f, project_dir) for f in spec_files],
        "overrides": cache.get(folder_name, {}).get("overrides", {}),
    }
    _status["scanned"] += 1
    return True

def stop_scan():
    """Stop the current knowledge scan."""
    global _status
    if _status["running"]:
        _status["running"] = False
        logger.info("Knowledge scan stop requested")
        return True
    return False

def scan_local_downloads(lead_id=None, force_rescan=False):
    """
    Scan downloaded project files and analyze them with AI.
    
    Args:
        lead_id: If provided, only scan that specific project (and bypass cache for it).
        force_rescan: If True, clear cache and rescan ALL projects regardless of previous scans.
    """
    if _status["running"]:
        return _status

    # If force_rescan for ALL projects (no lead_id), clear the cache
    # but preserve overrides. For single-lead rescans, only clear that project's signature.
    if force_rescan and not lead_id:
        logger.info("Force rescan requested - clearing knowledge cache (preserving overrides)")
        old_cache = _load_cache()
        new_cache = {}
        for key, entry in old_cache.items():
            if entry.get("overrides"):
                new_cache[key] = {"overrides": entry["overrides"]}
        _save_cache(new_cache)

    _status.update({
        "running": True,
        "last_error": None,
        "scanned": 0,
        "skipped": 0,
        "total": 0,
        "current_project": None,
    })

    try:
        # Step 0: Load leads first so we can download from GDrive if needed
        leads = load_leads()
        
        # Step 1: Download files from Google Drive for leads without local files
        logger.info("Knowledge scan: checking for GDrive files to download...")
        gdrive_downloaded = download_gdrive_files_for_leads(leads)
        if gdrive_downloaded:
            logger.info(f"Downloaded {gdrive_downloaded} files from Google Drive")
        
        # Step 2: Unzip all archives
        logger.info("Knowledge scan: extracting zip archives...")
        unzip_all_downloads()

        cache = _load_cache()

        # Step 3: Build list of scan targets
        # List of tuple: (absolute_path, folder_name_for_cache, known_lead_obj)
        targets = []
        
        # 3a. Add standard folders from DOWNLOAD_DIR
        if os.path.exists(DOWNLOAD_DIR):
            for name in os.listdir(DOWNLOAD_DIR):
                path = os.path.join(DOWNLOAD_DIR, name)
                if os.path.isdir(path):
                    targets.append((path, name, None))

        # 3b. Add custom paths from leads (files_link or local_file_path)
        for lead in leads:
            # Check files_link (Manual link)
            link = lead.get("files_link")
            link = link.strip() if link else ""
            if link and os.path.isdir(link):
                # Only add if not already in targets (by path)
                if not any(os.path.abspath(t[0]) == os.path.abspath(link) for t in targets):
                    targets.append((link, os.path.basename(link), lead))
                continue # Prioritize files_link
            
            # Check local_file_path (Scraper/Manual absolute path)
            local = lead.get("local_file_path")
            local = local.strip() if local else ""
            if local and os.path.isabs(local) and os.path.isdir(local):
                 if not any(os.path.abspath(t[0]) == os.path.abspath(local) for t in targets):
                    targets.append((local, os.path.basename(local), lead))

        # 3c. Filter if single lead requested
        if lead_id:
            target_lead = next((l for l in leads if l["id"] == lead_id), None)
            if target_lead:
                # Find the ONE folder for this lead
                target_path = _find_download_folder_for_lead(target_lead)
                if target_path and os.path.isdir(target_path):
                    # Override targets list to just this one
                    targets = [(target_path, os.path.basename(target_path), target_lead)]
                else:
                    # No folder found - set a clear message on the lead so
                    # the user knows the scan couldn't find any files
                    logger.warning(f"No download folder found for lead '{target_lead.get('name')}' (id={lead_id})")
                    target_lead["knowledge_last_scanned"] = datetime.now().isoformat()
                    target_lead["knowledge_notes"] = "No project files found. Use the files link field to point to a local folder, or download files first."
                    target_lead["knowledge_score"] = 0
                    target_lead["knowledge_badges"] = []
                    direct_save_leads(leads)
                    _status["running"] = False
                    _status["current_project"] = None
                    _status["last_run"] = datetime.now().isoformat()
                    return _status
            else:
                targets = []
        
        _status["total"] = len(targets)
        logger.info(f"Knowledge scan: found {len(targets)} targets to process")

        # Step 4: Process targets
        for path, name, known_lead in targets:
            if not _status["running"]:
                logger.info("Scan stopped by user")
                break
            
            _scan_project_folder(
                project_dir=path, 
                cache=cache, 
                leads=leads, 
                folder_name=name, 
                known_lead=known_lead, 
                force_rescan=force_rescan
            )

        # Save everything
        direct_save_leads(leads)
        _save_cache(cache)
        _status["last_run"] = datetime.now().isoformat()
        _status["current_project"] = None
        logger.info(f"Knowledge scan complete: {_status['scanned']} scanned, {_status['skipped']} skipped")
        return _status

    except Exception as e:
        logger.error(f"Knowledge scan error: {e}", exc_info=True)
        _status["last_error"] = str(e)
        return _status
    finally:
        _status["running"] = False
        _status["current_project"] = None


def _apply_overrides(project_dir, plan_files, spec_files, other_files, overrides):
    """Reclassify files based on manual overrides."""
    all_files = {os.path.relpath(f, project_dir): f for f in plan_files + spec_files + other_files}
    new_plans, new_specs, new_other = [], [], []

    for rel, abspath in all_files.items():
        cls = overrides.get(rel)
        if cls == "plan":
            new_plans.append(abspath)
        elif cls == "spec":
            new_specs.append(abspath)
        elif cls == "other":
            new_other.append(abspath)
        elif cls == "ignore":
            pass  # Drop ignored files from all classification lists
        else:
            # Keep original classification
            if abspath in plan_files:
                new_plans.append(abspath)
            elif abspath in spec_files:
                new_specs.append(abspath)
            else:
                new_other.append(abspath)

    return new_plans, new_specs, new_other


# ---------------------------------------------------------------------------
# High-level ranking pass (all projects at once)
# ---------------------------------------------------------------------------

def rank_all_projects():
    """
    After individual scans, make a high-level pass ranking all projects.
    Sorts by scope score and bid chance.
    """
    leads = load_leads()
    scanned = [l for l in leads if l.get("knowledge_last_scanned")]
    if not scanned:
        return []

    # Sort by: bid_chance (high first), then score (descending)
    # Sort by score (descending)
    scanned.sort(key=lambda l: -(l.get("knowledge_score", 0)))

    return [
        {
            "id": l.get("id"),
            "name": l.get("name"),
            "score": l.get("knowledge_score", 0),

            "badges": l.get("knowledge_badges", []),
            "system_type": l.get("knowledge_system_type", "unknown"),
        }
        for l in scanned
    ]
