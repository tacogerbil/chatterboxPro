"""
Audio Artifact Detection for Chatterbox TTS Quality Control

Detects audio artifacts that ASR validation might miss:
- Swooshes (high-frequency energy spikes)
- Clicks/pops (excessive zero-crossing rate)
- Muffled audio (poor spectral rolloff)

MCCC: Pure function module, no side effects, fully testable.
"""

import numpy as np
import librosa
from pathlib import Path
from typing import Tuple, Optional
import logging


class ArtifactType:
    """Enumeration of detectable artifact types."""
    SWOOSH = "swoosh_detected"
    EXCESSIVE_NOISE = "excessive_noise"
    MUFFLED = "muffled_audio"
    CLIPPING = "clipping_detected"
    NONE = None


def detect_audio_artifacts(
    audio_path: str,
    text: str,
    swoosh_threshold: float = 2.5,
    zcr_threshold: float = 0.15,
    rolloff_threshold: float = 0.25
) -> Tuple[bool, Optional[str], float]:
    """
    Detects audio artifacts that ASR might miss.
    
    Args:
        audio_path: Path to audio file to analyze
        text: Expected text (for context/logging)
        swoosh_threshold: Multiplier for high-freq energy spike detection
        zcr_threshold: Maximum acceptable zero-crossing rate
        rolloff_threshold: Minimum spectral rolloff ratio
    
    Returns:
        (is_clean, artifact_type, confidence)
        - is_clean: True if audio passes all checks
        - artifact_type: Type of artifact detected (or None)
        - confidence: Confidence score 0.0-1.0
    """
    try:
        # Load audio
        y, sr = librosa.load(audio_path, sr=None)
        
        if len(y) == 0:
            logging.warning(f"Empty audio file: {audio_path}")
            return False, "empty_audio", 1.0
        
        # Check 1: High-frequency energy spikes (swooshes)
        is_clean, artifact, confidence = _check_high_freq_spikes(y, sr, swoosh_threshold)
        if not is_clean:
            return False, artifact, confidence
        
        # Check 2: Zero-crossing rate (clicks/pops)
        is_clean, artifact, confidence = _check_zero_crossing_rate(y, zcr_threshold)
        if not is_clean:
            return False, artifact, confidence
        
        # Check 3: Spectral rolloff (muffled audio)
        is_clean, artifact, confidence = _check_spectral_rolloff(y, sr, rolloff_threshold)
        if not is_clean:
            return False, artifact, confidence
        
        # Check 4: Clipping detection
        is_clean, artifact, confidence = _check_clipping(y)
        if not is_clean:
            return False, artifact, confidence
        
        # All checks passed
        return True, ArtifactType.NONE, 1.0
        
    except Exception as e:
        logging.error(f"Error analyzing audio {audio_path}: {e}")
        return False, "analysis_error", 0.5


def _check_high_freq_spikes(
    y: np.ndarray,
    sr: int,
    threshold: float
) -> Tuple[bool, Optional[str], float]:
    """
    Detects swooshes via high-frequency energy spikes.
    
    Swooshes typically have abnormal energy above 8kHz, especially at the end.
    """
    # Compute STFT
    stft = librosa.stft(y)
    freqs = librosa.fft_frequencies(sr=sr)
    
    # Focus on high frequencies (> 8kHz)
    high_freq_mask = freqs > 8000
    if not np.any(high_freq_mask):
        return True, None, 1.0  # Sample rate too low to detect
    
    high_freq_energy = np.abs(stft[high_freq_mask, :]).mean(axis=0)
    
    if len(high_freq_energy) < 10:
        return True, None, 1.0  # Audio too short
    
    # Check if energy spikes at the end
    end_energy = high_freq_energy[-10:].mean()
    middle_energy = high_freq_energy[:-10].mean()
    
    if middle_energy == 0:
        return True, None, 1.0  # Avoid division by zero
    
    spike_ratio = end_energy / middle_energy
    
    if spike_ratio > threshold:
        confidence = min(0.9, (spike_ratio - threshold) / threshold)
        logging.warning(f"Swoosh detected: end/middle ratio = {spike_ratio:.2f}")
        return False, ArtifactType.SWOOSH, confidence
    
    return True, None, 1.0


def _check_zero_crossing_rate(
    y: np.ndarray,
    threshold: float
) -> Tuple[bool, Optional[str], float]:
    """
    Detects clicks/pops via excessive zero-crossing rate.
    
    High ZCR indicates rapid polarity changes (clicks, pops, noise).
    """
    zcr = librosa.zero_crossings(y, pad=False)
    zcr_rate = zcr.sum() / len(y)
    
    if zcr_rate > threshold:
        confidence = min(0.9, (zcr_rate - threshold) / threshold)
        logging.warning(f"Excessive noise detected: ZCR = {zcr_rate:.3f}")
        return False, ArtifactType.EXCESSIVE_NOISE, confidence
    
    return True, None, 1.0


def _check_spectral_rolloff(
    y: np.ndarray,
    sr: int,
    threshold: float
) -> Tuple[bool, Optional[str], float]:
    """
    Detects muffled audio via poor spectral rolloff.
    
    Muffled audio has most energy in low frequencies.
    """
    rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr)[0]
    max_rolloff = rolloff.max()
    
    # Rolloff should be at least 25% of sample rate for clear audio
    min_acceptable = sr * threshold
    
    if max_rolloff < min_acceptable:
        confidence = min(0.9, (min_acceptable - max_rolloff) / min_acceptable)
        logging.warning(f"Muffled audio detected: rolloff = {max_rolloff:.0f}Hz")
        return False, ArtifactType.MUFFLED, confidence
    
    return True, None, 1.0


def _check_clipping(y: np.ndarray) -> Tuple[bool, Optional[str], float]:
    """
    Detects audio clipping (saturation).
    
    Clipping occurs when audio hits digital maximum (±1.0).
    """
    # Check for samples at or near maximum
    max_val = np.abs(y).max()
    
    if max_val >= 0.99:  # Close to clipping
        # Count how many samples are clipped
        clipped_samples = np.sum(np.abs(y) >= 0.99)
        clip_ratio = clipped_samples / len(y)
        
        if clip_ratio > 0.01:  # More than 1% clipped
            confidence = min(0.9, clip_ratio * 10)
            logging.warning(f"Clipping detected: {clip_ratio*100:.1f}% of samples")
            return False, ArtifactType.CLIPPING, confidence
    
    return True, None, 1.0


def get_artifact_description(artifact_type: Optional[str]) -> str:
    """Returns user-friendly description of artifact type."""
    descriptions = {
        ArtifactType.SWOOSH: "High-frequency swoosh sound detected at end of audio",
        ArtifactType.EXCESSIVE_NOISE: "Excessive clicks, pops, or noise detected",
        ArtifactType.MUFFLED: "Audio sounds muffled or lacks high-frequency clarity",
        ArtifactType.CLIPPING: "Audio is clipping (distortion from excessive volume)",
        "empty_audio": "Audio file is empty or corrupted",
        "analysis_error": "Error analyzing audio file",
    }
    return descriptions.get(artifact_type, "Unknown artifact type")


def extract_audio_features(audio_path: str) -> dict:
    """
    Extracts key prosody features for outlier detection (Scream Detector).
    
    Returns:
        Dictionary containing:
        - rms_mean: Average loudness
        - rms_max: Peak loudness
        - f0_mean: Average pitch (Hz)
        - f0_max: Peak pitch (Hz)
        - peak_amp: Absolute peak amplitude
        - duration: Total duration in seconds
    """
    try:
        y, sr = librosa.load(audio_path, sr=None)
        
        # 1. Loudness (RMS)
        rms = librosa.feature.rms(y=y)[0]
        rms_mean = float(np.mean(rms))
        rms_max = float(np.max(rms))
        peak_amp = float(np.max(np.abs(y)))
        
        # 2. Pitch (F0) using Yin algorithm
        # Restrict range to normal speech (50Hz - 600Hz) to avoid noise errors
        f0 = librosa.yin(y, fmin=50, fmax=600, sr=sr)
        # Filter out unvoiced parts (where Yin is unreliable) - naive approximation is good enough
        f0_valid = f0[f0 > 50] # Simple filtering
        
        if len(f0_valid) > 0:
            f0_mean = float(np.mean(f0_valid))
            f0_max = float(np.max(f0_valid))
        else:
            f0_mean = 0.0
            f0_max = 0.0
            
        return {
            'rms_mean': rms_mean,
            'rms_max': rms_max,
            'f0_mean': f0_mean,
            'f0_max': f0_max,
            'peak_amp': peak_amp,
            'duration': float(librosa.get_duration(y=y, sr=sr))
        }
    except Exception as e:
        logging.warning(f"Feature extraction failed for {audio_path}: {e}")
        return {}
