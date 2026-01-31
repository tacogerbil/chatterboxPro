# utils/text_processor.py
import re
import uuid
import unicodedata
import os

try:
    from sentence_splitter import SentenceSplitter
except ImportError:
    SentenceSplitter = None

# Optional imports for file extraction (match legacy behavior)
try:
    from pdftextract import XPdf
except ImportError:
    XPdf = None
try:
    import ebooklib
    from ebooklib import epub
except ImportError:
    ebooklib = None
    epub = None
try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None
try:
    import pypandoc
except ImportError:
    pypandoc = None


def punc_norm(text: str) -> str:
    """Quick cleanup func for punctuation from LLMs or containing chars not seen often in the dataset."""
    if not text:
        return "You need to add some text for me to talk."

    # Capitalise first letter
    if text and text[0].islower():
        text = text[0].upper() + text[1:]

    # Remove multiple space chars
    text = " ".join(text.split())

    # Replace uncommon/llm punc
    punc_to_replace = [
        ("...", ", "), ("…", ", "), (":", ","), (" - ", ", "), (";", ", "),
        ("—", "-"), ("–", "-"), (" ,", ","), ("“", "\""), ("”", "\""),
        ("‘", "'"), ("’", "'"),
    ]
    for old_char_sequence, new_char in punc_to_replace:
        text = text.replace(old_char_sequence, new_char)

    # Add full stop if no ending punc
    text = text.rstrip()
    sentence_enders = {".", "!", "?", "-", ","}
    if text and not any(text.endswith(p) for p in sentence_enders):
        text += "."

    return text

class TextPreprocessor:
    """Handles all text extraction and splitting logic."""
    def __init__(self):
        if SentenceSplitter:
            self.splitter = SentenceSplitter(language='en')
        else:
            self.splitter = None

        # Regex for simple fallback splitting
        self.simple_split_re = re.compile(r'(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<=\.|\?|!)\s')

        # Regex for aggressive character cleaning. Whitelists common characters.
        self.aggressive_clean_re = re.compile(r"[^a-zA-Z0-9\s'\",.?!-]")

        # Define patterns for spelled-out numbers from one to ninety-nine
        units = ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
        teens = ["ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
        tens = ["twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
        tens_pattern = "|".join(tens)
        units_pattern = "|".join(units)
        compound_pattern = f"(?:{tens_pattern})(?:[\\s-]?(?:{units_pattern}))?"
        number_words_pattern = f"(?:{compound_pattern}|{'|'.join(teens)}|{units_pattern})"

        self.chapter_regex = re.compile(
            rf'^\s*(chapter\s+([ivxlcdm]+|\d+|{number_words_pattern})|prologue|epilogue)',
            re.IGNORECASE
        )
        
        # --- Pronunciation Dictionary (Optional Enhancement) ---
        # Initialize pronunciation dictionary
        try:
            from utils.pronunciation_dict import create_default_dictionary
            self.pronunciation_dict = create_default_dictionary()
        except Exception:
            self.pronunciation_dict = None

    def remove_accents(self, text: str) -> str:
        """
        Convert accented characters to their ASCII equivalents.
        Examples: ñ → n, á → a, é → e, ü → u
        This preserves pronunciation while making text TTS-safe.
        """
        # Normalize to NFD (decomposed form) where accents are separate characters
        nfd_form = unicodedata.normalize('NFD', text)
        # Filter out combining characters (accents)
        ascii_text = ''.join(char for char in nfd_form if unicodedata.category(char) != 'Mn')
        return ascii_text

    def clean_text_aggressively(self, text: str) -> str:
        """Removes characters not in a basic whitelist."""
        # First, convert accented characters to ASCII equivalents
        text = self.remove_accents(text)
        # Then apply aggressive cleaning
        return self.aggressive_clean_re.sub('', text)

    def filter_non_english_words(self, text: str) -> str:
        """
        Removes words containing characters not typical in English.
        This is a heuristic and may remove valid but unusual words/names.
        It preserves sentence-ending punctuation.
        """
        words = text.split(' ')
        # A word is kept if it's purely alphabetic, or contains apostrophes/hyphens surrounded by letters.
        valid_word_re = re.compile(r"^[a-zA-Z]+(?:['-]?[a-zA-Z]+)*$")
        
        filtered_words = []
        for word in words:
            # Preserve punctuation by stripping it before checking, then re-adding it.
            leading_punc = ''
            trailing_punc = ''
            
            # Find leading non-alphanumeric characters
            match_lead = re.match(r'^[^a-zA-Z]*', word)
            if match_lead:
                leading_punc = match_lead.group(0)
            
            # Find trailing non-alphanumeric characters
            match_trail = re.search(r'[^a-zA-Z]*$', word)
            if match_trail:
                trailing_punc = match_trail.group(0)
                
            clean_word = word[len(leading_punc):len(word)-len(trailing_punc)]

            if valid_word_re.match(clean_word) or clean_word == '':
                filtered_words.append(word)
        
        return ' '.join(filtered_words)

    def smart_split_long_sentence(self, sentence: str, max_chars: int = 400) -> list:
        """
        Splits very long sentences at natural pause points (commas, semicolons).
        
        MCCC: Single Responsibility - Handles only long sentence splitting.
        
        Args:
            sentence: The sentence to potentially split
            max_chars: Maximum length before splitting (default 400)
        
        Returns:
            List of sub-sentences (or [sentence] if no split needed)
        """
        if len(sentence) <= max_chars:
            return [sentence]
        
        # Split at commas and semicolons, but keep the delimiters
        parts = re.split(r'([,;])', sentence)
        
        # Recombine into chunks that respect max_chars
        chunks = []
        current = ""
        
        for part in parts:
            test_length = len(current + part)
            
            if test_length <= max_chars:
                current += part
            else:
                # Current chunk is full, finalize it
                if current.strip():
                    chunks.append(current.strip())
                current = part
        
        # Add remaining text
        if current.strip():
            chunks.append(current.strip())
        
        # Fallback: if no chunks created, return original
        return chunks if chunks else [sentence]

    def group_sentences_into_chunks(self, sentences, max_chars=400):
        """
        Groups individual sentences into larger chunks for TTS processing.
        Phase 2 Quality Improvement: Uses semantic chunking (400 chars) for better Chatterbox prosody.
        """
        from utils.semantic_chunker import semantic_chunk_sentences, get_chunking_stats
        import logging
        
        # Use semantic chunking
        chunks = semantic_chunk_sentences(
            sentences,
            target_chars=max_chars,
            min_chars=200,
            max_chars=500
        )
        
        # Log stats
        stats = get_chunking_stats(chunks)
        if stats['total_chunks'] > 0:
            logging.info(f"Semantic chunking: {stats['total_chunks']} chunks, avg {stats['avg_length']:.0f} chars")
        
        return chunks
        
        # OLD CHUNKING LOGIC BELOW (kept for reference, not executed)
        """
        chunks, current_chunk_items, current_chunk_text = [], [], ""
        
        def finalize_chunk(items):
            if not items: return None
            is_chapter = len(items) == 1 and items[0].get('is_chapter_heading', False)
            final_text = " ".join(item.get('original_sentence', '') for item in items)
            
            return {
                "uuid": uuid.uuid4().hex,
                "original_sentence": final_text, 
                "text": final_text,
                "paragraph": "no",
                "tts_generated": "no", 
                "marked": False,
                "is_chapter_heading": is_chapter
            }

        for sentence_data in sentences:
            sentence_text = sentence_data.get('original_sentence', '')

            if sentence_data.get('is_chapter_heading'):
                if current_chunk_items:
                    chunks.append(finalize_chunk(current_chunk_items))
                chunks.append(sentence_data)
                current_chunk_items, current_chunk_text = [], ""
                continue
            
            if len(sentence_text) >= max_chars:
                if current_chunk_items:
                    chunks.append(finalize_chunk(current_chunk_items))
                chunks.append(sentence_data)
                current_chunk_items, current_chunk_text = [], ""
                continue
            
            if len(current_chunk_text) + len(sentence_text) + (1 if current_chunk_text else 0) > max_chars:
                if current_chunk_items:
                    chunks.append(finalize_chunk(current_chunk_items))
                current_chunk_items = [sentence_data]
                current_chunk_text = sentence_text
            else:
                current_chunk_items.append(sentence_data)
                current_chunk_text += (" " if current_chunk_text else "") + sentence_text
        
        if current_chunk_items:
            chunks.append(finalize_chunk(current_chunk_items))
            
        for i, chunk in enumerate(chunks):
            chunk['sentence_number'] = str(i + 1)
        
        return chunks
        """

    def extract_text_from_file(self, file_path: str) -> str:
        """
        Extracts raw text from various file formats (.txt, .pdf, .epub, .docx, .mobi).
        Dependencies (XPdf, ebooklib, etc.) must be installed for non-txt files.
        """
        path = str(file_path)
        ext = os.path.splitext(path)[1].lower()
        text = ""

        try:
            if ext == '.txt':
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    text = f.read()
            
            elif ext == '.pdf':
                if XPdf:
                    text = XPdf(path).to_text()
                else:
                    return f"Error: pdftextract not installed. Cannot read {ext}."
            
            elif ext == '.epub':
                if ebooklib and BeautifulSoup:
                    book = epub.read_epub(path)
                    html_content = "".join([item.get_body_content().decode('utf-8', 'ignore') 
                                          for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT)])
                    soup = BeautifulSoup(html_content, 'html.parser')
                    text = soup.get_text("\n\n", strip=True)
                else:
                    return f"Error: EbookLib or BeautifulSoup not installed. Cannot read {ext}."
            
            elif ext in ['.docx', '.mobi']:
                if pypandoc:
                    # pypandoc might require system pandoc installed
                    text = pypandoc.convert_file(path, 'plain', encoding='utf-8')
                else:
                    return f"Error: pypandoc not installed. Cannot read {ext}."
            
            else:
                return f"Error: Unsupported file extension '{ext}'"
                
        except Exception as e:
            return f"Error processing file: {str(e)}"
            
        return text

    def preprocess_text(self, text, is_edited_text=False, aggressive_clean=False):
        """Splits raw text into sentences and identifies paragraph breaks."""
        # --- Pronunciation Dictionary (Optional Enhancement) ---
        # Apply custom pronunciations before other processing
        if self.pronunciation_dict:
            text, replacements = self.pronunciation_dict.apply_pronunciations(text)
            if replacements:
                import logging
                logging.info(f"Applied pronunciations: {', '.join(replacements)}")
        
        if aggressive_clean:
            text = self.clean_text_aggressively(text)
        
        text = re.sub(r'\r\n?', '\n', text)
        text = re.sub(r'\t', ' ', text)

        if is_edited_text:
            paragraph_break_positions = {m.start() for m in re.finditer(r'\n', text)}
        else:
            text_with_marker = re.sub(r'\n{2,}', '[[PARAGRAPH]]', text)
            paragraph_break_positions = {m.start() for m in re.finditer(r'\[\[PARAGRAPH\]\]', text_with_marker)}
            text = re.sub(r'(?<!\n)\n(?!\n)', ' ', text)
            text = text.replace('[[PARAGRAPH]]', '\n')

        # Fallback split logic
        if self.splitter:
            sentences = self.splitter.split(text)
        else:
             # Very basic fallback split
             sentences = self.simple_split_re.split(text)

        processed_sentences = []
        char_offset = 0
        
        for i, sentence_text in enumerate(sentences):
            clean_sentence = sentence_text.strip()
            if not clean_sentence:
                char_offset += len(sentence_text)
                continue

            is_chapter_heading = bool(self.chapter_regex.match(clean_sentence))

            # MCCC: Smart Split - Handle sentences >400 chars
            # Split at natural pause points to improve TTS/ASR accuracy
            if len(clean_sentence) > 400 and not is_chapter_heading:
                sub_sentences = self.smart_split_long_sentence(clean_sentence, max_chars=400)
            else:
                sub_sentences = [clean_sentence]

            try:
                sentence_start_pos = text.index(sentence_text, char_offset)
                is_paragraph = any(p_pos >= sentence_start_pos and p_pos < (sentence_start_pos + len(sentence_text)) for p_pos in paragraph_break_positions)
                char_offset = sentence_start_pos + len(sentence_text)
            except ValueError:
                is_paragraph = False
                char_offset += len(sentence_text)

            # Create sentence dict for each sub-sentence
            for sub_idx, sub_sentence in enumerate(sub_sentences):
                processed_sentences.append({
                    "uuid": uuid.uuid4().hex,
                    "sentence_number": str(i + 1) + (f".{sub_idx+1}" if len(sub_sentences) > 1 else ""),
                    "original_sentence": sub_sentence,
                    "text": sub_sentence,
                    "paragraph": "yes" if is_paragraph and sub_idx == 0 else "no",
                    "tts_generated": "no",
                    "marked": False,
                    "is_chapter_heading": is_chapter_heading
                })

            
        return processed_sentences


    def rechunk_current_session(self, current_sentences):
        """
        Re-chunks existing session while preserving chapters and pauses.
        Uses semantic chunking for better prosody.
        """
        import logging
        
        try:
            chapters, pauses, text_items = [], [], []
            
            # Separate chapters, pauses, and text
            for idx, s in enumerate(current_sentences):
                if s.get('is_chapter_heading'):
                    chapters.append((idx, s))
                elif s.get('is_pause') or not s.get('text', '').strip():
                    pauses.append((idx, s))
                else:
                    text_items.append(s)
            
            # If no text items, return original
            if not text_items:
                logging.warning("No text items to rechunk")
                return current_sentences
            
            # Combine all text
            raw_text = ' '.join([s.get('original_sentence', s.get('text', '')) for s in text_items])
            
            if not raw_text.strip():
                logging.warning("Empty text after combining")
                return current_sentences
            
            # Preprocess and chunk
            new_sentences = self.preprocess_text(raw_text)
            new_chunks = self.group_sentences_into_chunks(new_sentences)
            
            # Re-insert chapters and pauses at their original positions
            for idx, ch in chapters:
                new_chunks.insert(min(idx, len(new_chunks)), ch)
            for idx, p in pauses:
                new_chunks.insert(min(idx, len(new_chunks)), p)
            
            logging.info(f"Rechunked: {len(current_sentences)} → {len(new_chunks)} items")
            return new_chunks
            
        except Exception as e:
            logging.error(f"Rechunk failed: {e}", exc_info=True)
            # Return original on error
            return current_sentences
