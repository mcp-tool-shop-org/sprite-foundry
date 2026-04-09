"""
Prepare high-resolution input images for Hunyuan3D-2mv from a CharTurn turnaround sheet.

Extracts individual figures at full resolution (not downsampled to 48px),
removes green screen background, pads to square, and resizes to 512x512
for Hunyuan3D input.

Usage:
    python -m pipeline.prep_hunyuan3d_input \
        --sheet bakeoff/claude_opus_turn_20260408_235705/turnaround_sheet.png \
        --output bakeoff/hunyuan3d_input
"""

import argparse
from pathlib import Path

import numpy as np
from PIL import Image


def remove_background(img: Image.Image, tolerance: float = 40.0) -> Image.Image:
    """Remove background via corner-color matching, return RGBA with transparent BG."""
    arr = np.array(img.convert("RGBA")).copy()
    h, w = arr.shape[:2]
    rgb = arr[:, :, :3].astype(np.float32)

    # Estimate BG color from corners (average of 10x10 corner patches)
    patch = 10
    corners = np.concatenate([
        rgb[:patch, :patch].reshape(-1, 3),
        rgb[:patch, w - patch:].reshape(-1, 3),
        rgb[h - patch:, :patch].reshape(-1, 3),
        rgb[h - patch:, w - patch:].reshape(-1, 3),
    ])
    bg_color = np.median(corners, axis=0)

    # Remove pixels close to BG color
    diff = np.sqrt(np.sum((rgb - bg_color) ** 2, axis=2))
    arr[diff < tolerance, 3] = 0

    # Soften fringe
    fringe = (diff >= tolerance) & (diff < tolerance * 1.5)
    arr[fringe, 3] = ((diff[fringe] - tolerance) / (tolerance * 0.5) * 255).clip(0, 255).astype(np.uint8)

    return Image.fromarray(arr)


def find_figures(rgba_img: Image.Image, min_gap: int = 15, min_width: int = 50) -> list[tuple]:
    """Find bounding boxes of individual figures in a transparent image.

    Returns list of (left, top, right, bottom) tuples.
    """
    arr = np.array(rgba_img)
    col_has_content = np.any(arr[:, :, 3] > 30, axis=0)

    # Find contiguous runs of content columns
    figures = []
    in_figure = False
    start = 0

    for x in range(len(col_has_content)):
        if col_has_content[x] and not in_figure:
            start = x
            in_figure = True
        elif not col_has_content[x] and in_figure:
            gap_end = x
            while gap_end < len(col_has_content) and not col_has_content[gap_end]:
                gap_end += 1
            if gap_end - x >= min_gap or gap_end >= len(col_has_content):
                if x - start >= min_width:
                    figures.append((start, x))
                in_figure = False

    if in_figure and len(col_has_content) - start >= min_width:
        figures.append((start, len(col_has_content)))

    # Convert to full bounding boxes with vertical extent
    boxes = []
    for left, right in figures:
        region = arr[:, left:right, 3]
        row_has_content = np.any(region > 30, axis=1)
        rows = np.where(row_has_content)[0]
        if len(rows) > 0:
            top = rows[0]
            bottom = rows[-1] + 1
            boxes.append((left, top, right, bottom))

    return boxes


def pad_to_square_and_resize(img: Image.Image, target: int = 512, padding_pct: float = 0.1) -> Image.Image:
    """Pad image to square with margin, resize to target, fill BG with white."""
    w, h = img.size
    side = max(w, h)
    # Add padding
    padded_side = int(side * (1 + padding_pct * 2))

    # White background (Hunyuan3D expects white BG, not transparent)
    square = Image.new("RGBA", (padded_side, padded_side), (255, 255, 255, 255))
    paste_x = (padded_side - w) // 2
    paste_y = (padded_side - h) // 2
    square.paste(img, (paste_x, paste_y), img)

    # Convert to RGB (white BG) and resize
    rgb = Image.new("RGB", square.size, (255, 255, 255))
    rgb.paste(square, mask=square.split()[3])
    return rgb.resize((target, target), Image.LANCZOS)


def main():
    parser = argparse.ArgumentParser(description="Prepare Hunyuan3D input from turnaround sheet")
    parser.add_argument("--sheet", required=True, help="Path to turnaround sheet PNG")
    parser.add_argument("--output", default="bakeoff/hunyuan3d_input", help="Output directory")
    parser.add_argument("--target-size", type=int, default=512, help="Output image size (default 512)")
    args = parser.parse_args()

    sheet_path = Path(args.sheet)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading turnaround sheet: {sheet_path}")
    sheet = Image.open(sheet_path)
    print(f"  Size: {sheet.size[0]}x{sheet.size[1]}")

    # Remove green screen
    print("Removing green screen...")
    cleaned = remove_background(sheet)

    # Find individual figures
    print("Finding figures...")
    boxes = find_figures(cleaned)
    print(f"  Found {len(boxes)} figures")

    if len(boxes) < 3:
        print(f"ERROR: Need at least 3 figures (front, side, back), found {len(boxes)}")
        return

    # Assign views (left-to-right: front, intermediates..., back)
    # CharTurn typically: front, front_right, side, back_right, back, ...
    view_assignments = []
    if len(boxes) == 3:
        view_assignments = [("front", 0), ("left", 1), ("back", 2)]
    elif len(boxes) == 4:
        view_assignments = [("front", 0), ("front_left", 1), ("left", 2), ("back", 3)]
    elif len(boxes) == 5:
        view_assignments = [("front", 0), ("front_left", 1), ("left", 2), ("back_left", 3), ("back", 4)]
    elif len(boxes) >= 6:
        view_assignments = [("front", 0), ("front_left", 1), ("left", 2), ("back_left", 3), ("back", 4)]
        if len(boxes) >= 7:
            view_assignments.append(("back_right", 5))

    # Extract, pad, resize each figure
    for view_name, idx in view_assignments:
        left, top, right, bottom = boxes[idx]
        fig = cleaned.crop((left, top, right, bottom))
        w, h = fig.size
        print(f"  {view_name}: {w}x{h}px (bbox [{left},{top},{right},{bottom}])")

        # Save high-res crop (for reference)
        fig.save(str(out_dir / f"{view_name}_crop.png"))

        # Pad and resize for Hunyuan3D
        prepped = pad_to_square_and_resize(fig, target=args.target_size)
        prepped.save(str(out_dir / f"{view_name}.png"))
        print(f"    ->{view_name}.png ({args.target_size}x{args.target_size})")

    # Save the cleaned (transparent BG) sheet for reference
    cleaned.save(str(out_dir / "cleaned_sheet.png"))

    print(f"\nHunyuan3D-2mv input ready at: {out_dir}")
    print(f"Use front.png, left.png, back.png as multi-view input")


if __name__ == "__main__":
    main()
