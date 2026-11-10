"""Draws Alfred's icon (purple circle, white 'A') as a multi-size .ico - used for the Windows shortcuts."""
from __future__ import annotations

from pathlib import Path


def make_icon(path: str | Path) -> Path:
    from PIL import Image, ImageDraw, ImageFont

    path = Path(path)
    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((8, 8, size - 8, size - 8), fill=(124, 58, 237, 255))      # purple
    d.ellipse((8, 8, size - 8, size - 8), outline=(196, 160, 255, 255), width=10)
    font = None
    for name in ("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf", "Arial Bold.ttf"):
        try:
            font = ImageFont.truetype(name, 150)
            break
        except OSError:
            continue
    font = font or ImageFont.load_default()
    box = d.textbbox((0, 0), "A", font=font)
    w, h = box[2] - box[0], box[3] - box[1]
    d.text(((size - w) / 2 - box[0], (size - h) / 2 - box[1] - 4), "A", font=font, fill="white")
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return path


if __name__ == "__main__":
    import sys

    print(make_icon(sys.argv[1] if len(sys.argv) > 1 else "alfred.ico"))
