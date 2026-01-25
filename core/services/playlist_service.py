import uuid
import logging
from typing import List, Dict, Any, Optional
from core.state import AppState
from utils.text_processor import TextPreprocessor

class PlaylistService:
    """
    Handles modification of the sentence list (splitting, merging, editing, etc.).
    Ported from legacy MainWindow logic.
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
