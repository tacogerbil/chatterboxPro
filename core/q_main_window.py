import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QTabWidget, QSplitter
from qt_material import apply_stylesheet
from core.state import AppState

from ui.views.generation_view import GenerationView
from ui.views.chapters_view import ChaptersView
from ui.views.setup_view import SetupView
from ui.views.playlist_view import PlaylistView
from ui.views.controls_view import ControlsView
from ui.views.finalize_view import FinalizeView

from core.services.generation_service import GenerationService
from core.services.audio_service import AudioService
from core.services.playlist_service import PlaylistService

class ChatterboxProQt(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Chatterbox Pro (Qt Edition)")
        self.resize(1600, 900)
        
        self.app_state = AppState()
        
        # Instantiate Backend Services
        self.gen_service = GenerationService(self.app_state)
        self.audio_service = AudioService(self.app_state)
        self.playlist_service = PlaylistService(self.app_state)
        
        # Setup UI
        self.setup_ui()
        
    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        
        # Splitter: Left (Tabs) | Right (Playlist + Controls)
        splitter = QSplitter(sys.modules[__name__].Qt.Horizontal if hasattr(sys.modules[__name__], 'Qt') else sys.modules['PySide6.QtCore'].Qt.Horizontal)
        
        # --- Left Side: Tabs ---
        self.tabs = QTabWidget()
        self.setup_view = SetupView(self.app_state)
        self.gen_view = GenerationView(self.app_state)
        self.chapters_view = ChaptersView(self.app_state)
        self.finalize_view = FinalizeView(self.app_state)
        
        self.tabs.addTab(self.setup_view, "Setup Session")
        self.tabs.addTab(self.gen_view, "Generation")
        self.tabs.addTab(self.chapters_view, "Chapters")
        self.tabs.addTab(self.finalize_view, "Finalize & Export")
        
        splitter.addWidget(self.tabs)
        
        # --- Right Side: Playlist + Controls ---
        # ControlsView needs services
        services = {
            'playlist': self.playlist_service,
            'generation': self.gen_service
        }
        
        self.playlist_view = PlaylistView(self.app_state)
        self.controls_view = ControlsView(services, self.playlist_view)
        
        # Embed Controls into PlaylistView (Bottom Slot)
        self.playlist_view.add_controls_view(self.controls_view)
        
        splitter.addWidget(self.playlist_view)
        
        # Layout Config
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        
        main_layout.addWidget(splitter)
        
        # --- Inject Services into Views ---
        # SetupView needs ProjectService (created internally) but ideally passed.
        # GenView uses internal logic but we might switch later.
        
        self.chapters_view.set_generation_service(self.gen_service)
        self.finalize_view.set_audio_service(self.audio_service)
        
        # Connect Signals (Global Refresh)
        self.controls_view.playlist = self.playlist_view # Ensure ref matches
        
        # Optional: Status Bar
        self.statusBar().showMessage("Ready")

def launch_qt_app():
    # Create the Application
    app = QApplication(sys.argv)
    
    # Apply modern theme
    try:
        apply_stylesheet(app, theme='dark_teal.xml')
    except Exception as e:
        print(f"Warning: Could not apply material theme: {e}")

    print("--- Launching Chatterbox Pro (Qt) ---")
    
    # Create and Show Window
    window = ChatterboxProQt()
    window.show()
    
    sys.exit(app.exec())
