"""Groups OCR boxes into lines, and lines into sections (blocks of text that belong together)."""
from dataclasses import dataclass, field

from .ocr import TextBox


@dataclass
class Line:
    boxes: list[TextBox]

    @property
    def text(self) -> str:
        return " ".join(b.text for b in self.boxes)

    @property
    def x0(self): return min(b.x0 for b in self.boxes)
    @property
    def x1(self): return max(b.x1 for b in self.boxes)
    @property
    def y0(self): return min(b.y0 for b in self.boxes)
    @property
    def y1(self): return max(b.y1 for b in self.boxes)
    @property
    def height(self): return self.y1 - self.y0


@dataclass
class Section:
    lines: list[Line] = field(default_factory=list)
    index: int = 0              # 1-based number in reading order
    img_w: int = 1
    img_h: int = 1

    @property
    def text(self) -> str:
        return "\n".join(l.text for l in self.lines)

    @property
    def x0(self): return min(l.x0 for l in self.lines)
    @property
    def x1(self): return max(l.x1 for l in self.lines)
    @property
    def y0(self): return min(l.y0 for l in self.lines)
    @property
    def y1(self): return max(l.y1 for l in self.lines)

    @property
    def center_px(self) -> tuple[float, float]:
        return (self.x0 + self.x1) / 2, (self.y0 + self.y1) / 2

    @property
    def center_pct(self) -> tuple[float, float]:
        cx, cy = self.center_px
        return 100 * cx / self.img_w, 100 * cy / self.img_h


def group_lines(boxes: list[TextBox], line_tolerance: float = 0.5, column_gap: float = 2.5) -> list[Line]:
    """Merge boxes that share a vertical center into lines. Boxes on the same row but far
    apart horizontally (more than column_gap x line height) become separate lines,
    so side-by-side columns or buttons are not glued together."""
    rows: list[list[TextBox]] = []
    for box in sorted(boxes, key=lambda b: b.cy):
        for row in rows:
            ref_h = max(max(b.height for b in row), box.height)
            row_cy = sum(b.cy for b in row) / len(row)
            if abs(box.cy - row_cy) <= line_tolerance * ref_h:
                row.append(box)
                break
        else:
            rows.append([box])

    lines: list[Line] = []
    for row in rows:
        row.sort(key=lambda b: b.x0)
        current = [row[0]]
        for box in row[1:]:
            h = max(box.height, max(b.height for b in current))
            if box.x0 - max(b.x1 for b in current) > column_gap * h:
                lines.append(Line(current))
                current = [box]
            else:
                current.append(box)
        lines.append(Line(current))
    lines.sort(key=lambda l: (l.y0, l.x0))
    return lines


def _belongs_together(last: Line, line: Line, section_gap: float) -> bool:
    """Two lines are part of one text block (paragraph, multi-line label) when they are
    vertically close, have similar text height and share an alignment (left, center or right).
    This keeps separate UI elements (a button and a link below it) apart."""
    h = max(line.height, last.height)
    gap = line.y0 - last.y1
    if not (-0.5 * h <= gap <= section_gap * h):
        return False
    if max(line.height, last.height) > 1.5 * min(line.height, last.height):
        return False
    left = abs(line.x0 - last.x0)
    right = abs(line.x1 - last.x1)
    center = abs((line.x0 + line.x1) / 2 - (last.x0 + last.x1) / 2)
    return min(left, right, center) <= 0.5 * h


def group_sections(lines: list[Line], img_w: int, img_h: int, section_gap: float = 1.0) -> list[Section]:
    """Join consecutive lines into sections (text blocks)."""
    sections: list[Section] = []
    for line in lines:
        target = None
        for sec in sections:
            if _belongs_together(sec.lines[-1], line, section_gap):
                target = sec
                break
        if target is None:
            target = Section(img_w=img_w, img_h=img_h)
            sections.append(target)
        target.lines.append(line)

    # Number sections in reading order: top to bottom, then left to right
    sections.sort(key=lambda s: (round(s.y0 / max(img_h, 1) * 50), s.x0))
    for i, sec in enumerate(sections, 1):
        sec.index = i
    return sections


def build_sections(boxes, img_w, img_h, line_tolerance=0.5, section_gap=1.0, column_gap=2.5) -> list[Section]:
    return group_sections(group_lines(boxes, line_tolerance, column_gap), img_w, img_h, section_gap)
