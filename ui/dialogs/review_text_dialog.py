from PySide6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QHBoxLayout, QPushButton, QLabel

class ReviewTextDialog(QDialog):
    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Review and Edit Text")
        self.resize(800, 600)
        self.text = text
        self.result_text = None
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        lbl = QLabel("Review extracted text before processing:")
        layout.addWidget(lbl)
        
        self.editor = QTextEdit()
        self.editor.setPlainText(self.text)
        layout.addWidget(self.editor)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        confirm_btn = QPushButton("Confirm Processing")
        confirm_btn.setStyleSheet("background-color: #27AE60; color: white; padding: 5px 15px; font-weight: bold;")
        confirm_btn.clicked.connect(self.accept)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        
        btn_layout.addWidget(confirm_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def accept(self):
        self.result_text = self.editor.toPlainText()
        super().accept()
