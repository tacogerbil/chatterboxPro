import logging
import random
import uuid
import multiprocessing
import multiprocessing.connection
import time
import os
import signal
import subprocess
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import List, Dict, Any, Tuple, Optional, Union
import torch

from PySide6.QtCore import QObject, Signal, QThread, Slot
from workers.tts_worker import worker_process_chunk
from utils.text_processor import punc_norm
from core.state import AppState
from core.structs import WorkerTask

# Constants for Status
STATUS_YES = 'yes'
STATUS_FAILED = 'failed'
STATUS_NO = 'no'

class GenerationThread(QThread):
    """
    Background thread that manages the ProcessPoolExecutor loop.
    Emits batched signals for progress and completion to prevent UI lockups.
    """
    # Signals to communicate back to the Service (which runs on Main Thread)
    progress_update = Signal(int, int) # completed, total
    batch_complete = Signal(list) # list of result dicts
    generation_done = Signal()   # Renamed from 'finished' to avoid shadowing QThread.finished
    error_occurred = Signal(str)
    stopped = Signal()

    def __init__(self, tasks: List[Any], max_workers: int, outputs_dir: str) -> None:
        super().__init__()
        self.tasks = tasks
        self.max_workers = max_workers
        self.outputs_dir = outputs_dir
        self.stop_requested = multiprocessing.Event()
        self.executor: Optional[ProcessPoolExecutor] = None

    def request_stop(self) -> None:
        """Stops the loop and NUKES worker processes with extreme prejudice."""
        self.stop_requested.set()
        
        logging.warning("🛑 NUCLEAR STOP: Initiating Sequence...")
        
        # 1. Capture PIDs BEFORE shutting down implementation (Critical for Windows)
        pids = []
        if self.executor:
            # Try to get PIDs from private attribute (Standard in 3.9+)
            if hasattr(self.executor, '_processes') and self.executor._processes:
                 pids = list(self.executor._processes.keys())
        
        if not pids:
            logging.warning("Could not find active PIDs in executor. Processes may be orphaned.")

        # 2. Cancel Future Work
        if self.executor:
            try:
                self.executor.shutdown(wait=False, cancel_futures=True)
            except Exception as e:
                logging.error(f"Error during executor shutdown: {e}")

        # 3. Aggressive Kill (The "Double Tap")
        if pids:
            logging.warning(f"Killing {len(pids)} worker processes: {pids}")
            for pid in pids:
                try:
                    # Windows: use taskkill /F to kill process (No /T tree kill, no main app crash)
                    if os.name == 'nt':
                        subprocess.run(
                            ["taskkill", "/F", "/PID", str(pid)], 
                            stdout=subprocess.DEVNULL, 
                            stderr=subprocess.DEVNULL
                        )
                    else:
                        # Linux/Mac: SIGKILL
                        os.kill(pid, signal.SIGKILL)
                        
                    logging.warning(f"KILLED worker process {pid}")
                except Exception as e:
                     logging.error(f"Failed to kill process {pid}: {e}")

    def _cleanup_memory(self) -> None:
        import gc
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()

    def run(self) -> None:
        """The main blocking loop runs here, in a separate thread."""
        try:
            completed_count = 0
            total_tasks = len(self.tasks)
            self.progress_update.emit(0, total_tasks)

            ctx = multiprocessing.get_context('spawn')
            executor = ProcessPoolExecutor(max_workers=self.max_workers, mp_context=ctx)
            self.executor = executor
            
            try:
                # Map future -> task info
                futures = {executor.submit(worker_process_chunk, task): task for task in self.tasks}
                
                result_batch = []
                last_emit_time = time.time()
                
                for future in as_completed(futures):
                    if self.stop_requested.is_set():
                         # Clean shutdown handled by request_stop
                         break

                    try:
                        result = future.result()
                        if result and 'original_index' in result:
                            result_batch.append(result)
                    except Exception as e:
                        logging.error(f"Worker task error: {e}")
                        pass
                    
                    completed_count += 1
                    
                    current_time = time.time()
                    if len(result_batch) >= 10 or (current_time - last_emit_time) > 0.1:
                        if result_batch:
                            self.batch_complete.emit(result_batch)
                            result_batch = []
                        self.progress_update.emit(completed_count, total_tasks)
                        last_emit_time = current_time
                
                # Flush remaining if we didn't stop
                if result_batch and not self.stop_requested.is_set():
                     self.batch_complete.emit(result_batch)
                     self.progress_update.emit(completed_count, total_tasks)
                     
            finally:
                if self.stop_requested.is_set():
                    # We killed the processes, so don't wait for them! 
                    executor.shutdown(wait=False, cancel_futures=True)
                else:
                    # Clean exit
                    executor.shutdown(wait=True)
            
            self._cleanup_memory()
            
            if self.stop_requested.is_set():
                self.stopped.emit()
            else:
                self.generation_done.emit()  # Use renamed signal — never shadow QThread.finished

        except Exception as e:
            logging.error(f"GenerationThread crashed: {e}", exc_info=True)
            self.error_occurred.emit(str(e))

class GenerationService(QObject):
    """
    Handles the multi-process TTS generation.
    Decoupled from UI, uses Signals for updates.
    Manages a QThread to keep UI responsive.
    
    """
    
    # Signals
    progress_update = Signal(int, int) # completed, total
    items_updated = Signal(list) # list of indices of updated items (
    started = Signal()
    finished = Signal()
    stopped = Signal()
    error_occurred = Signal(str)
    
    # Progress Tracking Signals (
    stats_updated = Signal(int, int, int)  # total, passed, failed
    eta_updated = Signal(float)  # seconds remaining
    
    # Auto-Fix Signals
    auto_fix_status = Signal(str) # Status message for UI
    
    def __init__(self, app_state: AppState) -> None:
        super().__init__()
        self.state = app_state
        self.worker_thread: Optional[GenerationThread] = None
        self.playlist_service: Optional[Any] = None # Injected dependency
        self.is_running: bool = False
        self._original_max_attempts: Optional[int] = None  # For restoring when auto-loop boost is active

    def set_playlist_service(self, service: Any) -> None:
        self.playlist_service = service

    def request_stop(self) -> None:
        """Sets the stop flag to terminate generation."""
        if self.worker_thread and self.worker_thread.isRunning():
            logging.info("Generation stop requested...")
            self.worker_thread.request_stop()
        else:
            self.stopped.emit()

    def _restore_max_attempts(self) -> None:
        """Restores max_attempts to its original value if it was boosted for auto-loop."""
        if self._original_max_attempts is not None:
            self.state.settings.max_attempts = self._original_max_attempts
            logging.info(f"Auto-loop: max_attempts restored to {self._original_max_attempts}")
            self._original_max_attempts = None

    def set_attempts_boost(self, original: int) -> None:
        """Called by ControlsView when auto-loop boosts max_attempts."""
        self._original_max_attempts = original

    def _get_chapter_ranges(self) -> List[Tuple[int, int]]:
        """Returns list of (start_idx, end_idx) for each chapter."""
        chapter_starts = [
            i for i, s in enumerate(self.state.sentences) 
            if s.get('is_chapter_heading')
        ]
        
        if not chapter_starts:
            return [(0, len(self.state.sentences))]
        
        ranges = []
        for i, start in enumerate(chapter_starts):
            end = chapter_starts[i+1] if i+1 < len(chapter_starts) else len(self.state.sentences)
            ranges.append((start, end))
        return ranges

    def _configure_workers(self, target_gpus: str, combine_gpus: bool = False) -> Tuple[List[str], int]:
        """Determines devices and max_workers based on settings and hardware."""
        gpu_count = torch.cuda.device_count() if torch.cuda.is_available() else 0
        
        if "cpu" in target_gpus or gpu_count == 0:
            return ["cpu"], 1
            
        devices = [d.strip() for d in target_gpus.split(',') if d.strip()]
        
        # otherwise M workers will all try to load the model across M GPUs simultaneously, causing OOM.
        if combine_gpus and len(devices) > 0:
            logging.info("Combine GPUs enabled: Restricting GenerationService to 1 worker process.")
            return [devices[0]], 1
            
        return devices, len(devices)

    def _prepare_tasks(self, 
                      indices: List[int], 
                      devices: List[str], 
                      run_seed: int,
                      outputs_dir: str) -> List[Tuple]:
        """Creates the list of task tuples for the worker pool."""
        
        s = self.state.settings
        tasks: List[Tuple] = []
        
        # Determine sorting
        if hasattr(self.state, 'generation_order') and self.state.generation_order == "In Order":
             sorted_indices = sorted(indices, key=lambda i: int(self.state.sentences[i].get('sentence_number', 0)))
        else:
             sorted_indices = sorted(indices, key=lambda i: len(self.state.sentences[i].get('original_sentence', '')), reverse=True)
        
        for i, original_idx in enumerate(sorted_indices):
            sentence_data = self.state.sentences[original_idx]
            
            task = WorkerTask(
                task_index=i,
                original_index=original_idx,
                sentence_number=int(sentence_data.get('sentence_number', i+1)),
                uuid=sentence_data.get('uuid') or uuid.uuid4().hex,
                session_name=self.state.session_name,
                run_idx=0, # flattened
                output_dir_str=outputs_dir,
                text_chunk=punc_norm(sentence_data.get('original_sentence', '')),
                ref_audio_path=self.state.ref_audio_path if self.state.ref_audio_path and self.state.ref_audio_path.strip() else None,
                device_str=devices[i % len(devices)],
                master_seed=run_seed,
                exaggeration=s.exaggeration,
                temperature=s.temperature,
                cfg_weight=s.cfg_weight,
                disable_watermark=s.disable_watermark,
                num_candidates=s.num_candidates,
                max_attempts=s.max_attempts,
                bypass_asr=not s.asr_validation_enabled,
                asr_threshold=s.asr_threshold,
                speed=s.speed,
                tts_engine=s.tts_engine,
                combine_gpus=s.combine_gpus,
                pitch_shift=s.pitch_shift,
                timbre_shift=s.timbre_shift,
                gruffness=s.gruffness,
                bass_boost=s.bass_boost,
                treble_boost=s.treble_boost,
                auto_expression_enabled=getattr(s, 'auto_expression_enabled', False),
                expression_sensitivity=getattr(s, 'expression_sensitivity', 1.0),
                model_path=s.model_path,            # Chatterbox local path
                moss_model_path=s.moss_model_path,   # MOSS-TTS local path
            )
            
            tasks.append(task)
            
        return tasks

    def start_generation(self, indices_to_process: Optional[List[int]] = None) -> None:
        """
        Prepares tasks and starts the GenerationThread.
        Main entry point for starting a generation run.
        """
        if self.worker_thread and self.worker_thread.isRunning():
            logging.warning("Generation already running.")
            return
        
        self.is_running = True
        self.started.emit()
        
        import time
        import os
        self.state.chunks_passed = 0
        self.state.chunks_failed = 0
        self.state.chunks_completed = 0
        self.state.generation_start_time = time.time()
        self.state.chunk_status.clear()
        
        self.stats_history = {'rms': [], 'f0_mean': []}
        
        s = self.state.settings
        outputs_dir = "Outputs_Pro" 
        
        # 1. Determine Scope
        if indices_to_process is not None:
             # Explicit list (e.g. retry or selected chapters)
             process_indices = [
                 i for i in indices_to_process 
                 if not self.state.sentences[i].get('is_pause')
                 and self.state.sentences[i].get('uuid')
             ]
        else:
             # Full run (filter not-done items)
             # Logic: Iterate ranges, collect all valid items
             process_indices = []
             for start, end in self._get_chapter_ranges():
                 chunk = list(range(start, end))
                 # Filter checks
                 valid = [
                     i for i in chunk 
                     if self.state.sentences[i].get('tts_generated') != STATUS_YES 
                     and not self.state.sentences[i].get('is_pause')
                 ]
                 process_indices.extend(valid)

        if not process_indices:
            logging.info("No chunks need generation (or all were pauses).")
            self.finished.emit()
            return

        # ONLY delete WAV files for chunks that are actively scheduled to be regenerated!
        # This prevents the system from permanently wiping successful chunks and breaking Playback logic
        for idx in process_indices:
            sentence = self.state.sentences[idx]
            audio_path = sentence.get('audio_path')
            if audio_path and os.path.exists(audio_path):
                try:
                    os.remove(audio_path)
                    logging.info(f"🗑️ Cleaned up old WAV file for regenerating chunk [{idx+1}]: {os.path.basename(audio_path)}")
                    sentence['audio_path'] = None  # Clear the path reference
                    sentence['tts_generated'] = 'no' # Reset status to prevent ghostly 'yes' UI
                except Exception as e:
                    logging.warning(f"Failed to delete old WAV {audio_path}: {e}")

        # 2. Configure Resources
        devices, max_workers = self._configure_workers(s.target_gpus, s.combine_gpus)
        
        # 3. Prepare Logic (Seed, etc)
        num_runs = 1
        if indices_to_process is None: # Only for full runs
             num_runs = max(1, s.num_full_outputs)
        
        tasks = []
        for run_i in range(num_runs):
            # Vary seed per run
            current_seed = s.master_seed + run_i if s.master_seed != 0 else random.randint(1, 2**32 - 1)
            
            run_tasks = self._prepare_tasks(process_indices, devices, current_seed, outputs_dir)
            
            # Update run_idx for all tasks in this batch
            if run_i > 0:
                for t in run_tasks:
                    t.run_idx = run_i
            
            tasks.extend(run_tasks)
            
        self.state.total_chunks = len(process_indices)  # Unique chunks, not tasks (which may include multiple runs)
        self.stats_updated.emit(self.state.total_chunks, 0, 0)  # Initial stats
            
        # 5. Start Thread
        self.worker_thread = GenerationThread(tasks, max_workers, outputs_dir)
        
        self.worker_thread.progress_update.connect(self.progress_update)
        self.worker_thread.batch_complete.connect(self._on_batch_complete)
        self.worker_thread.generation_done.connect(self._on_finished)  # Custom signal (fired inside run)
        self.worker_thread.stopped.connect(self._on_stopped)
        self.worker_thread.error_occurred.connect(self.error_occurred)
        # Connect Qt's REAL built-in QThread.finished to deleteLater so the C++ thread object
        # is only destroyed AFTER run() has fully returned and isRunning() is False.
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        
        self.worker_thread.start()

    def _journal_path(self) -> Optional[Path]:
        """Returns the active session's progress journal path, or None if no session is loaded."""
        if not self.state.session_name:
            return None
        from pathlib import Path
        return Path("Outputs_Pro") / self.state.session_name / "generation_progress.jsonl"

    def _append_to_journal(self, result: Dict[str, Any], sentence: Dict[str, Any]) -> None:
        """Appends a single completed chunk record to the crash-safe progress journal."""
        journal_path = self._journal_path()
        if not journal_path:
            return
        try:
            journal_path.parent.mkdir(parents=True, exist_ok=True)
            record = {
                "uuid": sentence.get("uuid", ""),
                "index": result.get("original_index"),
                "status": result.get("status", "error"),
                "path": result.get("path", ""),
                "similarity_ratio": result.get("similarity_ratio")
            }
            with open(journal_path, "a", encoding="utf-8") as f:
                f.write(__import__('json').dumps(record) + "\n")
        except Exception as e:
            logging.warning(f"Progress journal write failed: {e}")

    @Slot(list)
    def _on_batch_complete(self, results: List[Dict[str, Any]]) -> None:
        """Called on Main Thread when a BATCH of chunks finishes."""
        if not results: return
        
        updated_indices = []
        
        # Build quick lookup by UUID to handle shifted indices
        uuid_to_index = {item.get('uuid'): idx for idx, item in enumerate(self.state.sentences) if item.get('uuid')}
        
        for result in results:
            result_uuid = result.get('uuid')
            
            # Strict UUID matching: no fallback to original_index
            if not result_uuid or result_uuid not in uuid_to_index:
                logging.warning(f"Result returned for unknown/stale UUID '{result_uuid}'. Chunk was likely deleted or split. Ignoring.")
                # We do NOT delete the audio file here because it might be needed for crash recovery or manual inspection.
                # It will simply remain orphaned in the session folder.
                continue
                
            actual_idx = uuid_to_index[result_uuid]
                
            updated_indices.append(actual_idx)
            
            # Update State
            self.state.sentences[actual_idx]['generation_seed'] = result.get('seed')
            self.state.sentences[actual_idx]['similarity_ratio'] = result.get('similarity_ratio')
            
            if result.get('path'):
                self.state.sentences[actual_idx]['audio_path'] = result.get('path')
            
            status = result.get('status')
            asr = result.get('similarity_ratio', 0.0)
            
            old_status = self.state.chunk_status.get(actual_idx)
            new_status = 'passed' if status == 'success' else 'failed'
            
            # Update counters based on status transition
            if old_status == 'failed' and new_status == 'passed':
                self.state.chunks_failed -= 1
                self.state.chunks_passed += 1
            elif old_status == 'passed' and new_status == 'failed':
                self.state.chunks_passed -= 1
                self.state.chunks_failed += 1
            elif old_status is None:
                if new_status == 'passed':
                    self.state.chunks_passed += 1
                else:
                    self.state.chunks_failed += 1
            
            self.state.chunk_status[actual_idx] = new_status
            self.state.chunks_completed += 1
            
            if status == 'success':
                self.state.sentences[actual_idx]['tts_generated'] = STATUS_YES
                self.state.sentences[actual_idx]['marked'] = False
                logging.info(f"✅ Chunk [{actual_idx+1}] PASSED: ASR Match={asr*100:.1f}%")
            else:
                self.state.sentences[actual_idx]['tts_generated'] = STATUS_FAILED
                self.state.sentences[actual_idx]['marked'] = True
                error_msg = result.get('error_message', 'Unknown Error')
                logging.warning(f"❌ Chunk [{actual_idx+1}] FAILED: {error_msg} (ASR={asr*100:.1f}%)")

            # Persist this result to the crash-safe progress journal immediately
            self._append_to_journal(result, self.state.sentences[actual_idx])
        # Emit Aggregated Signals (Once per batch)
        
        # 1. Stats
        self.stats_updated.emit(
            self.state.total_chunks,
            self.state.chunks_passed,
            self.state.chunks_failed
        )
        
        # 2. ETA
        import time
        elapsed = time.time() - self.state.generation_start_time
        if self.state.chunks_completed > 0:
            avg_time_per_chunk = elapsed / self.state.chunks_completed
            remaining_chunks = self.state.total_chunks - self.state.chunks_completed
            eta_seconds = avg_time_per_chunk * remaining_chunks
            self.eta_updated.emit(eta_seconds)
            
        # 3. Item Updates (Pass list to View)
        self.items_updated.emit(updated_indices)

    @Slot()
    def _on_finished(self) -> None:
        # Clear the thread reference FIRST before any downstream calls.
        self.worker_thread = None
        self.is_running = False
        self._restore_max_attempts()
        self.finished.emit()

    @Slot()
    def _on_stopped(self) -> None:
        self.worker_thread = None
        self.is_running = False
        self._restore_max_attempts()
        self.stopped.emit()

    # --- Preview Logic ---
    preview_ready = Signal(str) # audio_file_path
    preview_error = Signal(str)

    def generate_preview(self, text: str) -> None:
        """
        Generates a quick preview of the text using current settings.
        Running in a transient thread to keep UI responsive.
        """
        if not text: return

        # Cleanup old previews to prevent clutter
        # We try to remove the '_preview' session folder
        import shutil
        try:
            preview_dir = Path("Outputs_Pro") / "_preview"
            if preview_dir.exists():
                shutil.rmtree(preview_dir, ignore_errors=True)
        except Exception as e:
            logging.warning(f"Failed to clean preview dir: {e}")

        # Constants
        preview_output = "preview_temp.wav" # Keep it simple
        
        # Prepare single task
        s = self.state.settings
        
        # Determine device
        devices, _ = self._configure_workers(s.target_gpus, s.combine_gpus)
        device = devices[0]
        
        # Create task object (
        # Note: Index -1 indicates this is a transient preview
        task = WorkerTask(
            task_index=-1,
            original_index=-1,
            sentence_number=0,
            text_chunk=punc_norm(text),
            device_str=device,
            master_seed=random.randint(1, 999999),
            ref_audio_path=self.state.ref_audio_path if self.state.ref_audio_path and self.state.ref_audio_path.strip() else None,
            exaggeration=s.exaggeration,
            temperature=s.temperature,
            cfg_weight=s.cfg_weight,
            disable_watermark=s.disable_watermark,
            num_candidates=1,
            max_attempts=s.max_attempts,
            bypass_asr=True, # skip ASR for preview speed
            session_name="_preview",
            run_idx=0,
            output_dir_str="Outputs_Pro",
            uuid=f"preview_{str(uuid.uuid4())[:8]}",
            asr_threshold=s.asr_threshold,
            speed=s.speed,
            tts_engine=s.tts_engine,
            combine_gpus=s.combine_gpus,
            pitch_shift=s.pitch_shift,
            timbre_shift=s.timbre_shift,
            gruffness=s.gruffness,
            bass_boost=s.bass_boost,
            treble_boost=s.treble_boost,
            auto_expression_enabled=getattr(s, 'auto_expression_enabled', False),
            expression_sensitivity=getattr(s, 'expression_sensitivity', 1.0),
            model_path=s.model_path,            # Chatterbox local path
            moss_model_path=s.moss_model_path,   # MOSS-TTS local path
        )
        
        self._preview_worker = PreviewWorker(task)
        self._preview_worker.finished_signal.connect(self.preview_ready)
        self._preview_worker.error_signal.connect(self.preview_error)
        self._preview_worker.start()

class PreviewWorker(QThread):
    finished_signal = Signal(str)
    error_signal = Signal(str)
    
    def __init__(self, task: Any) -> None:
        super().__init__()
        self.task = task
        
    def run(self) -> None:
        try:
            # We call the worker function directly 
            # Note: worker_process_chunk returns a dict with 'output_path' if successful
            result = worker_process_chunk(self.task)
            
            if result and result.get('status') == 'success':
                # FIX: Use the path returned by the worker, which knows the structure (Sentence_wavs/, audio_uuid.wav, etc.)
                actual_path = result.get('path')
                if actual_path and Path(actual_path).exists():
                     self.finished_signal.emit(str(Path(actual_path).absolute()))
                else:
                     # Fallback logic only if path missing from result (shouldn't happen with updated worker)
                     self.error_signal.emit("Worker finished but returned no valid path.")
            else:
                self.error_signal.emit(f"Generation failed: {result.get('error_message', 'Unknown error')}")

        except Exception as e:
            self.error_signal.emit(str(e))
