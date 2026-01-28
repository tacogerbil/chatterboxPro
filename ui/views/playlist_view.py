from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QListView, 
                               QLabel, QStyle, QStyledItemDelegate, QGroupBox, QFormLayout)
from PySide6.QtGui import QColor, QBrush, QPalette
from PySide6.QtCore import Qt
from core.state import AppState
from core.models.playlist_model import PlaylistModel

class PlaylistDelegate(QStyledItemDelegate):
    """
    Renders playlist items with color coding based on status/type.
    MCCC Compliance: Uses initStyleOption to modify background, 
    letting super().paint() handle text rendering for CSS compatibility.
    """
    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        
        # Get Status
        status = index.data(PlaylistModel.StatusRole)
        
        # Apply Status Colors (Modify background brush)
        if not (option.state & QStyle.State_Selected):
            if status == "failed":
                option.backgroundBrush = QBrush(QColor("#543030")) # Darker Red
            elif status == "success":
                option.backgroundBrush = QBrush(QColor("#2E4B2E")) # Darker Green


class PlaylistView(QWidget):
    def __init__(self, app_state: AppState, parent=None):
        super().__init__(parent)
        self.app_state = app_state
        self.model = PlaylistModel(app_state)
        self.setup_ui()
        
    def setup_ui(self):
        # Main Layout: Vertical (Split: List/Stats on Top, Controls on Bottom)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Top Section: List + Stats (Horizontal)
        top_widget = QWidget()
        top_layout = QHBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        
        # Left Side: List (No controls here, moved to ControlsView)
        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0,0,0,0)
        
        left_layout.addWidget(QLabel("Generation Output (Playlist)"))
        
        self.list_view = QListView()
        self.list_view.setModel(self.model)
        self.list_view.setItemDelegate(PlaylistDelegate()) 
        self.list_view.setSelectionMode(QListView.ExtendedSelection)
        self.list_view.setAlternatingRowColors(True)
        
        # User Requested: Light Gray + Slightly Darker + Black Text
        p = self.list_view.palette()
        p.setColor(QPalette.Base, QColor("#F5F5F5"))
        p.setColor(QPalette.AlternateBase, QColor("#EBEBEB"))
        p.setColor(QPalette.Text, QColor("#000000"))
        self.list_view.setPalette(p)

        self.list_view.selectionModel().selectionChanged.connect(self.update_stats)
        left_layout.addWidget(self.list_view)
        
        top_layout.addWidget(left_container, stretch=3)
        
        # Right Side: Stats Panel
        stats_group = QGroupBox("Chunk Stats")
        stats_group.setMaximumWidth(220)
        stats_layout = QFormLayout(stats_group)
        
        self.lbl_status = QLabel("--")
        self.lbl_seed = QLabel("--")
        self.lbl_asr = QLabel("--")
        
        stats_layout.addRow("Status:", self.lbl_status)
        stats_layout.addRow("Seed:", self.lbl_seed)
        stats_layout.addRow("ASR Match:", self.lbl_asr)
        
        top_layout.addWidget(stats_group, stretch=1)
        
        main_layout.addWidget(top_widget, stretch=1)
        
        # Bottom Slot for ControlsView (Will be added by set_controls_view or public method)
        # We leave it open or add if passed in init?
        # Better: provide method `add_controls_widget(widget)`

    def add_controls_view(self, controls_widget):
        self.layout().addWidget(controls_widget)
        
    def refresh(self):
        self.model.refresh()
        
    def update_stats(self):
        indexes = self.list_view.selectedIndexes()
        if indexes:
            # Stats for single selection
            idx = indexes[0]
            row = idx.row()
            item = self.app_state.sentences[row]
            
            self.lbl_status.setText(item.get('tts_generated', 'pending'))
            self.lbl_seed.setText(str(item.get('generation_seed', '--')))
            ratio = item.get('similarity_ratio')
            self.lbl_asr.setText(f"{ratio:.2%}" if ratio else "N/A")
        else:
            self.lbl_asr.setText("--")
            
    def get_selected_indices(self) -> list[int]:
        """Returns a list of selected sentence indices (ints)."""
        indexes = self.list_view.selectionModel().selectedIndexes()
        # Filter for column 0 to avoid duplicates if multiple columns exist (though listview usually has 1)
        valid_indices = sorted([idx.row() for idx in indexes if idx.column() == 0])
        return valid_indices

    def jump_to_row(self, row_index: int) -> None:
        """MCCC: Handles navigation request from other components."""
        idx = self.model.index(row_index, 0)
        if idx.isValid():
            self.list_view.clearSelection()
            self.list_view.setCurrentIndex(idx)
            self.list_view.scrollTo(idx, QListView.PositionAtCenter)
            # Ensure stats update
            self.update_stats()
