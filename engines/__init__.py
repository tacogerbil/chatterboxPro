# engines/__init__.py
"""
TTS Engine Registry and Factory.
"""
from .base_engine import BaseTTSEngine
from .chatterbox_engine import ChatterboxEngine
from .moss_engine import MossEngine

# Engine registry
# MCCC: Only Chatterbox and MOSS are supported as per user request.
AVAILABLE_ENGINES = {
    'chatterbox': ChatterboxEngine,
    'moss': MossEngine,
}

def get_engine(engine_name: str, device: str, **kwargs) -> BaseTTSEngine:
    """
    Factory function to create TTS engine instances.
    
    Args:
        engine_name: Name of the engine ('chatterbox', 'moss', etc.)
        device: Device string ('cuda:0', 'cpu', etc.)
        **kwargs: specific engine args (e.g. model_path)
    
    Returns:
        Initialized TTS engine instance
    
    Raises:
        ValueError: If engine_name is not recognized
    """
    engine_name = engine_name.lower()
    
    if engine_name not in AVAILABLE_ENGINES:
        available = ', '.join(AVAILABLE_ENGINES.keys())
        raise ValueError(f"Unknown engine '{engine_name}'. Available engines: {available}")
    
    engine_class = AVAILABLE_ENGINES[engine_name]
    return engine_class(device, **kwargs)

def list_engines():
    """Return list of available engine names."""
    return list(AVAILABLE_ENGINES.keys())

__all__ = ['BaseTTSEngine', 'ChatterboxEngine', 'MossEngine', 'get_engine', 'list_engines']
