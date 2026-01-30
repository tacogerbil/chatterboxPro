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
        
        # Get Status & Mark
        status = index.data(PlaylistModel.StatusRole)
        is_marked = index.data(PlaylistModel.MarkedRole)
        
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
        
        # Connect selection and data changes to stats update
        self.list_view.selectionModel().selectionChanged.connect(self.update_stats)
        self.model.dataChanged.connect(self.on_data_changed)
        left_layout.addWidget(self.list_view)
        
        # Initial Theme Apply
        self.update_theme(self.app_state.theme_name)
        
        top_layout.addWidget(left_container, stretch=3)
        
        # Right Side: Stats Panel
        
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
        
    def on_data_changed(self, top_left, bottom_right, roles=None):
        """Called when model data changes. Updates stats if selected item changed."""
        selected = self.get_selected_indices()
        if not selected: return
        
        # Check if change intersection with selection
        # Simplified: just update if anything changes (cheap operation)
        self.update_stats()

    def update_stats(self):
        indices = self.get_selected_indices()
        
        if not indices or len(indices) > 1:
            self.lbl_status.setText("--")
            self.lbl_seed.setText("--")
            self.lbl_asr.setText("--")
            return
            
        full_data = self.model.get_item(indices[0])
        if not full_data: return
        
        if full_data.get('is_pause'):
             # Pause Item Handling (MCCC: Distinct UX)
             duration = full_data.get('duration', self.app_state.settings.silence_duration)
             self.lbl_status.setText(f"PAUSE ({duration}ms)")
             self.lbl_seed.setText("--")
             self.lbl_asr.setText("--")
             return

        self.lbl_status.setText(str(full_data.get('tts_generated', 'no')))
        self.lbl_seed.setText(str(full_data.get('generation_seed') or full_data.get('seed', '--')))
        
        # Format ASR
        asr = full_data.get('similarity_ratio') or full_data.get('asr_match')
        if asr is not None:
             self.lbl_asr.setText(f"{float(asr)*100:.2f}%")
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

    def update_theme(self, theme_name: str) -> None:
        """
        Updates the list palette based on whether the theme is dark or light.
        """
        is_dark = "light" not in theme_name.lower()
        
        p = self.list_view.palette()
        if is_dark:
            # Dark Theme Palette
            p.setColor(QPalette.Base, QColor("#2b2b2b"))
            p.setColor(QPalette.AlternateBase, QColor("#252525"))
            p.setColor(QPalette.Text, QColor("#eeeeee"))
        else:
            # Light Theme Palette
            p.setColor(QPalette.Base, QColor("#F5F5F5"))
            p.setColor(QPalette.AlternateBase, QColor("#EBEBEB"))
            p.setColor(QPalette.Text, QColor("#000000"))
            
        self.list_view.setPalette(p)

