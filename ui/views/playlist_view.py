from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QListView, 
                               QPushButton, QLabel, QStyle, QStyledItemDelegate, QGroupBox, QFormLayout)
from PySide6.QtGui import QColor, QFont, QPen, QBrush
from PySide6.QtCore import Qt, QModelIndex
from core.state import AppState
from core.models.playlist_model import PlaylistModel

class PlaylistDelegate(QStyledItemDelegate):
    """
    Renders playlist items with color coding based on status/type.
    """
    def paint(self, painter, option, index):
        painter.save()
        
        # Get data
        text = index.data(Qt.DisplayRole)
        status = index.data(PlaylistModel.StatusRole)
        # Use a hypothetical visual role or infer from text/index in model
        # For true MVP parity, we rely on StatusRole.
        
        # Background Colors
        bg_color = QColor(Qt.transparent)
        
        if option.state & QStyle.State_Selected:
            bg_color = option.palette.highlight().color()
        elif status == "failed":
            bg_color = QColor("#FFCCCC") # Light Red
        elif status == "success":
            bg_color = QColor("#CCFFCC") # Light Green
            
        painter.fillRect(option.rect, bg_color)
        
        # Text
        painter.setPen(option.palette.text().color())
        if option.state & QStyle.State_Selected:
             painter.setPen(option.palette.highlightedText().color())
             
        # Draw Text
        rect = option.rect.adjusted(5, 0, -5, 0) # Padding
        painter.drawText(rect, Qt.AlignVCenter | Qt.AlignLeft, text)
        
        painter.restore()

class PlaylistView(QWidget):
    def __init__(self, app_state: AppState, parent=None):
        super().__init__(parent)
        self.app_state = app_state
        self.model = PlaylistModel(app_state)
        self.setup_ui()
        
    def setup_ui(self):
        # Stats Panel needs horizontal layout with main list
        main_layout = QHBoxLayout(self)
        
        # Left Side: List + Controls
        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0,0,0,0)
        
        left_layout.addWidget(QLabel("Generation Output (Playlist)"))
        
        self.list_view = QListView()
        self.list_view.setModel(self.model)
        self.list_view.setItemDelegate(PlaylistDelegate()) # Use Custom Delegate
        self.list_view.setSelectionMode(QListView.ExtendedSelection) # Enable Ctrl/Shift Click
        self.list_view.selectionModel().selectionChanged.connect(self.update_stats)
        left_layout.addWidget(self.list_view)
        
        # Playback Controls
        ctrl_layout = QHBoxLayout()
        icon_prev = self.style().standardIcon(QStyle.SP_MediaSkipBackward)
        icon_play = self.style().standardIcon(QStyle.SP_MediaPlay)
        icon_stop = self.style().standardIcon(QStyle.SP_MediaStop)
        icon_next = self.style().standardIcon(QStyle.SP_MediaSkipForward)
        
        btn_prev = QPushButton(); btn_prev.setIcon(icon_prev)
        btn_play = QPushButton(); btn_play.setIcon(icon_play)
        btn_stop = QPushButton(); btn_stop.setIcon(icon_stop)
        btn_next = QPushButton(); btn_next.setIcon(icon_next)
        
        ctrl_layout.addWidget(btn_prev)
        ctrl_layout.addWidget(btn_play)
        ctrl_layout.addWidget(btn_stop)
        ctrl_layout.addWidget(btn_next)
        left_layout.addLayout(ctrl_layout)
        
        main_layout.addWidget(left_container, stretch=2)
        
        # Right Side: Stats Panel
        stats_group = QGroupBox("Chunk Stats")
        stats_group.setMaximumWidth(200)
        stats_layout = QFormLayout(stats_group)
        
        self.lbl_status = QLabel("--")
        self.lbl_seed = QLabel("--")
        self.lbl_asr = QLabel("--")
        
        stats_layout.addRow("Status:", self.lbl_status)
        stats_layout.addRow("Seed:", self.lbl_seed)
        stats_layout.addRow("ASR Match:", self.lbl_asr)
        
        main_layout.addWidget(stats_group, stretch=1)
        
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
