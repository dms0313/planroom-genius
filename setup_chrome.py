import os
import sys
import zipfile
import shutil
import urllib.request
import ssl

def download_chrome():
    """
    Download a portable Chromium build for Windows.
    Using a known stable version to ensure compatibility.
    """
    print("="*60)
    print("  SETTING UP DEDICATED CHROME EXECUTABLE")
    print("="*60)
    
    # Destination directory
    backend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend')
    chrome_dir = os.path.join(backend_dir, 'chrome-win')
    zip_path = os.path.join(backend_dir, 'chrome-win.zip')
    
    # Check if already exists
    exe_path = os.path.join(chrome_dir, 'chrome.exe')
    if os.path.exists(exe_path):
        print(f"\n[OK] Dedicated Chrome already exists at:\n     {exe_path}")
        print("\nSetup is already complete!")
        return

    # Get latest revision number
    print(f"\n[1/4] Fetching latest Chromium revision info...")
    try:
        context = ssl._create_unverified_context()
        last_change_url = "https://www.googleapis.com/download/storage/v1/b/chromium-browser-snapshots/o/Win_x64%2FLAST_CHANGE?alt=media"
        with urllib.request.urlopen(last_change_url, context=context) as response:
            revision = response.read().decode('utf-8').strip()
            
        print(f"      Latest revision: {revision}")
        
        chromium_url = f"https://www.googleapis.com/download/storage/v1/b/chromium-browser-snapshots/o/Win_x64%2F{revision}%2Fchrome-win.zip?alt=media"
        
    except Exception as e:
        print(f"\n[ERROR] Could not get latest revision: {e}")
        return

    print(f"\n[2/4] Downloading portable Chromium (Rev: {revision})...")
    print("      This may take a minute depending on your internet connection.")
    
    try:
        # Download with progress indicator
        def allow_progress(count, block_size, total_size):
            if total_size > 0:
                percent = int(count * block_size * 100 / total_size)
                sys.stdout.write(f"\r      Progress: {percent}% ")
                sys.stdout.flush()
            
        urllib.request.urlretrieve(chromium_url, zip_path, reporthook=allow_progress, data=None)
        print("\n      Download complete!")
        
    except Exception as e:
        print(f"\n[ERROR] Download failed: {e}")
        return

    # Extract
    print(f"\n[3/4] Extracting files...")
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(backend_dir)
        print("      Extraction complete!")
    except Exception as e:
        print(f"\n[ERROR] Extraction failed: {e}")
        return
        
    # Cleanup zip
    print(f"\n[3/3] Cleaning up...")
    try:
        os.remove(zip_path)
    except:
        pass
        
    # Verify
    if os.path.exists(exe_path):
        print("\n" + "="*60)
        print("  SUCCESS! Dedicated Chrome is ready.")
        print("="*60)
        print(f"  Location: {exe_path}")
        print("\n  The scraper will now automatically use this version instead of your system Chrome.")
        print("  Run the scraper again to see it in action!")
    else:
        print("\n[ERROR] Something went wrong. chrome.exe not found after extraction.")

if __name__ == "__main__":
    download_chrome()
    input("\nPress Enter to exit...")
