from PySide6.QtWidgets import (QWidget, QVBoxLayout, QPushButton, QFrame, QSizePolicy)
from PySide6.QtCore import Qt, Property

class CollapsibleFrame(QWidget):
    """
    A Qt equivalent of the legacy CustomTkinter CollapsibleFrame.
    Consists of a Header Button (toggle) and a Content Frame.
    """
    def __init__(self, title="", parent=None, start_open=True):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        
        # Header Button
        self.toggle_btn = QPushButton(f"▼ {title}")
        self.toggle_btn.setStyleSheet("""
            QPushButton {
                text-align: left; 
                font-weight: bold; 
                border: none;
                background-color: transparent;
                padding: 5px;
            }
            QPushButton:hover {
                background-color: #E0E0E0;
            }
        """)
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.setChecked(start_open)
        self.toggle_btn.toggled.connect(self.on_toggle)
        self.layout.addWidget(self.toggle_btn)
        
        # Content Frame
        self.content_area = QFrame()
        self.content_layout = QVBoxLayout(self.content_area)
        self.content_layout.setContentsMargins(5, 5, 5, 5)
        self.layout.addWidget(self.content_area)
        
        self.title_text = title
        
        # Initial State
        self.on_toggle(start_open)

    def on_toggle(self, checked):
        """Show/Hide content."""
        if checked:
            self.content_area.setVisible(True)
            self.toggle_btn.setText(f"▼ {self.title_text}")
        else:
            self.content_area.setVisible(False)
            self.toggle_btn.setText(f"▶ {self.title_text}")

    def add_widget(self, widget):
        """Adds a widget to the content area."""
        self.content_layout.addWidget(widget)

    def add_layout(self, layout):
        self.content_layout.addLayout(layout)
