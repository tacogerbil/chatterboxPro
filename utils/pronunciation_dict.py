"""
Pronunciation Dictionary for Chatterbox TTS

Allows users to define custom pronunciations for words that TTS might mispronounce:
- Fantasy/sci-fi character names
- Technical terms and acronyms
- Foreign words
- Brand names


"""

import json
import re
from pathlib import Path
from typing import Dict, List, Tuple
from dataclasses import dataclass, asdict


@dataclass
class PronunciationEntry:
    """Represents a pronunciation dictionary entry."""
    original: str
    pronunciation: str
    case_sensitive: bool = False
    whole_word_only: bool = True
    enabled: bool = True
    
    def to_dict(self) -> Dict:
        """Converts entry to dictionary for serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'PronunciationEntry':
        """Creates entry from dictionary."""
        return cls(**data)


class PronunciationDictionary:
    """Manages pronunciation replacements."""
    
    def __init__(self, dict_path: str = None):
        """
        Initializes pronunciation dictionary.
        
        Args:
            dict_path: Path to JSON dictionary file (optional)
        """
        self.dict_path = dict_path
        self.entries: List[PronunciationEntry] = []
        
        if dict_path and Path(dict_path).exists():
            self.load_from_file(dict_path)
        else:
            self._load_default_entries()
    
    def _load_default_entries(self) -> None:
        """Loads default pronunciation entries."""
        defaults = [
            # Common fantasy/sci-fi names
            PronunciationEntry("Hermione", "Her-my-oh-nee", whole_word_only=True),
            PronunciationEntry("Daenerys", "Duh-nair-iss", whole_word_only=True),
            PronunciationEntry("Khaleesi", "Kuh-lee-see", whole_word_only=True),
            PronunciationEntry("Tyrion", "Teer-ee-on", whole_word_only=True),
            PronunciationEntry("Sauron", "Sow-ron", whole_word_only=True),
            PronunciationEntry("Gandalf", "Gan-dalf", whole_word_only=True),
            
            # Technical terms
            PronunciationEntry("SQL", "sequel", case_sensitive=True, whole_word_only=True),
            PronunciationEntry("API", "A P I", case_sensitive=True, whole_word_only=True),
            PronunciationEntry("JSON", "jay-son", case_sensitive=True, whole_word_only=True),
            PronunciationEntry("regex", "reg-ex", whole_word_only=True),
            PronunciationEntry("async", "ay-sink", whole_word_only=True),
            
            # Common mispronunciations
            PronunciationEntry("GIF", "jiff", case_sensitive=True, whole_word_only=True),
            PronunciationEntry("meme", "meem", whole_word_only=True),
            PronunciationEntry("cache", "cash", whole_word_only=True),
        ]
        
        self.entries = defaults
    
    def add_entry(self, original: str, pronunciation: str, 
                  case_sensitive: bool = False, whole_word_only: bool = True) -> None:
        """
        Adds a new pronunciation entry.
        
        Args:
            original: Original word/phrase
            pronunciation: How to pronounce it
            case_sensitive: Whether to match case exactly
            whole_word_only: Whether to match whole words only
        """
        entry = PronunciationEntry(
            original=original,
            pronunciation=pronunciation,
            case_sensitive=case_sensitive,
            whole_word_only=whole_word_only,
            enabled=True
        )
        self.entries.append(entry)
    
    def remove_entry(self, original: str) -> bool:
        """
        Removes an entry by original word.
        
        Args:
            original: Original word to remove
        
        Returns:
            True if removed, False if not found
        """
        for i, entry in enumerate(self.entries):
            if entry.original == original:
                self.entries.pop(i)
                return True
        return False
    
    def apply_pronunciations(self, text: str) -> Tuple[str, List[str]]:
        """
        Applies pronunciation replacements to text.
        
        Args:
            text: Text to process
        
        Returns:
            (modified_text, list_of_replacements_made)
        """
        modified_text = text
        replacements_made = []
        
        for entry in self.entries:
            if not entry.enabled:
                continue
            
            # Build regex pattern
            if entry.whole_word_only:
                # Match whole words only
                if entry.case_sensitive:
                    pattern = r'\b' + re.escape(entry.original) + r'\b'
                    flags = 0
                else:
                    pattern = r'\b' + re.escape(entry.original) + r'\b'
                    flags = re.IGNORECASE
            else:
                # Match anywhere
                if entry.case_sensitive:
                    pattern = re.escape(entry.original)
                    flags = 0
                else:
                    pattern = re.escape(entry.original)
                    flags = re.IGNORECASE
            
            # Find matches
            matches = re.findall(pattern, modified_text, flags=flags)
            
            if matches:
                # Replace
                modified_text = re.sub(pattern, entry.pronunciation, modified_text, flags=flags)
                replacements_made.append(f"{entry.original} → {entry.pronunciation}")
        
        return modified_text, replacements_made
    
    def save_to_file(self, path: str = None) -> None:
        """
        Saves dictionary to JSON file.
        
        Args:
            path: Path to save to (uses self.dict_path if None)
        """
        save_path = path or self.dict_path
        if not save_path:
            raise ValueError("No path specified for saving")
        
        data = {
            'entries': [entry.to_dict() for entry in self.entries]
        }
        
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        
        with open(save_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def load_from_file(self, path: str) -> None:
        """
        Loads dictionary from JSON file.
        
        Args:
            path: Path to load from
        """
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        self.entries = [
            PronunciationEntry.from_dict(entry_data)
            for entry_data in data.get('entries', [])
        ]
        
        self.dict_path = path
    
    def get_entries(self) -> List[PronunciationEntry]:
        """Returns all entries."""
        return self.entries
    
    def clear_all(self) -> None:
        """Clears all entries."""
        self.entries = []
    
    def toggle_entry(self, original: str) -> bool:
        """
        Toggles an entry's enabled state.
        
        Args:
            original: Original word to toggle
        
        Returns:
            New enabled state, or None if not found
        """
        for entry in self.entries:
            if entry.original == original:
                entry.enabled = not entry.enabled
                return entry.enabled
        return None


def get_default_dict_path() -> str:
    """Returns default path for pronunciation dictionary."""
    from pathlib import Path
    return str(Path.home() / ".chatterboxpro" / "pronunciation_dict.json")


def create_default_dictionary() -> PronunciationDictionary:
    """Creates a dictionary with default entries."""
    dict_path = get_default_dict_path()
    dictionary = PronunciationDictionary(dict_path)
    
    # Save defaults if file doesn't exist
    if not Path(dict_path).exists():
        dictionary.save_to_file()
    
    return dictionary
