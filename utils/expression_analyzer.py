"""
Expression Analyzer for Chatterbox TTS

Automatically detects expression levels in text and suggests parameter adjustments:
- Detects quoted dialogue vs narration
- Detects exclamation marks (excitement)
- Detects question marks (curiosity)
- Detects ALL CAPS (shouting)
- Detects ellipsis (trailing off)


"""

import re
from dataclasses import dataclass
from typing import Tuple, List


@dataclass
class ExpressionProfile:
    """Represents detected expression characteristics and suggested TTS parameters."""
    temperature: float
    exaggeration: float
    speed: float
    reason: str
    detected_features: List[str]


# Base settings for different expression types
BASE_NARRATION = {'temp': 0.75, 'exag': 0.65, 'speed': 1.0}
BASE_DIALOGUE = {'temp': 0.85, 'exag': 0.80, 'speed': 1.0}


def analyze_expression(text: str, base_temp: float = 0.75, base_exag: float = 0.65) -> ExpressionProfile:
    """
    Analyzes text and returns suggested TTS parameters based on detected expression.
    
    Args:
        text: Text to analyze
        base_temp: Base temperature (used if no special features detected)
        base_exag: Base exaggeration (used if no special features detected)
    
    Returns:
        ExpressionProfile with suggested parameters
    """
    features = []
    temp = base_temp
    exag = base_exag
    speed = 1.0
    
    # Check 1: Is this dialogue?
    is_dialogue = detect_dialogue(text)
    if is_dialogue:
        features.append('dialogue')
        temp = BASE_DIALOGUE['temp']
        exag = BASE_DIALOGUE['exag']
    
    # Check 2: Exclamation marks (excitement/emphasis)
    exclamation_count = text.count('!')
    if exclamation_count > 0:
        features.append(f'exclamation_x{exclamation_count}')
        # Each ! adds +0.03 to exaggeration (max +0.15)
        exag = min(exag + (exclamation_count * 0.03), 0.95)
        
        # Multiple exclamations also increase temperature slightly
        if exclamation_count >= 2:
            temp = min(temp + 0.03, 0.92)
    
    # Check 3: Question marks (curiosity/uncertainty)
    question_count = text.count('?')
    if question_count > 0:
        features.append(f'question_x{question_count}')
        # Questions are slightly less exaggerated
        exag = max(exag - 0.02, 0.60)
    
    # Check 4: ALL CAPS (shouting)
    if detect_all_caps(text):
        features.append('all_caps')
        temp = 0.90
        exag = 0.90
        speed = 1.02  # Slightly faster for urgency
    
    # Check 5: Ellipsis (trailing off/hesitation)
    if '...' in text or '…' in text:
        features.append('ellipsis')
        exag = max(exag - 0.05, 0.60)
        speed = 0.97  # Slower, more hesitant
    
    # Check 6: Combined punctuation (!? or ?!)
    if '!?' in text or '?!' in text:
        features.append('combined_punctuation')
        exag = min(exag + 0.05, 0.92)
        temp = min(temp + 0.03, 0.90)
    
    # Build reason string
    if not features:
        reason = "Base narration (no special features)"
    else:
        reason = f"Detected: {', '.join(features)}"
    
    return ExpressionProfile(
        temperature=round(temp, 2),
        exaggeration=round(exag, 2),
        speed=round(speed, 2),
        reason=reason,
        detected_features=features
    )


def detect_dialogue(text: str) -> bool:
    """
    Detects if text is quoted dialogue.
    
    Args:
        text: Text to check
    
    Returns:
        True if text contains quoted dialogue
    """
    # Check for quotes at start/end or throughout
    text = text.strip()
    
    # Starts and ends with quotes
    if (text.startswith('"') and text.endswith('"')) or \
       (text.startswith("'") and text.endswith("'")):
        return True
    
    # Contains quoted sections
    if '"' in text or "'" in text:
        # Count quote pairs
        double_quotes = text.count('"')
        single_quotes = text.count("'")
        
        # If we have at least one pair, consider it dialogue
        if double_quotes >= 2 or single_quotes >= 2:
            return True
    
    return False


def detect_all_caps(text: str) -> bool:
    """
    Detects if text is shouting (ALL CAPS).
    
    Ignores:
    - Single-word caps (could be acronyms)
    - Text with no letters
    - Text shorter than 10 chars
    
    Args:
        text: Text to check
    
    Returns:
        True if text is shouting
    """
    # Remove quotes and punctuation for analysis
    clean_text = re.sub(r'["\',!?.;:]', '', text).strip()
    
    # Must have letters
    if not any(c.isalpha() for c in clean_text):
        return False
    
    # Must be at least 10 chars
    if len(clean_text) < 10:
        return False
    
    # Count uppercase vs total letters
    letters = [c for c in clean_text if c.isalpha()]
    uppercase = [c for c in letters if c.isupper()]
    
    # If 80%+ of letters are uppercase, it's shouting
    if len(letters) > 0:
        uppercase_ratio = len(uppercase) / len(letters)
        return uppercase_ratio >= 0.8
    
    return False


def get_expression_adjustment(
    text: str,
    current_temp: float,
    current_exag: float,
    sensitivity: float = 1.0
) -> Tuple[float, float, str]:
    """
    Gets suggested parameter adjustments based on text expression.
    
    Args:
        text: Text to analyze
        current_temp: Current temperature setting
        current_exag: Current exaggeration setting
        sensitivity: Multiplier for adjustments (0.5 = half, 2.0 = double)
    
    Returns:
        (adjusted_temp, adjusted_exag, reason)
    """
    profile = analyze_expression(text, current_temp, current_exag)
    
    # Apply sensitivity multiplier
    if sensitivity != 1.0:
        # Calculate delta from current
        temp_delta = (profile.temperature - current_temp) * sensitivity
        exag_delta = (profile.exaggeration - current_exag) * sensitivity
        
        adjusted_temp = current_temp + temp_delta
        adjusted_exag = current_exag + exag_delta
    else:
        adjusted_temp = profile.temperature
        adjusted_exag = profile.exaggeration
    
    # Clamp to valid ranges
    adjusted_temp = max(0.1, min(1.5, adjusted_temp))
    adjusted_exag = max(0.0, min(1.0, adjusted_exag))
    
    return adjusted_temp, adjusted_exag, profile.reason


def should_apply_expression_boost(text: str) -> bool:
    """
    Quick check if text has any expression features worth boosting.
    
    Returns:
        True if text has dialogue, exclamations, questions, or caps
    """
    return (
        detect_dialogue(text) or
        '!' in text or
        '?' in text or
        detect_all_caps(text) or
        '...' in text
    )
