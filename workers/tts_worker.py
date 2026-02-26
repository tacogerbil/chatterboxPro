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
from utils.pedalboard_processor import apply_pedalboard_effects
from utils.artifact_detector import (
    detect_audio_artifacts, 
    get_artifact_description, 
    extract_audio_features,
    extract_mfcc_profile,
    calculate_timbre_similarity
)
from utils.text_processor import normalize_numbers
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
_CURRENT_DEVICE = None
_CURRENT_COMBINE_GPUS = False

def get_or_init_worker_models(device_str: str, engine_name: str = 'chatterbox', model_path: str = None, combine_gpus: bool = False):
    """Initializes models once per worker process to save memory and time."""
    global _WORKER_TTS_ENGINE, _WORKER_WHISPER_MODEL, _CURRENT_ENGINE_NAME, _CURRENT_MODEL_PATH, _CURRENT_DEVICE, _CURRENT_COMBINE_GPUS
    pid = os.getpid()
    
    # Check if we need to switch engines OR switch model paths OR switch device
    config_changed = False
    if _WORKER_TTS_ENGINE is not None:
        if _CURRENT_COMBINE_GPUS != combine_gpus:
             logging.info(f"[Worker-{pid}] Combine GPUs switch: {_CURRENT_COMBINE_GPUS} -> {combine_gpus}")
             config_changed = True
        elif _CURRENT_DEVICE != device_str:
             logging.info(f"[Worker-{pid}] Device switch: {_CURRENT_DEVICE} -> {device_str}")
             config_changed = True
        elif _CURRENT_ENGINE_NAME != engine_name:
            logging.info(f"[Worker-{pid}] Engine switch: {_CURRENT_ENGINE_NAME} -> {engine_name}")
            config_changed = True
        elif _CURRENT_MODEL_PATH != model_path:
            logging.info(f"[Worker-{pid}] Model path switch: {_CURRENT_MODEL_PATH} -> {model_path}")
            config_changed = True
            
    if config_changed and _WORKER_TTS_ENGINE is not None:
        try:
             if hasattr(_WORKER_TTS_ENGINE, 'cleanup'):
                 _WORKER_TTS_ENGINE.cleanup()
        except: pass
        _WORKER_TTS_ENGINE = None
        _WORKER_WHISPER_MODEL = None # Whisper usually stays on same device as TTS, reload it too
    
    if _WORKER_TTS_ENGINE is None:
        logging.info(f"[Worker-{pid}] Initializing {engine_name} engine on device: {device_str}")
        try:
            from engines import get_engine
            # Pass model_path via kwargs
            _WORKER_TTS_ENGINE = get_engine(engine_name, device_str, model_path=model_path, combine_gpus=combine_gpus)
            _CURRENT_ENGINE_NAME = engine_name
            _CURRENT_MODEL_PATH = model_path
            _CURRENT_DEVICE = device_str
            _CURRENT_COMBINE_GPUS = combine_gpus
            
            # --- 
            from faster_whisper import WhisperModel
            import torch

            w_device = "cuda" if "cuda" in device_str and torch.cuda.is_available() else "cpu"

            # When combining GPUs, place Whisper on GPU 1 (the higher-VRAM card).
            # MOSS loads from GPU 0 first (device_map="auto"), so keeping Whisper off GPU 0
            # eliminates VRAM fragmentation that causes MOSS to OOM at 14% of its layers.
            # If not combining, use whatever GPU the worker was assigned.
            if combine_gpus and w_device == "cuda" and torch.cuda.device_count() > 1:
                w_device_index = [1]
                logging.info(f"[Worker-{pid}] combine_gpus: Placing Whisper on GPU 1 to keep GPU 0 free for MOSS.")
            else:
                w_device_index = [int(device_str.split(":")[-1])] if ":" in device_str else [0]

            compute_type = "float16" if w_device == "cuda" else "int8" # Auto-quantization
            
            # Note: We use the 'turbo' variant of faster-whisper which corresponds to Large-v3-Turbo
            _WORKER_WHISPER_MODEL = WhisperModel(
                "turbo", 
                device=w_device, 
                device_index=w_device_index,
                compute_type=compute_type, 
                download_root=str(Path.home() / ".cache" / "whisper")
            )
            logging.info(f"[Worker-{pid}] {engine_name} & Faster-Whisper loaded successfully on {device_str}.")
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
        
    # Check 3: Signal Energy (RMS)
    # Rejects "ghost speech" (pure silence or very faint air noise that Whisper hallucinates on).
    # Threshold 0.01 is approx -40dB. Real speech is usually > 0.1.
    rms = torch.sqrt(torch.mean(wav_tensor**2)).item()
    if rms < 0.01:
        return False, f"Low Signal Energy (RMS: {rms:.4f})"

    # Check 4: Trailing Noise (The "Woosh" Check)
    # If the file ends with loud noise (didn't fade out), reject it.
    # We traditionally check the last 250ms.
    num_samples = wav_tensor.numel()
    std_tail_len = int(sr * 0.25) # 250ms
    
    # Adaptive Tail: If file is short (<500ms), check last 33% instead of skipping
    if num_samples < std_tail_len * 2:
        tail_len = int(num_samples * 0.33)
    else:
        tail_len = std_tail_len
        
    # Only check if we have enough samples to be meaningful (>50ms)
    if tail_len > sr * 0.05:
        tail_tensor = wav_tensor[-tail_len:]
        tail_rms = torch.sqrt(torch.mean(tail_tensor**2)).item()
        
        # Threshold 0.035 (approx -29dB). 
        # Valid speech usually decays. A "Woosh" loop stays loud.
        if tail_rms > 0.035:
            return False, f"Trailing Noise Detected (Tail RMS: {tail_rms:.4f})"

    return True, "OK"


from utils.text_processor import normalize_numbers

def get_similarity_ratio(text1, text2):
    # Normalize numbers first (convert "one" → "1", etc.)
    text1 = normalize_numbers(text1)
    text2 = normalize_numbers(text2)
    
    # Then remove punctuation and lowercase
    norm1 = re.sub(r'[\W_]+', '', text1).lower()
    norm2 = re.sub(r'[\W_]+', '', text2).lower()
    if not norm1 or not norm2: return 0.0
    return difflib.SequenceMatcher(None, norm1, norm2).ratio()

# apply_voice_effects removed. Logic moved to utils/pedalboard_processor.py (

from core.structs import WorkerTask

def worker_process_chunk(task: WorkerTask):
    """The main function executed by each worker process to generate a single audio chunk."""
    # Unpack from explicit dataclass for local usage
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
    auto_expression_enabled = task.auto_expression_enabled
    expression_sensitivity = task.expression_sensitivity
    combine_gpus = task.combine_gpus


    pid = os.getpid()
    logging.info(f"[Worker-{pid}] Starting chunk (Idx: {original_index}, #: {sentence_number}, UUID: {uuid[:8]}) on device {device_str}")

    try:
        # Pass model_path to efficient initializer
        tts_engine, whisper_model = get_or_init_worker_models(device_str, engine_name, model_path, combine_gpus)
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

    ref_features = {}
    ref_mfcc_profile = None
    
    if ref_audio_path and str(ref_audio_path).strip():
        try:
            logging.info(f"[Worker-{pid}] Analyzing Reference Audio: {ref_audio_path}")
            ref_features = extract_audio_features(str(ref_audio_path))
            
            # Efficiently extract MFCC from the already loaded audio (if available)
            if 'y' in ref_features and 'sr' in ref_features:
                 ref_mfcc_profile = extract_mfcc_profile(y=ref_features['y'], sr=ref_features['sr'])
            else:
                 ref_mfcc_profile = extract_mfcc_profile(audio_path=str(ref_audio_path))
                 
            if ref_features:
                logging.info(f"[Worker-{pid}] Reference Baseline: F0={ref_features.get('f0_mean', 0):.1f}Hz, Timbre Profile Set: {ref_mfcc_profile is not None}")
        except Exception as e_ref:
            logging.warning(f"Failed to analyze reference audio: {e_ref}")

    passed_candidates = []
    best_failed_candidate = None
    best_fidelity_reject = None  # Last resort: best candidate that failed pitch/timbre gates
    
    for attempt_num in range(max_attempts):
        if len(passed_candidates) >= num_candidates:
            logging.info(f"Met required number of candidates ({num_candidates}). Stopping early.")
            break

        if master_seed != 0:
            seed = master_seed + attempt_num
        else:
            seed = random.randint(1, 2**32 - 1)
        
        logging.info(f"[Worker-{pid}] Chunk #{sentence_number}, Attempt {attempt_num + 1}/{max_attempts} with seed {seed}")
        
        # ... (CUDA Check Omitted for brevity in matching, assume context handles it) ...
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
            # --- Auto-Expression Detection (Phase 3 Quality Improvement) ---
            # Dynamically adjust exaggeration/temperature based on text content
            if auto_expression_enabled:
                from utils.expression_analyzer import get_expression_adjustment
                
                adjusted_temp, adjusted_exag, reason = get_expression_adjustment(
                    text_chunk,
                    temperature,
                    exaggeration,
                    expression_sensitivity
                )
                
                # Log if adjustments were made
                if adjusted_temp != temperature or adjusted_exag != exaggeration:
                    logging.info(f"Auto-expression: {reason}")
                    logging.info(f"  Adjusted temp {temperature:.2f}->{adjusted_temp:.2f}, exag {exaggeration:.2f}->{adjusted_exag:.2f}")
                    temperature = adjusted_temp
                    exaggeration = adjusted_exag
            
            # --- TTS Generation ---
            wav_tensor = tts_engine.generate(
                text_chunk, 
                ref_audio_path,
                exaggeration=exaggeration,
                temperature=temperature,
                cfg_weight=cfg_weight,
                apply_watermark=not disable_watermark
            )
            
            if not (torch.is_tensor(wav_tensor) and wav_tensor.numel() > tts_engine.sr * 0.1):
                logging.warning(f"Generation failed (empty audio) for chunk #{sentence_number}, attempt {attempt_num+1}.")
                continue
            
            audio_data = wav_tensor.cpu().numpy()
            if len(audio_data.shape) > 1:
                audio_data = audio_data.T
            
            try:
                sf.write(temp_path_str, audio_data, tts_engine.sr)
            except Exception as e_sf:
                logging.error(f"[Worker] sf.write failed: {e_sf}")
                raise

            duration = wav_tensor.shape[-1] / tts_engine.sr
            
            # --- Signal Processing Check (Pre-Whisper) ---
            is_valid_signal, signal_error = validate_audio_signal(wav_tensor.cpu(), tts_engine.sr)
            if not is_valid_signal:
                logging.warning(f"Signal Rejected inside worker chunk #{sentence_number}, attempt {attempt_num+1}: {signal_error}")
                if Path(temp_path_str).exists(): os.remove(temp_path_str)
                continue

            # --- 
            # Gate 1: Pitch Validation
            ref_f0 = ref_features.get('f0_mean')
            try:
                cand_features = extract_audio_features(temp_path_str)
            except:
                cand_features = {}

            if ref_f0 and ref_f0 > 50:
                cand_f0 = cand_features.get('f0_mean', 0)
                if cand_f0 > 50:
                    ratio = cand_f0 / ref_f0
                    if ratio > 1.4:
                        logging.warning(f"FIDELITY REJECT: Pitch too high ({cand_f0:.0f}Hz) vs Ref ({ref_f0:.0f}Hz). Ratio: {ratio:.2f}")
                        if best_fidelity_reject is None:
                            best_fidelity_reject = {"path": temp_path_str, "duration": duration, "seed": seed, "similarity_ratio": None}
                        elif Path(temp_path_str).exists():
                            os.remove(temp_path_str)
                        continue
                    if ratio < 0.6:
                        logging.warning(f"FIDELITY REJECT: Pitch too low ({cand_f0:.0f}Hz) vs Ref ({ref_f0:.0f}Hz). Ratio: {ratio:.2f}")
                        if best_fidelity_reject is None:
                            best_fidelity_reject = {"path": temp_path_str, "duration": duration, "seed": seed, "similarity_ratio": None}
                        elif Path(temp_path_str).exists():
                            os.remove(temp_path_str)
                        continue

            # Gate 2: Timbre Similarity
            if ref_mfcc_profile is not None:
                cand_y = cand_features.get('y')
                cand_sr = cand_features.get('sr')
                cand_mfcc = extract_mfcc_profile(temp_path_str, y=cand_y, sr=cand_sr)
                timbre_score = calculate_timbre_similarity(ref_mfcc_profile, cand_mfcc)
                TIMBRE_THRESHOLD = 0.82
                if timbre_score < TIMBRE_THRESHOLD:
                    logging.warning(f"FIDELITY REJECT: Timbre Mismatch (Score: {timbre_score:.2f} < {TIMBRE_THRESHOLD}). Possible accent drift.")
                    if best_fidelity_reject is None:
                        best_fidelity_reject = {"path": temp_path_str, "duration": duration, "seed": seed, "similarity_ratio": None}
                    elif Path(temp_path_str).exists():
                        os.remove(temp_path_str)
                    continue
                else:
                    logging.info(f"Fidelity Passed: Pitch OK, Timbre Score {timbre_score:.2f}")
            
            # GPU Memory Cleanup: Free tensor immediately after use
            del wav_tensor
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

        except Exception as e:
            logging.error(f"Generation crashed for chunk #{sentence_number}, attempt {attempt_num+1}: {e}", exc_info=True)
            if Path(temp_path_str).exists(): 
                try:
                    os.remove(temp_path_str) # Clean up partial file
                except OSError:
                    pass # Best effort cleanup
            
            # GPU State Recovery: Reset CUDA state after crashes to prevent cascading errors.
            # gc.collect() must run first — Python reference cycles in the exception traceback
            # keep partial from_pretrained() tensors alive, so empty_cache() alone does nothing.
            if torch.cuda.is_available():
                try:
                    import gc
                    gc.collect()              # Break reference cycles holding zombie CUDA tensors
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
            # Faster-Whisper returns a generator for segments and an info object
            segments, info = whisper_model.transcribe(
                temp_path_str,
                beam_size=5,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=500)
            )
            
            # Consume the generator to get the text and check segments
            segment_list = list(segments)
            transcribed = "".join([segment.text for segment in segment_list])
            
            # Early debug: Log what Whisper returned
            logging.warning(f"[DEBUG] Whisper returned for chunk #{sentence_number}, attempt {attempt_num+1}: '{transcribed}'")
            
            # Calculate Standard Text Similarity Check First (so we can log/save it even if we reject)
            ratio = get_similarity_ratio(text_chunk, transcribed)
            current_candidate_data['similarity_ratio'] = ratio

            # Log transcription for debugging (using WARNING level to ensure visibility)
            logging.warning(f"ASR Debug - Chunk #{sentence_number}, Attempt {attempt_num+1}:")
            logging.warning(f"  Expected: '{text_chunk[:80]}'")
            logging.warning(f"  Got:      '{transcribed[:80]}'")
            
            # 1. Check for Non-Speech Artifacts using Info & Segments
            # Because VAD is enabled, silence is mostly stripped before transcription.
            max_no_speech_prob = max((s.no_speech_prob for s in segment_list), default=0.0)
            if max_no_speech_prob > 0.4:
                logging.warning(f"ASR REJECTED: High No-Speech Probability ({max_no_speech_prob:.2f}) for chunk #{sentence_number}, attempt {attempt_num+1}")
                if best_failed_candidate is None or ratio > best_failed_candidate.get('similarity_ratio', 0.0):
                    if best_failed_candidate and Path(best_failed_candidate['path']).exists():
                        os.remove(best_failed_candidate['path'])
                    best_failed_candidate = current_candidate_data.copy()
                else:
                    if Path(temp_path_str).exists(): os.remove(temp_path_str)
                continue

            # 2. Check for Hallucination Loops (Screeching)
            # FasterWhisper segments have compression_ratio just like original whisper
            max_compression_ratio = max((s.compression_ratio for s in segment_list), default=0.0)
            if max_compression_ratio > 2.0:
                logging.warning(f"ASR REJECTED: High Compression Ratio ({max_compression_ratio:.2f}) for chunk #{sentence_number}, attempt {attempt_num+1}")
                if best_failed_candidate is None or ratio > best_failed_candidate.get('similarity_ratio', 0.0):
                    if best_failed_candidate and Path(best_failed_candidate['path']).exists():
                        os.remove(best_failed_candidate['path'])
                    best_failed_candidate = current_candidate_data.copy()
                else:
                    if Path(temp_path_str).exists(): os.remove(temp_path_str)
                continue
            
            # 3. Strict Length Validation (Hallucination Check)
            # The User reported a "93% match" containing "why?" at the end.
            # Rationale: Hallucinations usually ADD text. 
            # If transcription is significantly longer than source, reject it, even if Levenshtein is high.
            
            # Normalize first to account for "1" vs "one"
            n_trans = normalize_numbers(transcribed).lower().strip()
            n_source = normalize_numbers(text_chunk).lower().strip()
            
            # Remove punctuation for length check
            n_trans_clean = re.sub(r'[\W_]+', '', n_trans)
            n_source_clean = re.sub(r'[\W_]+', '', n_source)
            
            len_t = len(n_trans_clean)
            len_s = len(n_source_clean)
            
            # Tighter Rule for High Similarity:
            # If we are basically matching, we shouldn't have trailing garbage.
            # Let's use Word Count.
            wc_t = len(n_trans.split())
            wc_s = len(n_source.split())
            diff = wc_t - wc_s
            
            # Dynamic Tolerance based on length
            # Short sentences (< 10 words) -> Zero Tolerance for extra words.
            # Long sentences (>= 10 words) -> Allow +1 (accidental split like "can not")
            
            if wc_s < 10:
                if diff >= 1:
                     logging.warning(f"ASR REJECTED: Extra Word in Short Sentence ({wc_t} vs {wc_s}). Hallucination?")
                     if best_failed_candidate is None or ratio > best_failed_candidate.get('similarity_ratio', 0.0):
                         if best_failed_candidate and Path(best_failed_candidate['path']).exists():
                             os.remove(best_failed_candidate['path'])
                         best_failed_candidate = current_candidate_data.copy()
                     else:
                         if Path(temp_path_str).exists(): os.remove(temp_path_str)
                     continue
            else:
                if diff >= 2:
                     logging.warning(f"ASR REJECTED: Word Count Mismatch ({wc_t} vs {wc_s}) - Suspected Hallucination/Repetition.")
                     if best_failed_candidate is None or ratio > best_failed_candidate.get('similarity_ratio', 0.0):
                         if best_failed_candidate and Path(best_failed_candidate['path']).exists():
                             os.remove(best_failed_candidate['path'])
                         best_failed_candidate = current_candidate_data.copy()
                     else:
                         if Path(temp_path_str).exists(): os.remove(temp_path_str)
                     continue
            
            
        except Exception as e:
            logging.error(f"Whisper transcription failed for {temp_path_str}: {e}")
            # If whisper fails entirely, we probably shouldn't trust this file either
            if Path(temp_path_str).exists(): os.remove(temp_path_str)
            continue
        
        if ratio >= asr_threshold:
            logging.info(f"ASR PASSED for chunk #{sentence_number}, attempt {attempt_num+1} (Sim: {ratio:.2f})")
            
            # --- Audio Artifact Detection (Phase 1 Quality Improvement) ---
            # Check for swooshes, clicks, muffled audio that ASR might miss
            is_clean, artifact_type, confidence = detect_audio_artifacts(temp_path_str, text_chunk)
            
            if not is_clean:
                artifact_desc = get_artifact_description(artifact_type)
                logging.warning(f"ARTIFACT DETECTED for chunk #{sentence_number}, attempt {attempt_num+1}: {artifact_desc} (confidence: {confidence:.2f})")
                
                # Treat as failed attempt, track as best failure if better than existing
                if best_failed_candidate is None or ratio > best_failed_candidate['similarity_ratio']:
                    if best_failed_candidate and Path(best_failed_candidate['path']).exists():
                        os.remove(best_failed_candidate['path'])
                    best_failed_candidate = current_candidate_data
                else:
                    os.remove(temp_path_str)
                continue
            
            # All validations passed
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
    wavs_folder = "Sentence_wavs"
    if run_idx > 0:
        wavs_folder = f"Sentence_wavs_run_{run_idx+1}"

    wav_dir = Path(output_dir_str) / session_name / wavs_folder
    wav_dir.mkdir(exist_ok=True, parents=True)
    
    chosen_candidate = None
    status = "error"
    return_payload = {"uuid": uuid, "original_index": original_index}

    if passed_candidates:
        chosen_candidate = sorted(passed_candidates, key=lambda x: x["duration"])[0]
        status = "success"
    elif best_failed_candidate:
        ratio_str = f"{best_failed_candidate.get('similarity_ratio', 0.0):.2f}"
        logging.warning(f"No candidates passed. Using best failure (Sim: {ratio_str}) as placeholder.")
        chosen_candidate = best_failed_candidate
        return_payload["error_message"] = f"ASR Failed (Best Sim: {float(ratio_str)*100:.1f}%)"
        status = "failed_placeholder"
    elif best_fidelity_reject:
        logging.warning("All attempts rejected by fidelity gates. Using best fidelity-rejected candidate as placeholder.")
        chosen_candidate = best_fidelity_reject
        return_payload["error_message"] = "Fidelity gates failed (pitch/timbre mismatch — check reference audio or adjust thresholds)"
        status = "failed_placeholder"

    # --- Finalize and Cleanup ---
    if chosen_candidate:
        # Determine final filename: failed placeholder files get a _failed suffix
        # so they are identifiable on disk even if the progress journal is incomplete.
        wav_suffix = "_failed" if status == "failed_placeholder" else ""
        final_wav_path = wav_dir / f"audio_{uuid}{wav_suffix}.wav"

        # Move the chosen file to the final destination with retry logic for file locks
        if Path(chosen_candidate['path']).exists():
            # Windows file lock handling: retry with delays
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    shutil.copy2(chosen_candidate['path'], final_wav_path)
                    os.remove(chosen_candidate['path'])
                    break
                except PermissionError as e:
                    if attempt < max_retries - 1:
                        logging.warning(f"File lock detected, retrying in 0.5s (attempt {attempt+1}/{max_retries}): {e}")
                        import time
                        time.sleep(0.5)
                    else:
                        logging.error(f"Failed to move file after {max_retries} attempts: {e}")
                        # Copy succeeded but remove failed - file stays in temp
                        if final_wav_path.exists():
                            logging.info(f"File copied successfully despite lock, temp file remains: {chosen_candidate['path']}")
                        else:
                            raise
            
            # Apply speed adjustment if needed (FFmpeg post-processing)
            # Apply voice effects if needed (Pedalboard post-processing)
            if any([speed != 1.0, pitch_shift != 0.0, timbre_shift != 0.0, gruffness > 0.0, bass_boost != 0.0, treble_boost != 0.0]):
                try:
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

    if chosen_candidate:
        # Move temporary file to final location if not already moved/referenced
        chosen_candidate['path'] = str(final_wav_path)
        return_payload.update(chosen_candidate)
        return_payload["status"] = status
        
        # Done here to distribute CPU load to worker process
        try:
            audio_stats = extract_audio_features(str(final_wav_path))
            return_payload["audio_stats"] = audio_stats
            
            # Log for debug visibility
            if audio_stats:
                rms = audio_stats.get('rms_mean', 0)
                f0 = audio_stats.get('f0_mean', 0)
                logging.info(f"Audio Stats [#{sentence_number}]: RMS={rms:.4f}, Pitch={f0:.1f}Hz")
        except Exception as e:
            logging.warning(f"Audio feature extraction failed: {e}")
            
    else:
        return_payload["status"] = status
        if status == "failed_placeholder":
             pass
        else:
             return_payload["error"] = "No candidate audio produced."

    logging.info(f"Chunk #{sentence_number} (Status: {status}) processed.")
    return return_payload