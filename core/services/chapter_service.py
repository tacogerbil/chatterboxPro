from typing import List, Dict, Any, Tuple

class ChapterService:
    """
    Handles logic for chapter management:
    - Detecting chapters in sentence lists
    - Resolving selected chapters to sentence indices
    """
    
    def detect_chapters(self, sentences: List[Dict[str, Any]]) -> List[Tuple[int, Dict[str, Any]]]:
        """
        Scans sentences for 'is_chapter_heading' flag.
        Returns a list of (index, item) tuples.
        """
        found_chapters = []
        if not sentences:
            return found_chapters
            
        for i, item in enumerate(sentences):
            if item.get('is_chapter_heading'):
                found_chapters.append((i, item))
        
        return found_chapters

    def get_indices_for_chapters(self, 
                               all_sentences: List[Dict[str, Any]], 
                               chapter_indices: List[Tuple[int, Dict[str, Any]]], 
                               selected_chapter_indexes: List[int]) -> List[int]:
        """
        Given a list of selected *chapter* indices (0, 2, 5...),
        returns the list of *sentence* indices that belong to those chapters.
        """
        indices_to_process = []
        
        if not selected_chapter_indexes:
            return indices_to_process

        for ch_idx in selected_chapter_indexes:
            # Safety check
            if ch_idx >= len(chapter_indices):
                continue
                
            # Start is the index of the chapter heading
            start_real_index = chapter_indices[ch_idx][0]
            
            # End is the index of the next chapter heading, or the end of the list
            if ch_idx + 1 < len(chapter_indices):
                end_real_index = chapter_indices[ch_idx + 1][0]
            else:
                end_real_index = len(all_sentences)
                
            # Collect all indices in [start, end)
            indices_to_process.extend(range(start_real_index, end_real_index))
            
        # Ensure unique and sorted
        return sorted(list(set(indices_to_process)))
