"""
Silent launcher for Windows - runs with pythonw.exe (no console window).
Also works on Linux as a regular Python script.
"""
import os
import sys
import logging
from logging.handlers import RotatingFileHandler

# Set working directory to this script's directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Log to file since there's no console
log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent.log")
handler = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=2)
handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
logging.basicConfig(level=logging.INFO, handlers=[handler])

# Redirect stdout/stderr to log file (pythonw has no console)
sys.stdout = open(log_file, "a", encoding="utf-8")
sys.stderr = sys.stdout

import asyncio
from main import main

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logging.getLogger(__name__).critical(f"Fatal error: {e}", exc_info=True)
