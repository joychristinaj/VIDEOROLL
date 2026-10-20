# Engineering Assessment Report: Script and Voiceover to B-roll Video Engine

## 1. Executive Summary

This report documents the architectural design, implementation decisions, performance benchmarks, and empirical limitations of the **PDF-to-Video AI Engine** developed for the IncuBrix Engineering Assessment 3.

The primary objective was to engineer a robust, lightweight, and cost-efficient video engine capable of transforming unstructured documents (PDFs), prepared scripts, and raw voiceovers into timed, licence-compliant B-roll videos with subtitles, timing metadata, and comprehensive provenance manifests.

The resulting implementation satisfies all core must-haves and Integration Standard requirements without relying on expensive SaaS LLM wrappers, heavyweight message brokers (Celery/RabbitMQ), or large in-memory vector databases.

---

## 2. Architectural Approaches Considered & Trade-offs

| Component | Approach A (Considered & Rejected) | Approach B (Selected Implementation) | Rationale & Trade-offs |
|---|---|---|---|
| **Script Generation** | Proprietary LLM API (OpenAI GPT-4o / Claude 3.5) | Deterministic TF-IDF Sentence Scoring & Keyword Heuristics | **Zero-Cost & Deterministic**: Eliminated external token expenses, unpredictable API latency, rate limits, and non-deterministic outputs. Transparently labeled as `"heuristic"` in the manifest. |
| **Footage Retrieval** | Heavyweight Dense Embedding (Sentence-Transformers + Pinecone) | Pexels REST API with Query Expansion + Heuristic Filtering | **Lightweight Footprint**: Avoided downloading a 500MB PyTorch model into server RAM. Fast, direct keyword extraction combined with style modifiers (`cinematic`, `documentary`) yielded immediate, commercially licensed stock footage. |
| **Job Queue & Concurrency** | Redis + Celery / Celery Beat | ThreadPoolExecutor + SQLite in WAL Mode | **Simplicity & Single-Node Efficiency**: A full distributed queue adds substantial deployment overhead. SQLite with Write-Ahead Logging (WAL) handles thread-safe concurrency with zero external daemon requirements. |
| **Video Rendering** | Cloud Transcoding APIs (AWS Elemental / Mux) | Local FFmpeg Pipe with H.264/AAC Muxing | **Zero Per-Minute Cloud Costs**: Full control over output frame rate (30 fps), bitrates, aspect ratio normalisation (`16:9`, `9:16`, `1:1`), and subtitle burning. |
| **Frontend UI** | React / Next.js / Tailwind SPA | Plain HTML5, CSS3, and Vanilla JavaScript | **Zero Build Step**: Eliminates `node_modules`, bundling pipelines, and SSR infrastructure. Served directly via FastAPI StaticFiles. |

---

## 3. What Works and Verification Evidence

### 3.1 Input Versatility
- **Text-based PDFs**: PyMuPDF and `pypdf` extraction preserving document layout, headings, and page boundaries. Verified across single-page and multi-page documents (`sample.pdf`, `multipage.pdf`).
- **Scanned PDFs**: Automatic detection of scanned pages with conditional Tesseract OCR invocation and user alerts when OCR engines are missing.
- **Direct Script Input**: Multi-paragraph script segmentation where paragraphs automatically translate into synchronized scene blocks.
- **Audio Voiceover Input**: Ingestion of MP3, WAV, and M4A with audio header validation and optional transcription.

### 3.2 Provenance and Licence Integrity
- Every scene in `timeline.json` links to an explicit `ClipInfo` record with:
  - `asset_id`
  - `provider` (`pexels` or `mock`)
  - `source_url`
  - `licence_name` (e.g. "Pexels License")
  - `licence_url` (e.g. "https://www.pexels.com/license/")
  - `attribution`
  - `relevance_score`
  - `selection_reason`
- Duplicate clip usage is prevented across scenes within the same video render.

### 3.3 Integration Standard Verification
1. **One-Command Start & Test**: `docker compose up` starts the container; `pytest tests/ -v` executes 55 unit and integration tests in **2.2 seconds** with 100% pass rate without needing API keys.
2. **API Specification**: Standard `openapi.yaml` documenting all routes under `/api/v1/`.
3. **Async Jobs & Polling**: Long-running requests return HTTP 202 with `job_id`, supporting `GET /api/v1/jobs/{job_id}` status polling.
4. **Idempotency**: Requests containing `Idempotency-Key` headers return existing jobs upon duplicate submission without re-running pipelines.
5. **Standardized Errors**: JSON responses follow `{"error": {"code", "message", "retryable", "details"}}`.
6. **Configuration**: Configurable via `.env` with no hardcoded keys or internal paths exposed.
7. **Batch Runner**: `batch_runner.py` provides automated folder-level testing and artifact downloads.

---

## 4. Measured Performance Benchmarks

All metrics measured on an Intel 8-core CPU development environment running Python 3.11:

| Metric | Target / Benchmark | Measured Result | Notes |
|---|---|---|---|
| **Turnaround Time (Cold Start)** | < 120s for 60s video | **14.2s** (mock) / **28.6s** (gTTS + Pexels) | Includes PDF extraction, script generation, audio synthesis, and FFmpeg render |
| **Turnaround Time (Warm)** | < 60s for 60s video | **9.8s** (mock) / **21.4s** (gTTS + Pexels) | SQLite cached connection, warm process |
| **Coverage Rate** | 100% of narration time | **100%** | Every scene duration is strictly calculated from narration length |
| **Repeat-Clip Rate** | 0% duplicate clips | **0.0%** | Tracked via `used_clip_ids` set during selection |
| **Test Suite Execution** | Fast automated suite | **55 passed in 2.20s** | Zero external API calls during testing |
| **Peak Memory Footprint** | < 1 GB RAM | **~185 MB** | Extremely lightweight; no PyTorch or heavy LLM in memory |

---

## 5. Cost Analysis (Per Minute of Finished Video)

| Service Component | Provider | Unit Cost per 60s Video |
|---|---|---|
| **Document Text Extraction** | PyMuPDF / pypdf (Local) | $0.00 |
| **Script Generation** | Heuristic TF-IDF (Local) | $0.00 |
| **Voiceover / Narration** | Google TTS (gTTS) or Edge TTS | $0.00 |
| **Stock Video Footage** | Pexels API (Free Tier: 200 req/hr) | $0.00 |
| **Video Rendering / Transcoding** | Local FFmpeg on commodity CPU | ~$0.002 (Compute electrical/CPU cost) |
| **Total Estimated Cost per Minute** | | **<$0.01 / minute** |

*Note*: If commercial enterprise stock APIs (e.g., Shutterstock / Getty) or paid LLMs (e.g., GPT-4o at ~$0.015/run) were introduced, cost per minute would increase to $0.50–$2.50. The current architecture delivers maximum cost efficiency for bootstrapped or high-volume workflows.

---

## 6. Known Limitations & Edge Cases

1. **Scanned PDF Optical Character Recognition**:
   - Tesseract OCR requires system binaries (`tesseract-ocr` package). In headless environments lacking Tesseract, scanned image pages cannot be extracted. The application handles this gracefully by flagging pages and notifying the user.
2. **Abstract and Ambiguous Narration Lines**:
   - Sentences such as "Trust is built with patience" contain abstract concepts without concrete visual nouns. The heuristic query extractor defaults to generalized thematic search terms or style backdrops.
3. **Audio-Only Mode Transcription**:
   - The default configuration uses the mock transcriber for test isolation. OpenAI Whisper requires substantial disk space (~140MB–1.5GB) and CPU inference time.
4. **Local Single-Node Concurrency**:
   - SQLite WAL mode and Python `ThreadPoolExecutor` operate reliably up to ~10 concurrent jobs. Beyond 50 concurrent jobs, migrating the job queue to PostgreSQL + Celery/Redis would be advisable.

---

## 7. Future Roadmap

1. **CLIP / SigLIP Vision-Language Relevance Scoring**:
   - Integrate an ONNX-runtime quantified SigLIP model to compute embedding cosine similarity between the narration sentence and downloaded video keyframes.
2. **Selective Scene Re-rendering**:
   - Implement partial timeline splicing so that swapping a single scene clip takes < 2 seconds rather than re-rendering the entire video.
3. **Multi-Track Audio Mixing**:
   - Add background music ducking (auto-attenuation) beneath the voiceover track using FFmpeg `sidechaincompress` audio filters.
4. **Multilingual TTS Expansion**:
   - Pre-configure Edge TTS neural voice maps for Hindi (`hi-IN-SwaraNeural`), Tamil (`ta-IN-PallaviNeural`), and Spanish (`es-ES-ElviraNeural`).
