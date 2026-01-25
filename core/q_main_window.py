import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QTabWidget, QLabel, QHBoxLayout, QSplitter
from PySide6.QtCore import Qt
from qt_material import apply_stylesheet
from core.state import AppState

from ui.views.generation_view import GenerationView
from ui.views.chapters_view import ChaptersView
from ui.views.setup_view import SetupView
from ui.views.controls_view import ControlsView

class QChatterboxMainWindow(QMainWindow):
    def __init__(self, app_state: AppState):
        super().__init__()
        self.app_state = app_state
        
        self.setWindowTitle("Chatterbox Pro (Qt Edition)")
        self.resize(1400, 900)
        
        # Central Widget
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        
        # Main Layout (Horizontal Split)
        self.main_layout = QHBoxLayout(self.central_widget)
        
        # Splitter to allow resizing
        self.splitter = QSplitter(Qt.Horizontal)
        self.main_layout.addWidget(self.splitter)
        
        # Left Side (Tabs)
        self.tabs = QTabWidget()
        self.splitter.addWidget(self.tabs)
        
        # Right Side (Playlist + Controls)
        self.playlist_container = QWidget()
        pl_layout = QVBoxLayout(self.playlist_container)
        pl_layout.setContentsMargins(0, 0, 0, 0)
        
        self.playlist_view = PlaylistView(self.app_state)
        self.controls_view = ControlsView(self.app_state)
        
        # Connect Signals
        self.controls_view.refresh_requested.connect(self.playlist_view.refresh)
        
        pl_layout.addWidget(self.playlist_view, stretch=2)
        pl_layout.addWidget(self.controls_view, stretch=0) # Let it take natural height? No, stretch 0 means minimal necessary.
        
        self.splitter.addWidget(self.playlist_container)
        
        # Set initial sizes (Tabs check roughly 65%, Playlist 35%)
        self.splitter.setSizes([900, 500])
        
        # Add Tabs contents
        self._init_tabs()
        
        # Status Bar
        self.statusBar().showMessage("Ready")

    def _init_tabs(self):
        """Initialize the tabs (Setup, Chapters, Generation, etc.)"""
        # 1. Setup Tab (Implemented)
        setup_tab = SetupView(self.app_state)
        self.tabs.addTab(setup_tab, "1. Setup")
        
        # 2. Chapters Tab (Implemented)
        chapters_tab = ChaptersView(self.app_state)
        self.tabs.addTab(chapters_tab, "2. Chapters")
        
        # 3. Generation Tab (Implemented)
        gen_tab = GenerationView(self.app_state)
        self.tabs.addTab(gen_tab, "3. Generation")
        
        # 4. Finalize Tab (Implemented)
        final_tab = FinalizeView(self.app_state)
        self.tabs.addTab(final_tab, "4. Finalize")

def launch_qt_app():
    """Entry point for the Qt application."""
    # Create the Application
    app = QApplication(sys.argv)
    
    # Apply modern theme
    # Using 'dark_teal.xml' as a safe default - looks professional
    try:
        apply_stylesheet(app, theme='dark_teal.xml')
    except Exception as e:
        print(f"Warning: Could not apply material theme: {e}")
    
    # Initialize State
    state = AppState()
    
    # visual separation from legacy code
    print("--- Launching Chatterbox Pro (Qt) ---")
    
    # Create and Show Window
    window = QChatterboxMainWindow(state)
    window.show()
    
    # Start Event Loop
    sys.exit(app.exec())

if __name__ == "__main__":
    launch_qt_app()
