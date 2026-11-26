"""AI clip pipeline. Higgsfield HTTP is mocked: no network, nothing billed."""

import json
import subprocess

import pytest
from pydantic import ValidationError

from whatif_sports import config
from whatif_sports.clips import higgsfield, store
from whatif_sports.clips.reader import ClipReader
from whatif_sports.script import load_script
from whatif_sports.script.schema import AIClipSegment
from whatif_sports.visuals import Ctx, render_frame

PROMPT = "Night stadium, anonymous player in a navy uniform celebrates as confetti falls."


def _has_ffmpeg() -> bool:
    try:
        config.ffmpeg()
        return True
    except FileNotFoundError:
        return False


needs_ffmpeg = pytest.mark.skipif(not _has_ffmpeg(), reason="ffmpeg not installed")


def _seg(**kw) -> AIClipSegment:
    return AIClipSegment(**{"type": "ai_clip", "prompt": PROMPT, "narration": "x", **kw})


def test_prompt_rejects_logos():
    with pytest.raises(ValidationError):
        _seg(prompt="Player with the team logo on his helmet scores a touchdown")


def test_spec_adds_safety_suffix_and_vertical_format():
    spec = store.ClipSpec.from_segment(_seg())
    p = spec.payload()
    assert p["aspect_ratio"] == "9:16"
    assert p["generate_audio"] is False
    assert "no recognizable faces" in p["prompt"]
    assert "no logos" in p["prompt"]


def test_key_and_idempotency_are_stable_and_prompt_sensitive():
    a, b = store.ClipSpec.from_segment(_seg()), store.ClipSpec.from_segment(_seg())
    assert a.key == b.key and a.idempotency_key == b.idempotency_key
    c = store.ClipSpec.from_segment(_seg(duration=6))
    assert c.key != a.key


@pytest.fixture
def creds(monkeypatch):
    monkeypatch.delenv("HIGGSFIELD_API_KEY", raising=False)
    monkeypatch.setenv("HIGGSFIELD_KEY_ID", "id-not-real")
    monkeypatch.setenv("HIGGSFIELD_KEY_SECRET", "secret-not-real")


def test_missing_credentials(monkeypatch):
    for k in ("HIGGSFIELD_API_KEY", "HIGGSFIELD_KEY_ID", "HIGGSFIELD_KEY_SECRET"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(higgsfield.HiggsfieldError, match="HIGGSFIELD_API_KEY"):
        higgsfield._auth()


def test_auth_header_format(creds):
    assert higgsfield._auth() == "Key id-not-real:secret-not-real"


def test_single_api_key_is_used_as_is(monkeypatch):
    monkeypatch.setenv("HIGGSFIELD_API_KEY", "single-key-not-real")
    assert higgsfield._auth() == "Key single-key-not-real"
    monkeypatch.setenv("HIGGSFIELD_API_KEY", "Key already-prefixed")
    assert higgsfield._auth() == "Key already-prefixed"


@pytest.mark.parametrize(
    ("error", "ok"),
    [
        ("Higgsfield HTTP 404: Not found", True),
        ("Higgsfield rejected the API credentials (401).", False),
    ],
)
def test_check_auth_reads_404_as_accepted(monkeypatch, error, ok):
    def fake_request(*a, **k):
        raise higgsfield.HiggsfieldError(error)

    monkeypatch.setattr(higgsfield, "_request", fake_request)
    if ok:
        assert "accepted" in higgsfield.check_auth()
    else:
        with pytest.raises(higgsfield.HiggsfieldError, match="rejected"):
            higgsfield.check_auth()


@pytest.fixture
def fake_api(monkeypatch, creds, tmp_path):
    calls = []
    statuses = iter(["queued", "in_progress", "completed"])

    def fake_request(method, url, payload=None, headers=None, timeout=60):
        calls.append({"method": method, "url": url, "payload": payload, "headers": headers})
        if method == "POST":
            return json.dumps(
                {
                    "status": "queued",
                    "request_id": "req-123",
                    "status_url": "https://api.higgsfield.ai/requests/req-123/status",
                }
            ).encode()
        st = next(statuses)
        body = {"status": st}
        if st == "completed":
            body["video"] = {"url": "https://cdn.example/clip.mp4"}
        return json.dumps(body).encode()

    def fake_download(url, dest, timeout=300):
        calls.append({"method": "DOWNLOAD", "url": url})
        dest.write_bytes(b"fake mp4")

    monkeypatch.setattr(higgsfield, "_request", fake_request)
    monkeypatch.setattr(higgsfield, "download", fake_download)
    monkeypatch.setattr(higgsfield.time, "sleep", lambda s: None)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    return calls


def test_generate_submits_polls_downloads_and_caches(fake_api, tmp_path):
    script = load_script("seahawks-xlix-run")
    assert len(store.missing(script)) == 1
    files = store.generate(script, log=lambda *_: None)
    assert len(files) == 1 and files[0].exists()

    post = fake_api[0]
    assert post["url"] == "https://api.higgsfield.ai/bytedance/seedance-2.0/text-to-video"
    assert post["payload"]["aspect_ratio"] == "9:16"
    assert post["headers"]["Idempotency-Key"]
    assert [c["method"] for c in fake_api] == ["POST", "GET", "GET", "GET", "DOWNLOAD"]
    assert not list((tmp_path / script.id / "clips").glob("*.job.json"))

    assert store.missing(script) == []
    assert store.generate(script, log=lambda *_: None) == []
    assert len(fake_api) == 5, "cached clips must not be regenerated"


def test_resume_uses_saved_job_instead_of_resubmitting(fake_api, tmp_path):
    script = load_script("seahawks-xlix-run")
    _, seg = store.clip_segments(script)[0]
    spec = store.ClipSpec.from_segment(seg)
    d = tmp_path / script.id / "clips"
    d.mkdir(parents=True)
    (d / f"{spec.key}.job.json").write_text(
        json.dumps(
            {
                "request_id": "req-123",
                "status_url": "https://api.higgsfield.ai/requests/req-123/status",
            }
        )
    )
    store.generate(script, log=lambda *_: None)
    assert "POST" not in [c["method"] for c in fake_api]


def test_moderation_rejection_is_reported(monkeypatch, creds):
    monkeypatch.setattr(
        higgsfield, "_request", lambda *a, **k: json.dumps({"status": "nsfw"}).encode()
    )
    with pytest.raises(higgsfield.HiggsfieldError, match="moderation"):
        higgsfield.wait(
            higgsfield.Job("r", "https://x/status"), log=lambda *_: None, sleep=lambda s: None
        )


def test_placeholder_renders_without_clip():
    img = render_frame(_seg(text="Back-to-back"), Ctx(), 1.0, 4.0, caption="back to back")
    assert img.size == (config.WIDTH, config.HEIGHT)


@needs_ffmpeg
def test_clip_reader_scales_to_vertical_and_holds_last_frame(tmp_path):
    clip = tmp_path / "c.mp4"
    subprocess.run(
        [
            config.ffmpeg(),
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=640x360:rate=30:duration=0.5",
            "-pix_fmt",
            "yuv420p",
            str(clip),
        ],
        check=True,
    )
    r = ClipReader(clip)
    frames = [r.next() for _ in range(25)]  # clip has 15 frames
    r.close()
    assert frames[0].size == (config.WIDTH, config.HEIGHT)
    assert frames[-1].tobytes() == frames[-2].tobytes()
    img = render_frame(_seg(), Ctx(), 0.5, 3.0, source=frames[3])
    assert img.size == (config.WIDTH, config.HEIGHT)
