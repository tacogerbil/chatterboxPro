from PySide6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QHBoxLayout, QPushButton, QLabel

class EditorDialog(QDialog):
    """
    A full multi-line text editor dialog.
    Restores legacy functionality for editing text chunks comfortably.
    """
    def __init__(self, initial_text="", parent=None, title="Edit Text"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(500, 400)
        self.result_text = initial_text
        
        layout = QVBoxLayout(self)
        
        layout.addWidget(QLabel("Edit Text Content:"))
        
        self.text_edit = QTextEdit()
        self.text_edit.setPlainText(initial_text)
        layout.addWidget(self.text_edit)
        
        btn_layout = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.accept)
        save_btn.setStyleSheet("background-color: #2ECC71; color: white;")
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        
        btn_layout.addStretch()
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        
    def accept(self):
        self.result_text = self.text_edit.toPlainText()
        super().accept()
