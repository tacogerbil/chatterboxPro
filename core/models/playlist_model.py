from PySide6.QtCore import QAbstractListModel, Qt, QModelIndex
from core.state import AppState
import html  # MCCC: Move import out of hot path
from typing import List

class PlaylistModel(QAbstractListModel):
    """
    Qt Model for the main Playlist (Sentences).
    """
    StatusRole = Qt.UserRole + 1
    MarkedRole = Qt.UserRole + 2
    
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
            
            # Add Status Icon — order: chapter > chap-candidate > regen-flag > outlier > gen-status
            status = item.get('tts_generated', 'no')
            is_marked = item.get('marked', False)
            is_chapter = item.get('is_chapter_heading', False)

            icon = ""
            if is_chapter:     icon += "📑 "
            if is_marked:      icon += "🚩 "

            # Show Outlier Warning if present
            if item.get('outlier_reason'):
                icon += "⚠️ "

            if status == 'yes':    icon += "✅ "
            elif status == 'failed': icon += "❌ "

            return f"[{row+1}] {icon}{text}"
            
        elif role == self.StatusRole:
            # Return status string for View delegate to colorize
            status = item.get('tts_generated', 'no')
            if status == 'yes': return "success"
            if status == 'failed': return "failed"
            return "pending"
            
        elif role == self.MarkedRole:
            return item.get('marked', False)
            
        elif role == Qt.ToolTipRole:
            # MCCC: Format tooltip with HTML for word wrapping
            raw_text = item.get('original_sentence', '')
            safe_text = html.escape(raw_text)
            # Use styling to limit width and force wrap
            return f"<div style='width: 400px; text-align: left;'>{safe_text}</div>"
            
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

    def update_rows(self, row_indices: List[int]):
        """MCCC: Batched update for efficiency."""
        if not row_indices: return
        
        # Determine range (assuming somewhat contiguous for efficiency)
        min_idx = min(row_indices)
        max_idx = max(row_indices)
        
        # Emit one signal covering the range
        # This is more efficient than emitting 100 signals for 100 rows
        start = self.index(min_idx, 0)
        end = self.index(max_idx, 0)
        
        if start.isValid() and end.isValid():
            self.dataChanged.emit(start, end, [Qt.DisplayRole, self.StatusRole])

    def get_item(self, row_index: int):
        """Returns the raw data dict for a given row index."""
        if 0 <= row_index < len(self.app_state.sentences):
            return self.app_state.sentences[row_index]
        return None
