"""
Constants for ChatterboxPro


"""

# ============================================================================
# AUDIO PROCESSING CONSTANTS
# ============================================================================

# EBU R128 Normalization Defaults
DEFAULT_LUFS_TARGET = -23.0  # LUFS (Loudness Units relative to Full Scale)
EBU_R128_TRUE_PEAK_MAX = -1.5  # dBTP (True Peak maximum to prevent clipping)
EBU_R128_LOUDNESS_RANGE = 11  # LU (Loudness Range for dynamic consistency)

# Audio Export Settings
DEFAULT_SAMPLE_RATE = 44100  # Hz (CD quality)
DEFAULT_BITRATE = '192k'  # For MP3 export
DEFAULT_CHANNELS = 1  # Mono (TTS is typically mono)

# ============================================================================
# TEXT PROCESSING CONSTANTS
# ============================================================================

# Chunking Parameters
MAX_CHUNK_CHARS = 400  # Optimal for Chatterbox prosody (Phase 2: increased from 250)
MIN_CHUNK_CHARS = 200  # Minimum for maintaining context
LONG_SENTENCE_THRESHOLD = 400  # Sentences longer than this are split at punctuation

# Sentence Splitting
SENTENCE_DELIMITERS = ['.', '!', '?', '...']
CLAUSE_DELIMITERS = [',', ';', ':', '—', '–']

# ============================================================================
# GENERATION CONSTANTS
# ============================================================================

# Worker Pool
DEFAULT_MAX_WORKERS = 4  # Default number of parallel TTS workers
MIN_WORKERS = 1
MAX_WORKERS = 16

# Retry Logic
MAX_RETRY_ATTEMPTS = 3  # Maximum retries per chunk before marking as failed
AUTO_FIX_MAX_LOOPS = 5  # Maximum auto-regeneration loops to prevent infinite loops

# ============================================================================
# FILE SYSTEM CONSTANTS
# ============================================================================

# Output Directories
DEFAULT_OUTPUTS_DIR = "Outputs_Pro"
DEFAULT_SESSIONS_DIR = "sessions"
DEFAULT_TEMPLATES_DIR = "voice_templates"

# File Extensions
SUPPORTED_TEXT_FORMATS = ['.txt', '.pdf', '.epub', '.docx', '.mobi']
SUPPORTED_AUDIO_FORMATS = ['.wav', '.mp3', '.flac', '.ogg']

# ============================================================================
# UI CONSTANTS
# ============================================================================

# Theme Defaults
DEFAULT_THEME = "dark_teal.xml"
DEFAULT_THEME_INVERT = False

# Display Limits
MAX_PREVIEW_TEXT_LENGTH = 80  # Characters to show in playlist preview
MAX_LOG_LINES = 1000  # Maximum lines to keep in log view

# ============================================================================
# VALIDATION CONSTANTS
# ============================================================================

# Audio Settings Validation
MIN_LUFS = -70.0  # Minimum valid LUFS value
MAX_LUFS = 0.0  # Maximum valid LUFS value (0 dB is digital maximum)

MIN_SILENCE_THRESHOLD = 0.0  # Minimum silence detection threshold
MAX_SILENCE_THRESHOLD = 1.0  # Maximum silence detection threshold

MIN_FRAME_MARGIN = 0  # Minimum frame margin for silence removal
MAX_FRAME_MARGIN = 100  # Maximum frame margin (in frames)

MIN_SILENT_SPEED = 1.0  # Minimum speed multiplier for silent sections
MAX_SILENT_SPEED = 99999.0  # Maximum speed (effectively removes silence)

# Temperature/Exaggeration Ranges
MIN_TEMPERATURE = 0.0
MAX_TEMPERATURE = 2.0
DEFAULT_TEMPERATURE = 0.75

MIN_EXAGGERATION = 0.0
MAX_EXAGGERATION = 2.0
DEFAULT_EXAGGERATION = 0.70
