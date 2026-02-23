import uuid
import logging
from typing import List, Dict, Any, Optional
from itertools import groupby
from operator import itemgetter
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

    def reset_item(self, index: int) -> bool:
        """Resets generation status and clears artifacts for a single item."""
        item = self.get_selected_item(index)
        if not item: return False
        
        item['tts_generated'] = 'no'
        if not item.get('is_pause'):
            item['marked'] = True
        else:
            item['marked'] = False
        
        # Clear artifacts to prevent stale UI stats
        keys_to_clear = ['audio_path', 'similarity_ratio', 'generation_seed', 'asr_match', 'ffmpeg_cmd']
        for k in keys_to_clear:
            if k in item:
                del item[k]
                
        return True

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
             # Pauses should not be marked for regeneration
             return True
        return False

    def split_chunk(self, index: int) -> bool:
        item = self.get_selected_item(index)
        if not item: return False

        was_chapter = item.get('is_chapter_heading', False)

        text = item.get('original_sentence', '')
        split_sentences = self.processor.splitter.split(text)

        if len(split_sentences) <= 1:
            return False  # Cannot split

        # Create new items
        new_items = []
        for idx_s, s in enumerate(split_sentences):
            s_clean = s.strip()
            if not s_clean: continue

            # First child inherits is_chapter_heading from parent so the chapter
            # heading is NOT silently deleted when a heading is split to clean it up.
            is_ch = was_chapter if idx_s == 0 else bool(self.processor.chapter_regex.match(s_clean))

            new_item = {
                "uuid": uuid.uuid4().hex,
                "original_sentence": s_clean,
                "paragraph": "no",
                "tts_generated": "no",
                "marked": False,
                "is_chapter_heading": is_ch,
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
            "marked": False,
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

    def toggle_selection_mark(self, indices: List[int]) -> None:
        """Toggles the 'marked' status of selected items."""
        for idx in indices:
            if 0 <= idx < len(self.state.sentences):
                item = self.state.sentences[idx]
                
                # Special Logic for Pauses: Can UNMARK, but cannot MARK
                if item.get('is_pause'):
                    if item.get('marked'):
                        item['marked'] = False
                    continue
                
                current = item.get('marked', False)
                item['marked'] = not current
                
    def convert_to_chapter(self, index: int) -> bool:
        """Converts an existing item into a Chapter Heading.

        IMPORTANT: The item's `marked` flag is intentionally set to False.
        Chapter headings must NOT be included in batch-mark workflows
        (regen marked, reflow, split-all-marked) that scan the entire list.
        Setting marked=True here was the root cause of chapters vanishing in
        unrelated parts of the book during join/reflow operations.
        """
        item = self.get_selected_item(index)
        if not item: return False

        if not item.get('is_chapter_heading'):
            item['is_chapter_heading'] = True
            item['marked'] = False  # Never include chapters in batch-mark operations
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

    def search(self, query: str) -> List[str]:
        if not query: return []
        matches = []
        q_lower = query.lower()
        for s in self.state.sentences:
            if q_lower in s.get('original_sentence', '').lower():
                uid = s.get('uuid')
                if uid:
                    matches.append(uid)
        return matches

    def replace_current(self, index: int, search_term: str, replace_term: str) -> bool:
        """Replaces text in a specific chunk if it contains the search term. Flags it for regeneration."""
        if not search_term: return False
        item = self.get_selected_item(index)
        if not item: return False
        
        original = item.get('original_sentence', '')
        if search_term in original:
            new_text = original.replace(search_term, replace_term)
            if new_text != original:
                item['original_sentence'] = new_text
                item['tts_generated'] = 'no' # Invalidate audio
                item['marked'] = True
                return True
        return False

    def replace_all(self, search_term: str, replace_term: str) -> int:
        """Iterates through all chunks and replaces text, flagging modified chunks for regeneration."""
        if not search_term: return 0
        replaced_count = 0
        
        for s in self.state.sentences:
            original = s.get('original_sentence', '')
            if search_term in original:
                new_text = original.replace(search_term, replace_term)
                if new_text != original:
                    s['original_sentence'] = new_text
                    s['tts_generated'] = 'no' # Invalidate audio
                    s['marked'] = True
                    replaced_count += 1
                    
        return replaced_count

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
        """Merges failed chunks into the chunk below them.

        Chapter headings are never merged — they are skipped to preserve
        the chapter structure that the user has established.
        """
        merged_count = 0
        i = 0
        while i < len(self.state.sentences) - 1:
            curr = self.state.sentences[i]

            # GUARD: never merge a chapter heading away, and never merge INTO one.
            if curr.get('is_chapter_heading'):
                i += 1
                continue

            if curr.get('tts_generated') == 'failed':
                next_item = self.state.sentences[i + 1]

                # GUARD: don't merge into a chapter heading
                if next_item.get('is_chapter_heading'):
                    i += 1
                    continue

                # Merge text
                merged_text = (curr.get('original_sentence', '') + " " + next_item.get('original_sentence', '')).strip()
                next_item['original_sentence'] = merged_text
                next_item['tts_generated'] = 'no'
                next_item['marked'] = False

                # Clear associated metrics and artifacts for the merged item
                keys_to_clear = ['audio_path', 'asr_match', 'seed', 'ffmpeg_cmd']
                for k in keys_to_clear:
                    if k in next_item:
                        del next_item[k]

                # Remove current
                self.state.sentences.pop(i)
                merged_count += 1
                # Don't increment i — check this slot again (now holds next_item)
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
                    item['marked'] = False
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

    def apply_auto_pause_buffers(self, before_ms: int, after_ms: int) -> Dict[str, int]:
        """
        Wraps chapters with pauses.
        Logic: Reverse iteration.
        """
        stats = {'processed': 0, 'added': 0, 'skipped': 0}
        
        i = len(self.state.sentences) - 1
        while i >= 0:
            item = self.state.sentences[i]
            if item.get('is_chapter_heading'):
                stats['processed'] += 1
                
                # --- AFTER (buffer_after_ms) ---
                if after_ms > 0:
                    if i + 1 < len(self.state.sentences):
                        next_item = self.state.sentences[i+1]
                        if not next_item.get('is_pause'):
                            self.insert_item(i + 1, "[PAUSE]", is_pause=True, duration=after_ms)
                            stats['added'] += 1
                        else:
                            stats['skipped'] += 1
                    else:
                        self.insert_item(i + 1, "[PAUSE]", is_pause=True, duration=after_ms)
                        stats['added'] += 1

                # --- BEFORE (buffer_before_ms) ---
                # Note: If we inserted after, current is still at i.
                # If we insert before, current shifts to i+1.
                
                if before_ms > 0:
                    should_insert = True
                    if i > 0:
                        prev_item = self.state.sentences[i-1]
                        if prev_item.get('is_pause'):
                            should_insert = False
                            stats['skipped'] += 1
                    
                    if should_insert:
                        self.insert_item(i, "[PAUSE]", is_pause=True, duration=before_ms)
                        stats['added'] += 1
            
            i -= 1
            
        self._renumber()
        return stats

    def reflow_marked_items(self) -> int:
        """
        Smart Merge: Finds contiguous blocks of marked items, concatenates their text,
        and re-chunks them respecting the max_chunk_chars setting.

        Chapter headings are excluded from reflow — any group that contains a
        chapter heading is skipped entirely so `is_chapter_heading` is never lost.
        """
        if not self.state.sentences: return 0

        marked_indices = [i for i, s in enumerate(self.state.sentences) if s.get('marked')]
        if not marked_indices: return 0

        groups = []
        for k, g in groupby(enumerate(marked_indices), lambda ix: ix[0] - ix[1]):
            groups.append(list(map(itemgetter(1), g)))

        # Process groups in reverse order to keep indices valid
        processed_count = 0
        max_chars = self.state.settings.max_chunk_chars

        for group in reversed(groups):
            if not group: continue

            # GUARD: skip any group that contains a chapter heading.
            # Reflowing merges text, which would silently destroy the heading flag.
            if any(self.state.sentences[idx].get('is_chapter_heading') for idx in group):
                logging.debug(f"[reflow] Skipping group {group} — contains chapter heading.")
                continue

            start_idx = group[0]
            full_text = ""
            for idx in group:
                full_text += " " + self.state.sentences[idx].get('original_sentence', '')

            full_text = full_text.strip()

            raw_sentences = (self.processor.splitter.split(full_text)
                             if self.processor.splitter
                             else self.processor.simple_split_re.split(full_text))

            sentence_dicts = []
            for s in raw_sentences:
                s_clean = s.strip()
                if not s_clean: continue
                sentence_dicts.append({
                    "original_sentence": s_clean,
                    "is_chapter_heading": bool(self.processor.chapter_regex.match(s_clean))
                })

            new_chunks = self.processor.group_sentences_into_chunks(sentence_dicts, max_chars=max_chars)

            for chunk in new_chunks:
                chunk['tts_generated'] = 'no'
                chunk['marked'] = False

            self.state.sentences[start_idx: start_idx + len(group)] = new_chunks
            processed_count += len(group)

        if processed_count > 0:
            self._renumber()

        return processed_count

    def split_all_marked(self) -> int:
        """Splits all marked chunks using the sentence splitter."""
        split_count = 0
        i = 0
        while i < len(self.state.sentences):
            item = self.state.sentences[i]
            
            # GUARD: Do not batch-split chapter headings
            if item.get('is_chapter_heading'):
                i += 1
                continue
                
            if item.get('marked'):
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
