"""
Caption (SRT) generator from scene timing data.
"""
from __future__ import annotations

from pathlib import Path
from typing import List

from app.models.schemas import SceneResult


def _seconds_to_srt_time(secs: float) -> str:
    """Convert float seconds to SRT timestamp format HH:MM:SS,mmm"""
    h = int(secs // 3600)
    m = int((secs % 3600) // 60)
    s = int(secs % 60)
    ms = int((secs % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def generate_srt(scenes: List[SceneResult], output_path: Path) -> Path:
    """
    Generate an SRT subtitle file from timed scene results.
    Returns output_path.
    """
    lines = []
    counter = 1
    for scene in scenes:
        if not scene.text.strip():
            continue
        # Split long text into caption chunks (max 80 chars per line)
        chunks = _chunk_text(scene.text, max_chars=80)
        if not chunks:
            continue

        # Distribute chunk timing evenly within the scene
        scene_dur = scene.end_s - scene.start_s
        chunk_dur = scene_dur / len(chunks) if chunks else scene_dur

        for ci, chunk in enumerate(chunks):
            start = scene.start_s + ci * chunk_dur
            end   = scene.start_s + (ci + 1) * chunk_dur
            lines.append(str(counter))
            lines.append(f"{_seconds_to_srt_time(start)} --> {_seconds_to_srt_time(end)}")
            lines.append(chunk)
            lines.append("")
            counter += 1

    srt_content = "\n".join(lines)
    output_path.write_text(srt_content, encoding="utf-8")
    return output_path


def _chunk_text(text: str, max_chars: int = 80) -> List[str]:
    """Split text into caption-friendly chunks."""
    words = text.split()
    chunks = []
    current = []
    current_len = 0
    for word in words:
        if current_len + len(word) + 1 > max_chars and current:
            chunks.append(" ".join(current))
            current = [word]
            current_len = len(word)
        else:
            current.append(word)
            current_len += len(word) + 1
    if current:
        chunks.append(" ".join(current))
    return chunks
