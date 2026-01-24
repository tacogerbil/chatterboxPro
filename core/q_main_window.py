import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QTabWidget, QLabel
from PySide6.QtCore import Qt
from qt_material import apply_stylesheet

# Import our decoupled State
from core.state import AppState

class QChatterboxMainWindow(QMainWindow):
    def __init__(self, app_state: AppState):
        super().__init__()
        self.app_state = app_state
        
        self.setWindowTitle("Chatterbox Pro (Qt Edition)")
        self.resize(1280, 800)
        
        # Central Widget & Main Layout
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        
        # Tab Widget
        self.tabs = QTabWidget()
        self.main_layout.addWidget(self.tabs)
        
        # Add Placeholders for Tabs
        self._init_tabs()
        
        # Status Bar
        self.statusBar().showMessage("Ready")

    def _init_tabs(self):
        """Initialize the tabs (Setup, Chapters, Generation, etc.)"""
        # 1. Setup Tab (Placeholder)
        setup_tab = QWidget()
        setup_layout = QVBoxLayout(setup_tab)
        setup_layout.addWidget(QLabel("Setup Tab Placeholder"))
        setup_layout.addStretch()
        self.tabs.addTab(setup_tab, "1. Setup")
        
        # 2. Chapters Tab (Placeholder)
        chapters_tab = QWidget()
        chapters_layout = QVBoxLayout(chapters_tab)
        chapters_layout.addWidget(QLabel("Chapters Tab Placeholder"))
        chapters_layout.addStretch()
        self.tabs.addTab(chapters_tab, "2. Chapters")
        
        # 3. Generation Tab (Placeholder)
        gen_tab = QWidget()
        gen_layout = QVBoxLayout(gen_tab)
        gen_layout.addWidget(QLabel("Generation Tab Placeholder"))
        gen_layout.addStretch()
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
