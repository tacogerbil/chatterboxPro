from PySide6.QtWidgets import (QWidget, QVBoxLayout, QPushButton, QHBoxLayout, QGridLayout, 
                               QLineEdit, QLabel, QMessageBox, QInputDialog, QCheckBox)
from PySide6.QtCore import Qt, Signal
import logging
import os
from ui.components.collapsible_frame import CollapsibleFrame
from core.services.playlist_service import PlaylistService
from core.services.generation_service import GenerationService

class ControlsView(QWidget):
    """
    The "Editing Panel" comprising Playback, Editing, and Batch operations.
    Ported from legacy `ui/controls_frame.py`.
    """
    structure_changed = Signal() # Emitted when chapters are added/converted

    def __init__(self, services, playlist_view, parent=None):
        super().__init__(parent)
        self.services = services # Dict {playlist: PlaylistService, generation: GenerationService}
        self.playlist = playlist_view # Reference to list view for selection
        self.generation_service = services.get('generation')
        self.generation_service = services.get('generation')
        self.playlist_service = services.get('playlist')
        self.audio_service = services.get('audio') # Injected by MainWindow
        
        self.setup_ui()
        
    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # --- Group 1: Playback & Navigation ---
        self.playback_group = CollapsibleFrame("Playback & Navigation", start_open=True)
        main_layout.addWidget(self.playback_group)
        self._setup_playback(self.playback_group)

        # --- Group 2: Chunk Editing & Status ---
        self.edit_group = CollapsibleFrame("Chunk Editing & Status", start_open=True)
        main_layout.addWidget(self.edit_group)
        self._setup_editing(self.edit_group)

        # --- Group 3: Batch Fix & Regeneration ---
        self.batch_group = CollapsibleFrame("Batch Fix & Regeneration", start_open=False)
        main_layout.addWidget(self.batch_group)
        self._setup_batch(self.batch_group)
        
        main_layout.addStretch()

    def _setup_playback(self, group):
        layout = QGridLayout()
        
        # Row 0: Play Controls
        btn_play = QPushButton("▶ Play"); btn_play.clicked.connect(self._play_selected)
        btn_stop = QPushButton("■ Stop"); btn_stop.clicked.connect(self._stop_playback)
        btn_play_from = QPushButton("▶ Play From"); btn_play_from.clicked.connect(self._play_from)
        
        layout.addWidget(btn_play, 0, 0)
        layout.addWidget(btn_stop, 0, 1)
        layout.addWidget(btn_play_from, 0, 2, 1, 2)
        
        # Row 1: Nav
        btn_up = QPushButton("▲ Move Up"); btn_up.clicked.connect(lambda: self._move_items(-1))
        btn_down = QPushButton("▼ Move Down"); btn_down.clicked.connect(lambda: self._move_items(1))
        btn_prev_err = QPushButton("◄ Prev Error"); btn_prev_err.clicked.connect(lambda: self._nav_error(-1))
        btn_next_err = QPushButton("Next Error ►"); btn_next_err.clicked.connect(lambda: self._nav_error(1))
        
        layout.addWidget(btn_up, 1, 0)
        layout.addWidget(btn_down, 1, 1)
        layout.addWidget(btn_prev_err, 1, 2)
        layout.addWidget(btn_next_err, 1, 3)
        
        # Row 2: Search
        search_widget = QWidget()
        s_layout = QHBoxLayout(search_widget); s_layout.setContentsMargins(0,0,0,0)
        s_layout.addWidget(QLabel("🔍"))
        s_layout.addWidget(QLabel("🔍"))
        self.search_edit = QLineEdit(); self.search_edit.setPlaceholderText("Search text...")
        # MCCC: Force visible size and style to prevent red-box/rendering artifacts
        self.search_edit.setMinimumWidth(150)
        self.search_edit.setProperty("class", "search-box")
        self.search_edit.returnPressed.connect(self._search)
        s_layout.addWidget(self.search_edit)
        
        btn_s_prev = QPushButton("◄"); btn_s_prev.setFixedWidth(30); btn_s_prev.clicked.connect(self._search_prev)
        btn_s_next = QPushButton("►"); btn_s_next.setFixedWidth(30); btn_s_next.clicked.connect(self._search_next)
        s_layout.addWidget(btn_s_prev)
        s_layout.addWidget(btn_s_next)
        
        layout.addWidget(search_widget, 2, 0, 1, 4)
        
        group.add_layout(layout)

    def _setup_editing(self, group):
        layout = QGridLayout()
        
        # Row 0: Editing & Insertions
        btn_edit = QPushButton("✎ Edit"); btn_edit.clicked.connect(self._edit_text)
        btn_edit.setProperty("class", "action")

        btn_ins_txt = QPushButton("➕ Text"); btn_ins_txt.clicked.connect(self._insert_text)
        btn_ins_txt.setProperty("class", "action")

        btn_ins_pause = QPushButton("⏸ Pause"); btn_ins_pause.clicked.connect(self._insert_pause)
        btn_ins_pause.setProperty("class", "action")
        
        btn_ins_chap = QPushButton("📑 New Chap"); btn_ins_chap.clicked.connect(self._insert_chapter)
        btn_ins_chap.setProperty("class", "action")

        btn_conv_chap = QPushButton("➡️ Conv Chap"); btn_conv_chap.setToolTip("Convert Selection to Chapter")
        btn_conv_chap.clicked.connect(self._convert_to_chapter)
        btn_conv_chap.setProperty("class", "action")
        
        layout.addWidget(btn_edit, 0, 0)
        layout.addWidget(btn_ins_txt, 0, 1)
        layout.addWidget(btn_ins_pause, 0, 2)
        layout.addWidget(btn_ins_chap, 0, 3)
        layout.addWidget(btn_conv_chap, 0, 4)
        
        # Row 1: Markers, Status & Split
        btn_mark = QPushButton("M Mark"); btn_mark.clicked.connect(self._mark_current)
        btn_mark.setProperty("class", "action")

        # Moved Split Here per User Request
        btn_split = QPushButton("➗ Split"); btn_split.clicked.connect(self._split_chunk)
        btn_split.setProperty("class", "action")
        
        btn_pass = QPushButton("✓ Passed"); btn_pass.clicked.connect(self._mark_passed)
        btn_pass.setProperty("class", "success")
        
        btn_reset = QPushButton("🔄 Reset"); btn_reset.clicked.connect(self._reset_gen)
        btn_reset.setProperty("class", "warning")
        
        btn_del = QPushButton("❌ Delete"); btn_del.clicked.connect(self._delete_items)
        btn_del.setProperty("class", "danger")
        
        layout.addWidget(btn_mark, 1, 0)
        layout.addWidget(btn_split, 1, 1)
        layout.addWidget(btn_pass, 1, 2)
        layout.addWidget(btn_reset, 1, 3)
        layout.addWidget(btn_del, 1, 4)
        
        group.add_layout(layout)

    def _setup_batch(self, group):
        layout = QGridLayout()
        
        # Row 0
        self.chk_fix_all = QCheckBox("Apply Batch Fix to ALL Failed Chunks")
        layout.addWidget(self.chk_fix_all, 0, 0, 1, 3)
        
        # Row 1
        btn_merge = QPushButton("Merge Failed Down"); btn_merge.clicked.connect(self._merge_failed)
        btn_clean = QPushButton("Clean Special Chars"); btn_clean.clicked.connect(self._clean_chars)
        btn_filter = QPushButton("Filter Non-English"); btn_filter.clicked.connect(self._filter_english)
        
        layout.addWidget(btn_merge, 1, 0)
        layout.addWidget(btn_clean, 1, 1)
        layout.addWidget(btn_filter, 1, 2)
        
        # Row 2
        btn_split_all = QPushButton("Split All Failed"); btn_split_all.clicked.connect(self._split_all_failed)
        layout.addWidget(btn_split_all, 2, 0, 1, 3)
        
        # Row 3
        btn_regen = QPushButton("↻ Regenerate Marked"); btn_regen.clicked.connect(self._regen_marked)
        btn_regen.setStyleSheet("background-color: #A40000; color: white;")
        
        self.chk_auto_loop = QCheckBox("Auto-loop")
        self.chk_reassemble = QCheckBox("Re-Assemble after")
        
        layout.addWidget(btn_regen, 3, 0, 1, 2)
        layout.addWidget(self.chk_auto_loop, 3, 2)
        layout.addWidget(self.chk_reassemble, 4, 0, 1, 3)
        
        group.add_layout(layout)
        
    # --- Actions ---
    
    def _play_selected(self):
        idx = self._get_selected_index()
        if idx == -1: return
        
        item = self.playlist_service.get_selected_item(idx)
        print(f"DEBUG: Play request for Item {idx}", flush=True) # Debug
        
        if not item: return

        # 1. Try saved path
        path = item.get('audio_path')
        print(f"DEBUG: Saved audio_path: {path}", flush=True) # Debug
        
        if not path:
             # 2. Try constructing default path (fallback)
             # Check for both "audio_{uuid}.wav" (New) and "sentence_{uuid}.wav" (Legacy)
             uuid_str = item.get('uuid')
             base_dir = os.path.join(os.getcwd(), "output", "wavs") # Or "Output_Pro/Session/..."?
             # Better: Use saved session path if available?
             # For now, check standard output names relative to CWD
             
             candidates = [
                 os.path.join(base_dir, f"audio_{uuid_str}.wav"),
                 os.path.join(base_dir, f"sentence_{uuid_str}.wav"),
                 # Also try finding it in the session specific folder if possible, but path *should* be saved.
             ]
             
             for c in candidates:
                 if os.path.exists(c):
                     path = c
                     print(f"DEBUG: Found fallback audio at: {path}", flush=True)
                     break
             
             if not path:
                  print(f"DEBUG: Fallback search failed. Checked: {candidates}", flush=True)

        if not path or not os.path.exists(path):
            # MCCC: Path Resolution Fallback
            # The app might be running from a subdir (e.g. execution/chatterboxPro), 
            # while the path is relative to Project Root (Outputs_Pro).
            # We search up to 3 levels up.
            found = False
            cwd = os.getcwd()
            print(f"DEBUG: Path Direct Check Failed. CWD: {cwd}", flush=True)
            
            for i in range(4): # Check ., .., ../.., ../../..
                prefix = "../" * i
                candidate = os.path.abspath(os.path.join(cwd, prefix, path))
                if os.path.exists(candidate):
                    path = candidate
                    found = True
                    print(f"DEBUG: Found file at parent level {i}: {path}", flush=True)
                    break
            
            if not found:
                logging.warning(f"Audio file not found: {path}")
                print(f"DEBUG: File NOT FOUND at {path} (Checked parents)", flush=True) # Debug
                QMessageBox.warning(self, "Playback Error", f"File not found:\n{path}\n\nCWD: {cwd}")
                return
            
        # Ensure absolute path for QUrl compatibility (MCCC: Explicit Resolution)
        abs_path = os.path.abspath(path)
        print(f"DEBUG: Playing file (Absolute): {abs_path}", flush=True) # Debug
        
        if self.audio_service:
            self.audio_service.play_file(abs_path)
        else:
            QMessageBox.warning(self, "Error", "Audio Service not connected.")

    def _stop_playback(self):
        if self.audio_service:
            self.audio_service.stop()

    def _play_from(self):
        pass # To be wired

    def _get_selected_index(self):
        indices = self.playlist.get_selected_indices()
        return indices[0] if indices else -1

    def _get_selected_indices(self):
        return self.playlist.get_selected_indices()

    def _refresh(self):
        self.playlist.refresh()

    def _edit_text(self):
        try:
            print("DEBUG: Edit Button Clicked!", flush=True)
            idx = self._get_selected_index()
            print(f"DEBUG: Selected Index: {idx}", flush=True)
            
            if idx == -1: 
                logging.warning("Edit: No index selected.")
                print("DEBUG: Index is -1", flush=True)
                return
            
            item = self.playlist_service.get_selected_item(idx)
            if not item:
                logging.warning(f"Edit: Item at {idx} is None.")
                print("DEBUG: Item is None", flush=True)
                return

            print(f"DEBUG: Item Found. is_pause={item.get('is_pause')}", flush=True)
            
            # Check if Pause - Use Duration Editor
            if item.get('is_pause'):
                print("DEBUG: Attempting QInputDialog for Pause...", flush=True)
                old_dur = item.get('duration', 500)
                # Correct arguments: parent, title, label, value, min, max, step
                new_dur, ok = QInputDialog.getInt(self, "Edit Pause", "Duration (ms):", old_dur, 100, 10000, 50)
                print(f"DEBUG: QInputDialog returned: ok={ok}, val={new_dur}", flush=True)
                if ok and new_dur != old_dur:
                    logging.info(f"Updating pause duration to {new_dur}")
                    if self.playlist_service.edit_pause(idx, new_dur):
                        self._refresh()
                        # Force playlist repaint
                        self.playlist.list_view.viewport().update()
                return

            # Normal Text Editing
            print("DEBUG: Attempting EditorDialog for Text...", flush=True)
            old_text = item.get('original_sentence', '')
            
            from ui.dialogs.editor_dialog import EditorDialog
            dlg = EditorDialog(old_text, self)
            
            if dlg.exec():
                new_text = dlg.result_text
                if new_text != old_text:
                    if self.playlist_service.edit_text(idx, new_text):
                        self._refresh()
                        # Force playlist repaint
                        self.playlist.list_view.viewport().update()
                        print("DEBUG: Text updated and View refreshed.", flush=True)
                    else:
                        print("DEBUG: edit_text returned False (no change?)", flush=True)
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"DEBUG CRITICAL ERROR: {e}", flush=True)
            QMessageBox.critical(self, "Edit Error", f"An error occurred:\n{e}")

    def _split_chunk(self):
        idx = self._get_selected_index()
        if idx == -1: return
        if self.playlist_service.split_chunk(idx):
             self._refresh()
             self.structure_changed.emit()
        else:
            QMessageBox.warning(self, "Split Failed", "Could not split chunk (maybe too short?)")

    def _insert_text(self):
        idx = self._get_selected_index()
        text, ok = QInputDialog.getText(self, "Insert Text", "Enter text:")
        if ok and text:
            self.playlist_service.insert_item(idx, text)
            self._refresh()
            self.structure_changed.emit()

    def _insert_pause(self):
        idx = self._get_selected_index()
        # Fix: positional args (parent, title, label, value, min, max, step)
        dur, ok = QInputDialog.getInt(self, "Insert Pause", "Duration (ms):", 500, 100, 10000, 50)
        if ok:
             self.playlist_service.insert_item(idx, "[PAUSE]", is_pause=True, duration=dur)
             self._refresh()
             self.structure_changed.emit()

    def _insert_chapter(self):
        idx = self._get_selected_index()
        title, ok = QInputDialog.getText(self, "Insert Chapter", "Chapter Title:", text="Chapter X")
        if ok and title:
             self.playlist_service.insert_item(idx, title, is_chapter=True)
             self._refresh()
             self.structure_changed.emit()

    def _convert_to_chapter(self):
        idx = self._get_selected_index()
        if idx == -1: return
        
        if self.playlist_service.convert_to_chapter(idx):
            self._refresh()
            self.structure_changed.emit()
        else:
            QMessageBox.information(self, "Info", "Already a chapter or invalid selection.")

    def _mark_current(self):
        indices = self._get_selected_indices()
        if not indices: return
        for i in indices:
            item = self.playlist_service.get_selected_item(i)
            item['marked'] = True
        self._refresh()

    def _mark_passed(self):
        indices = self._get_selected_indices()
        if not indices: return
        for i in indices:
            item = self.playlist_service.get_selected_item(i)
            item['tts_generated'] = 'yes' # Force pass
            item['marked'] = False
        self._refresh()

    def _reset_gen(self):
        indices = self._get_selected_indices()
        for i in indices:
            self.playlist_service.reset_item(i)
        self._refresh()

    def _delete_items(self):
        indices = self._get_selected_indices()
        if not indices: return
        if QMessageBox.question(self, "Confirm", f"Delete {len(indices)} items?") == QMessageBox.Yes:
            self.playlist_service.delete_items(indices)
            self._refresh()
            self.structure_changed.emit()

    def _move_items(self, direction):
        indices = self._get_selected_indices()
        if self.playlist_service.move_items(indices, direction):
            self._refresh()
            self.structure_changed.emit()
            # Restore selection (tricky due to re-indexing, but service returns new indices)
            # Todo: update selection

    def _nav_error(self, direction):
        idx = self._get_selected_index()
        next_idx = self.playlist_service.find_next_status(idx, direction, 'failed')
        if next_idx != -1:
            self.playlist.jump_to_row(next_idx)

    def _search(self):
        q = self.search_edit.text()
        self.matches = self.playlist_service.search(q)
        self.match_idx = 0
        self._show_search_match()
        
    def _search_prev(self):
        if not hasattr(self, 'matches') or not self.matches: return
        self.match_idx = (self.match_idx - 1) % len(self.matches)
        self._show_search_match()
        
    def _search_next(self):
        if not hasattr(self, 'matches') or not self.matches: return
        self.match_idx = (self.match_idx + 1) % len(self.matches)
        self._show_search_match()
        
    def _show_search_match(self):
        if not self.matches: return
        target = self.matches[self.match_idx]
        self.playlist.jump_to_row(target)

    def _merge_failed(self):
        count = self.playlist_service.merge_failed_down()
        if count: 
            self._refresh()
            self.structure_changed.emit()
            QMessageBox.information(self, "Merged", f"Merged {count} chunks.")
        
    def _split_all_failed(self):
        count = self.playlist_service.split_all_failed()
        if count: 
            self._refresh()
            self.structure_changed.emit()
            QMessageBox.information(self, "Split", f"Split {count} chunks.")
        
    def _clean_chars(self):
        indices = self._get_selected_indices()
        c = self.playlist_service.clean_special_chars_selected(indices)
        if c: self._refresh()

    def _filter_english(self):
        indices = self._get_selected_indices()
        c = self.playlist_service.filter_non_english_in_selected(indices)
        if c: self._refresh()

    def _regen_marked(self):
        # Call generation service for marked items
        # Logic: find ALL marked items
        indices = [i for i, item in enumerate(self.playlist_service.state.sentences) if item.get('marked')]
        if not indices: QMessageBox.information(self, "Info", "No marked items."); return
        
        if self.generation_service:
            self.generation_service.start_generation(indices)
