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
        
        # Row 1: Move + Success / Error Navigation (restored as original)
        btn_up = QPushButton("▲ Move Up"); btn_up.clicked.connect(lambda: self._move_items(-1))
        btn_down = QPushButton("▼ Move Down"); btn_down.clicked.connect(lambda: self._move_items(1))
        
        btn_prev_success = QPushButton("◄ Prev Success")
        btn_prev_success.setStyleSheet("background-color: #90EE90; color: black; font-weight: bold;")
        btn_prev_success.clicked.connect(lambda: self._nav_success(-1))

        btn_next_success = QPushButton("Next Success ►")
        btn_next_success.setStyleSheet("background-color: #90EE90; color: black; font-weight: bold;")
        btn_next_success.clicked.connect(lambda: self._nav_success(1))

        btn_prev_err = QPushButton("◄ Prev Error")
        btn_prev_err.setStyleSheet("background-color: #FFB6C1; color: black; font-weight: bold;")
        btn_prev_err.clicked.connect(lambda: self._nav_error(-1))

        btn_next_err = QPushButton("Next Error ►")
        btn_next_err.setStyleSheet("background-color: #FFB6C1; color: black; font-weight: bold;")
        btn_next_err.clicked.connect(lambda: self._nav_error(1))

        layout.addWidget(btn_up, 1, 0)
        layout.addWidget(btn_down, 1, 1)
        layout.addWidget(btn_prev_success, 1, 2)
        layout.addWidget(btn_next_success, 1, 3)
        layout.addWidget(btn_prev_err, 1, 4)
        layout.addWidget(btn_next_err, 1, 5)

        # Row 2: Search (moved up)
        search_widget = QWidget()
        s_layout = QHBoxLayout(search_widget); s_layout.setContentsMargins(0,0,0,0)
        s_layout.addWidget(QLabel("🔍"))

        self.search_edit = QLineEdit(); self.search_edit.setPlaceholderText("Search text...")
        self.search_edit.setMinimumWidth(150)
        self.search_edit.setProperty("class", "search-box")
        self.search_edit.returnPressed.connect(self._search)
        s_layout.addWidget(self.search_edit)
        
        btn_s_prev = QPushButton("◄")
        btn_s_prev.setFixedWidth(40)
        btn_s_prev.setStyleSheet("padding: 2px; font-size: 16px; font-weight: bold;")
        btn_s_prev.clicked.connect(self._search_prev)
        
        btn_s_next = QPushButton("►")
        btn_s_next.setFixedWidth(40)
        btn_s_next.setStyleSheet("padding: 2px; font-size: 16px; font-weight: bold;")
        btn_s_next.clicked.connect(self._search_next)
        
        s_layout.addWidget(btn_s_prev)
        s_layout.addWidget(btn_s_next)
        
        layout.addWidget(search_widget, 2, 0, 1, 4)

        # Row 3: Replace
        replace_widget = QWidget()
        r_layout = QHBoxLayout(replace_widget); r_layout.setContentsMargins(0,0,0,0)
        r_layout.addWidget(QLabel("📝"))
        
        self.replace_edit = QLineEdit(); self.replace_edit.setPlaceholderText("Replace with...")
        self.replace_edit.setMinimumWidth(150)
        self.replace_edit.setProperty("class", "search-box")
        r_layout.addWidget(self.replace_edit)
        
        btn_replace = QPushButton("Replace")
        btn_replace.clicked.connect(self._replace_current)
        btn_replace.setToolTip("Replace text in the currently selected row and advance to next match.")
        
        btn_replace_all = QPushButton("Replace All")
        btn_replace_all.clicked.connect(self._replace_all)
        btn_replace_all.setToolTip("Replace text in all chunks across the entire session.")
        
        r_layout.addWidget(btn_replace)
        r_layout.addWidget(btn_replace_all)
        
        layout.addWidget(replace_widget, 3, 0, 1, 5)

        
        group.add_layout(layout)

    def _setup_editing(self, group):
        layout = QGridLayout()
        
        # Row 0: Editing & Insertions
        # Buttons: Edit, +Text, Pause, AutoPause, +Chap, Conv
        
        btn_edit = QPushButton("✎ Edit"); btn_edit.clicked.connect(self._edit_text)
        btn_edit.setProperty("class", "action")
        btn_edit.setToolTip("Edit the text or properties of the selected item.")

        btn_ins_txt = QPushButton("➕ Text"); btn_ins_txt.clicked.connect(self._insert_text)
        btn_ins_txt.setProperty("class", "action")
        btn_ins_txt.setToolTip("Insert a new text chunk below the selection.")

        btn_ins_pause = QPushButton("⏸ Pause"); btn_ins_pause.clicked.connect(self._insert_pause)
        btn_ins_pause.setProperty("class", "action")
        btn_ins_pause.setToolTip("Insert a silent pause block below the selection.")
        
        # NEW: Auto Pause
        btn_auto_pause = QPushButton("🤖 Auto Pause"); btn_auto_pause.clicked.connect(self._auto_pause_action)
        btn_auto_pause.setProperty("class", "action")
        btn_auto_pause.setToolTip("Automatically wrap all chapters with pauses.")
        
        btn_ins_chap = QPushButton("📑 New Chap"); btn_ins_chap.clicked.connect(self._insert_chapter)
        btn_ins_chap.setProperty("class", "action")
        btn_ins_chap.setToolTip("Insert a new Chapter Heading below the selection.")

        btn_conv_chap = QPushButton("➡️ Conv Chap"); btn_conv_chap.clicked.connect(self._convert_to_chapter)
        btn_conv_chap.setProperty("class", "action")
        btn_conv_chap.setToolTip("Convert the selected item into a Chapter Heading.")
        
        # Layout 6 columns
        layout.addWidget(btn_edit, 0, 0)
        layout.addWidget(btn_ins_txt, 0, 1)
        layout.addWidget(btn_ins_pause, 0, 2)
        layout.addWidget(btn_auto_pause, 0, 3)
        layout.addWidget(btn_ins_chap, 0, 4)
        layout.addWidget(btn_conv_chap, 0, 5)
        
        # Row 1: Markers, Status & Split
        btn_mark = QPushButton("⚑ Flag"); btn_mark.clicked.connect(self._mark_current)
        btn_mark.setProperty("class", "action")
        btn_mark.setToolTip("Toggle flag on selected item(s) — flagged items can be regenerated in batch.")
        
        btn_split = QPushButton("➗ Split"); btn_split.clicked.connect(self._split_chunk)
        btn_split.setProperty("class", "action")
        btn_split.setToolTip("Split the current text chunk into smaller sentences.")
        
        btn_merge_sel = QPushButton("🔗 Merge\nSelected"); btn_merge_sel.clicked.connect(self._merge_selected)
        btn_merge_sel.setProperty("class", "action")
        btn_merge_sel.setToolTip("Merge multiple selected contiguous chunks into one.")
        
        btn_pass = QPushButton("✓ Passed"); btn_pass.clicked.connect(self._mark_passed)
        btn_pass.setProperty("class", "success")
        btn_pass.setToolTip("Manually mark item as Passed (Green).")
        
        btn_reset = QPushButton("🔄 Reset"); btn_reset.clicked.connect(self._reset_gen)
        btn_reset.setProperty("class", "warning")
        btn_reset.setToolTip("Reset generation status and clear all audio/stats.")
        
        btn_del = QPushButton("❌ Delete"); btn_del.clicked.connect(self._delete_items)
        btn_del.setProperty("class", "danger")
        btn_del.setToolTip("Delete selected items.")
        
        # 6 columns to balance
        layout.addWidget(btn_mark, 1, 0)
        layout.addWidget(btn_split, 1, 1)
        layout.addWidget(btn_merge_sel, 1, 2)
        layout.addWidget(btn_pass, 1, 3)
        layout.addWidget(btn_reset, 1, 4)
        layout.addWidget(btn_del, 1, 5)
        
        group.add_layout(layout)

    def _setup_batch(self, group):
        layout = QGridLayout()
        
        # Row 0
        self.chk_fix_all = QCheckBox("Apply Batch Fix to ALL Failed Chunks")
        self.chk_fix_all.setToolTip("If checked, fixes apply to all failed chunks globally.")
        layout.addWidget(self.chk_fix_all, 0, 0, 1, 4)
        
        # Row 1: Merges & Cleaning
        # [Reflow Marked] [Merge Failed] [Clean] [Filter]
        
        btn_reflow = QPushButton("Merge Marked (Smart)"); btn_reflow.clicked.connect(self._reflow_marked)
        btn_reflow.setToolTip("Smart Merge: Combines marked items and re-chunks them to fit size limits.")
        
        btn_merge = QPushButton("Merge Failed Down"); btn_merge.clicked.connect(self._merge_failed)
        btn_merge.setToolTip("Merges failed chunks into the chunk below them.")
        
        btn_clean = QPushButton("Clean Special Chars"); btn_clean.clicked.connect(self._clean_chars)
        btn_clean.setToolTip("Removes aggressive special characters from selection.")
        
        btn_filter = QPushButton("Filter Non-English"); btn_filter.clicked.connect(self._filter_english)
        btn_filter.setToolTip("Removes non-English words from selection.")
        
        layout.addWidget(btn_reflow, 1, 0)
        layout.addWidget(btn_merge, 1, 1)
        layout.addWidget(btn_clean, 1, 2)
        layout.addWidget(btn_filter, 1, 3)
        
        btn_split_marked = QPushButton("Split Marked"); btn_split_marked.clicked.connect(self._split_marked)
        btn_split_marked.setToolTip("Splits all marked chunks using the sentence splitter.")
        
        btn_split_all_sent = QPushButton("Split Failed (Sentence)"); btn_split_all_sent.clicked.connect(self._split_all_failed)
        btn_split_all_sent.setToolTip("Splits all failed chunks out into individual sentences.")
        
        btn_split_all_half = QPushButton("Split Failed (Half Chunk)"); btn_split_all_half.clicked.connect(self._split_all_failed_half)
        btn_split_all_half.setToolTip("Splits all failed chunks exactly in half.")
        
        layout.addWidget(btn_split_marked, 2, 0, 1, 2)
        layout.addWidget(btn_split_all_sent, 2, 2, 1, 1)
        layout.addWidget(btn_split_all_half, 2, 3, 1, 1)
        
        # Row 2.5: Re-chunk Session (NEW)
        btn_rechunk = QPushButton("🔄 Re-chunk Session")
        btn_rechunk.clicked.connect(self._rechunk_session)
        btn_rechunk.setToolTip("Re-split all text using improved chunking (preserves chapters/pauses)")
        layout.addWidget(btn_rechunk, 3, 0, 1, 4)
        
        # Row 4: Regen & Loops
        btn_regen = QPushButton("↻ Regenerate Marked"); btn_regen.clicked.connect(self._regen_marked)
        btn_regen.setStyleSheet("background-color: #A40000; color: white;")
        btn_regen.setToolTip("Start generation for all items marked for regeneration.")
        
        self.chk_auto_loop = QCheckBox("Auto-loop")
        self.chk_auto_loop.setToolTip("Continue regenerating failed chunks until all pass.")
        
        self.chk_reassemble = QCheckBox("Re-Assemble after")
        self.chk_reassemble.setToolTip("Automatically assemble audiobook after generation completes.")
        
        layout.addWidget(btn_regen, 4, 0, 1, 2)
        layout.addWidget(self.chk_auto_loop, 4, 2)
        layout.addWidget(self.chk_reassemble, 5, 0, 1, 3)
        
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
            
        # Ensure absolute path for QUrl compatibility (
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
        idx = self._get_selected_index()
        if idx == -1: 
            QMessageBox.information(self, "Info", "Select a starting point.")
            return

        # Build Queue
        queue = []
        sentences = self.playlist_service.state.sentences
        
        # Iterate from selected index to end
        for i in range(idx, len(sentences)):
            item = sentences[i]
            
            # Handle Pauses
            if item.get('is_pause'):
                duration = item.get('duration', 0)
                if duration > 0:
                    queue.append({'type': 'pause', 'duration': duration})
                continue
                
            # Handle Audio
            path = item.get('audio_path')
            
            # If path missing, try fallback
            if not path:
                uuid_str = item.get('uuid')
                base_dir = os.path.join(os.getcwd(), "output", "wavs")
                candidates = [
                    os.path.join(base_dir, f"audio_{uuid_str}.wav"), 
                    os.path.join(base_dir, f"sentence_{uuid_str}.wav")
                ]
                for c in candidates:
                    if os.path.exists(c):
                        path = c
                        break
            
            if path and os.path.exists(path):
                queue.append({'type': 'file', 'path': os.path.abspath(path)})
        
        if not queue:
            QMessageBox.warning(self, "Playback", "No audio or pauses found starting from selection.")
            return
            
        logging.info(f"Controls: Play Queue with {len(queue)} items.")
        if self.audio_service:
            self.audio_service.play_queue(queue)
        else:
             QMessageBox.warning(self, "Error", "Audio Service disconnected.")

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
            
            # Pause items get the dedicated quick-insert dialog
            if item.get('is_pause'):
                from ui.dialogs.pause_dialog import PauseDialog
                old_dur = item.get('duration', 500)
                new_dur = PauseDialog.get_duration(initial_ms=old_dur, parent=self)
                if new_dur is not None and new_dur != old_dur:
                    logging.info(f"Updating pause duration to {new_dur}")
                    if self.playlist_service.edit_pause(idx, new_dur):
                        self._refresh()
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
            
    def _merge_selected(self):
        indices = self._get_selected_indices()
        if not indices or len(indices) < 2:
            QMessageBox.information(self, "Merge", "Please select at least two contiguous chunks to merge.")
            return
            
        count = self.playlist_service.merge_selected(indices)
        if count:
            self._refresh()
            self.structure_changed.emit()
            QMessageBox.information(self, "Merged", f"Merged {len(indices)} chunks into one.")
        else:
            QMessageBox.warning(self, "Merge Failed", "Could not merge chunks. Make sure they are contiguous and contain text (not just pauses).")

    def _insert_text(self):
        idx = self._get_selected_index()
        text, ok = QInputDialog.getText(self, "Insert Text", "Enter text:")
        if ok and text:
            self.playlist_service.insert_item(idx, text)
            self._refresh()
            self.structure_changed.emit()

    def _insert_pause(self):
        idx = self._get_selected_index()
        from ui.dialogs.pause_dialog import PauseDialog
        dur = PauseDialog.get_duration(initial_ms=500, parent=self)
        if dur is not None:
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
        self.playlist_service.toggle_selection_mark(indices)
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
            # Restore selection (tricky due to re-indexing, service would need to return new indices)

    def _nav_error(self, direction):
        idx = self._get_selected_index()
        next_idx = self.playlist_service.find_next_status(idx, direction, 'failed')
        if next_idx != -1:
            self.playlist.jump_to_row(next_idx)

    def _nav_success(self, direction):
        """Navigate to next/previous successful chunk."""
        idx = self._get_selected_index()
        next_idx = self.playlist_service.find_next_status(idx, direction, 'yes')
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
        if not hasattr(self, 'matches') or not self.matches: return
        
        target_uuid = self.matches[self.match_idx]
        
        current_idx = -1
        for i, s in enumerate(self.playlist_service.state.sentences):
            if s.get('uuid') == target_uuid:
                current_idx = i
                break
                
        if current_idx != -1:
            self.playlist.jump_to_row(current_idx)
        else:
            # Fallback if sentence was deleted — remove from matches and try next
            self.matches.pop(self.match_idx)
            if self.matches:
                self.match_idx = self.match_idx % len(self.matches)
                self._show_search_match()
            else:
                QMessageBox.information(self, "Search", "No more matches found (items deleted).")

    def _replace_current(self):
        """Replaces text in the selected row and auto-advances to the next search match."""
        search_term = self.search_edit.text()
        replace_term = self.replace_edit.text()
        
        if not search_term: return
        
        idx = self._get_selected_index()
        if idx == -1: return

        if self.playlist_service.replace_current(idx, search_term, replace_term):
            self._refresh()
            self.playlist.list_view.viewport().update()
            
        # Try to automatically advance to next match
        self._search_next()

    def _replace_all(self):
        """Replaces text in all chunks across the entire session."""
        search_term = self.search_edit.text()
        replace_term = self.replace_edit.text()
        
        if not search_term: return
        
        reply = QMessageBox.question(self, "Replace All", 
                                   f"Are you sure you want to replace all occurrences of '{search_term}' with '{replace_term}'?",
                                   QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                                   
        if reply == QMessageBox.Yes:
            count = self.playlist_service.replace_all(search_term, replace_term)
            if count > 0:
                self._refresh()
                self.playlist.list_view.viewport().update()
                
                # Re-run search to clear out the matches (since they are now gone)
                self._search()
                
                QMessageBox.information(self, "Replace All", f"Successfully updated {count} chunk(s).")
            else:
                QMessageBox.information(self, "Replace All", f"No exact matches for '{search_term}' were found.")

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
            QMessageBox.information(self, "Split", f"Split {count} chunks by sentence.")

    def _split_all_failed_half(self):
        count = self.playlist_service.split_all_failed_half()
        if count: 
            self._refresh()
            self.structure_changed.emit()
            QMessageBox.information(self, "Split", f"Split {count} chunks in half.")
        
    def _clean_chars(self):
        indices = self._get_selected_indices()
        c = self.playlist_service.clean_special_chars_selected(indices)
        if c: self._refresh()

    def _filter_english(self):
        indices = self._get_selected_indices()
        c = self.playlist_service.filter_non_english_in_selected(indices)
        if c: self._refresh()

    def _regen_marked(self):
        """Generate all marked items. If Auto-loop is checked, each chunk retries harder in-place."""
        indices = [
            i for i, item in enumerate(self.playlist_service.state.sentences)
            if item.get('marked') and not item.get('is_pause')
        ]
        if not indices:
            QMessageBox.information(self, "Info", "No marked items."); return
        
        if not self.generation_service:
            QMessageBox.warning(self, "Error", "Generation service not connected."); return
        
        # When Auto-loop is checked, multiply per-chunk max_attempts so each chunk
        # retries aggressively in-place rather than cycling entire batches.
        auto_loop = self.chk_auto_loop.isChecked()
        if auto_loop:
            original_attempts = self.playlist_service.state.settings.max_attempts
            LOOP_MULTIPLIER = 6  # e.g. 3 attempts → 18 per chunk
            self.generation_service.set_attempts_boost(original_attempts)  # Let service restore it on finish
            self.playlist_service.state.settings.max_attempts = original_attempts * LOOP_MULTIPLIER
            logging.info(f"Auto-loop ON: max_attempts boosted {original_attempts} → "
                         f"{self.playlist_service.state.settings.max_attempts} per chunk")
        
        self.generation_service.start_generation(indices)

    def _auto_pause_action(self):
        """Wraps all chapters with configured buffer pause."""
        s = self.playlist_service.state.settings
        before_ms = s.chapter_buffer_before_ms
        after_ms = s.chapter_buffer_after_ms
        
        stats = self.playlist_service.apply_auto_pause_buffers(before_ms, after_ms)
        self._refresh()
        self.structure_changed.emit()
        
        # Show Log/Results properly
        logging.info(f"Auto-Pause Complete: Processed {stats['processed']} chapters. Added {stats['added']} pauses. Skipped {stats['skipped']}.")
        QMessageBox.information(self, "Auto-Pause Complete", 
                                f"Wrapped {stats['processed']} chapters.\n"
                                f"Buffers: Before={before_ms}ms, After={after_ms}ms.\n\n"
                                f"Added: {stats['added']} pauses.\n"
                                f"Skipped: {stats['skipped']} (already present).")

    def _reflow_marked(self):
        """Smart Reflow of Marked Items."""
        count = self.playlist_service.reflow_marked_items()
        if count:
            self._refresh()
            self.structure_changed.emit()
            QMessageBox.information(self, "Reflow Complete", f"Reflowed {count} marked items into optimized chunks.")
        else:
             QMessageBox.information(self, "Info", "No marked items found to reflow.")

    def _split_marked(self):
        """Split All Marked Items."""
        count = self.playlist_service.split_all_marked()
        if count:
            self._refresh()
            self.structure_changed.emit()
            QMessageBox.information(self, "Split Complete", f"Split {count} marked items.")
        else:
             QMessageBox.information(self, "Info", "No marked items found or no split needed.")


    def _rechunk_session(self):
        '''Re-chunk current session using improved chunking algorithm.'''
        reply = QMessageBox.question(
            self, "Re-chunk Session?",
            "This will re-split all text using improved chunking.\n\n"
            "✅ Preserves: Chapters, Pauses\n"
            "⚠️ Warning: Generated audio will need regeneration\n\n"
            "Continue?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            from utils.text_processor import TextPreprocessor
            processor = TextPreprocessor()
            
            # Access state through playlist_service
            state = self.playlist_service.state
            old_count = len(state.sentences)
            
            # Rechunk
            new_sentences = processor.rechunk_current_session(state.sentences)
            state.sentences = new_sentences
            
            # Refresh UI
            self._refresh()
            self.structure_changed.emit()
            
            QMessageBox.information(
                self, "Re-chunk Complete", 
                f"Re-chunked session:\n"
                f"Before: {old_count} items\n"
                f"After: {len(new_sentences)} items"
            )
