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



def build_pedalboard_chain(
    pitch_semitones: float = 0.0,
    timbre_shift: float = 0.0,
    gruffness: float = 0.0,
    reverb_room_size: float = 0.1,
    reverb_wet_level: float = 0.08
) -> Pedalboard:
    """
    Constructs the Pedalboard effect chain.
    Pure Function (MCCC: Logic Isolation).
    """
    board_effects = []
    
    # 1. Cleanup (Always active)
    board_effects.append(HighpassFilter(cutoff_frequency_hz=60.0))
    
    # 2. Pitch Shift
    if pitch_semitones != 0:
        board_effects.append(PitchShift(semitones=pitch_semitones))
        
    # 3. Timbre / Formant Illusion
    if gruffness > 0:
        # Throat resonance gain
        gain = gruffness * 4.0 
        board_effects.append(PeakFilter(cutoff_frequency_hz=220.0, gain_db=gain, q=0.9))
        
    if timbre_shift != 0:
        if timbre_shift < 0: # Warmer
            board_effects.append(PeakFilter(cutoff_frequency_hz=350.0, gain_db=abs(timbre_shift)*2.0, q=1.0))
            board_effects.append(PeakFilter(cutoff_frequency_hz=3000.0, gain_db=timbre_shift*1.0, q=1.0))
        else: # Brighter
            board_effects.append(PeakFilter(cutoff_frequency_hz=300.0, gain_db=-abs(timbre_shift)*1.5, q=1.0))
            board_effects.append(PeakFilter(cutoff_frequency_hz=4000.0, gain_db=abs(timbre_shift)*2.0, q=0.8))

    # 4. Compression
    if gruffness > 0:
        # Aggressive for gravel
        board_effects.append(Compressor(threshold_db=-24.0, ratio=4.5, attack_ms=3.0, release_ms=120.0))
    else:
        # Standard polish
        board_effects.append(Compressor(threshold_db=-18.0, ratio=2.5, attack_ms=5.0, release_ms=150.0))

    # 5. Distortion
    if gruffness > 0:
        drive = gruffness * 5.0 
        board_effects.append(Distortion(drive_db=drive))
        
    # 6. Global Polish
    board_effects.append(LowpassFilter(cutoff_frequency_hz=14000.0))
    
    # 7. Reverb
    if reverb_wet_level > 0:
        board_effects.append(Reverb(room_size=reverb_room_size, wet_level=reverb_wet_level))

    return Pedalboard(board_effects)


def apply_pedalboard_effects(
    input_path: str,
    output_path: str,
    pitch_semitones: float = 0.0,
    timbre_shift: float = 0.0,
    gruffness: float = 0.0,
    speed: float = 1.0
) -> bool:
    """
    Applies effects to an audio file.
    Wrapper for I/O + Speed + Chain Execution.
    """
    # ... I/O Logic ... (unchanged parts handled below)
    
    # ... (Start of I/O Block) ...
    if not _PEDALBOARD_AVAILABLE:
        if input_path != output_path:
            import shutil
            shutil.copy2(input_path, output_path)
        return False
        
    # Optimization check
    if pitch_semitones == 0 and timbre_shift == 0 and gruffness == 0 and speed == 1.0:
        import shutil
        shutil.copy2(input_path, output_path)
        return True

    temp_speed_path = None
    processing_input = input_path
    
    try:
        # 1. Apply Speed (FFmpeg)
        if speed != 1.0:
            temp_speed_path = str(input_path).replace('.wav', '_speed.wav')
            if _apply_speed_ffmpeg(input_path, temp_speed_path, speed):
                processing_input = temp_speed_path
            else:
                logging.warning("Speed change failed, proceeding with original audio.")

        # 2. Read Audio
        with AudioFile(processing_input) as f:
            audio = f.read(f.frames)
            sr = f.samplerate
            
        # DIAGNOSTIC: Check Input Signal
        input_peak = np.max(np.abs(audio))
        print(f"[PEDALBOARD DEBUG] Input Audio Peak: {input_peak:.4f}", flush=True)
        if input_peak == 0:
            logging.warning("Pedalboard received SILENT input audio.")

        # 3. Build & Run Chain
        # Calls the Pure Function
        board = build_pedalboard_chain(
            pitch_semitones=pitch_semitones,
            timbre_shift=timbre_shift,
            gruffness=gruffness
        )
        processed = board(audio, sr)

        # 8. Write Output to Temp File (MCCC: I/O Hygiene)
        # Prevents overwriting input while it might still be open/locked or read from
        import uuid
        temp_output_path = str(output_path).replace('.wav', f'_temp_{uuid.uuid4().hex[:8]}.wav')
        
        # Ensure output is clipped/limited
        peak = np.max(np.abs(processed))
        print(f"[PEDALBOARD DEBUG] Processed Output Peak: {peak:.4f}", flush=True)

        if peak > 1.0:
            processed = processed / peak * 0.99 

        with AudioFile(temp_output_path, "w", sr, processed.shape[0]) as f:
            f.write(processed)
            
        # 9. Move Temp to Final
        import shutil
        shutil.move(temp_output_path, output_path)
            
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
