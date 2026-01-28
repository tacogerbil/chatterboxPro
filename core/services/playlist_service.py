import uuid
import logging
from typing import List, Dict, Any, Optional
from core.state import AppState
from utils.text_processor import TextPreprocessor

class PlaylistService:
    """
    Handles modification of the sentence list (splitting, merging, editing, etc.).

    """
    def __init__(self, app_state: AppState):
        self.state = app_state
        self.processor = TextPreprocessor()
        
    def get_selected_item(self, index: int) -> Optional[Dict[str, Any]]:
        if 0 <= index < len(self.state.sentences):
            return self.state.sentences[index]
        return None

    def edit_text(self, index: int, new_text: str) -> bool:
        item = self.get_selected_item(index)
        if not item: return False
        
        original = item.get('original_sentence', '')
        if new_text.strip() and new_text != original:
            item['original_sentence'] = new_text
            item['tts_generated'] = 'no' # Invalidate audio
            item['marked'] = True
            return True
        return False

    def edit_pause(self, index: int, duration: int) -> bool:
        """Updates duration of a pause item."""
        item = self.get_selected_item(index)
        if not item or not item.get('is_pause'): return False
        
        if duration != item.get('duration'):
             item['duration'] = duration
             item['tts_generated'] = 'n/a' # Pauses don't 'generate' but status is usually n/a or yes
             item['marked'] = True
             return True
        return False

    def split_chunk(self, index: int) -> bool:
        item = self.get_selected_item(index)
        if not item: return False
        
        text = item.get('original_sentence', '')
        split_sentences = self.processor.splitter.split(text)
        
        if len(split_sentences) <= 1:
            return False # Cannot split
            
        # Create new items
        new_items = []
        for s in split_sentences:
            s_clean = s.strip()
            if not s_clean: continue
            
            new_item = {
                "uuid": uuid.uuid4().hex,
                "original_sentence": s_clean,
                "paragraph": "no",
                "tts_generated": "no",
                "marked": True,
                "is_chapter_heading": bool(self.processor.chapter_regex.match(s_clean))
            }
            new_items.append(new_item)
            
        # Replace old item with new items
        self.state.sentences[index:index+1] = new_items
        self._renumber()
        return True

    def insert_item(self, index: int, text: str, is_pause: bool = False, duration: int = 0, is_chapter: bool = False):
        new_item = {
            "uuid": uuid.uuid4().hex,
            "original_sentence": text,
            "paragraph": "no",
            "tts_generated": "n/a" if is_pause else "no",
            "marked": True,
            "is_chapter_heading": is_chapter,
            "is_pause": is_pause
        }
        if is_pause:
             new_item["duration"] = duration
             
        # Insert AT index (shifting current item down)
        # If list empty, append.
        if index < 0: index = len(self.state.sentences)
        self.state.sentences.insert(index, new_item)
        self._renumber()

    def convert_to_chapter(self, index: int) -> bool:
        """Converts an existing item into a Chapter Heading."""
        item = self.get_selected_item(index)
        if not item: return False
        
        if not item.get('is_chapter_heading'):
            item['is_chapter_heading'] = True
            # Ideally reset generation status? Or keeps audio but acts as header?
            # Usually headers are skipped in generation or treated separately.
            # Let's keep content but mark modified.
            item['marked'] = True 
            return True
        return False

    def delete_items(self, indices: List[int]) -> int:
        """Deletes items at indices. Returns count deleted."""
        if not indices: return 0
        
        # Sort reverse to avoid index shifting problems
        for idx in sorted(indices, reverse=True):
            if 0 <= idx < len(self.state.sentences):
                self.state.sentences.pop(idx)
                
        self._renumber()
        return len(indices)

    def move_items(self, indices: List[int], direction: int) -> List[int]:
        """Moves items up/down. Returns new indices of moved items."""
        if not indices: return []
        
        sorted_indices = sorted(indices, reverse=(direction == 1))
        new_indices = set()
        moved = False
        
        temp_list = list(self.state.sentences) # Copy
        
        for idx in sorted_indices:
            new_idx = idx + direction
            if 0 <= new_idx < len(temp_list):
                 temp_list[idx], temp_list[new_idx] = temp_list[new_idx], temp_list[idx]
                 new_indices.add(new_idx)
                 moved = True
            else:
                 new_indices.add(idx) # Kept at boundary
                 
        if moved:
            self.state.sentences = temp_list
            self._renumber()
            return sorted(list(new_indices))
        return indices

    def search(self, query: str) -> List[int]:
        if not query: return []
        matches = []
        q_lower = query.lower()
        for i, s in enumerate(self.state.sentences):
            if q_lower in s.get('original_sentence', '').lower():
                matches.append(i)
        return matches

    def find_next_status(self, start_index: int, direction: int, status: str) -> int:
        """Finds next item with specific status (e.g. 'failed')."""
        count = len(self.state.sentences)
        if count == 0: return -1
        
        curr = start_index + direction
        looped = False
        
        while curr != start_index:
            if curr < 0: curr = count - 1
            if curr >= count: curr = 0
            
            # Correction for initial -1 start
            if start_index == -1 and not looped:
                if direction == 1: curr = 0
                else: curr = count - 1
                looped = True # Only jump once
            
            item = self.state.sentences[curr]
            if item.get('tts_generated') == status:
                return curr
            
            curr += direction
            
            # Break if full loop
            if curr == start_index: break
            
        return -1

    def _renumber(self):
        for i, item in enumerate(self.state.sentences):
            item['sentence_number'] = str(i + 1)

    def merge_failed_down(self) -> int:
        """Merges failed chunks into the chunk below them."""
        # Ported from legacy controls_frame.py logic (inferred) / main_window.py
        merged_count = 0
        i = 0
        while i < len(self.state.sentences) - 1:
            curr = self.state.sentences[i]
            if curr.get('tts_generated') == 'failed':
                next_item = self.state.sentences[i+1]
                
                # Merge text
                merged_text = (curr.get('original_sentence', '') + " " + next_item.get('original_sentence', '')).strip()
                next_item['original_sentence'] = merged_text
                next_item['tts_generated'] = 'no'
                next_item['marked'] = True
                
                # Remove current
                self.state.sentences.pop(i)
                merged_count += 1
                # Don't increment i, check this index again (which is now the next_item)
            else:
                i += 1
                
        if merged_count > 0:
            self._renumber()
        return merged_count

    def split_all_failed(self) -> int:
        """Splits all failed chunks using the sentence splitter."""
        split_count = 0
        i = 0
        while i < len(self.state.sentences):
            item = self.state.sentences[i]
            if item.get('tts_generated') == 'failed':
                text = item.get('original_sentence', '')
                split_sentences = self.processor.splitter.split(text)
                
                if len(split_sentences) > 1:
                     new_items = []
                     for s in split_sentences:
                        if not s.strip(): continue
                        new_items.append({
                            "uuid": uuid.uuid4().hex,
                            "original_sentence": s.strip(),
                            "paragraph": "no",
                            "tts_generated": "no",
                            "marked": True,
                            "is_chapter_heading": bool(self.processor.chapter_regex.match(s.strip()))
                        })
                     
                     self.state.sentences[i:i+1] = new_items
                     split_count += 1
                     i += len(new_items) # Skip over new items
                     continue
            i += 1
            
        if split_count > 0:
            self._renumber()
        return split_count

    def clean_special_chars_selected(self, indices: List[int]) -> int:
        """Removes special chars from selected items."""
        count = 0
        for idx in indices:
            if 0 <= idx < len(self.state.sentences):
                item = self.state.sentences[idx]
                text = item.get('original_sentence', '')
                # Use TextPreprocessor's clean_text_aggressively
                cleaned = self.processor.clean_text_aggressively(text)
                if cleaned != text:
                    item['original_sentence'] = cleaned
                    item['tts_generated'] = 'no'
                    item['marked'] = True
                    count += 1
        return count

    def filter_non_english_in_selected(self, indices: List[int]) -> int:
        """Filters non-english words from selected items."""
        count = 0
        for idx in indices:
            if 0 <= idx < len(self.state.sentences):
                item = self.state.sentences[idx]
                text = item.get('original_sentence', '')
                filtered = self.processor.filter_non_english_words(text)
                
                if filtered != text:
                    item['original_sentence'] = filtered
                    item['tts_generated'] = 'no'
                    item['marked'] = True
                    count += 1
        return count
