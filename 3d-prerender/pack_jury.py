"""Generic pack jury: judge every character's FRONT sprite for coherence. Refute-by-default, 2-of-3.
Run: python _pack_jury.py <pack-dir>   (expects <slug>_sprite/sprite_0.png)
"""
import base64, json, urllib.request, concurrent.futures as cf, sys, os
from pathlib import Path
OLLAMA = "http://127.0.0.1:11434/api/chat"
JURY = ["minimax-m3:cloud", "kimi-k2.6:cloud", "gemini-3-flash-preview:cloud"]
CANARY = "gemini-3-flash-preview:cloud"
PACK = Path(sys.argv[1])
SLUGS = ['berserker','bombardier','bosun','breaker','brig-keeper','cabin-kid','cannoneer','captain','cook','diver',
  'first-mate','harpooner','juggernaut','marine','marksman','navigator','poisoner','quartermaster','reaver','rigger',
  'sawbones','sea-witch','smuggler','stormcaller','swashbuckler','tide-cultist']

PROMPT = ("You are a STRICT 3D game-asset QA reviewer. REFUTE BY DEFAULT.\n"
  "INTENDED asset: a single stylized 3D game-character SPRITE of a fantasy PIRATE — may be human OR a fantasy "
  "species (orc/goblin/lizardfolk/frog-folk/brute), front view, usually holding a weapon, plain/transparent bg.\n"
  "This is a 3D MESH render (NOT anime/photo) — do NOT flag the CGI/3D look, matte shading, soft style, dark tones, "
  "the species, or the background. A held weapon (sword/axe/hammer/gun/harpoon/chain) IS intended, not a defect.\n"
  "Report ONLY genuine GEOMETRY/STRUCTURE defects: a melted/blobby/MISSING or caved-in face; holes or torn "
  "geometry; missing/extra/duplicated limbs; a limb detached; not a single coherent humanoid figure.\n"
  'Respond with STRICT JSON only: {"pass": true|false, "issues": ["short defect", ...]}. JSON only.')

def call(model, slug):
    img = PACK / f"{slug}_sprite" / "sprite_0.png"
    if not img.exists(): return {"model": model, "slug": slug, "pass": None, "issues": [], "error": "missing"}
    b64 = base64.b64encode(img.read_bytes()).decode()
    payload = {"model": model, "stream": False, "think": False, "messages": [{"role": "user", "content": PROMPT, "images": [b64]}]}
    try:
        req = urllib.request.Request(OLLAMA, json.dumps(payload).encode(), {"Content-Type": "application/json"})
        txt = json.loads(urllib.request.urlopen(req, timeout=300).read()).get("message", {}).get("content", "")
        i, j = txt.find("{"), txt.rfind("}")
        if i >= 0 and j > i:
            o = json.loads(txt[i:j+1]); return {"model": model, "slug": slug, "pass": bool(o.get("pass")), "issues": o.get("issues") or []}
        return {"model": model, "slug": slug, "pass": None, "issues": [], "raw": txt[:120]}
    except Exception as e:
        return {"model": model, "slug": slug, "pass": None, "issues": [], "error": str(e)[:120]}

tasks = [(m, s) for s in SLUGS for m in JURY]; res = {s: [] for s in SLUGS}
with cf.ThreadPoolExecutor(max_workers=8) as ex:
    futs = {ex.submit(call, m, s): (m, s) for m, s in tasks}
    for f in cf.as_completed(futs): m, s = futs[f]; res[s].append(f.result())

passed = []; failed = []
print("\n===== PIRATE PACK JURY (refute-by-default, 2-of-3, gemini=canary) =====")
for s in SLUGS:
    rs = res[s]; p = sum(1 for r in rs if r.get("pass") is True); dec = [r for r in rs if r.get("pass") is not None]
    v = "PASS" if p >= 2 else ("FAIL" if len(dec) >= 2 else "INCONCLUSIVE")
    (passed if v == "PASS" else failed).append(s)
    if v != "PASS":
        print(f"\n[{v}] {s} ({p}/3)")
        for r in rs:
            if r.get("pass") is False:
                can = " (canary)" if r["model"] == CANARY else ""
                print(f"    FAIL{can} {r['model']}: {'; '.join(r.get('issues') or [])}")
print(f"\n--- SUMMARY: {len(passed)}/26 PASS ---")
print("PASS:", ", ".join(passed))
print("NEEDS-WORK:", ", ".join(failed) if failed else "(none)")
