# chatter_pro.py
# Code Version: 2024-08-05-Final-Refactor

import sys
import os
from pathlib import Path
import multiprocessing
import logging

# --- EXPERT FIX: Add project root to Python path ---
# This ensures that all modules (ui, core, workers, etc.) can see each other.
project_root = Path(__file__).parent.resolve()
sys.path.insert(0, str(project_root))

# --- Project-Specific Imports ---
# from ui.main_window import ChatterboxProGUI # LEGACY
from core.q_main_window import QChatterboxPro
from PySide6.QtWidgets import QApplication
from utils.dependency_checker import DependencyManager

# --- Header ---
CODE_VERSION = "2026-01-25-PySide6-Migration"
print(f"--- Running Chatterbox Pro ---\n--- Code Version: {CODE_VERSION} ---")

if __name__ == "__main__":
    if sys.platform in ["win32", "darwin"] and multiprocessing.get_start_method(allow_none=True) != 'spawn':
        try:
            multiprocessing.set_start_method('spawn', force=True)
            logging.info("Multiprocessing start method set to 'spawn'.")
        except RuntimeError:
            logging.warning(f"Could not set 'spawn' method.")

    # Initialize Dependency Manager
    deps = DependencyManager()
    
    # Initialize Qt Application
    qt_app = QApplication(sys.argv)
    qt_app.setApplicationName("Chatterbox Pro")
    
    # Initialize Main Window (New Codebase)
    window = QChatterboxPro(dependency_manager=deps)
    window.show()
    
    # Run Event Loop
    sys.exit(qt_app.exec())