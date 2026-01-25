from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QLineEdit, QToolBox, QMessageBox, QGridLayout, QInputDialog
)
from PySide6.QtCore import Qt, Signal
from core.state import AppState
from core.services.playlist_service import PlaylistService

class ControlsView(QWidget):
    """
    The Editing Suite: Playback, Search, Editing, and Batch operations.
    Replaces legacy ControlsFrame.
    
    This view acts as a Controller for the PlaylistService, triggering
    state mutations based on user input (buttons/dialogs).
    """
    # Signals to request App actions
    refresh_requested = Signal() # Request playlist view refresh
    playback_requested = Signal(str) # cmd: "play", "stop", "play_from"
    
    def __init__(self, app_state: AppState, parent=None):
        super().__init__(parent)
        self.state = app_state
        self.service = PlaylistService(app_state)
        self.search_matches = []
        self.curr_search_idx = -1
        self.playlist_view = None
        self.setup_ui()
        
    def setup_ui(self):
        """Initializes the layout with collapsible groups (QToolBox)."""
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
        self.btn_s_prev.setEnabled(False) # Default disabled
        self.btn_s_next = QPushButton("►"); self.btn_s_next.clicked.connect(self.search_next)
        self.btn_s_next.setEnabled(False) # Default disabled
        
        search_layout.addWidget(self.btn_s_prev); search_layout.addWidget(self.btn_s_next)
        p1_layout.addLayout(search_layout)
        
        p1_layout.addStretch()
        self.toolbox.addItem(page1, "Playback & Navigation")
        
        # --- Page 2: Chunk Editing ---
        page2 = QWidget()
        p2_layout = QGridLayout(page2)
        
        # Tools: Edit / Split / Mark / Delete
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
        
        # Failed Chunk Fixes
        btn_merge = QPushButton("Merge Failed Down")
        btn_merge.clicked.connect(self.merge_failed_down)
        
        btn_split_failed = QPushButton("Split All Failed")
        btn_split_failed.clicked.connect(self.split_all_failed)
        
        p3_layout.addWidget(btn_merge)
        p3_layout.addWidget(btn_split_failed)
        p3_layout.addWidget(QLabel("---"))
        
        # Cleaning Tools
        clean_layout = QHBoxLayout()
        btn_clean = QPushButton("Clean Special Chars")
        btn_clean.clicked.connect(self.clean_selected)
        # Filter Non-English (logic pending in Service but button ready)
        # btn_filter = QPushButton("Filter Non-English")
        
        clean_layout.addWidget(btn_clean)
        p3_layout.addLayout(clean_layout)
        p3_layout.addWidget(QLabel("---"))
        
        btn_regen = QPushButton("↻ Regenerate Marked")
        btn_regen.setStyleSheet("background-color: #D35400; color: white; font-weight: bold;")
        btn_regen.clicked.connect(self.regenerate_marked)
        
        p3_layout.addWidget(btn_regen)
        p3_layout.addStretch()
        
        self.toolbox.addItem(page3, "Batch Operations")
        
        layout.addWidget(self.toolbox)

    def set_playlist_reference(self, playlist_view):
        """Stores reference to playlist for selection fetching."""
        self.playlist_view = playlist_view

    def get_selected_indices(self):
        """Retrieves selected indices from the PlaylistView."""
        if hasattr(self, 'playlist_view') and self.playlist_view:
            return self.playlist_view.get_selected_indices()
        return []

    # --- Batch Actions ---
    def merge_failed_down(self):
        """Attempts to merge all failed chunks with their successors."""
        count = self.service.merge_failed_down()
        if count > 0:
            QMessageBox.information(self, "Success", f"Merged {count} failed chunks.")
            self.refresh_requested.emit()
        else:
            QMessageBox.information(self, "Info", "No failed chunks found to merge.")
            
    def split_all_failed(self):
        """Attempts to split all failed chunks using the text splitter."""
        count = self.service.split_all_failed()
        if count > 0:
            QMessageBox.information(self, "Success", f"Split {count} failed chunks.")
            self.refresh_requested.emit()
        else:
            QMessageBox.information(self, "Info", "No valid splittable failed chunks found.")

    def clean_selected(self):
        """Cleans special characters from selected items."""
        indices = self.get_selected_indices()
        if not indices:
             QMessageBox.information(self, "Info", "Please select items to clean.")
             return
             
        count = self.service.clean_special_chars_selected(indices)
        if count > 0:
            self.refresh_requested.emit()
            QMessageBox.information(self, "Success", f"Cleaned {count} items.")
        else:
            QMessageBox.information(self, "Info", "No special characters found in selection.")
        
    def regenerate_marked(self):
        """Trigger generation for marked items."""
        # Signal main window to start? Or just emit signal?
        QMessageBox.information(self, "Regenerate", "Batch regen logic pending Phase 5 wiring.")

    # --- Navigation Actions ---
    def move_item(self, direction):
        """Moves selected items up or down."""
        indices = self.get_selected_indices()
        if not indices:
            QMessageBox.information(self, "Info", "Select items in playlist first.")
            return
            
        new_indices = self.service.move_items(indices, direction)
        if new_indices != indices:
            self.refresh_requested.emit()
            # Restore selection (requires PlaylistView method to set selection)
            # self.playlist_view.set_selection(new_indices) # TODO: Implement set_selection

    def find_error(self, direction):
        """Finds next/prev failed item."""
        # Currently defaults to searching from 0.
        # Ideally should search from current selection.
        indices = self.get_selected_indices()
        start = indices[0] if indices else -1
        
        idx = self.service.find_next_status(start, direction, 'failed')
        if idx >= 0:
            QMessageBox.information(self, "Found", f"Found error at index {idx}. (Selection jump pending)")
        else:
             QMessageBox.information(self, "Info", "No errors found.")

    # --- Search ---
    def perform_search(self):
        """Executes search and updates navigation buttons."""
        query = self.search_input.text()
        self.search_matches = self.service.search(query)
        if self.search_matches:
            self.curr_search_idx = 0
            self.btn_s_prev.setEnabled(True) # Enable
            self.btn_s_next.setEnabled(True) # Enable
            self.search_next()
        else:
            self.btn_s_prev.setEnabled(False) # Disable
            self.btn_s_next.setEnabled(False) # Disable
            QMessageBox.information(self, "Search", "No matches found.")
            
    def search_next(self):
        """Jumps to next search match."""
        if not self.search_matches: return
        idx = self.search_matches[self.curr_search_idx]
        self.curr_search_idx = (self.curr_search_idx + 1) % len(self.search_matches)
        QMessageBox.information(self, "Search", f"Found at {idx}. (Jump not wired)")

    def search_prev(self):
        """Jumps to previous search match."""
        if not self.search_matches: return
        self.curr_search_idx = (self.curr_search_idx - 1) % len(self.search_matches)
        idx = self.search_matches[self.curr_search_idx]
        QMessageBox.information(self, "Search", f"Found at {idx}. (Jump not wired)")

    # --- Editing ---
    def edit_current(self):
        """Opens dialog to edit the text of the single selected item."""
        indices = self.get_selected_indices()
        if len(indices) != 1:
            QMessageBox.information(self, "Info", "Please select exactly one item to edit.")
            return
            
        idx = indices[0]
        item = self.service.get_selected_item(idx)
        if not item: return
        
        current_text = item.get('original_sentence', '')
        
        new_text, ok = QInputDialog.getMultiLineText(self, "Edit Text", "Content:", current_text)
        
        if ok and new_text != current_text:
            if self.service.edit_text(idx, new_text):
                self.refresh_requested.emit()
        
    def split_current(self):
        """Splits the selected chunk using the text splitter."""
        indices = self.get_selected_indices()
        if len(indices) != 1:
            QMessageBox.information(self, "Info", "Please select exactly one item to split.")
            return
            
        idx = indices[0]
        if self.service.split_chunk(idx):
            self.refresh_requested.emit()
        else:
            QMessageBox.information(self, "Info", "Could not split this chunk (too specific? or 1 sentence).")
        
    def mark_current(self):
        """Marks selected items for regeneration."""
        indices = self.get_selected_indices()
        for idx in indices:
            item = self.state.sentences[idx]
            item['marked'] = True
            item['tts_generated'] = 'no'
        if indices:
            self.refresh_requested.emit()

    def delete_current(self):
        """Deletes selected items after confirmation."""
        indices = self.get_selected_indices()
        if not indices: return
        
        if QMessageBox.question(self, "Confirm", f"Delete {len(indices)} items?") == QMessageBox.Yes:
            self.service.delete_items(indices)
            self.refresh_requested.emit()
        
    def insert_text(self):
        """Inserts a new text block at the selected position."""
        idx = 0
        indices = self.get_selected_indices()
        if indices: idx = indices[0]
        
        text, ok = QInputDialog.getText(self, "Insert Text", "New Text:")
        if ok and text:
            self.service.insert_item(idx, text)
            self.refresh_requested.emit()
        
    def insert_pause(self):
        """Inserts a pause block at the selected position."""
        idx = 0
        indices = self.get_selected_indices()
        if indices: idx = indices[0]
        
        dur, ok = QInputDialog.getInt(self, "Insert Pause", "Duration (ms):", 500, 100, 10000)
        if ok:
            self.service.insert_item(idx, "--- PAUSE ---", is_pause=True, duration=dur)
            self.refresh_requested.emit()
        
    def insert_chapter(self):
        """Inserts a chapter marker at the selected position."""
        idx = 0
        indices = self.get_selected_indices()
        if indices: idx = indices[0]
        
        name, ok = QInputDialog.getText(self, "Insert Chapter", "Chapter Name:")
        if ok and name:
            self.service.insert_item(idx, name, is_chapter=True)
            self.refresh_requested.emit()
