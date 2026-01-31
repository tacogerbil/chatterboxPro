"""
Semantic Chunking for Chatterbox TTS

Improved chunking strategy that:
- Respects sentence boundaries (no mid-sentence splits)
- Respects chapter markers (is_pause, is_chapter_heading)
- Targets 400 chars for optimal Chatterbox prosody
- Maintains minimum 200 chars for context

MCCC: Pure function, no side effects, fully testable.
"""

from typing import List, Dict, Any
import uuid


def semantic_chunk_sentences(
    sentences: List[Dict[str, Any]],
    target_chars: int = 400,
    min_chars: int = 200,
    max_chars: int = 500
) -> List[Dict[str, Any]]:
    """
    Chunks sentences semantically for optimal TTS quality.
    
    Key improvements over character-based chunking:
    - Respects sentence boundaries (never splits mid-sentence)
    - Respects chapter boundaries (is_pause, is_chapter_heading)
    - Targets 400 chars (vs 250) for better Chatterbox prosody
    - Maintains minimum context (200 chars)
    
    Args:
        sentences: List of sentence dictionaries with 'original_sentence' key
        target_chars: Target chunk size (400 recommended for Chatterbox)
        min_chars: Minimum chunk size (200 for context)
        max_chars: Maximum chunk size (500 hard limit)
    
    Returns:
        List of chunk dictionaries (may be individual sentences or combined chunks)
    """
    chunks = []
    current_chunk_sentences = []
    current_chunk_length = 0
    
    def finalize_chunk(chunk_sentences: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Combines multiple sentences into a single chunk."""
        if not chunk_sentences:
            return None
        
        if len(chunk_sentences) == 1:
            # Single sentence, return as-is
            return chunk_sentences[0]
        
        # Combine multiple sentences
        combined_text = " ".join(s.get('original_sentence', '') for s in chunk_sentences)
        
        # Create new chunk with combined text
        chunk = {
            'uuid': uuid.uuid4().hex,
            'original_sentence': combined_text,
            'tts_generated': 'no',
            'is_chapter_heading': False,
            'is_pause': False
        }
        
        # Track source UUIDs if available
        source_uuids = [s.get('uuid') for s in chunk_sentences if s.get('uuid')]
        if source_uuids:
            chunk['combined_from'] = source_uuids
        
        return chunk
    
    for sentence_data in sentences:
        sentence_text = sentence_data.get('original_sentence', '')
        sentence_len = len(sentence_text)
        
        # Handle chapter boundaries - never combine across these
        if sentence_data.get('is_chapter_heading') or sentence_data.get('is_pause'):
            # Finalize current chunk
            if current_chunk_sentences:
                chunk = finalize_chunk(current_chunk_sentences)
                if chunk:
                    chunks.append(chunk)
                current_chunk_sentences = []
                current_chunk_length = 0
            
            # Add boundary marker as-is
            chunks.append(sentence_data)
            continue
        
        # Handle very long sentences (> max_chars)
        if sentence_len > max_chars:
            # Finalize current chunk
            if current_chunk_sentences:
                chunk = finalize_chunk(current_chunk_sentences)
                if chunk:
                    chunks.append(chunk)
                current_chunk_sentences = []
                current_chunk_length = 0
            
            # Add long sentence as standalone chunk
            chunks.append(sentence_data)
            continue
        
        # Check if adding this sentence would exceed target
        space_needed = 1 if current_chunk_length > 0 else 0  # Space between sentences
        new_length = current_chunk_length + space_needed + sentence_len
        
        if new_length > target_chars and current_chunk_sentences:
            # Would exceed target, finalize current chunk
            
            # But check if current chunk is too small
            if current_chunk_length < min_chars:
                # Current chunk is too small, add this sentence anyway
                current_chunk_sentences.append(sentence_data)
                current_chunk_length = new_length
            else:
                # Current chunk is good size, finalize it
                chunk = finalize_chunk(current_chunk_sentences)
                if chunk:
                    chunks.append(chunk)
                
                # Start new chunk with this sentence
                current_chunk_sentences = [sentence_data]
                current_chunk_length = sentence_len
        else:
            # Add to current chunk
            current_chunk_sentences.append(sentence_data)
            current_chunk_length = new_length
    
    # Finalize last chunk
    if current_chunk_sentences:
        chunk = finalize_chunk(current_chunk_sentences)
        if chunk:
            chunks.append(chunk)
    
    # Add sentence numbers
    for i, chunk in enumerate(chunks):
        chunk['sentence_number'] = str(i + 1)
    
    return chunks


def get_chunking_stats(chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Returns statistics about chunking results.
    Useful for debugging and optimization.
    """
    if not chunks:
        return {
            'total_chunks': 0,
            'avg_length': 0,
            'min_length': 0,
            'max_length': 0,
            'combined_chunks': 0
        }
    
    lengths = []
    combined_count = 0
    
    for chunk in chunks:
        # Skip pause markers and chapter headings
        if chunk.get('is_pause') or chunk.get('is_chapter_heading'):
            continue
        
        text = chunk.get('original_sentence', '')
        lengths.append(len(text))
        
        if 'combined_from' in chunk:
            combined_count += 1
    
    if not lengths:
        return {
            'total_chunks': len(chunks),
            'avg_length': 0,
            'min_length': 0,
            'max_length': 0,
            'combined_chunks': 0
        }
    
    return {
        'total_chunks': len(chunks),
        'avg_length': sum(lengths) / len(lengths),
        'min_length': min(lengths),
        'max_length': max(lengths),
        'combined_chunks': combined_count,
        'text_chunks': len(lengths)
    }
