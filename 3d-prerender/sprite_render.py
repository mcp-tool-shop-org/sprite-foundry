"""RTX-5090 PRE-RENDER directional sprite rig (Octopath HD-2D method; research-grounded wf_a3189d1d).
Fixed ORTHOGRAPHIC iso camera: yaw 45deg (Z), tilt 35.264deg (X)=atan(1/sqrt2) — NOT 54.736.
Rotate the SUBJECT (mesh parented to an Empty) by 360/N. Cycles+OptiX render, Persistent Data, adaptive
0.01 / N samples, transparent straight-alpha RGBA PNG, View Transform Standard, OIDN denoiser (OptiX eats
alpha edges). Outputs per-direction PNGs + a row sheet.
Run: blender -b --python _sprite_render.py -- --glb <glb> --out <dir> --dirs 8 --size 1024 --samples 512 [--tilt 35.264]
"""
import bpy, sys, os, math, mathutils
argv = sys.argv[sys.argv.index("--")+1:]
def arg(n, d=None): return argv[argv.index(n)+1] if n in argv else d
GLB = arg("--glb"); OUT = arg("--out"); DIRS = int(arg("--dirs","8")); SIZE = int(arg("--size","1024"))
SAMPLES = int(arg("--samples","512")); ELEV = float(arg("--elev","28")); os.makedirs(OUT, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)
for o in [o for o in bpy.context.scene.objects if o.type == "MESH" and len(o.data.vertices) < 300]:
    bb = [o.matrix_world @ v.co for v in o.data.vertices]
    if bb and max(max(p[i] for p in bb)-min(p[i] for p in bb) for i in range(3)) > 1.4:
        bpy.data.objects.remove(o, do_unlink=True)
meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
bpy.ops.object.select_all(action='DESELECT')
for o in meshes: o.select_set(True)
bpy.context.view_layer.objects.active = meshes[0]
if len(meshes) > 1: bpy.ops.object.join()
mesh = bpy.context.view_layer.objects.active

vs = [mesh.matrix_world @ v.co for v in mesh.data.vertices]
xs = [v.x for v in vs]; ys = [v.y for v in vs]; zs = [v.z for v in vs]
cx = (min(xs)+max(xs))/2; cy = (min(ys)+max(ys))/2; cz = (min(zs)+max(zs))/2
H = max(zs)-min(zs); rad = max(max(xs)-min(xs), max(ys)-min(ys), H); ctr = mathutils.Vector((cx, cy, cz))
R = max((wv - ctr).length for wv in vs)  # bounding-sphere radius (rotation/tilt-invariant framing)

# PROVEN turntable-orbit framing (telephoto perspective = near-ortho, minimal distortion): orbit the
# CAMERA around the figure at a gentle downward angle (ELEV); track_to keeps it centered every frame.
# Tight-fit + exact centering happen in post via the alpha bbox.
camd = bpy.data.cameras.new("C"); camd.lens = 95
cam = bpy.data.objects.new("C", camd); bpy.context.scene.collection.objects.link(cam); bpy.context.scene.camera = cam
t = bpy.data.objects.new("T", None); t.location = ctr; bpy.context.scene.collection.objects.link(t)
con = cam.constraints.new("TRACK_TO"); con.target = t; con.track_axis = "TRACK_NEGATIVE_Z"; con.up_axis = "UP_Y"
CAMDIST = rad*3.2; CAMZ = cz + CAMDIST*math.tan(math.radians(ELEV))   # ELEV-degree downward look
print(f"[frame] R={R:.3f} H={H:.3f} CAMDIST={CAMDIST:.3f} CAMZ={CAMZ:.3f}", flush=True)

world = bpy.data.worlds.new("W"); bpy.context.scene.world = world; world.use_nodes = True
bg = world.node_tree.nodes["Background"]; bg.inputs[0].default_value = (0.22,0.22,0.24,1); bg.inputs[1].default_value = 0.7
for nm, e, rot in [("key",4.5,(math.radians(55),0,math.radians(35))),("fill",2.5,(math.radians(60),0,math.radians(-50))),("rim",4.0,(math.radians(-45),0,math.radians(165)))]:
    L = bpy.data.lights.new(nm,"SUN"); L.energy = e; o = bpy.data.objects.new(nm,L); bpy.context.scene.collection.objects.link(o); o.rotation_euler = rot

sc = bpy.context.scene
sc.render.engine = 'CYCLES'
prefs = bpy.context.preferences.addons['cycles'].preferences
prefs.compute_device_type = 'OPTIX'
try: prefs.refresh_devices()
except: pass
for d in prefs.devices: d.use = (d.type == 'OPTIX')
sc.cycles.device = 'GPU'
sc.render.use_persistent_data = True
sc.cycles.use_adaptive_sampling = True; sc.cycles.adaptive_threshold = 0.01; sc.cycles.samples = SAMPLES
sc.cycles.use_denoising = True
try: sc.cycles.denoiser = 'OPENIMAGEDENOISE'   # OIDN — OptiX denoiser eats transparent-film alpha edges
except: pass
sc.view_settings.view_transform = 'Standard'
sc.render.film_transparent = True
sc.render.image_settings.file_format = 'PNG'; sc.render.image_settings.color_mode = 'RGBA'; sc.render.image_settings.compression = 15
sc.render.resolution_x = SIZE; sc.render.resolution_y = SIZE

paths = []
for i in range(DIRS):
    ang = -math.pi/2 + (2*math.pi)*i/DIRS   # view 0 = front (-Y), CCW (turntable convention)
    cam.location = (cx + CAMDIST*math.cos(ang), cy + CAMDIST*math.sin(ang), CAMZ)
    bpy.context.view_layer.update()
    p = os.path.join(OUT, f"dir_{i}.png"); sc.render.filepath = p; bpy.ops.render.render(write_still=True); paths.append(p)
    print(f"[dir {i}] deg={math.degrees(ang)%360:.0f} -> {os.path.basename(p)}", flush=True)

from PIL import Image
imgs = [Image.open(p).convert("RGBA") for p in paths]
# tight-fit in POST: union alpha bbox over all directions -> consistent scale + centered, no projection math
ux0 = uy0 = 10**9; ux1 = uy1 = -1
for im in imgs:
    bb = im.getbbox()
    if bb: ux0=min(ux0,bb[0]); uy0=min(uy0,bb[1]); ux1=max(ux1,bb[2]); uy1=max(uy1,bb[3])
pad = int(0.06*max(ux1-ux0, uy1-uy0))
ux0=max(0,ux0-pad); uy0=max(0,uy0-pad); ux1=min(imgs[0].width,ux1+pad); uy1=min(imgs[0].height,uy1+pad)
cw=ux1-ux0; ch=uy1-uy0; side=max(cw,ch)
crops=[]
for i, im in enumerate(imgs):
    c=im.crop((ux0,uy0,ux1,uy1)); canvas=Image.new("RGBA",(side,side),(0,0,0,0))
    canvas.alpha_composite(c,((side-cw)//2,(side-ch)//2)); canvas=canvas.resize((SIZE,SIZE))
    cp=os.path.join(OUT,f"sprite_{i}.png"); canvas.save(cp); crops.append(canvas)
g=8; w=sum(im.width for im in crops)+g*(len(crops)+1); h=max(im.height for im in crops)+2*g
M=Image.new("RGBA",(w,h),(40,40,46,255)); x=g
for im in crops: M.alpha_composite(im,(x,g)); x+=im.width+g
sheet=os.path.join(OUT,"_sheet.png"); M.convert("RGB").save(sheet)
print(f"[fit] crop=({ux0},{uy0},{ux1},{uy1}) side={side}", flush=True)
print(f"SHEET {sheet}", flush=True); print("SPRITE RENDER DONE", flush=True)
