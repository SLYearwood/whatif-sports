"""Pydantic models for the script YAML (the contract between pipeline modules)."""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    v = value.lstrip("#")
    return int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)


def _check_hex(v: str | None) -> str | None:
    if v is not None and not _HEX.match(v):
        raise ValueError(f"expected a color like '#69BE28', got {v!r}")
    return v


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Segment(_Model):
    narration: str = Field(min_length=1)


class TitleSegment(_Segment):
    type: Literal["title"]
    text: str


class StatSegment(_Segment):
    type: Literal["stat"]
    big: str = Field(description="Headline number, e.g. '102 yds'. Leading number counts up.")
    label: str


class ScoreTeam(_Model):
    name: str
    score: int
    color: str = "#FFFFFF"

    _hex = field_validator("color")(_check_hex)


class ScoreboardSegment(_Segment):
    type: Literal["scoreboard"]
    teams: list[ScoreTeam] = Field(min_length=2, max_length=2)
    clock: str = ""
    period: str = ""
    situation: str = ""


class PlayDiagramSegment(_Segment):
    type: Literal["play_diagram"]
    play: str = Field(description="Named play from visuals/plays.py")
    label: str = ""


class TeamKit(_Model):
    """Uniform colors for stylized players. Colors only: no numbers, names, or logos."""

    jersey: str
    pants: str = "#E1E4EC"
    helmet: str | None = None
    trim: str = "#F5F7FA"

    _hex = field_validator("jersey", "pants", "helmet", "trim")(_check_hex)


class PlaySceneSegment(_Segment):
    """Broadcast-angle animation of a named play with stylized players."""

    type: Literal["play_scene"]
    play: str = Field(description="Named play from visuals/plays.py")
    label: str = ""
    offense: TeamKit
    defense: TeamKit


class MomentSegment(_Segment):
    """One big stylized player reacting (celebrating, dejected...) with a headline."""

    type: Literal["moment"]
    pose: Literal["celebrate", "dejected", "dive", "run"]
    kit: TeamKit
    text: str = ""
    year: int | str | None = None


class AIClipSegment(_Segment):
    """A short AI-generated video shot (Higgsfield). Generated only via `whatif clips`.

    Prompts must describe anonymous, fictional people; the generator also gets a suffix
    forbidding recognizable faces, logos, numbers and text. Reviewers check the result.
    """

    type: Literal["ai_clip"]
    prompt: str = Field(min_length=20)
    model: str = "bytedance/seedance-2.0"
    duration: int = Field(default=5, ge=4, le=15)
    resolution: Literal["480p", "720p", "1080p"] = "720p"
    text: str = ""

    @field_validator("prompt")
    @classmethod
    def _no_marks(cls, v: str) -> str:
        banned = ("logo", "trademark", "jersey number", "nfl shield", "real face")
        hit = [b for b in banned if b in v.lower()]
        if hit:
            raise ValueError(f"prompt must not ask for {', '.join(hit)}")
        return v


class TimelineEvent(_Model):
    year: int | str
    text: str


class TimelineSegment(_Segment):
    type: Literal["timeline"]
    title: str = ""
    events: list[TimelineEvent] = Field(min_length=1, max_length=5)


class OutroSegment(_Segment):
    type: Literal["outro"]
    text: str


Segment = Annotated[
    TitleSegment
    | StatSegment
    | ScoreboardSegment
    | PlayDiagramSegment
    | PlaySceneSegment
    | MomentSegment
    | AIClipSegment
    | TimelineSegment
    | OutroSegment,
    Field(discriminator="type"),
]


class Script(_Model):
    id: str
    title: str
    sport: Literal["nfl", "nba", "mlb", "nhl", "ncaaf", "ncaab", "soccer", "other"]
    hook: str
    accent: str | None = Field(default=None, description="Team accent color, e.g. '#69BE28'")
    sources: list[str] = Field(min_length=1)
    segments: list[Segment] = Field(min_length=2)

    _hex = field_validator("accent")(_check_hex)

    @field_validator("id")
    @classmethod
    def _slug(cls, v: str) -> str:
        if not _ID.match(v):
            raise ValueError("id must be a lowercase slug like 'seahawks-xlix-run'")
        return v

    @field_validator("segments")
    @classmethod
    def _bookends(cls, v: list) -> list:
        if v[0].type != "title":
            raise ValueError("first segment must be a 'title' (the hook goes in the first 2s)")
        return v

    def word_count(self) -> int:
        return sum(len(s.narration.split()) for s in self.segments)
