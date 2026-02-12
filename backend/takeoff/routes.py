"""
Takeoff Routes - FastAPI endpoints for Fire Alarm Takeoff Assistant

This module provides FastAPI router with all endpoints needed for the
Fire Alarm Takeoff Assistant functionality.
"""
import os
import io
import uuid
import json
import base64
import tempfile
import threading
import logging
import time
from pathlib import Path
from datetime import datetime
from collections import Counter
from typing import Optional, List

import fitz
from PIL import Image
from fastapi import APIRouter, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse, StreamingResponse, FileResponse
from starlette.responses import Response

from . import takeoff_config as config
from .models import FireAlarmDevice, PageAnalysis
from .gemini_report_builder import build_gemini_report
from .history_store import HistoryStore
from .notion_client import NotionClient
from .gemini_analyzer import (
    GeminiFireAlarmAnalyzer as GeminiAnalyzer,
    ANALYSIS_MODES,
)
from .pdf_processor import PDFProcessor
from .visualizer import DetectionVisualizer

# Try to import local YOLO detector
LocalYOLODetector = None
LOCAL_YOLO_IMPORT_ERROR = None
try:
    from .local_yolo_detector import LocalYOLODetector
except Exception as exc:
    LOCAL_YOLO_IMPORT_ERROR = str(exc)

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/takeoff", tags=["takeoff"])

# Storage for analysis jobs
analysis_jobs = {}
analysis_lock = threading.Lock()
history_store = HistoryStore()
notion_client = NotionClient(
    getattr(config, 'NOTION_API_TOKEN', ''),
    getattr(config, 'NOTION_DATABASE_ID', '')
)

# Preview cache
PREVIEW_CACHE_TTL_SECONDS = 900
PREVIEW_CACHE_MAX_ENTRIES = 12
preview_cache = {}


class TakeoffAnalyzer:
    """Main analyzer class that coordinates all components."""

    def __init__(self):
        self.pdf_processor = PDFProcessor(dpi=getattr(config, 'DPI', 350))
        self.local_detector = None
        self.local_detector_error: str | None = None
        self.gemini_analyzer = GeminiAnalyzer()
        self.visualizer = DetectionVisualizer()
        self._initialize_local_detector()

    def _initialize_local_detector(self) -> None:
        """Initialize local detection model if available."""
        model_path = getattr(config, 'LOCAL_MODEL_PATH', None)
        self.local_detector_error = None

        if LocalYOLODetector is None:
            base_error = "Local detector module could not be imported"
            if LOCAL_YOLO_IMPORT_ERROR:
                base_error = f"{base_error}: {LOCAL_YOLO_IMPORT_ERROR}"
            self.local_detector_error = base_error
            logger.warning("⚠️ %s", self.local_detector_error)
            return

        if not model_path:
            self.local_detector_error = "LOCAL_MODEL_PATH is not configured"
            logger.warning("⚠️ %s", self.local_detector_error)
            return

        if not os.path.exists(model_path):
            self.local_detector_error = f"Local model file not found at {model_path}"
            logger.warning("⚠️ %s", self.local_detector_error)
            return

        try:
            logger.info("Initializing local detector from %s", model_path)
            self.local_detector = LocalYOLODetector(model_path)
            logger.info("✅ Local detector initialized successfully!")
        except Exception as exc:
            self.local_detector_error = f"Failed to initialize local detector: {exc}"
            logger.error("❌ %s", self.local_detector_error, exc_info=True)


# Global analyzer instance (initialized on first use)
_analyzer: TakeoffAnalyzer | None = None


def get_analyzer() -> TakeoffAnalyzer:
    """Get or create the global analyzer instance."""
    global _analyzer
    if _analyzer is None:
        _analyzer = TakeoffAnalyzer()
    return _analyzer


# =============================================================================
# MAIN PAGE
# =============================================================================
@router.get("/", response_class=HTMLResponse)
async def index():
    """Serve the main HTML interface."""
    template_path = Path(__file__).parent / "templates" / "index.html"
    if not template_path.exists():
        raise HTTPException(status_code=404, detail="Template not found")
    
    with open(template_path, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    return HTMLResponse(content=html_content)


# =============================================================================
# STATUS ENDPOINT
# =============================================================================
@router.get("/api/check_status")
async def check_status():
    """Check API status and configuration."""
    analyzer = get_analyzer()
    
    local_model_path = getattr(config, 'LOCAL_MODEL_PATH', '') or ''
    model_filename = os.path.basename(local_model_path) if local_model_path else ''
    model_name = os.path.splitext(model_filename)[0] if model_filename else ''

    response = {
        'local_model_configured': analyzer.local_detector is not None,
        'gemini_configured': analyzer.gemini_analyzer.is_available(),
        'local_model_name': model_name,
        'local_model_filename': model_filename,
        'local_detector_error': analyzer.local_detector_error,
        'gemini_error': getattr(analyzer.gemini_analyzer, 'initialization_error', None),
        'gemini_model': getattr(analyzer.gemini_analyzer, 'current_model', getattr(config, 'GEMINI_MODEL', None)),
        'available_gemini_models': getattr(config, 'GEMINI_MODEL_CHOICES', []),
        'gemini_system_instructions': getattr(analyzer.gemini_analyzer, 'system_instructions', ''),
        'gemini_default_system_instructions': getattr(analyzer.gemini_analyzer, 'default_system_instructions', ''),
        'gemini_analysis_mode': getattr(analyzer.gemini_analyzer, 'analysis_mode', None),
        'gemini_allowed_analysis_modes': list(ANALYSIS_MODES),
        'notion_configured': notion_client.is_configured(),
    }

    return JSONResponse(content=response)


# =============================================================================
# GEMINI MODEL SETTINGS
# =============================================================================
@router.post("/api/set_gemini_model")
async def set_gemini_model(request: Request):
    """Switch the active Gemini text model at runtime."""
    payload = await request.json()
    model = payload.get('model')

    if not model:
        return JSONResponse(content={'success': False, 'error': 'Model name is required'}, status_code=400)

    allowed_models = getattr(config, 'GEMINI_MODEL_CHOICES', [])
    if allowed_models and model not in allowed_models:
        return JSONResponse(content={'success': False, 'error': 'Model not in allowed list'}, status_code=400)

    analyzer = get_analyzer()
    if not analyzer.gemini_analyzer.update_model(model):
        error = getattr(analyzer.gemini_analyzer, 'initialization_error', 'Failed to initialize model')
        return JSONResponse(content={'success': False, 'error': error}, status_code=500)

    config.GEMINI_MODEL = model
    return JSONResponse(content={'success': True, 'gemini_model': model})


@router.post("/api/set_gemini_instructions")
async def set_gemini_instructions(request: Request):
    """Update Gemini system instructions at runtime."""
    payload = await request.json()
    instructions = payload.get('instructions')

    if instructions is None:
        return JSONResponse(content={'success': False, 'error': 'Instructions are required'}, status_code=400)

    if not isinstance(instructions, str):
        return JSONResponse(content={'success': False, 'error': 'Instructions must be a string'}, status_code=400)

    analyzer = get_analyzer()
    analyzer.gemini_analyzer.update_system_instructions(instructions)
    return JSONResponse(content={
        'success': True,
        'gemini_system_instructions': analyzer.gemini_analyzer.system_instructions,
    })

@router.post("/api/set_gemini_mode")
async def set_gemini_mode(request: Request):
    """Update Gemini analysis mode at runtime."""
    payload = await request.json()
    mode = (payload.get('mode') or '').strip().lower()

    if mode not in ANALYSIS_MODES:
        return JSONResponse(
            content={
                'success': False,
                'error': f"Mode must be one of: {', '.join(ANALYSIS_MODES)}",
            },
            status_code=400,
        )

    analyzer = get_analyzer()
    analyzer.gemini_analyzer.update_analysis_mode(mode)
    return JSONResponse(content={
        'success': True,
        'gemini_analysis_mode': analyzer.gemini_analyzer.analysis_mode,
        'gemini_system_instructions': analyzer.gemini_analyzer.system_instructions,
    })



# =============================================================================
# PREVIEW PAGES
# =============================================================================
def _cleanup_preview_cache():
    """Remove expired preview entries to keep memory usage bounded."""
    now = time.time()
    expired_keys = [
        key for key, value in preview_cache.items()
        if now - value.get("created", 0) > PREVIEW_CACHE_TTL_SECONDS
    ]

    for key in expired_keys:
        _remove_preview_entry(key)

    if len(preview_cache) > PREVIEW_CACHE_MAX_ENTRIES:
        sorted_keys = sorted(preview_cache.items(), key=lambda item: item[1].get("created", 0))
        for key, _ in sorted_keys[:-PREVIEW_CACHE_MAX_ENTRIES]:
            _remove_preview_entry(key)


def _remove_preview_entry(key: str):
    """Remove a cache entry and delete its temporary PDF."""
    entry = preview_cache.pop(key, None)
    if not entry:
        return

    pdf_path = entry.get("pdf_path")
    temp_dir = entry.get("temp_dir")

    try:
        if pdf_path and os.path.exists(pdf_path):
            os.remove(pdf_path)
        if temp_dir and os.path.isdir(temp_dir):
            os.rmdir(temp_dir)
    except OSError:
        logger.debug("Temporary preview directory already cleaned up", exc_info=True)


@router.post("/api/preview_pages")
async def preview_pages(pdf: UploadFile = File(...)):
    """Generate low-res thumbnails for PDF pages."""
    if not pdf.filename:
        return JSONResponse(content={'success': False, 'error': 'Empty filename'}, status_code=400)
    temp_dir = None
    pdf_path = None
    preview_token = None

    try:
        logger.info(f"Processing PDF preview request for: {pdf.filename}")

        temp_dir = tempfile.mkdtemp()
        pdf_path = os.path.join(temp_dir, 'upload.pdf')
        
        content = await pdf.read()
        with open(pdf_path, 'wb') as f:
            f.write(content)

        doc = fitz.open(pdf_path)
        pages = []

        for page_num in range(len(doc)):
            page = doc[page_num]
            mat = fitz.Matrix(120 / 72, 120 / 72)
            pix = page.get_pixmap(matrix=mat, alpha=False)

            base_image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            thumbnail_image = base_image.copy()
            thumbnail_image.thumbnail((220, 220))

            thumb_buffer = io.BytesIO()
            thumbnail_image.save(thumb_buffer, format="JPEG", quality=78)
            thumbnail_b64 = base64.b64encode(thumb_buffer.getvalue()).decode()

            pages.append({
                'thumbnail': f'data:image/jpeg;base64,{thumbnail_b64}',
                'page_number': page_num + 1
            })

        doc.close()

        _cleanup_preview_cache()
        preview_token = uuid.uuid4().hex
        preview_cache[preview_token] = {
            "created": time.time(),
            "pdf_path": pdf_path,
            "temp_dir": temp_dir,
            "previews": {},
        }

        return JSONResponse(content={
            'success': True,
            'pages': pages,
            'total_pages': len(pages),
            'preview_token': preview_token,
        })

    except Exception as e:
        logger.error(f"Error generating previews: {str(e)}", exc_info=True)
        if preview_token:
            _remove_preview_entry(preview_token)
        else:
            try:
                if pdf_path and os.path.exists(pdf_path):
                    os.remove(pdf_path)
                if temp_dir and os.path.isdir(temp_dir):
                    os.rmdir(temp_dir)
            except Exception:
                pass
        return JSONResponse(content={'success': False, 'error': str(e)}, status_code=500)


@router.get("/api/preview_pages/{preview_token}/{page_num}")
async def get_preview_page(preview_token: str, page_num: int):
    """Return the cached higher-resolution preview for a given page."""
    _cleanup_preview_cache()
    entry = preview_cache.get(preview_token)
    if not entry:
        return JSONResponse(content={'success': False, 'error': 'Preview token expired'}, status_code=404)

    previews = entry.get("previews", {})
    if page_num in previews:
        return JSONResponse(content={'success': True, 'preview': previews[page_num], 'page_number': page_num})

    pdf_path = entry.get("pdf_path")
    if not pdf_path or not os.path.exists(pdf_path):
        return JSONResponse(content={'success': False, 'error': 'Preview source expired'}, status_code=404)

    doc = None
    try:
        doc = fitz.open(pdf_path)
        if page_num < 1 or page_num > len(doc):
            return JSONResponse(content={'success': False, 'error': 'Invalid page number'}, status_code=404)

        page = doc[page_num - 1]
        mat = fitz.Matrix(210 / 72, 210 / 72)
        pix = page.get_pixmap(matrix=mat, alpha=False)

        preview_image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        preview_image.thumbnail((1000, 1000))

        preview_buffer = io.BytesIO()
        preview_image.save(preview_buffer, format="JPEG", quality=90)
        preview_b64 = base64.b64encode(preview_buffer.getvalue()).decode()

        previews[page_num] = f'data:image/jpeg;base64,{preview_b64}'
        entry["previews"] = previews
        preview_cache[preview_token] = entry

        return JSONResponse(content={'success': True, 'preview': previews[page_num], 'page_number': page_num})

    except Exception as e:
        logger.error(f"Error generating preview for page {page_num}: {str(e)}", exc_info=True)
        return JSONResponse(content={'success': False, 'error': 'Unable to generate preview'}, status_code=500)

    finally:
        if doc:
            doc.close()


# =============================================================================
# GEMINI ANALYSIS
# =============================================================================
@router.post("/api/analyze_gemini")
async def analyze_gemini(
    pdf: UploadFile = File(...),
    send_images: str = Form("true"),
    spec_pdf: Optional[UploadFile] = File(None),
    additional_files: Optional[List[UploadFile]] = File(None),
    analysis_mode: str = Form("advisory"),
):
    """Analyze PDF using Gemini AI."""
    analyzer = get_analyzer()
    
    if not analyzer.gemini_analyzer.is_available():
        return JSONResponse(content={'success': False, 'error': 'Gemini AI not configured'}, status_code=400)

    if not pdf.filename:
        return JSONResponse(content={'success': False, 'error': 'Empty filename'}, status_code=400)

    selected_mode = (analysis_mode or '').strip().lower()
    if selected_mode not in ANALYSIS_MODES:
        return JSONResponse(
            content={'success': False, 'error': f"Invalid analysis_mode. Allowed: {', '.join(ANALYSIS_MODES)}"},
            status_code=400,
        )

    # Save uploaded file
    job_id = str(uuid.uuid4())
    temp_dir = tempfile.mkdtemp()
    pdf_path = os.path.join(temp_dir, 'upload.pdf')
    
    content = await pdf.read()
    with open(pdf_path, 'wb') as f:
        f.write(content)

    # Handle additional attachments
    additional_spec_paths = []
    if additional_files:
        for idx, attachment in enumerate(additional_files):
            if not attachment or not attachment.filename:
                continue
            safe_name = os.path.basename(attachment.filename)
            attachment_path = os.path.join(temp_dir, f'attachment_{idx}_{safe_name}')
            att_content = await attachment.read()
            with open(attachment_path, 'wb') as f:
                f.write(att_content)
            additional_spec_paths.append(attachment_path)

    spec_path = None
    if spec_pdf and spec_pdf.filename:
        spec_path = os.path.join(temp_dir, 'spec.pdf')
        spec_content = await spec_pdf.read()
        with open(spec_path, 'wb') as f:
            f.write(spec_content)

    try:
        logger.info(f"Starting Gemini analysis job {job_id}")

        results = analyzer.gemini_analyzer.analyze_pdf(
            pdf_path,
            include_images=(send_images.lower() == 'true'),
            spec_pdf_path=spec_path,
            additional_spec_paths=additional_spec_paths,
            analysis_mode=selected_mode,
        )
        results['job_id'] = job_id

        project_name = _extract_project_name(results, pdf.filename)

        # Store results
        with analysis_lock:
            analysis_jobs[job_id] = {
                'results': results,
                'pdf_path': pdf_path,
                'temp_dir': temp_dir,
                'spec_pdf_path': spec_path,
                'additional_spec_paths': additional_spec_paths,
                'timestamp': datetime.now().isoformat(),
                'analysis_type': 'gemini'
            }

        history_store.save_entry(
            job_id,
            analysis_type='gemini',
            original_filename=pdf.filename,
            results=results,
            pdf_path=pdf_path,
            project_name=project_name,
        )

        logger.info(f"Gemini analysis {job_id} completed")
        return JSONResponse(content=results)

    except Exception as e:
        logger.error(f"Error in Gemini analysis: {str(e)}", exc_info=True)
        if os.path.exists(pdf_path):
            os.remove(pdf_path)
        if spec_path and os.path.exists(spec_path):
            os.remove(spec_path)
        for path in additional_spec_paths:
            if os.path.exists(path):
                os.remove(path)
        if os.path.exists(temp_dir):
            try:
                os.rmdir(temp_dir)
            except:
                pass
        return JSONResponse(content={'success': False, 'error': str(e)}, status_code=500)


@router.post("/api/gemini_follow_up")
async def gemini_follow_up(request: Request):
    """Answer follow-up questions using prior Gemini context."""
    analyzer = get_analyzer()
    
    if not analyzer.gemini_analyzer.is_available():
        return JSONResponse(content={'success': False, 'error': 'Gemini AI not configured'}, status_code=400)

    payload = await request.json()
    question = (payload.get('question') or '').strip()
    job_id = payload.get('job_id')

    if not question:
        return JSONResponse(content={'success': False, 'error': 'A follow-up question is required.'}, status_code=400)

    if not job_id:
        return JSONResponse(content={'success': False, 'error': 'Missing job_id for follow-up context.'}, status_code=400)

    with analysis_lock:
        job = analysis_jobs.get(job_id)

    if not job or job.get('analysis_type') != 'gemini':
        return JSONResponse(content={'success': False, 'error': 'Gemini analysis results not found for this job ID.'}, status_code=404)

    try:
        results = job.get('results') or {}
        pdf_path = job.get('pdf_path')
        spec_pdf_path = job.get('spec_pdf_path')
        additional_spec_paths = job.get('additional_spec_paths')

        follow_up = analyzer.gemini_analyzer.answer_follow_up_question(
            question,
            prior_results=results,
            pdf_path=pdf_path,
            spec_pdf_path=spec_pdf_path,
            additional_spec_paths=additional_spec_paths,
        )

        status_code = 200 if follow_up.get('success') else 400
        return JSONResponse(content=follow_up, status_code=status_code)
    except Exception as exc:
        logger.error("Follow-up question failed: %s", exc, exc_info=True)
        return JSONResponse(content={'success': False, 'error': str(exc)}, status_code=500)


@router.post("/api/run_gemini_from_history/{job_id}")
async def run_gemini_from_history(job_id: str, request: Request):
    """Re-run Gemini analysis for a stored history entry."""
    analyzer = get_analyzer()
    
    if not analyzer.gemini_analyzer.is_available():
        return JSONResponse(content={'success': False, 'error': 'Gemini AI not configured'}, status_code=400)

    entry = history_store.load_entry(job_id)
    if not entry:
        return JSONResponse(content={'success': False, 'error': 'History entry not found'}, status_code=404)

    pdf_path = entry.get('pdf_path')
    if not pdf_path or not os.path.exists(pdf_path):
        return JSONResponse(content={'success': False, 'error': 'Original PDF file not found in history'}, status_code=404)

    selected_mode = 'advisory'
    try:
        payload = await request.json()
        selected_mode = ((payload or {}).get('analysis_mode') or selected_mode).strip().lower()
    except Exception:
        selected_mode = 'advisory'

    if selected_mode not in ANALYSIS_MODES:
        return JSONResponse(
            content={'success': False, 'error': f"Invalid analysis_mode. Allowed: {', '.join(ANALYSIS_MODES)}"},
            status_code=400,
        )

    try:
        logger.info(f"Starting Gemini analysis for history job {job_id}")
        original_filename = entry.get('original_filename', 'history_reanalysis.pdf')

        results = analyzer.gemini_analyzer.analyze_pdf(
            pdf_path,
            include_images=True,
            spec_pdf_path=None,
            additional_spec_paths=[],
            analysis_mode=selected_mode,
        )
        results['job_id'] = job_id

        project_name = _extract_project_name(results, original_filename)

        with analysis_lock:
            analysis_jobs[job_id] = {
                'results': results,
                'pdf_path': pdf_path,
                'temp_dir': entry.get('storage_dir'),
                'timestamp': datetime.now().isoformat(),
                'analysis_type': 'gemini'
            }

        history_store.save_entry(
            job_id,
            analysis_type='gemini',
            original_filename=original_filename,
            results=results,
            pdf_path=pdf_path,
            project_name=project_name,
        )

        return JSONResponse(content=results)

    except Exception as e:
        logger.error(f"Error in Gemini history re-analysis: {str(e)}", exc_info=True)
        return JSONResponse(content={'success': False, 'error': str(e)}, status_code=500)


# =============================================================================
# NOTION EXPORT
# =============================================================================
@router.post("/api/notion/export")
async def export_to_notion(request: Request):
    """Send the latest Gemini project snapshot to Notion."""
    if not notion_client.is_configured():
        return JSONResponse(content={'success': False, 'error': 'Notion is not configured.'}, status_code=400)

    payload = await request.json()
    job_id = payload.get('job_id')

    if not job_id:
        return JSONResponse(content={'success': False, 'error': 'Missing job_id for Notion export.'}, status_code=400)

    with analysis_lock:
        job = analysis_jobs.get(job_id)

    if not job or job.get('analysis_type') != 'gemini':
        return JSONResponse(content={'success': False, 'error': 'Gemini results not found for this job ID.'}, status_code=404)

    results = job.get('results') or {}
    response = notion_client.create_project_page(results)
    status_code = 200 if response.get('success') else 500
    return JSONResponse(content=response, status_code=status_code)


# =============================================================================
# HISTORY
# =============================================================================
@router.get("/api/history")
async def list_history():
    """Return metadata for all stored analyses."""
    entries = history_store.list_entries()
    return JSONResponse(content={'success': True, 'entries': entries})


@router.get("/api/history/{job_id}")
async def load_history(job_id: str):
    """Load stored results for a previous analysis run."""
    entry = history_store.load_entry(job_id)
    if not entry:
        return JSONResponse(content={'success': False, 'error': 'History entry not found'}, status_code=404)

    with analysis_lock:
        if job_id not in analysis_jobs:
            analysis_jobs[job_id] = {
                'results': entry['results'],
                'pdf_path': entry['pdf_path'],
                'temp_dir': entry['storage_dir'],
                'timestamp': entry.get('timestamp'),
                'analysis_type': entry.get('analysis_type'),
            }

    payload = {**entry['results']}
    payload['job_id'] = job_id

    return JSONResponse(content={
        'success': True,
        'analysis_type': entry.get('analysis_type'),
        'project_name': entry.get('project_name'),
        'original_filename': entry.get('original_filename'),
        'timestamp': entry.get('timestamp'),
        'data': payload,
    })


@router.patch("/api/history/{job_id}/title")
async def update_history_title(job_id: str, request: Request):
    """Update the saved project title for a history entry."""
    payload = await request.json()
    project_name = (payload.get('project_name') or '').strip()

    if not project_name:
        return JSONResponse(content={'success': False, 'error': 'Project name is required'}, status_code=400)

    updated = history_store.update_project_name(job_id, project_name)
    if not updated:
        return JSONResponse(content={'success': False, 'error': 'History entry not found'}, status_code=404)

    return JSONResponse(content={'success': True, 'project_name': project_name})


@router.delete("/api/history/{job_id}")
async def delete_history_entry(job_id: str):
    """Remove a stored history entry and its assets."""
    try:
        removed = history_store.delete_entry(job_id)
    except Exception as exc:
        logger.error("Failed to delete history entry %s: %s", job_id, exc, exc_info=True)
        return JSONResponse(content={'success': False, 'error': 'Failed to delete history entry'}, status_code=500)

    if not removed:
        return JSONResponse(content={'success': False, 'error': 'History entry not found'}, status_code=404)

    with analysis_lock:
        analysis_jobs.pop(job_id, None)

    return JSONResponse(content={'success': True})


@router.get("/api/history/{job_id}/preview")
async def history_preview(job_id: str):
    """Return a PNG preview of the first page for a stored PDF."""
    entry = history_store.load_entry(job_id)
    if not entry or not entry.get('pdf_path'):
        return JSONResponse(content={'success': False, 'error': 'History entry not found'}, status_code=404)

    try:
        with fitz.open(entry['pdf_path']) as doc:
            if doc.page_count == 0:
                raise ValueError('PDF has no pages')

            page = doc[0]
            pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
            image_bytes = pix.tobytes("png")
    except Exception as exc:
        logger.error("Failed to build history preview for %s: %s", job_id, exc, exc_info=True)
        return JSONResponse(content={'success': False, 'error': 'Unable to generate preview'}, status_code=500)

    return Response(content=image_bytes, media_type="image/png")


# =============================================================================
# EXPORT
# =============================================================================
@router.get("/api/export/{job_id}")
async def export_results(job_id: str):
    """Export analysis results as JSON."""
    with analysis_lock:
        if job_id not in analysis_jobs:
            return JSONResponse(content={'success': False, 'error': 'Job not found'}, status_code=404)
        job = analysis_jobs[job_id]

    json_str = json.dumps(job['results'], indent=2)
    return Response(
        content=json_str,
        media_type='application/json',
        headers={'Content-Disposition': f'attachment; filename=fire_alarm_analysis_{job_id}.json'}
    )


@router.get("/api/gemini_report/{job_id}")
async def download_gemini_report(job_id: str):
    """Generate a DOCX report for Gemini analysis output."""
    with analysis_lock:
        job = analysis_jobs.get(job_id)

    if not job:
        return JSONResponse(content={'success': False, 'error': 'Job not found'}, status_code=404)

    if job.get('analysis_type') != 'gemini':
        return JSONResponse(content={'success': False, 'error': 'Gemini report unavailable for this job'}, status_code=400)

    results = job.get('results')
    if not results:
        return JSONResponse(content={'success': False, 'error': 'Analysis results missing'}, status_code=404)

    try:
        report_io = build_gemini_report(results)
    except Exception as exc:
        logger.error("Failed to build Gemini report: %s", exc, exc_info=True)
        return JSONResponse(content={'success': False, 'error': 'Failed to build Gemini report'}, status_code=500)

    filename = f'gemini_fire_alarm_report_{job_id}.docx'
    return StreamingResponse(
        report_io,
        media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================
def _extract_project_name(results: dict, fallback_name: str | None = None) -> str | None:
    """Derive a project name using Gemini output, falling back to filename."""
    if not isinstance(results, dict):
        return fallback_name

    high_level = results.get('high_level_overview') or {}
    project_info = results.get('project_info') or {}

    for candidate in (
        high_level.get('project_name'),
        project_info.get('project_name'),
        project_info.get('name'),
    ):
        if candidate:
            return candidate

    return fallback_name


def _classify_page_type(page_num: int, devices: list) -> str:
    """Classify page type based on detected devices."""
    if not devices:
        return 'other'
    # Simple heuristic - presence of devices suggests fire alarm page
    return 'special_systems'


def _summarize_devices(devices: list) -> dict:
    """Create a summary of detected devices by type."""
    counter = Counter(d.device_type if hasattr(d, 'device_type') else d.get('device_type', 'unknown') for d in devices)
    return dict(counter)
