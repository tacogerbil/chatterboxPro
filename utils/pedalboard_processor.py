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
        Compressor, Distortion, PitchShift, Reverb, Gain, Limiter
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

# --- Helper: Safety Logic ---
def get_safe_nyquist_clamp(hz: float, sample_rate: int) -> float:
    """Clamps frequency to 95% of Nyquist limit."""
    nyquist = sample_rate / 2.0
    limit = nyquist * 0.95
    return max(20.0, min(hz, limit))

# --- Chain 1: Main Voice (Intelligibility) ---
def _build_main_chain(
    sample_rate: int,
    pitch_semitones: float,
    timbre_shift: float
) -> Pedalboard:
    """
    Constructs the clean/intelligible signal path.
    """
    board_effects = []
    
    # 1. Highpass (Remove rumble before processing)
    board_effects.append(HighpassFilter(cutoff_frequency_hz=60.0))
    
    # 2. Main Pitch Shift (Subtle)
    if pitch_semitones != 0:
        safe_pitch = max(-24.0, min(pitch_semitones, 24.0))
        board_effects.append(PitchShift(semitones=safe_pitch))
        
    # 3. Timbre Shift (Formant)
    if timbre_shift != 0:
        if timbre_shift < 0: # Warmer/Darker
            f1 = get_safe_nyquist_clamp(350.0, sample_rate)
            f2 = get_safe_nyquist_clamp(3000.0, sample_rate)
            board_effects.append(PeakFilter(cutoff_frequency_hz=f1, gain_db=min(abs(timbre_shift)*2.0, 8.0), q=1.0))
            board_effects.append(PeakFilter(cutoff_frequency_hz=f2, gain_db=max(timbre_shift*1.0, -6.0), q=1.0))
        else: # Brighter
            f1 = get_safe_nyquist_clamp(300.0, sample_rate)
            f2 = get_safe_nyquist_clamp(4000.0, sample_rate)
            board_effects.append(PeakFilter(cutoff_frequency_hz=f1, gain_db=max(-abs(timbre_shift)*1.5, -8.0), q=1.0))
            board_effects.append(PeakFilter(cutoff_frequency_hz=f2, gain_db=min(abs(timbre_shift)*2.0, 8.0), q=0.8))
            
    # 4. Light Compression (Polish)
    board_effects.append(Compressor(threshold_db=-18.0, ratio=3.0, attack_ms=10.0, release_ms=100.0))
    
    # 5. Presence Boost (Intelligibility)
    f_pres = get_safe_nyquist_clamp(2500.0, sample_rate)
    board_effects.append(PeakFilter(cutoff_frequency_hz=f_pres, gain_db=2.0, q=0.7))

    return Pedalboard(board_effects)


# --- Chain 2: The "Grit" Layer (Rumble/Texture) ---
def _build_grit_chain(
    sample_rate: int,
    gruffness: float # 0.0 to 1.0
) -> Pedalboard:
    """
    Constructs the parallel distorted octave layer.
    """
    board_effects = []
    
    # 1. Octave Down (The Beast)
    # Fixed -12 semitones to create deep artificially generated sub-harmonics
    board_effects.append(PitchShift(semitones=-12.0))
    
    # 2. Heavy Distortion
    # Scale drive with gruffness: 10dB (mild) to 40dB (nuclear)
    drive = 10.0 + (gruffness * 30.0) 
    board_effects.append(Distortion(drive_db=drive))
    
    # 3. Lowpass (Remove Fizz/Harshness)
    # Essential! We only want the low rumble.
    # 600Hz usually nice, maybe up to 800Hz if very gruff.
    cutoff = 600.0 + (gruffness * 200.0) 
    board_effects.append(LowpassFilter(cutoff_frequency_hz=get_safe_nyquist_clamp(cutoff, sample_rate)))
    
    # 4. Smashed Compression (even out the rumble)
    board_effects.append(Compressor(threshold_db=-20.0, ratio=8.0, attack_ms=2.0, release_ms=50.0))
    
    return Pedalboard(board_effects)


# --- Chain 3: Master Bus (Space & Safety) ---
def _build_master_chain(
    sample_rate: int,
    reverb_room: float, 
    reverb_wet: float
) -> Pedalboard:
    board_effects = []
    
    # 1. Glue Compression
    board_effects.append(Compressor(threshold_db=-10.0, ratio=2.0, attack_ms=15.0, release_ms=100.0))

    # 2. Reverb (Subtle)
    if reverb_wet > 0:
        r_size = max(0.0, min(reverb_room, 1.0))
        r_wet = max(0.0, min(reverb_wet, 1.0))
        board_effects.append(Reverb(room_size=r_size, wet_level=r_wet))
        
    # 3. Final Limiter (Safety against clipping from adding signal paths)
    board_effects.append(Limiter(threshold_db=-1.0))
    
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
    Applies Parallel DSP Effects to an audio file.
    Orchestrates Main + Grit paths and mixes them.
    """
    # 0. Dependencies Check
    if not _PEDALBOARD_AVAILABLE:
        if input_path != output_path:
            shutil.copy2(input_path, output_path)
        return False
        
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
        if input_peak == 0:
            logging.warning("Pedalboard received SILENT input audio.")
            print("[PEDALBOARD DEBUG] Input is SILENT.", flush=True)

        # --- PARALLEL PROCESSING START ---
        
        # A. Main Chain (Always runs)
        main_board = _build_main_chain(sr, pitch_semitones, timbre_shift)
        audio_main = main_board(audio, sr)
        
        # B. Grit Chain (Run only if needed)
        audio_mixed = audio_main
        
        if gruffness > 0.01:
            grit_board = _build_grit_chain(sr, gruffness)
            audio_grit = grit_board(audio, sr)
            
            # Blend Logic
            # max mix = 40% grit at 1.0 gruffness
            grit_mix = min(gruffness * 0.40, 0.40) 
            
            # Ensure shapes match (PitchShift might alter length minutely?)
            # Usually safe, but robust coding requires checking.
            min_len = min(audio_main.shape[1], audio_grit.shape[1])
            audio_main = audio_main[:, :min_len]
            audio_grit = audio_grit[:, :min_len]
            
            # Summing (Superposition)
            # Main (kept high) + Grit (blended in)
            audio_mixed = audio_main + (audio_grit * grit_mix) 
            
        # C. Master Bus
        # Reduce reverb if gruff/heavy to prevent mud
        r_wet = 0.08 # Default subtle
        if gruffness > 0.2:
             r_wet = 0.04 # Dried out for clarity
             
        master_board = _build_master_chain(sr, reverb_room=0.15, reverb_wet=r_wet)
        final_audio = master_board(audio_mixed, sr)

        # --- PARALLEL PROCESSING END ---

        # 6. Safety Checks on Output
        if np.isnan(final_audio).any():
            logging.error("PEDALBOARD ERROR: Processed audio contains NaNs!")
            print("[PEDALBOARD DEBUG] !!! Processed Audio is NaN !!! - Aborting save.", flush=True)
            return False

        # 7. Write Output to Temp File (MCCC: I/O Hygiene)
        temp_output_path = str(output_path).replace('.wav', f'_temp_{uuid.uuid4().hex[:8]}.wav')
        
        with AudioFile(temp_output_path, "w", sr, final_audio.shape[0]) as f:
            f.write(final_audio)
            
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
