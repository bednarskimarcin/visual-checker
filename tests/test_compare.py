"""Tests for layout and comparison logic, using fake OCR boxes (no OCR needed)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vtester.compare import compare_sections, word_diff
from vtester.layout import build_sections
from vtester.ocr import TextBox
from vtester.report import build_report

W, H = 1000, 1000


def box(text, x, y, w=200, h=30):
    return TextBox(text, x, y, x + w, y + h)


def sections(*boxes):
    return build_sections(list(boxes), W, H)


def test_lines_close_together_form_one_section():
    secs = sections(box("Line one", 100, 100), box("Line two", 100, 140), box("Far away", 100, 500))
    assert [s.text for s in secs] == ["Line one\nLine two", "Far away"]


def test_close_but_unaligned_elements_stay_separate():
    # a centered button and a wider link just below it, not sharing any edge
    secs = sections(box("Sign in", 450, 400, w=100), box("Forgot your password?", 280, 440, w=200))
    assert sorted(s.text for s in secs) == ["Forgot your password?", "Sign in"]


def test_side_by_side_columns_stay_separate():
    secs = sections(box("Left", 100, 100, w=100), box("Right", 600, 100, w=100))
    assert sorted(s.text for s in secs) == ["Left", "Right"]


def test_identical():
    a = sections(box("Hello world", 100, 100), box("Sign in", 100, 400))
    b = sections(box("Hello world", 100, 100), box("Sign in", 100, 400))
    cmp = compare_sections(a, b)
    assert cmp.identical


def test_text_change_is_listed():
    a = sections(box("Enter your password here", 100, 100))
    b = sections(box("Enter your passcode here", 100, 100))
    cmp = compare_sections(a, b)
    r = cmp.results[0]
    assert r.second is not None
    assert r.text_changes == ['changed "password" -> "passcode"']
    assert not cmp.identical


def test_word_diff_missing_and_added():
    assert word_diff("a b c", "a c") == ['missing in file 2: "b"']
    assert word_diff("a c", "a b c") == ['added in file 2: "b"']


def test_moved_section():
    a = sections(box("Sign in", 100, 400))
    b = sections(box("Sign in", 100, 600))
    r = compare_sections(a, b).results[0]
    assert r.move is not None and r.move.dy_pct == 20
    assert "down" in r.move.describe()


def test_small_shift_is_ignored():
    a = sections(box("Sign in", 100, 400))
    b = sections(box("Sign in", 105, 410))
    assert compare_sections(a, b).identical


def test_missing_and_new_sections():
    a = sections(box("Keep me", 100, 100), box("Forgot password?", 100, 500))
    b = sections(box("Keep me", 100, 100), box("Create account", 100, 800))
    cmp = compare_sections(a, b)
    assert [r.first.text for r in cmp.results if r.missing] == ["Forgot password?"]
    assert [s.text for s in cmp.new_sections] == ["Create account"]


def test_order_change_detected():
    a = sections(box("First", 100, 100), box("Second", 100, 300), box("Third", 100, 500))
    b = sections(box("Second", 100, 100), box("First", 100, 300), box("Third", 100, 500))
    cmp = compare_sections(a, b)
    flagged = [r.first.text for r in cmp.results if r.order_changed]
    assert len(flagged) == 1 and flagged[0] in ("First", "Second")


def test_duplicate_texts_matched_by_position():
    a = sections(box("OK", 100, 100, w=50), box("OK", 100, 600, w=50))
    b = sections(box("OK", 100, 100, w=50), box("OK", 100, 600, w=50))
    assert compare_sections(a, b).identical


def test_report_mentions_everything():
    a = sections(box("Enter your password here", 100, 100), box("Gone soon", 100, 500))
    b = sections(box("Enter your passcode here", 100, 300), box("Brand new", 100, 800))
    text = build_report(compare_sections(a, b), Path("a.png"), Path("b.png"), (W, H), (W, H))
    for expected in ("TEXT CHANGED", "MOVED", "MISSING in file 2", "NEW in file 2", "RESULT: DIFFERENT"):
        assert expected in text
