import json
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

DB_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "leads_db.json")

def load_leads():
    """Load leads from the JSON database."""
    if not os.path.exists(DB_FILE):
        return []
    try:
        with open(DB_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load leads db: {e}")
        return []


def direct_save_leads(leads):
    """
    Directly save leads list to database (overwrites existing).
    Use this for manual add/update/delete operations.

    Args:
        leads: Complete list of leads to save

    Returns:
        bool: True if successful
    """
    try:
        with open(DB_FILE, 'w') as f:
            json.dump(leads, f, indent=2)
        logger.info(f"Saved {len(leads)} leads to {DB_FILE}")
        return True
    except Exception as e:
        logger.error(f"Failed to save leads: {e}")
        return False

def merge_lead_info(existing_lead, new_lead):
    """
    Merge information from two duplicate leads, keeping the most complete data.

    Args:
        existing_lead: The existing lead in database
        new_lead: The new lead being added

    Returns:
        dict: Merged lead with most complete information
    """
    merged = existing_lead.copy()

    # Merge each field, preferring non-empty/non-N/A values
    for key, new_value in new_lead.items():
        existing_value = merged.get(key)

        # Skip if new value is empty or N/A
        if not new_value or new_value == "N/A":
            continue

        # If existing value is empty or N/A, use new value
        if not existing_value or existing_value == "N/A":
            merged[key] = new_value
            continue

        # For specific fields, prefer certain values
        if key == 'local_file_path' and new_value:
            merged[key] = new_value  # Always use newer file path
        elif key == 'contact_email' and new_value and '@' in str(new_value):
            merged[key] = new_value  # Prefer valid email
        elif key == 'files_count' and new_value:
            merged[key] = new_value  # Prefer actual count
        elif key not in merged or not merged[key]:
            merged[key] = new_value

    return merged

def save_leads(new_leads):
    """
    Save new leads to the database, avoiding duplicates and merging information.

    Deduplication strategy:
    1. If lead has 'id' field (e.g., BuildingConnected), use id + site
    2. If lead has 'location' or 'city', use location + site (same address = duplicate)
    3. Otherwise, use name + site composite key (for compatibility)

    When duplicates are found, merge the information to keep the most complete data.

    Args:
        new_leads: List of lead dictionaries to save

    Returns:
        int: Number of new leads added
    """
    if not new_leads:
        return 0

    existing = load_leads()

    # Build lookup dictionaries for existing leads
    existing_by_id = {(l.get('id'), l.get('site')): i for i, l in enumerate(existing) if l.get('id')}
    existing_by_location = {(l.get('location'), l.get('site')): i for i, l in enumerate(existing) if l.get('location') and l.get('location') != 'N/A'}
    existing_by_name = {(l.get('name'), l.get('site')): i for i, l in enumerate(existing)}

    added_count = 0
    merged_count = 0

    for lead in new_leads:
        # Validate required fields
        if not lead.get('name') or not lead.get('site'):
            logger.warning(f"Skipping lead with missing name or site: {lead}")
            continue

        duplicate_index = None

        # Check for duplicate by ID (highest priority)
        if lead.get('id'):
            id_key = (lead.get('id'), lead.get('site'))
            if id_key in existing_by_id:
                duplicate_index = existing_by_id[id_key]
                logger.debug(f"Duplicate lead found (by ID): {lead.get('name')}")

        # Check for duplicate by location (if no ID match)
        if duplicate_index is None and lead.get('location') and lead.get('location') != 'N/A':
            location_key = (lead.get('location'), lead.get('site'))
            if location_key in existing_by_location:
                duplicate_index = existing_by_location[location_key]
                logger.debug(f"Duplicate lead found (by location): {lead.get('name')} at {lead.get('location')}")

        # Check for duplicate by name+site (fallback)
        if duplicate_index is None:
            name_key = (lead.get('name'), lead.get('site'))
            if name_key in existing_by_name:
                duplicate_index = existing_by_name[name_key]
                logger.debug(f"Duplicate lead found (by name): {lead.get('name')}")

        if duplicate_index is not None:
            # Merge information into existing lead
            existing[duplicate_index] = merge_lead_info(existing[duplicate_index], lead)
            merged_count += 1
            logger.info(f"Merged information for duplicate: {lead.get('name')}")
            continue

        # Not a duplicate - add as new lead
        # Add timestamp
        if 'discovered_at' not in lead:
            lead['discovered_at'] = datetime.now().isoformat()

        # Add to tracking dictionaries
        new_index = len(existing)
        if lead.get('id'):
            existing_by_id[(lead.get('id'), lead.get('site'))] = new_index
        if lead.get('location') and lead.get('location') != 'N/A':
            existing_by_location[(lead.get('location'), lead.get('site'))] = new_index
        existing_by_name[(lead.get('name'), lead.get('site'))] = new_index

        existing.append(lead)
        added_count += 1

    try:
        with open(DB_FILE, 'w') as f:
            json.dump(existing, f, indent=2)
        logger.info(f"Saved {added_count} new leads, merged {merged_count} duplicates to {DB_FILE}")
    except Exception as e:
        logger.error(f"Failed to save leads: {e}")

    return added_count

def parse_agent_result(raw_result):
    """
    Parses the agent's result and ensures it's in the correct format.
    Moved from scout_agent.py
    """
    if not raw_result:
        return []

    if isinstance(raw_result, list):
        return validate_leads(raw_result)

    if isinstance(raw_result, dict) and 'leads' in raw_result:
        return validate_leads(raw_result['leads'])

    if isinstance(raw_result, str):
        cleaned = raw_result.strip()
        if cleaned.startswith('```json') and cleaned.endswith('```'):
            cleaned = cleaned[7:-3].strip()
        elif cleaned.startswith('```') and cleaned.endswith('```'):
            cleaned = cleaned[3:-3].strip()

        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, list):
                return validate_leads(parsed)
            elif isinstance(parsed, dict):
                if 'leads' in parsed:
                    return validate_leads(parsed['leads'])
                elif 'projects' in parsed:
                    return validate_leads(parsed['projects'])
        except json.JSONDecodeError:
            pass

    return []

def deduplicate_database():
    """
    Clean up existing duplicates in the database by merging them.

    Returns:
        dict: Statistics about the deduplication process
    """
    existing = load_leads()
    original_count = len(existing)

    if original_count == 0:
        return {"original": 0, "deduplicated": 0, "removed": 0}

    # Track seen leads by different keys
    seen_by_id = {}
    seen_by_location = {}
    seen_by_name = {}
    deduplicated = []

    for lead in existing:
        duplicate_of = None

        # Check by ID first
        if lead.get('id'):
            id_key = (lead.get('id'), lead.get('site'))
            if id_key in seen_by_id:
                duplicate_of = seen_by_id[id_key]

        # Check by location
        if duplicate_of is None and lead.get('location') and lead.get('location') != 'N/A':
            location_key = (lead.get('location'), lead.get('site'))
            if location_key in seen_by_location:
                duplicate_of = seen_by_location[location_key]

        # Check by name
        if duplicate_of is None:
            name_key = (lead.get('name'), lead.get('site'))
            if name_key in seen_by_name:
                duplicate_of = seen_by_name[name_key]

        if duplicate_of is not None:
            # Merge with existing lead
            deduplicated[duplicate_of] = merge_lead_info(deduplicated[duplicate_of], lead)
            logger.info(f"Merged duplicate: {lead.get('name')}")
        else:
            # Add as new unique lead
            new_index = len(deduplicated)
            if lead.get('id'):
                seen_by_id[(lead.get('id'), lead.get('site'))] = new_index
            if lead.get('location') and lead.get('location') != 'N/A':
                seen_by_location[(lead.get('location'), lead.get('site'))] = new_index
            seen_by_name[(lead.get('name'), lead.get('site'))] = new_index
            deduplicated.append(lead)

    # Save deduplicated leads
    try:
        # Backup first
        backup_file = DB_FILE.replace('.json', f'_before_dedup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
        with open(backup_file, 'w') as f:
            json.dump(existing, f, indent=2)
        logger.info(f"Created backup: {backup_file}")

        # Save deduplicated
        with open(DB_FILE, 'w') as f:
            json.dump(deduplicated, f, indent=2)

        removed_count = original_count - len(deduplicated)
        logger.info(f"Deduplication complete: {original_count} -> {len(deduplicated)} leads (removed {removed_count} duplicates)")

        return {
            "original": original_count,
            "deduplicated": len(deduplicated),
            "removed": removed_count
        }
    except Exception as e:
        logger.error(f"Failed to deduplicate database: {e}")
        return {"error": str(e)}

def clear_all_leads():
    """
    Clear all leads from the database.

    Returns:
        int: Number of leads that were deleted
    """
    count = 0
    if os.path.exists(DB_FILE):
        existing = load_leads()
        count = len(existing)
        try:
            # Backup before clearing
            backup_file = DB_FILE.replace('.json', f'_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
            with open(backup_file, 'w') as f:
                json.dump(existing, f, indent=2)
            logger.info(f"Created backup: {backup_file}")

            # Clear the database
            with open(DB_FILE, 'w') as f:
                json.dump([], f, indent=2)
            logger.info(f"Cleared {count} leads from database")
        except Exception as e:
            logger.error(f"Failed to clear leads: {e}")
            return 0
    return count

def validate_leads(leads):
    """Validates and normalizes lead data structure."""
    if not isinstance(leads, list):
        return []

    validated = []
    for lead in leads:
        if not isinstance(lead, dict):
            continue

        validated_lead = {
            'name': lead.get('name') or lead.get('Project Name') or 'Unnamed Project',
            'gc': lead.get('gc') or lead.get('GC') or 'Not specified',
            'bid_date': lead.get('bid_date') or lead.get('Bid Date') or 'TBD',
            'site': lead.get('site') or lead.get('Source') or 'Unknown',
            'files_link': lead.get('files_link') or lead.get('Files Link') or '',
            'sprinklered': bool(lead.get('sprinklered') or lead.get('Sprinkler Keywords', False))
        }
        validated.append(validated_lead)

    return validated
