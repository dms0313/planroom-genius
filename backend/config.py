"""
Centralized configuration for Puppeteer scrapers.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
env_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(env_path)
parent_env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
load_dotenv(parent_env_path)


class ScraperConfig:
    """Base configuration for all scrapers"""

    # Chrome Profile Settings
    import platform
    if platform.system() == 'Linux':
        # Raspberry Pi specific path
        CHROME_USER_DATA_DIR = "/home/pi/.config/chromium"
        CHROME_PROFILE_NAME = "Profile 1"
    else:
        # Development/Local default
        CHROME_USER_DATA_DIR = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "planroom_agent_storage_browser-use-user-data-dir-persistent"
        )
        CHROME_PROFILE_NAME = os.getenv("CHROME_PROFILE_NAME", "Profile 2")

    # Browser Settings
    # Default to HEADLESS=True on Linux (Pi), False on Windows unless override
    import platform
    _is_linux = platform.system() == 'Linux'
    HEADLESS = os.getenv("HEADLESS", str(_is_linux)).lower() == "true"
    VIEWPORT_WIDTH = 1280
    VIEWPORT_HEIGHT = 720

    # Timeouts (in milliseconds)
    NAVIGATION_TIMEOUT = 60000
    SELECTOR_TIMEOUT = 10000
    DOWNLOAD_WAIT = 3000

    # Download Settings
    DOWNLOAD_DIR = os.path.join(os.path.dirname(__file__), 'downloads')

    # Scraping Limits
    MAX_PROJECTS_DEFAULT = None  # None = all projects
    MAX_CONSECUTIVE_ERRORS = 3

    # Delays (in seconds)
    DELAY_AFTER_CLICK = 1
    DELAY_BETWEEN_PROJECTS = 1
    DELAY_AFTER_NAVIGATION = 2

    # Database
    DB_FILE = os.path.join(os.path.dirname(__file__), 'leads_db.json')


class BuildingConnectedConfig(ScraperConfig):
    """BuildingConnected-specific configuration"""

    # URLs
    PIPELINE_URL = "https://app.buildingconnected.com/opportunities/pipeline"

    # Selectors - Due Date Sort
    DUE_DATE_SORT_SELECTORS = [
        'div.ReactVirtualized__Table__headerRow > div:nth-of-type(3) span',
        'text/Due Date'
    ]

    # Selectors - Project Grid
    PROJECT_GRID_SELECTOR = '.ReactVirtualized__Grid'
    # List View Column Selectors
    LIST_NAME_SELECTOR = 'div[class*="nameCellColumn"]'
    LIST_DATE_SELECTOR = 'div[class*="dateWrapper"], div[class*="bidDate"], div[class*="dateCellColumn"]'
    LIST_LOCATION_SELECTOR = 'div[class*="locationCellColumn"]'
    LIST_COMPANY_SELECTOR = 'div[class*="companyCellColumn"]'
    
    PROJECT_ROW_SELECTOR = 'div.ReactVirtualized__Grid > div > div[class*="nameCellColumn"]' # For counting
    PROJECT_DETAIL_SELECTOR = '[data-testid="new-badge"]'

    # Selectors - Project Details
    NAME_SELECTORS = [
        'span[class*="projectName"]',
        'h1[class*="title"]',
        '[data-testid="project-name"]',
        'div[class*="header"] span',
    ]

    DUE_DATE_SELECTORS = [
        'div[class*="dueDate"] span',
        'span[class*="date"]',
        '[data-testid="due-date"]',
    ]

    LOCATION_SELECTORS = [
        'div[class*="location"] span',
        '[data-testid="location"]',
        'span[class*="address"]',
    ]

    COMPANY_SELECTORS = [
        'h1[class*="company"]',
        'div[class*="company"] h1',
        '[data-testid="company-name"]',
    ]

    CONTACT_NAME_SELECTORS = [
        'div[class*="contact"] h1',
        'h1[class*="contactName"]',
        '[data-testid="contact-name"]',
    ]

    CONTACT_INFO_SELECTORS = [
        'div[class*="contact"] p',
        'p[class*="contactInfo"]',
        '[data-testid="contact-info"]',
    ]

    PROJECT_INFO_SELECTORS = [
        'div[class*="description"] div span',
        'div[class*="projectInfo"]',
        '[data-testid="project-info"]',
    ]

    # Selectors - Files Tab
    FILES_TAB_SELECTORS = [
        'a[href*="/files"]',
        '[data-testid="files-tab"]',
        'a:has-text("Files")',
        'div.Tabs___StyledDiv3-sc-v38ayv-2 a:nth-child(2)',
    ]

    DOWNLOAD_BTN_SELECTORS = [
        '[data-testid="download-all-bttn"]',
        'button:has-text("Download All")',
        'button[class*="download"]',
    ]


class PlanHubConfig(ScraperConfig):
    """PlanHub-specific configuration"""

    # URLs
    LOGIN_URL = "https://access.planhub.com/signin"
    PROJECT_LIST_URL = "https://supplier.planhub.com/project/list"

    # Credentials
    LOGIN_EMAIL = os.getenv("PLANHUB_LOGIN") or os.getenv("SITE_LOGIN", "")
    LOGIN_PASSWORD = os.getenv("PLANHUB_PW") or os.getenv("SITE_PW", "")

    # Filter Settings
    LOCATION_ZIP = "64030"
    LOCATION_RADIUS = 125  # miles (updated from 100)
    TRADE_FILTER = "Fire Alarm"
    REGIONS = ["Missouri", "Kansas"]  # MO and KS only

    # Scraping Limits
    MAX_PROJECTS_DEFAULT = 5  # PlanHub max 5 per run

    # Sprinkler Keywords
    SPRINKLER_KEYWORDS = [
        'sprinkler',
        'fire suppression',
        'fire protection',
        'wet pipe',
        'dry pipe',
        'pre-action',
        'deluge',
    ]

    # Selectors (to be discovered via DevTools)
    LOGIN_EMAIL_SELECTOR = 'input[type="email"], input[name="email"], input[id="email"]'
    LOGIN_PASSWORD_SELECTOR = 'input[type="password"], input[name="password"], input[id="password"]'
    LOGIN_SUBMIT_SELECTOR = 'button[type="submit"], button:has-text("Sign In"), button:has-text("Login")'

    # Filter Selectors (updated with actual PlanHub selectors)
    FIRE_ALARM_CHECKBOX_SELECTOR = '#mat-checkbox-980 > label > span.mat-checkbox-inner-container.mat-checkbox-inner-container-no-side-margin'

    # Region Filter Selectors (new)
    REGION_FILTER_DROPDOWN = '#mat-input-9'
    MISSOURI_CHECKBOX = '#mat-checkbox-51 > label > span.mat-checkbox-inner-container.mat-checkbox-inner-container-no-side-margin'
    IOWA_KANSAS_NEBRASKA_CHECKBOX = '#mat-checkbox-153 > label > span.mat-checkbox-inner-container.mat-checkbox-inner-container-no-side-margin'

    # Distance Filter Selectors (updated for 125 miles)
    DISTANCE_FILTER_DROPDOWN = '#mat-select-4 > div > div.mat-select-arrow-wrapper.ng-tns-c647416370-18 > div'
    DISTANCE_125MI_SELECTOR = '#mat-option-21 > span > div'

    # Legacy selectors (keeping for fallback)
    LOCATION_INPUT_SELECTOR = 'input[placeholder*="location"], input[name*="location"], input[id*="location"]'
    RADIUS_INPUT_SELECTOR = 'input[placeholder*="radius"], input[name*="radius"], select[name*="distance"]'
    TRADE_INPUT_SELECTOR = 'input[placeholder*="trade"], input[name*="trade"], select[name*="trade"]'

    # Project List Selectors
    # Project List Selectors
    PROJECT_TABLE_SELECTOR = 'table, [role="table"], planhub-project-table, mat-table'
    PROJECT_ROW_SELECTOR = 'tr, [role="row"], mat-row, .project-row'

    # Pagination and Sorting Selectors
    NEXT_PAGE_SELECTOR = 'body > planhub-main > div > mat-sidenav-container > mat-sidenav-content > app-root > div > app-projects > div > mat-card:nth-child(2) > planhub-project-list > div > planhub-project-table > div.table-pagination.table-pagination-bottom.flex-row.align-end-center > div > planhub-button:nth-child(4) > button'
    SORT_BY_DUE_DATE_SELECTOR = 'body > planhub-main > div > mat-sidenav-container > mat-sidenav-content > app-root > div > app-projects > div > mat-card:nth-child(2) > planhub-project-list > div > planhub-project-table > div.planhub-loading-container > table > thead > tr > th.mat-sort-header.mat-header-cell.cdk-header-cell.table-column.header.ng-tns-c1267148319-34.cdk-column-bid_due_date.mat-column-bid_due_date.ng-star-inserted > div > div.mat-sort-header-arrow.ng-trigger.ng-trigger-arrowPosition.ng-tns-c1267148319-34.ng-star-inserted > div.mat-sort-header-stem.ng-tns-c1267148319-34'

    # Project Cell Selectors
    BID_DATE_CELL_SELECTOR = 'body > planhub-main > div > mat-sidenav-container > mat-sidenav-content > app-root > div > app-projects > div > mat-card:nth-child(2) > planhub-project-list > div > planhub-project-table > div.planhub-loading-container > table > tbody > tr.mat-row.cdk-row.selected-row.viewed-row.ng-star-inserted > td.mat-cell.cdk-cell.table-column.cdk-column-bid_due_date.mat-column-bid_due_date.ng-star-inserted'
    LOCATION_CELL_SELECTOR = 'body > planhub-main > div > mat-sidenav-container > mat-sidenav-content > app-root > div > app-projects > div > mat-card:nth-child(2) > planhub-project-list > div > planhub-project-table > div.planhub-loading-container > table > tbody > tr.mat-row.cdk-row.selected-row.viewed-row.ng-star-inserted > td.mat-cell.cdk-cell.table-column.cdk-column-location.mat-column-location.ng-star-inserted > span'

    # Auto-update behavior note:
    # After updating filters, the page automatically updates after a few seconds
    # No need to search for specific text or trigger a search button
    FILTER_AUTO_UPDATE_DELAY = 3  # seconds to wait after filter changes

    # Detail & Download Selectors (from User Request - exact CSS selectors)
    # More Project Details button (in quick view)
    MORE_DETAILS_BTN_FULL = 'body > planhub-main > div > mat-sidenav-container > mat-sidenav-content > app-root > div > app-projects > div > mat-card:nth-child(2) > planhub-project-list > div > div > planhub-project-quick-view > div.section.align-center > div:nth-child(3) > planhub-button > button'

    # Project Files tab
    PROJECT_FILES_TAB = '#mat-button-toggle-2-button > span > div > span'

    # Select All Files checkbox
    SELECT_ALL_FILES_CHECKBOX = '#mat-checkbox-1 > label > span.mat-checkbox-inner-container.mat-checkbox-inner-container-no-side-margin'

    # Download Files button (full path)
    DOWNLOAD_FILES_BTN = 'body > planhub-main > div > mat-sidenav-container > mat-sidenav-content > app-root > div > app-project-details > div > app-project-details-v2 > div > div > div.tabs-container > div.project-files.ng-star-inserted > mat-card > planhub-project-file-table > div > div.table-pagination.flex-row.align-space-between.pd-0 > planhub-button > button'


# Date parsing formats
DATE_FORMATS = [
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%m/%d/%y",
    "%B %d, %Y",
    "%b %d, %Y",
    "%d %B %Y",
    "%d %b %Y",
]
