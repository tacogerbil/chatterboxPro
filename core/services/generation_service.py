import logging
import random
import shutil
import multiprocessing
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import torch

from PySide6.QtCore import QObject, Signal, QThread, Slot
from workers.tts_worker import worker_process_chunk
from utils.text_processor import punc_norm
from core.state import AppState

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

    def __init__(self, state_snapshot: dict, tasks: list, max_workers: int, outputs_dir: str):
        super().__init__()
        self.state_settings = state_snapshot # Dict of settings
        self.tasks = tasks
        self.max_workers = max_workers
        self.outputs_dir = outputs_dir
        self.stop_requested = multiprocessing.Event()
        self.executor = None

    def request_stop(self):
        self.stop_requested.set()

    def _cleanup_memory(self):
        import gc
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()

    def run(self):
        """The main blocking loop runs here, in a separate thread."""
        try:
            completed_count = 0
            total_tasks = len(self.tasks)
            self.progress_update.emit(0, total_tasks)

            ctx = multiprocessing.get_context('spawn')
            with ProcessPoolExecutor(max_workers=self.max_workers, mp_context=ctx) as executor:
                self.executor = executor
                futures = {executor.submit(worker_process_chunk, task): task[1] for task in self.tasks}
                
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
                        # Taking parity with legacy: Log and marked as failed
                        # But exception here means CRASH in worker logic before returning payload
                        # We can emit a failure payload manually if needed
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
        finally:
            # Cleanup temp dirs? Managed by Service usually?
            # Or define temp dir usage here.
            # Legacy logic handled `run_temp_dir` cleanup after loop.
            # We can't easily clean it here without knowing which run it was.
            # For this MVP refactor, we rely on standard cleanup.
            pass

class GenerationService(QObject):
    """
    Handles the multi-process TTS generation.
    Decoupled from UI, uses Signals for updates.
    Manages a QThread to keep UI responsive.
    """
    
    # Signals
    progress_update = Signal(int, int) # completed, total
    item_updated = Signal(int) # index of updated item
    started = Signal()
    finished = Signal()
    stopped = Signal()
    error_occurred = Signal(str)
    
    # Auto-Fix Signals
    auto_fix_status = Signal(str) # "Splitting failed chunks...", "Retrying...", etc.
    
    def __init__(self, app_state: AppState):
        super().__init__()
        self.state = app_state
        self.worker_thread = None
        self.playlist_service = None # Injected dependency for splitting
        self.auto_fix_stage = "NONE" # NONE, MAIN_INITIAL, MAIN_RETRY_1, MAIN_SPLIT, MAIN_LOOP
        self._loop_iteration = 0

    def set_playlist_service(self, service):
        self.playlist_service = service

    def request_stop(self):
        """Sets the stop flag to terminate generation."""
        self.auto_fix_stage = "NONE" # Hard stop breaks loop
        if self.worker_thread and self.worker_thread.isRunning():
            logging.info("Generation stop requested...")
            self.worker_thread.request_stop()
        else:
            self.stopped.emit()

    def _auto_fix_logic(self):
        """
        State machine for auto-regeneration loops.
        Ported from Legacy main_window.py _auto_fix_logic.
        """
        # 1. Identify Failures
        failed_indices = [i for i, s in enumerate(self.state.sentences) if s.get('tts_generated') == 'failed']
        
        if not failed_indices:
            self.auto_fix_stage = "NONE"
            logging.info("Auto-Fix: All clear.")
            self.finished.emit() # Real finish
            
            # Check Auto-Assemble
            if self.state.auto_assemble_after_run:
                pass # TODO: Emit signal to trigger assembly? Or handle elsewhere.
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
            
            # Call Splitting Logic
            if self.playlist_service:
                # We split ALL failed chunks.
                # Note: This modifies indices, so we must be careful with recursive calls.
                count = self.playlist_service.split_all_failed(confirm=False)
                if count == 0:
                     # Could not split (maybe too short). Force loop or stop?
                     # Legacy behavior: Move to Loop anyway.
                     pass
            
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
            # Infinite loop untill success or stop
            self._loop_iteration += 1
            self.auto_fix_status.emit(f"Auto-Fix: Loop Iteration {self._loop_iteration} ({len(failed_indices)} items)...")
            self.start_generation(failed_indices)
            
        else:
            # Should not happen if logic is correct, or stage was NONE
            self.finished.emit()

    def _get_chapter_ranges(self):
        """Returns list of (start_idx, end_idx) for each chapter."""
        chapter_starts = [i for i, s in enumerate(self.state.sentences) 
                          if s.get('is_chapter_heading')]
        
        if not chapter_starts:
            return [(0, len(self.state.sentences))]
        
        ranges = []
        for i, start in enumerate(chapter_starts):
            end = chapter_starts[i+1] if i+1 < len(chapter_starts) else len(self.state.sentences)
            ranges.append((start, end))
        return ranges

    def start_generation(self, indices_to_process=None):
        """
        Prepares tasks and starts the GenerationThread.
        Non-blocking.
        """
        if self.worker_thread and self.worker_thread.isRunning():
            logging.warning("Generation already running.")
            return

        self.started.emit()
        s = self.state.settings
        outputs_dir = "Outputs_Pro" 
        session_name = self.state.session_name
        
        # Logic to prepare tasks (Fastest First, etc)
        # We process ALL chapters in one go? Or queue them?
        # Legacy looped chapters.
        # To keep it simple inside Thread, we should flatten the chapters into one big list of tasks
        # OR run thread per chapter?
        # A single big list is best for packing.
        
        # Prepare Tasks
        tasks = []
        
        # Determine Runs (assuming 1 run for now or loop logic inside thread?)
        # Legacy loop: for run_idx in range(num_runs):
        # We will support 1 run for now in this Thread refactor, usually fine unless bulk generating.
        # If num_runs > 1, we should ideally queue them.
        # For parity, we'll implement logic for Run 0.
        
        run_idx = 0
        current_run_master_seed = (s.master_seed + run_idx) if s.master_seed != 0 else random.randint(1, 2**32 - 1)
        
        chapter_ranges = self._get_chapter_ranges()
        
        # Devices
        gpu_count = torch.cuda.device_count() if torch.cuda.is_available() else 0
        if "cpu" in s.target_gpus or gpu_count == 0:
                max_workers = 1
                devices = ["cpu"]
        else:
                devices = [d.strip() for d in s.target_gpus.split(',') if d.strip()]
                max_workers = len(devices)

        # Collect tasks across all chapters
        all_process_indices = []
        for start, end in chapter_ranges:
            indices = list(range(start, end))
            if indices_to_process is not None:
                filtered = [i for i in indices if i in indices_to_process]
            else:
                filtered = [i for i in indices if self.state.sentences[i].get('tts_generated') != 'yes']
            
            filtered = [i for i in filtered if not self.state.sentences[i].get('is_pause')]
            all_process_indices.extend(filtered)

        if not all_process_indices:
            logging.info("No chunks need generation.")
            self.finished.emit()
            return
            
        # Sorting "Fastest First"
        chunks_to_process_sorted = sorted(all_process_indices, key=lambda i: len(self.state.sentences[i]['original_sentence']), reverse=True)
        
        # Create Task Tuples
        for i, original_idx in enumerate(chunks_to_process_sorted):
            sentence_data = self.state.sentences[original_idx]
            task = (
                i, original_idx, int(sentence_data.get('sentence_number', i+1)),
                punc_norm(sentence_data['original_sentence']),
                devices[i % len(devices)], 
                current_run_master_seed,
                self.state.ref_audio_path, 
                s.exaggeration, s.temperature,
                s.cfg_weight, s.disable_watermark,
                s.num_candidates,
                s.max_attempts,
                not s.asr_validation_enabled, session_name,
                run_idx, outputs_dir, sentence_data['uuid'],
                s.asr_threshold,
                s.speed,
                s.tts_engine,
                s.pitch_shift,   # NEW
                s.timbre_shift,  # NEW
                s.gruffness      # NEW
            )
            tasks.append(task)
            
        # Create and Start Thread
        # We assume settings won't change mid-run, so we passed values in tasks.
        self.worker_thread = GenerationThread({}, tasks, max_workers, outputs_dir)
        
        self.worker_thread.progress_update.connect(self.progress_update)
        self.worker_thread.chunk_complete.connect(self._on_chunk_complete)
        self.worker_thread.finished.connect(self._on_finished)
        self.worker_thread.stopped.connect(self._on_stopped)
        self.worker_thread.error_occurred.connect(self.error_occurred)
        
        self.worker_thread.start()
        
    @Slot(int, dict)
    def _on_chunk_complete(self, original_idx, result):
        """Called on Main Thread when a chunk finishes."""
        # Update State
        self.state.sentences[original_idx]['generation_seed'] = result.get('seed')
        self.state.sentences[original_idx]['similarity_ratio'] = result.get('similarity_ratio')
        
        status = result.get('status')
        if status == 'success':
            self.state.sentences[original_idx]['tts_generated'] = 'yes'
            self.state.sentences[original_idx]['marked'] = False
        else:
            self.state.sentences[original_idx]['tts_generated'] = 'failed'
            self.state.sentences[original_idx]['marked'] = True
        
        # Emit update for UI
        self.item_updated.emit(original_idx)

    @Slot()
    def _on_finished(self):
        # Instead of plain finish, check auto-fix logic
        if self.state.auto_regen_main:
             # Delay slightly to allow UI to update? No, pure logic.
             self._auto_fix_logic()
        else:
             self.finished.emit()
        self.worker_thread = None

    @Slot()
    def _on_stopped(self):
        self.stopped.emit()
        self.worker_thread = None
