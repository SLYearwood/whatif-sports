"""Higgsfield API client (stdlib HTTP, no SDK). Docs: https://docs.higgsfield.ai

Lifecycle: POST /<model>/text-to-video -> {request_id, status_url} -> poll status_url until
completed (video.url) or failed/nsfw/canceled -> download the MP4 (URLs expire).

Credentials come from HIGGSFIELD_API_KEY (or HIGGSFIELD_KEY_ID + HIGGSFIELD_KEY_SECRET)
and are never logged.
"""

from __future__ import annotations

import json
import os
import random
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

API_ROOT = "https://api.higgsfield.ai"
TERMINAL_FAIL = {"failed", "nsfw", "canceled"}
MAX_RETRIES = 5


class HiggsfieldError(RuntimeError):
    pass


@dataclass(frozen=True)
class Job:
    request_id: str
    status_url: str


def _auth() -> str:
    """Authorization header value.

    The docs specify `Key <KEY_ID>:<KEY_SECRET>`. Accepted from .env as either:
      HIGGSFIELD_API_KEY=<the single string the Console gives you>  (used as-is), or
      HIGGSFIELD_KEY_ID + HIGGSFIELD_KEY_SECRET (joined with a colon).
    Run `whatif clips --check-auth` to confirm Higgsfield accepts it (free).
    """
    single = os.environ.get("HIGGSFIELD_API_KEY", "").strip()
    if single:
        return single if single.startswith("Key ") else f"Key {single}"
    key_id = os.environ.get("HIGGSFIELD_KEY_ID", "").strip()
    secret = os.environ.get("HIGGSFIELD_KEY_SECRET", "").strip()
    if key_id and secret:
        return f"Key {key_id}:{secret}"
    raise HiggsfieldError(
        "No Higgsfield key found. Put the key from console.higgsfield.ai in .env as "
        "HIGGSFIELD_API_KEY=... (or HIGGSFIELD_KEY_ID + HIGGSFIELD_KEY_SECRET if it gives two)."
    )


def check_auth() -> str:
    """Free credential check: ask for the status of a request id that can't exist.

    401 means the key was rejected; 404 means the key was accepted. Nothing is created
    or billed either way.
    """
    url = f"{API_ROOT}/requests/00000000-0000-0000-0000-000000000000/status"
    try:
        _request("GET", url, timeout=30)
    except HiggsfieldError as e:
        msg = str(e)
        if "401" in msg:
            raise HiggsfieldError(
                "Higgsfield rejected this key (401). If the Console shows a key ID and a "
                "secret, set HIGGSFIELD_KEY_ID and HIGGSFIELD_KEY_SECRET instead; if it shows "
                "one string, paste the whole string into HIGGSFIELD_API_KEY."
            ) from None
        if "403" in msg:
            raise HiggsfieldError(f"Key accepted but not usable: {msg}") from None
        if "404" in msg or "not found" in msg.lower():
            return "Key accepted by Higgsfield."
        raise
    return "Key accepted by Higgsfield."


def _request(
    method: str,
    url: str,
    payload: dict | None = None,
    headers: dict | None = None,
    timeout: float = 60,
) -> bytes:
    """One HTTP call with retries on 429/5xx/network errors. Replaced in tests."""
    body = json.dumps(payload).encode() if payload is not None else None
    hdrs = {"Authorization": _auth(), "Accept": "application/json"}
    if body is not None:
        hdrs["Content-Type"] = "application/json"
    hdrs.update(headers or {})
    for attempt in range(MAX_RETRIES + 1):
        req = urllib.request.Request(url, data=body, method=method, headers=hdrs)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            detail = _detail(e)
            if e.code in (429, 500, 502, 503, 504) and attempt < MAX_RETRIES:
                retry_after = e.headers.get("Retry-After") if e.headers else None
                wait = float(retry_after) if retry_after else min(30, 2**attempt * 2)
                time.sleep(wait + random.uniform(0, 1))
                continue
            if e.code == 401:
                raise HiggsfieldError("Higgsfield rejected the API credentials (401).") from None
            raise HiggsfieldError(f"Higgsfield HTTP {e.code}: {detail}") from None
        except urllib.error.URLError as e:
            if attempt < MAX_RETRIES:
                time.sleep(2**attempt)
                continue
            raise HiggsfieldError(f"Could not reach Higgsfield: {e.reason}") from None
    raise HiggsfieldError("unreachable")  # pragma: no cover


def _detail(e: urllib.error.HTTPError) -> str:
    try:
        data = json.loads(e.read().decode(errors="replace"))
        d = data.get("detail", data)
        return str(d.get("message", d)) if isinstance(d, dict) else str(d)
    except Exception:
        return e.reason or ""


def submit_text_to_video(model: str, payload: dict, idempotency_key: str) -> Job:
    url = f"{API_ROOT}/{model.strip('/')}/text-to-video"
    data = json.loads(_request("POST", url, payload, {"Idempotency-Key": idempotency_key}))
    try:
        rid = data["request_id"]
    except KeyError:
        raise HiggsfieldError(f"Unexpected submit response: {data}") from None
    return Job(rid, data.get("status_url") or f"{API_ROOT}/requests/{rid}/status")


def wait(job: Job, timeout_s: float = 900, log=print, sleep=time.sleep) -> str:
    """Poll until completed; returns the output video URL."""
    delay, waited, last = 2.0, 0.0, ""
    while waited < timeout_s:
        data = json.loads(_request("GET", job.status_url, timeout=30))
        status = data.get("status", "")
        if status != last:
            log(f"[clips]  {job.request_id[:8]}… {status}")
            last = status
        if status == "completed":
            url = (data.get("video") or {}).get("url")
            if not url:
                raise HiggsfieldError(f"Completed without a video URL: {data}")
            return url
        if status in TERMINAL_FAIL:
            why = data.get("error") or (
                "rejected by content moderation; rephrase the prompt" if status == "nsfw" else ""
            )
            raise HiggsfieldError(f"Generation {status}: {why}".rstrip(": "))
        pause = delay + random.uniform(0, 0.5)
        sleep(pause)
        waited += pause
        delay = min(10.0, delay * 1.5)
    raise HiggsfieldError(f"Timed out after {timeout_s:.0f}s waiting for {job.request_id}")


def download(url: str, dest: Path, timeout: float = 300) -> None:
    """Fetch the finished MP4. No credentials are sent to the file host."""
    tmp = dest.with_suffix(".part")
    req = urllib.request.Request(url, headers={"User-Agent": "whatif-sports"})
    with urllib.request.urlopen(req, timeout=timeout) as resp, tmp.open("wb") as f:
        while chunk := resp.read(1 << 16):
            f.write(chunk)
    tmp.replace(dest)
