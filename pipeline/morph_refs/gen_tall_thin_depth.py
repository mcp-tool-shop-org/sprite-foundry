"""Generate depth reference silhouettes for tall/thin body class.

Tall/thin creatures are elongated, narrow, spindly — lanky predators,
root puppets, stalker creatures. The depth guide is a narrow vertical
column that encourages height while suppressing width.

Target creatures: Lantern Angler, Root Puppet, Ink Shade, Mirror Stalker

Shape philosophy:
- Height >> width (opposite of wide/squat)
- Narrow torso tapering to thin limbs
- Slight head bulge at top (not a human head, just a mass)
- Very minimal horizontal spread — the model adds arms/limbs freely
- Slightly forward lean to suggest predatory posture
"""

from PIL import Image, ImageDraw
from pathlib import Path

OUT_BASE = Path(__file__).parent
GEN_WIDTH = 576
GEN_HEIGHT = 768


def _soften(img):
    small = img.resize((GEN_WIDTH // 4, GEN_HEIGHT // 4), Image.LANCZOS)
    return small.resize((GEN_WIDTH, GEN_HEIGHT), Image.LANCZOS)


def _make_sheet(out_dir, directions):
    CELL = 192
    PAD = 4
    sheet_w = len(directions) * (CELL + PAD) + PAD
    sheet_h = CELL + PAD * 2 + 20
    sheet = Image.new("L", (sheet_w, sheet_h), 0)
    for i, d in enumerate(directions):
        ref = Image.open(out_dir / f"{d}_depth_ref.png")
        w, h = ref.size
        top = (h - w) // 4
        cropped = ref.crop((0, top, w, top + w))
        cell = cropped.resize((CELL, CELL), Image.LANCZOS)
        sheet.paste(cell, (PAD + i * (CELL + PAD), PAD + 20))
    sheet.save(str(out_dir / "depth_ref_sheet.png"))


def draw_tall_thin(direction):
    """Draw a narrow vertical column — tall, spindly, predatory.

    The shape is a tapered vertical ellipse with a slight head bulge.
    Very narrow compared to frame width. Slightly forward-leaning.
    """
    img = Image.new("L", (GEN_WIDTH, GEN_HEIGHT), 0)
    draw = ImageDraw.Draw(img)
    cx, cy = GEN_WIDTH / 2, GEN_HEIGHT * 0.48  # slightly high center (tall creature)

    # Dimensions — narrow and very tall
    body_w = GEN_WIDTH * 0.16   # very narrow
    body_h = GEN_HEIGHT * 0.38  # tall torso
    head_w = GEN_WIDTH * 0.10   # small head bulge
    head_h = GEN_HEIGHT * 0.07
    leg_h = GEN_HEIGHT * 0.18   # long thin legs
    leg_w = body_w * 0.30       # thin legs

    if direction in ("front", "back"):
        # Narrow vertical column with head bulge
        # Main torso — tall narrow ellipse
        draw.ellipse([cx - body_w/2, cy - body_h/2,
                      cx + body_w/2, cy + body_h/2], fill=195)

        # Upper torso narrowing (shoulder region)
        draw.ellipse([cx - body_w*0.55, cy - body_h*0.40,
                      cx + body_w*0.55, cy - body_h*0.10], fill=205)

        if direction == "front":
            # Head — small bulge at top, not a human head shape
            draw.ellipse([cx - head_w/2, cy - body_h/2 - head_h*1.2,
                          cx + head_w/2, cy - body_h/2 + head_h*0.3], fill=230)
            # Neck connector
            draw.rectangle([cx - body_w*0.12, cy - body_h/2 - head_h*0.3,
                            cx + body_w*0.12, cy - body_h/2 + 5], fill=190)

        # Thin legs — two narrow columns
        for lx in [cx - body_w*0.25, cx + body_w*0.25]:
            draw.rectangle([lx - leg_w/2, cy + body_h/2 - 5,
                            lx + leg_w/2, cy + body_h/2 + leg_h], fill=165)
            # Lower leg taper
            draw.rectangle([lx - leg_w*0.35, cy + body_h/2 + leg_h*0.5,
                            lx + leg_w*0.35, cy + body_h/2 + leg_h*1.1], fill=150)

    elif direction in ("left", "right"):
        facing_left = direction == "left"
        sign = -1 if facing_left else 1

        # Side profile — even narrower, with forward lean
        side_w = body_w * 0.75
        lean = sign * body_w * 0.15  # slight forward lean

        # Main torso
        draw.ellipse([cx - side_w/2 - lean*0.3, cy - body_h/2,
                      cx + side_w/2 - lean*0.3, cy + body_h/2], fill=195)

        # Head — offset forward
        head_cx = cx - sign * side_w * 0.3 - lean*0.5
        draw.ellipse([head_cx - head_w*0.45, cy - body_h/2 - head_h*1.1,
                      head_cx + head_w*0.45, cy - body_h/2 + head_h*0.3], fill=230)
        # Neck
        draw.rectangle([head_cx - body_w*0.10, cy - body_h/2 - head_h*0.2,
                        head_cx + body_w*0.10, cy - body_h/2 + 5], fill=190)

        # Single visible leg (or slightly overlapping pair)
        lx = cx - lean*0.2
        draw.rectangle([lx - leg_w*0.45, cy + body_h/2 - 5,
                        lx + leg_w*0.45, cy + body_h/2 + leg_h], fill=165)
        draw.rectangle([lx - leg_w*0.30, cy + body_h/2 + leg_h*0.5,
                        lx + leg_w*0.30, cy + body_h/2 + leg_h*1.1], fill=150)

    else:  # 3/4 views
        facing_left = "left" in direction
        show_front = "front" in direction
        sign = -1 if facing_left else 1
        off = sign * body_w * 0.12
        view_w = body_w * 0.90

        # Main torso
        draw.ellipse([cx - view_w/2 - off, cy - body_h/2,
                      cx + view_w/2 - off, cy + body_h/2], fill=195)

        # Shoulder region
        draw.ellipse([cx - view_w*0.50 - off, cy - body_h*0.38,
                      cx + view_w*0.50 - off, cy - body_h*0.08], fill=205)

        if show_front:
            # Head
            head_cx = cx - sign * view_w * 0.15 - off
            draw.ellipse([head_cx - head_w*0.45, cy - body_h/2 - head_h*1.1,
                          head_cx + head_w*0.45, cy - body_h/2 + head_h*0.3], fill=230)
            draw.rectangle([head_cx - body_w*0.10, cy - body_h/2 - head_h*0.2,
                            head_cx + body_w*0.10, cy - body_h/2 + 5], fill=190)

        # Legs
        for loff in [-0.12, 0.12]:
            lx = cx + view_w * loff - off
            draw.rectangle([lx - leg_w*0.40, cy + body_h/2 - 5,
                            lx + leg_w*0.40, cy + body_h/2 + leg_h], fill=165)
            draw.rectangle([lx - leg_w*0.28, cy + body_h/2 + leg_h*0.5,
                            lx + leg_w*0.28, cy + body_h/2 + leg_h*1.1], fill=150)

    return _soften(img)


DIRECTIONS = [
    "front", "front_left", "left", "back_left",
    "back", "back_right", "right", "front_right",
]


def gen_set(name, draw_fn):
    out_dir = OUT_BASE / f"{name}_depth"
    out_dir.mkdir(parents=True, exist_ok=True)
    for d in DIRECTIONS:
        img = draw_fn(d)
        img.save(str(out_dir / f"{d}_depth_ref.png"))
    _make_sheet(out_dir, DIRECTIONS)
    print(f"  {name}: {out_dir}")


if __name__ == "__main__":
    print("Generating tall/thin body class depth refs...")
    gen_set("tall_thin", draw_tall_thin)
    print("Done.")
