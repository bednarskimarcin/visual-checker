"""OCR wrapper around RapidOCR."""
from dataclasses import dataclass
from pathlib import Path

from PIL import Image


@dataclass
class TextBox:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    confidence: float = 1.0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2


_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        from rapidocr_onnxruntime import RapidOCR  # slow import, load only when needed
        _engine = RapidOCR()
    return _engine


def image_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as img:
        return img.size


def read_text(path: Path, min_confidence: float = 0.5) -> list[TextBox]:
    """Run OCR on an image and return text boxes (axis-aligned) above the confidence limit."""
    result, _ = _get_engine()(str(path))
    boxes = []
    for quad, text, score in result or []:
        score = float(score)
        text = text.strip()
        if not text or score < min_confidence:
            continue
        xs = [p[0] for p in quad]
        ys = [p[1] for p in quad]
        boxes.append(TextBox(text, min(xs), min(ys), max(xs), max(ys), score))
    return boxes
