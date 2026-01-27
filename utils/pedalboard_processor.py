import logging
import soundfile as sf
import numpy as np
import subprocess
import os
from pathlib import Path

# MCCC: Modularity - Isolation of Audio Processing Logic
# MCCC: Side-Effect Isolation - File I/O isolated here

# Try to import pedalboard
print(f"[DEBUG] Attempting to import pedalboard...", flush=True)
try:
    from pedalboard import (
        Pedalboard, HighpassFilter, LowpassFilter, PeakFilter,
        Compressor, Distortion, PitchShift, Reverb
    )
    from pedalboard.io import AudioFile
    _PEDALBOARD_AVAILABLE = True
    print(f"[DEBUG] Pedalboard imported successfully.", flush=True)
except Exception as e:
    _PEDALBOARD_AVAILABLE = False
    print(f"[DEBUG] !!! PEDALBOARD IMPORT FAILED !!! Error: {e}", flush=True)
    logging.warning(f"Pedalboard not installed/working: {e}")


def _apply_speed_ffmpeg(input_path: str, output_path: str, speed: float) -> bool:
    """
    Helper to apply speed change using FFmpeg.
    Separated for MCCC Single Responsibility.
    """
    try:
        cmd = [
            'ffmpeg', '-y', '-i', str(input_path),
            '-filter:a', f"atempo={speed}",
            str(output_path)
        ]
        # Suppress output unless error
        subprocess.run(cmd, capture_output=True, check=True)
        return True
    except subprocess.CalledProcessError as e:
        logging.error(f"FFmpeg speed change failed: {e.stderr}")
        return False
    except Exception as e:
        logging.error(f"FFmpeg execution error: {e}")
        return False



def apply_pedalboard_effects(
    input_path: str,
    output_path: str,
    pitch_semitones: float = 0.0,
    timbre_shift: float = 0.0,
    gruffness: float = 0.0,
    speed: float = 1.0
) -> bool:
    """
    Apply "Narrator Polish" and "Batman Gravel" effects using Pedalboard.
    Handles Speed via FFmpeg (pre-process) if needed.
    
    Chain Logic:
    1. Speed (FFmpeg - if != 1.0)
    2. Pedalboard Chain:
       - HPF -> PitchShift -> EQ (Timbre/Resonance) -> Compressor -> Distortion -> Reverb
    
    Args:
        input_path: Input WAV path.
        output_path: Output WAV path.
        pitch_semitones: -12 to +12.
        timbre_shift: -3 to +3.
        gruffness: 0.0 to 1.0.
        speed: 0.5 to 2.0 (handled via ffmpeg atempo).
        
    Returns:
        True if successful, False otherwise.
    """
    if not _PEDALBOARD_AVAILABLE:
        # Fallback copy if pedalboard is missing
        if input_path != output_path:
            import shutil
            shutil.copy2(input_path, output_path)
        return False
        
    # Optimization: If no effects active, just copy
    if pitch_semitones == 0 and timbre_shift == 0 and gruffness == 0 and speed == 1.0:
        import shutil
        shutil.copy2(input_path, output_path)
        return True

    # Temporary path for speed processing intermediate
    # MCCC: Ensure temp files are cleaned up
    temp_speed_path = None
    processing_input = input_path
    
    try:
        # 1. Apply Speed (if needed)
        if speed != 1.0:
            temp_speed_path = str(input_path).replace('.wav', '_speed.wav')
            if _apply_speed_ffmpeg(input_path, temp_speed_path, speed):
                processing_input = temp_speed_path
            else:
                logging.warning("Speed change failed, proceeding with original audio.")

        # 2. Read Audio (from original or speed-altered temp)
        with AudioFile(processing_input) as f:
            audio = f.read(f.frames)
            sr = f.samplerate

        board_effects = []
        
        # --- Chain Construction ---
        
        # 1. Cleanup
        # Always good to cut rumble below 60Hz for clean speech
        board_effects.append(HighpassFilter(cutoff_frequency_hz=60.0))
        
        # 2. Pitch Shift
        # "Batman" element: Lower pitch slightly (-1.0 to -2.0)
        if pitch_semitones != 0:
            board_effects.append(PitchShift(semitones=pitch_semitones))
            
        # 3. Timbre / Formant Illusion / Throat Resonance
        # "Batman" element: Boost 150-400Hz for "throat rumble"
        # Timbre Shift (-3 to +3):
        # - Negative (Warmth): Boost low-mids (200-500Hz), Cut highs
        # - Positive (Bright): Cut low-mids, Boost highs (3-8kHz)
        
        # Base throat resonance (activated by Gruffness)
        if gruffness > 0:
            # "PeakFilter(220, gain_db=4.0, q=0.9)" - User recipe for throat resonance
            gain = gruffness * 4.0 # Up to +4dB
            board_effects.append(PeakFilter(center_frequency_hz=220.0, gain_db=gain, q=0.9))
            
        # User Timbre Slider (Global EQ color)
        if timbre_shift != 0:
            # Apply tilt-like EQ
            if timbre_shift < 0: # Warmer
                # Boost body (warmth)
                board_effects.append(PeakFilter(center_frequency_hz=350.0, gain_db=abs(timbre_shift)*2.0, q=1.0))
                # Cut harshness
                board_effects.append(PeakFilter(center_frequency_hz=3000.0, gain_db=timbre_shift*1.0, q=1.0)) # shift is neg, so this cuts
            else: # Brighter
                # Cut mud
                board_effects.append(PeakFilter(center_frequency_hz=300.0, gain_db=-abs(timbre_shift)*1.5, q=1.0))
                # Boost air/presence
                board_effects.append(PeakFilter(center_frequency_hz=4000.0, gain_db=abs(timbre_shift)*2.0, q=0.8))

        # 4. Compression
        # "Batman" element: "Compressor(threshold_db=-24, ratio=4.5)"
        # Bring forward the vocal fry
        if gruffness > 0:
            # Stronger compression for gravel
            board_effects.append(Compressor(threshold_db=-24.0, ratio=4.5, attack_ms=3.0, release_ms=120.0))
        else:
            # Standard narrator polish compression
            board_effects.append(Compressor(threshold_db=-18.0, ratio=2.5, attack_ms=5.0, release_ms=150.0))

        # 5. Saturation / Distortion
        # "Batman" element: "Distortion(drive_db=2.5)" - subtle saturation
        if gruffness > 0:
            # Scale 0.0-1.0 to 0.0-5.0 dB drive
            drive = gruffness * 5.0 
            board_effects.append(Distortion(drive_db=drive))
            
        # 6. Global Polish
        # Standard de-harshing Lowpass
        board_effects.append(LowpassFilter(cutoff_frequency_hz=14000.0))
        
        # 7. Reverb (Light Room)
        # Keeps it natural, avoids "dry booth" feeling
        board_effects.append(Reverb(room_size=0.1, wet_level=0.08))

        # --- Processing ---
        board = Pedalboard(board_effects)
        processed = board(audio, sr)

        # 8. Write Output
        # Ensure output is clipped/limited to prevent digital clipping if gain grew
        # Simple peak normalization if > 1.0 (or hard clip prevention)
        peak = np.max(np.abs(processed))
        if peak > 1.0:
            processed = processed / peak * 0.99  # Normalize to -0.1dB

        with AudioFile(output_path, "w", sr, processed.shape[0]) as f:
            f.write(processed)
            
        return True

    except Exception as e:
        logging.error(f"Pedalboard processing failed: {e}")
        # Fallback copy
        import shutil
        if input_path != output_path:
            shutil.copy2(input_path, output_path)
        return False
    finally:
        # MCCC: Cleanup side effects (temp files)
        if temp_speed_path and os.path.exists(temp_speed_path):
            try:
                os.remove(temp_speed_path)
            except OSError:
                pass
