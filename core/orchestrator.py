# core/orchestrator.py
import logging
import random
import gc
from pathlib import Path
import shutil
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing
from tkinter import messagebox
import torch

from workers.tts_worker import worker_process_chunk
from utils.text_processor import punc_norm

class GenerationOrchestrator:
    """Handles the entire multi-GPU generation process."""
    def __init__(self, app_instance):
        self.app = app_instance

    def _get_chapter_ranges(self):
        """Returns list of (start_idx, end_idx) for each chapter."""
        chapter_starts = [i for i, s in enumerate(self.app.sentences) 
                          if s.get('is_chapter_heading')]
        
        if not chapter_starts:
            # No chapters detected - treat whole book as one chapter
            return [(0, len(self.app.sentences))]
        
        ranges = []
        for i, start in enumerate(chapter_starts):
            end = chapter_starts[i+1] if i+1 < len(chapter_starts) else len(self.app.sentences)
            ranges.append((start, end))
        
        return ranges
    
    def _cleanup_memory(self):
        """Force RAM and GPU cleanup between chapters."""
        import gc
        import torch
        
        logging.info("Cleaning up memory between chapters...")
        
        # Python garbage collection
        gc.collect()
        
        # GPU cache cleanup
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()  # Wait for GPU operations to finish
        
        logging.info("Memory cleanup complete")

    def run(self, indices_to_process=None):
        app = self.app
        num_runs = app.get_validated_int(app.num_full_outputs_str, 1) if not indices_to_process else 1

        for run_idx in range(num_runs):
            run_temp_dir = Path(app.OUTPUTS_DIR) / app.session_name.get() / f"run_{run_idx+1}_temp"
            try:
                if app.stop_flag.is_set(): break

                if run_idx > 0 and not indices_to_process:
                    logging.info(f"Resetting generation status for Run {run_idx + 1}")
                    for s in app.sentences: s['tts_generated'] = 'no'
                    app.after(0, app.playlist_frame.display_page, app.playlist_frame.current_page)
                    app.save_session()

                master_seed = app.get_validated_int(app.master_seed_str, 0)
                current_run_master_seed = (master_seed + run_idx) if master_seed != 0 else random.randint(1, 2**32 - 1)

                # Get chapter ranges for chapter-by-chapter processing
                chapter_ranges = self._get_chapter_ranges()
                logging.info(f"\\n--- Starting {'Regeneration' if indices_to_process else f'Full Run {run_idx+1}/{num_runs}'} with {len(chapter_ranges)} chapter(s) ---")

                for chapter_idx, (chapter_start, chapter_end) in enumerate(chapter_ranges):
                    if app.stop_flag.is_set(): break
                    
                    logging.info(f"\\n=== Processing Chapter {chapter_idx+1}/{len(chapter_ranges)} (Indices {chapter_start}-{chapter_end-1}) ===")
                    
                    # Get indices for this chapter
                    chapter_indices = list(range(chapter_start, chapter_end))
                    
                    # Filter based on what needs processing
                    if indices_to_process is not None:
                        process_list = [i for i in chapter_indices if i in indices_to_process]
                    else:
                        process_list = [i for i in chapter_indices if app.sentences[i].get('tts_generated') != 'yes']
                    
                    process_list = [i for i in process_list if not app.sentences[i].get('is_pause')]

                    if not process_list:
                        logging.info(f"Chapter {chapter_idx+1}: All chunks already generated, skipping.")
                        continue

                    # Determine worker count: 1 by default, 2 if dual-GPU enabled and available
                    if app.use_dual_gpu.get() and app.gpu_count >= 2:
                        devices = [f"cuda:{i}" for i in range(2)]
                        max_workers = 2
                    else:
                        devices = ["cuda:0"] if torch.cuda.is_available() else ["cpu"]
                        max_workers = 1
                    
                    logging.info(f"Using {max_workers} worker(s) on devices: {devices}")

                    generation_order = app.generation_order.get()
                    if generation_order == "Fastest First":
                        chunks_to_process_sorted = sorted(process_list, key=lambda i: len(app.sentences[i]['original_sentence']), reverse=True)
                    else: # "In Order"
                        chunks_to_process_sorted = sorted(process_list, key=lambda i: int(app.sentences[i]['sentence_number']))
                    
                    tasks = []
                    for i, original_idx in enumerate(chunks_to_process_sorted):
                        sentence_data = app.sentences[original_idx]
                        task = (
                            i, original_idx, int(sentence_data['sentence_number']),
                            punc_norm(sentence_data['original_sentence']),
                            devices[i % len(devices)], 
                            current_run_master_seed,
                            app.ref_audio_path.get(), app.exaggeration.get(), app.temperature.get(),
                            app.cfg_weight.get(), app.disable_watermark.get(),
                            app.get_validated_int(app.num_candidates_str, 1),
                            app.get_validated_int(app.max_attempts_str, 1),
                            not app.asr_validation_enabled.get(), app.session_name.get(),
                            run_idx, app.OUTPUTS_DIR, sentence_data['uuid'],
                            app.get_validated_float(app.asr_threshold_str, 0.85),
                            app.speed.get(),  # Speed parameter for FFmpeg post-processing
                            app.tts_engine.get()  # TTS engine selection
                        )
                        tasks.append(task)

                    app.after(0, app.update_progress_display, 0, 0, len(tasks))
                    completed_count = 0

                    ctx = multiprocessing.get_context('spawn')
                    with ProcessPoolExecutor(max_workers=max_workers, mp_context=ctx) as executor:
                        futures = {executor.submit(worker_process_chunk, task): task[1] for task in tasks}
                        try:
                            for future in as_completed(futures):
                                if app.stop_flag.is_set():
                                    logging.info("Stop flag detected - terminating all worker processes...")
                                    # Cancel all pending futures
                                    for f in futures.keys():
                                        f.cancel()
                                    # Force shutdown executor to kill running processes
                                    executor.shutdown(wait=False, cancel_futures=True)
                                    logging.info("All workers terminated.")
                                    break
                                
                                # Process completed future
                                try:
                                    result = future.result()
                                except concurrent.futures.process.BrokenProcessPool as e:
                                    # Worker crashed - log details
                                    task_info = futures.get(future, {})
                                    logging.error(f"Worker crashed for task {task_info}: {e}")
                                    # Mark as failed
                                    if 'original_index' in task_info:
                                        idx = task_info['original_index']
                                        app.sentences[idx]['tts_generated'] = 'failed'
                                        app.sentences[idx]['error_message'] = f"Worker crash: {e}"
                                except Exception as e:
                                    # Other errors
                                    task_info = futures.get(future, {})
                                    logging.error(f"Error processing result for task {task_info}: {e}", exc_info=True)
                                else:
                                    # Successfully got result - process it
                                    if result and 'original_index' in result:
                                        original_idx = result['original_index']
                                        
                                        app.sentences[original_idx].pop('similarity_ratio', None)
                                        app.sentences[original_idx].pop('generation_seed', None)

                                        status = result.get('status')
                                        app.sentences[original_idx]['generation_seed'] = result.get('seed')
                                        app.sentences[original_idx]['similarity_ratio'] = result.get('similarity_ratio')

                                        if status == 'success':
                                            app.sentences[original_idx]['tts_generated'] = 'yes'
                                            app.sentences[original_idx]['marked'] = False
                                        else:
                                            app.sentences[original_idx]['tts_generated'] = 'failed'
                                            app.sentences[original_idx]['marked'] = True
                                            if status == 'failed_placeholder':
                                                logging.warning(f"Chunk {app.sentences[original_idx]['sentence_number']} failed validation. A placeholder audio was saved. Marked for regeneration.")
                                            else: 
                                                logging.error(f"Chunk {app.sentences[original_idx]['sentence_number']} had a hard error during generation and was marked.")
                                                
                                        app.after(0, app.playlist_frame.update_item, original_idx)
                                
                                finally:
                                    # Always update progress
                                    completed_count += 1
                                    app.after(0, app.update_progress_display, completed_count / len(tasks), completed_count, len(tasks))
                        except Exception as e:
                            logging.error(f"Error during generation: {e}", exc_info=True)
                            # Ensure executor shuts down even if there's an error
                            executor.shutdown(wait=False, cancel_futures=True)
                    
                    # CRITICAL: Clean up memory after each chapter
                    self._cleanup_memory()
                    logging.info(f"Chapter {chapter_idx+1}/{len(chapter_ranges)} complete. Moving to next chapter...")

                if not app.stop_flag.is_set() and not indices_to_process and app.auto_assemble_after_run.get():
                    logging.info(f"Auto-assembly triggered for run {run_idx+1}.")
                    run_output_path = Path(app.OUTPUTS_DIR) / app.session_name.get() / f"{app.session_name.get()}_run{run_idx+1}_seed{current_run_master_seed}.wav"
                    app.audio_manager.assemble_audiobook(auto_path=str(run_output_path))
                elif app.stop_flag.is_set():
                    logging.info(f"Run {run_idx+1} was stopped by user.")
                    break
            finally:
                if run_temp_dir.exists():
                    try:
                        shutil.rmtree(run_temp_dir)
                        logging.info(f"Cleaned up temporary directory: {run_temp_dir}")
                    except Exception as e:
                        logging.error(f"Failed to clean up temp directory {run_temp_dir}: {e}")

        app.after(0, app.reinit_audio_player)
        app.after(0, lambda: app.start_stop_button.configure(text="Start Generation", state="normal", fg_color=app.button_color, hover_color=app.button_hover_color))
        app.save_session()
        app.after(0, lambda: messagebox.showinfo("Complete", "All generation runs are complete!"))
