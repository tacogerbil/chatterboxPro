import pathlib

# Read current file
p = pathlib.Path(r'a:/Coding_Projects/AI Coding/ChatterboxPro/execution/chatterboxPro/utils/text_processor.py')
content = p.read_text()

# Append new method
new_method = '''

    def rechunk_current_session(self, current_sentences):
        """Re-chunks existing session while preserving chapters and pauses."""
        chapters, pauses, text_items = [], [], []
        for idx, s in enumerate(current_sentences):
            if s.get("is_chapter_heading"):
                chapters.append((idx, s))
            elif not s.get("text", "").strip():
                pauses.append((idx, s))
            else:
                text_items.append(s)
        if not text_items:
            return current_sentences
        raw_text = " ".join([s.get("original_sentence", s.get("text", "")) for s in text_items])
        new_sentences = self.preprocess_text(raw_text)
        new_chunks = self.group_sentences_into_chunks(new_sentences)
        for idx, ch in chapters:
            new_chunks.insert(min(idx, len(new_chunks)), ch)
        for idx, pause in pauses:
            new_chunks.insert(min(idx, len(new_chunks)), pause)
        return new_chunks
'''

# Write back
p.write_text(content + new_method)
print("Method added successfully!")
