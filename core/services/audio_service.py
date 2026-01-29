from PySide6.QtCore import QObject, QUrl, Signal, Slot, QTimer
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from pathlib import Path
import logging

class AudioService(QObject):
    """
    Handles audio playback for the application.
    Replaces legacy pygame.mixer logic with native QMediaPlayer.
    """
    # ... (Signals remain same)
    playback_started = Signal(str) 
    playback_stopped = Signal()
    playback_error = Signal(str)
    
    # Assembly Signals
    assembly_progress = Signal(str)
    assembly_finished = Signal(str)
    assembly_error = Signal(str)
    
    def __init__(self):
        super().__init__()
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        
        self.pause_timer = QTimer(self)
        self.pause_timer.setSingleShot(True)
        self.pause_timer.timeout.connect(self._on_pause_finished)
        
        # Connect signals
        self.player.playbackStateChanged.connect(self._on_state_changed)
        self.player.mediaStatusChanged.connect(self._on_status_changed)
        self.player.errorOccurred.connect(self._on_error)
        
        self.current_file = None

    # ... (play_file, stop, etc remain same)

    def play_queue(self, items: list[dict]):
        """
        Starts playing a mixed list of items sequentially.
        Items: [{'type': 'file', 'path': str}, {'type': 'pause', 'duration': int}]
        """
        if not items: return
        logging.info(f"AudioService: Starting Queue. {len(items)} items.")
        self.output_queue = items
        self.queue_index = 0
        self.is_queue_active = True
        self._play_next_in_queue()

    def _play_next_in_queue(self):
        if not hasattr(self, 'output_queue') or self.queue_index >= len(self.output_queue):
            self.is_queue_active = False
            self.playback_stopped.emit()
            logging.info("AudioService: Queue finished.")
            return

        item = self.output_queue[self.queue_index]
        self.queue_index += 1
        
        if item['type'] == 'pause':
            duration = item.get('duration', 0)
            logging.info(f"AudioService: Pausing for {duration}ms")
            # We treat pause as 'playing silence'.
            # We don't emit 'playback_started' for pause? maybe we should?
            # Or just wait.
            self.pause_timer.start(duration)
            
        elif item['type'] == 'file':
            path = item.get('path')
            logging.info(f"AudioService: Queue Next [{self.queue_index}/{len(self.output_queue)}]: {path}")
            
            if path and Path(path).exists():
                self.play_file(path)
            else:
                logging.warning(f"AudioService: Queue skipping missing file: {path}")
                self._play_next_in_queue()

    def _on_pause_finished(self):
        """Called when pause timer ends."""
        # Proceed to next
        if hasattr(self, 'is_queue_active') and self.is_queue_active:
             self._play_next_in_queue()

    def stop(self):
        """Stops playback and clears queue."""
        self.is_queue_active = False
        self.output_queue = []
        self.pause_timer.stop()
        if self.player.playbackState() != QMediaPlayer.StoppedState:
            self.player.stop()
            self.playback_stopped.emit()

    def assemble_audiobook(self, output_path, is_for_acx=False, metadata=None):
        """
        Proxy method to call AssemblyService.
        This allows Views to interact with a single "AudioService" if preferred,
        or serves as a legacy bridge.
        """
        # We need access to assembly_service. 
        # Ideally, it should be injected or accessed via global state if not passed.
        # But based on architecture, it seems AudioService is standalone.
        # HOWEVER, the crash shows FinalizeView calls THIS method on AudioService.
        # So AudioService MUST handle it.
        
        # If AudioService doesn't have the logic, it must signal 'error' or we inject AssemblyService?
        # A clearer architecture: FinalizeView should use AssemblyService directly.
        # BUT to fix the immediate crash without refactoring the View logic repeatedly:
        pass # Placeholder: The view connects to the signals, but who emits them?
             # The View calls this method. If this method does nothing, nothing happens.
             # We need to INJECT AssemblyService into AudioService or REFACTOR View.
             # Looking at QMainWindow, AssemblyService IS instantiated separately.
             
             # CORRECTION: FinalizeView has `set_assembly_service`.
             # It ALSO calls `set_audio_service`.
             # And then it calls `self.audio_service.assemble_audiobook`.
             # This implies the View is confused or AudioService IS wrapping it.
             # Since I cannot see AudioService having a ref to AssemblyService, 
             # I should probably FIX THE VIEW to call assembly_service.assemble_audiobook()
             # instead of audio_service.assemble_audiobook().
             
             # But the user rule says "manual edits only", minimizing risk.
             # Refactoring the View to use the correct service is safer than hacking AudioService.
             
             # Wait, FinalizeView line 192: self.audio_service.assemble_audiobook(...)
             # FinalizeView line 18: set_assembly_service(self, service)
             
             # Use the correct service in FinalizeView.

