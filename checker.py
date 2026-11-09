#!/usr/bin/env python
"""Compare two screenshots and write a readable report.

Usage: checker.py file1 file2 [--config PATH] [--mode text|visual] [--output PATH]

Exit codes: 0 = no differences, 1 = differences found, 2 = error.
"""
import argparse
import sys
from pathlib import Path

from vtester.config import ConfigError, load_config

DEFAULT_CONFIG = Path(__file__).resolve().parent / "config.ini"


def resolve_input(name: str, input_dir: Path) -> Path:
    """Use the path as given if it exists, otherwise look it up in input_dir."""
    p = Path(name)
    if p.is_absolute() or p.exists():
        candidate = p
    else:
        candidate = input_dir / p
    if not candidate.is_file():
        raise FileNotFoundError(f"File not found: {name} (looked in {input_dir})")
    return candidate.resolve()


def run_text_mode(file1: Path, file2: Path, cfg, output: Path | None) -> int:
    from vtester.compare import compare_sections
    from vtester.layout import build_sections
    from vtester.ocr import image_size, read_text
    from vtester.report import build_report, write_report

    sections, sizes = [], []
    for f in (file1, file2):
        w, h = image_size(f)
        boxes = read_text(f, cfg.min_confidence)
        sections.append(build_sections(boxes, w, h, cfg.line_tolerance, cfg.section_gap, cfg.column_gap))
        sizes.append((w, h))

    cmp = compare_sections(sections[0], sections[1], cfg.match_threshold, cfg.position_tolerance)
    text = build_report(cmp, file1, file2, sizes[0], sizes[1], cfg.mode)
    path = write_report(text, cfg.report_dir, file1, file2, output)

    print(f"Result: {'IDENTICAL' if cmp.identical else 'DIFFERENT'}")
    print(f"Report: {path}")
    return 0 if cmp.identical else 1


def run_visual_mode(file1: Path, file2: Path, cfg, output: Path | None) -> int:
    from vtester.visual import compare_screens, load_screen
    from vtester.visual_report import write_visual_report

    cmp = compare_screens(load_screen(file1, cfg), load_screen(file2, cfg), cfg)
    text_path, marked_path, picture_path = write_visual_report(cmp, cfg.report_dir, output)

    print(f"Result: {'IDENTICAL' if cmp.identical else 'DIFFERENT'} ({len(cmp.diffs)} differences)")
    print(f"Report: {text_path}")
    print(f"Marked: {marked_path}")
    print(f"Picture: {picture_path}")
    return 0 if cmp.identical else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Compare two screenshots and write a readable report.")
    ap.add_argument("file1", help="reference screenshot")
    ap.add_argument("file2", help="screenshot to compare against the reference")
    ap.add_argument("--config", type=Path, help=f"config file (default: {DEFAULT_CONFIG.name} next to checker.py)")
    ap.add_argument("--mode", choices=["text", "visual"], help="override the mode from the config file")
    ap.add_argument("--output", type=Path, help="report file path (default: <report_dir>/<file1>_vs_<file2>_<time>.txt); "
                    "visual mode also writes <name>_marked.png and <name>_report.png next to it")
    args = ap.parse_args(argv)

    try:
        cfg = load_config(args.config or DEFAULT_CONFIG, args.mode, required=args.config is not None)
        file1 = resolve_input(args.file1, cfg.input_dir)
        file2 = resolve_input(args.file2, cfg.input_dir)
    except (ConfigError, FileNotFoundError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    run = run_visual_mode if cfg.mode == "visual" else run_text_mode
    try:
        return run(file1, file2, cfg, args.output)
    except Exception as e:  # unreadable image, OCR failure, etc.
        print(f"Error: {type(e).__name__}: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
