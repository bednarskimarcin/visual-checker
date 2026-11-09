"""Draws sample 'login screen' screenshots into input/ for trying out checker.py.

base.png     - reference
same.png     - identical copy
changed.png  - a few words changed
moved.png    - the "Sign in" button moved lower
removed.png  - the "Forgot your password?" link removed
added.png    - an extra "Create account" link
restyled.png - the "Sign in" button is green (same text - only visual mode sees it)
mixed.png    - several changes at once: title text, button moved, logo missing, wider field, new link
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "input"
SIZE = (800, 600)


def font(size):
    for name in ("arial.ttf", "DejaVuSans.ttf", "Arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default(size)


BASE = [
    # (text, x, y, font size, button?)
    ("Welcome back to the portal", 200, 50, 36, False),
    ("Email address", 200, 160, 26, False),
    ("Password", 200, 260, 26, False),
    ("Sign in", 340, 370, 28, True),
    ("Forgot your password?", 270, 480, 24, False),
]


# Widgets without text: (kind, box)
WIDGETS = [
    ("logo", (110, 45, 160, 95)),
    ("field", (200, 198, 600, 238)),
    ("field", (200, 298, 600, 338)),
]


def draw(elements, path, widgets=WIDGETS, button_color="#1f6feb"):
    img = Image.new("RGB", SIZE, "white")
    d = ImageDraw.Draw(img)
    for kind, box in widgets:
        if kind == "logo":
            d.ellipse(box, fill="#f0883e")
            d.ellipse((box[0] + 15, box[1] + 15, box[2] - 15, box[3] - 15), fill="white")
        else:
            d.rounded_rectangle(box, radius=4, outline="#8c959f", width=2)
    for text, x, y, size, button in elements:
        f = font(size)
        if button:
            l, t, r, b = d.textbbox((x, y), text, font=f)
            d.rounded_rectangle((l - 30, t - 15, r + 30, b + 15), radius=8, fill=button_color)
            d.text((x, y), text, font=f, fill="white")
        else:
            d.text((x, y), text, font=f, fill="black")
    img.save(path)


def replace(elements, old_text, **changes):
    out = []
    for e in elements:
        if e[0] == old_text:
            text, x, y, size, button = e
            e = (changes.get("text", text), changes.get("x", x), changes.get("y", y), size, button)
        out.append(e)
    return out


def main():
    OUT.mkdir(exist_ok=True)
    draw(BASE, OUT / "base.png")
    draw(BASE, OUT / "same.png")
    changed = replace(BASE, "Welcome back to the portal", text="Welcome to the new portal")
    changed = replace(changed, "Password", text="Passcode")
    draw(changed, OUT / "changed.png")
    draw(replace(BASE, "Sign in", y=430, x=380), OUT / "moved.png")
    draw([e for e in BASE if e[0] != "Forgot your password?"], OUT / "removed.png")
    draw(BASE + [("Create account", 300, 540, 24, False)], OUT / "added.png")
    draw(BASE, OUT / "restyled.png", button_color="#2da44e")
    mixed = replace(BASE, "Welcome back to the portal", text="Welcome to the new portal")
    mixed = replace(mixed, "Sign in", y=420)
    mixed = mixed + [("Create account", 300, 540, 24, False)]
    widgets = [("field", (200, 198, 680, 238)), ("field", (200, 298, 600, 338))]
    draw(mixed, OUT / "mixed.png", widgets=widgets)
    print(f"Samples written to {OUT}")


if __name__ == "__main__":
    main()
