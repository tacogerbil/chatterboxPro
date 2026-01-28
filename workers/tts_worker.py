# workers/tts_worker.py
import sys
import os
import re
import random
import logging
from pathlib import Path
import shutil
import difflib
import numpy as np

import torch
import torchaudio
import soundfile as sf

# Chatterbox-specific imports
from chatterbox.tts import ChatterboxTTS
import whisper
from utils.pedalboard_processor import apply_pedalboard_effects # MCCC: Use external processor
# --- DEBUG: ASK PYTHON WHERE FFMPEG IS ---
print(f"\n[DEBUG] Python executable: {sys.executable}")
ffmpeg_location = shutil.which("ffmpeg")
if ffmpeg_location:
    print(f"[DEBUG] SUCCESS: Found ffmpeg at: {ffmpeg_location}")
else:
    print(f"[DEBUG] FAILURE: Python cannot find 'ffmpeg' in the system PATH.")
    # Print the path so you can see if your hard work was ignored
    print(f"[DEBUG] Current PATH: {os.environ['PATH']}\n")
# -----------------------------------------

# --- WINDOWS FFMPEG FIX ---
# Force Python to see the FFmpeg executable inside Conda
if os.name == 'nt':  # Check if we are on Windows
    # The ffmpeg.exe lives in Env/Library/bin
    ffmpeg_bin = os.path.join(sys.prefix, 'Library', 'bin')
    if os.path.exists(ffmpeg_bin):
        os.environ["PATH"] += os.pathsep + ffmpeg_bin
# --------------------------

# --- Worker-Specific Globals ---
_WORKER_TTS_ENGINE, _WORKER_WHISPER_MODEL = None, None
_CURRENT_ENGINE_NAME = None
_CURRENT_MODEL_PATH = None

def get_or_init_worker_models(device_str: str, engine_name: str = 'chatterbox', model_path: str = None):
    """Initializes models once per worker process to save memory and time."""
    global _WORKER_TTS_ENGINE, _WORKER_WHISPER_MODEL, _CURRENT_ENGINE_NAME, _CURRENT_MODEL_PATH
    pid = os.getpid()
    
    # Check if we need to switch engines OR switch model paths
    config_changed = False
    if _WORKER_TTS_ENGINE is not None:
        if _CURRENT_ENGINE_NAME != engine_name:
            logging.info(f"[Worker-{pid}] Engine switch: {_CURRENT_ENGINE_NAME} -> {engine_name}")
            config_changed = True
        elif _CURRENT_MODEL_PATH != model_path:
            logging.info(f"[Worker-{pid}] Model path switch: {_CURRENT_MODEL_PATH} -> {model_path}")
            config_changed = True
            
    if config_changed and _WORKER_TTS_ENGINE is not None:
        _WORKER_TTS_ENGINE.cleanup()
        _WORKER_TTS_ENGINE = None
    
    if _WORKER_TTS_ENGINE is None:
        logging.info(f"[Worker-{pid}] Initializing {engine_name} engine on device: {device_str}")
        try:
            from engines import get_engine
            # Pass model_path via kwargs
            _WORKER_TTS_ENGINE = get_engine(engine_name, device_str, model_path=model_path)
            _CURRENT_ENGINE_NAME = engine_name
            _CURRENT_MODEL_PATH = model_path
            
            whisper_device = torch.device(device_str if "cuda" in device_str and torch.cuda.is_available() else "cpu")
            _WORKER_WHISPER_MODEL = whisper.load_model("base.en", device=whisper_device, download_root=str(Path.home() / ".cache" / "whisper"))
            logging.info(f"[Worker-{pid}] {engine_name} engine loaded successfully on {device_str}.")
        except Exception as e:
            logging.critical(f"[Worker-{pid}] CRITICAL ERROR: Failed to initialize models: {e}", exc_info=True)
            _WORKER_TTS_ENGINE, _WORKER_WHISPER_MODEL = None, None
            raise
    return _WORKER_TTS_ENGINE, _WORKER_WHISPER_MODEL

def set_seed(seed: int):
    """Sets random seeds for reproducibility."""
    import numpy as np
    torch.manual_seed(seed)
    random.seed(seed)
    np.random.seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)

def validate_audio_signal(wav_tensor, sr):
    """
    Checks for signal-level artifacts like constant clipping (screeching) or excessive noise (ZCR).
    Returns (Passed: bool, Reason: str)
    """
    # Ensure tensor is CPU and flat
    if wav_tensor.dim() > 1:
        wav_tensor = wav_tensor.squeeze()
    
    # Check 1: Amplitude Saturation / constant clipping
    # If a large percentage of samples are near the limits (-1.0 or 1.0), it's likely digital screaming.
    # Checks if > 25% of samples are > 0.95 amp. (Generous threshold, real speech rarely sustains this)
    abs_wav = torch.abs(wav_tensor)
    saturation_ratio = (abs_wav > 0.95).float().mean().item()
    if saturation_ratio > 0.25:
        return False, f"Amplitude Saturation ({saturation_ratio:.1%})"
        
    # Check 2: Zero Crossing Rate (ZCR)
    # High ZCR indicates high-frequency noise.
    # Simple ZCR implementation
    zcr = ((wav_tensor[:-1] * wav_tensor[1:]) < 0).float().mean().item()
    
    # Speech usually has low ZCR. Sibilants ('s') can be high (~0.3-0.4).
    # White noise is ~0.5.
    # We set a high threshold to only catch pure static/noise.
    if zcr > 0.45:
        return False, f"High ZCR ({zcr:.2f})"
        
    return True, "OK"

def normalize_numbers(text):
    """Convert written number words to digits for consistent ASR comparison.
    
    Whisper often transcribes spoken numbers as digits (e.g., "one" → "1"),
    even when the TTS model correctly says the word. This function normalizes
    both texts to use digits before comparison.
    
    Handles:
    - Single digits: "one" → "1"
    - Teens: "thirteen" → "13"
    - Tens: "twenty" → "20"
    - Compound: "twenty-three" → "23", "twenty three" → "23"
    - Hundreds: "one hundred" → "100", "one hundred fifty" → "150"
    - Thousands: "two thousand" → "2000", "two thousand twenty-four" → "2024"
    """
    text_lower = text.lower()
    
    # Single number words (for direct replacement and compound building)
    ones = {
        'zero': 0, 'one': 1, 'two': 2, 'three': 3, 'four': 4,
        'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9
    }
    teens = {
        'ten': 10, 'eleven': 11, 'twelve': 12, 'thirteen': 13, 'fourteen': 14,
        'fifteen': 15, 'sixteen': 16, 'seventeen': 17, 'eighteen': 18, 'nineteen': 19
    }
    tens = {
        'twenty': 20, 'thirty': 30, 'forty': 40, 'fifty': 50,
        'sixty': 60, 'seventy': 70, 'eighty': 80, 'ninety': 90
    }
    
    # Pattern for compound numbers - process from most specific to least specific
    import re
    
    # Pattern: "X thousand Y hundred Z" (e.g., "two thousand three hundred forty-two")
    text_lower = re.sub(
        r'\b(one|two|three|four|five|six|seven|eight|nine)\s+thousand\s+(one|two|three|four|five|six|seven|eight|nine)\s+hundred\s+(?:and\s+)?(\w+(?:\s+|-)\w+|\w+)',
        lambda m: str(_parse_compound_number(m.group(0), ones, teens, tens)),
        text_lower
    )
    
    # Pattern: "X thousand Y hundred" (e.g., "five thousand three hundred")
    text_lower = re.sub(
        r'\b(one|two|three|four|five|six|seven|eight|nine)\s+thousand\s+(one|two|three|four|five|six|seven|eight|nine)\s+hundred\b',
        lambda m: str(_parse_compound_number(m.group(0), ones, teens, tens)),
        text_lower
    )
    
    # Pattern: "X thousand Y" where Y is a compound/teen/ten (e.g., "two thousand twenty-four")
    text_lower = re.sub(
        r'\b(one|two|three|four|five|six|seven|eight|nine)\s+thousand\s+(\w+(?:\s+|-)\w+|\w+)',
        lambda m: str(_parse_compound_number(m.group(0), ones, teens, tens)),
        text_lower
    )
    
    # Pattern: "X thousand" alone (e.g., "two thousand")
    text_lower = re.sub(
        r'\b(one|two|three|four|five|six|seven|eight|nine)\s+thousand\b',
        lambda m: str(ones.get(m.group(1), 0) * 1000),
        text_lower
    )
    
    # Pattern: "X hundred Y" (e.g., "one hundred fifty-six")
    text_lower = re.sub(
        r'\b(one|two|three|four|five|six|seven|eight|nine)\s+hundred\s+(?:and\s+)?(\w+(?:\s+|-)\w+|\w+)',
        lambda m: str(_parse_compound_number(m.group(0), ones, teens, tens)),
        text_lower
    )
    
    # Pattern: "X hundred" alone (e.g., "two hundred")
    text_lower = re.sub(
        r'\b(one|two|three|four|five|six|seven|eight|nine)\s+hundred\b',
        lambda m: str(ones.get(m.group(1), 0) * 100),
        text_lower
    )
    
    # Pattern: tens + ones (e.g., "twenty-three", "twenty three")
    text_lower = re.sub(
        r'\b(twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)[\s-](one|two|three|four|five|six|seven|eight|nine)\b',
        lambda m: str(tens.get(m.group(1), 0) + ones.get(m.group(2), 0)),
        text_lower
    )
    
    # Replace single-word numbers (excluding 'hundred' and 'thousand' which are handled above)
    all_numbers = {**ones, **teens, **tens}
    for word, digit in all_numbers.items():
        text_lower = re.sub(r'\b' + word + r'\b', str(digit), text_lower)
    
    return text_lower

def _parse_compound_number(text, ones, teens, tens):
    """Helper to parse complex compound numbers like 'two thousand twenty-four'."""
    total = 0
    current = 0
    
    words = text.lower().replace('-', ' ').split()
    
    for word in words:
        if word == 'and':
            continue
        elif word in ones:
            current += ones[word]
        elif word in teens:
            current += teens[word]
        elif word in tens:
            current += tens[word]
        elif word == 'hundred':
            current *= 100
        elif word == 'thousand':
            current *= 1000
            total += current
            current = 0
    
    return total + current

def get_similarity_ratio(text1, text2):
    # Normalize numbers first (convert "one" → "1", etc.)
    text1 = normalize_numbers(text1)
    text2 = normalize_numbers(text2)
    
    # Then remove punctuation and lowercase
    norm1 = re.sub(r'[\W_]+', '', text1).lower()
    norm2 = re.sub(r'[\W_]+', '', text2).lower()
    if not norm1 or not norm2: return 0.0
    return difflib.SequenceMatcher(None, norm1, norm2).ratio()

# apply_voice_effects removed. Logic moved to utils/pedalboard_processor.py (MCCC: Separation of Concerns)

from core.structs import WorkerTask

def worker_process_chunk(task: WorkerTask):
    """The main function executed by each worker process to generate a single audio chunk."""
    # Unpack from explicit dataclass for local usage
    # MCCC: Explicit Interface
    task_index = task.task_index
    original_index = task.original_index
    sentence_number = task.sentence_number
    text_chunk = task.text_chunk
    device_str = task.device_str
    master_seed = task.master_seed
    ref_audio_path = task.ref_audio_path
    exaggeration = task.exaggeration
    temperature = task.temperature
    cfg_weight = task.cfg_weight
    disable_watermark = task.disable_watermark
    num_candidates = task.num_candidates
    max_attempts = task.max_attempts
    bypass_asr = task.bypass_asr
    session_name = task.session_name
    run_idx = task.run_idx
    output_dir_str = task.output_dir_str
    uuid = task.uuid
    asr_threshold = task.asr_threshold
    speed = task.speed
    engine_name = task.tts_engine # Mapped field name
    pitch_shift = task.pitch_shift
    timbre_shift = task.timbre_shift
    gruffness = task.gruffness
    bass_boost = task.bass_boost
    treble_boost = task.treble_boost
    model_path = task.model_path

    pid = os.getpid()
    logging.info(f"[Worker-{pid}] Starting chunk (Idx: {original_index}, #: {sentence_number}, UUID: {uuid[:8]}) on device {device_str}")

    try:
        # Pass model_path to efficient initializer
        tts_engine, whisper_model = get_or_init_worker_models(device_str, engine_name, model_path)
        if tts_engine is None or whisper_model is None:
            raise RuntimeError(f"Engine initialization failed for device {device_str}")
    except Exception as e_model_load:
        return {"original_index": original_index, "status": "error", "error_message": f"Engine Load Fail: {e_model_load}"}

    run_temp_dir = Path(output_dir_str) / session_name / f"run_{run_idx+1}_temp"
    run_temp_dir.mkdir(exist_ok=True, parents=True)
    
    base_candidate_path_prefix = run_temp_dir.resolve() / f"c_{uuid}_cand"

    try:
        if ref_audio_path and str(ref_audio_path).strip():
            tts_engine.prepare_reference(ref_audio_path, exaggeration=min(exaggeration, 1.0))
    except Exception as e:
        logging.error(f"[Worker-{pid}] Failed to prepare reference for chunk {sentence_number}: {e}", exc_info=True)
        return {"original_index": original_index, "status": "error", "error_message": f"Reference Prep Fail: {e}"}

    passed_candidates = []
    best_failed_candidate = None
    
    for attempt_num in range(max_attempts):
        if len(passed_candidates) >= num_candidates:
            logging.info(f"Met required number of candidates ({num_candidates}). Stopping early.")
            break

        if master_seed != 0:
            seed = master_seed + attempt_num
        else:
            seed = random.randint(1, 2**32 - 1)
        
        logging.info(f"[Worker-{pid}] Chunk #{sentence_number}, Attempt {attempt_num + 1}/{max_attempts} with seed {seed}")
        
        # CUDA State Validation: Check if GPU is in a valid state before attempting generation
        if torch.cuda.is_available():
            try:
                torch.cuda.synchronize()  # This will fail if CUDA is in a bad state
            except Exception as cuda_check_error:
                logging.error(f"CUDA state check failed before chunk #{sentence_number}, attempt {attempt_num+1}: {cuda_check_error}")
                logging.error("GPU is in an invalid state. Aborting remaining attempts.")
                break  # Exit the retry loop - GPU is corrupted
        
        set_seed(seed)
        
        temp_path_str = str(base_candidate_path_prefix) + f"_{attempt_num+1}_seed{seed}.wav"


        try:
            wav_tensor = tts_engine.generate(
                text_chunk, 
                ref_audio_path,
                exaggeration=exaggeration,
                temperature=temperature,
                cfg_weight=cfg_weight,
                apply_watermark=not disable_watermark
            )
            print(f"[Worker Debug] generate returned. Tensor type: {type(wav_tensor)}", flush=True)
            
            if not (torch.is_tensor(wav_tensor) and wav_tensor.numel() > tts_engine.sr * 0.1):
                logging.warning(f"Generation failed (empty audio) for chunk #{sentence_number}, attempt {attempt_num+1}.")
                continue
            
            print(f"[Worker Debug] Saving to {temp_path_str}...", flush=True)
#            torchaudio.save(temp_path_str, wav_tensor.cpu(), tts_engine.sr, backend="soundfile")
            audio_data = wav_tensor.cpu().numpy()
            if len(audio_data.shape) > 1:
                audio_data = audio_data.T
            
            try:
                sf.write(temp_path_str, audio_data, tts_engine.sr)
                print(f"[Worker Debug] File saved to disk.", flush=True)
            except Exception as e_sf:
                print(f"[Worker Debug] sf.write failed: {e_sf}", flush=True)
                raise

            duration = wav_tensor.shape[-1] / tts_engine.sr
            
            # --- Signal Processing Check (Pre-Whisper) ---
            print(f"[Worker Debug] Validating audio signal...", flush=True)
            is_valid_signal, signal_error = validate_audio_signal(wav_tensor.cpu(), tts_engine.sr)
            print(f"[Worker Debug] Validation result: {is_valid_signal}", flush=True)
            
            if not is_valid_signal:
                logging.warning(f"Signal Rejected inside worker chunk #{sentence_number}, attempt {attempt_num+1}: {signal_error}")
                if Path(temp_path_str).exists(): os.remove(temp_path_str) # Cleanup if we wrote it (logic above wrote sf.write first)
                continue
            
            # GPU Memory Cleanup: Free tensor immediately after use
            print(f"[Worker Debug] Cleaning up GPU memory...", flush=True)
            del wav_tensor
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            print(f"[Worker Debug] GPU memory cleaned.", flush=True)

        except Exception as e:
            logging.error(f"Generation crashed for chunk #{sentence_number}, attempt {attempt_num+1}: {e}", exc_info=True)
            if Path(temp_path_str).exists(): os.remove(temp_path_str) # Clean up partial file
            
            # GPU State Recovery: Reset CUDA state after crashes to prevent cascading errors
            if torch.cuda.is_available():
                try:
                    torch.cuda.synchronize()  # Wait for all CUDA operations to complete
                    torch.cuda.empty_cache()  # Clear GPU memory cache
                    logging.info(f"GPU state reset after crash on chunk #{sentence_number}, attempt {attempt_num+1}")
                except Exception as reset_error:
                    logging.error(f"Failed to reset GPU state: {reset_error}")
            continue

        current_candidate_data = {"path": temp_path_str, "duration": duration, "seed": seed}

        if bypass_asr:
            current_candidate_data['similarity_ratio'] = None 
            passed_candidates.append(current_candidate_data)
            logging.info(f"ASR bypassed for chunk #{sentence_number}, attempt {attempt_num+1}")
            continue

        # --- ASR Validation Logic ---
        ratio = 0.0
        try:
            # Get full result object to access confidence metrics
            result = whisper_model.transcribe(temp_path_str, fp16=(whisper_model.device.type == 'cuda'))
            transcribed = result['text']
            
            # Early debug: Log what Whisper returned
            logging.warning(f"[DEBUG] Whisper returned for chunk #{sentence_number}, attempt {attempt_num+1}: '{transcribed}'")
            
            # 1. Check for Non-Speech Artifacts (Balloon/Rubber/Static)
            # Short TTS clips usually result in 1 segment. If any segment is highly confident "no speech", we reject.
            # Use threshold 0.4 based on analysis (0.71 was observed for rubber noise).
            # Whisper API change: segments are now dicts, not objects
            max_no_speech_prob = max((s.get('no_speech_prob', 0.0) if isinstance(s, dict) else getattr(s, 'no_speech_prob', 0.0) 
                                     for s in result.get('segments', [])), default=0.0)
            if max_no_speech_prob > 0.4:
                logging.warning(f"ASR REJECTED: High No-Speech Probability ({max_no_speech_prob:.2f}) for chunk #{sentence_number}, attempt {attempt_num+1}")
                # Treat as failure, do not even check text match
                if Path(temp_path_str).exists(): os.remove(temp_path_str)
                continue

            # 2. Check for Hallucination Loops (Screeching)
            # High compression ratio (>2.0) indicates repetitive loops, common in screeching/hallucinated outputs.
            max_compression_ratio = max((s.get('compression_ratio', 0.0) if isinstance(s, dict) else getattr(s, 'compression_ratio', 0.0)
                                        for s in result.get('segments', [])), default=0.0)
            if max_compression_ratio > 2.0:
                logging.warning(f"ASR REJECTED: High Compression Ratio ({max_compression_ratio:.2f}) for chunk #{sentence_number}, attempt {attempt_num+1}")
                if Path(temp_path_str).exists(): os.remove(temp_path_str)
                continue
            
            # 3. Standard Text Similarity Check
            ratio = get_similarity_ratio(text_chunk, transcribed)
            
            # Log transcription for debugging (using WARNING level to ensure visibility)
            logging.warning(f"ASR Debug - Chunk #{sentence_number}, Attempt {attempt_num+1}:")
            logging.warning(f"  Expected: '{text_chunk[:80]}'")
            logging.warning(f"  Got:      '{transcribed[:80]}'")
            
            
        except Exception as e:
            logging.error(f"Whisper transcription failed for {temp_path_str}: {e}")
            # If whisper fails entirely, we probably shouldn't trust this file either
            if Path(temp_path_str).exists(): os.remove(temp_path_str)
            continue

        current_candidate_data['similarity_ratio'] = ratio
        
        if ratio >= asr_threshold:
            logging.info(f"ASR PASSED for chunk #{sentence_number}, attempt {attempt_num+1} (Sim: {ratio:.2f})")
            passed_candidates.append(current_candidate_data)
        else:
            logging.warning(f"ASR FAILED for chunk #{sentence_number}, attempt {attempt_num+1} (Sim: {ratio:.2f})")
            # FIX: Simplified logic to robustly track the best failure
            if best_failed_candidate is None or ratio > best_failed_candidate['similarity_ratio']:
                # If there was a previous best failure, delete its audio file
                if best_failed_candidate and Path(best_failed_candidate['path']).exists():
                    os.remove(best_failed_candidate['path'])
                best_failed_candidate = current_candidate_data
            else:
                # This attempt is worse than our stored best failure, so delete its audio
                os.remove(temp_path_str)

    # --- Final Selection Logic ---
    # --- Final Selection Logic ---
    # MCCC: Respect run_idx for multiple output support
    wavs_folder = "Sentence_wavs"
    if run_idx > 0:
        wavs_folder = f"Sentence_wavs_run_{run_idx+1}"
        
    final_wav_path = Path(output_dir_str) / session_name / wavs_folder / f"audio_{uuid}.wav"
    final_wav_path.parent.mkdir(exist_ok=True, parents=True)
    
    chosen_candidate = None
    status = "error"
    return_payload = {"original_index": original_index}

    if passed_candidates:
        chosen_candidate = sorted(passed_candidates, key=lambda x: x["duration"])[0]
        status = "success"
    elif best_failed_candidate:
        ratio_str = f"{best_failed_candidate.get('similarity_ratio', 0.0):.2f}"
        logging.warning(f"No candidates passed. Using best failure (Sim: {ratio_str}) as placeholder.")
        chosen_candidate = best_failed_candidate
        status = "failed_placeholder"
    
    # --- Finalize and Cleanup ---
    if chosen_candidate:
        # Move the chosen file to the final destination
        if Path(chosen_candidate['path']).exists():
            shutil.move(chosen_candidate['path'], final_wav_path)
            
            # Apply speed adjustment if needed (FFmpeg post-processing)
            # Apply voice effects if needed (Pedalboard post-processing)
            if any([speed != 1.0, pitch_shift != 0.0, timbre_shift != 0.0, gruffness > 0.0, bass_boost != 0.0, treble_boost != 0.0]):
                try:
                    # MCCC: Delegated to utils/pedalboard_processor.py
                    apply_pedalboard_effects(
                        str(final_wav_path), str(final_wav_path),
                        pitch_semitones=pitch_shift,
                        timbre_shift=timbre_shift,
                        gruffness=gruffness,
                        speed=speed,
                        bass_boost=bass_boost,
                        treble_boost=treble_boost
                    )
                except Exception as e:
                    logging.warning(f"Voice effects failed for chunk #{sentence_number}: {e}")
        
        # Clean up any other temporary candidate files that might still exist
        # This is for passed candidates that were not the shortest
        for cand in passed_candidates:
            if cand['path'] != chosen_candidate['path'] and Path(cand['path']).exists():
                os.remove(cand['path'])

        return_payload.update({
            "status": status,
            "path": str(final_wav_path),
            "seed": chosen_candidate.get('seed'),
            "similarity_ratio": chosen_candidate.get('similarity_ratio')
        })
        logging.info(f"Chunk #{sentence_number} (Status: {status}) processed. Final audio: {final_wav_path.name}")
    else:
        return_payload.update({"status": "error", "error_message": "All generation attempts failed."})

    return return_payload