"""Build the v7 BoostDeck layout and artwork: a left-side toolbar (Engine / Hybrid) on both pages.

Usage: make_toolbar_assets.py <BoostDeck.xml in/out (v6)> <images zip in (v6)> <images zip out> <preview dir>

BMW's own plugin apps on this head unit (ActiveSeating, SecurityMenu) use <toolbarHmiState> with
<toolbarComponents>; this follows their structure. The toolbar takes the left edge of the screen,
so both pages are redrawn 80 px narrower and start at x = 104.
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
ICON = (226, 234, 240, 255)
# Where the page background sits. In a toolbar state the content area already starts to the
# right of the icon column (seen on the car with v7), so no extra left offset is needed.
ORIGIN_X, ORIGIN_Y = 24, 13
TILE_W, TILE_H, GAP, SIDE_W = 220, 192, 18, 140
PITCH_X, PITCH_Y = TILE_W + GAP, TILE_H + 16
WIDTH, HEIGHT = 4 * TILE_W + 4 * GAP + SIDE_W, 400
SIDE_X = 4 * PITCH_X
OLD_PITCH, OLD_FIRST = 258, 39        # v6 geometry: tile pitch and first bar/label x
PAGES = {
    "56300.png": ("BOOST", "AFR", "TIMING", "INTAKE AIR", "TRANSMISSION", "RAIL PRESSURE",
                  "OIL PRESSURE", "COOLANT"),
    "56301.png": ("ELECTRIC RANGE", "PETROL RANGE", "TOTAL RANGE", "FUEL LEVEL",
                  "HV VOLTAGE", "12 V BATTERY", "OIL TEMP", "OUTSIDE TEMP"),
}
SCALE = 4


def font(size):
    face = ImageFont.truetype(FONT, size)
    face.set_variation_by_name(b"Regular")
    return face


def background(captions):
    big = Image.new("RGBA", (WIDTH * SCALE, HEIGHT * SCALE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(big)
    for column in range(4):
        for row in range(2):
            x, y = column * PITCH_X, row * PITCH_Y
            draw.rounded_rectangle((x * SCALE, y * SCALE, (x + TILE_W) * SCALE - 1, (y + TILE_H) * SCALE - 1),
                                   radius=14 * SCALE, fill=PANEL_BG)
    draw.rounded_rectangle((SIDE_X * SCALE, 0, (SIDE_X + SIDE_W) * SCALE - 1, HEIGHT * SCALE - 1),
                           radius=14 * SCALE, fill=PANEL_BG)
    image = big.resize((WIDTH, HEIGHT), Image.LANCZOS)
    draw = ImageDraw.Draw(image)
    face = font(23)
    widest = 0
    for index, caption in enumerate(captions):
        x, y = (index // 2) * PITCH_X, (index % 2) * PITCH_Y
        box = face.getbbox(caption)
        draw.text((x + 16 - box[0], y + 26 - box[1]), caption, font=face, fill=COLOR)
        widest = max(widest, box[2] - box[0])
    box = face.getbbox("HV BATT")
    draw.text((SIDE_X + (SIDE_W - (box[2] - box[0])) // 2 - box[0], 21 - box[1]), "HV BATT", font=face, fill=COLOR)
    assert widest <= TILE_W - 28, f"caption too wide: {widest}"
    return image


def icon(kind):
    size = 64 * SCALE
    big = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(big)
    s, w = SCALE, 4 * SCALE
    if kind == "engine":   # a dial with a needle
        draw.arc((8 * s, 12 * s, 56 * s, 60 * s), start=150, end=390, fill=ICON, width=w)
        draw.line((32 * s, 36 * s, 45 * s, 22 * s), fill=ICON, width=w)
        draw.ellipse((28 * s, 32 * s, 36 * s, 40 * s), fill=ICON)
    else:                  # a battery with a lightning bolt
        draw.rounded_rectangle((6 * s, 20 * s, 52 * s, 46 * s), radius=4 * s, outline=ICON, width=w)
        draw.rectangle((52 * s, 28 * s, 58 * s, 38 * s), fill=ICON)
        draw.polygon(((32 * s, 23 * s), (22 * s, 34 * s), (29 * s, 34 * s), (26 * s, 43 * s),
                      (37 * s, 31 * s), (30 * s, 31 * s)), fill=ICON)
    return big.resize((64, 64), Image.LANCZOS)


def png(image):
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def set_property(component, identifier, value):
    for prop in component.find("properties"):
        if prop.get("id") == str(identifier):
            prop.set("value", str(value))
            return
    raise SystemExit(f"component {component.get('id')} has no property {identifier}")


def get_property(component, identifier):
    return int(next(p.get("value") for p in component.find("properties") if p.get("id") == str(identifier)))


def layout(path):
    tree = ET.parse(path)
    app = tree.getroot().find("pluginApp")
    actions, models, states = app.find("actions"), app.find("models"), app.find("hmiStates")
    by_id = {s.get("id"): s for s in states}
    if "110" not in by_id or states.find("toolbarHmiState") is not None:
        raise SystemExit("expected the v6 layout (menu screen, no toolbar yet)")
    states.remove(by_id["110"])
    for action in actions.findall("hmiAction"):
        if action.get("id") == "10":
            action.set("target", "100")
    ET.SubElement(models, "imageIdModel", id="71", imageId="56310")
    ET.SubElement(models, "imageIdModel", id="72", imageId="56311")
    ET.SubElement(models, "imageIdModel", id="73", imageId="56312")       # transparent focus target
    ET.SubElement(models, "raDataModel", id="140", modelType="Richtext")  # toolbar label "Engine"
    ET.SubElement(models, "raDataModel", id="141", modelType="Richtext")  # toolbar label "Hybrid"
    engine, hybrid = by_id["100"], by_id["105"]
    for state, attrs in ((engine, {"id": "100", "text": "Engine"}),
                         (hybrid, {"id": "105", "parentId": "100", "text": "Hybrid"})):
        state.tag = "toolbarHmiState"
        state.attrib.clear()
        state.attrib.update(attrs)
        for component in state.find("components"):
            ident = int(component.get("id"))
            if component.tag == "button":
                continue
            if ident in (209, 509):                               # page background
                set_property(component, 20, ORIGIN_X)
                set_property(component, 9, WIDTH)
            elif ident in (208, 508):                             # HV bar, centred in its column
                set_property(component, 20, ORIGIN_X + SIDE_X + 50)
            elif ident in (158, 528):                             # HV percentage label
                set_property(component, 20, ORIGIN_X + SIDE_X + 24)
            else:                                                 # tile bar or value label
                column = (get_property(component, 20) - OLD_FIRST) // OLD_PITCH
                set_property(component, 20, ORIGIN_X + 15 + column * PITCH_X)
                set_property(component, 9, 190 if component.tag == "image" else 196)
        here = state is engine
        # The toolbar only folds away when focus can move into the page, and these pages had
        # nothing focusable. This transparent button gives focus somewhere to go and opens Gauge
        # color. The HMI draws a focus frame on top of everything (seen on the car with v8), so
        # the button is a single pixel tucked into the rounded bottom-right corner of the page.
        focus = ET.Element("button", {"id": "450" if here else "451", "action": "31", "imageModel": "73"})
        props = ET.SubElement(focus, "properties")
        for identifier, value in ((20, ORIGIN_X + WIDTH - 2), (21, ORIGIN_Y + HEIGHT - 2), (9, 1), (10, 1)):
            ET.SubElement(props, "property", id=str(identifier), value=str(value))
        state.find("components").insert(0, focus)
        toolbar = ET.SubElement(state, "toolbarComponents")
        first = 440 if here else 442
        # The button for the page you are on has no action; the other one switches page.
        ET.SubElement(toolbar, "button", {"id": str(first), "imageModel": "71", "tooltipModel": "140",
                                          "text": "Engine", **({} if here else {"action": "34"})})
        ET.SubElement(toolbar, "button", {"id": str(first + 1), "imageModel": "72", "tooltipModel": "141",
                                          "text": "Hybrid", **({"action": "32"} if here else {})})
    ids = [e.get("id") for s in states for group in s for e in group]
    assert len(ids) == len(set(ids)), "duplicate component id"
    ET.indent(tree, space="  ")
    tree.write(path, encoding="utf-8", xml_declaration=True)
    print("layout: states", [(s.tag, s.get("id")) for s in states], "components", len(ids))


def artwork(source, output, preview):
    new = {name: background(captions) for name, captions in PAGES.items()}
    new["56310.png"], new["56311.png"] = icon("engine"), icon("hybrid")
    new["56312.png"] = Image.new("RGBA", (112, 63), (0, 0, 0, 0))
    Path(preview).mkdir(parents=True, exist_ok=True)
    for name, image in new.items():
        image.save(Path(preview) / name)
    with zipfile.ZipFile(source) as src:
        infos = src.infolist()
        reference = next(i for i in infos if i.filename == "56300.png")
        with zipfile.ZipFile(output, "w") as dst:
            def write(name, data, like):
                clone = zipfile.ZipInfo(name, like.date_time)
                clone.compress_type, clone.external_attr, clone.create_system = (
                    like.compress_type, like.external_attr, like.create_system)
                dst.writestr(clone, data)
            for info in infos:
                write(info.filename, png(new[info.filename]) if info.filename in new else src.read(info.filename), info)
            for name in ("56310.png", "56311.png", "56312.png"):
                write(name, png(new[name]), reference)
    with zipfile.ZipFile(source) as a, zipfile.ZipFile(output) as b:
        changed = [i.filename for i in a.infolist() if a.read(i.filename) != b.read(i.filename)]
        print("artwork: entries", len(b.infolist()), "changed", changed, "size", (WIDTH, HEIGHT))


if __name__ == "__main__":
    layout(sys.argv[1])
    artwork(sys.argv[2], sys.argv[3], sys.argv[4])
