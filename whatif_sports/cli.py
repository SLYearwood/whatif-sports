"""Command line entry point: `whatif <command>`."""

from __future__ import annotations

import argparse
import sys

from whatif_sports import config


def _cmd_validate(args: argparse.Namespace) -> int:
    from whatif_sports.script import load_script
    from whatif_sports.visuals.plays import PLAYS

    s = load_script(args.script)
    bad = [seg.play for seg in s.segments if seg.type == "play_diagram" and seg.play not in PLAYS]
    if bad:
        print(f"Unknown play(s): {', '.join(bad)}. Known: {', '.join(sorted(PLAYS))}")
        return 1
    print(
        f"OK  {s.id}: {len(s.segments)} segments, {s.word_count()} words, {len(s.sources)} sources"
    )
    return 0


def _cmd_render(args: argparse.Namespace) -> int:
    from whatif_sports.assemble import render
    from whatif_sports.script import load_script
    from whatif_sports.voice import Voice

    if _cmd_validate(args):
        return 1
    voice = Voice.from_env()
    if args.voice:
        voice = Voice(args.voice, "" if args.voice == "sapi" else "rms")
    render(load_script(args.script), voice)
    return 0


def main(argv: list[str] | None = None) -> int:
    config.load_dotenv()
    parser = argparse.ArgumentParser(prog="whatif", description="Sports 'What If' Shorts pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    v = sub.add_parser("validate", help="check a script YAML against the schema")
    v.add_argument("script", help="item id or path to a script YAML")
    v.set_defaults(func=_cmd_validate)

    r = sub.add_parser("render", help="render a script to data/<id>/render/<id>.mp4")
    r.add_argument("script", help="item id or path to a script YAML")
    r.add_argument("--voice", choices=["flite", "sapi"], help="override WHATIF_TTS")
    r.set_defaults(func=_cmd_render)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (FileNotFoundError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
