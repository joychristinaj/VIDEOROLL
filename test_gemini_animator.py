"""
Unit tests for Gemini Omni Flash Animated Video Generation and Token Accounting.
"""
import pytest
from pathlib import Path
from app.models.schemas import AspectRatio, ScriptScene, VideoSettings
from app.services.gemini_animator import (
    call_gemini_analysis,
    compute_cost,
    extract_topic_from_text,
    render_animated_scene_mp4,
)
from app.services.job_runner import run_job
from app.core.config import get_settings


def test_extract_topic_from_text():
    assert extract_topic_from_text("A beautiful pink flower blooming in spring") == "flower"
    assert extract_topic_from_text("Deep neural network and brain cognitive functions") == "brain"
    assert extract_topic_from_text("Autonomous robots and industrial automation") == "robot"
    assert extract_topic_from_text("Digital cloud data software architecture") == "tech"
    assert extract_topic_from_text("Clean solar energy and sustainable forest trees") == "nature"


def test_compute_cost():
    # 1M prompt tokens = $0.075, 1M candidate tokens = $0.30
    cost = compute_cost(1000, 500)
    expected = (1000 * 0.075 / 1e6) + (500 * 0.30 / 1e6)
    assert round(cost, 6) == round(expected, 6)
    assert cost > 0


def test_call_gemini_analysis_offline():
    topic, prompt_tokens, candidate_tokens = call_gemini_analysis("Red roses and yellow sunflowers blossoming")
    assert topic == "flower"
    assert prompt_tokens > 0
    assert candidate_tokens > 0


def test_render_animated_scene_flower(tmp_path):
    output_mp4 = tmp_path / "test_flower.mp4"
    rendered = render_animated_scene_mp4(
        topic="flower",
        duration_s=2.0,
        width=640,
        height=360,
        output_mp4=output_mp4,
        fps=15,
    )
    assert rendered.exists()
    assert rendered.stat().st_size > 10000


def test_job_runner_api_mode_flower(tmp_path):
    cfg = get_settings()
    scenes = [
        ScriptScene(
            index=0,
            text="The gentle morning dew awakens vibrant flower petals in the botanic garden.",
            duration_hint=2.0,
        ),
        ScriptScene(
            index=1,
            text="Robotic sensors monitor soil moisture and automated systems nourish each blossom.",
            duration_hint=2.0,
        ),
    ]
    settings = VideoSettings(
        aspect_ratio=AspectRatio.r16x9,
        generation_mode="api",
        captions=True,
    )
    db_path = tmp_path / "test_jobs.db"
    from app.core.database import init_db, create_job
    init_db(db_path)
    job_id = "test_api_flower_job"
    create_job(db_path, job_id, None, "script", settings.model_dump())

    result = run_job(
        job_id=job_id,
        scenes=scenes,
        settings=settings,
        output_dir=tmp_path / "outputs",
        db_path=db_path,
        cfg=cfg,
    )

    assert result.generation_mode == "api"
    assert result.token_usage is not None
    assert result.token_usage.total_tokens > 0
    assert result.token_usage.estimated_cost_usd >= 0
    assert len(result.scenes) == 2
    assert "flower" in result.scenes[0].clip.asset_id
    assert Path(result.scenes[0].clip.local_path).exists()
    assert Path(result.video_url.replace("/outputs/", str(tmp_path / "outputs") + "/")).exists()
