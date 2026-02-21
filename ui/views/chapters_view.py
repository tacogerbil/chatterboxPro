from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListView, 
    QPushButton, QLabel, QMessageBox, QCheckBox, QStyledItemDelegate, QStyle, QApplication, QStyleOptionViewItem
)
from PySide6.QtGui import QColor, QBrush, QPalette
from PySide6.QtCore import Qt, Signal, Slot, QModelIndex, QRect, QEvent, QAbstractListModel
from typing import Optional, List, Dict, Any
from core.state import AppState
from core.services.generation_service import GenerationService
from core.services.chapter_service import ChapterService
from ui.components.progress_widget import ProgressWidget

class ChapterModel(QAbstractListModel):
    def __init__(self, app_state: AppState):
        super().__init__()
        self.app_state = app_state
        self.logic = ChapterService()
        self._chapters: List[Dict[str, Any]] = []
        self._checked_state: Dict[int, bool] = {} # Map original_idx -> is_checked
        self.refresh()

    def refresh(self):
        self.beginResetModel()
        # Detect chapters from current sentences
        self._chapters = self.logic.detect_chapters(self.app_state.sentences)
        # Reset checked state on refresh? Or try to preserve? For safety, reset.
        self._checked_state = {}
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._chapters)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._chapters)):
            return None
        
        chapter = self._chapters[index.row()]
        
        if role == Qt.DisplayRole:
            return f"{chapter['title']} (Sentences {chapter['start_idx']+1}-{chapter['end_idx']+1})"
            
        if role == Qt.CheckStateRole:
            # We map row index to check state.
            # Ideally we map absolute chapter index, but row index is fine if we clear on refresh.
            return Qt.Checked if self._checked_state.get(index.row(), False) else Qt.Unchecked
            
        return None

    def setData(self, index, value, role=Qt.EditRole):
        if not index.isValid() or role != Qt.CheckStateRole:
            return False
            
        self._checked_state[index.row()] = (value == Qt.Checked)
        self.dataChanged.emit(index, index, [role])
        return True

    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable

    def get_selected_indices(self) -> List[int]:
        """Returns the list of INDICES in the chapter list that are checked."""
        return [row for row, checked in self._checked_state.items() if checked]

    def get_chapter_index(self, row: int) -> int:
        """Returns the start sentence index for the chapter at the given row."""
        if 0 <= row < len(self._chapters):
            return self._chapters[row]['start_idx']
        return -1

class ChapterDelegate(QStyledItemDelegate):
    jump_clicked = Signal(int)

    def _get_check_rect(self, option, widget):
        style = widget.style() if widget else QApplication.style()
        check_rect = style.subElementRect(QStyle.SE_ItemViewItemCheckIndicator, option, widget)
        # Fallback if style returns empty rect or too small
        if check_rect.width() <= 0 or check_rect.height() <= 0:
             check_rect = QRect(option.rect.left() + 5, option.rect.top() + (option.rect.height() - 20)//2, 20, 20)
        return check_rect

    def paint(self, painter, option, index):
        # 1. Init Style
        self.initStyleOption(option, index)
        painter.save()
        
        style = option.widget.style() if option.widget else QApplication.style()
        
        # 2. Draw Background (Selection)
        style.drawPrimitive(QStyle.PE_PanelItemViewItem, option, painter, option.widget)
        
        # 3. Calculate Rects
        rect = option.rect
        button_width = 80
        # Button Rect (Right aligned)
        button_rect = QRect(rect.right() - button_width - 5, rect.top() + 2, button_width, rect.height() - 4)
        
        # Checkbox Rect (Left aligned Standard)
        check_rect = self._get_check_rect(option, option.widget)

        # Text Rect (Between Check and Button)
        text_rect = style.subElementRect(QStyle.SE_ItemViewItemText, option, option.widget)
        # If check rect was manually calculated, text rect logic needs update too
        if text_rect.left() < check_rect.right():
             text_rect.setLeft(check_rect.right() + 5)
        
        text_rect.setRight(button_rect.left() - 10)
        
        # 4. Draw Checkbox (Explicitly - ALWAYS)
        check_opt = QStyleOptionViewItem(option)
        check_opt.rect = check_rect
        check_opt.state = check_opt.state & ~QStyle.State_HasFocus
        
        if option.checkState == Qt.Checked:
            check_opt.state |= QStyle.State_On
        else:
            check_opt.state |= QStyle.State_Off
            
        style.drawPrimitive(QStyle.PE_IndicatorItemViewItemCheck, check_opt, painter, option.widget)
            
        # 5. Draw Text
        text = option.text
        # Handle truncation if needed
        # Style usually handles eliding if we pass the rect
        if option.state & QStyle.State_Selected:
            painter.setPen(option.palette.highlightedText().color())
        else:
            painter.setPen(option.palette.text().color())
            
        # Draw aligned text
        # AlignLeft | AlignVCenter is standard
        style.drawItemText(painter, text_rect, Qt.AlignLeft | Qt.AlignVCenter, option.palette, 
                           True, text, QPalette.Text)

        # 6. Draw "SELECT" Button
        # Background
        btn_color = QColor("#D35400")
        painter.setBrush(QBrush(btn_color))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(button_rect, 4, 4)
        
        # Text
        painter.setPen(Qt.white)
        painter.drawText(button_rect, Qt.AlignCenter, "SELECT")
        
        painter.restore()

    def editorEvent(self, event, model, option, index):
        # Handle Clicks
        if event.type() == QEvent.MouseButtonRelease:
            pos = event.pos()
            
            # Check for SELECT Button
            button_width = 80
            rect = option.rect
            button_rect = QRect(rect.right() - button_width - 5, rect.top() + 2, button_width, rect.height() - 4)
            
            if button_rect.contains(pos):
                real_idx = model.get_chapter_index(index.row())
                self.jump_clicked.emit(real_idx)
                return True
                
            # Check for Checkbox
            check_rect = self._get_check_rect(option, option.widget)
            if check_rect.contains(pos):
                # Toggle Check State
                current_state = model.data(index, Qt.CheckStateRole)
                new_state = Qt.Checked if current_state == Qt.Unchecked else Qt.Unchecked
                model.setData(index, new_state, Qt.CheckStateRole)
                return True
                
        return super().editorEvent(event, model, option, index)

class ChaptersView(QWidget):
    jump_requested = Signal(int)
    structure_changed = Signal()  # Emitted when chapters are committed

    def __init__(self, app_state: AppState, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.app_state = app_state
        self.logic = ChapterService()
        self.model = ChapterModel(app_state)
        self.gen_service: Optional[GenerationService] = None
        self.playlist_service = None  # Injected later via set_playlist_service()

        self.setup_ui()

    def setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Header row: word search | Mark | Conv Chap | Refresh
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("Detected Chapters (Double-click to Jump)"))
        header_layout.addStretch()

        # ── Word-search ──────────────────────────────────────────────
        self.chap_word_edit = QLineEdit()
        self.chap_word_edit.setPlaceholderText("Chapter word...")
        self.chap_word_edit.setFixedWidth(130)
        self.chap_word_edit.setToolTip(
            "Type a word and click Mark to highlight all matching\n"
            "sentences as chapter candidates (amber in playlist)."
        )
        self.chap_word_edit.returnPressed.connect(self._mark_word_matches)

        btn_mark_word = QPushButton("Mark")
        btn_mark_word.setToolTip("Mark all sentences containing this word as chapter candidates.")
        btn_mark_word.setStyleSheet("background-color: #B8860B; color: white; font-weight: bold;")
        btn_mark_word.clicked.connect(self._mark_word_matches)

        btn_conv_chap = QPushButton("Conv Chap")
        btn_conv_chap.setToolTip("Convert all marked chapter candidates into proper chapter headings.")
        btn_conv_chap.setStyleSheet("background-color: #1A6B47; color: white; font-weight: bold;")
        btn_conv_chap.clicked.connect(self._convert_chap_marked)

        header_layout.addWidget(self.chap_word_edit)
        header_layout.addWidget(btn_mark_word)
        header_layout.addWidget(btn_conv_chap)
        # ─────────────────────────────────────────────────────────────

        # Auto-loop Checkbox (Moved to Header)
        s = self.app_state.settings
        self.auto_loop_chk = QCheckBox("Auto-loop")
        self.auto_loop_chk.setToolTip("Reflects the 'Auto-loop' setting from Config → ASR Validation.\nChange the setting there.")
        self.auto_loop_chk.setChecked(getattr(self.app_state, 'auto_regen_main', False))
        self.auto_loop_chk.setEnabled(False)  # Read-only reflection; canonical setting is in Config tab
        
        self.lbl_auto_loop_info = QLabel(f"(Retries: {s.max_attempts} | ASR: {int(s.asr_threshold*100)}%)")
        self.lbl_auto_loop_info.setStyleSheet("color: gray; font-size: 8pt; margin-right: 10px;")

        # Initial Status Check

        refresh_btn = QPushButton("↻ Refresh")
        refresh_btn.setToolTip("Rescan source text for chapters")
        refresh_btn.clicked.connect(self.model.refresh)
        # Also refresh GPU status on clicking refresh (why not?)
        refresh_btn.clicked.connect(self.refresh_gpu_status)
        header_layout.addWidget(refresh_btn)
        
        layout.addLayout(header_layout)
        
        # List View
        self.list_view = QListView()
        self.list_view.setModel(self.model)
        self.list_view.setAlternatingRowColors(True)
        self.list_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_view.customContextMenuRequested.connect(self._show_context_menu)
        

        # Palette set in update_theme() called at end of setup
        
        self.list_view.setSelectionMode(QListView.ExtendedSelection)
        

        self.list_view.doubleClicked.connect(self.on_double_click)
        
        # Delegate
        self.delegate = ChapterDelegate()
        self.delegate.jump_clicked.connect(self.jump_requested)
        self.list_view.setItemDelegate(self.delegate)
        self.list_view.setMouseTracking(True) 
        
        layout.addWidget(self.list_view, stretch=1)
        
        # Initial Theme Apply

        self.update_theme(self.app_state.theme_name)
        
        # MCCC Audit: Restore "No Chapters Detected" Placeholder
        self.empty_label = QLabel("No chapters detected.\n\nUse 'Insert Chapter' in the Editing panel\nor re-process text.")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setStyleSheet("color: gray; font-size: 14px; padding: 20px;")
        layout.addWidget(self.empty_label)
        
        # Listen to model changes to toggle view
        self.model.modelReset.connect(self._update_empty_state)
        self._update_empty_state()
        
        # Listen to model changes to toggle view
        self.model.modelReset.connect(self._update_empty_state)
        self._update_empty_state()
        
        # Continuation of setup_ui...
        self.model.rowsInserted.connect(self._update_empty_state)
        self.model.rowsRemoved.connect(self._update_empty_state)

        # Footer: Selection + Actions
        footer_layout = QHBoxLayout()
        
        sel_all = QPushButton("Select All")
        sel_all.clicked.connect(self.select_all)
        footer_layout.addWidget(sel_all)
        
        sel_none = QPushButton("Deselect All")
        sel_none.clicked.connect(self.deselect_all)
        footer_layout.addWidget(sel_none)
        
        # New Feature: Check Highlighted
        check_high = QPushButton("Check Highlighted")
        check_high.setToolTip("Check the boxes for all currently highlighted rows")
        check_high.clicked.connect(self.check_highlighted)
        footer_layout.addWidget(check_high)
        
        footer_layout.addStretch()
        
        # Generate Selected button (Restored Initialization)
        self.gen_btn = QPushButton("Generate Selected")
        self.gen_btn.setStyleSheet("background-color: #D35400; color: white; font-weight: bold; padding: 5px;")
        self.gen_btn.clicked.connect(self.generate_selected)
        
        # Stacked Layout: Auto-loop (Top) + GPU Status (Bottom)
        stats_layout = QVBoxLayout()
        stats_layout.setSpacing(2)
        
        # Row 1: Auto-loop (Align Right)
        auto_loop_layout = QHBoxLayout()
        auto_loop_layout.setAlignment(Qt.AlignRight)
        auto_loop_layout.addWidget(self.auto_loop_chk)
        auto_loop_layout.addWidget(self.lbl_auto_loop_info)
        stats_layout.addLayout(auto_loop_layout)
        
        # Row 2: GPU Status (Align Right)
        self.lbl_gpu_status = QLabel("")
        self.lbl_gpu_status.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.lbl_gpu_status.setTextFormat(Qt.RichText) 
        self.lbl_gpu_status.setStyleSheet("color: #555; font-size: 10pt;")
        stats_layout.addWidget(self.lbl_gpu_status)
        
        footer_layout.addLayout(stats_layout)
        
        # Spacer
        footer_layout.addSpacing(10)
        footer_layout.addWidget(self.gen_btn)
        
        # Stop Button
        self.stop_btn = QPushButton("🛑 Stop")
        self.stop_btn.setToolTip("Stop Generation")
        self.stop_btn.setFixedSize(110, 30) # Increased width to prevent cutoff
        self.stop_btn.setStyleSheet("background-color: #A93226; color: white; font-weight: bold; border-radius: 4px;")
        self.stop_btn.clicked.connect(self.stop_generation)
        footer_layout.addWidget(self.stop_btn)
        
        layout.addLayout(footer_layout)
        
        # MCCC: Progress Tracking Widget
        self.progress_widget = ProgressWidget()
        self.progress_widget.setVisible(False)  # Hidden until generation starts
        layout.addWidget(self.progress_widget)
        
        # Initial Refresh (Must be after UI init)
        self.refresh_gpu_status()

    def showEvent(self, event) -> None:
        """MCCC: Refresh status when tab becomes visible."""
        self.refresh_gpu_status()
        super().showEvent(event)

    def update_theme(self, theme_name: str) -> None:
        """
        Updates the list palette based on whether the theme is dark or light.
        MCCC: Isolates visual logic.
        """
        is_dark = "light" not in theme_name.lower()
        
        p = self.list_view.palette()
        if is_dark:
            # Dark Theme Palette
            p.setColor(QPalette.Base, QColor("#2b2b2b"))       # Dark Gray
            p.setColor(QPalette.AlternateBase, QColor("#252525")) # Subtle darker
            p.setColor(QPalette.Text, QColor("#eeeeee"))       # White Text
        else:
            # Light Theme Palette
            p.setColor(QPalette.Base, QColor("#F5F5F5"))       # Light Gray
            p.setColor(QPalette.AlternateBase, QColor("#EBEBEB")) # Subtle darker
            p.setColor(QPalette.Text, QColor("#000000"))       # Black Text
            
        self.list_view.setPalette(p)

    def refresh_values(self) -> None:
        """Updates UI based on state changes."""
        s = self.app_state.settings
        if hasattr(self, 'lbl_auto_loop_info'):
            self.lbl_auto_loop_info.setText(f"(Retries: {s.max_attempts} | ASR: {int(s.asr_threshold*100)}%)")
        if hasattr(self, 'auto_loop_chk'):
            # Block signals while syncing to avoid any unintended write
            self.auto_loop_chk.blockSignals(True)
            self.auto_loop_chk.setChecked(getattr(self.app_state, 'auto_regen_main', False))
            self.auto_loop_chk.blockSignals(False)
            

    def select_all(self) -> None:
        for i in range(self.model.rowCount()):
            idx = self.model.index(i, 0)
            self.model.setData(idx, Qt.Checked, Qt.CheckStateRole)

    def deselect_all(self) -> None:
        for i in range(self.model.rowCount()):
            idx = self.model.index(i, 0)
            self.model.setData(idx, Qt.Unchecked, Qt.CheckStateRole)

    def check_highlighted(self) -> None:
        """Checks the checkboxes for all currently highlighted rows in the list."""
        selected_indexes = self.list_view.selectionModel().selectedIndexes()
        if not selected_indexes:
            QMessageBox.information(self, "Info", "No rows highlighted. Click to highlight rows first.")
            return
            
        count = 0
        for index in selected_indexes:
            # Check the box
            self.model.setData(index, Qt.Checked, Qt.CheckStateRole)
            count += 1

    def set_generation_service(self, gen_service: GenerationService) -> None:
        self.gen_service = gen_service
        gen_service.progress_update.connect(self.progress_widget.update_progress)
        gen_service.stats_updated.connect(self.progress_widget.update_stats)
        gen_service.eta_updated.connect(self.progress_widget.update_eta)
        gen_service.started.connect(lambda: self.progress_widget.setVisible(True))
        gen_service.finished.connect(lambda: self.progress_widget.setVisible(False))
        gen_service.stopped.connect(lambda: self.progress_widget.setVisible(False))
        if hasattr(gen_service, 'items_updated'):
             gen_service.items_updated.connect(self.on_items_updated)

    def set_playlist_service(self, playlist_service) -> None:
        """Inject PlaylistService so Conv Chap can call convert_to_chapter()."""
        self.playlist_service = playlist_service

    # ── Chapter Marking ───────────────────────────────────────────────────

    def _mark_word_matches(self) -> None:
        """Find all sentences containing the search word and add to chap_marked."""
        word = self.chap_word_edit.text().strip()
        if not word:
            return
        word_lower = word.lower()
        added = 0
        for i, sentence in enumerate(self.app_state.sentences):
            text = sentence.get('original_sentence', '').lower()
            if word_lower in text:
                self.app_state.chap_marked.add(i)
                added += 1
        # Refresh playlist so amber highlight appears
        from PySide6.QtWidgets import QApplication
        for widget in QApplication.topLevelWidgets():
            pv = widget.findChild(type(None).__class__, 'playlist_view')
        # Simpler: emit a signal to whoever holds the playlist
        self._refresh_playlist()
        print(f"[ChaptersView] Marked {added} sentences containing '{word}'.")

    def _convert_chap_marked(self) -> None:
        """Convert all chap_marked sentence indices into chapter headings."""
        if not self.app_state.chap_marked:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, "Nothing Marked",
                "No chapter candidates marked.\nUse the word search + Mark button first.")
            return
        if not self.playlist_service:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Error", "Playlist service not connected.")
            return

        # Process in reverse order so indices stay valid as items are replaced
        indices = sorted(self.app_state.chap_marked, reverse=True)
        converted = 0
        for idx in indices:
            if self.playlist_service.convert_to_chapter(idx):
                converted += 1

        self.app_state.chap_marked.clear()
        self._refresh_playlist()
        self.model.refresh()
        self.structure_changed.emit()
        print(f"[ChaptersView] Converted {converted} candidates to chapters.")

    def _unmark_chap_item(self, row: int) -> None:
        """Remove a single sentence index from chap_marked."""
        # Map chapter-list row → sentence start index
        sent_idx = self.model.get_chapter_index(row)
        if sent_idx >= 0:
            self.app_state.chap_marked.discard(sent_idx)
        else:
            # Fallback: remove by row if chapter mapping failed
            self.app_state.chap_marked.discard(row)
        self._refresh_playlist()

    def _show_context_menu(self, pos) -> None:
        """Right-click context menu on the chapter list."""
        from PySide6.QtWidgets import QMenu
        idx = self.list_view.indexAt(pos)
        if not idx.isValid():
            return
        menu = QMenu(self)
        unmark_action = menu.addAction("Unmark")
        action = menu.exec(self.list_view.viewport().mapToGlobal(pos))
        if action == unmark_action:
            self._unmark_chap_item(idx.row())

    def _refresh_playlist(self) -> None:
        """Asks the parent window to refresh the playlist model (chap_marked changed)."""
        # Best-effort: find PlaylistView in app window hierarchy
        from PySide6.QtWidgets import QApplication
        from core.models.playlist_model import PlaylistModel
        app = QApplication.instance()
        if app:
            for widget in app.topLevelWidgets():
                for child in widget.findChildren(type(PlaylistModel)):
                    child.refresh()
                    return

    # ─────────────────────────────────────────────────────────────────────

    @Slot(list)
    def on_items_updated(self, indices: List[int]) -> None:
        """
        Handles batched updates from GenerationService.
        Emits dataChanged for the range of affected rows.
        """
        if not indices: return
        # Since ChaptersView shows CHAPTERS, not sentences, we typically don't update individual rows 
        # based on sentence updates unless we track status per chapter.
        # But if we did, we would map sentence index -> chapter row.
        # For now, just ensuring this slot exists prevents crashes if connected.
        pass

    def generate_selected(self) -> None:
        # Merge Checkbox selection + Highlighting selection
        checked_indices = self.model.get_selected_indices() # From checkboxes
        
        # Get highlighted rows
        highlighted_indices = [idx.row() for idx in self.list_view.selectionModel().selectedIndexes()]
        
        # Merge unique
        final_selection = sorted(list(set(checked_indices + highlighted_indices)))
        
        if not final_selection:
            QMessageBox.information(self, "Info", "No chapters selected (checkbox or highlight).")
            return
            
        full_indices = self.logic.get_indices_for_chapters(
            self.app_state.sentences,
            self.model._chapters, # Pass the cached chapter list
            final_selection
        )
        
        if not self.gen_service:
            QMessageBox.warning(self, "Error", "Generation Service not connected.")
            return
            
        # Trigger generation
        self.gen_service.start_generation(full_indices)

    def stop_generation(self) -> None:
        if self.gen_service:
            self.gen_service.request_stop()
        else:
            QMessageBox.warning(self, "Error", "Generation Service not connected.")
        
    def on_double_click(self, index: QModelIndex) -> None:
        """Handle double click to jump to chapter start."""
        if not index.isValid(): return
        
        # Determine real index from model
        real_idx = self.model.get_chapter_index(index.row())
        if real_idx >= 0:
            self.jump_requested.emit(real_idx)
            
    def _update_empty_state(self, *args) -> None:
        """MCCC: Toggles between ListView and EmptyLabel based on content."""
        has_items = self.model.rowCount() > 0
        self.list_view.setVisible(has_items)
        self.empty_label.setVisible(not has_items)
        if hasattr(self, 'gen_btn'):
            self.gen_btn.setEnabled(has_items)

    def refresh_gpu_status(self):
        """Updates footer indicator with active GPU names."""
        caps = self.app_state.system_capabilities
        gpu_names = caps.get('gpu_names', [])
        targets = self.app_state.settings.target_gpus
        
        # Parse targets
        active_names = []
        if "cuda:" in targets:
            try:
                parts = targets.split(',')
                for p in parts:
                    idx = int(p.split(':')[1])
                    if idx < len(gpu_names):
                        active_names.append(gpu_names[idx])
            except: 
                pass
                
        if active_names:
            if len(active_names) > 1:
                # Stacked Names
                joined = "<br>".join([f"{n} ●" for n in active_names])
                text = f"Active GPUs:<br>{joined}"
                self.lbl_gpu_status.setText(text)
                self.lbl_gpu_status.setStyleSheet("color: #00FF00; font-weight: bold;") # Bright Green
            else:
                text = f"Active GPU:<br>{active_names[0]} ●"
                self.lbl_gpu_status.setText(text)
                self.lbl_gpu_status.setStyleSheet("color: #27AE60; font-weight: bold;") # Normal Green
            
            self.lbl_gpu_status.setVisible(True)
        else:
            self.lbl_gpu_status.setVisible(False)
