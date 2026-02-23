"""
recover_session_wavs.py

Scans the Sentence_wavs folder on disk and re-links any found .wav files
back into the session JSON by matching filenames to chunk UUIDs.

Sets tts_generated='yes' and audio_path for each matched chunk.

Usage:
    python recover_session_wavs.py <session_dir>

Example:
    python recover_session_wavs.py "I:/ChatterboxPro/chatterboxPro/Outputs_Pro/Obake Files"
"""

import sys
import json
import shutil
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def recover_session(session_dir: str) -> None:
    session_path = Path(session_dir).resolve()

    if not session_path.exists():
        logging.error(f"Session directory not found: {session_path}")
        sys.exit(1)

    # Locate the session JSON
    json_candidates = list(session_path.glob("*_session.json"))
    if not json_candidates:
        logging.error(f"No *_session.json found in: {session_path}")
        sys.exit(1)

    json_path = json_candidates[0]
    logging.info(f"Loading session: {json_path.name}")

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    sentences = data.get("sentences", [])
    if not sentences:
        logging.error("Session JSON has no sentences. Nothing to recover.")
        sys.exit(1)

    # Scan all Sentence_wavs folders (including multi-run variants)
    wav_by_uuid: dict[str, Path] = {}
    wav_dirs = list(session_path.glob("Sentence_wavs*"))

    if not wav_dirs:
        logging.error(f"No Sentence_wavs folder found in: {session_path}")
        sys.exit(1)

    for wav_dir in wav_dirs:
        for wav_file in wav_dir.glob("audio_*.wav"):
            # Filename pattern: audio_<uuid>.wav
            chunk_uuid = wav_file.stem.removeprefix("audio_")
            wav_by_uuid[chunk_uuid] = wav_file

    logging.info(f"Found {len(wav_by_uuid)} WAV files on disk across {len(wav_dirs)} folder(s).")

    # Back up the session JSON before modifying
    backup_path = json_path.with_suffix(".bak")
    shutil.copy2(json_path, backup_path)
    logging.info(f"Backup saved to: {backup_path.name}")

    matched = 0
    already_set = 0
    unmatched = 0

    for sentence in sentences:
        if sentence.get("is_pause") or sentence.get("is_chapter_heading"):
            continue

        chunk_uuid = sentence.get("uuid", "")
        if not chunk_uuid:
            continue

        if sentence.get("tts_generated") == "yes" and sentence.get("audio_path"):
            # Verify the path still exists on disk; if not, re-link it
            existing = Path(sentence["audio_path"])
            if existing.exists():
                already_set += 1
                continue

        wav_path = wav_by_uuid.get(chunk_uuid)
        if wav_path:
            sentence["tts_generated"] = "yes"
            sentence["audio_path"] = str(wav_path)
            sentence["marked"] = False
            matched += 1
        else:
            unmatched += 1

    # Write the updated JSON
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logging.info("─" * 50)
    logging.info(f"Recovery complete.")
    logging.info(f"  Matched and re-linked : {matched}")
    logging.info(f"  Already linked (valid) : {already_set}")
    logging.info(f"  No WAV found on disk   : {unmatched}")
    logging.info(f"Updated session saved to: {json_path.name}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    recover_session(sys.argv[1])
