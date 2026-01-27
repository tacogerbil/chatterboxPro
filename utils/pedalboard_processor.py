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
    """
    board_effects = []
    
    # 0. Safety: Nyquist Limit
    nyquist = sample_rate / 2.0
    
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
            board_effects.append(PeakFilter(cutoff_frequency_hz=min(4000.0, nyquist*0.9), gain_db=abs(timbre_shift)*2.0, q=0.8))

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
    # SAFETY: Clamp Lowpass to be strictly below Nyquist (0.45 * SR is typically safe/audible limit)
    safe_cutoff = min(14000.0, nyquist * 0.9) 
    board_effects.append(LowpassFilter(cutoff_frequency_hz=safe_cutoff))
    
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
    # ... (Speed logic handled by caller or pre-check) ...
    # This block is just to fix the signature of build_pedalboard_chain call in line 158
    
    # ... I/O Logic starts (omitted for brevity in replacement, targeting only changed block) ...
    pass # Implementation detail, replace relevant block below

    
# REPLACEMENT AT TARGET

            effect_name = str(type(effect).__name__)
            try:
                # Create a mini-board for just this effect step
                mini_board = Pedalboard([effect])
                current_audio = mini_board(current_audio, sr)
                
                step_peak = np.max(np.abs(current_audio))
                print(f"[PEDALBOARD DEBUG] Step {i+1}: {effect_name} -> Peak: {step_peak:.4f}", flush=True)
                
                if np.isnan(current_audio).any():
                    print(f"[PEDALBOARD DEBUG] !!! NaN DETECTED after {effect_name} !!!", flush=True)
                    logging.error(f"Pedalboard NaN explosion at effect: {effect_name}")
                    return False
                    
            except Exception as e:
                 print(f"[PEDALBOARD DEBUG] Step {i+1} ({effect_name}) CRASHED: {e}", flush=True)
                 return False

        processed = current_audio

        # 8. Write Output to Temp File (MCCC: I/O Hygiene)
        # Prevents overwriting input while it might still be open/locked or read from
        import uuid
        temp_output_path = str(output_path).replace('.wav', f'_temp_{uuid.uuid4().hex[:8]}.wav')
        
        # Ensure output is clipped/limited
        if np.isnan(processed).any():
            logging.error("PEDALBOARD ERROR: Processed audio contains NaNs!")
            print("[PEDALBOARD DEBUG] !!! Processed Audio is NaN !!!", flush=True)
            return False

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
