import logging
import os
from PySide6.QtWidgets import QWidget, QVBoxLayout, QTextEdit
from PySide6.QtCore import QObject, Signal, Slot

class QtLogHandler(logging.Handler):
    """
    Custom logging handler that emits a signal for each log record.
    Must be connected to a receiver in the UI thread.
    """
    def __init__(self, emitter):
        super().__init__()
        self.emitter = emitter

    def emit(self, record):
        msg = self.format(record)
        self.emitter.log_signal.emit(msg)

class LogEmitter(QObject):
    log_signal = Signal(str)

class LogView(QWidget):
    """
    Displays log messages in a read-only text area.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        self._setup_logging()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setStyleSheet("font-family: Consolas, monospace; font-size: 10pt; background-color: #1E1E1E; color: #D4D4D4;")
        layout.addWidget(self.text_edit)

    def _setup_logging(self):
        # Create Signal Emitter
        self.emitter = LogEmitter()
        self.emitter.log_signal.connect(self.append_log)
        
        # Create Handler
        self.handler = QtLogHandler(self.emitter)
        self.handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        self.handler.setLevel(logging.DEBUG)
        
        # Add to Root Logger
        root_logger = logging.getLogger()
        root_logger.addHandler(self.handler)
        root_logger.setLevel(logging.DEBUG)
        
        # Setting root to DEBUG affects all handlers. We must clamp file handlers.
        for h in root_logger.handlers:
            if isinstance(h, logging.FileHandler):
                try:
                    base_name = os.path.basename(h.baseFilename).lower()
                    if 'error' in base_name:
                        if h.level < logging.ERROR:
                            h.setLevel(logging.ERROR)
                            logging.info(f"Fixed Config: Clamped {base_name} to ERROR level.")
                    elif 'debug' not in base_name:
                        # Default others to INFO to avoid massive log files
                        if h.level < logging.INFO:
                            h.setLevel(logging.INFO)
                except Exception as e:
                    print(f"Failed to adjust log handler {h}: {e}")

        for lib in ["numba", "llvmlite", "matplotlib", "PIL", "urllib3"]:
            logging.getLogger(lib).setLevel(logging.WARNING)

        # Log initial message
        logging.info("Log View initialized.")

    @Slot(str)
    def append_log(self, msg: str):
        self.text_edit.append(msg)
        # Move scrollbar to bottom
        sb = self.text_edit.verticalScrollBar()
        sb.setValue(sb.maximum())
