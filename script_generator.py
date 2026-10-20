"""
Heuristic script generation from extracted PDF text.

This module uses deterministic text-processing methods (sentence segmentation,
TF-IDF-style keyword weighting, heading detection) to organize PDF content into
a narration script. It does NOT use any AI/LLM.

The provider name is explicitly reported as "heuristic" so callers and users
know exactly what is generating the script.
"""
from __future__ import annotations

import math
import re
from typing import List, Optional, Tuple

from app.models.schemas import (
    ScriptResponse,
    ScriptScene,
    VideoDuration,
    VisualStyle,
)

# Words-per-minute for narration speed estimation
WPM = {
    VideoDuration.short:  130,
    VideoDuration.medium: 140,
    VideoDuration.long:   150,
}

# Approximate target word counts per duration
TARGET_WORDS = {
    VideoDuration.short:  130,   # ~60 s at 130 wpm
    VideoDuration.medium: 280,   # ~120 s
    VideoDuration.long:   450,   # ~180 s
}

STOP_WORDS = frozenset(
    "a an the is are was were be been being have has had do does did "
    "will would shall should may might must can could of in on at to "
    "for from by with as this that these those and or but not it its "
    "he she we they you i me us our their his her".split()
)


def _clean_text(text: str) -> str:
    """Remove control characters and excessive whitespace."""
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", text)
    text = re.sub(r" {2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _split_sentences(text: str) -> List[str]:
    """Naive sentence splitter – avoids NLTK dependency."""
    # Split on sentence-ending punctuation followed by whitespace + capital letter
    sents = re.split(r"(?<=[.!?])\s+(?=[A-Z\"\'])", text)
    result = []
    for s in sents:
        s = s.strip()
        if s:
            result.append(s)
    return result


def _term_frequencies(text: str) -> dict[str, float]:
    """Compute raw term frequencies, excluding stop words."""
    words = re.findall(r"\b[a-z]{3,}\b", text.lower())
    tf: dict[str, float] = {}
    for w in words:
        if w not in STOP_WORDS:
            tf[w] = tf.get(w, 0) + 1
    total = max(1, sum(tf.values()))
    return {k: v / total for k, v in tf.items()}


def _score_sentence(sent: str, corpus_tf: dict[str, float]) -> float:
    """Score a sentence by average TF score of its keywords."""
    words = re.findall(r"\b[a-z]{3,}\b", sent.lower())
    keywords = [w for w in words if w not in STOP_WORDS]
    if not keywords:
        return 0.0
    return sum(corpus_tf.get(k, 0) for k in keywords) / len(keywords)


def _is_heading(line: str) -> bool:
    line = line.strip()
    if not line:
        return False
    # ALL-CAPS line or starts with digit+dot
    if re.match(r"^[A-Z][A-Z\s\-]{3,}$", line) and len(line) < 80:
        return True
    if re.match(r"^\d+[\.\)]\s+[A-Z]", line) and len(line) < 100:
        return True
    return False


def _extract_sentences_with_pages(full_text: str) -> List[Tuple[str, Optional[int]]]:
    """
    Split [Page N] annotated text into (sentence, page_number) tuples.
    """
    page_blocks = re.split(r"\[Page (\d+)\]", full_text)
    results: List[Tuple[str, Optional[int]]] = []
    i = 0
    while i < len(page_blocks):
        block = page_blocks[i].strip()
        page_num: Optional[int] = None
        if block.isdigit() and i + 1 < len(page_blocks):
            page_num = int(block)
            block = page_blocks[i + 1].strip()
            i += 2
        else:
            i += 1
        if not block:
            continue
        for sent in _split_sentences(block):
            sent = sent.strip()
            if len(sent) > 20:
                results.append((sent, page_num))
    return results


def generate_script(
    full_text: str,
    duration: VideoDuration = VideoDuration.medium,
    language: str = "en",
    style: VisualStyle = VisualStyle.documentary,
) -> ScriptResponse:
    """
    Generate a narration script from extracted PDF text using heuristic methods.

    Strategy:
    1. Split text into (sentence, page) pairs preserving page annotations.
    2. Score every sentence using TF-IDF term frequency.
    3. Boost sentences that contain headings or start a new page.
    4. Select top-scoring sentences up to the target word count.
    5. Re-order selected sentences to preserve original document order.
    6. Group consecutive sentences into scenes (max 50 words / scene).
    7. Generate a visual search query per scene from its top keywords.
    """
    full_text = _clean_text(full_text)
    if not full_text.strip():
        raise ValueError("Cannot generate script: no text content provided.")

    target_words = TARGET_WORDS[duration]
    corpus_tf = _term_frequencies(full_text)
    sent_page_pairs = _extract_sentences_with_pages(full_text)

    if not sent_page_pairs:
        raise ValueError("Could not extract any sentences from the provided text.")

    # Score each sentence
    scored: List[Tuple[float, int, str, Optional[int]]] = []  # (score, orig_idx, sent, page)
    for idx, (sent, page) in enumerate(sent_page_pairs):
        score = _score_sentence(sent, corpus_tf)
        # Boost first sentence of each page
        if idx == 0 or (idx > 0 and sent_page_pairs[idx - 1][1] != page):
            score *= 1.3
        scored.append((score, idx, sent, page))

    # Sort by score descending, pick until target word count
    scored_sorted = sorted(scored, key=lambda x: -x[0])
    selected: List[Tuple[int, str, Optional[int]]] = []  # (orig_idx, sent, page)
    word_count = 0
    for _score, orig_idx, sent, page in scored_sorted:
        wc = len(sent.split())
        if word_count + wc > target_words * 1.2:
            break
        selected.append((orig_idx, sent, page))
        word_count += wc
        if word_count >= target_words:
            break

    # Restore document order
    selected.sort(key=lambda x: x[0])

    # Group into scenes (max ~50 words each)
    scenes: List[ScriptScene] = []
    scene_sentences: List[str] = []
    scene_page: Optional[int] = None
    scene_words = 0
    scene_idx = 0

    def _flush_scene():
        nonlocal scene_idx, scene_sentences, scene_page, scene_words
        if not scene_sentences:
            return
        text = " ".join(scene_sentences)
        query = _make_visual_query(text, style)
        scenes.append(ScriptScene(
            index=scene_idx,
            text=text,
            source_page=scene_page,
            visual_query=query,
        ))
        scene_idx += 1
        scene_sentences = []
        scene_page = None
        scene_words = 0

    for orig_idx, sent, page in selected:
        wc = len(sent.split())
        if scene_words + wc > 50 and scene_sentences:
            _flush_scene()
        scene_sentences.append(sent)
        scene_page = scene_page or page
        scene_words += wc

    _flush_scene()

    if not scenes:
        raise ValueError(
            "Script generation produced no scenes. "
            "The PDF may not contain enough readable text."
        )

    # Compute duration hints based on WPM
    wpm = WPM[duration]
    total_duration = 0.0
    for scene in scenes:
        wc = len(scene.text.split())
        dur = (wc / wpm) * 60
        scene.duration_hint = round(dur, 2)
        total_duration += dur

    script_text = "\n\n".join(s.text for s in scenes)
    actual_word_count = len(script_text.split())

    return ScriptResponse(
        script_text=script_text,
        scenes=scenes,
        word_count=actual_word_count,
        estimated_duration_s=round(total_duration, 1),
        provider="heuristic",
    )


def _make_visual_query(text: str, style: VisualStyle) -> str:
    """
    Build a visual search query from text keywords.
    Appends a style modifier to refine footage search results.
    """
    words = re.findall(r"\b[a-z]{4,}\b", text.lower())
    keywords = [w for w in words if w not in STOP_WORDS]

    # Count and pick top 3-4 terms
    freq: dict[str, int] = {}
    for w in keywords:
        freq[w] = freq.get(w, 0) + 1
    top = sorted(freq, key=lambda w: -freq[w])[:4]

    style_hints = {
        VisualStyle.cinematic:   "cinematic",
        VisualStyle.documentary: "documentary footage",
        VisualStyle.corporate:   "professional business",
        VisualStyle.energetic:   "dynamic action",
    }
    modifier = style_hints.get(style, "")
    query_parts = top + ([modifier] if modifier else [])
    return " ".join(query_parts) if query_parts else "nature landscape"


def scenes_from_script(script_text: str, style: VisualStyle = VisualStyle.documentary) -> List[ScriptScene]:
    """
    Re-segment an edited script text into scenes without re-scoring.
    Used when the user has edited the script and we need fresh scenes.
    """
    paragraphs = [p.strip() for p in script_text.split("\n\n") if p.strip()]
    scenes: List[ScriptScene] = []
    for i, para in enumerate(paragraphs):
        query = _make_visual_query(para, style)
        scenes.append(ScriptScene(
            index=i,
            text=para,
            visual_query=query,
        ))
    return scenes
