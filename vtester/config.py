"""Loads config.ini and applies command-line overrides."""
import configparser
from dataclasses import dataclass
from pathlib import Path

MODES = ("text", "visual")


class ConfigError(Exception):
    pass


@dataclass
class Config:
    input_dir: Path
    mode: str = "text"
    report_dir: Path = Path("reports")
    min_confidence: float = 0.5
    line_tolerance: float = 0.5
    section_gap: float = 1.0
    column_gap: float = 2.5
    match_threshold: float = 0.6
    position_tolerance: float = 2.0
    # visual mode
    pixel_tolerance: float = 40.0
    change_tolerance: float = 3.0
    size_tolerance: float = 10.0
    merge_x: float = 15.0
    merge_y: float = 10.0
    min_block_size: float = 4.0
    max_widget_area: float = 15.0


def load_config(path: Path, mode_override: str | None = None, required: bool = False) -> Config:
    """Read the config file. Relative paths are resolved against the config file's folder.
    A missing file falls back to defaults unless required=True."""
    parser = configparser.ConfigParser(inline_comment_prefixes=(";", "#"))
    if path.exists():
        try:
            parser.read(path, encoding="utf-8-sig")  # -sig: tolerate a BOM (e.g. Notepad)
        except configparser.Error as e:
            raise ConfigError(f"Cannot parse {path}: {e}")
    elif required:
        raise ConfigError(f"Config file not found: {path}")

    base = path.resolve().parent

    def get(section, key, fallback):
        return parser.get(section, key, fallback=fallback) if parser.has_section(section) else fallback

    def get_float(section, key, fallback):
        raw = get(section, key, str(fallback))
        try:
            return float(raw)
        except ValueError:
            raise ConfigError(f"[{section}] {key} must be a number, got {raw!r}")

    def resolve(p: str) -> Path:
        p = Path(p)
        return p if p.is_absolute() else (base / p).resolve()

    mode = (mode_override or get("checker", "mode", "text")).strip().lower()
    if mode not in MODES:
        raise ConfigError(f"Unknown mode {mode!r}. Use one of: {', '.join(MODES)}")

    return Config(
        input_dir=resolve(get("checker", "input_dir", "./input")),
        mode=mode,
        report_dir=resolve(get("checker", "report_dir", "./reports")),
        min_confidence=get_float("checker", "min_confidence", 0.5),
        line_tolerance=get_float("layout", "line_tolerance", 0.5),
        section_gap=get_float("layout", "section_gap", 1.0),
        column_gap=get_float("layout", "column_gap", 2.5),
        match_threshold=get_float("compare", "match_threshold", 0.6),
        position_tolerance=get_float("compare", "position_tolerance", 2.0),
        pixel_tolerance=get_float("visual", "pixel_tolerance", 40.0),
        change_tolerance=get_float("visual", "change_tolerance", 3.0),
        size_tolerance=get_float("visual", "size_tolerance", 10.0),
        merge_x=get_float("visual", "merge_x", 15.0),
        merge_y=get_float("visual", "merge_y", 10.0),
        min_block_size=get_float("visual", "min_block_size", 4.0),
        max_widget_area=get_float("visual", "max_widget_area", 15.0),
    )
