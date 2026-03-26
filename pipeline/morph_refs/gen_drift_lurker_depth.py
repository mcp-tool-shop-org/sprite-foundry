"""Generate depth reference silhouettes for the Drift Lurker.

A low-slung predatory quadruped — leaner and lower than Cargo Beast,
wider stance, head thrust forward, long whip tail, armored dorsal ridge.

8 directions, matching the foundry's standard direction set.
"""

from PIL import Image, ImageDraw
from pathlib import Path

OUT_DIR = Path(__file__).parent / "drift_lurker_depth"
GEN_WIDTH = 576
GEN_HEIGHT = 768

# Body proportions — leaner and lower than Cargo Beast
BODY_W = 0.50   # body width (slightly narrower than cargo beast)
BODY_H = 0.13   # body height (very low, flat predator)
LEG_H = 0.10    # shorter legs — low to ground
HEAD_W = 0.20   # wider wedge head
HEAD_H = 0.10   # flat head
TAIL_W = 0.28   # long whip tail
TAIL_H = 0.04   # thin tail
RIDGE_H = 0.04  # dorsal ridge height above body

# Vertical center — creature sits in lower-center of portrait frame
CENTER_Y = 0.58  # lower than cargo beast — crouched


def draw_lurker_depth(direction: str) -> Image.Image:
    img = Image.new("L", (GEN_WIDTH, GEN_HEIGHT), 0)
    draw = ImageDraw.Draw(img)

    cx = GEN_WIDTH / 2
    cy = GEN_HEIGHT * CENTER_Y

    bw = GEN_WIDTH * BODY_W
    bh = GEN_HEIGHT * BODY_H
    lh = GEN_HEIGHT * LEG_H
    hw = GEN_WIDTH * HEAD_W
    hh = GEN_HEIGHT * HEAD_H
    tw = GEN_WIDTH * TAIL_W
    th = GEN_HEIGHT * TAIL_H
    rh = GEN_HEIGHT * RIDGE_H

    if direction == "front":
        _draw_front(draw, cx, cy, bw, bh, lh, hw, hh, rh)
    elif direction == "back":
        _draw_back(draw, cx, cy, bw, bh, lh, tw, th, rh)
    elif direction == "left":
        _draw_side(draw, cx, cy, bw, bh, lh, hw, hh, tw, th, rh, facing_left=True)
    elif direction == "right":
        _draw_side(draw, cx, cy, bw, bh, lh, hw, hh, tw, th, rh, facing_left=False)
    elif direction == "front_left":
        _draw_3q(draw, cx, cy, bw, bh, lh, hw, hh, tw, th, rh, facing_left=True, show_front=True)
    elif direction == "front_right":
        _draw_3q(draw, cx, cy, bw, bh, lh, hw, hh, tw, th, rh, facing_left=False, show_front=True)
    elif direction == "back_left":
        _draw_3q(draw, cx, cy, bw, bh, lh, hw, hh, tw, th, rh, facing_left=True, show_front=False)
    elif direction == "back_right":
        _draw_3q(draw, cx, cy, bw, bh, lh, hw, hh, tw, th, rh, facing_left=False, show_front=False)

    # Soften
    small = img.resize((GEN_WIDTH // 4, GEN_HEIGHT // 4), Image.LANCZOS)
    img = small.resize((GEN_WIDTH, GEN_HEIGHT), Image.LANCZOS)

    return img


def _draw_front(draw, cx, cy, bw, bh, lh, hw, hh, rh):
    """Front view: wide low body, wedge head centered forward, 4 splayed legs."""
    # Body (wide, very flat)
    draw.ellipse([cx - bw/2, cy - bh/2, cx + bw/2, cy + bh/2], fill=195)

    # Dorsal ridge (sharp triangular bumps along top)
    for i in range(7):
        rx = cx - bw*0.3 + i * bw*0.1
        draw.polygon([
            (rx, cy - bh/2 - rh*2.5),
            (rx - 6, cy - bh/2 + 2),
            (rx + 6, cy - bh/2 + 2),
        ], fill=210)

    # Head (wide wedge, thrust forward and low — nearest/brightest)
    draw.ellipse([cx - hw/2, cy - bh/2 - hh*0.8, cx + hw/2, cy - bh/2 + hh*0.3], fill=240)
    # Wide jaw
    draw.ellipse([cx - hw*0.55, cy - bh/2 - hh*0.2, cx + hw*0.55, cy - bh/2 + hh*0.5], fill=230)

    # 4 legs (wide splayed stance)
    leg_w = bw * 0.10
    for lx in [cx - bw*0.45, cx - bw*0.18, cx + bw*0.18, cx + bw*0.45]:
        draw.rectangle([lx - leg_w/2, cy + bh/2 - 3, lx + leg_w/2, cy + bh/2 + lh], fill=155)


def _draw_back(draw, cx, cy, bw, bh, lh, tw, th, rh):
    """Back view: body, long tail visible, no head."""
    # Body
    draw.ellipse([cx - bw/2, cy - bh/2, cx + bw/2, cy + bh/2], fill=175)

    # Dorsal ridge
    for i in range(7):
        rx = cx - bw*0.3 + i * bw*0.1
        draw.polygon([
            (rx, cy - bh/2 - rh*2.5),
            (rx - 6, cy - bh/2 + 2),
            (rx + 6, cy - bh/2 + 2),
        ], fill=185)

    # Tail (long, thin, extending upward/back — whip tail)
    draw.ellipse([cx - tw*0.08, cy - bh/2 - th*6, cx + tw*0.08, cy - bh/2 + th], fill=140)
    # Tail base thicker
    draw.ellipse([cx - tw*0.15, cy - bh/2 - th*2, cx + tw*0.15, cy - bh/2 + th*0.5], fill=150)

    # 4 legs
    leg_w = bw * 0.10
    for lx in [cx - bw*0.45, cx - bw*0.18, cx + bw*0.18, cx + bw*0.45]:
        draw.rectangle([lx - leg_w/2, cy + bh/2 - 3, lx + leg_w/2, cy + bh/2 + lh], fill=135)


def _draw_side(draw, cx, cy, bw, bh, lh, hw, hh, tw, th, rh, facing_left):
    """Side profile: long horizontal body, head forward at one end, whip tail at other."""
    sign = -1 if facing_left else 1

    body_w = bw * 1.2  # longer in profile
    # Body
    draw.ellipse([cx - body_w/2, cy - bh/2, cx + body_w/2, cy + bh/2], fill=190)

    # Dorsal ridge along top
    for i in range(9):
        rx = cx - body_w*0.4 + i * body_w*0.1
        draw.polygon([
            (rx, cy - bh/2 - rh*2.5),
            (rx - 5, cy - bh/2 + 2),
            (rx + 5, cy - bh/2 + 2),
        ], fill=200)

    # Head (forward-thrust, low — at front end)
    head_cx = cx - sign * body_w * 0.5
    head_cy = cy + bh*0.1  # head level with body, not above
    draw.ellipse([head_cx - hw*0.6, head_cy - hh*0.5, head_cx + hw*0.6, head_cy + hh*0.5], fill=230)
    # Jaw forward
    jaw_cx = head_cx - sign * hw * 0.5
    draw.ellipse([jaw_cx - hw*0.35, head_cy - hh*0.3, jaw_cx + hw*0.35, head_cy + hh*0.4], fill=225)

    # Tail (long, extending from back end — thin whip)
    tail_cx = cx + sign * body_w * 0.55
    tail_end = tail_cx + sign * tw * 0.8
    tail_x0 = min(tail_cx, tail_end)
    tail_x1 = max(tail_cx, tail_end)
    draw.ellipse([tail_x0, cy - bh*0.2 - th, tail_x1, cy - bh*0.2 + th], fill=130)

    # 2 visible legs
    leg_w = bw * 0.09
    for lx_offset in [-0.25, 0.2]:
        lx = cx + body_w * lx_offset
        draw.rectangle([lx - leg_w/2, cy + bh/2 - 3, lx + leg_w/2, cy + bh/2 + lh], fill=155)


def _draw_3q(draw, cx, cy, bw, bh, lh, hw, hh, tw, th, rh, facing_left, show_front):
    """3/4 view."""
    sign = -1 if facing_left else 1

    body_w = bw * 1.0
    draw.ellipse([cx - body_w/2 - sign*15, cy - bh/2, cx + body_w/2 - sign*15, cy + bh/2], fill=190)

    # Dorsal ridge
    for i in range(6):
        rx = cx - body_w*0.3 + i * body_w*0.12 - sign*15
        draw.polygon([
            (rx, cy - bh/2 - rh*2.5),
            (rx - 5, cy - bh/2 + 2),
            (rx + 5, cy - bh/2 + 2),
        ], fill=200)

    if show_front:
        # Head visible — forward thrust
        head_cx = cx - sign * body_w * 0.35
        head_cy = cy + bh*0.1
        draw.ellipse([head_cx - hw*0.5, head_cy - hh*0.5, head_cx + hw*0.5, head_cy + hh*0.4], fill=230)
        jaw_cx = head_cx - sign * hw * 0.3
        draw.ellipse([jaw_cx - hw*0.3, head_cy - hh*0.2, jaw_cx + hw*0.3, head_cy + hh*0.35], fill=225)
    else:
        # Tail visible
        tail_cx = cx + sign * body_w * 0.4
        tail_end = tail_cx + sign * tw * 0.6
        tail_x0 = min(tail_cx, tail_end)
        tail_x1 = max(tail_cx, tail_end)
        draw.ellipse([tail_x0, cy - bh*0.3 - th, tail_x1, cy - bh*0.3 + th], fill=130)

    # 3 visible legs
    leg_w = bw * 0.09
    for lx_offset in [-0.35, -0.05, 0.22]:
        lx = cx + body_w * lx_offset - sign*12
        draw.rectangle([lx - leg_w/2, cy + bh/2 - 3, lx + leg_w/2, cy + bh/2 + lh], fill=155)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    directions = [
        "front", "front_left", "left", "back_left",
        "back", "back_right", "right", "front_right",
    ]

    for d in directions:
        img = draw_lurker_depth(d)
        path = OUT_DIR / f"{d}_depth_ref.png"
        img.save(str(path))
        print(f"  {d}: {path}")

    # Contact sheet
    CELL = 192
    PAD = 4
    sheet_w = len(directions) * (CELL + PAD) + PAD
    sheet_h = CELL + PAD * 2 + 20
    sheet = Image.new("L", (sheet_w, sheet_h), 0)

    for i, d in enumerate(directions):
        ref = Image.open(OUT_DIR / f"{d}_depth_ref.png")
        w, h = ref.size
        top = (h - w) // 4
        cropped = ref.crop((0, top, w, top + w))
        cell = cropped.resize((CELL, CELL), Image.LANCZOS)
        sheet.paste(cell, (PAD + i * (CELL + PAD), PAD + 20))

    sheet_path = OUT_DIR / "depth_ref_sheet.png"
    sheet.save(str(sheet_path))
    print(f"\n  Contact sheet: {sheet_path}")


if __name__ == "__main__":
    main()
