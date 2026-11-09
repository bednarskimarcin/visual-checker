"""Visual mode output: the second screenshot with differences marked in red, a side-by-side
report picture, and a text report. Difference numbers are the same in all three."""
import math
import textwrap
from datetime import datetime
from pathlib import Path

import cv2
from PIL import Image, ImageDraw, ImageFont

from .visual import Box, Diff, Screen, VisualComparison

RED = (220, 20, 20)
WIDTH = 78
KIND_TEXT = {"changed": "CHANGED", "moved": "MOVED", "missing": "MISSING", "new": "NEW"}


def _font(size: int):
    for name in ("arial.ttf", "DejaVuSans.ttf", "Arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default(size)


def _to_pil(s: Screen) -> Image.Image:
    return Image.fromarray(cv2.cvtColor(s.img, cv2.COLOR_BGR2RGB))


def _pad(box: Box, pad: float, w: int, h: int) -> Box:
    return (max(0, box[0] - pad), max(0, box[1] - pad), min(w - 1, box[2] + pad), min(h - 1, box[3] + pad))


def _dashed_line(draw, p, q, width, dash):
    length = math.dist(p, q)
    if length == 0:
        return
    steps = max(1, int(length // dash))
    for i in range(0, steps, 2):
        t0, t1 = i / steps, min(1, (i + 1) / steps)
        draw.line([(p[0] + (q[0] - p[0]) * t0, p[1] + (q[1] - p[1]) * t0),
                   (p[0] + (q[0] - p[0]) * t1, p[1] + (q[1] - p[1]) * t1)], fill=RED, width=width)


def _dashed_rect(draw, box, width, dash):
    x0, y0, x1, y1 = box
    for p, q in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
        _dashed_line(draw, p, q, width, dash)


def _arrow(draw, p, q, width):
    draw.line([p, q], fill=RED, width=width)
    angle = math.atan2(q[1] - p[1], q[0] - p[0])
    size = 4 * width + 6
    left = (q[0] - size * math.cos(angle - 0.45), q[1] - size * math.sin(angle - 0.45))
    right = (q[0] - size * math.cos(angle + 0.45), q[1] - size * math.sin(angle + 0.45))
    draw.polygon([q, left, right], fill=RED)


def _label(draw, box, text, font, img_w):
    """Red tag with white text beside the box (right, else left), else above or inside it,
    so it covers as little of the screenshot as possible."""
    l, t, r, b = draw.textbbox((0, 0), text, font=font)
    tw, th = r - l + 8, b - t + 6
    if box[2] + 3 + tw <= img_w:
        x, y = box[2] + 3, box[1]
    elif box[0] - 3 - tw >= 0:
        x, y = box[0] - 3 - tw, box[1]
    else:
        x = min(max(0, box[0]), max(0, img_w - tw))
        y = box[1] - th if box[1] - th >= 0 else box[1]
    draw.rectangle((x, y, x + tw, y + th), fill=RED)
    draw.text((x + 4 - l, y + 3 - t), text, font=font, fill="white")


def _style(img: Image.Image):
    lw = max(2, round(max(img.size) / 400))
    return lw, lw * 5, _font(max(12, round(max(img.size) / 60)))


def mark_second(cmp: VisualComparison) -> Image.Image:
    """File 2 with every difference marked: solid red = what is there now,
    dashed red = where something used to be (missing or moved away)."""
    img = _to_pil(cmp.second).convert("RGBA")
    w, h = img.size
    lw, dash, font = _style(img)
    pad = lw + 2

    shade = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shade)
    for d in cmp.diffs:
        if d.kind == "missing":
            sd.rectangle(_pad(d.old_in_2, pad, w, h), fill=RED + (50,))
    img = Image.alpha_composite(img, shade).convert("RGB")
    draw = ImageDraw.Draw(img)

    for d in cmp.diffs:
        tag = f"{d.number} {d.kind}"
        if d.kind == "missing":
            box = _pad(d.old_in_2, pad, w, h)
            _dashed_rect(draw, box, lw, dash)
        elif d.kind == "moved":
            old, box = _pad(d.old_in_2, pad, w, h), _pad(d.box2, pad, w, h)
            _dashed_rect(draw, old, lw, dash)
            draw.rectangle(box, outline=RED, width=lw)
            (ox, oy), (nx, ny) = ((old[0] + old[2]) / 2, (old[1] + old[3]) / 2), ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
            _arrow(draw, (ox, oy), (nx, ny), max(1, lw - 1))
        else:
            box = _pad(d.box2, pad, w, h)
            draw.rectangle(box, outline=RED, width=lw)
            big = (d.box2[2] - d.box2[0]) * (d.box2[3] - d.box2[1]) > 0.04 * w * h
            if d.kind == "changed" and big and len(d.details) > 1:
                for spot in d.details:  # exact spots inside a bigger changed block
                    draw.rectangle(_pad(spot, 1, w, h), outline=RED, width=1)
        _label(draw, box, tag, font, w)
    return img


def mark_first(cmp: VisualComparison) -> Image.Image:
    """File 1 with the areas that differ outlined (thin, dashed) for side-by-side viewing."""
    img = _to_pil(cmp.first)
    w, h = img.size
    lw, dash, font = _style(img)
    draw = ImageDraw.Draw(img)
    for d in cmp.diffs:
        if d.kind == "new" or d.box1 is None:
            continue
        box = _pad(d.box1, lw + 2, w, h)
        _dashed_rect(draw, box, max(1, lw - 1), dash)
        _label(draw, box, str(d.number), font, w)
    return img


# ---------------------------------------------------------------- text

def _pct(s: Screen, box: Box) -> str:
    return f"({100 * (box[0] + box[2]) / 2 / s.w:.0f}%, {100 * (box[1] + box[3]) / 2 / s.h:.0f}%)"


def _size(box: Box) -> str:
    return f"{box[2] - box[0]:.0f}x{box[3] - box[1]:.0f} px"


def _move_text(shift) -> str:
    dx_pct, dy_pct, dx_px, dy_px = shift
    parts = []
    if abs(dy_pct) >= 0.05:
        parts.append(f"{abs(dy_pct):.1f}% {'down' if dy_pct > 0 else 'up'} ({abs(dy_px):.0f} px)")
    if abs(dx_pct) >= 0.05:
        parts.append(f"{abs(dx_pct):.1f}% {'right' if dx_pct > 0 else 'left'} ({abs(dx_px):.0f} px)")
    return ", ".join(parts) or "no shift"


def describe(d: Diff, cmp: VisualComparison) -> str:
    s1, s2 = cmp.first, cmp.second
    if d.kind == "moved":
        return (f"{d.number}. MOVED - block {_size(d.box2)} moved from {_pct(s1, d.box1)} "
                f"to {_pct(s2, d.box2)}: {_move_text(d.shift)}")
    if d.kind == "missing":
        return f"{d.number}. MISSING - block {_size(d.box1)} at {_pct(s1, d.box1)} is not in file 2"
    if d.kind == "new":
        return f"{d.number}. NEW - block {_size(d.box2)} at {_pct(s2, d.box2)} is only in file 2"
    size = _size(d.box1) if _size(d.box1) == _size(d.box2) else f"{_size(d.box1)} -> {_size(d.box2)}"
    return (f"{d.number}. CHANGED - block at {_pct(s2, d.box2)} looks different "
            f"({d.score:.0%} of its content differs), size {size}")


def summary(cmp: VisualComparison) -> str:
    count = {k: sum(1 for d in cmp.diffs if d.kind == k) for k in KIND_TEXT}
    return (f"{len(cmp.first.blocks)} blocks in file 1, {len(cmp.second.blocks)} in file 2 | "
            f"{cmp.unchanged} unchanged | {count['changed']} changed | {count['moved']} moved | "
            f"{count['missing']} missing | {count['new']} new")


def build_text_report(cmp: VisualComparison, marked: Path, picture: Path) -> str:
    s1, s2 = cmp.first, cmp.second
    out = [
        "=" * WIDTH,
        "VISUAL TEST REPORT - visual mode (no OCR, compares blocks by look and position)",
        "=" * WIDTH,
        f"File 1 (reference): {s1.path}  ({s1.w}x{s1.h})",
        f"File 2 (compared) : {s2.path}  ({s2.w}x{s2.h})",
        f"Date: {datetime.now():%Y-%m-%d %H:%M:%S}",
        "",
        f"SUMMARY: {summary(cmp)}",
        f"RESULT: {'IDENTICAL' if cmp.identical else 'DIFFERENT'}",
        "",
        f"Marked screenshot: {marked}",
        f"Report picture   : {picture}",
        "",
        "Positions are block centers as (x%, y%) of the image size.",
        "Numbers match the red labels on the pictures.",
        "",
        "DIFFERENCES",
        "-" * WIDTH,
    ]
    out += [describe(d, cmp) for d in cmp.diffs] or ["  (none)"]
    for title, s in (("BLOCKS FOUND - FILE 1", s1), ("BLOCKS FOUND - FILE 2", s2)):
        out += ["", title, "-" * WIDTH]
        out += [f"  [{b.index}] {_size(b.box)} at {_pct(s, b.box)}" for b in s.blocks] or ["  (no blocks found)"]
    out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------- report picture

def _fit(img: Image.Image, max_w: int, max_h: int) -> Image.Image:
    scale = min(1.0, max_w / img.width, max_h / img.height)
    if scale < 1:
        img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    return img


def build_report_picture(cmp: VisualComparison, marked2: Image.Image) -> Image.Image:
    left = _fit(mark_first(cmp), 1000, 1400)
    right = _fit(marked2, 1000, 1400)
    margin, gap = 24, 24
    title_f, text_f, small_f = _font(26), _font(17), _font(15)
    width = max(margin * 2 + left.width + gap + right.width, 900)
    wrap = max(40, (width - 2 * margin) // 9)

    result = "IDENTICAL" if cmp.identical else "DIFFERENT"
    header = [
        (f"Visual test - {result}", title_f, (20, 130, 20) if cmp.identical else RED),
        (f"File 1: {cmp.first.path.name}   |   File 2: {cmp.second.path.name}", text_f, (40, 40, 40)),
        (summary(cmp), text_f, (40, 40, 40)),
        ("Solid red = how it is now (changed / new / moved here).  "
         "Dashed red = where it used to be (missing / moved away).", small_f, (90, 90, 90)),
    ]
    items = [line for d in cmp.diffs for line in textwrap.wrap(describe(d, cmp), wrap, subsequent_indent="    ")]
    if not items:
        items = ["No differences found."]

    line_h = 26
    header_h = margin + 40 + line_h * (len(header) - 1) + 12
    caption_h = 28
    panels_h = max(left.height, right.height)
    list_h = 40 + line_h * len(items) + margin
    canvas = Image.new("RGB", (width, header_h + caption_h + panels_h + list_h), "white")
    draw = ImageDraw.Draw(canvas)

    y = margin
    for text, font, color in header:
        draw.text((margin, y), text, font=font, fill=color)
        y += 40 if font is title_f else line_h
    y = header_h

    x2 = margin + left.width + gap
    draw.text((margin, y), "File 1 (reference)", font=text_f, fill=(40, 40, 40))
    draw.text((x2, y), "File 2 (compared) - differences in red", font=text_f, fill=RED)
    y += caption_h
    for x, panel in ((margin, left), (x2, right)):
        canvas.paste(panel, (x, y))
        draw.rectangle((x - 1, y - 1, x + panel.width, y + panel.height), outline=(180, 180, 180))
    y += panels_h + 20

    draw.text((margin, y), "Differences", font=text_f, fill=(40, 40, 40))
    y += 30
    for line in items:
        draw.text((margin, y), line, font=small_f, fill=(30, 30, 30))
        y += line_h
    return canvas


def write_visual_report(cmp: VisualComparison, report_dir: Path, output: Path | None = None) -> tuple[Path, Path, Path]:
    """Write <name>.txt, <name>_marked.png and <name>_report.png. Returns their paths."""
    if output is None:
        report_dir.mkdir(parents=True, exist_ok=True)
        stem = f"{cmp.first.path.stem}_vs_{cmp.second.path.stem}_{datetime.now():%Y%m%d_%H%M%S}"
        text_path = report_dir / f"{stem}.txt"
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        text_path = output
    marked_path = text_path.with_name(f"{text_path.stem}_marked.png")
    picture_path = text_path.with_name(f"{text_path.stem}_report.png")

    marked = mark_second(cmp)
    marked.save(marked_path)
    build_report_picture(cmp, marked).save(picture_path)
    text_path.write_text(build_text_report(cmp, marked_path, picture_path), encoding="utf-8")
    return text_path, marked_path, picture_path
