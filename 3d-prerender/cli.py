"""Single-file argparse dispatcher for the 3d-prerender pipeline.

Every stage lives in its own script (mesh_character.py, retexture_character.py,
texture_patch_region.py, sprite_render.py, pack_jury.py, sprite_jury.py) with its own
argparse definition. This CLI does NOT re-declare those flags — that would drift out of
sync the moment a wrapped script's argparse changes. Instead each stage subcommand takes
`argparse.parse_known_args()` leftovers and forwards them verbatim to a `subprocess.run()`
call of the real script, using the SAME python interpreter (`sys.executable`) that invoked
this CLI (so venv/conda selection is respected) — except `render`, which always shells out
to `config.BLENDER_EXE` since sprite_render.py runs *inside* Blender's bundled Python, not
this one.

Run `python cli.py --help` for the subcommand list, or `python cli.py <stage> --help` to see
the wrapped script's own flags (forwarded straight through, e.g. `python cli.py mesh --help`
prints mesh_character.py's real argparse help).

stdlib only. No Click/Typer. No new pip dependency.
"""
import argparse
import subprocess
import sys
import urllib.request
import urllib.error
from pathlib import Path

import config

HERE = Path(__file__).resolve().parent

MESH_SCRIPT = HERE / "mesh_character.py"
RETEXTURE_SCRIPT = HERE / "retexture_character.py"
PATCH_SCRIPT = HERE / "texture_patch_region.py"
RENDER_SCRIPT = HERE / "sprite_render.py"
PACK_JURY_SCRIPT = HERE / "pack_jury.py"
SPRITE_JURY_SCRIPT = HERE / "sprite_jury.py"


def _add_probe(ap):
    ap.add_argument(
        "--probe", "--dry-run", dest="probe", action="store_true",
        help="print the resolved subprocess command line and exit 0 WITHOUT invoking it",
    )


def _run_or_probe(argv, probe, label):
    """Print (probe) or actually run (subprocess.run) a resolved command line.

    argv: full argv list (program + args), already resolved.
    Returns the subprocess exit code (0 for a probe).
    """
    printable = " ".join(str(a) for a in argv)
    if probe:
        print(f"[probe:{label}] {printable}", flush=True)
        return 0
    print(f"[run:{label}] {printable}", flush=True)
    result = subprocess.run(argv)
    return result.returncode


def cmd_mesh(known, extra):
    argv = [sys.executable, str(MESH_SCRIPT), *extra]
    return _run_or_probe(argv, known.probe, "mesh")


def cmd_retexture(known, extra):
    argv = [sys.executable, str(RETEXTURE_SCRIPT), *extra]
    return _run_or_probe(argv, known.probe, "retexture")


def cmd_patch(known, extra):
    argv = [sys.executable, str(PATCH_SCRIPT), *extra]
    return _run_or_probe(argv, known.probe, "patch")


def cmd_render(known, extra):
    argv = [str(config.BLENDER_EXE), "-b", "--python", str(RENDER_SCRIPT), "--", *extra]
    return _run_or_probe(argv, known.probe, "render")


def cmd_jury(known, extra):
    script = SPRITE_JURY_SCRIPT if known.target == "sprite" else PACK_JURY_SCRIPT
    argv = [sys.executable, str(script), *extra]
    # jury has no --probe/--dry-run per the task spec (only mesh/retexture/patch/render do);
    # it's a read-only/API-call stage, not GPU time, so a dry-run wrapper adds little value.
    print(f"[run:jury:{known.target}] {' '.join(str(a) for a in argv)}", flush=True)
    result = subprocess.run(argv)
    return result.returncode


def cmd_doctor(known, extra):
    checks = [
        ("MODEL_ROOT", config.MODEL_ROOT),
        ("COMFY_ROOT", config.COMFY_ROOT),
        ("ROSTER", config.ROSTER),
        ("BLENDER_EXE", config.BLENDER_EXE),
    ]
    fail = False
    print("=== 3d-prerender doctor ===", flush=True)
    for name, path in checks:
        ok = Path(path).exists()
        status = "PASS" if ok else "FAIL"
        if not ok:
            fail = True
        print(f"[{status}] {name} = {path}", flush=True)

    # non-fatal HTTP reachability check against COMFY_URL — report either way
    try:
        req = urllib.request.Request(config.COMFY_URL, method="GET")
        urllib.request.urlopen(req, timeout=3)
        print(f"[PASS] COMFY_URL reachable = {config.COMFY_URL}", flush=True)
    except urllib.error.HTTPError as e:
        # ComfyUI returns a valid HTTP response (even a 404) if the server is up.
        print(f"[PASS] COMFY_URL reachable = {config.COMFY_URL} (HTTP {e.code})", flush=True)
    except Exception as e:
        print(f"[INFO] COMFY_URL unreachable = {config.COMFY_URL} ({e})", flush=True)

    print("", flush=True)
    if fail:
        print("doctor: one or more required paths are missing.", flush=True)
        return 1
    print("doctor: all required paths present.", flush=True)
    return 0


def cmd_pipeline(known, extra):
    """Chain mesh -> retexture -> render for one character. Thin convenience wrapper —
    not a rewrite of the individual stages, and not a replacement for running them by hand
    when you need per-stage flags beyond --image/--mesh/--out/--glb.
    """
    image = known.image
    workdir = Path(known.workdir) if known.workdir else HERE
    mesh_out = workdir / f"{known.name}_mesh.glb"
    retexture_out = workdir / f"{known.name}_retextured.glb"

    mesh_argv = [sys.executable, str(MESH_SCRIPT), "--image", str(image), "--out", str(mesh_out), *extra]
    retexture_argv = [
        sys.executable, str(RETEXTURE_SCRIPT),
        "--mesh", str(mesh_out), "--image", str(image), "--out", str(retexture_out), *extra,
    ]
    render_argv = [str(config.BLENDER_EXE), "-b", "--python", str(RENDER_SCRIPT), "--", "--glb", str(retexture_out), "--out", str(workdir), *extra]

    if known.probe:
        print(f"[probe:pipeline:mesh] {' '.join(str(a) for a in mesh_argv)}", flush=True)
        print(f"[probe:pipeline:retexture] {' '.join(str(a) for a in retexture_argv)}", flush=True)
        print(f"[probe:pipeline:render] {' '.join(str(a) for a in render_argv)}", flush=True)
        return 0

    print(f"[run:pipeline:mesh] {' '.join(str(a) for a in mesh_argv)}", flush=True)
    rc = subprocess.run(mesh_argv).returncode
    if rc != 0:
        print(f"pipeline: mesh stage failed (exit {rc}), stopping.", flush=True)
        return rc

    print(f"[run:pipeline:retexture] {' '.join(str(a) for a in retexture_argv)}", flush=True)
    rc = subprocess.run(retexture_argv).returncode
    if rc != 0:
        print(f"pipeline: retexture stage failed (exit {rc}), stopping.", flush=True)
        return rc

    print(f"[run:pipeline:render] {' '.join(str(a) for a in render_argv)}", flush=True)
    rc = subprocess.run(render_argv).returncode
    if rc != 0:
        print(f"pipeline: render stage failed (exit {rc}), stopping.", flush=True)
        return rc

    print("pipeline: mesh -> retexture -> render complete.", flush=True)
    return 0


def build_parser():
    ap = argparse.ArgumentParser(
        prog="cli.py",
        description="3d-prerender pipeline dispatcher (mesh -> retexture -> patch -> render -> jury).",
    )
    sub = ap.add_subparsers(dest="command", required=True)

    p_mesh = sub.add_parser("mesh", help="run mesh_character.py (image -> GLB mesh via TRELLIS.2)")
    _add_probe(p_mesh)
    p_mesh.set_defaults(func=cmd_mesh)

    p_retexture = sub.add_parser("retexture", help="run retexture_character.py (mesh + image -> re-textured GLB)")
    _add_probe(p_retexture)
    p_retexture.set_defaults(func=cmd_retexture)

    p_patch = sub.add_parser("patch", help="run texture_patch_region.py (direct texture-space patch on a GLB)")
    _add_probe(p_patch)
    p_patch.set_defaults(func=cmd_patch)

    p_render = sub.add_parser("render", help="run sprite_render.py inside Blender (GLB -> 8-direction sprite renders)")
    _add_probe(p_render)
    p_render.set_defaults(func=cmd_render)

    p_jury = sub.add_parser("jury", help="run pack_jury.py or sprite_jury.py (cloud-vision QA pass)")
    p_jury.add_argument(
        "--target", choices=["pack", "sprite"], default="pack",
        help="'pack' = pack_jury.py (whole pack, front sprite only), 'sprite' = sprite_jury.py (one character, front/side/back). Default: pack.",
    )
    p_jury.set_defaults(func=cmd_jury)

    p_doctor = sub.add_parser("doctor", help="validate config.py paths exist + probe COMFY_URL reachability")
    p_doctor.set_defaults(func=cmd_doctor)

    p_pipeline = sub.add_parser("pipeline", help="chain mesh -> retexture -> render for one character")
    p_pipeline.add_argument("--image", required=True, help="source concept image")
    p_pipeline.add_argument("--name", required=True, help="character slug, used to name intermediate files")
    p_pipeline.add_argument("--workdir", default=None, help="directory for intermediate/output files (default: 3d-prerender/)")
    _add_probe(p_pipeline)
    p_pipeline.set_defaults(func=cmd_pipeline)

    return ap


def main():
    ap = build_parser()
    known, extra = ap.parse_known_args()
    return known.func(known, extra)


if __name__ == "__main__":
    sys.exit(main())
