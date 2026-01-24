# utils/voice_effects.py
"""
FFmpeg-based voice effects for post-processing TTS audio.
Provides pitch shifting, timbre adjustment, and gruffness effects.
"""

import subprocess
import os
import logging
from pathlib import Path

def check_ffmpeg_available():
    """Check if FFmpeg is available in PATH."""
    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

def apply_pitch_shift(input_path: str, output_path: str, semitones: float) -> bool:
    """
    Shift pitch by semitones without changing speed.
    
    Args:
        input_path: Path to input WAV file
        output_path: Path to output WAV file
        semitones: Pitch shift in semitones (-12 to +12)
                  Negative = lower pitch, Positive = higher pitch
    
    Returns:
        True if successful, False otherwise
    """
    if semitones == 0:
        # No change needed, just copy
        import shutil
        shutil.copy2(input_path, output_path)
        return True
    
    try:
        # Calculate pitch shift factor
        # Each semitone is 2^(1/12) ratio
        pitch_factor = 2 ** (semitones / 12.0)
        
        # Use asetrate + atempo to shift pitch without speed change
        # asetrate changes sample rate (affects pitch)
        # atempo compensates for speed change
        cmd = [
            'ffmpeg', '-y', '-i', input_path,
            '-af', f'asetrate=44100*{pitch_factor},atempo={1/pitch_factor}',
            '-ar', '24000',  # Resample to 24kHz for TTS consistency
            output_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return True
    except subprocess.CalledProcessError as e:
        logging.error(f"Pitch shift failed: {e.stderr}")
        return False
    except Exception as e:
        logging.error(f"Pitch shift error: {e}")
        return False

def apply_timbre_adjustment(input_path: str, output_path: str, formant_shift: float) -> bool:
    """
    Adjust vocal timbre/formant character.
    
    Args:
        input_path: Path to input WAV file
        output_path: Path to output WAV file
        formant_shift: Formant shift amount (-3 to +3)
                      Negative = warmer/darker, Positive = brighter/thinner
    
    Returns:
        True if successful, False otherwise
    """
    if formant_shift == 0:
        import shutil
        shutil.copy2(input_path, output_path)
        return True
    
    try:
        # Use EQ to simulate formant shifting
        # Negative shift = boost lows, cut highs (warmer)
        # Positive shift = cut lows, boost highs (brighter)
        
        # Scale factor for EQ adjustments
        eq_factor = formant_shift * 3  # Max ±9dB
        
        # Multi-band EQ to shift formants
        eq_filters = [
            f'equalizer=f=200:width_type=o:width=2:g={-eq_factor}',   # Low-mid
            f'equalizer=f=800:width_type=o:width=2:g={eq_factor*0.5}', # Mid
            f'equalizer=f=3000:width_type=o:width=2:g={eq_factor}',    # High-mid
            f'equalizer=f=8000:width_type=o:width=2:g={eq_factor*1.5}' # High
        ]
        
        filter_chain = ','.join(eq_filters)
        
        cmd = [
            'ffmpeg', '-y', '-i', input_path,
            '-af', filter_chain,
            output_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return True
    except subprocess.CalledProcessError as e:
        logging.error(f"Timbre adjustment failed: {e.stderr}")
        return False
    except Exception as e:
        logging.error(f"Timbre adjustment error: {e}")
        return False

def apply_gruffness(input_path: str, output_path: str, intensity: float) -> bool:
    """
    Add vocal gruffness/rasp/texture.
    
    Args:
        input_path: Path to input WAV file
        output_path: Path to output WAV file
        intensity: Gruffness intensity (0.0 to 1.0)
                  0 = clean, 1 = maximum gruffness
    
    Returns:
        True if successful, False otherwise
    """
    if intensity == 0:
        import shutil
        shutil.copy2(input_path, output_path)
        return True
    
    try:
        # Simulate gruffness with universally available filters:
        # 1. Boost volume slightly for saturation effect
        # 2. High-pass filter to emphasize breathiness
        # 3. Bass boost for depth
        # 4. Treble boost for edge
        
        # Scale intensity to effect parameters
        volume_boost = 1 + (intensity * 0.5)  # 1.0-1.5x volume
        bass_boost = intensity * 6  # 0-6dB bass boost
        treble_boost = intensity * 4  # 0-4dB treble boost
        
        filters = [
            # Slight volume boost for saturation
            f'volume={volume_boost}',
            # High-pass to emphasize breathiness
            f'highpass=f=120',
            # Bass boost for depth/gruffness
            f'bass=g={bass_boost}:f=200:w=1',
            # Treble boost for edge/rasp
            f'treble=g={treble_boost}:f=4000:w=1'
        ]
        
        filter_chain = ','.join(filters)
        
        cmd = [
            'ffmpeg', '-y', '-i', input_path,
            '-af', filter_chain,
            output_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return True
    except subprocess.CalledProcessError as e:
        logging.error(f"Gruffness effect failed: {e.stderr}")
        return False
    except Exception as e:
        logging.error(f"Gruffness effect error: {e}")
        return False

def apply_voice_effects(
    input_path: str, 
    output_path: str, 
    pitch: float = 0.0,
    timbre: float = 0.0,
    gruffness: float = 0.0
) -> bool:
    """
    Apply combined voice effects to audio file.
    
    Args:
        input_path: Path to input WAV file
        output_path: Path to output WAV file
        pitch: Pitch shift in semitones (-12 to +12)
        timbre: Timbre/formant shift (-3 to +3)
        gruffness: Gruffness intensity (0.0 to 1.0)
    
    Returns:
        True if successful, False otherwise
    """
    # Check if any effects are needed
    if pitch == 0 and timbre == 0 and gruffness == 0:
        import shutil
        shutil.copy2(input_path, output_path)
        return True
    
    if not check_ffmpeg_available():
        logging.error("FFmpeg not available - cannot apply voice effects")
        import shutil
        shutil.copy2(input_path, output_path)
        return False
    
    try:
        # Build combined filter chain for efficiency
        filters = []
        
        # Pitch shift
        if pitch != 0:
            pitch_factor = 2 ** (pitch / 12.0)
            filters.append(f'asetrate=44100*{pitch_factor}')
            filters.append(f'atempo={1/pitch_factor}')
        
        # Timbre adjustment (EQ-based formant shift)
        if timbre != 0:
            eq_factor = timbre * 3
            filters.extend([
                f'equalizer=f=200:width_type=o:width=2:g={-eq_factor}',
                f'equalizer=f=800:width_type=o:width=2:g={eq_factor*0.5}',
                f'equalizer=f=3000:width_type=o:width=2:g={eq_factor}',
                f'equalizer=f=8000:width_type=o:width=2:g={eq_factor*1.5}'
            ])
        
        # Gruffness
        if gruffness > 0:
            volume_boost = 1 + (gruffness * 0.5)
            bass_boost = gruffness * 6
            treble_boost = gruffness * 4
            filters.extend([
                f'volume={volume_boost}',
                'highpass=f=120',
                f'bass=g={bass_boost}:f=200:w=1',
                f'treble=g={treble_boost}:f=4000:w=1'
            ])
        
        # Combine all filters
        filter_chain = ','.join(filters)
        
        cmd = [
            'ffmpeg', '-y', '-i', input_path,
            '-af', filter_chain,
            '-ar', '24000',  # Resample to 24kHz
            output_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        logging.info(f"Applied voice effects: pitch={pitch}, timbre={timbre}, gruffness={gruffness}")
        return True
        
    except subprocess.CalledProcessError as e:
        logging.error(f"Voice effects failed: {e.stderr}")
        # Fallback: copy original
        import shutil
        shutil.copy2(input_path, output_path)
        return False
    except Exception as e:
        logging.error(f"Voice effects error: {e}")
        import shutil
        shutil.copy2(input_path, output_path)
        return False

# Test function
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    if not check_ffmpeg_available():
        print("ERROR: FFmpeg not found in PATH")
        exit(1)
    
    print("FFmpeg is available ✓")
    print("\nVoice effects module loaded successfully.")
    print("Use apply_voice_effects(input, output, pitch, timbre, gruffness) to process audio.")
