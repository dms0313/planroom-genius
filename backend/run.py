import sys
import asyncio
import logging
import uvicorn
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("PlanroomRunner")

def main():
    # CRITICAL: Force ProactorEventLoop on Windows to support subprocesses (Chrome)
    if sys.platform == 'win32':
        logger.info("🔧 Enforcing WindowsProactorEventLoopPolicy for browser support...")
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    # Ensure the current directory is in sys.path
    sys.path.append(os.getcwd())

    logger.info("🚀 Starting Uvicorn Server...")
    # Run uvicorn programmatically
    # We disable reload to prevent loop policy interference and subprocess issues
    uvicorn.run(
        "backend.api:app", 
        host="0.0.0.0", 
        port=8000, 
        reload=False,  # Important for stability with browser-use on Windows
        log_level="info"
    )

if __name__ == "__main__":
    main()
