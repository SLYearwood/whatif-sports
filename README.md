# whatif-sports

Automated pipeline for a faceless sports "What If" Shorts channel: idea → script → voice → visuals → captions → 9:16 MP4. Every idea and script gets a human review before publishing. See [CLAUDE.md](CLAUDE.md) for the full plan and content rules.

## Status

- Milestone 1 is done: render a Short from a hand-written script YAML, fully offline.
- Milestone 2 is done: ElevenLabs narration with a cache, so re-renders aren't billed again, and captions synced to the actual speech.
- Characters are done: animated stylized players in broadcast-style play scenes, plus optional AI video clips (Higgsfield) for key moments.

## Setup

Requires Python 3.11+ and an ffmpeg build with `libflite` (on Windows: `winget install Gyan.FFmpeg`).

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
copy .env.example .env
```

## Usage

```powershell
.\.venv\Scripts\whatif validate seahawks-xlix-run
.\.venv\Scripts\whatif render seahawks-xlix-run                    # ElevenLabs if configured, else flite
.\.venv\Scripts\whatif render seahawks-xlix-run --voice flite      # force the offline voice
.\.venv\Scripts\whatif render seahawks-xlix-run --voice sapi       # Windows voice, offline
.\.venv\Scripts\whatif voices                                      # list ElevenLabs voice ids
.\.venv\Scripts\whatif clips seahawks-xlix-run                     # preview AI clips to generate
.\.venv\Scripts\whatif clips seahawks-xlix-run --yes               # generate them (billed)
```

The output goes to `data/<id>/render/<id>.mp4`, next to a `manifest.json` that records segment timings, the voice used, and the sources. Audio is cached in `data/<id>/audio/`, keyed by a hash of everything that affects the sound: text, voice, model, settings, and the neighbouring segments' text.

### ElevenLabs voice

1. In ElevenLabs, create a voice clone. Instant Voice Clone needs about 1–2 minutes of clean speech.
2. Put `ELEVENLABS_API_KEY` in `.env`, then run `whatif voices` and copy your clone's id into `ELEVENLABS_VOICE_ID`.
3. Run `whatif render <id>`. The log shows how many characters will be billed. Segments that are already cached cost nothing, and a render that would send more than `WHATIF_MAX_TTS_CHARS` (default 3000) is refused.

Each segment is sent along with the segments before and after it (`previous_text` / `next_text`), so the delivery flows across cuts. ElevenLabs returns per-character timings, and captions use them, so each caption appears exactly when its words are spoken.

### Characters

Two ways to put players on screen, and both keep to the content rules: no real athletes' likenesses, logos, numbers, or league marks.

- **`play_scene`** shows a named play from `visuals/plays.py`, acted out by stylized, faceless players from a broadcast sideline angle. The camera follows the ball, and the play shows the snap, the routes, the throw or handoff, and then the interception or the touchdown dive and celebration. Uniforms use colors only (`offense` / `defense` kits in the YAML). It's free and fully automatic.
- **`moment`** shows one big player reacting (`celebrate`, `dejected`, `dive`, `run`) under a headline.
- **`ai_clip`** is an AI-generated shot for a key moment, made with Higgsfield (Seedance 2.0, 9:16, no generated audio). Every prompt gets a suffix that forbids recognizable faces, logos, numbers, and text. Prompts that ask for logos are rejected outright.
  - `whatif render` never spends money. Until a clip exists, it shows a clearly marked placeholder.
  - `whatif clips <id>` lists what would be generated. Add `--yes` to submit. Clips are cached by prompt hash, and an interrupted job resumes instead of resubmitting.
  - The render manifest records `synthetic_media: true` when clips are used, so publishing can set each platform's AI-content disclosure. It also lists `pending_clips`, so nothing ships with a placeholder.
  - Review every generated clip before approving the video.

A script can be an id (resolved from `data/<id>/script.yaml`, then `examples/<id>.yaml`) or a path to a YAML file.

## Layout

```
whatif_sports/
  script/    pydantic schema for the script YAML + loader
  voice/     TTS: ElevenLabs (with timestamps), flite via ffmpeg, Windows SAPI; hash-keyed cache
  visuals/   Pillow templates: title, stat, scoreboard, play_diagram, play_scene, moment,
             timeline, outro; plays.py (play data), figures.py (players), scene.py (camera)
  clips/     Higgsfield client, clip cache, and frame reader for ai_clip segments
  assemble/  caption chunking/timing, narration mix, frame piping into ffmpeg
  cli.py     `whatif validate|render|voices|clips`
examples/    hand-written scripts
tests/
```

## Dev

```powershell
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\ruff check .
.\.venv\Scripts\ruff format .
```
