from ui.views.generation_view import GenerationView
from ui.views.chapters_view import ChaptersView

class QChatterboxMainWindow(QMainWindow):
    def __init__(self, app_state: AppState):
        # ... (same) ...

    def _init_tabs(self):
        """Initialize the tabs (Setup, Chapters, Generation, etc.)"""
        # 1. Setup Tab (Placeholder)
        setup_tab = QWidget()
        setup_layout = QVBoxLayout(setup_tab)
        setup_layout.addWidget(QLabel("Setup Tab Placeholder"))
        setup_layout.addStretch()
        self.tabs.addTab(setup_tab, "1. Setup")
        
        # 2. Chapters Tab (Implemented)
        chapters_tab = ChaptersView(self.app_state)
        self.tabs.addTab(chapters_tab, "2. Chapters")
        
        # 3. Generation Tab (Implemented)
        gen_tab = GenerationView(self.app_state)
        self.tabs.addTab(gen_tab, "3. Generation")

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
