"""Generate depth reference silhouettes for wide/squat body class.

Wide/squat creatures are broad, low, and heavy — stone golems, idols,
squatting statues. The depth guide is a short wide pillar or block
that prevents the model from elongating into a humanoid shape.

Target creatures: Grinning Idol, Clock Golem, Bell Warden

Shape philosophy:
- Width > height (inverted from humanoid proportions)
- Flat or domed top — no tall head
- Heavy base for grounding
- Slight taper upward (pyramid feel) for visual stability
- No limb stubs — arms/legs emerge from the broad form naturally
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


def draw_wide_squat(direction):
    """Draw a wide, low block/pillar — heavy and grounded.

    The shape is a tapered trapezoid with a domed or flat top.
    Wider at the base, slightly narrower at the shoulders.
    Front/back show the broad face; side views show depth.
    """
    img = Image.new("L", (GEN_WIDTH, GEN_HEIGHT), 0)
    draw = ImageDraw.Draw(img)
    cx, cy = GEN_WIDTH / 2, GEN_HEIGHT * 0.55  # low center of mass

    # Dimensions — wide and short
    base_w = GEN_WIDTH * 0.52   # very wide
    base_h = GEN_HEIGHT * 0.32  # short
    top_w = base_w * 0.80       # tapers inward at top

    if direction in ("front", "back"):
        # Broad face — trapezoidal body with domed top
        top_y = cy - base_h / 2
        bot_y = cy + base_h / 2

        # Main body — trapezoid via polygon
        draw.polygon([
            (cx - base_w/2, bot_y),      # bottom-left
            (cx - top_w/2, top_y),       # top-left
            (cx + top_w/2, top_y),       # top-right
            (cx + base_w/2, bot_y),      # bottom-right
        ], fill=200)

        # Domed top — slight rounded cap
        draw.ellipse([cx - top_w*0.45, top_y - base_h*0.15,
                      cx + top_w*0.45, top_y + base_h*0.15], fill=220)

        # Heavy base spread
        draw.ellipse([cx - base_w*0.55, bot_y - base_h*0.12,
                      cx + base_w*0.55, bot_y + base_h*0.15], fill=175)

        if direction == "front":
            # Face region — darker indent in upper center
            draw.ellipse([cx - top_w*0.20, top_y + base_h*0.05,
                          cx + top_w*0.20, top_y + base_h*0.25], fill=230)

        # Shoulder masses — wide blocky shoulders
        draw.ellipse([cx - base_w*0.55, cy - base_h*0.30,
                      cx - base_w*0.20, cy + base_h*0.05], fill=180)
        draw.ellipse([cx + base_w*0.20, cy - base_h*0.30,
                      cx + base_w*0.55, cy + base_h*0.05], fill=180)

    elif direction in ("left", "right"):
        # Side profile — shows depth (narrower than front)
        facing_left = direction == "left"
        sign = -1 if facing_left else 1
        side_w = base_w * 0.65  # narrower in profile
        top_y = cy - base_h / 2
        bot_y = cy + base_h / 2

        # Main body
        draw.polygon([
            (cx - side_w/2, bot_y),
            (cx - side_w*0.40, top_y),
            (cx + side_w*0.40, top_y),
            (cx + side_w/2, bot_y),
        ], fill=200)

        # Dome top
        draw.ellipse([cx - side_w*0.35, top_y - base_h*0.12,
                      cx + side_w*0.35, top_y + base_h*0.12], fill=220)

        # Leading face
        face_cx = cx - sign * side_w * 0.25
        draw.ellipse([face_cx - side_w*0.15, top_y + base_h*0.08,
                      face_cx + side_w*0.15, top_y + base_h*0.28], fill=225)

        # Base spread
        draw.ellipse([cx - side_w*0.50, bot_y - base_h*0.10,
                      cx + side_w*0.50, bot_y + base_h*0.12], fill=175)

    else:  # 3/4 views
        facing_left = "left" in direction
        show_front = "front" in direction
        sign = -1 if facing_left else 1
        off = sign * base_w * 0.06
        view_w = base_w * 0.85
        top_y = cy - base_h / 2
        bot_y = cy + base_h / 2

        # Main body — shifted
        draw.polygon([
            (cx - view_w/2 - off, bot_y),
            (cx - view_w*0.40 - off, top_y),
            (cx + view_w*0.40 - off, top_y),
            (cx + view_w/2 - off, bot_y),
        ], fill=200)

        # Dome
        draw.ellipse([cx - view_w*0.38 - off, top_y - base_h*0.13,
                      cx + view_w*0.38 - off, top_y + base_h*0.13], fill=220)

        if show_front:
            face_cx = cx - sign * view_w * 0.15
            draw.ellipse([face_cx - view_w*0.14, top_y + base_h*0.06,
                          face_cx + view_w*0.14, top_y + base_h*0.24], fill=228)

        # Shoulder mass on visible side
        shoulder_cx = cx + sign * view_w * 0.30
        draw.ellipse([shoulder_cx - view_w*0.15, cy - base_h*0.25,
                      shoulder_cx + view_w*0.15, cy + base_h*0.05], fill=178)

        # Base
        draw.ellipse([cx - view_w*0.50 - off, bot_y - base_h*0.10,
                      cx + view_w*0.50 - off, bot_y + base_h*0.13], fill=175)

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
    print("Generating wide/squat body class depth refs...")
    gen_set("wide_squat", draw_wide_squat)
    print("Done.")
