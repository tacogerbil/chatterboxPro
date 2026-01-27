import logging
import soundfile as sf
import numpy as np
import subprocess
import os
import uuid
import shutil
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
    sample_rate: int = 44100,
    pitch_semitones: float = 0.0,
    timbre_shift: float = 0.0,
    gruffness: float = 0.0,
    reverb_room_size: float = 0.1,
    reverb_wet_level: float = 0.08
) -> Pedalboard:
    """
    Constructs the Pedalboard effect chain.
    Pure Function (MCCC: Logic Isolation).
    Includes Safety Clamps for Nyquist and Parameter Ranges.
    """
    board_effects = []
    
    # 0. Safety: Nyquist Limit
    # Ensure we never request a center/cutoff frequency >= Nyquist
    nyquist = sample_rate / 2.0
    safe_max_freq = nyquist * 0.95  # 5% safety margin
    safe_min_freq = 20.0 # Standard low end
    
    def clamp_freq(f: float) -> float:
        return max(safe_min_freq, min(f, safe_max_freq))

    # 1. Cleanup (Always active) - Fixed Low Cut
    board_effects.append(HighpassFilter(cutoff_frequency_hz=60.0))
    
    # 2. Pitch Shift
    if pitch_semitones != 0:
        # Range check: +/- 24 semitones is reasonable max
        safe_pitch = max(-24.0, min(pitch_semitones, 24.0))
        board_effects.append(PitchShift(semitones=safe_pitch))
        
    # 3. Timbre / Formant Illusion
    # MCCC: Audit - Ensure gains don't blow out signal
    if gruffness > 0:
        # Throat resonance gain
        gain = min(gruffness * 4.0, 12.0) # Clamp gain max 12dB
        board_effects.append(PeakFilter(cutoff_frequency_hz=220.0, gain_db=gain, q=0.9))
        
    if timbre_shift != 0:
        if timbre_shift < 0: # Warmer (Darker)
            f1 = clamp_freq(350.0)
            f2 = clamp_freq(3000.0)
            board_effects.append(PeakFilter(cutoff_frequency_hz=f1, gain_db=min(abs(timbre_shift)*2.0, 12.0), q=1.0))
            board_effects.append(PeakFilter(cutoff_frequency_hz=f2, gain_db=min(timbre_shift*1.0, 6.0), q=1.0)) # negative gain
        else: # Brighter
            f1 = clamp_freq(300.0)
            target_f2 = 4000.0
            
            board_effects.append(PeakFilter(cutoff_frequency_hz=f1, gain_db=max(-abs(timbre_shift)*1.5, -12.0), q=1.0))
            
            # Only add high boost if safely within Nyquist
            if target_f2 < safe_max_freq:
                f2 = clamp_freq(target_f2)
                board_effects.append(PeakFilter(cutoff_frequency_hz=f2, gain_db=min(abs(timbre_shift)*2.0, 12.0), q=0.8))

    # 4. Compression
    if gruffness > 0:
        # Aggressive for gravel
        board_effects.append(Compressor(threshold_db=-24.0, ratio=4.5, attack_ms=3.0, release_ms=120.0))
    else:
        # Standard polish
        board_effects.append(Compressor(threshold_db=-18.0, ratio=2.5, attack_ms=5.0, release_ms=150.0))
    
    # 5. Distortion
    if gruffness > 0:
        drive = min(gruffness * 5.0, 24.0) # Cap drive to safeguard ears
        board_effects.append(Distortion(drive_db=drive))
        
    # 6. Global Polish
    # SAFETY: Clamp Lowpass to be strictly below Nyquist
    # If SR is low (24k), Nyquist is 12k. 14k would crash.
    # We ideally want 14k, but MUST cap at Safe Max.
    polish_cutoff = clamp_freq(14000.0)
    board_effects.append(LowpassFilter(cutoff_frequency_hz=polish_cutoff))
    
    # 7. Reverb
    if reverb_wet_level > 0:
        # Clamp Reverb params to 0.0-1.0
        r_size = max(0.0, min(reverb_room_size, 1.0))
        r_wet = max(0.0, min(reverb_wet_level, 1.0))
        board_effects.append(Reverb(room_size=r_size, wet_level=r_wet))

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
    # 0. Dependencies Check
    if not _PEDALBOARD_AVAILABLE:
        if input_path != output_path:
            shutil.copy2(input_path, output_path)
        return False
        
    # 1. Optimization check (No-Op)
    if pitch_semitones == 0 and timbre_shift == 0 and gruffness == 0 and speed == 1.0:
        logging.info("Pedalboard: No effects requested, pass-through.")
        if input_path != output_path:
            shutil.copy2(input_path, output_path)
        return True

    temp_speed_path = None
    processing_input = input_path
    
    try:
        # 2. Apply Speed (FFmpeg) - Handled separately as Pedalboard is focusing on VST-like effects
        if speed != 1.0:
            temp_speed_path = str(input_path).replace('.wav', '_speed.wav')
            if _apply_speed_ffmpeg(input_path, temp_speed_path, speed):
                processing_input = temp_speed_path
            else:
                logging.warning("Speed change failed, proceeding with original audio.")

        # 3. Read Audio
        with AudioFile(processing_input) as f:
            audio = f.read(f.frames)
            sr = f.samplerate
            
        # DIAGNOSTIC: Check Input Signal
        input_peak = np.max(np.abs(audio))
        if input_peak == 0:
            logging.warning("Pedalboard received SILENT input audio.")
            print("[PEDALBOARD DEBUG] Input is SILENT.", flush=True)

        # 4. Build Chain - PASSING SAMPLE RATE (Critical Logic)
        board = build_pedalboard_chain(
            sample_rate=sr,
            pitch_semitones=pitch_semitones,
            timbre_shift=timbre_shift,
            gruffness=gruffness
        )
        
        # 5. Process Audio
        # Restore standard execution (diagnostics removed for production/speed)
        # Using implicit __call__
        processed = board(audio, sr)

        # 6. Safety Checks on Output
        if np.isnan(processed).any():
            logging.error("PEDALBOARD ERROR: Processed audio contains NaNs!")
            print("[PEDALBOARD DEBUG] !!! Processed Audio is NaN !!! - Aborting save.", flush=True)
            return False

        # Clip excessive peaks (Limiter)
        peak = np.max(np.abs(processed))
        if peak > 1.0:
            logging.info(f"Pedalboard: Soft clipping peak {peak:.2f} -> 0.99")
            processed = processed / peak * 0.99 

        # 7. Write Output to Temp File (MCCC: I/O Hygiene)
        # Prevents overwriting input while it might still be open/locked or read from
        temp_output_path = str(output_path).replace('.wav', f'_temp_{uuid.uuid4().hex[:8]}.wav')
        
        with AudioFile(temp_output_path, "w", sr, processed.shape[0]) as f:
            f.write(processed)
            
        # 8. Move Temp to Final (Atomic)
        shutil.move(temp_output_path, output_path)
        return True

    except Exception as e:
        logging.error(f"Pedalboard processing failed: {e}")
        print(f"[PEDALBOARD DEBUG] Crash: {e}", flush=True)
        # Fallback copy
        if input_path != output_path:
            try:
                shutil.copy2(input_path, output_path)
            except:
                pass
        return False
    finally:
        # MCCC: Cleanup side effects (temp files)
        if temp_speed_path and os.path.exists(temp_speed_path):
            try:
                os.remove(temp_speed_path)
            except OSError:
                pass
