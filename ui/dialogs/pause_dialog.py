"""
ui/dialogs/pause_dialog.py

Custom dialog for inserting or editing a pause item.
Shows a spinbox (default 500ms) plus three quick-apply buttons
that commit immediately without needing to press OK.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QSpinBox, QPushButton, QDialogButtonBox
)
from PySide6.QtCore import Qt
from typing import Optional


class PauseDialog(QDialog):
    """
    Dialog for selecting a pause duration.

    Quick-insert buttons (1000, 1500, 2000 ms) accept the dialog immediately
    without requiring the user to press OK.  The spin-box defaults to 500 ms
    and still requires an explicit OK press.
    """

    QUICK_DURATIONS = [1000, 1500, 2000]

    def __init__(self, initial_ms: int = 500, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Insert Pause")
        self.setMinimumWidth(240)
        self._result_ms: Optional[int] = None
        self._build_ui(initial_ms)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def duration_ms(self) -> Optional[int]:
        """Returns the chosen duration in ms, or None if cancelled."""
        return self._result_ms

    @staticmethod
    def get_duration(initial_ms: int = 500, parent=None) -> Optional[int]:
        """
        Convenience factory.  Shows the dialog and returns the duration or None.
        """
        dlg = PauseDialog(initial_ms=initial_ms, parent=parent)
        dlg.exec()
        return dlg.duration_ms

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_ui(self, initial_ms: int) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        layout.addWidget(QLabel("Duration (ms):"))

        self._spin = QSpinBox()
        self._spin.setRange(100, 10000)
        self._spin.setSingleStep(50)
        self._spin.setValue(initial_ms)
        self._spin.setSuffix(" ms")
        layout.addWidget(self._spin)

        # Quick-insert buttons row
        quick_row = QHBoxLayout()
        for ms in self.QUICK_DURATIONS:
            btn = QPushButton(str(ms))
            btn.setToolTip(f"Insert {ms} ms pause immediately")
            # Capture ms by default-argument binding
            btn.clicked.connect(lambda _checked, v=ms: self._accept_quick(v))
            quick_row.addWidget(btn)
        layout.addLayout(quick_row)

        # Standard OK / Cancel
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            Qt.Horizontal,
        )
        buttons.accepted.connect(self._accept_spin)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _accept_quick(self, ms: int) -> None:
        """Accepts the dialog immediately with the given quick-insert value."""
        self._result_ms = ms
        self.accept()

    def _accept_spin(self) -> None:
        """Accepts the dialog using the current spinbox value."""
        self._result_ms = self._spin.value()
        self.accept()
