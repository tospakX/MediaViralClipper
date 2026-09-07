# Media Viral Clipper

Media Viral Clipper is a local-first pipeline that finds coherent, funny, surprising, or
high-retention moments in a video and exports them for Shorts, Reels, and TikTok. It analyzes
the video locally and uses the lightweight local `qwen3:1.7b` Ollama model as its default moment
judge, with a deterministic heuristic fallback.

## What it does

1. Probes streams, duration, dimensions, codecs, and embedded subtitles with ffprobe/FFmpeg.
2. Prefers usable embedded subtitles; otherwise transcribes locally with faster-whisper.
3. Detects visual scene changes with PySceneDetect and measures audio energy and peaks.
4. Generates many dialogue-led windows, rejecting intros, credits, incomplete sentences, and
   windows outside the configured duration range.
5. Scores humor, punchline, surprise, quotability, hook, standalone context, pacing, reactions,
   and retention. It then suppresses overlapping, adjacent, and lexically duplicated jokes.
6. Refines selected boundaries around complete dialogue, setup, punchline, and reaction while
   enforcing the configured hard maximum.
7. Renders a clean source-aspect clip and, when enabled, a 1080x1920 version. The vertical crop
   samples faces first, then motion/saliency, damps movement, and falls back to a safe center crop.
8. Exports short portrait-safe burned captions with active-word emphasis and a separate SRT file.
9. Delivers both final videos at 1.10x by default, with pitch-preserving audio and synchronized
   subtitle timing.

Each expensive stage has a content/config fingerprint under `.cache`. Re-running the same input
reuses valid stages, while changed media or relevant settings invalidate only affected work.
Every FFmpeg call uses an argv list, so spaces and shell characters in paths are safe. Rendering
errors are captured per clip and do not discard other selections.

## Requirements

- Linux with FFmpeg and ffprobe on `PATH` (libass is needed for burned captions)
- Python 3.11–3.13; Python 3.12 is recommended
- An NVIDIA GPU is optional. `--hardware-encoding auto` uses NVENC when FFmpeg exposes it and
  falls back to CPU if NVENC fails at runtime.

## Install

Using [uv](https://docs.astral.sh/uv/):

```bash
cd /home/tospak/Desktop/Code/MediaViralClipper
uv sync --python 3.12 --extra analysis --extra dev
```

The `analysis` extra installs faster-whisper, OpenCV, and PySceneDetect. If every source has good
embedded subtitles, the base install can perform dry runs without downloading a Whisper model.
The first transcription run downloads the chosen faster-whisper model.

Before feeding it a full episode, run the read-only readiness check:

```bash
uv run clipper-doctor
```

It verifies FFmpeg/ffprobe, burned-caption support, transcription dependencies, free disk space,
and reports optional NVENC acceleration separately. It does not download a speech model.

## Local web UI

Start the cut room:

```bash
cd /home/tospak/Desktop/Code/MediaViralClipper
uv run clipper-web
```

Open <http://127.0.0.1:8765>, choose one episode or browse to a folder, then select **Find my best
clips**. The web UI chooses one to three clips automatically from the number of distinct,
high-scoring moments. Nearby candidates are treated as one story sequence so two pieces of the same
scene do not consume separate output slots. A folder is scanned recursively for MP4, MKV, MOV,
WebM, M4V, and AVI files. Up to 100 episodes can be queued in one batch, with one aggregate progress
view instead of one browser request per episode. Select **View clips** beside any completed episode
to inspect its transcript, scores, previews, and downloads.

The built-in file browser reads local paths directly; it does not upload or duplicate episode files.
Paste-a-path remains available for power users, and output defaults to
`~/Downloads/MediaViralClipper`.

The queue is sized for season-scale batches: search and status filters keep 80–100 episodes
manageable while one worker processes them sequentially. The preview panel loads only one video at
a time and supports vertical/original switching and direct downloads.

The web UI defaults to `~/Downloads/MediaViralClipper`; each episode gets its own folder below that
location. Paths beginning with `~/` are expanded automatically. Only one episode runs at a time,
so a 70–100 episode batch cannot make jobs compete for the GPU. Closing the browser does not stop
the queue. The live batch list is intentionally in memory. Restarting or stopping the server clears
old queue state and pipeline `.cache` directories, while finished videos, SRT files,
`ranking.json`, `transcript.json`, and metadata remain on disk.

The server binds to `127.0.0.1` by default. Do not use `--host 0.0.0.0` unless you intentionally
want other devices on the network to reach it. Clip download routes can serve only artifacts
recorded for a completed job; they are not general-purpose filesystem routes.

## Use

Exact command for a normal 20-minute episode:

```bash
cd /home/tospak/Desktop/Code/MediaViralClipper
uv run python -m clipper "/path/to/20 minute episode.mkv" \
  --clips 3 \
  --min-duration 15 \
  --max-duration 40 \
  --vertical \
  --captions \
  --output ./output
```

Analyze and rank without rendering:

```bash
uv run python -m clipper "/path/to/episode.mkv" --dry-run --output ./output
```

Useful controls:

```text
--clips 3
--min-duration 15
--max-duration 40
--vertical / --no-vertical
--captions / --no-captions
--caption-style default|bold|minimal
--playback-speed 1.10
--whisper-model small
--language en
--device auto|cpu|cuda
--compute-type auto|float16|int8
--hardware-encoding auto|cpu|nvenc
--workers 2
--scene-threshold 27
--output ./output
--dry-run
```

The maximum is a hard boundary. Values over 40 seconds are accepted only when explicitly passed
with `--max-duration`.

## Optional LLM scoring

The web UI and CLI use local Ollama with `qwen3:1.7b` by default and fall back to the offline
heuristic ranker if the local model is unavailable. An OpenAI-compatible endpoint can be used
without changing the rest of the pipeline:

```bash
export CLIPPER_LLM_API_KEY="your-key"
uv run python -m clipper episode.mkv \
  --ranker openai-compatible \
  --llm-base-url https://provider.example/v1 \
  --llm-model provider-model \
  --dry-run
```

Only candidate transcript text, timestamps, and compact timing features are sent. Video and audio
are never sent to the provider.

## Output

```text
~/Downloads/MediaViralClipper/
└── episode_name/
    ├── .cache/
    ├── run.jsonl
    ├── ranking.json
    ├── transcript.json
    ├── clip_01/
    │   ├── original.mp4
    │   ├── vertical.mp4
    │   ├── subtitles.srt
    │   └── metadata.json
    ├── clip_02/
    └── clip_03/
```

`metadata.json` records source, refined timestamps, source and accelerated output durations,
playback speed, transcript, every component score, overall score, selection explanation, and render
status. A hidden ASS file may be retained beside the SRT because FFmpeg uses it to burn the styled
vertical captions.

## Quality and development checks

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src/clipper
uv run python -m build
```

Browser smoke test (requires the `dev` extra and `uv run playwright install chromium` once):

```bash
uv run python /home/tospak/.agents/skills/webapp-testing/scripts/with_server.py \
  --server "uv run clipper-web --port 8765" --port 8765 \
  -- uv run python tests/browser/browser_smoke.py
```

The end-to-end test generates its own synthetic video, audio, scene pattern, and dialogue subtitle
track with FFmpeg. No copyrighted test media is stored in this project.

## Operational notes

- The source file is opened read-only and is never deleted or replaced.
- CPU encoding is limited by `--workers` (default 2) to avoid unnecessarily saturating the host.
- Use `--device cuda --compute-type float16` for faster-whisper on a supported NVIDIA GPU.
- If a source's embedded subtitle track is incomplete, disable it in code/config or remux a correct
  full subtitle track.
- Embedded tracks are scored by coverage, language, and disposition. Short forced/sign tracks are
  ignored automatically; use `--no-use-embedded-subtitles` if a full track is still inaccurate.
- If a clip render fails, inspect its `metadata.json` and the episode's `run.jsonl`; other clips
  continue rendering.
