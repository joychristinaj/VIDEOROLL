"""
Audio transcription adapters.

Providers:
  - WhisperAdapter : OpenAI Whisper (local, requires pip install openai-whisper)
  - MockTranscriber: Returns the raw filename as placeholder – testing only

The adapter returns a transcription string.
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol


class TranscriptionAdapter(Protocol):
    name: str

    def transcribe(self, audio_path: Path, language: str = "en") -> str: ...


class WhisperAdapter:
    """
    Local Whisper transcription.
    Requires: pip install openai-whisper
    Note: Whisper models are large (39 MB – 1.5 GB). The tiny model is used by
    default to keep footprint manageable.
    """
    name = "whisper"

    def __init__(self, model_name: str = "tiny") -> None:
        self._model_name = model_name
        self._model = None  # lazy-load

    def _load(self):
        if self._model is None:
            try:
                import whisper
                self._model = whisper.load_model(self._model_name)
            except ImportError:
                raise RuntimeError(
                    "openai-whisper is not installed. Run: pip install openai-whisper\n"
                    "Alternatively, set TRANSCRIPTION_PROVIDER=mock."
                )
        return self._model

    def transcribe(self, audio_path: Path, language: str = "en") -> str:
        model = self._load()
        result = model.transcribe(str(audio_path), language=language)
        return result.get("text", "").strip()


class MockTranscriber:
    """
    Mock transcriber for offline testing.
    Returns a placeholder string that clearly indicates mock usage.
    """
    name = "mock"

    def transcribe(self, audio_path: Path, language: str = "en") -> str:
        return (
            f"[MOCK TRANSCRIPTION of {audio_path.name}] "
            "This is a placeholder. Configure TRANSCRIPTION_PROVIDER=whisper "
            "and install openai-whisper for real transcription."
        )


def get_transcription_adapter(provider: str) -> TranscriptionAdapter:
    if provider == "whisper":
        return WhisperAdapter()
    elif provider == "mock":
        return MockTranscriber()
    else:
        raise ValueError(f"Unknown transcription provider: '{provider}'")
