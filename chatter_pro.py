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
    
    # --- UI Theme & State Bootstrap ---
    try:
        from core.state import AppState
        from core.services.config_service import ConfigService
        from ui.theme_manager import ThemeManager
        from core.q_main_window import QChatterboxPro # Alias for ChatterboxProQt
        
        # 1. Init State
        app_state = AppState()
        config_service = ConfigService()
        
        # 2. Load Persistence
        config_service.load_state(app_state)
        
        # 3. Apply Theme
        print(f"Loading Theme: {app_state.theme_name}")
        ThemeManager.apply_theme(qt_app, app_state.theme_name, app_state.theme_invert)
        
        # 4. Create Window with Injection
        window = QChatterboxPro(app_state=app_state, config_service=config_service)
        window.show()
        
    except Exception as e:
        print(f"Critical Startup Error: {e}")
        import traceback
        traceback.print_exc()
    
    # Run Event Loop
    sys.exit(qt_app.exec())