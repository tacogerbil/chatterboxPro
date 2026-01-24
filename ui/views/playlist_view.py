from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QListView, 
                               QPushButton, QLabel, QStyle)
from PySide6.QtCore import Qt
from core.state import AppState
from core.models.playlist_model import PlaylistModel

class PlaylistView(QWidget):
    def __init__(self, app_state: AppState, parent=None):
        super().__init__(parent)
        self.app_state = app_state
        self.model = PlaylistModel(app_state)
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Header
        layout.addWidget(QLabel("Generation Output (Playlist)"))
        
        # List
        self.list_view = QListView()
        self.list_view.setModel(self.model)
        self.list_view.setAlternatingRowColors(True)
        layout.addWidget(self.list_view)
        
        # Playback Controls
        ctrl_layout = QHBoxLayout()
        
        # Standard Icons
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
        
        layout.addLayout(ctrl_layout)
        
    def refresh(self):
        self.model.refresh()
