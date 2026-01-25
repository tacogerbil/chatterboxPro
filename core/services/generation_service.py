import logging
import random
import shutil
import multiprocessing
import concurrent.futures
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import torch

from PySide6.QtCore import QObject, Signal, QTimer
# We reuse the existing worker because it is pure logic (no UI dependency)
from workers.tts_worker import worker_process_chunk
from utils.text_processor import punc_norm
from core.state import AppState

class GenerationService(QObject):
    """
    Handles the multi-process TTS generation.
    Decoupled from UI, uses Signals for updates.
    """
    
    # Signals
    progress_update = Signal(int, int) # completed, total
    item_updated = Signal(int) # index of updated item
    started = Signal()
    finished = Signal()
    stopped = Signal()
    error_occurred = Signal(str)
    
    def __init__(self, app_state: AppState):
        super().__init__()
        self.state = app_state
        self.stop_flag = multiprocessing.Event()
        self.executor = None
        
    def request_stop(self):
        """Sets the stop flag to terminate generation."""
        self.stop_flag.set()
        logging.info("Generation stop requested...")

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

    def _cleanup_memory(self):
        import gc
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()

    def start_generation(self, indices_to_process=None):
        """
        Starts the generation process.
        NOTE: This is a blocking call if run in main thread.
        Ideally should be run in a QThread. For now, we will run logic here
        but use ProcessPoolExecutor for the heavy lifting.
        Process events might hang if we don't thread this method itself.
        """
        # We really should run this entire method in a thread to keep GUI responsive.
        # But ProcessPoolExecutor handles the heavies. The loop logic is fast.
        # Let's try running it directly, pumping events if needed, OR use a worker thread for the service loop.
        # For simplicity in this port, we will assume the caller puts this in a Thread 
        # OR we rely on the fact that `as_completed` blocks but we can update UI via signals.
        # Actually, if we block main thread, signals won't process until function returns!
        # Thus, `GenerationService` needs to be moved to a Thread or run this logic in a Thread.
        
        # We will implement `run_in_thread` pattern from the View side?
        # Or simpler: The View creates a generic QThread that runs `service.run()`.
        self.stop_flag.clear()
        self.started.emit()
        
        try:
            self._run_logic(indices_to_process)
        except Exception as e:
            logging.error(f"Generation failed: {e}", exc_info=True)
            self.error_occurred.emit(str(e))
        finally:
            self.finished.emit()

    def _run_logic(self, indices_to_process):
        s = self.state.settings
        outputs_dir = "Outputs_Pro" # Fixed or from settings? Legacy strict "Outputs_Pro"
        session_name = self.state.session_name
        
        num_runs = s.num_full_outputs if not indices_to_process else 1

        for run_idx in range(num_runs):
            run_temp_dir = Path(outputs_dir) / session_name / f"run_{run_idx+1}_temp"
            try:
                if self.stop_flag.is_set(): break

                # Reset status logic (Legacy Line 62)
                if run_idx > 0 and not indices_to_process:
                    for item in self.state.sentences: 
                        item['tts_generated'] = 'no'
                    # Signal view refresh needed? 
                    # We can't batch signal easily, maybe emit one general refresh?
                    # For now, items will update individually.

                master_seed = s.master_seed
                current_run_master_seed = (master_seed + run_idx) if master_seed != 0 else random.randint(1, 2**32 - 1)

                chapter_ranges = self._get_chapter_ranges()
                
                for chapter_idx, (chapter_start, chapter_end) in enumerate(chapter_ranges):
                    if self.stop_flag.is_set(): break
                    
                    # Prepare indices
                    chapter_indices = list(range(chapter_start, chapter_end))
                    
                    if indices_to_process is not None:
                        process_list = [i for i in chapter_indices if i in indices_to_process]
                    else:
                        process_list = [i for i in chapter_indices if self.state.sentences[i].get('tts_generated') != 'yes']
                    
                    process_list = [i for i in process_list if not self.state.sentences[i].get('is_pause')]

                    if not process_list: continue

                    # Workers setup
                    # Assuming we check GPU count from torch locally used inside logic
                    gpu_count = torch.cuda.device_count() if torch.cuda.is_available() else 0
                    if "cpu" in s.target_gpus or gpu_count == 0:
                         max_workers = 1
                         devices = ["cpu"]
                    else:
                         # Heuristic: Parse target_gpus string "cuda:0,cuda:1"
                         devices = [d.strip() for d in s.target_gpus.split(',') if d.strip()]
                         max_workers = len(devices)

                    # Sorting
                    if hasattr(self.state, 'generation_order_str'): # Check legacy var existence or use default
                         # Assuming 'Fastest First' is default logic in Settings?
                         # Settings dataclass doesn't have generation_order string? 
                         # Checking state.py... it is NOT in GenerationSettings.
                         # It was in UI vars. We assume "Fastest First" for now.
                         chunks_to_process_sorted = sorted(process_list, key=lambda i: len(self.state.sentences[i]['original_sentence']), reverse=True)
                    else:
                         chunks_to_process_sorted = sorted(process_list, key=lambda i: len(self.state.sentences[i]['original_sentence']), reverse=True)

                    tasks = []
                    for i, original_idx in enumerate(chunks_to_process_sorted):
                        sentence_data = self.state.sentences[original_idx]
                        task = (
                            i, original_idx, int(sentence_data.get('sentence_number', i+1)),
                            punc_norm(sentence_data['original_sentence']),
                            devices[i % len(devices)], 
                            current_run_master_seed,
                            self.state.ref_audio_path, s.exaggeration, s.temperature,
                            s.cfg_weight, s.disable_watermark,
                            s.num_candidates,
                            s.max_attempts,
                            not s.asr_validation_enabled, session_name,
                            run_idx, outputs_dir, sentence_data['uuid'],
                            s.asr_threshold,
                            s.speed,
                            s.tts_engine
                        )
                        tasks.append(task)

                    self.progress_update.emit(0, len(tasks))
                    completed_count = 0

                    ctx = multiprocessing.get_context('spawn')
                    with ProcessPoolExecutor(max_workers=max_workers, mp_context=ctx) as executor:
                        self.executor = executor
                        futures = {executor.submit(worker_process_chunk, task): task[1] for task in tasks}
                        
                        try:
                            for future in as_completed(futures):
                                if self.stop_flag.is_set():
                                    executor.shutdown(wait=False, cancel_futures=True)
                                    self.stopped.emit()
                                    break
                                
                                result = future.result()
                                if result and 'original_index' in result:
                                    original_idx = result['original_index']
                                    
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
                                    
                                    # Emit update for this item
                                    self.item_updated.emit(original_idx)

                                completed_count += 1
                                self.progress_update.emit(completed_count, len(tasks))
                                
                        except Exception as e:
                            logging.error(f"Executor loop error: {e}")
                            executor.shutdown(wait=False, cancel_futures=True)
                            raise e
                    
                    self._cleanup_memory()

                if self.stop_flag.is_set(): break
            
            finally:
                if run_temp_dir.exists():
                     try: shutil.rmtree(run_temp_dir)
                     except: pass
                     
        logging.info("Generation Service run complete.")
