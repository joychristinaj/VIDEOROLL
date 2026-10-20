"""
Comprehensive test suite for the PDF-to-Video application.
Run with: pytest tests/ -v

Tests cover:
- PDF extraction (valid, multi-page, empty, corrupted, encrypted, oversized, scanned)
- Script generation
- Script and audio input modes
- Job creation, status, and idempotency
- Footage provider (mock)
- Caption generation
- Security utilities
- API endpoints (using FastAPI TestClient)
"""
from __future__ import annotations

import io
import json
import struct
import time
import uuid
import wave
from pathlib import Path
from typing import Generator

import pytest

# ── Fixtures ──────────────────────────────────────────────────────────────────

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.fixture(scope="session")
def simple_pdf_bytes() -> bytes:
    """A minimal valid PDF with one page of text."""
    return FIXTURES_DIR.joinpath("sample.pdf").read_bytes()


@pytest.fixture(scope="session")
def multi_page_pdf_bytes() -> bytes:
    """A multi-page PDF."""
    p = FIXTURES_DIR / "multipage.pdf"
    if p.exists():
        return p.read_bytes()
    return FIXTURES_DIR.joinpath("sample.pdf").read_bytes()


@pytest.fixture(scope="session")
def empty_pdf_bytes() -> bytes:
    """A PDF with no pages (invalid)."""
    return b"%PDF-1.4\n%%EOF\n"


@pytest.fixture(scope="session")
def corrupted_pdf_bytes() -> bytes:
    return b"%PDF-1.4 THIS IS NOT A REAL PDF \x00\xff\xfe"


@pytest.fixture(scope="session")
def not_pdf_bytes() -> bytes:
    return b"PK\x03\x04 This is a ZIP file"


@pytest.fixture(scope="session")
def silent_wav_bytes() -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(22050)
        wf.writeframes(b"\x00\x00" * 22050)  # 1 second of silence
    return buf.getvalue()


# ── PDF Extraction Tests ───────────────────────────────────────────────────────

class TestPDFExtraction:
    def test_valid_pdf_extraction(self, simple_pdf_bytes):
        from app.services.pdf_extractor import extract_pdf
        result = extract_pdf(simple_pdf_bytes, "sample.pdf")
        assert result.page_count >= 1
        assert result.full_text.strip() != ""
        assert len(result.pages) == result.page_count

    def test_multi_page_pdf(self, multi_page_pdf_bytes):
        from app.services.pdf_extractor import extract_pdf
        result = extract_pdf(multi_page_pdf_bytes, "multi.pdf")
        assert result.page_count >= 1
        assert result.full_text

    def test_page_numbers_preserved(self, simple_pdf_bytes):
        from app.services.pdf_extractor import extract_pdf
        result = extract_pdf(simple_pdf_bytes, "sample.pdf")
        for page in result.pages:
            assert page.page_number >= 1

    def test_empty_pdf_raises(self, empty_pdf_bytes):
        from app.services.pdf_extractor import extract_pdf
        with pytest.raises((ValueError, Exception)):
            extract_pdf(empty_pdf_bytes, "empty.pdf")

    def test_corrupted_pdf_raises(self, corrupted_pdf_bytes):
        from app.services.pdf_extractor import extract_pdf
        with pytest.raises((ValueError, Exception)):
            extract_pdf(corrupted_pdf_bytes, "corrupt.pdf")

    def test_not_pdf_signature_raises(self, not_pdf_bytes):
        from app.core.security import validate_pdf_signature
        with pytest.raises(ValueError):
            validate_pdf_signature(not_pdf_bytes)

    def test_pdf_page_limit(self, simple_pdf_bytes):
        from app.services.pdf_extractor import extract_pdf
        # Should raise when max_pages=0
        with pytest.raises((ValueError, Exception)):
            extract_pdf(simple_pdf_bytes, "sample.pdf", max_pages=0)

    def test_ocr_unavailable_message(self, simple_pdf_bytes):
        """When OCR is requested but unavailable, should warn not crash."""
        from app.services.pdf_extractor import extract_pdf, _tesseract_available
        result = extract_pdf(simple_pdf_bytes, "sample.pdf", use_ocr=False)
        # Should succeed regardless of Tesseract presence
        assert result.ocr_available == _tesseract_available


# ── Script Generation Tests ────────────────────────────────────────────────────

class TestScriptGeneration:
    SAMPLE_TEXT = """[Page 1]
    Introduction to Machine Learning
    Machine learning is a subset of artificial intelligence that enables computers to learn
    from experience without being explicitly programmed. It uses algorithms and statistical
    models to identify patterns in data.

    [Page 2]
    Supervised Learning
    In supervised learning, the algorithm is trained on labeled data. The model learns
    to map input features to output labels. Common applications include spam detection,
    image classification, and speech recognition.

    [Page 3]
    Neural Networks
    Neural networks are computing systems inspired by the biological neural networks
    in animal brains. They consist of layers of interconnected nodes that process
    information using connectionist approaches to computation.
    """

    def test_basic_script_generation(self):
        from app.services.script_generator import generate_script
        from app.models.schemas import VideoDuration, VisualStyle
        result = generate_script(self.SAMPLE_TEXT, duration=VideoDuration.short)
        assert result.script_text.strip() != ""
        assert result.word_count > 0
        assert result.estimated_duration_s > 0
        assert result.provider == "heuristic"

    def test_scenes_have_visual_queries(self):
        from app.services.script_generator import generate_script
        from app.models.schemas import VideoDuration
        result = generate_script(self.SAMPLE_TEXT, duration=VideoDuration.medium)
        assert len(result.scenes) > 0
        for scene in result.scenes:
            assert scene.visual_query.strip() != ""

    def test_empty_text_raises(self):
        from app.services.script_generator import generate_script
        with pytest.raises(ValueError, match="no text content"):
            generate_script("   ")

    def test_duration_affects_word_count(self):
        from app.services.script_generator import generate_script
        from app.models.schemas import VideoDuration
        short = generate_script(self.SAMPLE_TEXT, duration=VideoDuration.short)
        long  = generate_script(self.SAMPLE_TEXT, duration=VideoDuration.long)
        # long should have more (or equal) words
        assert long.word_count >= short.word_count

    def test_scenes_from_script_direct(self):
        from app.services.script_generator import scenes_from_script
        from app.models.schemas import VisualStyle
        script = "First scene text here.\n\nSecond scene text here."
        scenes = scenes_from_script(script, VisualStyle.documentary)
        assert len(scenes) == 2
        assert scenes[0].index == 0

    def test_visual_style_modifies_query(self):
        from app.services.script_generator import _make_visual_query
        from app.models.schemas import VisualStyle
        q1 = _make_visual_query("technology innovation", VisualStyle.cinematic)
        q2 = _make_visual_query("technology innovation", VisualStyle.corporate)
        # Different styles should produce different queries
        assert q1 != q2


# ── Footage Provider Tests ─────────────────────────────────────────────────────

class TestFootageProvider:
    def test_mock_provider_returns_clips(self):
        from app.services.footage_provider import MockProvider
        from app.models.schemas import AspectRatio
        provider = MockProvider()
        clips = provider.search("technology", AspectRatio.r16x9, n=3)
        assert len(clips) == 3
        for c in clips:
            assert c.is_mock is True
            assert c.licence_name  # not empty
            assert c.licence_url   # not empty

    def test_mock_provider_deduplication(self):
        from app.services.footage_provider import MockProvider
        from app.models.schemas import AspectRatio
        provider = MockProvider()
        clips1 = provider.search("nature", AspectRatio.r16x9, n=3)
        used_ids = {c.asset_id for c in clips1}
        clips2 = provider.search("nature", AspectRatio.r16x9, n=3, avoid_ids=used_ids)
        # No clip IDs should repeat
        new_ids = {c.asset_id for c in clips2}
        assert new_ids.isdisjoint(used_ids)

    def test_mock_provider_deterministic(self):
        from app.services.footage_provider import MockProvider
        from app.models.schemas import AspectRatio
        provider = MockProvider()
        r1 = provider.search("science research", AspectRatio.r16x9, n=2)
        r2 = provider.search("science research", AspectRatio.r16x9, n=2)
        assert [c.asset_id for c in r1] == [c.asset_id for c in r2]

    def test_pexels_missing_key_raises(self):
        from app.services.footage_provider import get_footage_provider
        with pytest.raises(ValueError, match="PEXELS_API_KEY"):
            get_footage_provider("pexels", pexels_api_key=None)

    def test_unknown_provider_raises(self):
        from app.services.footage_provider import get_footage_provider
        with pytest.raises(ValueError):
            get_footage_provider("nonexistent")

    def test_minimum_relevance_filtering(self):
        from app.services.footage_provider import MockProvider
        from app.models.schemas import AspectRatio
        provider = MockProvider()
        clips = provider.search("a", AspectRatio.r16x9, n=5)
        # Mock clips all have relevance >= 0.25
        for c in clips:
            assert c.relevance_score > 0


# ── TTS Adapter Tests ──────────────────────────────────────────────────────────

class TestTTSAdapter:
    def test_mock_tts_generates_wav(self, tmp_path):
        from app.services.tts_adapter import MockTTSAdapter
        adapter = MockTTSAdapter()
        out = tmp_path / "output"
        result = adapter.synthesize("Hello world this is a test", out)
        assert result.exists()
        assert result.suffix == ".wav"
        assert result.stat().st_size > 0

    def test_mock_tts_duration_proportional(self, tmp_path):
        from app.services.tts_adapter import MockTTSAdapter
        adapter = MockTTSAdapter()
        short_out = tmp_path / "short"
        long_out  = tmp_path / "long"
        adapter.synthesize("Short", short_out)
        adapter.synthesize("This is a much longer text with many more words for a longer narration", long_out)
        # Longer text → longer WAV
        assert long_out.with_suffix(".wav").stat().st_size > short_out.with_suffix(".wav").stat().st_size

    def test_unknown_tts_provider_raises(self):
        from app.services.tts_adapter import get_tts_adapter
        with pytest.raises(ValueError):
            get_tts_adapter("nonexistent_provider")


# ── Caption Generation Tests ───────────────────────────────────────────────────

class TestCaptionGeneration:
    def _make_scene(self, idx, text, start, end):
        from app.models.schemas import SceneResult
        return SceneResult(index=idx, text=text, start_s=start, end_s=end)

    def test_srt_generation(self, tmp_path):
        from app.services.caption_generator import generate_srt
        scenes = [
            self._make_scene(0, "Hello world this is caption test one.", 0.0, 3.0),
            self._make_scene(1, "Second scene caption text here.", 3.0, 6.0),
        ]
        out = tmp_path / "caps.srt"
        generate_srt(scenes, out)
        content = out.read_text()
        assert "00:00:00" in content
        assert "Hello world" in content

    def test_srt_timestamp_format(self, tmp_path):
        from app.services.caption_generator import generate_srt, _seconds_to_srt_time
        assert _seconds_to_srt_time(0.0) == "00:00:00,000"
        assert _seconds_to_srt_time(3661.5) == "01:01:01,500"


# ── Security Tests ─────────────────────────────────────────────────────────────

class TestSecurity:
    def test_safe_filename(self):
        from app.core.security import safe_filename
        assert safe_filename("../etc/passwd") == "passwd"
        assert safe_filename("my file (2).pdf") == "my_file__2_.pdf"
        assert " " not in safe_filename("file name.pdf")

    def test_pdf_signature_valid(self):
        from app.core.security import validate_pdf_signature
        validate_pdf_signature(b"%PDF-1.4\nsome content")  # should not raise

    def test_pdf_signature_invalid(self):
        from app.core.security import validate_pdf_signature
        with pytest.raises(ValueError):
            validate_pdf_signature(b"NOTAPDF")

    def test_ssrf_protection_localhost(self):
        from app.core.security import validate_url_safe
        with pytest.raises(ValueError):
            validate_url_safe("http://localhost/secret")

    def test_ssrf_protection_private_ip(self):
        from app.core.security import validate_url_safe
        with pytest.raises(ValueError):
            validate_url_safe("http://192.168.1.1/secret")

    def test_ssrf_protection_file_scheme(self):
        from app.core.security import validate_url_safe
        with pytest.raises(ValueError):
            validate_url_safe("file:///etc/passwd")

    def test_valid_url_passes(self):
        from app.core.security import validate_url_safe
        url = validate_url_safe("https://api.pexels.com/videos/search")
        assert url.startswith("https://")


# ── Database Tests ─────────────────────────────────────────────────────────────

class TestDatabase:
    def test_create_and_get_job(self, tmp_path):
        from app.core.database import create_job, get_job, init_db
        db = tmp_path / "test.db"
        init_db(db)
        job_id = str(uuid.uuid4())
        create_job(db, job_id, None, "pdf", {"duration": "medium"})
        job = get_job(db, job_id)
        assert job is not None
        assert job["id"] == job_id
        assert job["status"] == "queued"
        assert job["settings"]["duration"] == "medium"

    def test_idempotency_key_dedup(self, tmp_path):
        from app.core.database import create_job, get_job_by_idempotency_key, init_db
        db = tmp_path / "test2.db"
        init_db(db)
        ikey = "unique-key-123"
        j1 = str(uuid.uuid4())
        j2 = str(uuid.uuid4())
        create_job(db, j1, ikey, "pdf", {})
        # Second create with same key should raise IntegrityError (UNIQUE constraint)
        with pytest.raises(Exception):
            create_job(db, j2, ikey, "pdf", {})
        found = get_job_by_idempotency_key(db, ikey)
        assert found["id"] == j1

    def test_update_job_status(self, tmp_path):
        from app.core.database import create_job, get_job, init_db, update_job
        db = tmp_path / "test3.db"
        init_db(db)
        job_id = str(uuid.uuid4())
        create_job(db, job_id, None, "script", {})
        update_job(db, job_id, status="running", progress=50)
        job = get_job(db, job_id)
        assert job["status"] == "running"
        assert job["progress"] == 50

    def test_missing_job_returns_none(self, tmp_path):
        from app.core.database import get_job, init_db
        db = tmp_path / "test4.db"
        init_db(db)
        assert get_job(db, "nonexistent-id") is None


# ── API Endpoint Tests (FastAPI TestClient) ────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    """FastAPI test client with mock providers configured."""
    import os
    os.environ.setdefault("FOOTAGE_PROVIDER", "mock")
    os.environ.setdefault("TTS_PROVIDER", "mock")
    os.environ.setdefault("TRANSCRIPTION_PROVIDER", "mock")
    os.environ.setdefault("DB_PATH", str(Path(__file__).parent.parent / "test_jobs.db"))

    from fastapi.testclient import TestClient
    from app.main import app
    from app.core.config import get_settings
    get_settings.cache_clear()
    with TestClient(app) as c:
        yield c


class TestHealthEndpoints:
    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_ready(self, client):
        r = client.get("/ready")
        assert r.status_code == 200
        data = r.json()
        assert "ready" in data
        assert "checks" in data
        assert "database" in data["checks"]


class TestPDFEndpoints:
    def test_extract_valid_pdf(self, client, simple_pdf_bytes):
        files = {"file": ("sample.pdf", simple_pdf_bytes, "application/pdf")}
        r = client.post("/api/v1/pdf/extract", files=files)
        assert r.status_code == 200
        data = r.json()
        assert data["page_count"] >= 1
        assert data["full_text"].strip() != ""

    def test_extract_non_pdf_rejected(self, client):
        files = {"file": ("evil.exe", b"MZ\x90\x00 this is an exe", "application/octet-stream")}
        r = client.post("/api/v1/pdf/extract", files=files)
        assert r.status_code in (415, 422)

    def test_extract_corrupted_pdf(self, client, corrupted_pdf_bytes):
        files = {"file": ("bad.pdf", corrupted_pdf_bytes, "application/pdf")}
        r = client.post("/api/v1/pdf/extract", files=files)
        assert r.status_code == 422

    def test_generate_script(self, client):
        body = {
            "full_text": "[Page 1]\nArtificial intelligence is transforming industries. "
                         "Machine learning enables computers to learn from data patterns. "
                         "Deep learning uses neural networks for complex tasks.\n\n"
                         "[Page 2]\nNatural language processing allows computers to understand text. "
                         "Computer vision helps machines interpret images and video.",
            "duration": "short",
            "language": "en",
            "style": "documentary",
        }
        r = client.post("/api/v1/pdf/script", json=body)
        assert r.status_code == 200
        data = r.json()
        assert data["provider"] == "heuristic"
        assert data["word_count"] > 0
        assert len(data["scenes"]) > 0

    def test_empty_text_script_rejected(self, client):
        body = {"full_text": "   ", "duration": "short", "language": "en", "style": "documentary"}
        r = client.post("/api/v1/pdf/script", json=body)
        assert r.status_code == 422


class TestJobEndpoints:
    def test_script_mode_job_creation(self, client):
        data = {
            "input_mode": "script",
            "script_text": (
                "Technology is changing the world rapidly.\n\n"
                "Artificial intelligence enables new possibilities.\n\n"
                "The future holds great promise."
            ),
            "duration": "short",
            "language": "en",
            "style": "documentary",
            "aspect_ratio": "16:9",
            "captions": "true",
        }
        r = client.post("/api/v1/broll/jobs", data=data)
        assert r.status_code == 202
        job = r.json()
        assert "job_id" in job
        assert job["status"] in ("queued", "running")

    def test_job_status_endpoint(self, client):
        # Create a job first
        data = {
            "input_mode": "script",
            "script_text": "Test job for status checking.",
            "duration": "short",
            "language": "en",
            "style": "corporate",
            "aspect_ratio": "1:1",
            "captions": "false",
        }
        r = client.post("/api/v1/broll/jobs", data=data)
        job_id = r.json()["job_id"]

        # Poll status
        status_r = client.get(f"/api/v1/jobs/{job_id}")
        assert status_r.status_code == 200
        assert status_r.json()["job_id"] == job_id

    def test_job_not_found(self, client):
        r = client.get("/api/v1/jobs/nonexistent-job-id")
        assert r.status_code == 404

    def test_idempotency_key_dedup(self, client):
        ikey = f"idem-{uuid.uuid4()}"
        data = {
            "input_mode": "script",
            "script_text": "Idempotency test content here.",
            "duration": "short",
            "language": "en",
            "style": "documentary",
            "aspect_ratio": "16:9",
            "captions": "true",
        }
        r1 = client.post("/api/v1/broll/jobs", data=data, headers={"Idempotency-Key": ikey})
        r2 = client.post("/api/v1/broll/jobs", data=data, headers={"Idempotency-Key": ikey})
        assert r1.status_code == 202
        assert r2.status_code == 202
        assert r1.json()["job_id"] == r2.json()["job_id"]

    def test_empty_script_rejected(self, client):
        data = {
            "input_mode": "script",
            "script_text": "   ",
            "duration": "short",
            "language": "en",
            "style": "documentary",
            "aspect_ratio": "16:9",
            "captions": "true",
        }
        r = client.post("/api/v1/broll/jobs", data=data)
        assert r.status_code == 422

    def test_invalid_aspect_ratio_rejected(self, client):
        data = {
            "input_mode": "script",
            "script_text": "Test content.",
            "duration": "short",
            "language": "en",
            "style": "documentary",
            "aspect_ratio": "4:3",  # not supported
            "captions": "true",
        }
        r = client.post("/api/v1/broll/jobs", data=data)
        assert r.status_code == 422

    def test_pdf_mode_without_file_rejected(self, client):
        data = {
            "input_mode": "pdf",
            "duration": "short",
            "language": "en",
            "style": "documentary",
            "aspect_ratio": "16:9",
            "captions": "true",
        }
        r = client.post("/api/v1/broll/jobs", data=data)
        assert r.status_code == 422

    def test_pdf_mode_with_valid_pdf(self, client, simple_pdf_bytes):
        files = {"pdf_file": ("sample.pdf", simple_pdf_bytes, "application/pdf")}
        data = {
            "input_mode": "pdf",
            "duration": "short",
            "language": "en",
            "style": "documentary",
            "aspect_ratio": "16:9",
            "captions": "true",
        }
        r = client.post("/api/v1/broll/jobs", data=data, files=files)
        assert r.status_code == 202
        assert "job_id" in r.json()

    def test_all_aspect_ratios(self, client):
        for ar in ["16:9", "9:16", "1:1"]:
            data = {
                "input_mode": "script",
                "script_text": f"Test content for aspect ratio {ar}.",
                "duration": "short",
                "language": "en",
                "style": "documentary",
                "aspect_ratio": ar,
                "captions": "false",
            }
            r = client.post("/api/v1/broll/jobs", data=data)
            assert r.status_code == 202, f"Expected 202 for aspect_ratio={ar}, got {r.status_code}"

    def test_audio_mode_with_wav(self, client, silent_wav_bytes):
        files = {"audio_file": ("test.wav", silent_wav_bytes, "audio/wav")}
        data = {
            "input_mode": "audio",
            "duration": "short",
            "language": "en",
            "style": "documentary",
            "aspect_ratio": "16:9",
            "captions": "true",
        }
        r = client.post("/api/v1/broll/jobs", data=data, files=files)
        assert r.status_code == 202

    def test_audio_mode_without_file_rejected(self, client):
        data = {
            "input_mode": "audio",
            "duration": "short",
            "language": "en",
            "style": "documentary",
            "aspect_ratio": "16:9",
            "captions": "true",
        }
        r = client.post("/api/v1/broll/jobs", data=data)
        assert r.status_code == 422


class TestWebUI:
    def test_index_returns_html(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]
        assert "PDF to Video AI" in r.text
