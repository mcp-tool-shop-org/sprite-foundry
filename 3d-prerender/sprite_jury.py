"""Cross-family CLOUD-VISION jury for a directional 3D SPRITE — coherence + face gate. Refute-by-default,
2-of-3. Run: python _sprite_jury.py <sprite-dir>  (expects sprite_0/2/4.png = front/side/back)
"""
import base64, json, urllib.request, concurrent.futures as cf, sys
from pathlib import Path
OLLAMA = "http://127.0.0.1:11434/api/chat"
JURY = ["minimax-m3:cloud", "kimi-k2.6:cloud", "gemini-3-flash-preview:cloud"]
CANARY = "gemini-3-flash-preview:cloud"
D = Path(sys.argv[1])
TASKS = {"front": (D/"sprite_0.png", "FRONT"), "side": (D/"sprite_2.png", "SIDE/profile"), "back": (D/"sprite_4.png", "BACK")}

def prompt(view):
    return ("You are a STRICT 3D game-asset QA reviewer. REFUTE BY DEFAULT: assume DEFECTIVE unless clearly clean.\n"
        f"INTENDED asset: a single stylized 3D game-character SPRITE of a fantasy PIRATE CAPTAIN — bandana/headscarf, "
        f"beard, long tattered greatcoat, sash and a buckled belt, dark trousers, tall boots, holding a curved cutlass "
        f"at his side. {view} view, plain/transparent background.\n"
        "This is a 3D MESH render (NOT anime, NOT a photo) — do NOT flag the CGI/3D look, matte shading, soft style, "
        "dark coat tones, or the background. A thin curved cutlass held at the side IS intended (not a defect).\n"
        "Report ONLY genuine GEOMETRY/STRUCTURE defects: a melted/blobby/MISSING or caved-in face; holes or torn "
        "geometry; missing/extra/duplicated limbs; a limb detached; the sword exploded/shredded; not a single "
        "coherent humanoid. (Minor stray specks on the hair are a known texture artifact — mention if severe, but "
        "do not fail the asset on hair specks alone.)\n"
        'Respond with STRICT JSON only: {"pass": true|false, "issues": ["short defect", ...]}. JSON only.')

def call(model, key):
    img, view = TASKS[key]
    if not Path(img).exists(): return {"model": model, "pass": None, "issues": [], "error": "image missing"}
    b64 = base64.b64encode(Path(img).read_bytes()).decode()
    payload = {"model": model, "stream": False, "think": False, "messages": [{"role": "user", "content": prompt(view), "images": [b64]}]}
    try:
        req = urllib.request.Request(OLLAMA, json.dumps(payload).encode(), {"Content-Type": "application/json"})
        txt = json.loads(urllib.request.urlopen(req, timeout=300).read()).get("message", {}).get("content", "")
        i, j = txt.find("{"), txt.rfind("}")
        if i >= 0 and j > i:
            o = json.loads(txt[i:j+1]); return {"model": model, "pass": bool(o.get("pass")), "issues": o.get("issues") or []}
        return {"model": model, "pass": None, "issues": [], "raw": txt[:160]}
    except Exception as e:
        return {"model": model, "pass": None, "issues": [], "error": str(e)[:160]}

tasks = [(m, k) for k in TASKS for m in JURY]; res = {k: [] for k in TASKS}
with cf.ThreadPoolExecutor(max_workers=6) as ex:
    futs = {ex.submit(call, m, k): (m, k) for m, k in tasks}
    for f in cf.as_completed(futs): m, k = futs[f]; res[k].append(f.result())
print("\n===== SPRITE JURY (refute-by-default, 2-of-3, gemini=canary) =====")
for k in TASKS:
    rs = res[k]; passes = sum(1 for r in rs if r.get("pass") is True); decided = [r for r in rs if r.get("pass") is not None]
    verdict = "PASS" if passes >= 2 else ("FAIL" if len(decided) >= 2 else "INCONCLUSIVE")
    print(f"\n[{verdict}] {k}  ({passes}/{len(rs)} jury pass)")
    for r in rs:
        tag = "pass" if r.get("pass") else ("FAIL" if r.get("pass") is False else "n/a"); can = " (canary)" if r["model"] == CANARY else ""
        extra = "; ".join(r.get("issues") or []) or r.get("error") or r.get("raw") or ""
        print(f"   [{tag}]{can} {r['model']}: {extra}")
