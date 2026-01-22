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
_WORKER_TTS_MODEL, _WORKER_WHISPER_MODEL = None, None

def get_or_init_worker_models(device_str: str):
    """Initializes models once per worker process to save memory and time."""
    global _WORKER_TTS_MODEL, _WORKER_WHISPER_MODEL
    pid = os.getpid()
    if _WORKER_TTS_MODEL is None:
        logging.info(f"[Worker-{pid}] Initializing models for device: {device_str}")
        try:
            _WORKER_TTS_MODEL = ChatterboxTTS.from_pretrained(device_str)
            whisper_device = torch.device(device_str if "cuda" in device_str and torch.cuda.is_available() else "cpu")
            _WORKER_WHISPER_MODEL = whisper.load_model("base.en", device=whisper_device, download_root=str(Path.home() / ".cache" / "whisper"))
            logging.info(f"[Worker-{pid}] Models loaded successfully on {device_str}.")
        except Exception as e:
            logging.critical(f"[Worker-{pid}] CRITICAL ERROR: Failed to initialize models: {e}", exc_info=True)
            _WORKER_TTS_MODEL, _WORKER_WHISPER_MODEL = None, None
            raise
    return _WORKER_TTS_MODEL, _WORKER_WHISPER_MODEL

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

def get_similarity_ratio(text1, text2):
    norm1 = re.sub(r'[\W_]+', '', text1).lower()
    norm2 = re.sub(r'[\W_]+', '', text2).lower()
    if not norm1 or not norm2: return 0.0
    return difflib.SequenceMatcher(None, norm1, norm2).ratio()

def worker_process_chunk(task_bundle):
    """The main function executed by each worker process to generate a single audio chunk."""
    (task_index, original_index, sentence_number, text_chunk, device_str, master_seed, ref_audio_path,
     exaggeration, temperature, cfg_weight, disable_watermark, num_candidates, max_attempts,
     bypass_asr, session_name, run_idx, output_dir_str, uuid, asr_threshold) = task_bundle

    pid = os.getpid()
    logging.info(f"[Worker-{pid}] Starting chunk (Idx: {original_index}, #: {sentence_number}, UUID: {uuid[:8]}) on device {device_str}")

    try:
        tts_model, whisper_model = get_or_init_worker_models(device_str)
        if tts_model is None or whisper_model is None:
            raise RuntimeError(f"Model initialization failed for device {device_str}")
    except Exception as e_model_load:
        return {"original_index": original_index, "status": "error", "error_message": f"Model Load Fail: {e_model_load}"}

    run_temp_dir = Path(output_dir_str) / session_name / f"run_{run_idx+1}_temp"
    run_temp_dir.mkdir(exist_ok=True, parents=True)
    
    base_candidate_path_prefix = run_temp_dir.resolve() / f"c_{uuid}_cand"

    try:
        tts_model.prepare_conditionals(ref_audio_path, exaggeration=min(exaggeration, 1.0), use_cache=True)
    except Exception as e:
        logging.error(f"[Worker-{pid}] Failed to prepare conditionals for chunk {sentence_number}: {e}", exc_info=True)
        return {"original_index": original_index, "status": "error", "error_message": f"Conditional Prep Fail: {e}"}

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
        set_seed(seed)
        
        temp_path_str = str(base_candidate_path_prefix) + f"_{attempt_num+1}_seed{seed}.wav"

        try:
            wav_tensor = tts_model.generate(text_chunk, cfg_weight=cfg_weight, temperature=temperature, apply_watermark=not disable_watermark)
            if not (torch.is_tensor(wav_tensor) and wav_tensor.numel() > tts_model.sr * 0.1):
                logging.warning(f"Generation failed (empty audio) for chunk #{sentence_number}, attempt {attempt_num+1}.")
                continue
            
#            torchaudio.save(temp_path_str, wav_tensor.cpu(), tts_model.sr, backend="soundfile")
            audio_data = wav_tensor.cpu().numpy()
            if len(audio_data.shape) > 1:
                audio_data = audio_data.T
            sf.write(temp_path_str, audio_data, tts_model.sr)

            duration = wav_tensor.shape[-1] / tts_model.sr
            
            # --- Signal Processing Check (Pre-Whisper) ---
            # Reject obvious garbage before wasting time saving to disk or running Whisper
            is_valid_signal, signal_error = validate_audio_signal(wav_tensor.cpu(), tts_model.sr)
            if not is_valid_signal:
                logging.warning(f"Signal Rejected inside worker chunk #{sentence_number}, attempt {attempt_num+1}: {signal_error}")
                if Path(temp_path_str).exists(): os.remove(temp_path_str) # Cleanup if we wrote it (logic above wrote sf.write first)
                continue
            
            # GPU Memory Cleanup: Free tensor immediately after use
            del wav_tensor
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

        except Exception as e:
            logging.error(f"Generation crashed for chunk #{sentence_number}, attempt {attempt_num+1}: {e}", exc_info=True)
            if Path(temp_path_str).exists(): os.remove(temp_path_str) # Clean up partial file
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
            
            # 1. Check for Non-Speech Artifacts (Balloon/Rubber/Static)
            # Short TTS clips usually result in 1 segment. If any segment is highly confident "no speech", we reject.
            # Use threshold 0.4 based on analysis (0.71 was observed for rubber noise).
            max_no_speech_prob = max((s.no_speech_prob for s in result['segments']), default=0.0)
            if max_no_speech_prob > 0.4:
                logging.warning(f"ASR REJECTED: High No-Speech Probability ({max_no_speech_prob:.2f}) for chunk #{sentence_number}, attempt {attempt_num+1}")
                # Treat as failure, do not even check text match
                if Path(temp_path_str).exists(): os.remove(temp_path_str)
                continue

            # 2. Check for Hallucination Loops (Screeching)
            # High compression ratio (>2.0) indicates repetitive loops, common in screeching/hallucinated outputs.
            max_compression_ratio = max((s.compression_ratio for s in result['segments']), default=0.0)
            if max_compression_ratio > 2.0:
                logging.warning(f"ASR REJECTED: High Compression Ratio ({max_compression_ratio:.2f}) for chunk #{sentence_number}, attempt {attempt_num+1}")
                if Path(temp_path_str).exists(): os.remove(temp_path_str)
                continue
            
            # 3. Standard Text Similarity Check
            ratio = get_similarity_ratio(text_chunk, transcribed)
            
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
    final_wav_path = Path(output_dir_str) / session_name / "Sentence_wavs" / f"audio_{uuid}.wav"
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