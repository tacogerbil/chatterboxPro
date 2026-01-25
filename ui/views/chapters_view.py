from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QListView, 
                               QPushButton, QLabel, QMessageBox, QCheckBox)
from PySide6.QtCore import Qt
from core.state import AppState
from core.models.chapter_model import ChapterModel
from core.services.chapter_service import ChapterService

class ChaptersView(QWidget):
    def __init__(self, app_state: AppState, parent=None):
        super().__init__(parent)
        self.app_state = app_state
        self.logic = ChapterService()
        
        self.model = ChapterModel(app_state)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Header / Controls
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("Detected Chapters"))
        header_layout.addStretch()
        
        # Generate Selected button
        self.gen_btn = QPushButton("Generate Selected")
        self.gen_btn.setStyleSheet("background-color: #D35400; color: white; font-weight: bold;")
        self.gen_btn.clicked.connect(self.generate_selected)
        header_layout.addWidget(self.gen_btn)
        
        # Auto-loop Checkbox
        self.auto_loop_chk = QCheckBox("Auto-loop")
        self.auto_loop_chk.setChecked(self.app_state.auto_regen_main)
        self.auto_loop_chk.stateChanged.connect(lambda s: setattr(self.app_state, 'auto_regen_main', s == Qt.Checked))
        header_layout.addWidget(self.auto_loop_chk)
        
        refresh_btn = QPushButton("↻ Refresh")
        refresh_btn.clicked.connect(self.model.refresh)
        header_layout.addWidget(refresh_btn)
        
        layout.addLayout(header_layout)
        
        # List View
        self.list_view = QListView()
        self.list_view.setModel(self.model)
        self.list_view.setAlternatingRowColors(True)
        # self.list_view.setSelectionMode(QListView.ExtendedSelection) # Using checkboxes instead
        layout.addWidget(self.list_view)
        
        # Footer Selection Controls
        footer_layout = QHBoxLayout()
        
        sel_all = QPushButton("Select All")
        sel_all.clicked.connect(self.select_all)
        footer_layout.addWidget(sel_all)
        
        sel_none = QPushButton("Deselect All")
        sel_none.clicked.connect(self.deselect_all)
        footer_layout.addWidget(sel_none)
        
        footer_layout.addStretch()
        
        # Generate Button
        self.gen_btn = QPushButton("Generate Selected")
        self.gen_btn.setStyleSheet("background-color: #D35400; color: white; font-weight: bold;")
        self.gen_btn.clicked.connect(self.generate_selected)
        footer_layout.addWidget(self.gen_btn)
        
        layout.addLayout(footer_layout)

    def select_all(self):
        for i in range(self.model.rowCount()):
            idx = self.model.index(i, 0)
            self.model.setData(idx, Qt.Checked, Qt.CheckStateRole)

    def deselect_all(self):
        for i in range(self.model.rowCount()):
            idx = self.model.index(i, 0)
            self.model.setData(idx, Qt.Unchecked, Qt.CheckStateRole)

    def generate_selected(self):
        selected_chapters = self.model.get_selected_indices()
        if not selected_chapters:
            QMessageBox.information(self, "Info", "No chapters selected.")
            return
            
        full_indices = self.logic.get_indices_for_chapters(
            self.app_state.sentences,
            self.model._chapters, # Pass the cached chapter list
            selected_chapters
        )
        
        QMessageBox.information(self, "Generation", 
                              f"Simulated Generation Start.\nIndices to process: {len(full_indices)}")
        # Logic link: In real app, this would emit a signal: self.generation_requested.emit(full_indices)
        
