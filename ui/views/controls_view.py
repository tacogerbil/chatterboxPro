from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                               QLabel, QLineEdit, QGroupBox, QGridLayout, QMessageBox, QFrame, QToolBox)
from PySide6.QtCore import Qt, Signal
from core.state import AppState
from core.services.playlist_service import PlaylistService

class ControlsView(QWidget):
    """
    The Editing Suite: Playback, Search, Editing, and Batch operations.
    Replaces legacy ControlsFrame.
    """
    # Signals to request App actions
    refresh_requested = Signal() # Request playlist view refresh
    playback_requested = Signal(str) # cmd: "play", "stop", "play_from"
    
    def __init__(self, app_state: AppState, parent=None):
        super().__init__(parent)
        self.state = app_state
        self.service = PlaylistService(app_state)
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0) # Tight fit
        
        # We use QToolBox to simulate the Collapsible Groups
        self.toolbox = QToolBox()
        
        # --- Page 1: Playback & Navigation ---
        page1 = QWidget()
        p1_layout = QVBoxLayout(page1)
        
        # Row 1: Playback
        pb_layout = QHBoxLayout()
        self.btn_play = QPushButton("▶ Play"); self.btn_play.clicked.connect(lambda: self.playback_requested.emit("play"))
        self.btn_stop = QPushButton("■ Stop"); self.btn_stop.clicked.connect(lambda: self.playback_requested.emit("stop"))
        self.btn_play_from = QPushButton("▶ From Selec."); self.btn_play_from.clicked.connect(lambda: self.playback_requested.emit("play_from"))
        pb_layout.addWidget(self.btn_play); pb_layout.addWidget(self.btn_stop); pb_layout.addWidget(self.btn_play_from)
        p1_layout.addLayout(pb_layout)
        
        # Row 2: Move / Errors
        mv_layout = QHBoxLayout()
        self.btn_up = QPushButton("▲ Up"); self.btn_up.clicked.connect(lambda: self.move_item(-1))
        self.btn_down = QPushButton("▼ Down"); self.btn_down.clicked.connect(lambda: self.move_item(1))
        self.btn_prev_err = QPushButton("◄ Prev Err"); self.btn_prev_err.clicked.connect(lambda: self.find_error(-1))
        self.btn_next_err = QPushButton("Next Err ►"); self.btn_next_err.clicked.connect(lambda: self.find_error(1))
        mv_layout.addWidget(self.btn_up); mv_layout.addWidget(self.btn_down)
        mv_layout.addWidget(self.btn_prev_err); mv_layout.addWidget(self.btn_next_err)
        p1_layout.addLayout(mv_layout)
        
        # Row 3: Search
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("🔍"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search text...")
        self.search_input.returnPressed.connect(self.perform_search)
        search_layout.addWidget(self.search_input)
        self.btn_s_prev = QPushButton("◄"); self.btn_s_prev.clicked.connect(self.search_prev)
        self.btn_s_next = QPushButton("►"); self.btn_s_next.clicked.connect(self.search_next)
        search_layout.addWidget(self.btn_s_prev); search_layout.addWidget(self.btn_s_next)
        p1_layout.addLayout(search_layout)
        
        p1_layout.addStretch()
        self.toolbox.addItem(page1, "Playback & Navigation")
        
        # --- Page 2: Chunk Editing ---
        page2 = QWidget()
        p2_layout = QGridLayout(page2)
        
        # Edit/Split/Insert
        btn_edit = QPushButton("✎ Edit"); btn_edit.clicked.connect(self.edit_current)
        btn_split = QPushButton("➗ Split"); btn_split.clicked.connect(self.split_current)
        btn_mark = QPushButton("M Mark"); btn_mark.clicked.connect(self.mark_current)
        btn_del = QPushButton("❌ Delete"); btn_del.clicked.connect(self.delete_current)
        
        p2_layout.addWidget(btn_edit, 0, 0)
        p2_layout.addWidget(btn_split, 0, 1)
        p2_layout.addWidget(btn_mark, 1, 0)
        p2_layout.addWidget(btn_del, 1, 1)
        
        # Advanced Inserts
        btn_ins_txt = QPushButton("➕ Text"); btn_ins_txt.clicked.connect(self.insert_text)
        btn_ins_pause = QPushButton("⏸ Pause"); btn_ins_pause.clicked.connect(self.insert_pause)
        btn_ins_chap = QPushButton("📑 Chapter"); btn_ins_chap.clicked.connect(self.insert_chapter)
        
        p2_layout.addWidget(btn_ins_txt, 2, 0)
        p2_layout.addWidget(btn_ins_pause, 2, 1)
        p2_layout.addWidget(btn_ins_chap, 3, 0, 1, 2)
        
        self.toolbox.addItem(page2, "Chunk Editing")
        
        # --- Page 3: Batch Operations ---
        page3 = QWidget()
        p3_layout = QVBoxLayout(page3)
        
        btn_merge = QPushButton("Merge Failed Down (TODO)")
        btn_regen = QPushButton("↻ Regenerate Marked")
        btn_regen.setStyleSheet("background-color: #D35400; color: white;")
        
        p3_layout.addWidget(btn_merge)
        p3_layout.addWidget(btn_regen)
        p3_layout.addStretch()
        
        self.toolbox.addItem(page3, "Batch Operations")
        
        layout.addWidget(self.toolbox)
        
        # Internal Search State
        self.search_matches = []
        self.curr_search_idx = -1

    # --- Actions ---
    def get_selected_indices(self):
        # This view doesn't own the selection. 
        # Ideally it should receive it or query the main window/state.
        # For now, we assume AppState has a 'selection' field or we query via parent?
        # NO. We should emit signals or rely on shared state.
        # But 'selected_indices' isn't in AppState yet. It was in PlaylistFrame.
        # SHORTCUT: Only operate if we can get selection.
        # For this MVP, we will rely on single-item actions via dialogs or similar.
        pass
        
    def move_item(self, direction):
        # Currently difficult without knowing selection from PlaylistView.
        QMessageBox.information(self, "Info", "Select items in playlist first (Wiring pending).")

    def find_error(self, direction):
        # We need to know where we are.
        # Just searching from 0 for now or using service.
        idx = self.service.find_next_status(-1, direction, 'failed')
        if idx >= 0:
            QMessageBox.information(self, "Found", f"Found error at index {idx}. (Selection wiring needed)")
        else:
             QMessageBox.information(self, "Info", "No errors found.")

    def perform_search(self):
        query = self.search_input.text()
        self.search_matches = self.service.search(query)
        if self.search_matches:
            self.curr_search_idx = 0
            self.search_next()
        else:
            QMessageBox.information(self, "Search", "No matches found.")
            
    def search_next(self):
        if not self.search_matches: return
        idx = self.search_matches[self.curr_search_idx]
        self.curr_search_idx = (self.curr_search_idx + 1) % len(self.search_matches)
        # Emit signal to select this index
        QMessageBox.information(self, "Search", f"Found at {idx}. (Jump not wired)")

    def search_prev(self):
        if not self.search_matches: return
        self.curr_search_idx = (self.curr_search_idx - 1) % len(self.search_matches)
        idx = self.search_matches[self.curr_search_idx]
        QMessageBox.information(self, "Search", f"Found at {idx}. (Jump not wired)")

    # --- Editing ---
    def edit_current(self):
        QMessageBox.information(self, "Edit", "Edit dialog would open here.")
        
    def split_current(self):
        # Simulating split of index 0 for testing if no selection
        QMessageBox.information(self, "Split", "Split logic ready in Service, need selection wiring.")
        
    def mark_current(self):
        pass

    def delete_current(self):
        pass
        
    def insert_text(self):
        self.service.insert_item(0, "New Text Block")
        self.refresh_requested.emit()
        
    def insert_pause(self):
        self.service.insert_item(0, "--- PAUSE ---", is_pause=True, duration=500)
        self.refresh_requested.emit()
        
    def insert_chapter(self):
        self.service.insert_item(0, "Chapter X", is_chapter=True)
        self.refresh_requested.emit()
