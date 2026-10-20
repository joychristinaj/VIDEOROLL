# Sources and Attribution

## Stock Footage & Media
- **Pexels API**: Used for stock video search and B-roll retrieval ([https://www.pexels.com/api/](https://www.pexels.com/api/)).
  - Licence: Pexels License ([https://www.pexels.com/license/](https://www.pexels.com/license/))
  - All footage metadata (photographer name, source URL, asset ID, license name and URL) is stored and tracked per scene.
  - When offline or without an API key, deterministic mock footage with explicit mock licensing indicators is used for automated testing.

## Text & PDF Extraction
- **PyMuPDF (fitz)**: [https://github.com/pymupdf/PyMuPDF](https://github.com/pymupdf/PyMuPDF) (GNU AGPL / Commercial) - High-performance PDF parsing and text rendering.
- **Tesseract OCR (pytesseract)**: [https://github.com/tesseract-ocr/tesseract](https://github.com/tesseract-ocr/tesseract) (Apache 2.0) - Optional OCR engine for scanned PDF text extraction.

## Narration & Audio
- **gTTS (Google Text-to-Speech)**: [https://github.com/pndurette/gTTS](https://github.com/pndurette/gTTS) (MIT License) - Lightweight text-to-speech adapter.
- **edge-tts**: [https://github.com/rany2/edge-tts](https://github.com/rany2/edge-tts) (LGPL-3.0) - High-quality neural voice TTS adapter.
- **eSpeak / eSpeak NG**: [https://github.com/espeak-ng/espeak-ng](https://github.com/espeak-ng/espeak-ng) (GPL-3.0) - Fast local offline speech synthesizer.
- **OpenAI Whisper**: [https://github.com/openai/whisper](https://github.com/openai/whisper) (MIT License) - Optional local audio transcription.

## Video Rendering & Audio-Video Synchronization
- **FFmpeg & FFprobe**: [https://ffmpeg.org/](https://ffmpeg.org/) (LGPL / GPL) - Industrial-standard command-line media processing tool used for segment generation, video concatenation, audio muxing, subtitle burning, and output stream validation.

## Web Backend & Database
- **FastAPI**: [https://github.com/tiangolo/fastapi](https://github.com/tiangolo/fastapi) (MIT License) - Modern, async web framework.
- **SQLite 3**: Public domain, embedded ACID database with WAL mode for reliable job tracking and status persistence.
- **Pydantic & Pydantic-Settings**: [https://github.com/pydantic/pydantic](https://github.com/pydantic/pydantic) (MIT License) - Data parsing, validation, and type safety.
