"""Replace the 'ACTIVE E' caption on the BoostDeck background (56300.png) with 'HV BATT'.

Usage: relabel_bar.py <source images zip> <output images zip> <preview png>
Keeps every other archive entry byte-identical and in the same order.
"""
import io
import sys
import zipfile

from PIL import Image, ImageDraw, ImageFont

TEXT = "HV BATT"
FONT = r"C:\Windows\Fonts\bahnschrift.ttf"
PANEL_BG = (23, 27, 34, 255)
COLOR = (186, 200, 216, 255)
OLD_BOX = (1046, 14, 1158, 43)      # generous box around the old caption, inside the panel
LEFT, TOP, BOTTOM, MAX_RIGHT = 1052, 19, 37, 1154   # old caption's cap box and right limit


def fitted_font():
    """Largest size/width whose capitals match the old cap height and fit the panel."""
    for size in range(26, 14, -1):
        for variation in (b"Regular", b"SemiCondensed", b"Condensed"):
            font = ImageFont.truetype(FONT, size)
            try:
                font.set_variation_by_name(variation)
            except (OSError, ValueError):
                continue
            left, top, right, bottom = font.getbbox(TEXT)
            if bottom - top <= BOTTOM - TOP + 1 and LEFT + (right - left) <= MAX_RIGHT:
                return font, variation, size, (left, top, right, bottom)
    raise SystemExit("no font variation fits the panel")


def main(source, output, preview):
    with zipfile.ZipFile(source) as src:
        infos = src.infolist()
        image = Image.open(io.BytesIO(src.read("56300.png"))).convert("RGBA")
        draw = ImageDraw.Draw(image)
        draw.rectangle(OLD_BOX, fill=PANEL_BG)
        font, variation, size, box = fitted_font()
        height = box[3] - box[1]
        y = TOP + ((BOTTOM - TOP + 1) - height) // 2 - box[1]
        draw.text((LEFT - box[0], y), TEXT, font=font, fill=COLOR)
        print("font", variation.decode(), size, "text box", box, "right edge", LEFT + box[2] - box[0])
        image.save(preview)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG", optimize=True)
        with zipfile.ZipFile(output, "w") as dst:
            for info in infos:
                data = buffer.getvalue() if info.filename == "56300.png" else src.read(info.filename)
                clone = zipfile.ZipInfo(info.filename, info.date_time)
                clone.compress_type = info.compress_type
                clone.external_attr = info.external_attr
                clone.create_system = info.create_system
                dst.writestr(clone, data)
    with zipfile.ZipFile(source) as a, zipfile.ZipFile(output) as b:
        names = [i.filename for i in a.infolist()]
        assert names == [i.filename for i in b.infolist()], "entry order changed"
        changed = [n for n in names if a.read(n) != b.read(n)]
        print("entries", len(names), "changed", changed)


if __name__ == "__main__":
    main(*sys.argv[1:4])
