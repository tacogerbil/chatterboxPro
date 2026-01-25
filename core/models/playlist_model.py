from PySide6.QtCore import QAbstractListModel, Qt, QModelIndex
from core.state import AppState

class PlaylistModel(QAbstractListModel):
    """
    Qt Model for the main Playlist (Sentences).
    """
    StatusRole = Qt.UserRole + 1
    
    def __init__(self, app_state: AppState, parent=None):
        super().__init__(parent)
        self.app_state = app_state
        
    def rowCount(self, parent=QModelIndex()):
        return len(self.app_state.sentences)
        
    def data(self, index, role):
        if not index.isValid():
            return None
            
        row = index.row()
        item = self.app_state.sentences[row]
        
        if role == Qt.DisplayRole:
            # Show index + snippet
            text = item.get('text', '')
            if len(text) > 80: text = text[:77] + "..."
            return f"[{row+1}] {text}"
            
        elif role == self.StatusRole:
            # Return status string for View delegate to colorize
            status = item.get('tts_generated', 'no')
            if status == 'yes': return "success"
            if status == 'failed': return "failed"
            return "pending"
            
        elif role == Qt.ToolTipRole:
            return item.get('original_sentence', '')
            
        return None
        
    def refresh(self):
        """Force full refresh."""
        self.beginResetModel()
        self.endResetModel()
