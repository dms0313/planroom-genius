# Knowledge Scanner - Implementation Plan

## Root Cause: Why the Scanner Isn't Working

1. **Missing Python dependencies**: `PyMuPDF` (fitz) and `requests` are NOT in `requirements.txt` -- the scanner silently catches ImportError and returns empty results
2. **ZIP files are not extracted**: Downloads dir has raw `.zip` files. The `_unzip_downloads()` in the BC scraper only runs once at the very end of a scrape; PlanHub never unzips at all. Knowledge scanner looks for PDFs but finds none in un-extracted zips
3. **No `schedule` package in requirements.txt** (used by scheduler.py)

---

## Phase 1: Fix Dependencies & ZIP Extraction (Backend Foundation)

### 1a. Update `requirements.txt`
Add:
- `PyMuPDF>=1.25.0` (the `fitz` library for PDF rendering)
- `requests>=2.31.0` (for Gemini API calls)
- `schedule>=1.2.0` (already used but missing from reqs)
- `google-generativeai>=0.8.0` (optional, cleaner Gemini SDK)

### 1b. Add standalone ZIP extraction to Knowledge scanner
- Add `unzip_all_downloads()` function in `knowledge.py` that runs BEFORE scanning
- Extracts all `.zip` files in `backend/downloads/` to subdirectories
- Moves original `.zip` into the extracted folder (prevents re-extraction)
- Handles nested zips
- Also call `_unzip_downloads()` at end of PlanHub scraper's `run()` (currently only BC does this)

### 1c. Fix the PlanHub scraper to also unzip
- The PlanHub scraper downloads files too but never unzips them. Add the same `_unzip_downloads()` call.

---

## Phase 2: Robust Document Identification System

### 2a. Enhance `_classify_pdfs()` in `knowledge.py`
Current logic is too simple (just checks filename for "plan"/"spec"). Improve to:

- **Directory-based detection**: Check for subdirectories named `Plans`, `Drawings`, `Specs`, `Specifications`, `Project Manual`, etc.
- **Filename patterns**: Match common construction doc naming:
  - Plans: `*-E*.pdf`, `*electrical*.pdf`, `*drawing*.pdf`, `*plan*.pdf`, `*sheet*.pdf`
  - Specs: `*spec*.pdf`, `*manual*.pdf`, `*division*.pdf`, `*section*.pdf`
- **Multi-file support**: Return lists (plans can be split into multiple PDFs, specs too)
- **First-page text analysis**: If filename is ambiguous, read first page text for keywords like "SPECIFICATIONS", "TABLE OF CONTENTS", "DRAWING INDEX", etc.

### 2b. Enhanced Page Selection (`_select_pages_from_text`)
Refine to match user's exact requirements:

**INCLUDE**:
- Cover pages (first 2-3 pages of each document)
- Code pages (IBC, NFPA references)
- Power plans (pages with "power plan", "E-xxx" sheet numbers)
- Special systems plans (pages with "special systems", "FA-xxx")
- Fire alarm plans (pages with "fire alarm", "FA")
- General electrical notes (pages with "general electrical notes", "electrical notes")
- HVAC pages ONLY if they contain: "duct detector", "fire smoke damper", "smoke damper"

**EXCLUDE**:
- Lighting pages ("lighting", "light fixture", "luminaire")
- Electrical schedules ("panel schedule", "electrical schedule")
- Graphical schematics ("schematic", "one-line", "riser diagram")
- Any other unrelated pages

### 2c. Image-first approach with OCR fallback
- Primary: Render selected pages to images via PyMuPDF at 150 DPI -> send to Gemini as images
- Fallback: If Gemini unavailable or image rendering fails, use OCR text extraction
- Additional confirmation: Extract OCR text alongside images to provide context

---

## Phase 3: Enhanced AI Analysis (Gemini Integration)

### 3a. Improve Gemini prompt
Update `_call_gemini()` prompt to be more specific:
- Cross-reference NFPA 72 / IBC codes to confirm fire alarm requirements
- Identify system type: new, existing to remain, modification
- Extract required vendors (exact names from specs)
- Extract required manufacturers (exact names)
- Identify deal-breakers (prevailing wage, bonding, specific certifications)
- Rate scope of work (0-100 scale)
- Provide detailed notes

### 3b. Add high-level ranking pass
After all individual project scans complete:
- Call Gemini with a summary of ALL projects
- Ask it to rank projects by: scope size, bid likelihood (high/medium/low)
- Factor in: deal-breakers lower bid chance, required vendors/mfrs lower chance, no FA = skip, existing systems = lower scope

### 3c. Badge computation
Compute badges from analysis results:
- `NO FA` - Project does not require fire alarm
- `EXISTING` - System is existing to remain
- `NEW SYSTEM` - New fire alarm system
- `REQ VENDOR` - Required/approved vendor list
- `REQ MFR` - Required/approved manufacturer
- `DEAL BREAKER` - Has deal-breaking requirements
- Score badge: visual indicator of scope (0-100)
- Bid chance badge: `HIGH` / `MEDIUM` / `LOW`

---

## Phase 4: New API Endpoints

### 4a. PDF preview endpoint
`GET /knowledge/preview/{lead_id}` - Returns first page of identified plan/spec as PNG image (base64) for the "point to file" feature

### 4b. File listing endpoint
`GET /knowledge/files/{lead_id}` - Lists all PDFs found in a project's download directory with:
- Filename, path, size
- Classification (plan/spec/other)
- First page preview thumbnail (base64)

### 4c. Manual file override endpoint
`POST /knowledge/files/{lead_id}/override` - Allows user to manually select which file is the "plans" and which is the "specs" for a project. Stores override in knowledge cache so scanner uses those files.

### 4d. Knowledge scan status with per-project progress
`GET /knowledge/status` - Enhanced to return:
- Overall progress (scanned/total/skipped)
- Current project being scanned
- Per-project results summary

### 4e. Rescan single project
`POST /knowledge/scan/{lead_id}` - Rescan a specific project (bypasses cache)

---

## Phase 5: Frontend - Tabbed Navigation & Knowledge Tab

### 5a. Tabbed navigation (already exists - refine)
- Bid Board tab (Building2 icon) - default, current page
- Knowledge tab (Brain icon) - new analysis page
- Both tabs stay mounted (use `hidden` class, already implemented)

### 5b. Knowledge Tab - Full Redesign
Replace the basic table with a rich analysis dashboard:

**Header section:**
- "Run Knowledge Scan" button with progress indicator
- Status: running/idle, scanned count, skipped count
- Sort controls: by score, by bid chance, by name

**Project cards/rows:**
- Project name + bid date
- Score gauge/bar (0-100, color-coded: red < 30, yellow 30-69, green >= 70)
- Badges row (colored pills for each designation)
- Bid chance indicator (HIGH=green, MEDIUM=yellow, LOW=red)
- System type indicator (NEW/EXISTING/UNKNOWN)
- Required vendors/manufacturers list (if any)
- Deal-breakers list (if any)
- Notes preview (expandable)
- "Identified Files" section showing plan/spec with first-page thumbnails
- "Point to File" button to manually override document selection
- Last scanned timestamp

**Sorting/filtering:**
- Sort by: Score (high to low), Bid Chance, Name, Date
- Filter by: Has fire alarm / No fire alarm / All
- Filter by: Bid chance (high/medium/low)

### 5c. "Point to File" Modal
When user clicks "Point to File":
- Show all PDFs in the project directory as a grid
- Each PDF shows: filename + first-page preview image
- User clicks on the correct plan/spec file
- Selection is saved via the manual override API
- Triggers re-scan of that project with the correct files

---

## Phase 6: Directory Change Detection & Caching

Already implemented via SHA256 hash in `knowledge.py`:
- `_hash_dir()` creates signature from file names, sizes, and modification times
- Cache stored in `knowledge_cache.json`
- Projects with unchanged signature are skipped

**Enhancements:**
- Add manual override storage to cache (so overrides persist)
- Add per-file classification cache (plan/spec/other)
- Clear cache entry when user requests re-scan

---

## Phase 7: Fix "Download All" Large File Popup

The BC scraper's `handle_large_file_prompt()` already tries to click "OK, go for it!" but may need refinement:
- The popup uses obfuscated CSS classes (e.g. `fVcsQUfFFU2Ptl2BgGD1SQ==`)
- Add `aria-label="OK, go for it!"` selector (most reliable, already partially there)
- After clicking "OK, go for it!", sometimes a **Close** button appears that also needs clicking
- Add a secondary check after the confirmation click to dismiss any remaining close button

---

## File Changes Summary

| File | Changes |
|------|---------|
| `backend/requirements.txt` | Add PyMuPDF, requests, schedule |
| `backend/services/knowledge.py` | Major rewrite: unzip, classify, page selection, Gemini prompt, ranking, previews |
| `backend/api.py` | Add 4 new endpoints: preview, files, override, single-scan |
| `frontend/src/Dashboard.jsx` | Major rewrite of Knowledge tab: cards, badges, scores, sorting, point-to-file modal |
| `backend/scrapers/planhub.py` | Add `_unzip_downloads()` call at end of `run()` |
| `backend/config.py` | Add `GEMINI_API_KEY` reference in config comments |

---

## Implementation Order

1. **Phase 1** - Fix deps + unzip (gets scanner actually working)
2. **Phase 2** - Document identification (accuracy)
3. **Phase 3** - AI analysis improvements (quality)
4. **Phase 4** - New API endpoints (backend ready for frontend)
5. **Phase 5** - Frontend Knowledge tab (user-facing)
6. **Phase 6** - Caching enhancements (polish)
