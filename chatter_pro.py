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
from ui.main_window import ChatterboxProGUI
from utils.dependency_checker import DependencyManager

# --- FIX: Monkeypatch CTkToolTip for compatibility with new CustomTkinter ---
# The ScalingTracker in CTk 5.2.2 expects tracked windows to have 'block_update_dimensions_event'.
try:
    from CTkToolTip import CTkToolTip
    if not hasattr(CTkToolTip, 'block_update_dimensions_event'):
        def block_update_dimensions_event(self):
            pass
        CTkToolTip.block_update_dimensions_event = block_update_dimensions_event
except ImportError:
    pass # If CTkToolTip isn't installed, we don't need the patch (app might degrade gracefully)

# --- Header ---
CODE_VERSION = "2024-08-05-Final-Refactor"
print(f"--- Running Chatterbox Pro ---\n--- Code Version: {CODE_VERSION} ---")

if __name__ == "__main__":
    if sys.platform in ["win32", "darwin"] and multiprocessing.get_start_method(allow_none=True) != 'spawn':
        try:
            multiprocessing.set_start_method('spawn', force=True)
            logging.info("Multiprocessing start method set to 'spawn'.")
        except RuntimeError:
            logging.warning(f"Could not set 'spawn' method, already set to: {multiprocessing.get_start_method(allow_none=True)}.")

    deps = DependencyManager()
    app = ChatterboxProGUI(dependency_manager=deps)
    app.mainloop()