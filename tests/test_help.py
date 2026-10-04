"""Help stays short; long disclaimer lives there."""

from bot import render


def test_help_at_most_eight_content_lines():
    text = render.help_text()
    lines = [ln for ln in text.splitlines() if ln.strip()]
    # title + 5 bullets + channel link + disclaimer blockquote = 8
    assert len(lines) <= 8
    assert "Closing today" in text
    assert "Fits" in text
    assert "Too early" in text
    assert "Skip" in text
    assert "⚠️" in text
    assert "<blockquote expandable>" in text
    assert "not investment advice" in text.lower()
