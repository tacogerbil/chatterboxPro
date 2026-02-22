# Chatterbox Pro Audiobook Generator

<img src="images/Main.png" width="600">

**Chatterbox Pro** is a powerful, user-friendly graphical interface for generating high-quality audiobooks using cutting-edge Neural TTS. This tool is designed for creators, authors, and hobbyists who want to convert long-form text into professional-sounding audio with a consistent, cloned voice.

This application provides a complete end-to-end workflow: from text processing and voice cloning to multi-GPU audio generation and final audiobook assembly.

<img src="images/generation.png" width="600">

## ✨ Features

-   **High-Quality Voice Cloning**: Clone any voice from a short audio sample.
-   **Multi-Engine Core**: Don't get locked in. Seamlessly switch between **Chatterbox** and **MOSS-TTS** to find the perfect sound for your project.
    -   **Custom Models**: Load `.pth` files from anywhere on your system (e.g., massive external drives) without copying them into system folders.
-   **Intuitive GUI (PySide6)**:
    -   **Zero Lag**: The Qt-based engine handles massive playlists (10,000+ items) without stuttering.
    -   **Modern & Responsive**: Full High-DPI scaling, smooth resizing, and native OS integration.
    -   **Theming**: Beautiful built-in Dark/Light themes that are easy on the eyes during long editing sessions.
-   **Comprehensive Text Processing**:
    -   Supports various input formats: `.txt`, `.pdf`, `.epub`, and with Pandoc installed, `.docx` and `.mobi`.
    -   Intelligent sentence and chapter detection.
    -   In-app text editor / smart splitter for reviewing and correcting source material.
    <img src="images/chapters.png" width="600">
-   **🛡️ Session Safety & Recovery**:
    -   **Triple-Layer Protection**: Prevents accidental data loss with safety gates that block saving empty sessions.
    -   **Auto-Backup**: Automatically creates `.bak` snapshots of your session data before every save.
    -   **Workspace Anchoring**: Bulletproof session and voice template loading that survives OS-level folder shifts. 
-   **Powerful Generation Controls**:
    -   **Real-Time Voice Lab**: No more saving "templates" blindly. Type sample text, tweak parameters (Speed, Pitch, Style), and **hear the results instantly**. Iteration is now immediate.
    -   **Clean Slate Playback**: Your successful audio generations are intelligently protected during re-rolls; Playback buttons continue to work seamlessly even if you regenerate other chunks in the middle of your book.
    -   **Studio Effects (Post-Processing)**: Powered by **Pedalboard**. Apply a non-destructive **FX Chain** (EQ, Compression, High-Pass) to your generated audio *after* synthesis for a broadcast-ready sound.
-   **Advanced Playlist Management (The Forge)**:
    -   **Search & Replace Superpowers**: Natively track down words or phrases across your entire manuscript. Use the built-in Replace engine to instantly correct misspellings and automatically queue those specific chunks for regeneration.
    -   **Chapter & Pause Mastery**: Select any line to insert granular **Digital Silence Pauses** (tuned down to the exact millisecond) or mark Chapter Headings. The Generation engine intelligently skips these pauses to save GPU time, while the Assembly engine mathematically stitches them back together for perfect audiobook pacing.
    -   **Status-Based Workflow**: Target lines based on ASR status (e.g., **"Merge All Failed"** or **"Split Failed"**) to fix difficult passages in bulk.
    -   **Mark & Merge**: Visually tag chunks with the **Gold Marker (🟨)** system. Toggle marks on/off and "Smart Merge" them into single coherent lines.
-   **ASR-Powered Validation**:
    -   **Strict Mode**: Uses word-count validation to reject hallucinations (extra words) instantly.
    -   **Double-Protection Signal Check**: The system pre-screens audio for **Signal Energy (RMS)** and **Trailing Noise**. Only files with valid speech energy are sent for transcription, preventing "Ghost Hallucinations" on empty audio.
    -   **Recursive Auto-Fix Loop**: "Set it and forget it." The system will automatically retry failed chunks, splitting them if necessary, and re-rolling seeds indefinitely until your entire book passes QA.
-   **Mastering Suite (Post-Processing)**:
    -   **Audio Normalization**: Ensure consistent volume levels (-23 LUFS) across all chapters.
    -   **Smart Silence Removal**: Use `auto-editor` to tighten up gaps and flow.
    -   **One-Click Assembly**: Compile thousands of individual audio chunks and precise digital pauses into a single, polished audiobook file ready for distribution.

<img src="images/finalize.png" width="600">
<img src="images/config.png" width="600">

## 🔧 Installation

This project requires Python 3.10 or higher. An NVIDIA GPU with CUDA support is highly recommended for optimal performance.

### 1. System Dependencies

For full functionality, you need to install these command-line tools and ensure they are in your system's PATH.

-   **FFmpeg**: Required for audio normalization and assembling the final audiobook.
    -   Download from [ffmpeg.org](https://ffmpeg.org/download.html).
-   **auto-editor**: Required for smart silence removal.
    -   Install via pip: `pip install auto-editor`
-   **Pandoc (Optional)**: Required for processing `.docx` and `.mobi` files.
    -   Download from [pandoc.org](https://pandoc.org/installing.html).

### 2. Clone the Repository

```bash
git clone https://github.com/your-username/chatterboxPro_updated.git
cd chatterboxPro_updated
```

### 3. Create a Virtual Environment and Install Dependencies

```bash
# Create a virtual environment
python -m venv venv

# Activate it (Windows)
venv\Scripts\activate

# Install the required Python packages
pip install -r requirements.txt
```

## 🚀 How to Use

1.  **Launch the Application**:
    ```bash
    python chatter_pro.py
    ```

2.  **Tab 1: Setup**
      - **Create a Session**: Click "New Session". All files are saved in `Outputs_Pro/<session_name>`.
      - **Load Text**: Select your source file. Use the **Internal Editor** to verify sentence splitting.

3.  **Tab 2: Generation**
      - **Reference Audio**: Select a 10-30s WAV file of the voice you want to clone.
      - **Custom Models**: Point the engine to your own `.pth` / `.json` model files.

4.  **Tab 3: Playlist (The Forge)**
      - **Control the Flow**: Use **M Mark** (Toggle) and **Merge Marked** to refine your text chunks.
      - **Search & Replace**: Instantly find character names and batch-replace them to fix mispronunciations.
      - **Structure**: Insert **Chapter Headings** and **Pauses** to build your audiobook's skeleton.
      - **Generate**: Start the process. Failed chunks turn Red (❌), Success turned Green (✅).
      - **Review**: Allow the **Auto-Loop** to fix red chunks automatically, or manually Playback successes.

5.  **Tab 4: Finalize**
      - **Assemble**: Compile everything into a single audiobook file or export by Chapter. Your digital pauses are injected here.

## 📜 Licensing

Chatterbox Pro is released under a dual-license model (AGPLv3 / Commercial). See `LICENSE` for details.

## 🙏 Acknowledgements

Built on top of the powerful **Chatterbox TTS model** by Resemble AI and **MOSS-TTS**. All credit for the underlying speech synthesis technology goes to the original creators.
