"""AI clip cache: data/<id>/clips/<key>.mp4, generated only on explicit request.

A clip's key hashes everything sent to the generator, so editing the prompt makes a new
clip and re-rendering never re-bills. The job file (<key>.job.json) is written right after
submission so an interrupted run resumes polling instead of paying again.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from pathlib import Path

from whatif_sports import config
from whatif_sports.clips import higgsfield
from whatif_sports.script.schema import AIClipSegment, Script

# Appended to every prompt: keeps generated people anonymous and brand-free.
SAFETY_SUFFIX = (
    " Stylized, cinematic. All people are anonymous, fictional athletes with no recognizable "
    "faces; plain uniforms in solid colors with no logos, numbers, names, or text anywhere."
)


@dataclass(frozen=True)
class ClipSpec:
    model: str
    prompt: str
    duration: int
    resolution: str
    aspect_ratio: str = "9:16"

    @classmethod
    def from_segment(cls, seg: AIClipSegment) -> ClipSpec:
        return cls(seg.model, seg.prompt.strip() + SAFETY_SUFFIX, seg.duration, seg.resolution)

    def payload(self) -> dict:
        return {
            "prompt": self.prompt,
            "duration": self.duration,
            "resolution": self.resolution,
            "aspect_ratio": self.aspect_ratio,
            "generate_audio": False,  # narration is ours
        }

    @property
    def key(self) -> str:
        raw = json.dumps({"model": self.model, **self.payload()}, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    @property
    def idempotency_key(self) -> str:
        # Deterministic, so a retried submit of the same clip is never charged twice.
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"whatif-sports/{self.key}"))


def clips_dir(script_id: str) -> Path:
    return config.DATA_DIR / script_id / "clips"


def clip_path(script_id: str, seg: AIClipSegment) -> Path:
    return clips_dir(script_id) / f"{ClipSpec.from_segment(seg).key}.mp4"


def clip_segments(script: Script) -> list[tuple[int, AIClipSegment]]:
    return [(i, s) for i, s in enumerate(script.segments) if s.type == "ai_clip"]


def missing(script: Script) -> list[tuple[int, AIClipSegment]]:
    return [(i, s) for i, s in clip_segments(script) if not clip_path(script.id, s).exists()]


def generate(script: Script, log=print) -> list[Path]:
    """Generate every missing clip (this spends money). Returns the new files."""
    out = []
    d = clips_dir(script.id)
    d.mkdir(parents=True, exist_ok=True)
    for i, seg in missing(script):
        spec = ClipSpec.from_segment(seg)
        dest = d / f"{spec.key}.mp4"
        job_file = d / f"{spec.key}.job.json"
        if job_file.exists():
            job = higgsfield.Job(**json.loads(job_file.read_text(encoding="utf-8")))
            log(f"[clips]  segment {i + 1}: resuming {job.request_id[:8]}…")
        else:
            log(
                f"[clips]  segment {i + 1}: submitting {spec.duration}s {spec.resolution} "
                f"to {spec.model}"
            )
            job = higgsfield.submit_text_to_video(spec.model, spec.payload(), spec.idempotency_key)
            job_file.write_text(json.dumps(job.__dict__), encoding="utf-8")
        url = higgsfield.wait(job, log=log)
        higgsfield.download(url, dest)
        (d / f"{spec.key}.json").write_text(
            json.dumps({"segment": i, "request_id": job.request_id, **spec.__dict__}, indent=2),
            encoding="utf-8",
        )
        job_file.unlink(missing_ok=True)
        log(f"[clips]  segment {i + 1}: saved {dest.name}")
        out.append(dest)
    return out
