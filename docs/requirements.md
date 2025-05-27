## Introduction

This document specifies detailed requirements for **BestVideo**, a Python tool designed to process terabytes of video data, extract comprehensive metadata, detect duplicates, analyze quality, and select the best video per language with robust logging, resumability, and accurate language detection.

---

## 1. Directory Scanning & Initial Grouping

* **Recursive Scan**

  * Walk a given root path.
  * Include common video extensions (`.mp4, .mkv, .avi`, etc.).
* **Batch Processing**

  * Process files in configurable **batches** (e.g. 1 000 files/batch) for memory control.
* **Filename Clustering**

  * Group by directory and **base filename** to form initial clusters (e.g. `movie.en.1080p.mp4` vs. `movie.en.720p.mkv`).

---

## 2. Duplicate Detection & Content Identification

* **Size & Duration Pre-filter**

  * Exclude files whose **size** differs by > 5% or **duration** by > 0.5 s.
* **Perceptual Video Hash**

  * Use a library like **videohash** for fast, robust hashing ([PyPI][1]).
  * Assign a `content_id` for each near-duplicate cluster.

---

## 3. Metadata Extraction

* **Tool: FFprobe**

  * Extract streams via:

    ```bash
    ffprobe \
      -v error -hide_banner \
      -show_streams -show_format \
      -print_format json <file>
    ```

  ([Gist][2])
* **Extracted Fields**

  * **Video**: resolution, frame rate, codec, bitrate, duration.
  * **Audio**: codec, bitrate, channels, metadata language tag.
  * **Subtitle**: codec, format, metadata language tag.
* **Integrity Check**

  * Run `ffmpeg -v error -i <file> -f null -` to flag **broken frames**.

---

## 4. Database Schema (SQLite)

```sql
CREATE TABLE videos (
  id INTEGER PRIMARY KEY,
  content_id TEXT,
  path TEXT UNIQUE,
  size_bytes INTEGER,
  duration_s REAL,
  width INTEGER, height INTEGER,
  fps REAL,
  video_codec TEXT, video_bitrate INTEGER,
  audio_tracks INTEGER, audio_codecs TEXT,
  audio_languages_label TEXT, audio_languages_detected TEXT,
  subtitle_tracks INTEGER, subtitle_languages_label TEXT,
  subtitle_languages_detected TEXT,
  corruption_flag BOOLEAN,
  sharpness_score REAL, color_score REAL,
  audio_quality_score REAL, weighted_score REAL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE tasks (
  file_id INTEGER,
  stage TEXT,            -- SCAN, HASH, META, ANALYZE, AUDIO_LANG_ID, SUBTITLE_LANG_ID
  status TEXT,           -- PENDING, DONE, ERROR
  last_updated DATETIME,
  PRIMARY KEY (file_id, stage)
);
CREATE INDEX idx_tasks_status ON tasks(status);
```

* **JSON Fields** store arrays of `{track_index, lang, confidence}`.

---

## 5. Quality Metrics & Scoring

1. **Resolution & Bitrate**

   * Score ∝ `width × height` and `video_bitrate`.
2. **Codec Ranking**

   * Predefined map: **AV1 > H.265 > H.264**, etc.
3. **Sharpness**

   * Sample frames, compute **variance of Laplacian** via OpenCV.
4. **Color Fidelity**

   * Compare **color histograms** or average saturation.
5. **Audio Quality**

   * Score by **bitrate**, sample rate, channel count.
6. **Corruption Penalty**

   * Negative weight if `corruption_flag` is true.
7. **Language & Subtitle Bonus**

   * Extra points if detected audio/subtitle languages match target.
   * Bonus for **multiple audio/subtitle tracks**.

---

## 6. Selection Algorithm

For each `(content_id, language)` group:

1. **Filter** files by detected audio language.
2. **Compute** `weighted_score`.
3. **Add** bonus for multiple audio tracks.
4. **Select** highest-scoring file.
5. **Tiebreaker**: Newer creation date.

---

## 7. Scalability & Performance

* **Parallel Workers**

  * `--workers N` to set concurrency (multiprocessing or threads).
* **Streaming I/O**

  * Probe with `-map` and sample frames only.
* **Resource Limits**

  * Optionally throttle CPU and disk I/O usage.
* **Batch Size**

  * Configurable per run to handle **TB-scale** data.

---

## 8. Robust Logging & Progress Reporting

* **Logging** via Python’s `logging` module:

  * **StreamHandler** for console (INFO level).
  * **RotatingFileHandler** for full DEBUG logs (100 MB, 5 backups).
* **Progress Bars**

  * Use **tqdm** or **rich** for:

    * Directory scanning
    * Metadata extraction
    * Quality analysis
* **Log Levels**

  * DEBUG, INFO, WARNING, ERROR; configurable via CLI.

---

## 9. Resumable & Fault-Tolerant Workflow

* **Checkpointing**

  * Before each stage, consult `tasks.status`.
  * Skip `DONE` stages on resume (`--resume`).
* **Graceful Shutdown**

  * Handle SIGINT/SIGTERM, commit DB, exit cleanly.
* **Retry Logic**

  * Retry transient errors up to configurable limit.

---

## 10. Audio-Language Detection (All Tracks)

* **Voice Activity Detection (VAD)**

  * Use **pyannote.audio** or **webrtcvad** to isolate speech ([Hugging Face][3]).
* **Language Identification**

  * **OpenAI Whisper (small)** for transcription + lang ID ([Hugging Face][4]).
  * **fasttext-langdetect** for faster detection ([PyPI][5]).
* **Per-Track Pipeline**

  1. Extract 30 s of speech.
  2. Run VAD → extract speech segments.
  3. Transcribe & detect language.
* **Results Storage**

  * `audio_languages_detected`: JSON array of `{track_index, lang, confidence}`.
  * `audio_languages_label`: original metadata tag.
* **Confidence Threshold**

  * Accept if ≥ 0.7; else `und`.

---

## 11. Subtitle-Language Detection (All Tracks)

* **Extraction**

  * Use **mkvextract** (from mkvtoolnix) to dump first 100 lines per stream ([Ask Ubuntu][6]).
* **Language ID**

  * **langdetect** for text-based detection ([PyPI][7]).
  * For short streams, aggregate multiple segments.
* **Results Storage**

  * `subtitle_languages_detected`: JSON array of `{stream_index, lang, confidence}`.
  * `subtitle_languages_label`: original metadata.
* **Fallback**

  * Confidence < 0.6 → `und`.
  * No text/binary-only → `no_text`.

---

## 12. Configuration & CLI

* **Config File** (`YAML`/`TOML`):

  ```yaml
  batch_size: 1000
  workers: 8
  retry_limit: 3
  language_detection:
    audio:
      model: whisper-small
      vad: webrtcvad
      min_confidence: 0.7
    subtitle:
      library: langdetect
      min_confidence: 0.6
      lines_per_stream: 100
  weights:
    resolution: 1.0
    bitrate: 0.8
    codec: 0.5
    sharpness: 0.7
  ```
* **CLI Flags**:

  * `--root <path>`, `--db <path>`, `--config <file>`, `--resume`, `--dry-run`, `--verbose`

---

## 13. Reporting & Actions

* **Output**:

  * CSV/JSON list of `(selected_path, language, score)`.
* **Optional**:

  * Move best files to `best/` folder.
  * Delete duplicates after confirmation (`--purge`).
* **Summary Report**:

  * Mismatches between labels and detections.

---

## 14. Testing & Validation

* **Unit Tests** for:

  * Metadata parsing.
  * VAD → LangID.
  * Checkpoint & resume logic.
* **Integration Tests** on small dataset (< 10 GB).
* **Performance Benchmarks**:

  * Files/minute throughput.
  * Database write latency.

---

This comprehensive specification ensures **modularity**, **scalability**, **accuracy**, and **robustness**, covering every requirement for automated best-video selection across **large-scale** video archives.

[1]: https://pypi.org/project/videohash/?utm_source=chatgpt.com "videohash - PyPI"
[2]: https://gist.github.com/nrk/2286511?utm_source=chatgpt.com "Using ffprobe to get info from a file in a nice JSON format - GitHub Gist"
[3]: https://huggingface.co/pyannote/voice-activity-detection?utm_source=chatgpt.com "pyannote/voice-activity-detection - Hugging Face"
[4]: https://huggingface.co/openai/whisper-small?utm_source=chatgpt.com "openai/whisper-small - Hugging Face"
[5]: https://pypi.org/project/fasttext-langdetect/?utm_source=chatgpt.com "fasttext-langdetect - PyPI"
[6]: https://askubuntu.com/questions/452268/extract-subtitle-from-mkv-files?utm_source=chatgpt.com "Extract subtitle from mkv files - Ask Ubuntu"
[7]: https://pypi.org/project/langdetect/?utm_source=chatgpt.com "langdetect - PyPI"
