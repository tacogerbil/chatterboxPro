"""
Reference Audio Validation for Chatterbox TTS

Validates reference audio quality before generation to ensure optimal voice cloning results.
Checks for common issues that degrade Chatterbox TTS quality:
- Insufficient duration (< 10 seconds)
- Low sample rate (< 22050Hz)
- Stereo audio (Chatterbox works best with mono)
- Excessive silence (> 30%)
- Clipping/distortion

MCCC: Pure validation functions, no side effects, fully testable.
"""

from pathlib import Path
from typing import Tuple, Optional, List
import logging

try:
    from pydub import AudioSegment
    from pydub.silence import detect_silence
    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False
    logging.warning("pydub not available, reference audio validation will be limited")


class ValidationIssue:
    """Enumeration of validation issue types."""
    TOO_SHORT = "too_short"
    TOO_LONG = "too_long"
    LOW_SAMPLE_RATE = "low_sample_rate"
    STEREO = "stereo_audio"
    EXCESSIVE_SILENCE = "excessive_silence"
    CLIPPING = "clipping"
    FILE_ERROR = "file_error"


def validate_reference_audio(audio_path: str) -> Tuple[bool, List[str], List[str]]:
    """
    Validates reference audio for Chatterbox TTS quality.
    
    Args:
        audio_path: Path to reference audio file
    
    Returns:
        (is_valid, errors, warnings)
        - is_valid: True if audio passes all critical checks
        - errors: List of critical issues (prevent generation)
        - warnings: List of non-critical issues (suggest improvements)
    """
    if not PYDUB_AVAILABLE:
        return True, [], ["pydub not available, skipping reference audio validation"]
    
    errors = []
    warnings = []
    
    try:
        audio_path_obj = Path(audio_path)
        
        # Check file exists
        if not audio_path_obj.exists():
            errors.append(f"Reference audio file not found: {audio_path}")
            return False, errors, warnings
        
        # Load audio
        try:
            audio = AudioSegment.from_file(audio_path)
        except Exception as e:
            errors.append(f"Cannot load audio file: {e}")
            return False, errors, warnings
        
        # Check 1: Duration
        duration_sec = len(audio) / 1000.0
        if duration_sec < 10:
            errors.append(f"Reference audio too short ({duration_sec:.1f}s). Minimum 10 seconds recommended for Chatterbox.")
        elif duration_sec > 60:
            warnings.append(f"Reference audio is long ({duration_sec:.1f}s). 15-30 seconds is optimal for Chatterbox.")
        
        # Check 2: Sample Rate
        if audio.frame_rate < 22050:
            errors.append(f"Sample rate too low ({audio.frame_rate}Hz). Minimum 22050Hz required for quality voice cloning.")
        elif audio.frame_rate < 44100:
            warnings.append(f"Sample rate is {audio.frame_rate}Hz. 44100Hz or higher recommended for best quality.")
        
        # Check 3: Mono vs Stereo
        if audio.channels > 1:
            warnings.append(f"Audio is stereo ({audio.channels} channels). Chatterbox works best with mono. Consider converting to mono.")
        
        # Check 4: Silence Detection
        silence_ratio = _detect_silence_ratio(audio)
        if silence_ratio > 0.3:
            errors.append(f"Too much silence in reference audio ({silence_ratio*100:.1f}%). Should be < 30% for best results.")
        elif silence_ratio > 0.2:
            warnings.append(f"Reference audio has {silence_ratio*100:.1f}% silence. Lower is better for voice cloning.")
        
        # Check 5: Clipping Detection
        max_dbfs = audio.max_dBFS
        if max_dbfs > -1.0:
            errors.append(f"Audio is clipping (peak: {max_dbfs:.1f} dBFS). Reduce volume to prevent distortion.")
        elif max_dbfs > -3.0:
            warnings.append(f"Audio is close to clipping (peak: {max_dbfs:.1f} dBFS). Consider reducing volume slightly.")
        
        # Check 6: Overall loudness
        avg_dbfs = audio.dBFS
        if avg_dbfs < -30:
            warnings.append(f"Audio is very quiet (avg: {avg_dbfs:.1f} dBFS). Consider normalizing to -20 dBFS.")
        
        # Determine if valid
        is_valid = len(errors) == 0
        
        return is_valid, errors, warnings
        
    except Exception as e:
        logging.error(f"Error validating reference audio: {e}")
        errors.append(f"Validation error: {e}")
        return False, errors, warnings


def _detect_silence_ratio(audio: AudioSegment, silence_thresh: int = -40) -> float:
    """
    Detects the ratio of silence in audio.
    
    Args:
        audio: AudioSegment to analyze
        silence_thresh: Threshold in dBFS below which is considered silence
    
    Returns:
        Ratio of silence (0.0 to 1.0)
    """
    try:
        # Detect silent chunks (minimum 100ms)
        silent_chunks = detect_silence(
            audio,
            min_silence_len=100,
            silence_thresh=silence_thresh
        )
        
        # Calculate total silence duration
        total_silence_ms = sum(end - start for start, end in silent_chunks)
        total_duration_ms = len(audio)
        
        if total_duration_ms == 0:
            return 0.0
        
        return total_silence_ms / total_duration_ms
        
    except Exception as e:
        logging.warning(f"Error detecting silence: {e}")
        return 0.0


def get_validation_summary(errors: List[str], warnings: List[str]) -> str:
    """
    Creates a user-friendly summary of validation results.
    
    Args:
        errors: List of error messages
        warnings: List of warning messages
    
    Returns:
        Formatted summary string
    """
    if not errors and not warnings:
        return "✅ Reference audio is excellent quality!"
    
    summary_parts = []
    
    if errors:
        summary_parts.append("❌ ERRORS (must fix):")
        for i, error in enumerate(errors, 1):
            summary_parts.append(f"  {i}. {error}")
    
    if warnings:
        summary_parts.append("\n⚠️ WARNINGS (recommended fixes):")
        for i, warning in enumerate(warnings, 1):
            summary_parts.append(f"  {i}. {warning}")
    
    return "\n".join(summary_parts)


def get_quick_fixes(errors: List[str], warnings: List[str]) -> List[str]:
    """
    Suggests quick fixes for common issues.
    
    Args:
        errors: List of error messages
        warnings: List of warning messages
    
    Returns:
        List of actionable fix suggestions
    """
    fixes = []
    
    all_issues = errors + warnings
    
    for issue in all_issues:
        if "too short" in issue.lower():
            fixes.append("Record at least 10-15 seconds of clear speech")
        
        if "sample rate" in issue.lower():
            fixes.append("Re-export audio at 44100Hz or higher")
        
        if "stereo" in issue.lower():
            fixes.append("Convert to mono: Audacity → Tracks → Mix → Mix Stereo Down to Mono")
        
        if "silence" in issue.lower():
            fixes.append("Trim silence from beginning and end, speak continuously")
        
        if "clipping" in issue.lower():
            fixes.append("Reduce recording volume by 6dB and re-record")
        
        if "quiet" in issue.lower():
            fixes.append("Normalize audio to -20 dBFS (Audacity → Effect → Normalize)")
    
    # Remove duplicates while preserving order
    seen = set()
    unique_fixes = []
    for fix in fixes:
        if fix not in seen:
            seen.add(fix)
            unique_fixes.append(fix)
    
    return unique_fixes
