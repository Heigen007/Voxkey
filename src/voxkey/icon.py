"""The microphone glyph, shared by the tray icon and the .exe icon."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

IDLE_COLOR = (150, 158, 172, 255)
RECORDING_COLOR = (242, 84, 91, 255)
BRAND_COLOR = (91, 141, 239, 255)

ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def mic_image(color: tuple[int, int, int, int], size: int = 64) -> Image.Image:
    """A simple microphone that still reads at 16 px."""
    k = size / 64
    image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    line = max(1, round(5 * k))
    draw.rounded_rectangle(
        (25 * k, 10 * k, 39 * k, 38 * k), radius=max(1, round(7 * k)), fill=color
    )
    draw.arc((17 * k, 24 * k, 47 * k, 48 * k), start=0, end=180, fill=color, width=line)
    draw.line((32 * k, 46 * k, 32 * k, 54 * k), fill=color, width=line)
    draw.line((23 * k, 54 * k, 41 * k, 54 * k), fill=color, width=line)
    return image


def save_ico(path: Path | str) -> None:
    """Write a multi-resolution .ico for the packaged executable."""
    mic_image(BRAND_COLOR, 256).save(path, format='ICO', sizes=ICO_SIZES)


if __name__ == '__main__':
    target = Path(__file__).resolve().parents[2] / 'icon.ico'
    save_ico(target)
    print(f'wrote {target}')
