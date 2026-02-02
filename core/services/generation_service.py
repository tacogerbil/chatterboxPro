import logging
import random
import uuid
import multiprocessing
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
    Emits signals for progress and completion so the Service/UI stays responsive.
    """
    # Signals to communicate back to the Service (which runs on Main Thread)
    progress_update = Signal(int, int) # completed, total
    chunk_complete = Signal(int, dict) # original_index, result_payload
    finished = Signal()
    error_occurred = Signal(str)
    stopped = Signal()

    # Task structure passed via content dictionary for simplicity
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
        
        if self.executor:
            logging.warning("🛑 NUCLEAR STOP: Killing worker processes...")
            try:
                # 1. Cancel pending futures
                self.executor.shutdown(wait=False, cancel_futures=True)
                
                # 2. KILL running processes (not terminate - KILL)
                # MCCC: Explicit Intent - terminate() sends SIGTERM which CUDA can ignore
                # kill() sends SIGKILL which is instant death, no cleanup
                if hasattr(self.executor, '_processes'):
                    for pid, process in list(self.executor._processes.items()):
                        try:
                            process.kill()  # SIGKILL (was terminate/SIGTERM)
                            logging.warning(f"KILLED worker process {pid}")
                        except Exception as e:
                            logging.error(f"Failed to kill process {pid}: {e}")
                            
                # 3. Delayed Cleanup (Fallback)
                # If processes are STILL alive after 1 second, force kill again
                import threading
                def delayed_cleanup():
                    import time
                    time.sleep(1.0)
                    if hasattr(self.executor, '_processes'):
                        for pid, process in list(self.executor._processes.items()):
                            if process.is_alive():
                                try:
                                    process.kill()
                                    logging.warning(f"Delayed KILL on zombie process {pid}")
                                except:
                                    pass
                                    
                cleanup_thread = threading.Thread(target=delayed_cleanup, daemon=True)
                cleanup_thread.start()
                
            except Exception as e:
                logging.error(f"Error during nuclear stop: {e}")

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
            with ProcessPoolExecutor(max_workers=self.max_workers, mp_context=ctx) as executor:
                self.executor = executor
                # Map future -> task info (index 1 is original_index)
                futures = {executor.submit(worker_process_chunk, task): task for task in self.tasks}
                
                for future in as_completed(futures):
                    if self.stop_requested.is_set():
                         executor.shutdown(wait=False, cancel_futures=True)
                         self.stopped.emit()
                         return

                    try:
                        result = future.result()
                        if result and 'original_index' in result:
                            # Pass result back to Main Thread for state update
                            self.chunk_complete.emit(result['original_index'], result)
                    except Exception as e:
                        logging.error(f"Worker task error: {e}")
                        # Don't abort entire run for one chunk failure unless critical?
                        pass
                    
                    completed_count += 1
                    self.progress_update.emit(completed_count, total_tasks)
            
            self._cleanup_memory()
            
            if self.stop_requested.is_set():
                self.stopped.emit()
            else:
                self.finished.emit()

        except Exception as e:
            logging.error(f"GenerationThread crashed: {e}", exc_info=True)
            self.error_occurred.emit(str(e))

class GenerationService(QObject):
    """
    Handles the multi-process TTS generation.
    Decoupled from UI, uses Signals for updates.
    Manages a QThread to keep UI responsive.
    MCCC Compliant: SRP, Explicit Interfaces.
    """
    
    # Signals
    progress_update = Signal(int, int) # completed, total
    item_updated = Signal(int) # index of updated item
    started = Signal()
    finished = Signal()
    stopped = Signal()
    error_occurred = Signal(str)
    
    # Progress Tracking Signals (MCCC: Explicit Statistics Interface)
    stats_updated = Signal(int, int, int)  # total, passed, failed
    eta_updated = Signal(float)  # seconds remaining
    
    # Auto-Fix Signals
    auto_fix_status = Signal(str) # Status message for UI
    
    def __init__(self, app_state: AppState) -> None:
        super().__init__()
        self.state = app_state
        self.worker_thread: Optional[GenerationThread] = None
        self.playlist_service: Optional[Any] = None # Injected dependency
        self.auto_fix_stage: str = "NONE" 
        self._loop_iteration: int = 0
        self.is_running: bool = False  # MCCC: Track generation state

    def set_playlist_service(self, service: Any) -> None:
        self.playlist_service = service

    def request_stop(self) -> None:
        """Sets the stop flag to terminate generation."""
        self.auto_fix_stage = "NONE" # Hard stop breaks loop
        if self.worker_thread and self.worker_thread.isRunning():
            logging.info("Generation stop requested...")
            self.worker_thread.request_stop()
        else:
            self.stopped.emit()

    def _auto_fix_logic(self) -> None:
        """
        State machine for auto-regeneration loops.
        Handles retries, splitting, and infinite looping for stubborn chunks.
        """
        # 1. Identify Failures
        failed_indices = [
            i for i, s in enumerate(self.state.sentences) 
            if s.get('tts_generated') == STATUS_FAILED
        ]
        
        if not failed_indices:
            self.auto_fix_stage = "NONE"
            logging.info("Auto-Fix: All clear.")
            self.finished.emit() 
            return

        # 2. State Transition
        if self.auto_fix_stage == "MAIN_INITIAL":
            # Initial run had failures. Trigger Retry 1.
            self.auto_fix_stage = "MAIN_RETRY_1"
            self.auto_fix_status.emit(f"Auto-Fix: Retry 1 ({len(failed_indices)} items)...")
            
            # Mark failed for regeneration
            for idx in failed_indices: 
                self.state.sentences[idx]['marked'] = True
                
            self.start_generation(failed_indices)

        elif self.auto_fix_stage == "MAIN_RETRY_1":
            # Retry 1 had failures. Split them.
            self.auto_fix_stage = "MAIN_SPLIT"
            self.auto_fix_status.emit(f"Auto-Fix: Splitting {len(failed_indices)} failed items...")
            
            if self.playlist_service:
                count = self.playlist_service.split_all_failed(confirm=False)
            
            # After splitting, identify new marked items (the pieces)
            new_marked = [i for i, s in enumerate(self.state.sentences) if s.get('marked')]
            self.start_generation(new_marked)

        elif self.auto_fix_stage == "MAIN_SPLIT":
            # Post-Split run finished. If failures remain, enter infinite loop.
            self.auto_fix_stage = "MAIN_LOOP"
            self._loop_iteration = 0
            self.auto_fix_status.emit(f"Auto-Fix: Entering Loop for {len(failed_indices)} items...")
            self.start_generation(failed_indices)

        elif self.auto_fix_stage == "MAIN_LOOP":
            # Infinite loop until success or stop
            self._loop_iteration += 1
            self.auto_fix_status.emit(f"Auto-Fix: Loop Iteration {self._loop_iteration} ({len(failed_indices)} items)...")
            self.start_generation(failed_indices)
            
        else:
            self.finished.emit()

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

    def _configure_workers(self, target_gpus: str) -> Tuple[List[str], int]:
        """Determines devices and max_workers based on settings and hardware."""
        gpu_count = torch.cuda.device_count() if torch.cuda.is_available() else 0
        
        if "cpu" in target_gpus or gpu_count == 0:
            return ["cpu"], 1
            
        devices = [d.strip() for d in target_gpus.split(',') if d.strip()]
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
                pitch_shift=s.pitch_shift,
                timbre_shift=s.timbre_shift,
                gruffness=s.gruffness,
                bass_boost=s.bass_boost,
                treble_boost=s.treble_boost,
                auto_expression_enabled=getattr(s, 'auto_expression_enabled', False),
                expression_sensitivity=getattr(s, 'expression_sensitivity', 1.0),
                model_path=s.model_path 
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
        
        self.is_running = True  # MCCC: Set running state
        self.started.emit()
        
        # MCCC: Reset Progress Statistics
        import time
        import os
        self.state.chunks_passed = 0
        self.state.chunks_failed = 0
        self.state.chunks_completed = 0
        self.state.generation_start_time = time.time()
        self.state.chunk_status.clear()
        
        # MCCC: Smart WAV File Cleanup
        # Delete WAV files for chunks that are NOT marked as successful
        # This ensures a clean slate when regenerating unmarked chunks
        for idx, sentence in enumerate(self.state.sentences):
            # Only delete if chunk is NOT marked as successful
            if sentence.get('tts_generated') != STATUS_YES:
                audio_path = sentence.get('audio_path')
                if audio_path and os.path.exists(audio_path):
                    try:
                        os.remove(audio_path)
                        logging.info(f"🗑️ Cleaned up WAV file for unmarked chunk [{idx+1}]: {os.path.basename(audio_path)}")
                        sentence['audio_path'] = None  # Clear the path reference
                    except Exception as e:
                        logging.warning(f"Failed to delete {audio_path}: {e}")
        
        s = self.state.settings
        outputs_dir = "Outputs_Pro" 
        
        # 1. Determine Scope
        if indices_to_process is not None:
             # Explicit list (e.g. retry or selected chapters)
             # MCCC: Must filter out pauses here too!
             process_indices = [
                 i for i in indices_to_process 
                 if not self.state.sentences[i].get('is_pause')
                 and self.state.sentences[i].get('uuid') # MCCC: Safety check
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

        # 2. Configure Resources
        devices, max_workers = self._configure_workers(s.target_gpus)
        
        # 3. Prepare Logic (Seed, etc)
        # MCCC Audit: Handle Multiple Full Outputs
        # If indices_to_process is None (Full Run), respect num_full_outputs.
        # If explicit indices (Repair/Retry), run only once (run_idx=0).
        
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
            
        # MCCC: Set total chunks for progress tracking
        self.state.total_chunks = len(process_indices)  # Unique chunks, not tasks (which may include multiple runs)
        self.stats_updated.emit(self.state.total_chunks, 0, 0)  # Initial stats
            
        # 5. Start Thread
        self.worker_thread = GenerationThread(tasks, max_workers, outputs_dir)
        
        self.worker_thread.progress_update.connect(self.progress_update)
        self.worker_thread.chunk_complete.connect(self._on_chunk_complete)
        self.worker_thread.finished.connect(self._on_finished)
        self.worker_thread.stopped.connect(self._on_stopped)
        self.worker_thread.error_occurred.connect(self.error_occurred)
        
        self.worker_thread.start()
        
    @Slot(int, dict)
    def _on_chunk_complete(self, original_idx: int, result: Dict[str, Any]) -> None:
        """Called on Main Thread when a chunk finishes."""
        # Update State
        self.state.sentences[original_idx]['generation_seed'] = result.get('seed')
        self.state.sentences[original_idx]['similarity_ratio'] = result.get('similarity_ratio')
        
        # MCCC: Store audio path for playback
        if result.get('path'):
            self.state.sentences[original_idx]['audio_path'] = result.get('path')
        
        status = result.get('status')
        asr = result.get('similarity_ratio', 0.0)
        
        # MCCC: Track Statistics (Dynamic - Handles Regeneration)
        old_status = self.state.chunk_status.get(original_idx)
        new_status = 'passed' if status == 'success' else 'failed'
        
        # Update counters based on status transition
        if old_status == 'failed' and new_status == 'passed':
            # Regeneration success: failed -> passed
            self.state.chunks_failed -= 1
            self.state.chunks_passed += 1
        elif old_status == 'passed' and new_status == 'failed':
            # Regression: passed -> failed (rare, but possible)
            self.state.chunks_passed -= 1
            self.state.chunks_failed += 1
        elif old_status is None:
            # First time processing this chunk
            if new_status == 'passed':
                self.state.chunks_passed += 1
            else:
                self.state.chunks_failed += 1
        # else: same status, no change needed
        
        self.state.chunk_status[original_idx] = new_status
        self.state.chunks_completed += 1
        
        # Emit statistics update
        self.stats_updated.emit(
            self.state.total_chunks,
            self.state.chunks_passed,
            self.state.chunks_failed
        )
        
        # Calculate and emit ETA
        import time
        elapsed = time.time() - self.state.generation_start_time
        if self.state.chunks_completed > 0:
            avg_time_per_chunk = elapsed / self.state.chunks_completed
            remaining_chunks = self.state.total_chunks - self.state.chunks_completed
            eta_seconds = avg_time_per_chunk * remaining_chunks
            self.eta_updated.emit(eta_seconds)
        
        if status == 'success':
            self.state.sentences[original_idx]['tts_generated'] = STATUS_YES
            self.state.sentences[original_idx]['marked'] = False
            logging.info(f"✅ Chunk [{original_idx+1}] PASSED: ASR Match={asr*100:.1f}%")
        else:
            self.state.sentences[original_idx]['tts_generated'] = STATUS_FAILED
            self.state.sentences[original_idx]['marked'] = True
            error_msg = result.get('error_message', 'Unknown Error')
            logging.warning(f"❌ Chunk [{original_idx+1}] FAILED: {error_msg} (ASR={asr*100:.1f}%)")
        
        # Emit update for UI
        self.item_updated.emit(original_idx)

    @Slot()
    def _on_finished(self) -> None:
        # Check auto-fix logic
        if self.state.auto_regen_main:
             self._auto_fix_logic()
        else:
             self.finished.emit()
        self.worker_thread = None
        self.is_running = False  # MCCC: Reset running state

    @Slot()
    def _on_stopped(self) -> None:
        self.stopped.emit()
        self.worker_thread = None
        self.is_running = False  # MCCC: Reset running state

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
        devices, _ = self._configure_workers(s.target_gpus)
        device = devices[0]
        
        # Create task tuple (similar to _prepare_tasks but simplified)
        # Note: Index -1 indicates this is a transient preview, not a sentence item
        # Create task object (MCCC: Explicit Interface)
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
            pitch_shift=s.pitch_shift,
            timbre_shift=s.timbre_shift,
            gruffness=s.gruffness,
            bass_boost=s.bass_boost,
            treble_boost=s.treble_boost,
            auto_expression_enabled=getattr(s, 'auto_expression_enabled', False),
            expression_sensitivity=getattr(s, 'expression_sensitivity', 1.0),
            model_path=s.model_path
        )
        
        # We can reuse GenerationThread, or just spawn a simple thread 
        # Since GenerationThread assumes "chunk_complete" behavior mapped to state, 
        # we might want a lightweight PreviewThread.
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
