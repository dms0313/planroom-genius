"""
Google Drive integration service for Planroom Genius.
Handles OAuth 2.0 authentication, file uploads, and shareable link creation.
"""
import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
load_dotenv(env_path)
parent_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env')
load_dotenv(parent_env_path)

logger = logging.getLogger(__name__)

# Google API imports - wrapped in try/except for graceful degradation
try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from googleapiclient.errors import HttpError
    GOOGLE_DRIVE_AVAILABLE = True
except ImportError:
    GOOGLE_DRIVE_AVAILABLE = False
    logger.warning("Google Drive API libraries not installed. Run: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib")


# Configuration
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CREDENTIALS_FILE = os.path.join(BACKEND_DIR, 'credentials.json')
TOKEN_FILE = os.path.join(BACKEND_DIR, 'token.json')

# Scope for Google Drive - only access files created by this app
SCOPES = ['https://www.googleapis.com/auth/drive.file']

# Folder names for organization
ROOT_FOLDER_NAME = "Planroom Genius Files"
BC_FOLDER_NAME = "BuildingConnected"
PH_FOLDER_NAME = "PlanHub"

# Cache for folder IDs to avoid repeated lookups
_folder_cache = {}


def is_available():
    """Check if Google Drive integration is available."""
    return GOOGLE_DRIVE_AVAILABLE


def is_configured():
    """Check if Google Drive credentials are configured."""
    return os.path.exists(CREDENTIALS_FILE)


def is_authenticated():
    """Check if we have valid authentication tokens."""
    if not GOOGLE_DRIVE_AVAILABLE or not is_configured():
        return False

    if not os.path.exists(TOKEN_FILE):
        return False

    try:
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        return creds and creds.valid
    except Exception:
        return False


def get_status():
    """Get detailed Google Drive connection status."""
    status = {
        "available": GOOGLE_DRIVE_AVAILABLE,
        "configured": is_configured(),
        "authenticated": False,
        "needs_reauth": False,
        "error": None
    }

    if not GOOGLE_DRIVE_AVAILABLE:
        status["error"] = "Google Drive API libraries not installed"
        return status

    if not is_configured():
        status["error"] = "credentials.json not found in backend directory"
        return status

    if not os.path.exists(TOKEN_FILE):
        status["error"] = "Not authenticated - OAuth flow required"
        return status

    try:
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        if creds and creds.valid:
            status["authenticated"] = True
        elif creds and creds.expired and creds.refresh_token:
            status["needs_reauth"] = True
            status["error"] = "Token expired - will attempt refresh on next use"
        else:
            status["error"] = "Invalid or expired credentials"
    except Exception as e:
        status["error"] = f"Error checking credentials: {str(e)}"

    return status


def authenticate(force_new=False):
    """
    Authenticate with Google Drive using OAuth 2.0.

    Args:
        force_new: If True, force a new authentication flow even if valid tokens exist

    Returns:
        Credentials object if successful, None otherwise
    """
    if not GOOGLE_DRIVE_AVAILABLE:
        logger.error("Google Drive API not available")
        return None

    if not is_configured():
        logger.error(f"Credentials file not found: {CREDENTIALS_FILE}")
        return None

    creds = None

    # Load existing token if available
    if os.path.exists(TOKEN_FILE) and not force_new:
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        except Exception as e:
            logger.warning(f"Could not load existing token: {e}")

    # Refresh or get new credentials
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                logger.info("Refreshing expired token...")
                creds.refresh(Request())
            except Exception as e:
                logger.warning(f"Token refresh failed: {e}")
                creds = None

        if not creds:
            try:
                logger.info("Starting OAuth flow - browser will open for authorization...")
                flow = InstalledAppFlow.from_client_secrets_file(
                    CREDENTIALS_FILE, SCOPES
                )
                # Use a fixed port for OAuth. Allow override via env if needed.
                port_env = os.getenv("GOOGLE_OAUTH_PORT", "").strip()
                port = int(port_env) if port_env.isdigit() else 8089
                creds = flow.run_local_server(
                    port=port,
                    prompt='consent',
                    success_message='Authorization successful! You can close this window.',
                    open_browser=True
                )
            except Exception as e:
                logger.error(f"OAuth flow failed: {e}")
                return None

        # Save the credentials for future use
        if creds:
            try:
                with open(TOKEN_FILE, 'w') as token:
                    token.write(creds.to_json())
                logger.info(f"Credentials saved to {TOKEN_FILE}")
            except Exception as e:
                logger.warning(f"Could not save token: {e}")

    return creds


def get_service():
    """
    Get an authenticated Google Drive service object.

    Returns:
        Google Drive service object or None if authentication fails
    """
    creds = authenticate()
    if not creds:
        return None

    try:
        service = build('drive', 'v3', credentials=creds)
        return service
    except Exception as e:
        logger.error(f"Failed to build Drive service: {e}")
        return None


def get_or_create_folder(folder_name, parent_id=None):
    """
    Get existing folder or create new one.

    Args:
        folder_name: Name of the folder
        parent_id: Optional parent folder ID

    Returns:
        Folder ID or None if failed
    """
    # Check cache first
    cache_key = f"{parent_id or 'root'}:{folder_name}"
    if cache_key in _folder_cache:
        return _folder_cache[cache_key]

    service = get_service()
    if not service:
        return None

    try:
        # Search for existing folder
        query = f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        if parent_id:
            query += f" and '{parent_id}' in parents"

        results = service.files().list(
            q=query,
            spaces='drive',
            fields='files(id, name)'
        ).execute()

        files = results.get('files', [])

        if files:
            folder_id = files[0]['id']
            _folder_cache[cache_key] = folder_id
            logger.info(f"Found existing folder: {folder_name} ({folder_id})")
            return folder_id

        # Create new folder
        file_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        if parent_id:
            file_metadata['parents'] = [parent_id]

        folder = service.files().create(
            body=file_metadata,
            fields='id'
        ).execute()

        folder_id = folder.get('id')
        _folder_cache[cache_key] = folder_id
        logger.info(f"Created folder: {folder_name} ({folder_id})")
        return folder_id

    except HttpError as e:
        logger.error(f"Error with folder {folder_name}: {e}")
        return None


def get_root_folder():
    """Get or create the root 'Planroom Genius Files' folder."""
    return get_or_create_folder(ROOT_FOLDER_NAME)


def get_source_folder(source):
    """
    Get or create folder for a specific source (BC or PlanHub).

    Args:
        source: 'BuildingConnected' or 'PlanHub'

    Returns:
        Folder ID or None
    """
    root_id = get_root_folder()
    if not root_id:
        return None

    if 'building' in source.lower():
        folder_name = BC_FOLDER_NAME
    elif 'planhub' in source.lower():
        folder_name = PH_FOLDER_NAME
    else:
        folder_name = source

    return get_or_create_folder(folder_name, parent_id=root_id)


def check_file_exists(filename, source='BuildingConnected'):
    """
    Check if a file with the given name already exists in the source folder.

    Args:
        filename: Name of the file to check
        source: 'BuildingConnected' or 'PlanHub'

    Returns:
        dict with 'file_id', 'web_link', 'download_link' if found, else None
    """
    if not GOOGLE_DRIVE_AVAILABLE:
        return None

    service = get_service()
    if not service:
        return None

    # Get folder for this source
    folder_id = get_source_folder(source)
    if not folder_id:
        # If we can't find the source folder, we can't be sure it exists there
        return None

    try:
        # Escape single quotes in filename
        safe_filename = filename.replace("'", "\\'")
        query = f"name = '{safe_filename}' and trashed = false and '{folder_id}' in parents"
        
        results = service.files().list(
            q=query, 
            fields='files(id, name, webViewLink, webContentLink)',
            pageSize=1
        ).execute()
        
        files = results.get('files', [])
        if files:
            file = files[0]
            file_id = file.get('id')
            return {
                'file_id': file_id,
                'web_link': file.get('webViewLink') or f"https://drive.google.com/file/d/{file_id}/view",
                'download_link': file.get('webContentLink') or f"https://drive.google.com/uc?id={file_id}&export=download",
                'filename': filename
            }
        return None

    except Exception as e:
        logger.error(f"Error checking for file existence: {e}")
        return None


def upload_file(local_path, filename=None, source='BuildingConnected'):
    """
    Upload a file to Google Drive and return shareable link.

    Args:
        local_path: Path to local file
        filename: Optional custom filename (defaults to original)
        source: Source for folder organization ('BuildingConnected' or 'PlanHub')

    Returns:
        dict with 'file_id', 'web_link', 'download_link' or None if failed
    """
    if not os.path.exists(local_path):
        logger.error(f"File not found: {local_path}")
        return None

    service = get_service()
    if not service:
        logger.error("Could not get Google Drive service")
        return None

    # Get folder for this source
    folder_id = get_source_folder(source)
    if not folder_id:
        logger.warning(f"Could not get folder for {source}, uploading to root")
        folder_id = get_root_folder()

    # Prepare file metadata
    if not filename:
        filename = os.path.basename(local_path)

    file_metadata = {
        'name': filename,
        'parents': [folder_id] if folder_id else []
    }

    # Check if file with same name already exists in folder
    try:
        query = f"name = '{filename}' and trashed = false"
        if folder_id:
            query += f" and '{folder_id}' in parents"
        existing = service.files().list(q=query, fields='files(id, name, size)').execute()
        existing_files = existing.get('files', [])
        
        if existing_files:
            # File already exists - get its info and return it
            existing_file = existing_files[0]
            file_id = existing_file.get('id')
            web_link = f"https://drive.google.com/file/d/{file_id}/view"
            download_link = f"https://drive.google.com/uc?id={file_id}&export=download"
            logger.info(f"File already exists in Google Drive, skipping upload: {filename}")
            return {
                'file_id': file_id,
                'web_link': web_link,
                'download_link': download_link,
                'filename': filename,
                'was_duplicate': True
            }
    except Exception as e:
        logger.warning(f"Could not check for existing file: {e}")
        # Continue with upload if check fails

    # Determine MIME type
    extension = os.path.splitext(filename)[1].lower()
    mime_types = {
        '.zip': 'application/zip',
        '.pdf': 'application/pdf',
        '.doc': 'application/msword',
        '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        '.xls': 'application/vnd.ms-excel',
        '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        '.dwg': 'application/acad',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
    }
    mime_type = mime_types.get(extension, 'application/octet-stream')

    try:
        # Upload file
        media = MediaFileUpload(
            local_path,
            mimetype=mime_type,
            resumable=True
        )

        logger.info(f"Uploading {filename} to Google Drive...")
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink, webContentLink'
        ).execute()

        file_id = file.get('id')

        # Do NOT make files public. Keep them private in the owner's Drive.
        # Provide a standard Drive link that requires authentication.
        web_link = file.get('webViewLink') or f"https://drive.google.com/file/d/{file_id}/view"
        download_link = file.get('webContentLink') or f"https://drive.google.com/uc?id={file_id}&export=download"

        logger.info(f"File uploaded successfully (private): {filename} ({file_id})")

        return {
            'file_id': file_id,
            'web_link': web_link,
            'download_link': download_link,
            'filename': filename
        }

    except HttpError as e:
        logger.error(f"Upload failed for {filename}: {e}")
        return None


def delete_local_file(local_path):
    """
    Delete a local file after successful upload.

    Args:
        local_path: Path to file to delete

    Returns:
        True if deleted, False otherwise
    """
    try:
        if os.path.exists(local_path):
            os.remove(local_path)
            logger.info(f"Deleted local file: {local_path}")
            return True
    except Exception as e:
        logger.warning(f"Could not delete local file {local_path}: {e}")
    return False


def upload_and_cleanup(local_path, filename=None, source='BuildingConnected', delete_local=True):
    """
    Upload file to Google Drive and optionally delete local copy.

    Args:
        local_path: Path to local file
        filename: Optional custom filename
        source: Source for folder organization
        delete_local: If True, delete local file after successful upload

    Returns:
        dict with upload info or None if failed
    """
    result = upload_file(local_path, filename, source)

    if result and delete_local:
        delete_local_file(local_path)

    return result


def download_file(file_id, destination_dir=None, filename=None):
    """
    Download a file from Google Drive to local storage.

    Args:
        file_id: Google Drive file ID
        destination_dir: Optional destination directory (defaults to DOWNLOAD_DIR from config)
        filename: Optional custom filename (defaults to file's name in Drive)

    Returns:
        Local file path on success, None on failure
    """
    if not file_id:
        logger.error("No file_id provided for download")
        return None

    service = get_service()
    if not service:
        logger.error("Could not get Google Drive service for download")
        return None

    try:
        # Get file metadata to determine filename
        file_metadata = service.files().get(fileId=file_id, fields='name, mimeType').execute()
        drive_filename = filename or file_metadata.get('name', f'download_{file_id}')
        
        # Set destination directory
        if not destination_dir:
            from backend.config import ScraperConfig
            destination_dir = ScraperConfig.DOWNLOAD_DIR
        
        os.makedirs(destination_dir, exist_ok=True)
        local_path = os.path.join(destination_dir, drive_filename)
        
        # Check if file already exists
        if os.path.exists(local_path):
            logger.info(f"File already exists locally: {local_path}")
            return local_path
        
        # Download file content
        import io
        from googleapiclient.http import MediaIoBaseDownload
        
        request = service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        
        logger.info(f"Downloading from Google Drive: {drive_filename}")
        done = False
        while not done:
            status, done = downloader.next_chunk()
            if status:
                logger.debug(f"Download progress: {int(status.progress() * 100)}%")
        
        # Write to local file
        fh.seek(0)
        with open(local_path, 'wb') as f:
            f.write(fh.read())
        
        logger.info(f"Downloaded to: {local_path}")
        return local_path

    except HttpError as e:
        logger.error(f"Failed to download file {file_id}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error downloading file {file_id}: {e}")
        return None


# Convenience function to check if we should use Google Drive
def should_use_gdrive():
    """
    Check if Google Drive should be used for file storage.
    Checks environment variable and authentication status.
    """
    # Check environment variable
    use_gdrive = os.getenv('USE_GOOGLE_DRIVE', 'false').lower() in ('true', '1', 'yes')

    if not use_gdrive:
        return False

    # Check if available and authenticated
    status = get_status()
    return status['available'] and (status['authenticated'] or status['needs_reauth'])


# Test function
def test_connection():
    """
    Test Google Drive connection by listing root folder contents.

    Returns:
        dict with status and file list or error
    """
    service = get_service()
    if not service:
        return {"success": False, "error": "Could not authenticate"}

    try:
        results = service.files().list(
            pageSize=10,
            fields="files(id, name)"
        ).execute()

        items = results.get('files', [])
        return {
            "success": True,
            "files": items,
            "message": f"Found {len(items)} files in Drive"
        }
    except HttpError as e:
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    # Test script
    print("Google Drive Integration Test")
    print("=" * 40)

    print(f"\nAvailable: {is_available()}")
    print(f"Configured: {is_configured()}")
    print(f"Authenticated: {is_authenticated()}")

    status = get_status()
    print(f"\nStatus: {status}")

    if status['configured'] and not status['authenticated']:
        print("\nAttempting authentication...")
        creds = authenticate()
        if creds:
            print("Authentication successful!")

            print("\nTesting connection...")
            result = test_connection()
            print(f"Result: {result}")
