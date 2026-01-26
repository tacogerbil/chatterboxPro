from PySide6.QtCore import QAbstractListModel, Qt, QModelIndex, Slot
from typing import List, Set, Tuple, Any, Union, Optional
from core.state import AppState
from core.services.chapter_service import ChapterService

class ChapterModel(QAbstractListModel):
    """
    Qt Model for displaying "Detected Chapters".
    It does not copy data; it wraps AppState.sentences (via ChapterService detection).
    """
    NameRole: int = Qt.UserRole + 1
    RealIndexRole: int = Qt.UserRole + 2
    CheckedRole: int = Qt.UserRole + 3

    def __init__(self, app_state: AppState, parent: Optional[Any] = None) -> None:
        super().__init__(parent)
        self.app_state: AppState = app_state
        self.chapter_service: ChapterService = ChapterService()
        
        # Internal cache of (real_index, item)
        self._chapters: List[Tuple[int, Dict[str, Any]]] = []
        self._checked_state: Set[int] = set() # Stores row indices that are checked
        
        # Initial scan
        self.refresh()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._chapters)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid():
            return None
        
        row = index.row()
        if row >= len(self._chapters): 
             return None
             
        real_idx, item = self._chapters[row]
        
        if role == Qt.DisplayRole or role == self.NameRole:
            text = item.get('original_sentence', f'Chapter {row+1}')
            if len(text) > 60: text = text[:57] + "..."
            return f"{row+1}. {text}"
            
        elif role == self.RealIndexRole:
            return real_idx
            
        elif role == Qt.CheckStateRole:
            return Qt.Checked if row in self._checked_state else Qt.Unchecked
            
        return None

    def setData(self, index: QModelIndex, value: Any, role: int = Qt.EditRole) -> bool:
        if not index.isValid():
            return False
            
        if role == Qt.CheckStateRole:
            row = index.row()
            if value == Qt.Checked or value == 2:
                self._checked_state.add(row)
            else:
                self._checked_state.discard(row)
            self.dataChanged.emit(index, index, [Qt.CheckStateRole])
            return True
            
        return False

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        if not index.isValid():
            return Qt.NoItemFlags
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable

    def refresh(self) -> None:
        """Re-scan sentences for chapters."""
        self.beginResetModel()
        self._chapters = self.chapter_service.detect_chapters(self.app_state.sentences)
        self._checked_state.clear() # Clear selection on refresh
        self.endResetModel()

    def get_selected_indices(self) -> List[int]:
        """Returns list of selected CHAPTER indices (0, 1, 3 etc)."""
        return sorted(list(self._checked_state))

    def get_chapter_index(self, row: int) -> int:
        """Returns the real sentence index for the chapter at row."""
        if 0 <= row < len(self._chapters):
            return self._chapters[row][0]
        return -1
