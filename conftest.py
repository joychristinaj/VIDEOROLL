"""
conftest.py – shared pytest fixtures loaded automatically.
"""
from __future__ import annotations

import io
import os
import struct
import wave
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def _ensure_fixtures():
    """Generate fixture PDFs if they don't exist yet."""
    sample = FIXTURES_DIR / "sample.pdf"
    if not sample.exists():
        try:
            import sys
            sys.path.insert(0, str(Path(__file__).parent.parent))
            from fixtures.make_fixtures import make_sample_pdf, make_multipage_pdf
            make_sample_pdf()
            make_multipage_pdf()
        except Exception as e:
            print(f"Warning: could not generate fixtures: {e}")


def pytest_configure(config):
    """Called once at the beginning of pytest collection."""
    os.environ.setdefault("FOOTAGE_PROVIDER", "mock")
    os.environ.setdefault("TTS_PROVIDER", "mock")
    os.environ.setdefault("TRANSCRIPTION_PROVIDER", "mock")
    # Use a temporary DB so tests don't pollute production
    os.environ.setdefault("DB_PATH", str(FIXTURES_DIR.parent / "test_jobs.db"))
    _ensure_fixtures()


@pytest.fixture(scope="session")
def simple_pdf_bytes() -> bytes:
    p = FIXTURES_DIR / "sample.pdf"
    if p.exists():
        return p.read_bytes()
    # Fallback: minimal valid PDF
    return (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]"
        b"/Contents 4 0 R/Resources<</Font<</F1<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>>>>>>"
        b">>endobj\n"
        b"4 0 obj<</Length 44>>stream\n"
        b"BT /F1 12 Tf 100 700 Td (Hello World from AI) Tj ET\n"
        b"endstream endobj\n"
        b"xref\n0 5\n0000000000 65535 f \n"
        b"trailer<</Size 5/Root 1 0 R>>\n"
        b"startxref\n9\n%%EOF\n"
    )


@pytest.fixture(scope="session")
def multi_page_pdf_bytes() -> bytes:
    p = FIXTURES_DIR / "multipage.pdf"
    if p.exists():
        return p.read_bytes()
    # fallback to sample
    sp = FIXTURES_DIR / "sample.pdf"
    if sp.exists():
        return sp.read_bytes()
    return b"%PDF-1.4\n%%EOF\n"


@pytest.fixture(scope="session")
def corrupted_pdf_bytes() -> bytes:
    return b"%PDF-1.4 CORRUPTED DATA \x00\xff\xfe garbage"


@pytest.fixture(scope="session")
def not_pdf_bytes() -> bytes:
    return b"PK\x03\x04 This is a ZIP file not a PDF"


@pytest.fixture(scope="session")
def silent_wav_bytes() -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(22050)
        wf.writeframes(b"\x00\x00" * 22050)
    return buf.getvalue()
