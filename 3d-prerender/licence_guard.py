"""Keep non-commercially-licensed code out of the character pipeline.

THE PROBLEM
-----------
Replacing our texture bake (see bake_glb.py) removed every CALL we make into nvdiffrast.
It did not stop nvdiffrast being LOADED, because it arrives as collateral of a package
__init__ four levels up from anything we asked for. Measured import chain:

    Trellis2ImageTo3DPipeline.from_pretrained
      -> trellis2/models/__init__.py:65          (model registry instantiates the VAE)
        -> trellis2/models/sc_vaes/fdg_vae.py:20 `from o_voxel.convert import ...`
          -> o_voxel/__init__.py:1               eagerly imports .postprocess
            -> o_voxel/postprocess.py:10         `import nvdiffrast.torch as dr`

The shape VAE genuinely needs `o_voxel.convert`. Importing ANY o_voxel submodule executes
o_voxel/__init__.py, which imports .postprocess unconditionally, whose module-scope
nvdiffrast import then fires. Nothing in the mesh-GENERATION path ever calls nvdiffrast --
it is pulled in and never used.

THE FIX
-------
Pre-seed sys.modules with a stub named `nvdiffrast` before trellis2 is imported. The
o_voxel import then binds to the stub and the NVIDIA package is never located, loaded or
executed. This is not circumvention -- we removed the only code that called it. This stops
an unnecessary transitive import of software we are not licensed to use in production.

The stub is deliberately NOT a working rasteriser. Any actual call raises immediately and
says what to use instead, so a future code path that quietly starts depending on
nvdiffrast fails loudly here rather than shipping a licence violation. That is the andon
cord: a defect stops the line rather than propagating downstream.

Usage -- MUST run before `import trellis2`:

    import licence_guard
    licence_guard.block_noncommercial()
    from trellis2.pipelines import Trellis2ImageTo3DPipeline
"""

import sys
import types

_MESSAGE = (
    "{module}.{attr} was CALLED, but nvdiffrast is blocked by licence_guard.\n"
    "  nvdiffrast is under the Nvidia Source Code License (1-Way Commercial), s3.3:\n"
    "  usable 'for research or evaluation purposes only and not for any direct or\n"
    "  indirect monetary gain' -- so it cannot be in an asset-production pipeline.\n"
    "  Our UV-space bake lives in uv_rasterize.py; use that.\n"
    "  To run the old path deliberately for COMPARISON, pass --bake ovoxel, which\n"
    "  skips this guard."
)


def _blocked_module(name: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    mod.__doc__ = "licence_guard stub -- see licence_guard.py"
    mod.__licence_guard_stub__ = True

    def __getattr__(attr):
        # Let normal dunder probing (e.g. __path__, __all__) fail quietly as usual so
        # the import machinery behaves; only real API access is an error.
        if attr.startswith("__") and attr.endswith("__"):
            raise AttributeError(attr)
        raise RuntimeError(_MESSAGE.format(module=name, attr=attr))

    mod.__getattr__ = __getattr__
    return mod


def block_noncommercial(verbose: bool = True) -> None:
    """Install stubs so nvdiffrast/nvdiffrec can never be loaded in this process."""
    already = sorted(m for m in sys.modules
                     if m.split(".")[0] in ("nvdiffrast", "nvdiffrec")
                     and not getattr(sys.modules[m], "__licence_guard_stub__", False))
    if already:
        # Too late to prevent the load; say so rather than pretend it worked.
        print(f"licence_guard: WARNING -- already imported before guard installed: {already}",
              flush=True)
        return

    for root in ("nvdiffrast", "nvdiffrec"):
        if root in sys.modules:
            continue
        mod = _blocked_module(root)
        sys.modules[root] = mod
        # `import nvdiffrast.torch as dr` needs both the submodule in sys.modules and the
        # attribute on the parent.
        for sub in ("torch",):
            full = f"{root}.{sub}"
            submod = _blocked_module(full)
            sys.modules[full] = submod
            setattr(mod, sub, submod)

    if verbose:
        print("licence_guard: nvdiffrast/nvdiffrec blocked (non-commercial licence)", flush=True)


def report(context: str = "") -> bool:
    """Print whether real (non-stub) non-commercial modules got loaded. True = clean."""
    real = sorted(m for m in sys.modules
                  if m.split(".")[0] in ("nvdiffrast", "nvdiffrec")
                  and not getattr(sys.modules[m], "__licence_guard_stub__", False))
    tag = f" {context}" if context else ""
    if real:
        print(f"LICENCE WARNING:{tag} non-commercial modules loaded: {real}", flush=True)
        return False
    print(f"LICENCE OK:{tag} no nvdiffrast/nvdiffrec loaded this run.", flush=True)
    return True
