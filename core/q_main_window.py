import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QTabWidget, QLabel, QHBoxLayout, QSplitter
from PySide6.QtCore import Qt
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

class ChatterboxProQt(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Chatterbox Pro (Qt Edition)")
        self.resize(1600, 900)
        
        self.app_state = AppState()
        
        # Instantiate Backend Services
        self.gen_service = GenerationService(self.app_state)
        self.audio_service = AudioService(self.app_state)
        
        # Setup UI
        self.setup_ui()
        self.setup_connections()
        
    def setup_ui(self):
        # ... (Layout code typically here, but views are created below)
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        
        # Views
        self.setup_view = SetupView(self.app_state)
        self.gen_view = GenerationView(self.app_state) # Creates its own gen_service wrapper? No, use shared?
        # Correction: GenerationView creates its own. We should pass ours OR let it maintain its own.
        # But global logic (ChaptersView) needs one too.
        # Ideally we share ONE service instance.
        
        # Let's injecting the SHARED service into GenView instead of letting it create one.
        # I need to update GenView constructor or setter? 
        # I'll use setter for consistency.
        
        self.chapters_view = ChaptersView(self.app_state)
        self.finalize_view = FinalizeView(self.app_state)
        
        self.playlist_view = PlaylistView(self.app_state)
        self.controls_view = ControlsView(self.app_state)
        
        # Inject Services
        # GenerationView creates one internally in current code (Step 1761). 
        # That's okay, but better to share if we want global stop?
        # Actually Step 1761 code: self.service = GenerationService(state).
        # We will leave GenView having its own for now (Parity: Generation Tab was isolated).
        # BUT ChaptersView needs one. We pass self.gen_service to ChaptersView.
        # And ControlsView needs AudioService.
        # FinalizeView needs AudioService.
        
        self.controls_view.set_playlist_reference(self.playlist_view)
        self.controls_view.set_audio_service(self.audio_service)
        
        self.chapters_view.set_generation_service(self.gen_service)
        
        self.finalize_view.set_audio_service(self.audio_service)
        
        # Connect Signals
        self.controls_view.refresh_requested.connect(self.playlist_view.refresh)
        

    # ... (No _init_tabs needed)

def launch_qt_app():
    """Entry point for the Qt application."""
    # Create the Application
    app = QApplication(sys.argv)
    
    # Apply modern theme
    try:
        apply_stylesheet(app, theme='dark_teal.xml')
    except Exception as e:
        print(f"Warning: Could not apply material theme: {e}")
    
    # Initialize State
    # state = AppState() # Moved inside MainWindow to be self-contained or passed?
    # Let's keep it clean: MainWindow creates it if not passed, or we pass it.
    # Current implementation of ChatterboxProQt creates it. 
    # Let's stick to that for simplicity of entry point.
    
    # visual separation from legacy code
    print("--- Launching Chatterbox Pro (Qt) ---")
    
    # Create and Show Window
    window = ChatterboxProQt()
    window.show()
    
    # Start Event Loop
    sys.exit(app.exec())

if __name__ == "__main__":
    launch_qt_app()
