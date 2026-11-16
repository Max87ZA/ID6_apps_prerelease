"""Add the Exhaust flap page (v10) to the v9 BoostDeck layout and image archive.

Usage: make_flap_page.py <BoostDeck.xml in/out (v9)> <images zip in (v9)> <images zip out> <preview dir>

Adds a third toolbar state (106) with three tiles, OPEN / AUTO / CLOSE. Each tile is an image
(off or on) under a transparent button, the arrangement BMW-style plugins render reliably.
The buttons are focusable, so this page folds the side toolbar without a hidden focus target.
"""
import io
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from PIL import Image, ImageDraw, ImageFont

FONT = r"C:\Windows\Fonts\bahnschrift.ttf"
PANEL_BG = (23, 27, 34, 255)
COLOR = (186, 200, 216, 255)
ON_FILL = (255, 79, 26, 255)          # BMW Orange, the default gauge colour
ICON = (226, 234, 240, 255)
ORIGIN_X, ORIGIN_Y, PAGE_W = 24, 13, 1092
TILE_W, TILE_H, TILE_Y = 340, 230, 60
GAP = (PAGE_W - 3 * TILE_W) // 2
TILES = (("OPEN", "Flap held open"), ("AUTO", "DME decides"), ("CLOSE", "Flap held closed"))
FIRST_IMAGE = 56320
SCALE = 4


def font(size, variation=b"Regular"):
    face = ImageFont.truetype(FONT, size)
    face.set_variation_by_name(variation)
    return face


def tile(title, subtitle, on):
    big = Image.new("RGBA", (TILE_W * SCALE, TILE_H * SCALE), (0, 0, 0, 0))
    ImageDraw.Draw(big).rounded_rectangle((0, 0, TILE_W * SCALE - 1, TILE_H * SCALE - 1),
                                          radius=14 * SCALE, fill=ON_FILL if on else PANEL_BG)
    image = big.resize((TILE_W, TILE_H), Image.LANCZOS)
    draw = ImageDraw.Draw(image)
    text = (255, 255, 255, 255) if on else COLOR
    for face, words, y in ((font(52, b"SemiBold"), title, 70), (font(23), subtitle, 150)):
        box = face.getbbox(words)
        draw.text(((TILE_W - (box[2] - box[0])) // 2 - box[0], y - box[1]), words, font=face, fill=text)
    return image


def icon():
    size, s, w = 64 * SCALE, SCALE, 4 * SCALE
    big = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(big)
    draw.rounded_rectangle((4 * s, 26 * s, 40 * s, 42 * s), radius=3 * s, outline=ICON, width=w)  # pipe
    draw.ellipse((36 * s, 20 * s, 52 * s, 48 * s), outline=ICON, width=w)                         # tip
    draw.line((44 * s, 24 * s, 44 * s, 44 * s), fill=ICON, width=w)                              # flap
    for y in (22, 34, 46):                                                                         # gas
        draw.arc((50 * s, (y - 6) * s, 62 * s, (y + 6) * s), start=270, end=90, fill=ICON, width=3 * s)
    return big.resize((64, 64), Image.LANCZOS)


def props(element, values, image=False):
    holder = ET.SubElement(element, "properties")
    for identifier, value in list(values) + ([(2, "false"), (3, "true")] if image else []):
        ET.SubElement(holder, "property", id=str(identifier), value=str(value))


def layout(path):
    tree = ET.parse(path)
    app = tree.getroot().find("pluginApp")
    actions, models, states = app.find("actions"), app.find("models"), app.find("hmiStates")
    if any(s.get("id") == "106" for s in states):
        raise SystemExit("layout already has the flap page; start from the v9 layout")
    position = list(actions).index(actions.find("raAction"))
    actions.insert(position, ET.Element("hmiAction", id="38", target="106"))
    for identifier in (35, 36, 37):
        ET.SubElement(actions, "raAction", id=str(identifier))
    ET.SubElement(models, "imageIdModel", id="74", imageId="56313")
    ET.SubElement(models, "raDataModel", id="142", modelType="Richtext")
    ET.SubElement(models, "raDataModel", id="145", modelType="Richtext")
    for index in range(3):
        start = FIRST_IMAGE + index * 2 + (1 if index == 1 else 0)   # AUTO starts highlighted
        ET.SubElement(models, "imageIdModel", id=str(150 + index), imageId=str(start))
    # Third toolbar button on the existing pages.
    for state, ident in (("100", 444), ("105", 445)):
        toolbar = next(s for s in states if s.get("id") == state).find("toolbarComponents")
        ET.SubElement(toolbar, "button", {"id": str(ident), "imageModel": "74", "tooltipModel": "142",
                                          "text": "Exhaust flap", "action": "38"})
    flap = ET.SubElement(states, "toolbarHmiState", id="106", parentId="100", text="Exhaust flap")
    components = ET.SubElement(flap, "components")
    for index, action in enumerate((35, 36, 37)):
        x = ORIGIN_X + index * (TILE_W + GAP)
        geometry = ((20, x), (21, TILE_Y), (9, TILE_W), (10, TILE_H))
        props(ET.SubElement(components, "image", id=str(600 + index), model=str(150 + index)), geometry, True)
        props(ET.SubElement(components, "button", id=str(610 + index), action=str(action), imageModel="73"),
              geometry)
    props(ET.SubElement(components, "label", id="620", model="145"),
          ((20, ORIGIN_X + 10), (21, TILE_Y + TILE_H + 30), (9, PAGE_W - 20), (10, 50)))
    toolbar = ET.SubElement(flap, "toolbarComponents")
    ET.SubElement(toolbar, "button", {"id": "446", "imageModel": "71", "tooltipModel": "140",
                                      "text": "Engine", "action": "34"})
    ET.SubElement(toolbar, "button", {"id": "447", "imageModel": "72", "tooltipModel": "141",
                                      "text": "Hybrid", "action": "32"})
    ET.SubElement(toolbar, "button", {"id": "448", "imageModel": "74", "tooltipModel": "142",
                                      "text": "Exhaust flap"})
    ids = [e.get("id") for s in states for group in s for e in group]
    assert len(ids) == len(set(ids)), "duplicate component id"
    model_ids = [m.get("id") for m in models]
    assert len(model_ids) == len(set(model_ids)), "duplicate model id"
    ET.indent(tree, space="  ")
    tree.write(path, encoding="utf-8", xml_declaration=True)
    print("layout: states", [(s.tag, s.get("id")) for s in states], "components", len(ids))


def artwork(source, output, preview):
    new = {"56313.png": icon()}
    for index, (title, subtitle) in enumerate(TILES):
        new[f"{FIRST_IMAGE + index * 2}.png"] = tile(title, subtitle, False)
        new[f"{FIRST_IMAGE + index * 2 + 1}.png"] = tile(title, subtitle, True)
    Path(preview).mkdir(parents=True, exist_ok=True)
    sheet = Image.new("RGBA", (PAGE_W + 100, 2 * (TILE_H + 20) + 20), (60, 70, 90, 255))
    sheet.paste(new["56313.png"], (18, 20), new["56313.png"])
    for index in range(3):
        for row in range(2):
            image = new[f"{FIRST_IMAGE + index * 2 + row}.png"]
            sheet.paste(image, (100 + index * (TILE_W + GAP), 20 + row * (TILE_H + 20)), image)
    sheet.save(Path(preview) / "flap_sheet.png")
    with zipfile.ZipFile(source) as src:
        infos = src.infolist()
        if any(i.filename in new for i in infos):
            raise SystemExit("archive already has flap images; start from the v9 archive")
        reference = next(i for i in infos if i.filename == "56300.png")
        with zipfile.ZipFile(output, "w") as dst:
            def write(name, data, like):
                clone = zipfile.ZipInfo(name, like.date_time)
                clone.compress_type, clone.external_attr, clone.create_system = (
                    like.compress_type, like.external_attr, like.create_system)
                dst.writestr(clone, data)
            for info in infos:
                write(info.filename, src.read(info.filename), info)
            for name, image in new.items():
                buffer = io.BytesIO()
                image.save(buffer, format="PNG", optimize=True)
                write(name, buffer.getvalue(), reference)
    with zipfile.ZipFile(source) as a, zipfile.ZipFile(output) as b:
        same = all(a.read(i.filename) == b.read(i.filename) for i in a.infolist())
        print("artwork: entries", len(b.infolist()), "existing images unchanged:", same)


if __name__ == "__main__":
    layout(sys.argv[1])
    artwork(sys.argv[2], sys.argv[3], sys.argv[4])
