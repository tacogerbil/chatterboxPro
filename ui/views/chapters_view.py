from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListView, 
    QPushButton, QLabel, QMessageBox, QCheckBox, QStyledItemDelegate, QStyle, QApplication, QStyleOptionViewItem
)
from PySide6.QtGui import QColor, QBrush, QPalette
from PySide6.QtCore import Qt, Signal, QModelIndex, QRect, QEvent, QAbstractListModel
from typing import Optional, List, Dict, Any
from core.state import AppState
from core.services.generation_service import GenerationService
from core.services.chapter_service import ChapterService

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
        check_rect = style.subElementRect(QStyle.SE_ItemViewItemCheckIndicator, option, option.widget)
        # Fallback if style returns empty rect (Common in some custom styles if they don't see the flag)
        if check_rect.width() <= 0 or check_rect.height() <= 0:
             check_rect = QRect(rect.left() + 5, rect.top() + (rect.height() - 20)//2, 20, 20)

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
            # Check if click was in button rect
            rect = option.rect
            button_width = 80
            button_rect = QRect(rect.right() - button_width - 5, rect.top() + 2, button_width, rect.height() - 4)
            
            if button_rect.contains(event.pos()):
                real_idx = model.get_chapter_index(index.row())
                self.jump_clicked.emit(real_idx)
                return True
                
        return super().editorEvent(event, model, option, index)

class ChaptersView(QWidget):
    jump_requested = Signal(int)

    def __init__(self, app_state: AppState, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.app_state = app_state
        self.logic = ChapterService()
        self.model = ChapterModel(app_state)
        # Type hint for generation service (injected later)
        self.gen_service: Optional[GenerationService] = None
        
        self.setup_ui()

    def setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        
        # Header: Title + Refresh
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("Detected Chapters (Double-click to Jump)"))
        header_layout.addStretch()
        
        refresh_btn = QPushButton("↻ Refresh")
        refresh_btn.setToolTip("Rescan source text for chapters")
        refresh_btn.clicked.connect(self.model.refresh)
        header_layout.addWidget(refresh_btn)
        
        layout.addLayout(header_layout)
        
        # List View
        self.list_view = QListView()
        self.list_view.setModel(self.model)
        self.list_view.setAlternatingRowColors(True)
        
        self.list_view.setAlternatingRowColors(True)
        # Palette set in update_theme() called at end of setup
        
        self.list_view.setSelectionMode(QListView.ExtendedSelection)
        
        self.list_view.setSelectionMode(QListView.ExtendedSelection)
        self.list_view.doubleClicked.connect(self.on_double_click)
        
        # Delegate
        self.delegate = ChapterDelegate()
        self.delegate.jump_clicked.connect(self.jump_requested)
        self.list_view.setItemDelegate(self.delegate)
        self.list_view.setMouseTracking(True) 
        
        layout.addWidget(self.list_view)
        
        # Initial Theme Apply
        self.update_theme(self.app_state.theme_name)

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
        self.list_view.update()
        
        # MCCC Audit: Restore "No Chapters Detected" Placeholder
        self.empty_label = QLabel("No chapters detected.\n\nUse 'Insert Chapter' in the Editing panel\nor re-process text.")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setStyleSheet("color: gray; font-size: 14px; padding: 20px;")
        layout.addWidget(self.empty_label)
        
        # Listen to model changes to toggle view
        self.model.modelReset.connect(self._update_empty_state)
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
        
        # New Feature: Check Highlighted
        check_high = QPushButton("Check Highlighted")
        check_high.setToolTip("Check the boxes for all currently highlighted rows")
        check_high.clicked.connect(self.check_highlighted)
        footer_layout.addWidget(check_high)
        
        footer_layout.addStretch()
        
        # Auto-loop Checkbox
        self.auto_loop_chk = QCheckBox("Auto-loop")
        self.auto_loop_chk.setToolTip("Automatically regenerate until success (Warning: Infinite Loop possible)")
        self.auto_loop_chk.setChecked(self.app_state.auto_regen_main)
        self.auto_loop_chk.stateChanged.connect(
            lambda s: setattr(self.app_state, 'auto_regen_main', s == Qt.Checked or s == 2)
        )
        footer_layout.addWidget(self.auto_loop_chk)
        
        # Generate Selected button
        self.gen_btn = QPushButton("Generate Selected")
        self.gen_btn.setStyleSheet("background-color: #D35400; color: white; font-weight: bold; padding: 5px;")
        self.gen_btn.clicked.connect(self.generate_selected)
        footer_layout.addWidget(self.gen_btn)
        
        layout.addLayout(footer_layout)

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
        
