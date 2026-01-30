# Append rechunk method to text_processor.py

method_code = """

    def rechunk_current_session(self, current_sentences):
        '''Re-chunks existing session while preserving chapters and pauses.'''
        chapters, pauses, text_items = [], [], []
        for idx, s in enumerate(current_sentences):
            if s.get('is_chapter_heading'):
                chapters.append((idx, s))
            elif not s.get('text', '').strip():
                pauses.append((idx, s))
            else:
                text_items.append(s)
        if not text_items:
            return current_sentences
        raw_text = ' '.join([s.get('original_sentence', s.get('text', '')) for s in text_items])
        new_sentences = self.preprocess_text(raw_text)
        new_chunks = self.group_sentences_into_chunks(new_sentences)
        for idx, ch in chapters:
            new_chunks.insert(min(idx, len(new_chunks)), ch)
        for idx, p in pauses:
            new_chunks.insert(min(idx, len(new_chunks)), p)
        return new_chunks
"""

with open('utils/text_processor.py', 'a', encoding='utf-8') as f:
    f.write(method_code)

print("Method appended successfully!")
