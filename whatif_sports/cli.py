"""Command line entry point: `whatif <command>`."""

from __future__ import annotations

import argparse
import sys

from whatif_sports import config


def _cmd_validate(args: argparse.Namespace) -> int:
    from whatif_sports.script import load_script
    from whatif_sports.visuals.plays import PLAYS

    s = load_script(args.script)
    bad = [
        seg.play
        for seg in s.segments
        if seg.type in ("play_diagram", "play_scene") and seg.play not in PLAYS
    ]
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
    render(load_script(args.script), Voice.from_env(args.voice))
    return 0


def _cmd_voices(args: argparse.Namespace) -> int:
    from whatif_sports.voice import elevenlabs

    for v in elevenlabs.list_voices():
        print(f"{v['voice_id']}  {v.get('category', ''):<12} {v.get('name', '')}")
    print("\nPut the one you want in .env as ELEVENLABS_VOICE_ID=<id>")
    return 0


def _cmd_clips(args: argparse.Namespace) -> int:
    from whatif_sports.clips import store
    from whatif_sports.script import load_script

    s = load_script(args.script)
    todo = store.missing(s)
    have = len(store.clip_segments(s)) - len(todo)
    if not todo:
        print(f"All {have} AI clip(s) for {s.id} are already generated.")
        return 0
    seconds = sum(seg.duration for _, seg in todo)
    print(f"{len(todo)} clip(s) to generate ({seconds}s of video total), {have} already cached:")
    for i, seg in todo:
        print(f"  segment {i + 1}: {seg.duration}s {seg.resolution}  {seg.prompt[:70]}...")
    if not args.yes:
        print("\nThis is billed by Higgsfield. Re-run with --yes to generate.")
        return 0
    store.generate(s)
    print(f"Done. Re-render with: whatif render {s.id}")
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
    r.add_argument("--voice", choices=["elevenlabs", "flite", "sapi"], help="override WHATIF_TTS")
    r.set_defaults(func=_cmd_render)

    vs = sub.add_parser("voices", help="list the voices on your ElevenLabs account")
    vs.set_defaults(func=_cmd_voices)

    c = sub.add_parser("clips", help="generate missing AI clips for a script (billed)")
    c.add_argument("script", help="item id or path to a script YAML")
    c.add_argument("--yes", action="store_true", help="actually submit (costs money)")
    c.set_defaults(func=_cmd_clips)

    from whatif_sports.clips import HiggsfieldError
    from whatif_sports.voice import ElevenLabsError

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (FileNotFoundError, ValueError, ElevenLabsError, HiggsfieldError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
