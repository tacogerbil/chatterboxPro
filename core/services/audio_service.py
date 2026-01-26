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
