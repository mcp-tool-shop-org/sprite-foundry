"""
Phase 3 — Foundry-integrated finish capture pipeline.

For a given run:
1. Copies 48px sprites + normals to Godot render-lab assets
2. Rewrites auto_lab.gd for the target character
3. Runs Godot editor import pass
4. Runs Godot capture sweep (batched: 2-3 directions per run)
5. Registers finish_captures in the foundry
6. Advances attempts to finish_review_pending

Usage:
    python -m pipeline.foundry_finish --run <run_id>
"""

import argparse
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

FOUNDRY_ROOT = Path(__file__).parent.parent
GODOT_PROJECT = FOUNDRY_ROOT / "game" / "godot" / "render-lab"


def resolve_godot_exe() -> Path:
    """Resolve the Godot 4 binary from the environment, falling back to discovery.

    Resolution order:
      1. $SPRITE_FOUNDRY_GODOT  (explicit project override)
      2. $GODOT4_BIN            (common Godot env var)
      3. `godot4` / `godot` on PATH (shutil.which)

    No drive letters or Godot patch versions are hardcoded — the rig may run
    any Godot 4.x build at any path. Validation (existence + executability) is
    deferred to validate_godot_exe() so callers can surface a clear error.
    """
    for env_var in ("SPRITE_FOUNDRY_GODOT", "GODOT4_BIN"):
        val = os.environ.get(env_var)
        if val:
            return Path(val)

    for candidate in ("godot4", "godot"):
        found = shutil.which(candidate)
        if found:
            return Path(found)

    # Nothing found — return a sentinel that validate_godot_exe() will reject
    # with an actionable message rather than failing deep in subprocess.
    return Path("godot4")


def validate_godot_exe(exe: Path) -> None:
    """Fail fast with an actionable error if the Godot binary is unusable.

    A bare command name (resolved via PATH by shutil.which) is accepted as-is;
    an absolute/relative path must point at an existing file.
    """
    # If it's a plain command name and on PATH, trust it.
    if exe.name == str(exe) and shutil.which(str(exe)):
        return
    if not exe.exists():
        raise FileNotFoundError(
            f"Godot executable not found: {exe}\n"
            f"  Set SPRITE_FOUNDRY_GODOT (or GODOT4_BIN) to your Godot 4 binary, "
            f"or put 'godot4'/'godot' on PATH.\n"
            f"  Example (PowerShell): $env:SPRITE_FOUNDRY_GODOT = 'C:/path/to/Godot_v4.x-stable_win64.exe'"
        )


GODOT_EXE = resolve_godot_exe()

DIRECTIONS = [
    "front", "front_left", "left", "back_left",
    "back", "back_right", "right", "front_right",
]

LIGHTING_STATES = ["baseline", "moonlight", "torch", "moon_particles_depth"]

# Process in batches of 2 to stay within Godot's quit-after timeout
BATCH_SIZE = 2


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def copy_assets(conn, run_id: str, subject_id: str):
    """Copy 48px sprites and normals from foundry artifacts to Godot assets."""
    sprites_dir = GODOT_PROJECT / "assets" / f"{subject_id}_sprites"
    normals_dir = GODOT_PROJECT / "assets" / f"{subject_id}_normals"
    sprites_dir.mkdir(parents=True, exist_ok=True)
    normals_dir.mkdir(parents=True, exist_ok=True)

    attempts = conn.execute(
        """SELECT id, direction FROM attempts
           WHERE run_id = ? AND state = 'accepted' AND direction != '__contact_sheets__'
           ORDER BY direction""",
        (run_id,),
    ).fetchall()

    copied = 0
    for a in attempts:
        aid = a["id"]
        direction = a["direction"]

        # Copy pixel sprite
        pixel = conn.execute(
            "SELECT path FROM artifacts WHERE attempt_id = ? AND kind = 'pixel'",
            (aid,),
        ).fetchone()
        if pixel:
            src = FOUNDRY_ROOT / pixel["path"]
            dst = sprites_dir / f"{direction}.png"
            if src.exists():
                shutil.copy2(src, dst)

        # Copy normal map
        normal = conn.execute(
            "SELECT path FROM artifacts WHERE attempt_id = ? AND kind = 'normal'",
            (aid,),
        ).fetchone()
        if normal:
            src = FOUNDRY_ROOT / normal["path"]
            dst = normals_dir / f"{direction}_normal.png"
            if src.exists():
                shutil.copy2(src, dst)
                copied += 1

    print(f"  Copied {copied} sprite+normal pairs to Godot assets")
    return sprites_dir, normals_dir


def write_auto_lab(subject_id: str, directions: list[str], screenshot_prefix: str):
    """Write a parameterized auto_lab.gd for the given character and directions."""
    dirs_str = ", ".join(f'"{d}"' for d in directions)
    sprites_path = f"res://assets/{subject_id}_sprites"
    normals_path = f"res://assets/{subject_id}_normals"

    script = f'''extends Node2D

## Phase 3 Finish Capture — {subject_id}
## {len(directions)} directions x 4 states

const DIRECTIONS := [{dirs_str}]
const STATES := ["baseline", "moonlight", "torch", "moon_particles_depth"]

var sprite: Sprite2D
var light_torch: PointLight2D
var light_moon: PointLight2D
var particles_ember: GPUParticles2D
var particles_dust: GPUParticles2D

var current_dir_idx := 0
var current_state_idx := 0
var frame_wait := 0
var captures_done := 0
var total_captures: int

var albedo_textures := {{}}
var normal_textures := {{}}
var canvas_textures := {{}}

var depth_shader: ShaderMaterial


func _ready() -> void:
\ttotal_captures = DIRECTIONS.size() * STATES.size()
\t_build_scene()

\tfor dir_name in DIRECTIONS:
\t\talbedo_textures[dir_name] = load("{sprites_path}/%s.png" % dir_name)
\t\tnormal_textures[dir_name] = load("{normals_path}/%s_normal.png" % dir_name)

\t\tvar ct := CanvasTexture.new()
\t\tct.diffuse_texture = albedo_textures[dir_name]
\t\tct.normal_texture = normal_textures[dir_name]
\t\tct.specular_color = Color(0.3, 0.3, 0.3, 1.0)
\t\tct.specular_shininess = 0.3
\t\tcanvas_textures[dir_name] = ct

\tvar depth_sh := Shader.new()
\tdepth_sh.code = """
shader_type canvas_item;

uniform float falloff_strength : hint_range(0.0, 1.0) = 0.35;
uniform vec4 atmosphere_color : source_color = vec4(0.4, 0.5, 0.7, 1.0);
uniform float rim_strength : hint_range(0.0, 2.0) = 0.5;
uniform vec4 rim_color : source_color = vec4(0.6, 0.7, 1.0, 1.0);

void fragment() {{
\tvec4 tex = texture(TEXTURE, UV);
\tif (tex.a < 0.1) discard;
\tfloat vert = UV.y;
\tvec2 px = TEXTURE_PIXEL_SIZE;
\tfloat a_l = texture(TEXTURE, UV + vec2(-px.x, 0)).a;
\tfloat a_r = texture(TEXTURE, UV + vec2(px.x, 0)).a;
\tfloat a_u = texture(TEXTURE, UV + vec2(0, -px.y)).a;
\tfloat a_d = texture(TEXTURE, UV + vec2(0, px.y)).a;
\tfloat edge = max(0.0, 1.0 - (a_l + a_r + a_u + a_d) / 4.0);
\tvec3 result = mix(tex.rgb, atmosphere_color.rgb, vert * falloff_strength * 0.5);
\tfloat rim_weight = (1.0 - vert * 0.6);
\tresult += rim_color.rgb * edge * rim_strength * rim_weight;
\tCOLOR = vec4(result, tex.a);
}}
"""
\tdepth_shader = ShaderMaterial.new()
\tdepth_shader.shader = depth_sh

\t_set_direction(0)
\t_apply_state("baseline")
\tprint("Finish Lab: %d captures to make" % total_captures)


func _build_scene() -> void:
\tvar cam := Camera2D.new()
\tcam.position = Vector2(256, 256)
\tadd_child(cam)

\tvar ground := ColorRect.new()
\tground.position = Vector2(0, 380)
\tground.size = Vector2(512, 132)
\tground.color = Color(0.12, 0.12, 0.15, 1)
\tadd_child(ground)

\tsprite = Sprite2D.new()
\tsprite.position = Vector2(256, 270)
\tsprite.scale = Vector2(5, 5)
\tsprite.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
\tadd_child(sprite)

\tlight_moon = PointLight2D.new()
\tlight_moon.position = Vector2(200, 80)
\tlight_moon.color = Color(0.45, 0.6, 1.0, 1.0)
\tlight_moon.energy = 1.4
\tlight_moon.texture = _make_moon_texture()
\tlight_moon.texture_scale = 2.0
\tlight_moon.visible = false
\tadd_child(light_moon)

\tlight_torch = PointLight2D.new()
\tlight_torch.position = Vector2(320, 180)
\tlight_torch.color = Color(1.0, 0.6, 0.27, 1.0)
\tlight_torch.energy = 1.2
\tlight_torch.texture = _make_light_texture()
\tlight_torch.texture_scale = 2.5
\tlight_torch.visible = false
\tadd_child(light_torch)

\tparticles_ember = GPUParticles2D.new()
\tparticles_ember.position = Vector2(280, 420)
\tparticles_ember.amount = 8
\tparticles_ember.lifetime = 3.5
\tparticles_ember.emitting = false
\tvar ember_mat := ParticleProcessMaterial.new()
\tember_mat.direction = Vector3(0, -1, 0)
\tember_mat.spread = 30.0
\tember_mat.initial_velocity_min = 8.0
\tember_mat.initial_velocity_max = 20.0
\tember_mat.gravity = Vector3(0, -15, 0)
\tember_mat.scale_min = 1.0
\tember_mat.scale_max = 2.5
\tember_mat.color = Color(1.0, 0.6, 0.2, 0.85)
\tparticles_ember.process_material = ember_mat
\tadd_child(particles_ember)

\tparticles_dust = GPUParticles2D.new()
\tparticles_dust.position = Vector2(256, 240)
\tparticles_dust.amount = 6
\tparticles_dust.lifetime = 6.0
\tparticles_dust.emitting = false
\tvar dust_mat := ParticleProcessMaterial.new()
\tdust_mat.direction = Vector3(1, -0.2, 0)
\tdust_mat.spread = 120.0
\tdust_mat.initial_velocity_min = 2.0
\tdust_mat.initial_velocity_max = 5.0
\tdust_mat.gravity = Vector3(0, 0, 0)
\tdust_mat.scale_min = 2.0
\tdust_mat.scale_max = 5.0
\tdust_mat.color = Color(0.6, 0.7, 0.9, 0.25)
\tparticles_dust.process_material = dust_mat
\tadd_child(particles_dust)


func _make_light_texture() -> GradientTexture2D:
\tvar tex := GradientTexture2D.new()
\ttex.width = 256
\ttex.height = 256
\ttex.fill = GradientTexture2D.FILL_RADIAL
\ttex.fill_from = Vector2(0.5, 0.5)
\ttex.fill_to = Vector2(0.5, 1.0)
\tvar grad := Gradient.new()
\tgrad.set_color(0, Color.WHITE)
\tgrad.set_color(1, Color.TRANSPARENT)
\ttex.gradient = grad
\treturn tex


func _make_moon_texture() -> GradientTexture2D:
\tvar tex := GradientTexture2D.new()
\ttex.width = 256
\ttex.height = 256
\ttex.fill = GradientTexture2D.FILL_RADIAL
\ttex.fill_from = Vector2(0.5, 0.5)
\ttex.fill_to = Vector2(0.5, 0.8)
\tvar grad := Gradient.new()
\tgrad.set_color(0, Color.WHITE)
\tgrad.add_point(0.6, Color(0.5, 0.5, 0.5, 0.5))
\tgrad.set_color(1, Color.TRANSPARENT)
\ttex.gradient = grad
\treturn tex


func _set_direction(idx: int) -> void:
\tvar dir_name: String = DIRECTIONS[idx]
\tsprite.texture = canvas_textures[dir_name]


func _apply_state(state: String) -> void:
\tlight_torch.visible = false
\tlight_moon.visible = false
\tparticles_ember.emitting = false
\tparticles_dust.emitting = false
\tsprite.material = null

\tmatch state:
\t\t"baseline":
\t\t\tpass
\t\t"torch":
\t\t\tlight_torch.visible = true
\t\t"moonlight":
\t\t\tlight_moon.visible = true
\t\t"moon_particles_depth":
\t\t\tlight_moon.visible = true
\t\t\tparticles_dust.emitting = true
\t\t\tparticles_ember.emitting = true
\t\t\tsprite.material = depth_shader


func _process(_delta: float) -> void:
\tif current_dir_idx >= DIRECTIONS.size():
\t\treturn

\tframe_wait += 1
\tif frame_wait < 3:
\t\treturn
\tframe_wait = 0

\tvar dir_name: String = DIRECTIONS[current_dir_idx]
\tvar state_name: String = STATES[current_state_idx]

\tvar img := get_viewport().get_texture().get_image()
\tvar path := "res://screenshots/{screenshot_prefix}_%s_%s.png" % [dir_name, state_name]
\timg.save_png(path)
\tcaptures_done += 1
\tprint("[%d/%d] Captured: %s" % [captures_done, total_captures, path])

\tcurrent_state_idx += 1
\tif current_state_idx >= STATES.size():
\t\tcurrent_state_idx = 0
\t\tcurrent_dir_idx += 1
\t\tif current_dir_idx < DIRECTIONS.size():
\t\t\t_set_direction(current_dir_idx)

\tif current_dir_idx >= DIRECTIONS.size():
\t\tprint("\\n=== ALL CAPTURES COMPLETE ===")
\t\tawait get_tree().create_timer(0.5).timeout
\t\tget_tree().quit()
\telse:
\t\t_apply_state(STATES[current_state_idx])
'''
    script_path = GODOT_PROJECT / "scripts" / "auto_lab.gd"
    script_path.write_text(script, encoding="utf-8")
    print(f"  Wrote auto_lab.gd for {subject_id} ({len(directions)} dirs)")


def _stderr_tail(result, n: int = 8) -> str:
    """Return the last n non-empty lines of stderr for diagnostics."""
    if not getattr(result, "stderr", None):
        return "(no stderr)"
    lines = [ln for ln in result.stderr.strip().split("\n") if ln.strip()]
    return "\n".join(f"      {ln}" for ln in lines[-n:]) or "(no stderr)"


def run_godot_import():
    """Run Godot editor pass to import new textures.

    Aborts the finish run on a missing binary, a non-zero exit, or a timeout
    rather than printing 'done' over a silent failure (F-016).
    """
    print("  Running Godot import pass...", end=" ", flush=True)
    try:
        result = subprocess.run(
            [str(GODOT_EXE), "--headless", "--editor", "--quit-after", "15",
             "--path", str(GODOT_PROJECT)],
            capture_output=True, text=True, timeout=30,
        )
    except FileNotFoundError as e:
        print("FAILED")
        raise RuntimeError(
            f"Godot binary not found while running import pass: {GODOT_EXE} ({e}). "
            f"Set SPRITE_FOUNDRY_GODOT or GODOT4_BIN."
        ) from e
    except subprocess.TimeoutExpired as e:
        print("TIMEOUT")
        raise RuntimeError(
            f"Godot import pass timed out after 30s. Godot may have hung on import."
        ) from e

    if result.returncode != 0:
        print("FAILED")
        raise RuntimeError(
            f"Godot import pass exited with code {result.returncode}. stderr tail:\n"
            f"{_stderr_tail(result)}"
        )
    print("done")


def run_godot_capture(timeout_secs: int = 60):
    """Run Godot capture sweep.

    Returns the number of captures parsed from stdout. Aborts the finish run on
    a missing binary, a non-zero exit, or a process timeout (the editor process
    overrunning the wall-clock guard) — a launch failure must not masquerade as
    '0 captures' and trigger a blind retry (F-016).
    """
    print("  Running Godot capture...", end=" ", flush=True)
    try:
        result = subprocess.run(
            [str(GODOT_EXE), "--quit-after", str(timeout_secs),
             "--path", str(GODOT_PROJECT)],
            capture_output=True, text=True, timeout=timeout_secs + 15,
        )
    except FileNotFoundError as e:
        print("FAILED")
        raise RuntimeError(
            f"Godot binary not found while running capture: {GODOT_EXE} ({e}). "
            f"Set SPRITE_FOUNDRY_GODOT or GODOT4_BIN."
        ) from e
    except subprocess.TimeoutExpired as e:
        print("TIMEOUT")
        raise RuntimeError(
            f"Godot capture process did not exit within {timeout_secs + 15}s "
            f"(--quit-after was {timeout_secs}s). The capture scene likely hung."
        ) from e

    if result.returncode != 0:
        print("FAILED")
        raise RuntimeError(
            f"Godot capture exited with code {result.returncode}. stderr tail:\n"
            f"{_stderr_tail(result)}"
        )

    # Count captures from stdout
    captures = result.stdout.count("Captured:")
    print(f"{captures} captures")
    if result.stdout:
        # Print last few lines
        lines = result.stdout.strip().split("\n")
        for line in lines[-3:]:
            print(f"    {line}")
    return captures


def register_captures(conn, run_id: str, subject_id: str, screenshot_prefix: str):
    """Register finish captures in the foundry and advance to finish_review_pending."""
    screenshots_dir = GODOT_PROJECT / "screenshots"
    from foundry.cli import now_iso

    attempts = conn.execute(
        """SELECT id, direction FROM attempts
           WHERE run_id = ? AND state = 'accepted' AND direction != '__contact_sheets__'
           ORDER BY direction""",
        (run_id,),
    ).fetchall()

    registered = 0
    for a in attempts:
        aid = a["id"]
        direction = a["direction"]

        for state in LIGHTING_STATES:
            filename = f"{screenshot_prefix}_{direction}_{state}.png"
            filepath = screenshots_dir / filename
            if filepath.exists():
                rel_path = str(filepath.relative_to(FOUNDRY_ROOT))
                conn.execute(
                    """INSERT INTO finish_captures
                       (attempt_id, lighting_state, path, created_at)
                       VALUES (?, ?, ?, ?)""",
                    (aid, state, rel_path, now_iso()),
                )
                registered += 1

    conn.commit()
    print(f"  Registered {registered} finish captures")

    # Advance to finish_review_pending
    from foundry import db
    advanced = 0
    for a in attempts:
        row = conn.execute("SELECT state FROM attempts WHERE id = ?", (a["id"],)).fetchone()
        if row and row["state"] == "accepted":
            db.transition_attempt(conn, a["id"], "finish_review_pending")
            advanced += 1
    conn.commit()
    print(f"  Advanced {advanced} attempts to finish_review_pending")


def run_finish_pipeline(run_id: str):
    """Full finish pipeline for a run."""
    sys.path.insert(0, str(FOUNDRY_ROOT))
    from foundry import db

    conn = db.init_db()

    run = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    if not run:
        print(f"Run '{run_id}' not found.")
        conn.close()
        return

    subject_id = run["subject_id"]
    subject = conn.execute(
        "SELECT display_name FROM subjects WHERE id = ?", (subject_id,)
    ).fetchone()
    char_name = subject["display_name"] if subject else subject_id
    screenshot_prefix = subject_id

    # Fail fast if Godot is missing — the finish pipeline cannot run without it,
    # and a clear error here beats a confusing FileNotFoundError mid-capture (F-001).
    try:
        validate_godot_exe(GODOT_EXE)
    except FileNotFoundError as e:
        print(f"\nERROR: {e}")
        conn.close()
        sys.exit(1)

    print(f"\n{'=' * 60}")
    print(f"FINISH PIPELINE: {char_name}")
    print(f"Run: {run_id}")
    print(f"Godot: {GODOT_EXE}")
    print(f"{'=' * 60}\n")

    # Step 1: Copy assets
    print("--- Step 1: Copy assets to Godot ---")
    copy_assets(conn, run_id, subject_id)

    # Step 2: Godot import pass
    print("\n--- Step 2: Godot import ---")
    run_godot_import()

    # Step 3: Capture in batches
    print("\n--- Step 3: Capture sweep ---")

    # Ensure screenshots directory exists
    (GODOT_PROJECT / "screenshots").mkdir(exist_ok=True)

    for batch_start in range(0, len(DIRECTIONS), BATCH_SIZE):
        batch_dirs = DIRECTIONS[batch_start:batch_start + BATCH_SIZE]
        print(f"\n  Batch: {', '.join(batch_dirs)}")

        write_auto_lab(subject_id, batch_dirs, screenshot_prefix)
        # run_godot_capture raises on a missing binary / non-zero exit / process
        # timeout, so a 0 here means Godot launched and exited cleanly but the
        # scene produced no captures — a slow-render retry is legitimate.
        captures = run_godot_capture(timeout_secs=90)

        if captures == 0:
            print(f"  WARNING: No captures in this batch! Retrying with longer timeout...")
            captures = run_godot_capture(timeout_secs=120)

    # Step 4: Register captures
    print(f"\n--- Step 4: Register captures ---")
    register_captures(conn, run_id, subject_id, screenshot_prefix)

    # Summary
    total_expected = len(DIRECTIONS) * len(LIGHTING_STATES)
    screenshots_dir = GODOT_PROJECT / "screenshots"
    actual_files = list(screenshots_dir.glob(f"{screenshot_prefix}_*_*.png"))
    print(f"\n  Expected: {total_expected} captures")
    print(f"  Found:    {len(actual_files)} files")

    conn.close()

    print(f"\n{'=' * 60}")
    print(f"FINISH COMPLETE: {char_name}")
    print(f"Next: foundry review-show {run_id}")
    print(f"{'=' * 60}")


def main():
    parser = argparse.ArgumentParser(description="Foundry finish capture pipeline")
    parser.add_argument("--run", required=True, help="Run ID")
    args = parser.parse_args()
    run_finish_pipeline(args.run)


if __name__ == "__main__":
    main()
