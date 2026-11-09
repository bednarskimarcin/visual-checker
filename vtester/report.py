"""Writes a comparison as a plain-text report for people to read."""
from datetime import datetime
from pathlib import Path

from .compare import Comparison
from .layout import Section

WIDTH = 78


def _short(text: str, limit: int = 60) -> str:
    one_line = " / ".join(t.strip() for t in text.splitlines() if t.strip())
    return one_line if len(one_line) <= limit else one_line[: limit - 3] + "..."


def _pos(sec: Section) -> str:
    x, y = sec.center_pct
    return f"({x:.0f}%, {y:.0f}%)"


def _section_dump(title: str, sections: list[Section]) -> list[str]:
    out = [title, "-" * WIDTH]
    if not sections:
        out.append("  (no text found)")
    for s in sections:
        out.append(f"  [{s.index}] at {_pos(s)}")
        out.extend(f"      {line}" for line in s.text.splitlines())
    return out


def build_report(cmp: Comparison, file1: Path, file2: Path,
                 size1: tuple[int, int], size2: tuple[int, int], mode: str = "text") -> str:
    res = cmp.results
    changed = sum(1 for r in res if r.text_changes)
    moved = sum(1 for r in res if r.move)
    reordered = sum(1 for r in res if r.order_changed)
    missing = sum(1 for r in res if r.missing)
    ok = sum(1 for r in res if r.ok)

    out = [
        "=" * WIDTH,
        f"VISUAL TEST REPORT - {mode} mode",
        "=" * WIDTH,
        f"File 1 (reference): {file1}  ({size1[0]}x{size1[1]})",
        f"File 2 (compared) : {file2}  ({size2[0]}x{size2[1]})",
        f"Date: {datetime.now():%Y-%m-%d %H:%M:%S}",
        "",
        f"SUMMARY: {len(res)} sections in file 1 | {ok} identical | {changed} text changed | "
        f"{moved} moved | {reordered} out of order | {missing} missing | {len(cmp.new_sections)} new in file 2",
        f"RESULT: {'IDENTICAL' if cmp.identical else 'DIFFERENT'}",
        "",
        "Positions are section centers as (x%, y%) of the image size.",
        "",
        "SECTIONS OF FILE 1 AND WHAT HAPPENED TO THEM IN FILE 2",
        "-" * WIDTH,
    ]
    if not res:
        out.append("  (no text found in file 1)")

    for r in res:
        label = f'[{r.first.index}] "{_short(r.first.text)}"'
        if r.missing:
            out.append(f"{label} - MISSING in file 2 (was at {_pos(r.first)})")
            continue
        if r.ok:
            out.append(f"{label} - OK (same text, same position)")
            continue
        tags = []
        if r.text_changes:
            tags.append("TEXT CHANGED")
        if r.move:
            tags.append("MOVED")
        if r.order_changed:
            tags.append("ORDER CHANGED")
        out.append(f"{label} - {', '.join(tags)}")
        if r.text_changes:
            out.append(f"      found in file 2 as section [{r.second.index}] (text similarity {r.score:.0%}):")
            out.extend(f"      - {c}" for c in r.text_changes)
        if r.move:
            out.append(f"      - moved from {_pos(r.first)} to {_pos(r.second)}: {r.move.describe()}")
        if r.order_changed:
            out.append(f"      - reading order changed: section {r.first.index} in file 1 "
                       f"is section {r.second.index} in file 2")

    if cmp.new_sections:
        out += ["", "SECTIONS ONLY IN FILE 2", "-" * WIDTH]
        for s in cmp.new_sections:
            out.append(f'[+] "{_short(s.text)}" - NEW in file 2 at {_pos(s)}')

    out += [""] + _section_dump("OCR TEXT - FILE 1", [r.first for r in res])
    second_sections = sorted([r.second for r in res if r.second] + cmp.new_sections, key=lambda s: s.index)
    out += [""] + _section_dump("OCR TEXT - FILE 2", second_sections)
    out.append("")
    return "\n".join(out)


def write_report(text: str, report_dir: Path, file1: Path, file2: Path, output: Path | None = None) -> Path:
    if output is None:
        report_dir.mkdir(parents=True, exist_ok=True)
        output = report_dir / f"{file1.stem}_vs_{file2.stem}_{datetime.now():%Y%m%d_%H%M%S}.txt"
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")
    return output
