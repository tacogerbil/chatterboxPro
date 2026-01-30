# Append rechunk handler to controls_view.py

method_code = """

    def _rechunk_session(self):
        '''Re-chunk current session using improved chunking algorithm.'''
        reply = QMessageBox.question(
            self, "Re-chunk Session?",
            "This will re-split all text using improved chunking.\\n\\n"
            "✅ Preserves: Chapters, Pauses\\n"
            "⚠️ Warning: Generated audio will need regeneration\\n\\n"
            "Continue?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            from utils.text_processor import TextPreprocessor
            processor = TextPreprocessor()
            old_count = len(self.state.sentences)
            new_sentences = processor.rechunk_current_session(self.state.sentences)
            self.state.sentences = new_sentences
            self._refresh()
            self.structure_changed.emit()
            QMessageBox.information(
                self, "Re-chunk Complete", 
                f"Re-chunked session:\\n"
                f"Before: {old_count} items\\n"
                f"After: {len(new_sentences)} items"
            )
"""

with open('ui/views/controls_view.py', 'a', encoding='utf-8') as f:
    f.write(method_code)

print("Handler method appended successfully!")
