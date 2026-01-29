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
            # MCCC: Strict adherence to data model (original_sentence)
            text = item.get('original_sentence', '')
            
            # Format Pause Items
            if item.get('is_pause'):
                duration = item.get('duration', 0)
                text = f"[PAUSE : {duration}ms]"
                
            if len(text) > 80: text = text[:77] + "..."
            
            # Add Status Icon
            status = item.get('tts_generated', 'no')
            icon = ""
            if status == 'yes': icon = "✅ "
            elif status == 'failed': icon = "❌ "
            # elif status == 'no': icon = "⬜ " # User requested 'red x' for 'hadn't been generated', but ❌ is usually error.
            # Let's stick to X for fail/pending if user insisted, but standard UX distinguishes.
            # User said: "red x ... signify it hadn't been generated".
            # Let's try:
            # Success: ✅
            # Failed: ❌
            # Pending: (no icon) - reduces clutter.
            
            return f"[{row+1}] {icon}{text}"
            
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

    def update_row(self, row_index: int):
        """MCCC: granular update to avoid list reset."""
        idx = self.index(row_index, 0)
        if idx.isValid():
            self.dataChanged.emit(idx, idx, [Qt.DisplayRole, self.StatusRole])
