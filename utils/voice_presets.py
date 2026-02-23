"""
Exaggeration Presets for Chatterbox TTS

Provides pre-configured temperature and exaggeration settings optimized for different content types.
Users can quickly switch between presets instead of manually tuning parameters.


"""

from dataclasses import dataclass
from typing import Dict, List


@dataclass
class VoicePreset:
    """Represents a voice preset with temperature and exaggeration settings."""
    name: str
    description: str
    temperature: float
    exaggeration: float
    speed: float = 1.0
    
    def to_dict(self) -> Dict[str, any]:
        """Converts preset to dictionary for serialization."""
        return {
            'name': self.name,
            'description': self.description,
            'temperature': self.temperature,
            'exaggeration': self.exaggeration,
            'speed': self.speed
        }


# ============================================================================
# BUILT-IN PRESETS
# ============================================================================

AUDIOBOOK_NARRATION = VoicePreset(
    name="Audiobook Narration",
    description="Calm, professional narration for general audiobooks. Balanced and natural.",
    temperature=0.75,
    exaggeration=0.65,
    speed=1.0
)

CHARACTER_DIALOGUE = VoicePreset(
    name="Character Dialogue",
    description="Expressive dialogue for character conversations. More dynamic and engaging.",
    temperature=0.85,
    exaggeration=0.80,
    speed=1.0
)

DOCUMENTARY_TECHNICAL = VoicePreset(
    name="Documentary/Technical",
    description="Authoritative, measured tone for non-fiction, technical, or educational content.",
    temperature=0.70,
    exaggeration=0.55,
    speed=0.98
)

ACTION_THRILLER = VoicePreset(
    name="Action/Thriller",
    description="High energy, dramatic delivery for action scenes and thrillers.",
    temperature=0.90,
    exaggeration=0.85,
    speed=1.02
)

CHILDRENS_BOOK = VoicePreset(
    name="Children's Book",
    description="Playful, animated narration for children's stories. Very expressive.",
    temperature=0.88,
    exaggeration=0.90,
    speed=1.0
)

ROMANCE_INTIMATE = VoicePreset(
    name="Romance/Intimate",
    description="Warm, emotional delivery for romance and intimate scenes.",
    temperature=0.82,
    exaggeration=0.75,
    speed=0.97
)

HORROR_SUSPENSE = VoicePreset(
    name="Horror/Suspense",
    description="Tense, atmospheric narration for horror and suspense.",
    temperature=0.78,
    exaggeration=0.70,
    speed=0.95
)


# ============================================================================
# PRESET REGISTRY
# ============================================================================

BUILTIN_PRESETS: List[VoicePreset] = [
    AUDIOBOOK_NARRATION,
    CHARACTER_DIALOGUE,
    DOCUMENTARY_TECHNICAL,
    ACTION_THRILLER,
    CHILDRENS_BOOK,
    ROMANCE_INTIMATE,
    HORROR_SUSPENSE
]


def get_preset_by_name(name: str) -> VoicePreset:
    """
    Retrieves a preset by name.
    
    Args:
        name: Name of the preset
    
    Returns:
        VoicePreset if found, otherwise AUDIOBOOK_NARRATION as default
    """
    for preset in BUILTIN_PRESETS:
        if preset.name == name:
            return preset
    
    # Default fallback
    return AUDIOBOOK_NARRATION


def get_preset_names() -> List[str]:
    """Returns list of all preset names."""
    return [preset.name for preset in BUILTIN_PRESETS]


def apply_preset_to_state(preset: VoicePreset, state) -> None:
    """
    Applies a preset to the application state.
    
    Args:
        preset: VoicePreset to apply
        state: Application state object (modified in-place)
    """
    state.temperature = preset.temperature
    state.exaggeration = preset.exaggeration
    # Speed is not currently in state, but could be added in future


def get_current_preset_name(state) -> str:
    """
    Determines which preset (if any) matches current state settings.
    
    Args:
        state: Application state object
    
    Returns:
        Preset name if exact match found, otherwise "Custom"
    """
    current_temp = state.temperature
    current_exag = state.exaggeration
    
    for preset in BUILTIN_PRESETS:
        # Check for exact match (within 0.01 tolerance)
        if (abs(preset.temperature - current_temp) < 0.01 and
            abs(preset.exaggeration - current_exag) < 0.01):
            return preset.name
    
    return "Custom"


def get_preset_description(name: str) -> str:
    """Returns description for a preset by name."""
    preset = get_preset_by_name(name)
    return preset.description


def format_preset_display(preset: VoicePreset) -> str:
    """
    Formats preset for display in UI.
    
    Returns:
        Formatted string like "Audiobook Narration (temp: 0.75, exag: 0.65)"
    """
    return f"{preset.name} (temp: {preset.temperature:.2f}, exag: {preset.exaggeration:.2f})"
