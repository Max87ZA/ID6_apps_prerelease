"""Build the v6 BoostDeck layout and artwork: app renamed, a menu entry screen, and a tiled Hybrid page.

Usage: make_hybrid_assets.py <BoostDeck.xml in/out> <images zip in> <images zip out> <preview png>
The Hybrid page copies the gauge page's geometry, so both screens line up exactly.
"""
import copy
import io
import sys
import zipfile
from xml.etree import ElementTree as ET

from PIL import Image, ImageDraw, ImageFont

APP_NAME = "Elina's Dashboard"
FONT = r"C:\Windows\Fonts\bahnschrift.ttf"
PANEL_BG = (23, 27, 34, 255)
COLOR = (186, 200, 216, 255)
# Captions in tile order: column by column, top then bottom (same order as the gauge page).
CAPTIONS = ("ELECTRIC RANGE", "PETROL RANGE", "TOTAL RANGE", "FUEL LEVEL",
            "HV VOLTAGE", "12 V BATTERY", "OIL TEMP", "OUTSIDE TEMP")
COLUMNS, ROWS = (0, 258, 516, 774), (0, 208)


def layout(path):
    tree = ET.parse(path)
    app = tree.getroot().find("pluginApp")
    app.set("text", APP_NAME)
    actions, models, states = app.find("actions"), app.find("models"), app.find("hmiStates")
    by_id = {s.get("id"): s for s in states.findall("hmiState")}
    if "110" in by_id:
        raise SystemExit("layout already has the menu screen; start from the v5 file")
    # Navigation: entry button -> menu (110) -> Engine (100) or Hybrid (105).
    for action in actions.findall("hmiAction"):
        if action.get("id") == "10":
            action.set("target", "110")
    position = list(actions).index(actions.find("raAction"))
    actions.insert(position, ET.Element("hmiAction", id="34", target="100"))
    engine, hybrid = by_id["100"], by_id["105"]
    for state, title in ((engine, "Engine"), (hybrid, "Hybrid")):
        state.attrib.clear()
        state.attrib.update(id="100" if state is engine else "105", parentId="110", text=title)
    options = engine.find("optionComponents")
    for button in options.findall("button"):
        if button.get("action") == "32":
            options.remove(button)
    menu = ET.Element("hmiState", id="110", text=APP_NAME)
    entries = ET.SubElement(menu, "components")
    ET.SubElement(entries, "button", id="430", action="34", text="Engine")
    ET.SubElement(entries, "button", id="431", action="32", text="Hybrid")
    states.insert(0, menu)
    # Models: three more value labels, eight bar images, the page background, and the HV bar copy.
    for identifier in (125, 126, 127, 128):
        ET.SubElement(models, "raDataModel", id=str(identifier), modelType="Richtext")
    for identifier in range(130, 138):
        ET.SubElement(models, "imageIdModel", id=str(identifier), imageId="55000")
    ET.SubElement(models, "imageIdModel", id="138", imageId="56100")
    ET.SubElement(models, "imageIdModel", id="70", imageId="56301")
    # Hybrid page components: a remapped copy of the gauge page.
    components = hybrid.find("components")
    for child in list(components):
        components.remove(child)
    for source in engine.find("components"):
        clone = copy.deepcopy(source)
        ident, model = int(source.get("id")), int(source.get("model"))
        if source.tag == "image" and ident == 209:
            clone.set("id", "509"); clone.set("model", "70")
        elif source.tag == "image" and 200 <= ident <= 207:
            clone.set("id", str(ident + 300)); clone.set("model", str(model + 70))
        elif source.tag == "image" and ident == 208:
            clone.set("id", "508"); clone.set("model", "138")
        elif source.tag == "label" and 150 <= ident <= 157:
            clone.set("id", str(ident + 370)); clone.set("model", str(model + 70))
        elif source.tag == "label" and ident == 158:
            clone.set("id", "528"); clone.set("model", "128")
        else:
            raise SystemExit(f"unexpected gauge page component {source.tag} {ident}")
        components.append(clone)
    ids = [e.get("id") for s in states for group in s for e in group]
    assert len(ids) == len(set(ids)), "duplicate component id"
    model_ids = [m.get("id") for m in models]
    assert len(model_ids) == len(set(model_ids)), "duplicate model id"
    ET.indent(tree, space="  ")
    tree.write(path, encoding="utf-8", xml_declaration=True)
    print("layout: states", [s.get("id") for s in states], "components", len(ids), "models", len(model_ids))


def artwork(source, output, preview):
    with zipfile.ZipFile(source) as src:
        infos = src.infolist()
        if any(i.filename == "56301.png" for i in infos):
            raise SystemExit("archive already has 56301.png; start from the v4 archive")
        image = Image.open(io.BytesIO(src.read("56300.png"))).convert("RGBA")
        draw = ImageDraw.Draw(image)
        font = ImageFont.truetype(FONT, 26)
        font.set_variation_by_name(b"Regular")
        widest = 0
        for index, caption in enumerate(CAPTIONS):
            x0, y0 = COLUMNS[index // 2], ROWS[index % 2]
            draw.rectangle((x0 + 10, y0 + 15, x0 + 232, y0 + 52), fill=PANEL_BG)
            box = font.getbbox(caption)
            draw.text((x0 + 18 - box[0], y0 + 25 - box[1]), caption, font=font, fill=COLOR)
            widest = max(widest, box[2] - box[0])
        print("artwork: widest caption", widest, "px of 214 available")
        image.save(preview)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG", optimize=True)
        reference = next(i for i in infos if i.filename == "56300.png")
        with zipfile.ZipFile(output, "w") as dst:
            for info in infos:
                clone = zipfile.ZipInfo(info.filename, info.date_time)
                clone.compress_type, clone.external_attr, clone.create_system = (
                    info.compress_type, info.external_attr, info.create_system)
                dst.writestr(clone, src.read(info.filename))
            extra = zipfile.ZipInfo("56301.png", reference.date_time)
            extra.compress_type, extra.external_attr, extra.create_system = (
                reference.compress_type, reference.external_attr, reference.create_system)
            dst.writestr(extra, buffer.getvalue())
    with zipfile.ZipFile(source) as a, zipfile.ZipFile(output) as b:
        same = all(a.read(i.filename) == b.read(i.filename) for i in a.infolist())
        print("artwork: entries", len(b.infolist()), "existing images unchanged:", same)


if __name__ == "__main__":
    layout(sys.argv[1])
    artwork(sys.argv[2], sys.argv[3], sys.argv[4])
