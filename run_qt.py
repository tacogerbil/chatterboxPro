import sys
import os


# Ensure the execution directory is in path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

from core.q_main_window import launch_qt_app


# Setup Logging
import logging
from logging.handlers import RotatingFileHandler

def setup_logging():
    log_dir = os.path.join(current_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "error.log")
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            RotatingFileHandler(log_file, maxBytes=1024*1024, backupCount=5),
            logging.StreamHandler(sys.stdout)
        ]
    )
    # Redirect stderr to log
    sys.stderr = open(os.path.join(log_dir, "stderr.log"), 'w')

if __name__ == "__main__":
    setup_logging()
    launch_qt_app()
