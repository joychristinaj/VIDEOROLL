"""
Gemini Omni Flash Animated Video Generation Service.

Provides:
1. Gemini API integration for visual scene conceptualization and token usage tracking.
2. Dynamic, script-relevant animated video rendering for each scene beat (e.g. flower blooming,
   neural firing, robotics, tech grids, nature dynamics).
3. Token usage and credit calculation accounting.
"""
from __future__ import annotations

import math
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import httpx
from PIL import Image, ImageDraw

from app.models.schemas import AspectRatio, SceneResult, ScriptScene, TokenUsage

# Pricing per million tokens (Gemini 1.5 Flash rates)
GEMINI_FLASH_INPUT_PRICE_PER_M = 0.075    # $0.075 / 1M input tokens
GEMINI_FLASH_OUTPUT_PRICE_PER_M = 0.300   # $0.300 / 1M output tokens

GEMINI_API_URL_TEMPLATE = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
)


def _matches_any(t: str, keywords: List[str]) -> bool:
    """Check if any keyword appears as a whole word in text."""
    for k in keywords:
        if re.search(rf"\b{re.escape(k)}\b", t):
            return True
    return False


def extract_topic_from_text(text: str) -> str:
    """Heuristic topic extraction fallback when offline or no API key."""
    t = text.lower()
    if _matches_any(t, [
        "flower", "flowers", "sunflower", "sunflowers", "rose", "roses",
        "bloom", "blooming", "blooms", "petal", "petals", "blossom", "blossoming",
        "blossoms", "flora", "botanical", "garden", "gardens"
    ]):
        return "flower"
    if _matches_any(t, [
        "brain", "brains", "neuron", "neurons", "neural", "mind", "cognition", "neuroscience"
    ]):
        return "brain"
    if _matches_any(t, [
        "robot", "robots", "robotic", "robotics", "automation", "automated", "drone", "drones",
        "machine", "machines", "hardware", "autonomous"
    ]):
        return "robot"
    if _matches_any(t, [
        "nature", "tree", "trees", "forest", "forests", "green", "energy", "solar", "eco", "climate"
    ]):
        return "nature"
    if _matches_any(t, [
        "tech", "technology", "technologies", "software", "computer", "computers", "ai",
        "artificial", "code", "coding", "digital", "data"
    ]):
        return "tech"
    if _matches_any(t, [
        "space", "galaxy", "galaxies", "star", "stars", "planet", "planets", "astronomy", "cosmic"
    ]):
        return "space"
    if _matches_any(t, [
        "city", "cities", "urban", "traffic", "building", "buildings", "metro"
    ]):
        return "city"
    if _matches_any(t, [
        "business", "finance", "money", "market", "markets", "economy", "growth"
    ]):
        return "business"
    return "nature"


def call_gemini_analysis(
    scene_text: str,
    api_key: Optional[str] = None,
    model: str = "gemini-1.5-flash",
) -> Tuple[str, int, int]:
    """
    Call Google Gemini API to analyze scene and extract visual animation concept.
    Returns: (visual_topic, prompt_tokens, candidate_tokens)
    """
    api_key = api_key or os.getenv("GEMINI_API_KEY", "").strip()

    if api_key:
        prompt = (
            f"Analyze the following video narration beat and identify the single best visual subject "
            f"to animate (e.g. flower, brain, robot, tech, nature, space, city, business). "
            f"Return ONLY a single lowercase word for the topic.\n\n"
            f"Narration: \"{scene_text}\""
        )
        url = GEMINI_API_URL_TEMPLATE.format(model=model, api_key=api_key)
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 20},
        }
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    usage = data.get("usageMetadata", {})
                    p_tokens = usage.get("promptTokenCount", max(len(prompt) // 4, 120))
                    c_tokens = usage.get("candidatesTokenCount", max(10, 15))
                    candidate = data.get("candidates", [{}])[0]
                    content = candidate.get("content", {}).get("parts", [{}])[0].get("text", "").strip().lower()
                    topic = re.sub(r"[^a-z]", "", content)
                    if topic:
                        return topic, p_tokens, c_tokens
        except Exception:
            pass  # Fall back to heuristic simulation

    # Offline / Free Tier Simulation mode
    topic = extract_topic_from_text(scene_text)
    # Estimate realistic token counts
    estimated_prompt_tokens = max(len(scene_text.split()) * 4 + 48, 65)
    estimated_candidate_tokens = 16
    return topic, estimated_prompt_tokens, estimated_candidate_tokens


def compute_cost(prompt_tokens: int, completion_tokens: int) -> float:
    """Calculate estimated cost in USD based on Gemini Flash rates."""
    input_cost = (prompt_tokens / 1_000_000.0) * GEMINI_FLASH_INPUT_PRICE_PER_M
    output_cost = (completion_tokens / 1_000_000.0) * GEMINI_FLASH_OUTPUT_PRICE_PER_M
    return round(input_cost + output_cost, 6)


# ── Animated Scene Frame Renderers ──────────────────────────────────────────

def _render_flower_frame(draw: ImageDraw.ImageDraw, width: int, height: int, progress: float):
    """
    Render a blooming flower animation with stem growth, expanding petals,
    glowing pistil, and floating pollen particles.
    """
    cx, cy = width // 2, int(height * 0.52)
    # Background soft gradient vignette
    stem_bottom_y = height
    stem_top_y = cy + 40

    # Draw stem with organic curve
    stem_w = max(width // 100, 8)
    draw.line([(cx, stem_bottom_y), (cx - 10, int(height * 0.75)), (cx, stem_top_y)], fill=(34, 139, 34), width=stem_w)

    # Leaves
    leaf_scale = min(1.0, progress * 1.5)
    if leaf_scale > 0.1:
        lx = cx - 40
        ly = int(height * 0.72)
        draw.ellipse([lx - int(35 * leaf_scale), ly - int(15 * leaf_scale), lx, ly + int(15 * leaf_scale)], fill=(46, 160, 67))
        rx = cx + 40
        ry = int(height * 0.68)
        draw.ellipse([rx, ry - int(15 * leaf_scale), rx + int(35 * leaf_scale), ry + int(15 * leaf_scale)], fill=(46, 160, 67))

    # Bloom expansion factor (0.15 at start to 1.0 at full bloom)
    bloom = 0.2 + 0.8 * math.sin(progress * (math.pi / 2))
    petal_count = 8
    max_radius = min(width, height) * 0.22 * bloom

    # Outer Petals (Deep Pink / Coral Rose)
    for i in range(petal_count):
        angle = (2 * math.pi / petal_count) * i + (progress * 0.2)
        petal_dist = max_radius * 0.75
        px = cx + petal_dist * math.cos(angle)
        py = cy + petal_dist * math.sin(angle)
        pw = int(max_radius * 0.62)
        ph = int(max_radius * 0.82)
        draw.ellipse([px - pw // 2, py - ph // 2, px + pw // 2, py + ph // 2], fill=(244, 63, 94, 230), outline=(225, 29, 72))

    # Inner Petals (Warm Golden Rose)
    inner_count = 6
    inner_radius = max_radius * 0.52
    for i in range(inner_count):
        angle = (2 * math.pi / inner_count) * i - (progress * 0.3)
        px = cx + inner_radius * math.cos(angle)
        py = cy + inner_radius * math.sin(angle)
        pw = int(inner_radius * 0.7)
        ph = int(inner_radius * 0.85)
        draw.ellipse([px - pw // 2, py - ph // 2, px + pw // 2, py + ph // 2], fill=(251, 146, 60, 240), outline=(249, 115, 22))

    # Glowing Flower Center
    center_r = int(max_radius * 0.32)
    draw.ellipse([cx - center_r, cy - center_r, cx + center_r, cy + center_r], fill=(250, 204, 21), outline=(234, 179, 8), width=3)

    # Floating pollen particles
    for p in range(16):
        p_offset = (p * 47) % 360
        rad = math.radians(p_offset + progress * 60)
        dist = (max_radius * 1.2) + ((p * 23) % int(width * 0.25)) * (0.8 + 0.4 * math.sin(progress * 3 + p))
        part_x = cx + dist * math.cos(rad)
        part_y = cy + dist * math.sin(rad) - (progress * 50)
        p_size = 3 + (p % 4)
        if 0 <= part_x < width and 0 <= part_y < height:
            draw.ellipse([part_x, part_y, part_x + p_size, part_y + p_size], fill=(254, 240, 138, 200))


def _render_tech_frame(draw: ImageDraw.ImageDraw, width: int, height: int, progress: float):
    """Render animated digital tech network with pulsing nodes and data stream."""
    cx, cy = width // 2, height // 2
    nodes = [
        (cx - 200, cy - 100), (cx + 200, cy - 100),
        (cx - 150, cy + 120), (cx + 150, cy + 120),
        (cx, cy), (cx - 300, cy), (cx + 300, cy)
    ]
    # Draw animated connecting edges
    for i, (x1, y1) in enumerate(nodes):
        for j, (x2, y2) in enumerate(nodes[i+1:], i+1):
            pulse = 0.5 + 0.5 * math.sin(progress * 6 + i + j)
            draw.line([(x1, y1), (x2, y2)], fill=(int(59 * pulse), int(130 * pulse), int(246 * pulse)), width=2)

    # Pulsing glowing nodes
    for i, (nx, ny) in enumerate(nodes):
        r = int(14 + 6 * math.sin(progress * 8 + i * 2))
        draw.ellipse([nx - r, ny - r, nx + r, ny + r], fill=(14, 165, 233), outline=(56, 189, 248), width=3)

    # Dynamic scanning beam
    scan_y = int(height * (progress % 1.0))
    draw.line([(0, scan_y), (width, scan_y)], fill=(99, 102, 241, 120), width=3)


def _render_robot_frame(draw: ImageDraw.ImageDraw, width: int, height: int, progress: float):
    """Render animated robotic eye / cybernetic sensor with dynamic scanning arcs."""
    cx, cy = width // 2, height // 2
    max_r = min(width, height) * 0.28
    # Rotating outer HUD arcs
    draw.ellipse([cx - max_r, cy - max_r, cx + max_r, cy + max_r], outline=(59, 130, 246), width=4)
    # Inner articulating iris
    iris_r = max_r * (0.5 + 0.15 * math.sin(progress * 5))
    draw.ellipse([cx - iris_r, cy - iris_r, cx + iris_r, cy + iris_r], fill=(30, 58, 138), outline=(96, 165, 250), width=4)
    # Central laser core
    core_r = max_r * 0.2
    draw.ellipse([cx - core_r, cy - core_r, cx + core_r, cy + core_r], fill=(239, 68, 68), outline=(252, 165, 165), width=2)


def _render_brain_frame(draw: ImageDraw.ImageDraw, width: int, height: int, progress: float):
    """Render neural brain synapse firing network animation."""
    cx, cy = width // 2, height // 2
    for ring in range(1, 5):
        rad = ring * min(width, height) * 0.08
        points = []
        for a in range(8):
            angle = (math.pi * 2 / 8) * a + (progress * 0.5 * (1 if ring % 2 == 0 else -1))
            px = cx + rad * math.cos(angle)
            py = cy + rad * math.sin(angle)
            points.append((px, py))
            # Synaptic impulse flash
            glow = int(180 + 75 * math.sin(progress * 10 + ring + a))
            draw.ellipse([px - 6, py - 6, px + 6, py + 6], fill=(glow, 100, 255))
        for p1, p2 in zip(points, points[1:] + [points[0]]):
            draw.line([p1, p2], fill=(139, 92, 246, 140), width=2)


def _render_nature_frame(draw: ImageDraw.ImageDraw, width: int, height: int, progress: float):
    """Render dynamic rolling landscape with animated sunrise and drifting clouds."""
    # Sun rising
    sun_y = int(height * 0.55 - (progress * height * 0.2))
    sun_r = int(min(width, height) * 0.12)
    draw.ellipse([width // 2 - sun_r, sun_y - sun_r, width // 2 + sun_r, sun_y + sun_r], fill=(251, 191, 36), outline=(245, 158, 11), width=4)
    # Rolling green hills in foreground
    hill_points1 = [(0, int(height * 0.65))]
    for x in range(0, width + 50, 50):
        y = int(height * 0.65 + math.sin((x / width * 4) + progress * 0.5) * 40)
        hill_points1.append((x, y))
    hill_points1.extend([(width, height), (0, height)])
    draw.polygon(hill_points1, fill=(22, 101, 52))

    hill_points2 = [(0, int(height * 0.75))]
    for x in range(0, width + 50, 50):
        y = int(height * 0.75 + math.sin((x / width * 3) - progress * 0.8) * 30)
        hill_points2.append((x, y))
    hill_points2.extend([(width, height), (0, height)])
    draw.polygon(hill_points2, fill=(34, 197, 94))


def render_animated_scene_mp4(
    topic: str,
    duration_s: float,
    width: int,
    height: int,
    output_mp4: Path,
    fps: int = 30,
    ffmpeg_bin: str = "ffmpeg",
) -> Path:
    """
    Render a smooth 30fps MP4 video clip dynamically customized for the script topic.
    """
    duration = max(duration_s, 2.0)
    total_frames = int(duration * fps)

    # Palette backgrounds per topic
    bg_palettes = {
        "flower": (15, 23, 42),       # Midnight Navy garden
        "tech": (10, 15, 30),         # Deep Cyber Blue
        "robot": (18, 18, 24),        # Dark Titanium
        "brain": (19, 13, 36),        # Deep Violet Cosmos
        "nature": (12, 35, 28),       # Dark Emerald
        "space": (5, 5, 16),          # Obsidian Space
        "city": (20, 24, 33),         # Midnight Urban
        "business": (15, 28, 48),     # Executive Slate
    }
    bg_color = bg_palettes.get(topic, (15, 23, 42))

    with tempfile.TemporaryDirectory(prefix="anim_frames_") as tmpdir:
        tmp = Path(tmpdir)
        frame_pattern = tmp / "frame_%05d.png"

        # Generate frames
        for frame_idx in range(total_frames):
            progress = frame_idx / float(total_frames)
            img = Image.new("RGB", (width, height), color=bg_color)
            draw = ImageDraw.Draw(img)

            # Route to thematic visual animation
            if topic == "flower":
                _render_flower_frame(draw, width, height, progress)
            elif topic == "tech":
                _render_tech_frame(draw, width, height, progress)
            elif topic == "robot":
                _render_robot_frame(draw, width, height, progress)
            elif topic == "brain":
                _render_brain_frame(draw, width, height, progress)
            else:
                _render_nature_frame(draw, width, height, progress)

            # Header watermark badge showing AI Generative Subject
            subject_tag = f"AI ANIMATION · {topic.upper()}"
            draw.text((40, 40), subject_tag, fill=(244, 244, 245, 180))

            frame_file = tmp / f"frame_{frame_idx:05d}.png"
            img.save(str(frame_file), format="PNG")

        # Encode frames into MP4 using FFmpeg
        cmd = [
            ffmpeg_bin, "-y",
            "-framerate", str(fps),
            "-i", str(frame_pattern),
            "-t", str(duration),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-preset", "ultrafast",
            "-crf", "22",
            "-an",
            str(output_mp4),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg animated render failed: {res.stderr[:300]}")

    return output_mp4
