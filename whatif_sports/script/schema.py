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
