import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QTabWidget, QSplitter
from typing import Optional, Dict, Any

from core.state import AppState

from ui.views.generation_view import GenerationView
from ui.views.chapters_view import ChaptersView
from ui.views.setup_view import SetupView
from ui.views.playlist_view import PlaylistView
from ui.views.controls_view import ControlsView
from ui.views.finalize_view import FinalizeView
from ui.views.config_view import ConfigView

from core.services.generation_service import GenerationService
from core.services.audio_service import AudioService
from core.services.playlist_service import PlaylistService
from core.services.assembly_service import AssemblyService

class ChatterboxProQt(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Chatterbox Pro (Qt Edition)")
        self.resize(1600, 900)
        
        self.app_state = AppState()
        
        # Instantiate Backend Services
        self.gen_service = GenerationService(self.app_state)
        self.audio_service = AudioService()
        self.assembly_service = AssemblyService(self.app_state)
        self.playlist_service = PlaylistService(self.app_state)
        
        # UI Components Placeholders
        self.tabs: Optional[QTabWidget] = None
        self.split_view: Optional[QSplitter] = None
        
        self.setup_ui()
        self._inject_dependencies()
        self._connect_signals()
        
        # Status Bar
        self.statusBar().showMessage("Ready")
        
    def setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        
        # Splitter: Left (Tabs) | Right (Playlist + Controls)
        self.split_view = QSplitter(sys.modules[__name__].Qt.Horizontal if hasattr(sys.modules[__name__], 'Qt') else sys.modules['PySide6.QtCore'].Qt.Horizontal)
        
        # --- Left Side: Tabs ---
        self._setup_tabs()
        self.split_view.addWidget(self.tabs)
        
        # --- Right Side: Playlist + Controls ---
        self._setup_playlist_controls()
        self.split_view.addWidget(self.playlist_view)
        
        # Layout Config
        self.split_view.setStretchFactor(0, 3)
        self.split_view.setStretchFactor(1, 2)
        self.split_view.setCollapsible(0, False)
        self.split_view.setCollapsible(1, False)
        
        main_layout.addWidget(self.split_view)

    def _setup_tabs(self) -> None:
        self.tabs = QTabWidget()
        self.setup_view = SetupView(self.app_state)
        self.gen_view = GenerationView(self.app_state)
        self.chapters_view = ChaptersView(self.app_state)
        self.finalize_view = FinalizeView(self.app_state)
        
        self.tabs.addTab(self.setup_view, "Setup Session")
        self.tabs.addTab(self.gen_view, "Generation")
        self.tabs.addTab(self.chapters_view, "Chapters")
        self.tabs.addTab(self.chapters_view, "Chapters")
        self.tabs.addTab(self.finalize_view, "Finalize & Export")
        
        self.config_view = ConfigView()
        self.tabs.addTab(self.config_view, "Config")

    def _setup_playlist_controls(self) -> None:
        # ControlsView needs services map
        services: Dict[str, Any] = {
            'playlist': self.playlist_service,
            'generation': self.gen_service
        }
        
        self.playlist_view = PlaylistView(self.app_state)
        self.controls_view = ControlsView(services, self.playlist_view)
        
        # Embed Controls into PlaylistView (Bottom Slot)
        self.playlist_view.add_controls_view(self.controls_view)
        self.controls_view.playlist = self.playlist_view

    def _inject_dependencies(self) -> None:
        """Injects services into Views that need them."""
        # Generation View
        self.gen_view.set_generation_service(self.gen_service)
        self.gen_view.set_audio_service(self.audio_service)

        # Other Views
        self.chapters_view.set_generation_service(self.gen_service)
        self.finalize_view.set_audio_service(self.audio_service)
        self.finalize_view.set_assembly_service(self.assembly_service)
        
        # Inject dependencies for Auto-Fix Loop in GenService
        self.gen_service.set_playlist_service(self.playlist_service)

    def _connect_signals(self) -> None:
        """Connects global signals between components."""
        # Connect Auto-Fix Status to Status Bar
        self.gen_service.auto_fix_status.connect(self.statusBar().showMessage)
        
        # Wire Template Loading (View Migration Parity)
        self.setup_view.template_loaded.connect(self.gen_view.refresh_values)

def launch_qt_app() -> None:
    # Create the Application
    app = QApplication(sys.argv)
    
    # Theme is handled in the main entry point (chatter_pro.py) via qt-material
    # Legacy pyqtdarktheme removed.

    print("--- Launching Chatterbox Pro (Qt) ---")
    
    # Create and Show Window
    window = ChatterboxProQt()
    window.show()
    
    sys.exit(app.exec())
