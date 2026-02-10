"""
Triage Agent - Scores and prioritizes leads for deep analysis.
"""
import logging
import json
import sys
import os
from datetime import datetime

# Add parent directory to path to allow imports from backend
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.storage import load_leads, direct_save_leads

logger = logging.getLogger(__name__)

# Keywords that indicate high priority (Trade specific)
HIGH_PRIORITY_KEYWORDS = [
    'fire alarm', 'fire detection', 'fire suppression', 'sprinkler', 
    'mass notification', 'area of refuge', 'nurse call', 'security',
    'access control', 'cctv', 'low voltage'
]

# Keywords that indicate low priority (Avoid)
LOW_PRIORITY_KEYWORDS = [
    'paving', 'roofing', 'landscaping', 'painting', 'flooring', 
    'demolition', 'hvac replacement', 'glass', 'glazing', 'concrete'
]

def triage_projects():
    """
    Score projects and assign priority.
    
    Returns:
        int: Number of projects triaged
    """
    leads = load_leads()
    if not leads:
        return 0
        
    updated_count = 0
    
    for lead in leads:
        # Skip if already triaged (unless we want to re-triage force?)
        if lead.get('priority'):
            continue
            
        name = (lead.get('name') or '').lower()
        desc = (lead.get('description') or '').lower()
        full_text = f"{name} {desc}"
        
        # Default
        priority = "Medium"
        reason = "General construction project"
        
        # Check High Priority
        matched_high = [kw for kw in HIGH_PRIORITY_KEYWORDS if kw in full_text]
        if matched_high:
            priority = "High"
            reason = f"Matched keywords: {', '.join(matched_high[:3])}"
            
        # Check Low Priority
        # Only downgrade to Low if it doesn't match High
        if priority != "High":
            matched_low = [kw for kw in LOW_PRIORITY_KEYWORDS if kw in full_text]
            if matched_low:
                priority = "Low"
                reason = f"Likely irrelevant: {', '.join(matched_low[:3])}"
                
        # Scraper-specific logic
        # If scraped by a specific scraper that already filters (like PlanHub), 
        # trust it more (at least Medium)
        if lead.get('site') in ['PlanHub', 'BuildingConnected'] and priority == "Low":
            # If our scrapers picked it up, it probably matched a trade filter.
            # Don't easily discard it unless we are sure.
            # But for now, let's trust the keyword match.
            pass

        # Update Lead
        lead['priority'] = priority
        lead['triage_reason'] = reason
        lead['triaged_at'] = datetime.now().isoformat()
        
        updated_count += 1
        
    if updated_count > 0:
        if direct_save_leads(leads):
            logger.info(f"Triaged {updated_count} new projects.")
            return updated_count
            
    return 0

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    triage_projects()
