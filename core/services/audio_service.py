from PySide6.QtCore import QObject, QUrl, Signal, Slot
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from pathlib import Path
import logging

class AudioService(QObject):
    """
    Handles audio playback for the application.
    Replaces legacy pygame.mixer logic with native QMediaPlayer.
    """
    playback_started = Signal(str) # file_path
    playback_stopped = Signal()
    playback_error = Signal(str)
    
    # Assembly Signals
    assembly_progress = Signal(str)
    assembly_finished = Signal(str) # success message
    assembly_error = Signal(str)
    
    def __init__(self):
        super().__init__()
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        
        # Connect signals
        self.player.playbackStateChanged.connect(self._on_state_changed)
        self.player.errorOccurred.connect(self._on_error)
        
        self.current_file = None

    def play_file(self, file_path: str):
        """Plays the specified audio file."""
        if not file_path: return
        
        path = Path(file_path)
        if not path.exists():
            self.playback_error.emit(f"File not found: {path}")
            return
            
        try:
            self.player.stop()
            self.player.setSource(QUrl.fromLocalFile(str(path)))
            self.audio_output.setVolume(1.0) # Full volume
            self.player.play()
            self.current_file = str(path)
            self.playback_started.emit(self.current_file)
            logging.info(f"AudioService: Playing {path}")
        except Exception as e:
            msg = f"Failed to play audio: {e}"
            logging.error(msg)
            self.playback_error.emit(msg)

    def stop(self):
        """Stops playback."""
        if self.player.playbackState() != QMediaPlayer.StoppedState:
            self.player.stop()
            self.playback_stopped.emit()

    @Slot(QMediaPlayer.PlaybackState)
    def _on_state_changed(self, state):
        if state == QMediaPlayer.StoppedState:
            self.playback_stopped.emit()

    @Slot(QMediaPlayer.Error, str)
    def _on_error(self, error, error_string):
        self.playback_error.emit(f"QMediaPlayer Error: {error_string}")

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

