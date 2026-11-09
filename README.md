# Visual Tester

Compares two screenshots and writes a report of what is different. Typical use: a reference
screenshot of a page vs. a new screenshot after a change.

There are two modes:

| Mode | What it compares | Output |
|---|---|---|
| `text` (default) | Reads the text on both screenshots (OCR) and compares the text sections: changed words, missing/new sections, moved sections. | Text report |
| `visual` | Compares visual blocks (text blocks, buttons, form fields, icons) by how they look and where they are. No OCR. Catches changes text mode cannot see, such as a button changing color. | Text report, second screenshot with differences marked in red, side-by-side report picture |

## Requirements

- Python 3.10 or newer (developed on Python 3.13)
- The packages in `requirements.txt`: RapidOCR (OCR engine, used by text mode), OpenCV, numpy, Pillow, pytest

## Installation

Run these in the project folder (`visual tester`).

**Windows (PowerShell)**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**Linux / macOS**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

The first text-mode run may take a few seconds longer while the OCR models load.

> If PowerShell refuses to run `Activate.ps1`, run
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, or call the venv's Python directly:
> `.venv\Scripts\python checker.py ...`

## Usage

```
python checker.py FILE1 FILE2 [--mode text|visual] [--config PATH] [--output PATH]
```

| Argument | Meaning |
|---|---|
| `FILE1` | Reference screenshot (how it should look) |
| `FILE2` | Screenshot to check against the reference |
| `--mode` | `text` or `visual`. Overrides `mode` in the config file. |
| `--config` | Config file to use. Default: `config.ini` next to `checker.py`. |
| `--output` | Where to write the text report. Default: `reports/<file1>_vs_<file2>_<date>_<time>.txt`. |

File names are looked up in the input folder (`input/` by default). You can also give a full
path or a path relative to the current folder.

### Examples

```bash
# Text mode (default): compare the text on both screenshots
python checker.py base.png changed.png

# Visual mode: compare blocks and mark the differences on the second screenshot
python checker.py base.png mixed.png --mode visual

# Files outside the input folder, report written to a chosen file
python checker.py C:\shots\before.png C:\shots\after.png --mode visual --output results\login.txt
```

The console shows the result and where the report files are:

```
Result: DIFFERENT (5 differences)
Report: reports\base_vs_mixed_20261109_191502.txt
Marked: reports\base_vs_mixed_20261109_191502_marked.png
Picture: reports\base_vs_mixed_20261109_191502_report.png
```

### Exit codes

Useful for scripts and CI pipelines:

| Code | Meaning |
|---|---|
| `0` | No differences |
| `1` | Differences found |
| `2` | Error (file not found, unreadable image, bad config) |

## Reports

### Text mode

A `.txt` file that lists every text section of file 1 and what happened to it in file 2:

- **OK**: same text, same position
- **TEXT CHANGED**: the section exists, with the word differences listed (`changed "Password" -> "Passcode"`)
- **MOVED**: how far and in which direction, in % of the image and in pixels
- **ORDER CHANGED**: the section appears in a different place in the reading order
- **MISSING** in file 2, or **NEW** in file 2

At the end, the report includes the full OCR text of both screenshots.

### Visual mode

Three files with the same name:

| File | Content |
|---|---|
| `<name>.txt` | Summary and a numbered list of differences: **CHANGED**, **MOVED**, **MISSING**, **NEW**. Also lists every block found in both screenshots. |
| `<name>_marked.png` | File 2 with each difference marked in red and numbered. **Solid box**: how it looks now (changed, new, moved here). **Dashed box**: where something used to be (missing, moved away). An **arrow** shows a move. |
| `<name>_report.png` | One picture for sharing: file 1 and the marked file 2 side by side, with the summary and the list of differences. |

The numbers are the same in all three files.

How visual mode decides:

1. It finds blocks: pixels that stand out from the background (text, outlines, filled
   buttons, icons), with nearby pixels merged into one block.
2. It matches blocks that look the same, anywhere on the screen. A matched block whose
   position changed by more than `position_tolerance` is reported as **moved**.
3. It compares the remaining blocks in place. Overlapping blocks that look different are
   **changed**. The rest are **missing** (only in file 1) or **new** (only in file 2).

Screenshots of different sizes are compared after scaling file 2 to the size of file 1.

## Configuration (`config.ini`)

```ini
[checker]
input_dir = ./input        ; where FILE1/FILE2 are looked up
mode = text                ; text or visual
report_dir = ./reports     ; where reports are written
min_confidence = 0.5       ; text mode: ignore OCR results less certain than this (0..1)
```

Relative paths are resolved from the folder that contains the config file.

**Text mode**

| Setting | Default | Meaning |
|---|---|---|
| `[layout] line_tolerance` | 0.5 | Text pieces are on one line if their vertical centers differ by less than this fraction of the line height |
| `[layout] section_gap` | 1.0 | A vertical gap larger than this many line heights starts a new section |
| `[layout] column_gap` | 2.5 | Text on the same row further apart than this many line heights is split into separate sections (columns, buttons side by side) |
| `[compare] match_threshold` | 0.6 | How similar (0..1) two sections' texts must be to count as the same section |

**Both modes**

| Setting | Default | Meaning |
|---|---|---|
| `[compare] position_tolerance` | 2.0 | Shifts larger than this (% of image width or height) are reported as moved |

**Visual mode**

| Setting | Default | Meaning | Raise it if... |
|---|---|---|---|
| `[visual] pixel_tolerance` | 40 | Color difference per pixel (0..255) that is ignored | JPEG noise or anti-aliasing is reported as changes |
| `[visual] change_tolerance` | 3.0 | A block is changed when more than this % of its content differs | Tiny rendering differences are reported |
| `[visual] size_tolerance` | 10 | Blocks can differ in size by this % and still match | Elements that only resized slightly are reported as missing and new |
| `[visual] merge_x`, `merge_y` | 15, 10 | Elements closer than this many pixels (horizontally, vertically) form one block | Words or lines of one paragraph are split into many blocks |
| `[visual] min_block_size` | 4 | Specks smaller than this many pixels are ignored | Dust-sized noise is reported |
| `[visual] max_widget_area` | 15 | Elements inside a container up to this % of the image (button, input field) belong to it. Inside bigger containers (cards, panels), elements are compared separately. | — |

For high-resolution screenshots (for example 4K), increase `merge_x` and `merge_y` roughly in
proportion to the resolution.

You can keep several config files (for example one per application) and choose one with `--config`.

## Sample screenshots

`tests/make_samples.py` draws a simple login screen and variations of it into `input/`:

| File | Difference from `base.png` |
|---|---|
| `same.png` | None |
| `changed.png` | Title and "Password" label text changed |
| `moved.png` | "Sign in" button moved |
| `removed.png` | "Forgot your password?" link removed |
| `added.png` | "Create account" link added |
| `restyled.png` | "Sign in" button is green (same text, so only visual mode sees it) |
| `mixed.png` | Several changes at once: title text, logo removed, wider input field, button moved, new link |

```bash
python tests/make_samples.py
python checker.py base.png mixed.png --mode visual
```

## Running the tests

```bash
python -m pytest -q
```

The tests use generated images and fake OCR results, so they run in about a second and do
not need the OCR models.

## Project structure

```
checker.py               command-line entry point
config.ini               settings
vtester/
  config.py              reads config.ini
  ocr.py                 text mode: OCR (RapidOCR)
  layout.py              text mode: groups text into lines and sections
  compare.py             text mode: matches sections, word differences, moves
  report.py              text mode: text report
  visual.py              visual mode: finds and matches blocks
  visual_report.py       visual mode: marked screenshot, report picture, text report
tests/
  make_samples.py        draws the sample screenshots
  test_compare.py        text mode tests
  test_visual.py         visual mode tests
input/                   screenshots to compare
reports/                 generated reports
```

## Known limitations

- **Text mode:** when an element moves right next to another one, OCR may group them into one
  section. The move then shows up as one missing section plus one changed section.
- **Visual mode:** a block that changes and also moves far away is reported as missing plus new.
- **Visual mode:** pages with busy backgrounds (photos, gradients) produce less precise blocks,
  because only edges are used to find elements there.
- **Visual mode:** compare screenshots taken at the same zoom level and window size. A different
  layout (for example a mobile vs. desktop view) shows up as many differences.
