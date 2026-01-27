import hashlib
from pathlib import Path
from typing import Union

def get_audio_hash(wav_fpath_or_bytes: Union[str, Path, bytes]) -> str:
    """
    Calculate MD5 hash of an audio file path or bytes.
    reads file in chunks to avoid memory issues with large files.
    """
    hasher = hashlib.md5()
    if isinstance(wav_fpath_or_bytes, (str, Path)):
        with open(wav_fpath_or_bytes, "rb") as f:
            buf = f.read(65536)
            while len(buf) > 0:
                hasher.update(buf)
                buf = f.read(65536)
    elif isinstance(wav_fpath_or_bytes, bytes):
        hasher.update(wav_fpath_or_bytes)
    else:
        raise TypeError("Input must be a file path or bytes object for hashing.")
    return hasher.hexdigest()
