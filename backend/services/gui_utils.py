import tkinter
from tkinter import filedialog
import logging

logger = logging.getLogger(__name__)

def pick_folder():
    """
    Opens a system folder picker dialog and returns the selected path.
    Returns None if cancelled or error.
    IMPORTANT: This must be run in a way that doesn't block the main thread if called from async context,
    but tkinter requires the main thread usually. However, for a simple dialog, creating a new root often works
    if no other tk loop is running.
    """
    try:
        # Create a root window and hide it
        root = tkinter.Tk()
        root.withdraw()  # Hide the main window
        root.attributes('-topmost', True)  # Make dialog appear on top

        # Open directory dialog
        folder_path = filedialog.askdirectory()
        
        # Destroy root to clean up
        root.destroy()
        
        if folder_path:
            # tkinter returns "/" as separator even on Windows, usually fine for Python
            # but let's normalize just in case
            import os
            return os.path.normpath(folder_path)
        return None
    except Exception as e:
        logger.error(f"Error opening folder picker: {e}")
        return None

def open_folder(path):
    """
    Opens a folder in the system file explorer.
    """
    import os
    import subprocess
    import platform

    try:
        path = os.path.normpath(path)
        if not os.path.exists(path):
            return False
            
        if platform.system() == "Windows":
            os.startfile(path)
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return True
    except Exception as e:
        logger.error(f"Error opening folder {path}: {e}")
        return False
