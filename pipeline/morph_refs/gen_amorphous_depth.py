"""Generate depth reference silhouettes for amorphous body class.

Amorphous creatures have no defined skeleton — they're masses, colonies,
mounds, or oozes. The depth guide is a rough oval/blob that indicates
occupied volume without implying limbs or joints.

Target creatures: Rat King, Spore Mother, Mud Revenant, Hive Keeper

Shape philosophy:
- Center-heavy irregular mass, slightly bottom-weighted for grounding
- No limb stubs — the model invents appendages freely
- Mild directional asymmetry (front views slightly taller, side views wider)
- Softer blur than humanoid refs to allow more creative freedom
"""

from PIL import Image, ImageDraw
from pathlib import Path
import random
import math

OUT_BASE = Path(__file__).parent
GEN_WIDTH = 576
GEN_HEIGHT = 768


def _soften(img):
    """4x downsample + re-expand for gaussian-like blur."""
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


def draw_amorphous(direction):
    """Draw an irregular blob mass — no limbs, no skeleton.

    The blob is built from overlapping ellipses to create organic irregularity.
    Front/back views are taller, side views are wider, 3/4 views are in between.
    """
    img = Image.new("L", (GEN_WIDTH, GEN_HEIGHT), 0)
    draw = ImageDraw.Draw(img)
    cx, cy = GEN_WIDTH / 2, GEN_HEIGHT * 0.52  # slightly below center for grounding

    # Base mass dimensions — wide and squat, not tall
    base_w = GEN_WIDTH * 0.42
    base_h = GEN_HEIGHT * 0.30

    if direction in ("front", "back"):
        # Slightly taller, narrower — facing/away from viewer
        w = base_w * 0.90
        h = base_h * 1.10
        # Main mass — large central blob
        draw.ellipse([cx - w/2, cy - h/2, cx + w/2, cy + h/2], fill=200)
        # Upper lobe (head region — just a bulge, not a head)
        draw.ellipse([cx - w*0.35, cy - h*0.65, cx + w*0.35, cy - h*0.15], fill=220)
        # Lower spread (grounding mass)
        draw.ellipse([cx - w*0.55, cy + h*0.05, cx + w*0.55, cy + h*0.50], fill=170)
        # Irregular side bulges
        draw.ellipse([cx - w*0.65, cy - h*0.10, cx - w*0.20, cy + h*0.25], fill=160)
        draw.ellipse([cx + w*0.20, cy - h*0.15, cx + w*0.60, cy + h*0.20], fill=155)

    elif direction in ("left", "right"):
        # Wider in profile — the mass spreads horizontally
        facing_left = direction == "left"
        sign = -1 if facing_left else 1
        w = base_w * 1.15
        h = base_h * 0.95
        # Main mass
        draw.ellipse([cx - w/2, cy - h/2, cx + w/2, cy + h/2], fill=200)
        # Leading bulge (front of creature, whichever direction it faces)
        lead_cx = cx - sign * w * 0.30
        draw.ellipse([lead_cx - w*0.25, cy - h*0.50, lead_cx + w*0.25, cy - h*0.05], fill=220)
        # Trailing mass
        trail_cx = cx + sign * w * 0.25
        draw.ellipse([trail_cx - w*0.20, cy - h*0.10, trail_cx + w*0.30, cy + h*0.35], fill=165)
        # Ground spread
        draw.ellipse([cx - w*0.50, cy + h*0.10, cx + w*0.50, cy + h*0.48], fill=170)

    else:  # 3/4 views
        facing_left = "left" in direction
        show_front = "front" in direction
        sign = -1 if facing_left else 1
        w = base_w * 1.0
        h = base_h * 1.0
        # Offset center toward facing direction
        off = sign * w * 0.08
        # Main mass
        draw.ellipse([cx - w/2 - off, cy - h/2, cx + w/2 - off, cy + h/2], fill=200)
        # Upper lobe — shifted toward facing direction
        lobe_cx = cx - sign * w * 0.15
        draw.ellipse([lobe_cx - w*0.30, cy - h*0.55, lobe_cx + w*0.30, cy - h*0.05], fill=215)
        # Side bulge on the visible flank
        flank_cx = cx + sign * w * 0.25
        draw.ellipse([flank_cx - w*0.18, cy - h*0.15, flank_cx + w*0.22, cy + h*0.25], fill=160)
        # Ground spread
        draw.ellipse([cx - w*0.50 - off, cy + h*0.05, cx + w*0.50 - off, cy + h*0.45], fill=170)

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
    print("Generating amorphous body class depth refs...")
    gen_set("amorphous", draw_amorphous)
    print("Done.")
