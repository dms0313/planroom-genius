"""
Cleanup Service - Manages expiration and deletion of old project data.
"""
import os
import shutil
import logging
import json
import sys
from datetime import datetime, date

# Add parent directory to path to allow imports from backend
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.storage import load_leads, save_leads, DB_FILE, direct_save_leads
from config import ScraperConfig, DATE_FORMATS

logger = logging.getLogger(__name__)

def parse_date(date_str):
    """
    Parse date string into date object.
    
    Args:
        date_str: Date string to parse
        
    Returns:
        date: Parsed date object or None if parsing failed
    """
    if not date_str or date_str == "N/A" or date_str == "TBD":
        return None
        
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(date_str.strip(), fmt).date()
        except ValueError:
            continue
            
    return None

def cleanup_expired_projects(dry_run=False):
    """
    Remove projects where the bid date has passed.
    
    Args:
        dry_run: If True, only log what would be deleted without taking action.
        
    Returns:
        dict: Stats on deleted items
    """
    logger.info(f"Starting cleanup scan (Dry Run: {dry_run})...")
    
    leads = load_leads()
    if not leads:
        logger.info("No leads to check.")
        return {"deleted": 0, "space_freed_mb": 0}
        
    today = date.today()
    active_leads = []
    expired_leads = []
    
    # 1. Identify expired projects
    for lead in leads:
        bid_date_str = lead.get('bid_date')
        if not bid_date_str:
            active_leads.append(lead)
            continue
            
        bid_date = parse_date(bid_date_str)
        
        if bid_date and bid_date < today:
            expired_leads.append(lead)
            logger.info(f"Found expired project: {lead.get('name')} (Bid Date: {bid_date_str})")
        else:
            active_leads.append(lead)
            
    if not expired_leads:
        logger.info("No expired projects found.")
        return {"deleted": 0, "space_freed_mb": 0}
        
    logger.info(f"Found {len(expired_leads)} expired projects. Cleaning up...")
    
    space_freed_bytes = 0
    deleted_count = 0
    
    # 2. Delete local files
    download_dir = ScraperConfig.DOWNLOAD_DIR
    
    if not dry_run:
        for lead in expired_leads:
            # Delete project specific folder if it exists
            # Convention: downloads/Project_Name_Cleaned
            name = lead.get('name', '')
            if not name:
                continue
                
            # Try to find matching implementation of folder naming
            # Usually: "".join(c for c in name[:50] if c.isalnum() or c in ' -_').strip()
            # But sometimes files are loose in download_dir or in subfolders
            
            # Simple approach: Check if 'local_file_path' points to a specific folder
            local_path = lead.get('local_file_path')
            if local_path:
                # local_path usually relative like "/downloads/file.pdf"
                full_path = ""
                if local_path.startswith("/downloads/"):
                    full_path = os.path.join(os.path.dirname(download_dir), local_path.lstrip('/'))
                elif local_path.startswith("downloads/"):
                    full_path = os.path.join(os.path.dirname(download_dir), local_path)
                else:
                    full_path = local_path
                    
                if os.path.exists(full_path):
                    try:
                        if os.path.isfile(full_path):
                            size = os.path.getsize(full_path)
                            os.remove(full_path)
                            space_freed_bytes += size
                            logger.info(f"Deleted file: {full_path}")
                        elif os.path.isdir(full_path):
                            size = sum(os.path.getsize(os.path.join(dirpath, filename)) for dirpath, _, filenames in os.walk(full_path) for filename in filenames)
                            shutil.rmtree(full_path)
                            space_freed_bytes += size
                            logger.info(f"Deleted directory: {full_path}")
                    except Exception as e:
                        logger.error(f"Failed to delete {full_path}: {e}")
            
            # Also check for unzipped folders in download_dir matching the name
            # This is a bit heuristic, but 'knowledge.py' unzips into folders named after the zip
            # We might want to be careful here. 
            # For now, relying on 'local_file_path' is safer.
            
        # 3. Update Database
        try:
            # We use direct socket to avoid deduplication logic which might re-merge?
            # Actually save_leads is fine, but we want to REPLACE the list
            if direct_save_leads(active_leads):
                deleted_count = len(expired_leads)
                logger.info(f"Database updated. Removed {deleted_count} expired projects.")
        except Exception as e:
            logger.error(f"Failed to update database: {e}")
            
    return {
        "deleted": len(expired_leads),
        "space_freed_mb": round(space_freed_bytes / (1024 * 1024), 2)
    }

if __name__ == "__main__":
    # Test run
    logging.basicConfig(level=logging.INFO)
    cleanup_expired_projects(dry_run=True)
