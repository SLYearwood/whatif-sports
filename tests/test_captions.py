import pytest

from whatif_sports.assemble import captions as cap


def test_chunks_respect_word_limit_and_pauses():
    chunks = cap.chunk(
        "Super Bowl 49. One yard to go. Seattle has Marshawn Lynch... and they throw it."
    )
    assert chunks == [
        "Super Bowl 49.",
        "One yard to go.",
        "Seattle has Marshawn Lynch...",
        "and they throw it.",
    ]
    assert all(len(c.split()) <= cap.MAX_WORDS for c in chunks)


def test_no_lone_word_after_word_limit_cut():
    chunks = cap.chunk("Or just bad luck? Tell me in the comments.")
    assert chunks[-1] == "the comments."
    assert chunks[-2] == "Tell me in"


def test_timing_covers_audio_exactly_and_in_order():
    caps = cap.timed("Down four, twenty six seconds left, second and goal from the one.", 4.0)
    assert caps[0].start == 0
    assert caps[-1].end == pytest.approx(4.0)
    for a, b in zip(caps, caps[1:], strict=False):
        assert a.end == pytest.approx(b.start)
        assert a.end > a.start


def test_display_text_strips_trailing_punctuation_but_keeps_questions():
    assert cap.display_text("Seattle has Marshawn Lynch...") == "Seattle has Marshawn Lynch"
    assert cap.display_text("Down four,") == "Down four"
    assert cap.display_text("or just bad luck?") == "or just bad luck?"


def test_at_finds_active_caption():
    caps = cap.timed("One two. Three four.", 2.0)
    assert cap.at(caps, 0.0).text == "One two"
    assert cap.at(caps, 1.9).text == "Three four"
    assert cap.at(caps, 2.5) is None
