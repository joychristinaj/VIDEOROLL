"""
TTS (Text-to-Speech) adapters.

Providers:
  - GTTSAdapter   : Google Text-to-Speech (gTTS) – free, requires internet
  - ESpeakAdapter : eSpeak / espeak-ng – local, offline, requires binary
  - EdgeTTSAdapter: Microsoft Edge TTS – free, requires internet + edge-tts package
  - MockTTSAdapter: Generates a silent WAV for testing ONLY

The adapter returns a Path to a WAV or MP3 file.
"""
from __future__ import annotations

import io
import math
import struct
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Optional, Protocol


class TTSAdapter(Protocol):
    name: str

    def synthesize(self, text: str, output_path: Path, language: str = "en", voice: str = "default") -> Path:
        """Synthesize speech and write to output_path. Returns output_path."""
        ...


# ── gTTS ──────────────────────────────────────────────────────────────────────

class GTTSAdapter:
    """
    Uses the gTTS library (Google TTS over HTTP).
    Falls back to pyttsx3 offline synthesizer if network unavailable.
    """
    name = "gtts"

    def synthesize(self, text: str, output_path: Path, language: str = "en", voice: str = "default") -> Path:
        try:
            from gtts import gTTS
            tts = gTTS(text=text, lang=language, slow=False)
            mp3_path = output_path.with_suffix(".mp3")
            tts.save(str(mp3_path))
            return mp3_path
        except Exception:
            # Fall back to local pyttsx3
            return Pyttsx3Adapter().synthesize(text, output_path, language, voice)


class Pyttsx3Adapter:
    """
    Native offline speech synthesis via pyttsx3 (Windows SAPI5 / macOS / Linux).
    100% offline, requires no network.
    """
    name = "pyttsx3"

    def synthesize(self, text: str, output_path: Path, language: str = "en", voice: str = "default") -> Path:
        import pyttsx3
        wav_path = output_path.with_suffix(".wav")
        engine = pyttsx3.init()
        engine.setProperty("rate", 160)
        engine.save_to_file(text, str(wav_path))
        engine.runAndWait()
        return wav_path


# ── eSpeak ────────────────────────────────────────────────────────────────────

class ESpeakAdapter:
    """
    Uses the eSpeak or eSpeak-NG binary (offline, local).
    Requires: espeak or espeak-ng installed on the system.
    """
    name = "espeak"

    def __init__(self, binary: str = "espeak") -> None:
        self._bin = binary

    def synthesize(self, text: str, output_path: Path, language: str = "en", voice: str = "default") -> Path:
        wav_path = output_path.with_suffix(".wav")
        cmd = [
            self._bin,
            "-v", language,
            "-s", "150",          # speed (words/min)
            "-w", str(wav_path),
            text,
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=60)
        if result.returncode != 0:
            raise RuntimeError(
                f"eSpeak failed (exit {result.returncode}): {result.stderr.decode()[:300]}\n"
                "Make sure espeak or espeak-ng is installed."
            )
        return wav_path


# ── Edge TTS ──────────────────────────────────────────────────────────────────

class EdgeTTSAdapter:
    """
    Uses the edge-tts Python library (Microsoft Edge TTS, free, internet required).
    Requires: pip install edge-tts
    """
    name = "edge"

    def __init__(self, voice: str = "en-US-AriaNeural") -> None:
        self._default_voice = voice

    def synthesize(self, text: str, output_path: Path, language: str = "en", voice: str = "default") -> Path:
        try:
            import asyncio
            import edge_tts
        except ImportError:
            raise RuntimeError(
                "edge-tts is not installed. Run: pip install edge-tts\n"
                "Alternatively, set TTS_PROVIDER=gtts or TTS_PROVIDER=mock."
            )
        selected_voice = voice if voice != "default" else self._default_voice
        mp3_path = output_path.with_suffix(".mp3")

        async def _run():
            communicate = edge_tts.Communicate(text, selected_voice)
            await communicate.save(str(mp3_path))

        asyncio.run(_run())
        return mp3_path


# ── Mock TTS ──────────────────────────────────────────────────────────────────

class MockTTSAdapter:
    """
    Generates a silent WAV file proportional to text length.
    For OFFLINE TESTING ONLY – never used in real production jobs.
    """
    name = "mock"
    SAMPLE_RATE = 22050
    WPM = 140

    def synthesize(self, text: str, output_path: Path, language: str = "en", voice: str = "default") -> Path:
        word_count = len(text.split())
        duration_s = max(1.0, (word_count / self.WPM) * 60)
        num_samples = int(self.SAMPLE_RATE * duration_s)

        wav_path = output_path.with_suffix(".wav")
        with wave.open(str(wav_path), "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(self.SAMPLE_RATE)
            # Generate a very quiet 440 Hz tone so FFmpeg doesn't fail on silence
            data = []
            for i in range(num_samples):
                sample = int(500 * math.sin(2 * math.pi * 440 * i / self.SAMPLE_RATE))
                data.append(struct.pack("<h", sample))
            wf.writeframes(b"".join(data))

        return wav_path


# ── Factory ───────────────────────────────────────────────────────────────────

def get_tts_adapter(provider: str, edge_voice: str = "en-US-AriaNeural") -> TTSAdapter:
    if provider in ("gtts", "auto", "default"):
        return GTTSAdapter()
    elif provider == "pyttsx3":
        return Pyttsx3Adapter()
    elif provider == "espeak":
        return ESpeakAdapter()
    elif provider == "edge":
        return EdgeTTSAdapter(voice=edge_voice)
    elif provider == "mock":
        return MockTTSAdapter()
    else:
        raise ValueError(f"Unknown TTS provider: '{provider}'")


def list_available_voices(provider: str) -> list[dict]:
    """Return available voices for the given TTS provider."""
    if provider == "gtts":
        return [
            {"id": "en", "name": "English (gTTS)", "language": "en"},
            {"id": "es", "name": "Spanish (gTTS)", "language": "es"},
            {"id": "fr", "name": "French (gTTS)", "language": "fr"},
            {"id": "de", "name": "German (gTTS)", "language": "de"},
            {"id": "hi", "name": "Hindi (gTTS)", "language": "hi"},
        ]
    elif provider == "edge":
        return [
            {"id": "en-US-AriaNeural",   "name": "Aria (US English, Neural)", "language": "en-US"},
            {"id": "en-US-GuyNeural",    "name": "Guy (US English, Neural)",  "language": "en-US"},
            {"id": "en-GB-SoniaNeural",  "name": "Sonia (UK English, Neural)", "language": "en-GB"},
            {"id": "en-AU-NatashaNeural","name": "Natasha (AU English, Neural)", "language": "en-AU"},
        ]
    elif provider == "espeak":
        return [{"id": "en", "name": "English (eSpeak)", "language": "en"}]
    elif provider == "mock":
        return [{"id": "mock", "name": "Mock Voice (Test Only)", "language": "en"}]
    return []
