"""Visual mode: compares two screenshots by their visual blocks (text blocks, buttons, form
fields, icons) without reading any text.

1. Blocks are found from pixels that stand out from the background (edges and filled shapes),
   merged when they are close together (letters -> words -> lines -> paragraphs).
2. Blocks are matched between the screenshots by how they look, with tolerance for small color
   noise, 1 px jitter and small size changes. Matched blocks that shifted too far are "moved".
3. Blocks without a look-alike are compared in place: overlapping ones are "changed",
   the rest are "missing" (only in file 1) or "new" (only in file 2).
"""
import math
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

Box = tuple[float, float, float, float]  # x0, y0, x1, y1 (x1/y1 exclusive)


@dataclass
class Block:
    x0: int
    y0: int
    x1: int
    y1: int
    index: int = 0                              # 1-based number in reading order
    holes: list = field(default_factory=list)   # inner blocks of a large container, compared on their own

    @property
    def box(self) -> Box:
        return (self.x0, self.y0, self.x1, self.y1)

    @property
    def w(self) -> int:
        return self.x1 - self.x0

    @property
    def h(self) -> int:
        return self.y1 - self.y0

    @property
    def area(self) -> int:
        return self.w * self.h


@dataclass
class Screen:
    path: Path
    img: np.ndarray       # BGR pixels
    mask: np.ndarray      # True where a pixel is not background
    blocks: list[Block]

    @property
    def w(self) -> int:
        return self.img.shape[1]

    @property
    def h(self) -> int:
        return self.img.shape[0]


@dataclass
class Diff:
    kind: str                       # "changed", "moved", "missing", "new"
    box1: Box | None = None         # area in file 1 (file 1 pixels)
    box2: Box | None = None         # area in file 2 (file 2 pixels)
    old_in_2: Box | None = None     # file 1 area mapped onto file 2 (where it used to be)
    details: list = field(default_factory=list)  # changed spots inside the area (file 2 pixels)
    score: float = 0.0              # share of the block's content that differs (0..1)
    shift: tuple | None = None      # (dx %, dy %, dx px, dy px) for moved blocks
    number: int = 0


@dataclass
class VisualComparison:
    first: Screen
    second: Screen
    diffs: list[Diff]
    unchanged: int

    @property
    def identical(self) -> bool:
        return not self.diffs


# ---------------------------------------------------------------- loading and block detection

def load_image(path: Path) -> np.ndarray:
    """Read an image as 8-bit BGR. Transparent areas are put on white."""
    data = np.fromfile(str(path), dtype=np.uint8)  # imread cannot open some Windows paths
    img = cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError(f"Cannot read image: {path}")
    if img.dtype != np.uint8:
        img = (img / 257).astype(np.uint8)
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    elif img.shape[2] == 4:
        alpha = img[:, :, 3:4].astype(np.float32) / 255
        img = (img[:, :, :3] * alpha + 255 * (1 - alpha)).astype(np.uint8)
    return img


def background_color(img: np.ndarray) -> np.ndarray:
    """Most common color along the image border."""
    border = np.concatenate([img[0], img[-1], img[:, 0], img[:, -1]]).astype(np.int32)
    q = border // 8
    keys = q[:, 0] * 1024 + q[:, 1] * 32 + q[:, 2]
    values, counts = np.unique(keys, return_counts=True)
    return np.median(border[keys == values[counts.argmax()]], axis=0)


def foreground_mask(img: np.ndarray, pixel_tolerance: float) -> np.ndarray:
    """Pixels that are part of some element: edges (text, outlines) plus, on a plain
    background, every pixel of a different color (filled buttons, panels, icons)."""
    grad = cv2.morphologyEx(img, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)).max(axis=2)
    mask = grad > pixel_tolerance
    bg = background_color(img)
    off_bg = np.abs(img.astype(np.int16) - bg.astype(np.int16)).max(axis=2) > pixel_tolerance
    if off_bg.mean() < 0.6:  # skip fills on busy backgrounds (photos, gradients)
        mask |= off_bg
    return mask


def _contains(outer: Box, inner: Box) -> bool:
    return outer[0] <= inner[0] and outer[1] <= inner[1] and outer[2] >= inner[2] and outer[3] >= inner[3]


def detect_blocks(img: np.ndarray, mask: np.ndarray, cfg) -> list[Block]:
    h, w = mask.shape
    kx, ky = max(1, int(cfg.merge_x)), max(1, int(cfg.merge_y))
    joined = cv2.dilate(mask.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_RECT, (kx, ky)))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(joined, connectivity=8)

    boxes = []
    for i in range(1, n):
        x, y, bw, bh, _ = stats[i]
        own = (labels[y:y + bh, x:x + bw] == i) & mask[y:y + bh, x:x + bw]
        ys, xs = np.nonzero(own)
        if len(xs) == 0:
            continue
        box = (x + xs.min(), y + ys.min(), x + xs.max() + 1, y + ys.max() + 1)
        if box[2] - box[0] < cfg.min_block_size and box[3] - box[1] < cfg.min_block_size:
            continue  # speck / noise
        boxes.append(box)

    # Elements inside a small widget (text in a button, field in a form row) belong to it.
    # Elements inside a large container (card, panel, page frame) stay separate blocks and are
    # left out when the container itself is compared.
    max_widget = cfg.max_widget_area / 100 * w * h
    boxes.sort(key=lambda b: (b[2] - b[0]) * (b[3] - b[1]), reverse=True)
    blocks: list[Block] = []
    for box in boxes:
        parents = [p for p in blocks if _contains(p.box, box)]
        if any(p.area <= max_widget for p in parents):
            continue
        for p in parents:
            p.holes.append(box)
        blocks.append(Block(*map(int, box)))

    blocks.sort(key=lambda b: (round(b.y0 / max(h, 1) * 50), b.x0))
    for i, b in enumerate(blocks, 1):
        b.index = i
    return blocks


def load_screen(path: Path, cfg) -> Screen:
    img = load_image(path)
    mask = foreground_mask(img, cfg.pixel_tolerance)
    return Screen(path, img, mask, detect_blocks(img, mask, cfg))


# ---------------------------------------------------------------- comparing regions

def _scale(box: Box, fx: float, fy: float) -> Box:
    return (box[0] * fx, box[1] * fy, box[2] * fx, box[3] * fy)


def _int_box(box: Box, w: int, h: int) -> tuple[int, int, int, int]:
    x0, y0 = max(0, int(np.floor(box[0]))), max(0, int(np.floor(box[1])))
    x1, y1 = min(w, int(np.ceil(box[2]))), min(h, int(np.ceil(box[3])))
    return x0, y0, max(x0, x1), max(y0, y1)


def _union(boxes) -> Box:
    boxes = list(boxes)
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def _mismatch(a: np.ndarray, b: np.ndarray, tol: float) -> np.ndarray:
    """Pixels that differ by more than tol, allowing each pixel to match anywhere in the
    3x3 neighborhood of the other image (tolerates 1 px jitter and anti-aliasing)."""
    k = np.ones((3, 3), np.uint8)
    a16, b16 = a.astype(np.int16), b.astype(np.int16)
    a_lo, a_hi = cv2.erode(a, k).astype(np.int16), cv2.dilate(a, k).astype(np.int16)
    b_lo, b_hi = cv2.erode(b, k).astype(np.int16), cv2.dilate(b, k).astype(np.int16)
    bad_a = ((a16 < b_lo - tol) | (a16 > b_hi + tol)).any(axis=2)
    bad_b = ((b16 < a_lo - tol) | (b16 > a_hi + tol)).any(axis=2)
    bad = (bad_a | bad_b).astype(np.uint8)
    return cv2.morphologyEx(bad, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8)) > 0  # drop lone pixels


@dataclass
class RegionDiff:
    bad: np.ndarray    # mismatch mask in file 1 region coordinates
    score: float       # differing pixels / content pixels
    region1: tuple     # integer region in file 1
    region2: tuple     # integer region in file 2


def region_diff(s1: Screen, box1: Box, s2: Screen, box2: Box, tol: float,
                holes1=(), holes2=()) -> RegionDiff | None:
    """Compare a region of file 1 with a region of file 2 (resized onto it)."""
    r1 = _int_box(box1, s1.w, s1.h)
    r2 = _int_box(box2, s2.w, s2.h)
    a = s1.img[r1[1]:r1[3], r1[0]:r1[2]]
    b = s2.img[r2[1]:r2[3], r2[0]:r2[2]]
    if a.size == 0 or b.size == 0:
        return None
    ink_a = s1.mask[r1[1]:r1[3], r1[0]:r1[2]]
    ink_b = s2.mask[r2[1]:r2[3], r2[0]:r2[2]]
    size = (a.shape[1], a.shape[0])
    if b.shape[:2] != a.shape[:2]:
        b = cv2.resize(b, size, interpolation=cv2.INTER_AREA)
        ink_b = cv2.resize(ink_b.astype(np.uint8), size, interpolation=cv2.INTER_NEAREST) > 0
    bad = _mismatch(a, b, tol)
    ink = ink_a | ink_b

    # Leave out inner blocks of containers; they are compared separately
    fx, fy = a.shape[1] / max(1, r2[2] - r2[0]), a.shape[0] / max(1, r2[3] - r2[1])
    rel = [(h[0] - r1[0], h[1] - r1[1], h[2] - r1[0], h[3] - r1[1]) for h in holes1]
    rel += [((h[0] - r2[0]) * fx, (h[1] - r2[1]) * fy, (h[2] - r2[0]) * fx, (h[3] - r2[1]) * fy) for h in holes2]
    for hb in rel:
        x0, y0, x1, y1 = _int_box(hb, size[0], size[1])
        bad[y0:y1, x0:x1] = False
        ink[y0:y1, x0:x1] = False

    score = float(bad.sum()) / max(int(ink.sum()), 1)
    return RegionDiff(bad, min(score, 1.0), r1, r2)


def _spots(rd: RegionDiff, min_size: int) -> list[Box]:
    """Bounding boxes of the differing areas, in file 2 pixels."""
    bad = cv2.dilate(rd.bad.astype(np.uint8), np.ones((5, 5), np.uint8))
    n, _, stats, _ = cv2.connectedComponentsWithStats(bad, connectivity=8)
    x0, y0, x1, y1 = rd.region1
    fx = (rd.region2[2] - rd.region2[0]) / max(1, x1 - x0)
    fy = (rd.region2[3] - rd.region2[1]) / max(1, y1 - y0)
    spots = []
    for i in range(1, n):
        x, y, w, h, _ = stats[i]
        if w < min_size and h < min_size:
            continue
        spots.append((rd.region2[0] + x * fx, rd.region2[1] + y * fy,
                      rd.region2[0] + (x + w) * fx, rd.region2[1] + (y + h) * fy))
    return spots


def _find_inside(src: Screen, box: Box, dst: Screen, area: Box, tol: float, change_tol: float) -> Box | None:
    """Look for the content of `box` (in src) inside `area` (in dst). Used when blocks were
    merged differently, e.g. a button moved next to a link and now forms one block with it."""
    fx, fy = dst.w / src.w, dst.h / src.h
    tw, th = round((box[2] - box[0]) * fx), round((box[3] - box[1]) * fy)
    r = _int_box((area[0] - 2, area[1] - 2, area[2] + 2, area[3] + 2), dst.w, dst.h)
    search = dst.img[r[1]:r[3], r[0]:r[2]]
    if tw < 2 or th < 2 or search.shape[1] < tw or search.shape[0] < th:
        return None
    sb = _int_box(box, src.w, src.h)
    tmpl = src.img[sb[1]:sb[3], sb[0]:sb[2]]
    if tmpl.shape[:2] != (th, tw):
        tmpl = cv2.resize(tmpl, (tw, th), interpolation=cv2.INTER_AREA)
    result = cv2.matchTemplate(search, tmpl, cv2.TM_SQDIFF_NORMED)
    _, _, (lx, ly), _ = cv2.minMaxLoc(result)
    found = (r[0] + lx, r[1] + ly, r[0] + lx + tw, r[1] + ly + th)
    # The match must stand on its own: content crossing its edge means it is only a slice
    # of a bigger element (e.g. the left part of a wider input field)
    x0, y0, x1, y1 = found
    m = dst.mask
    sides = (m[max(0, y0 - 2):y0, x0:x1], m[y1:y1 + 2, x0:x1], m[y0:y1, max(0, x0 - 2):x0], m[y0:y1, x1:x1 + 2])
    if any(side.size and side.mean() > 0.05 for side in sides):
        return None
    rd = region_diff(src, box, dst, found, tol)
    return found if rd is not None and rd.score <= change_tol else None


def _overlap(a: Box, b: Box) -> float:
    """Intersection area divided by the smaller box area."""
    iw = min(a[2], b[2]) - max(a[0], b[0])
    ih = min(a[3], b[3]) - max(a[1], b[1])
    if iw <= 0 or ih <= 0:
        return 0.0
    smaller = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
    return iw * ih / max(smaller, 1)


def _center(box: Box) -> tuple[float, float]:
    return (box[0] + box[2]) / 2, (box[1] + box[3]) / 2


# ---------------------------------------------------------------- matching

def compare_screens(s1: Screen, s2: Screen, cfg) -> VisualComparison:
    fx, fy = s1.w / s2.w, s1.h / s2.h          # file 2 -> file 1 coordinates
    tol = cfg.pixel_tolerance
    change_tol = cfg.change_tolerance / 100
    size_tol = cfg.size_tolerance / 100
    in1 = {b.index: _scale(b.box, fx, fy) for b in s2.blocks}

    # Pass 1: blocks that look the same (anywhere on the screen)
    candidates = []
    for a in s1.blocks:
        for b in s2.blocks:
            bb = in1[b.index]
            bw, bh = bb[2] - bb[0], bb[3] - bb[1]
            if abs(a.w - bw) > size_tol * max(a.w, bw) + 2 or abs(a.h - bh) > size_tol * max(a.h, bh) + 2:
                continue
            rd = region_diff(s1, a.box, s2, b.box, tol, a.holes, b.holes)
            if rd is None or rd.score > change_tol:
                continue
            (ax, ay), (bx, by) = _center(a.box), _center(bb)
            dist = ((ax - bx) / s1.w) ** 2 + ((ay - by) / s1.h) ** 2
            candidates.append((dist, rd.score, a.index, b.index, a, b))
    candidates.sort(key=lambda c: c[:4])  # nearest first: duplicates pair up with their neighbor

    diffs: list[Diff] = []
    unchanged = 0

    def record(box1: Box, box2: Box):
        nonlocal unchanged
        (ax, ay), (bx, by) = _center(box1), _center(_scale(box2, fx, fy))
        dx_pct, dy_pct = 100 * (bx - ax) / s1.w, 100 * (by - ay) / s1.h
        if abs(dx_pct) > cfg.position_tolerance or abs(dy_pct) > cfg.position_tolerance:
            diffs.append(Diff("moved", box1=box1, box2=box2, old_in_2=_scale(box1, 1 / fx, 1 / fy),
                              shift=(dx_pct, dy_pct, (bx - ax) / fx, (by - ay) / fy)))
        else:
            unchanged += 1

    used1, used2 = set(), set()
    for _, _, ai, bi, a, b in candidates:
        if ai in used1 or bi in used2:
            continue
        used1.add(ai)
        used2.add(bi)
        record(a.box, b.box)

    # Pass 1b: a block may be found inside a bigger block of the other screenshot when it
    # was merged with a neighbor there. Found parts are left out of later comparisons.
    extra1: dict[int, list] = {}
    extra2: dict[int, list] = {}
    for src, dst, used_src, used_dst, extra_dst, first_is_src in (
            (s1, s2, used1, used2, extra2, True), (s2, s1, used2, used1, extra1, False)):
        fwd = (1 / fx, 1 / fy) if first_is_src else (fx, fy)   # src -> dst coordinates
        containers = [b for b in dst.blocks if b.index not in used_dst]
        for a in [a for a in src.blocks if a.index not in used_src and not a.holes]:
            a_in_dst = _scale(a.box, *fwd)
            near = sorted(containers, key=lambda b: math.dist(_center(b.box), _center(a_in_dst)))
            for b in near:
                if b.w + 2 < (a_in_dst[2] - a_in_dst[0]) or b.h + 2 < (a_in_dst[3] - a_in_dst[1]):
                    continue
                found = _find_inside(src, a.box, dst, b.box, tol, change_tol)
                if found is None:
                    continue
                used_src.add(a.index)
                extra_dst.setdefault(b.index, []).append(found)
                record(a.box, found) if first_is_src else record(found, a.box)
                break

    # Pass 2: the rest - group blocks that overlap across the two screenshots
    rest1 = [a for a in s1.blocks if a.index not in used1]
    rest2 = [b for b in s2.blocks if b.index not in used2]
    parent = list(range(len(rest1) + len(rest2)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, a in enumerate(rest1):
        for j, b in enumerate(rest2):
            if _overlap(a.box, in1[b.index]) >= 0.3:
                parent[find(i)] = find(len(rest1) + j)

    groups: dict[int, tuple[list, list]] = {}
    for i, a in enumerate(rest1):
        groups.setdefault(find(i), ([], []))[0].append(a)
    for j, b in enumerate(rest2):
        groups.setdefault(find(len(rest1) + j), ([], []))[1].append(b)

    for g1, g2 in groups.values():
        # Look at the whole area in both screenshots, so a block that is only detected
        # differently (but looks the same) is not reported
        area1 = _union([a.box for a in g1] + [in1[b.index] for b in g2])
        area2 = _scale(area1, 1 / fx, 1 / fy)
        holes1 = [h for a in g1 for h in a.holes + extra1.get(a.index, [])]
        holes2 = [h for b in g2 for h in b.holes + extra2.get(b.index, [])]
        rd = region_diff(s1, area1, s2, area2, tol, holes1, holes2)
        if rd is None or rd.score <= change_tol:
            unchanged += len(g1)
            continue
        box1 = _union(a.box for a in g1) if g1 else None
        box2 = _union(b.box for b in g2) if g2 else None
        if g1 and g2:
            diffs.append(Diff("changed", box1=box1, box2=box2, score=rd.score,
                              details=_spots(rd, cfg.min_block_size)))
        elif g1:
            diffs.append(Diff("missing", box1=box1, old_in_2=_scale(box1, 1 / fx, 1 / fy), score=rd.score))
        else:
            diffs.append(Diff("new", box1=_scale(box2, fx, fy), box2=box2, score=rd.score))

    # Number differences top to bottom, left to right (as seen on file 2)
    def where(d: Diff):
        box = d.box2 or d.old_in_2
        return (round(box[1] / max(s2.h, 1) * 50), box[0])

    diffs.sort(key=where)
    for i, d in enumerate(diffs, 1):
        d.number = i
    return VisualComparison(s1, s2, diffs, unchanged)
