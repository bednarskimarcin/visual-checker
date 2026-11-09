"""Tests for visual mode (block detection and comparison) on drawn images - no OCR involved."""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vtester.config import Config
from vtester.visual import compare_screens, load_screen
from vtester.visual_report import write_visual_report

CFG = Config(input_dir=Path("."))
SIZE = (600, 400)


def image(tmp_path, name, shapes, size=SIZE, noise=0):
    """shapes: list of (kind, box, color); kind = rect (filled), frame (outline), bar (text-like stripes)."""
    img = Image.new("RGB", size, "white")
    d = ImageDraw.Draw(img)
    for kind, box, color in shapes:
        if kind == "rect":
            d.rectangle(box, fill=color)
        elif kind == "frame":
            d.rectangle(box, outline=color, width=2)
        elif kind == "bar":  # imitates a line of text: short vertical strokes
            x0, y0, x1, y1 = box
            for x in range(x0, x1, 6):
                d.rectangle((x, y0, x + 2, y1), fill=color)
    if noise:
        rng = np.random.default_rng(0)
        arr = np.asarray(img).astype(np.int16) + rng.integers(-noise, noise + 1, (size[1], size[0], 3))
        img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    path = tmp_path / f"{name}.png"
    img.save(path)
    return path


def compare(tmp_path, shapes1, shapes2, **kw):
    p1 = image(tmp_path, "a", shapes1, **kw.get("img1", {}))
    p2 = image(tmp_path, "b", shapes2, **kw.get("img2", {}))
    return compare_screens(load_screen(p1, CFG), load_screen(p2, CFG), CFG)


BUTTON = ("rect", (250, 200, 350, 240), "#1f6feb")
TITLE = ("bar", (100, 40, 400, 60), "black")
ICON = ("rect", (30, 30, 70, 70), "#f0883e")
PAGE = [TITLE, BUTTON, ICON]


def kinds(cmp):
    return sorted(d.kind for d in cmp.diffs)


def test_identical(tmp_path):
    assert compare(tmp_path, PAGE, PAGE).identical


def test_small_color_noise_is_tolerated(tmp_path):
    assert compare(tmp_path, PAGE, PAGE, img2={"noise": 12}).identical


def test_small_shift_is_tolerated(tmp_path):
    shifted = [TITLE, ("rect", (253, 203, 353, 243), "#1f6feb"), ICON]
    assert compare(tmp_path, PAGE, shifted).identical


def test_moved_block(tmp_path):
    moved = [TITLE, ("rect", (250, 300, 350, 340), "#1f6feb"), ICON]
    cmp = compare(tmp_path, PAGE, moved)
    assert kinds(cmp) == ["moved"]
    assert cmp.diffs[0].shift[1] == 25.0  # 100 px down = 25% of 400


def test_color_change_is_changed(tmp_path):
    green = [TITLE, ("rect", (250, 200, 350, 240), "#2da44e"), ICON]
    assert kinds(compare(tmp_path, PAGE, green)) == ["changed"]


def test_missing_and_new(tmp_path):
    other = [TITLE, BUTTON, ("rect", (500, 300, 560, 360), "#8250df")]
    assert kinds(compare(tmp_path, PAGE, other)) == ["missing", "new"]


def test_move_next_to_neighbor_is_still_a_move(tmp_path):
    # the button ends up 5 px above a link, so both form one block in file 2
    link = ("bar", (260, 320, 340, 332), "black")
    before = [TITLE, BUTTON, link]
    after = [TITLE, ("rect", (250, 275, 350, 315), "#1f6feb"), link]
    assert kinds(compare(tmp_path, before, after)) == ["moved"]


def test_different_image_sizes(tmp_path):
    big = [(k, tuple(v * 2 for v in box), c) for k, box, c in [ICON, BUTTON]]
    cmp = compare(tmp_path, [ICON, BUTTON], big, img2={"size": (1200, 800)})
    assert cmp.identical


def test_change_inside_large_container_is_reported_once(tmp_path):
    card = ("frame", (20, 20, 580, 380), "#8c959f")
    before = [card, TITLE, BUTTON, ICON]
    after = [card, TITLE, ("rect", (250, 200, 350, 240), "#2da44e"), ICON]
    cmp = compare(tmp_path, before, after)
    assert kinds(cmp) == ["changed"]
    assert cmp.diffs[0].box2[2] - cmp.diffs[0].box2[0] < 150  # the button, not the card


def test_writes_text_and_pictures(tmp_path):
    moved = [TITLE, ("rect", (250, 300, 350, 340), "#1f6feb")]
    cmp = compare(tmp_path, PAGE, moved)
    paths = write_visual_report(cmp, tmp_path, tmp_path / "out" / "r.txt")
    text = paths[0].read_text(encoding="utf-8")
    assert "MOVED" in text and "MISSING" in text and "RESULT: DIFFERENT" in text
    for p in paths[1:]:
        with Image.open(p) as img:
            assert img.width > 0
    with Image.open(paths[1]) as marked:
        assert marked.size == SIZE  # marks are drawn on file 2 at its own size
