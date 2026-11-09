"""Matches sections between two screenshots and describes text and position differences."""
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from .layout import Section


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def similarity(a: str, b: str) -> float:
    a, b = normalize(a), normalize(b)
    if not a and not b:
        return 1.0
    return SequenceMatcher(None, a, b, autojunk=False).ratio()


def _quote(words: list[str]) -> str:
    return '"' + " ".join(words) + '"'


def word_diff(a: str, b: str) -> list[str]:
    """Readable list of word-level changes needed to turn text a into text b."""
    wa, wb = a.split(), b.split()
    changes = []
    for op, i1, i2, j1, j2 in SequenceMatcher(None, wa, wb, autojunk=False).get_opcodes():
        if op == "replace":
            changes.append(f"changed {_quote(wa[i1:i2])} -> {_quote(wb[j1:j2])}")
        elif op == "delete":
            changes.append(f"missing in file 2: {_quote(wa[i1:i2])}")
        elif op == "insert":
            changes.append(f"added in file 2: {_quote(wb[j1:j2])}")
    return changes


@dataclass
class Move:
    dx_pct: float
    dy_pct: float
    dx_px: float
    dy_px: float

    def describe(self) -> str:
        parts = []
        if abs(self.dy_pct) >= 0.05:
            parts.append(f"{abs(self.dy_pct):.1f}% {'down' if self.dy_pct > 0 else 'up'} ({abs(self.dy_px):.0f} px)")
        if abs(self.dx_pct) >= 0.05:
            parts.append(f"{abs(self.dx_pct):.1f}% {'right' if self.dx_pct > 0 else 'left'} ({abs(self.dx_px):.0f} px)")
        return ", ".join(parts) or "no shift"


@dataclass
class SectionResult:
    first: Section                  # section from file 1
    second: Section | None = None   # matching section from file 2 (None = missing)
    score: float = 0.0
    text_changes: list[str] = field(default_factory=list)
    move: Move | None = None        # set only when the shift exceeds the tolerance
    order_changed: bool = False

    @property
    def missing(self) -> bool:
        return self.second is None

    @property
    def ok(self) -> bool:
        return not self.missing and not self.text_changes and self.move is None and not self.order_changed


@dataclass
class Comparison:
    results: list[SectionResult]   # one per section of file 1, in reading order
    new_sections: list[Section]    # sections found only in file 2

    @property
    def identical(self) -> bool:
        return all(r.ok for r in self.results) and not self.new_sections


def _lcs_indices(seq: list[int]) -> set[int]:
    """Positions in seq that form the longest increasing subsequence (items that kept their order)."""
    n = len(seq)
    if n == 0:
        return set()
    best = [1] * n
    prev = [-1] * n
    for i in range(n):
        for j in range(i):
            if seq[j] < seq[i] and best[j] + 1 > best[i]:
                best[i], prev[i] = best[j] + 1, j
    i = max(range(n), key=lambda k: best[k])
    keep = set()
    while i != -1:
        keep.add(i)
        i = prev[i]
    return keep


def compare_sections(first: list[Section], second: list[Section],
                     match_threshold: float = 0.6, position_tolerance: float = 2.0) -> Comparison:
    # Score every pair; prefer higher text similarity, then smaller distance
    candidates = []
    for a in first:
        for b in second:
            score = similarity(a.text, b.text)
            if score >= match_threshold:
                (ax, ay), (bx, by) = a.center_pct, b.center_pct
                dist = ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5
                candidates.append((-score, dist, a.index, b.index, a, b))
    candidates.sort(key=lambda c: c[:4])

    matched: dict[int, tuple[Section, float]] = {}
    used_second = set()
    for neg_score, _, ai, bi, a, b in candidates:
        if ai in matched or bi in used_second:
            continue
        matched[ai] = (b, -neg_score)
        used_second.add(bi)

    results = []
    for a in first:
        res = SectionResult(first=a)
        if a.index in matched:
            b, score = matched[a.index]
            res.second, res.score = b, score
            res.text_changes = word_diff(a.text, b.text)
            (ax, ay), (bx, by) = a.center_pct, b.center_pct
            (apx, apy), (bpx, bpy) = a.center_px, b.center_px
            if abs(bx - ax) > position_tolerance or abs(by - ay) > position_tolerance:
                res.move = Move(bx - ax, by - ay, bpx - apx, bpy - apy)
        results.append(res)

    # Order check: matched sections that are out of sequence in file 2
    matched_results = [r for r in results if r.second is not None]
    keep = _lcs_indices([r.second.index for r in matched_results])
    for i, r in enumerate(matched_results):
        if i not in keep:
            r.order_changed = True

    new_sections = [b for b in second if b.index not in used_second]
    return Comparison(results, new_sections)
