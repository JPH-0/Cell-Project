"""
ANIMAL CELL - 3D model builder for Blender 3.6+
------------------------------------------------
Builds a round, textbook-style animal cell with a cutaway wedge so you can
see inside, then exports it as a .glb file for a three.js website.

HOW TO RUN (Blender 3.6):
  1. File > New > General   (this script clears the scene!)
  2. Click the "Scripting" tab at the top
  3. In the text editor click "Open" (or "New" and paste this in)
  4. Click "Run Script" (the play button)
  5. Files are saved to:  Desktop/AnimalCell/
        animal_cell.glb    <- use this on the website
        animal_cell.blend  <- the Blender file

Organelles included:
  Cell membrane, Cytoplasm, Nucleus, Nucleolus, Rough ER, Smooth ER,
  Ribosomes, Golgi body, Mitochondria, Lysosomes, Vacuoles/Vesicles

Every object carries custom properties "organelle" and "info". They export
into the .glb (as "extras"), so the website can show the name and a short
description when someone clicks a part.
"""

import bpy
import bmesh
import math
import os
import random
from mathutils import Vector, Matrix

# ----------------------------------------------------------------- settings
OUTPUT_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "AnimalCell")
R = 2.0            # cell radius (Blender units)
SEED = 7           # change for a different random arrangement
# False = cutaway model with the wedge removed (animal_cell.glb)
# True  = closed, uncut cell for the website intro (animal_cell_full.glb)
MAKE_FULL_CELL = os.environ.get("MAKE_FULL_CELL") == "1"
SUFFIX = "_full" if MAKE_FULL_CELL else ""
random.seed(SEED)

INFO = {
    "Cell Membrane": "The thin, flexible outer boundary of the cell. It controls what goes in and out.",
    "Cytoplasm": "The jelly-like fluid that fills the cell and holds all the organelles in place.",
    "Nucleus": "The control center of the cell. It stores the DNA, the instructions for everything the cell does.",
    "Nucleolus": "A dense spot inside the nucleus that builds ribosomes.",
    "Rough ER": "Folded membranes covered in ribosomes. It makes and folds proteins.",
    "Smooth ER": "A network of tubes with no ribosomes. It makes fats (lipids) and helps remove toxins.",
    "Ribosomes": "Tiny protein factories. Some float freely, others sit on the rough ER.",
    "Golgi Body": "The cell's packing and shipping center. It sorts proteins and sends them out in vesicles.",
    "Mitochondria": "The powerhouse of the cell. It turns food into energy (ATP).",
    "Lysosome": "The cell's clean-up crew. It holds enzymes that break down waste and worn-out parts.",
    "Vacuoles/Vesicles": "Small bubbles that store and carry materials around the cell. Animal cells have small vacuoles.",
}

# ------------------------------------------------------------ clear scene
for ob in list(bpy.data.objects):
    bpy.data.objects.remove(ob, do_unlink=True)
for datablocks in (bpy.data.meshes, bpy.data.materials, bpy.data.curves,
                   bpy.data.cameras, bpy.data.lights):
    for b in list(datablocks):
        if b.users == 0:
            datablocks.remove(b)
for c in list(bpy.data.collections):
    bpy.data.collections.remove(c)

scene = bpy.context.scene
cell_coll = bpy.data.collections.new("Animal Cell")
scene.collection.children.link(cell_coll)
sub = {}
for name in INFO:
    c = bpy.data.collections.new(name)
    cell_coll.children.link(c)
    sub[name] = c

# --------------------------------------------------------------- materials
def _set(node, names, value):
    for n in names:
        if n in node.inputs:
            node.inputs[n].default_value = value
            return


def make_mat(name, color, rough=0.45, alpha=1.0, glow=0.0, sheen=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (*color, 1.0)
    _set(b, ["Roughness"], rough)
    _set(b, ["Alpha"], alpha)
    if glow:
        _set(b, ["Emission Color", "Emission"], (*color, 1.0))
        _set(b, ["Emission Strength"], glow)
    if sheen:
        _set(b, ["Sheen Weight", "Sheen"], sheen)
    m.diffuse_color = (*color, alpha)          # viewport colour
    if alpha < 1.0:
        for attr, val in (("blend_method", "BLEND"),
                          ("surface_render_method", "BLENDED"),
                          ("shadow_method", "HASHED")):
            if hasattr(m, attr):
                try:
                    setattr(m, attr, val)
                except Exception:
                    pass
        m.use_backface_culling = False
    return m


MAT = {
    "membrane":   make_mat("Cell Membrane", (1.00, 0.24, 0.025), 0.35, 0.80, sheen=0.5),
    "cytoplasm":  make_mat("Cytoplasm", (0.55, 0.85, 0.92), 0.10, 0.16),
    "nucleus":    make_mat("Nucleus", (0.42, 0.33, 0.80), 0.40),
    "nucleolus":  make_mat("Nucleolus", (0.70, 0.12, 0.45), 0.50),
    "pore":       make_mat("Nuclear Pore", (0.20, 0.15, 0.45), 0.60),
    "rer":        make_mat("Rough ER", (0.28, 0.52, 0.95), 0.40),
    "ser":        make_mat("Smooth ER", (0.30, 0.78, 0.62), 0.35),
    "ribosome":   make_mat("Ribosome", (0.18, 0.10, 0.35), 0.60),
    "golgi":      make_mat("Golgi Body", (0.98, 0.62, 0.15), 0.35),
    "mito":       make_mat("Mitochondria Outer", (0.22, 0.78, 0.30), 0.30, 0.55),
    "cristae":    make_mat("Mitochondria Cristae", (0.72, 1.00, 0.55), 0.40),
    "lysosome":   make_mat("Lysosome", (0.90, 0.20, 0.25), 0.35),
    "vesicle":    make_mat("Vesicle", (1.00, 0.88, 0.45), 0.25, 0.85),
    "vacuole":    make_mat("Vacuole", (0.62, 0.82, 1.00), 0.10, 0.55),
}

# ----------------------------------------------------------------- helpers
def in_wedge(p, margin=0.0):
    """True if point p is inside the cut-away wedge (x>0, y<0, z>0)."""
    return p.x > -margin and p.y < margin and p.z > -margin


def cut_wedge(bm):
    if MAKE_FULL_CELL:
        return
    faces = [f for f in bm.faces if in_wedge(f.calc_center_median(), -1e-4)]
    bmesh.ops.delete(bm, geom=faces, context='FACES')



def finish(bm, name, mats, kind, loc=(0, 0, 0), rot=None, smooth=True):
    me = bpy.data.meshes.new(name)
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    for m in mats:
        me.materials.append(m)
    if smooth:
        for p in me.polygons:
            p.use_smooth = True
    ob = bpy.data.objects.new(name, me)
    sub[kind].objects.link(ob)
    ob.location = loc
    if rot is not None:
        ob.rotation_mode = 'QUATERNION'
        ob.rotation_quaternion = rot
    ob["organelle"] = kind
    ob["info"] = INFO[kind]
    return ob


def sphere_bm(radius, segs=48, rings=24, matrix=None):
    bm = bmesh.new()
    kw = dict(u_segments=segs, v_segments=rings, radius=radius)
    if matrix is not None:
        kw["matrix"] = matrix
    bmesh.ops.create_uvsphere(bm, **kw)
    return bm


def solidify(bm, thickness):
    bmesh.ops.solidify(bm, geom=bm.faces[:], thickness=thickness)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])


def sph(r, az, el):
    """Spherical -> cartesian (degrees)."""
    a, e = math.radians(az), math.radians(el)
    return Vector((r * math.cos(e) * math.cos(a), r * math.cos(e) * math.sin(a), r * math.sin(e)))


occupied = []   # (centre, radius) of things already placed


def free_spot(p, rad):
    if in_wedge(p, rad + 0.05):
        return False
    if p.length + rad > R - 0.12:
        return False
    return all((p - c).length > rad + cr + 0.04 for c, cr in occupied)


def random_point(rmin, rmax, rad, tries=4000):
    for _ in range(tries):
        d = Vector((random.gauss(0, 1), random.gauss(0, 1), random.gauss(0, 1))).normalized()
        p = d * random.uniform(rmin, rmax)
        if free_spot(p, rad):
            return p
    return None


# --------------------------------------------------------- cell membrane
bm = sphere_bm(R, 64, 32)
cut_wedge(bm)
solidify(bm, 0.07)
finish(bm, "Cell_Membrane", [MAT["membrane"]], "Cell Membrane")

# --------------------------------------------------------------- cytoplasm
bm = sphere_bm(R - 0.075, 64, 32)
cut_wedge(bm)
finish(bm, "Cytoplasm", [MAT["cytoplasm"]], "Cytoplasm")

# ----------------------------------------------------------------- nucleus
NUC_R = 0.70
bm = sphere_bm(NUC_R, 48, 24)
cut_wedge(bm)
solidify(bm, 0.05)
shell = set(bm.faces)
# nuclear pores: little dark dots on the outer surface
for i in range(70):
    d = Vector((random.gauss(0, 1), random.gauss(0, 1), random.gauss(0, 1))).normalized()
    if not MAKE_FULL_CELL and in_wedge(d * NUC_R, 0.06):
        continue
    bmesh.ops.create_uvsphere(bm, u_segments=8, v_segments=5, radius=0.028,
                              matrix=Matrix.Translation(d * (NUC_R + 0.005)))
for f in bm.faces:
    f.material_index = 0 if f in shell else 1
finish(bm, "Nucleus", [MAT["nucleus"], MAT["pore"]], "Nucleus")
occupied.append((Vector((0, 0, 0)), NUC_R + 0.05))

# --------------------------------------------------------------- nucleolus
bm = sphere_bm(0.24, 32, 16)
# lumpy surface
for v in bm.verts:
    n = v.co.normalized()
    v.co += n * 0.025 * math.sin(7 * n.x + 3) * math.cos(6 * n.y + 1) * math.sin(5 * n.z + 2)
finish(bm, "Nucleolus", [MAT["nucleolus"]], "Nucleolus", loc=(0.12, -0.12, 0.10))

# ---------------------------------------------------------------- rough ER
def shell_patch(bm, r, az0, az1, el0, el1, ripple, freq, nu=60, nv=22):
    grid = []
    for i in range(nu + 1):
        row = []
        for j in range(nv + 1):
            az = az0 + (az1 - az0) * i / nu
            el = el0 + (el1 - el0) * j / nv
            rr = r + ripple * math.sin(math.radians(az) * freq) * math.cos(math.radians(el) * freq * 0.7)
            row.append(bm.verts.new(sph(rr, az, el)))
        grid.append(row)
    for i in range(nu):
        for j in range(nv):
            bm.faces.new((grid[i][j], grid[i + 1][j], grid[i + 1][j + 1], grid[i][j + 1]))


RER_SHEETS = [  # radius, az0, az1, el0, el1, ripple, freq
    (0.86, 15, 255, -42, 42, 0.025, 9),
    (0.97, 25, 245, -38, 46, 0.030, 8),
    (1.08, 35, 235, -46, 36, 0.030, 7),
    (1.19, 45, 225, -34, 40, 0.035, 6),
    (0.90, 255, 352, -58, -12, 0.025, 8),
    (1.03, 262, 345, -52, -16, 0.030, 7),
]
bm = bmesh.new()
for s in RER_SHEETS:
    shell_patch(bm, *s)
solidify(bm, 0.035)
finish(bm, "Rough_ER", [MAT["rer"]], "Rough ER")

# ---------------------------------------------------------------- ribosomes
rib = bmesh.new()
rib_count = 0
for (r, az0, az1, el0, el1, ripple, freq) in RER_SHEETS:      # bound to RER
    for _ in range(170):
        az = random.uniform(az0 + 2, az1 - 2)
        el = random.uniform(el0 + 2, el1 - 2)
        rr = r + ripple * math.sin(math.radians(az) * freq) * math.cos(math.radians(el) * freq * 0.7)
        side = random.choice((-1, 1))
        p = sph(rr + side * 0.04, az, el)
        bmesh.ops.create_uvsphere(rib, u_segments=6, v_segments=4, radius=0.02,
                                  matrix=Matrix.Translation(p))
        rib_count += 1
occupied.append((Vector((0, 0, 0)), 1.27))   # nucleus + rough ER zone

# --------------------------------------------------------------- golgi body
# A stack of curved, arch-shaped sacs (cisternae) with swollen ends,
# like the classic textbook drawing.
G_DIR = sph(1.0, 40, -20).normalized()   # below the middle so it stays whole when cut in half
G_POS = G_DIR * 1.50
_gy = Vector((G_DIR.x, G_DIR.y, 0)).normalized()          # level: arches lie flat, facing the nucleus
_gz = Vector((0, 0, 1))
_gx = _gy.cross(_gz).normalized()
g_mat = Matrix((_gx, _gy, _gz)).transposed()               # local +Y points away from nucleus
g_rot = g_mat.to_quaternion()

G_SHIFT = 0.74                  # moves the stack so the object origin sits in its middle


def golgi_sac(bm, arc_r, span, half_thick, half_depth, nu=80, nv=22):
    """One curved, flattened sac with round, swollen ends."""
    rings = []
    for i in range(nu + 1):
        u = i / nu
        ang = math.pi / 2 + span * (u - 0.5)             # gentle arch around the local +Y axis
        e = 2 * u - 1
        cap = max(0.0, 1 - e ** 16) ** 0.5               # closes the ends smoothly
        knob = math.exp(-((u - 0.055) / 0.06) ** 2) + math.exp(-((u - 0.945) / 0.06) ** 2)
        t = half_thick * (1 + 1.6 * knob) * cap          # swollen ends
        body = max(0.0, 1 - e * e) ** 0.6                # rounded like a lens when seen from above
        d = max(half_depth * body, half_thick * 2.4 * knob) * cap
        rr = arc_r + 0.006 * math.sin(u * math.pi * 6)   # slight wobble
        radial = Vector((math.cos(ang), math.sin(ang), 0))
        centre = radial * rr - Vector((0, G_SHIFT, 0))
        ring = []
        for j in range(nv):
            a = 2 * math.pi * j / nv
            ring.append(bm.verts.new(centre + radial * (t * math.cos(a)) + Vector((0, 0, d * math.sin(a)))))
        rings.append(ring)
    for i in range(nu):
        for j in range(nv):
            bm.faces.new((rings[i][j], rings[i][(j + 1) % nv], rings[i + 1][(j + 1) % nv], rings[i + 1][j]))


bm = bmesh.new()
for k in range(6):
    tk = (k - 2.5) / 2.5                                  # -1 .. 1
    arc_r = 0.58 + k * 0.068                              # stacked, concentric arches
    span = math.radians(78) * (1 - 0.18 * tk * tk)        # middle sacs longest
    golgi_sac(bm, arc_r, span, half_thick=0.022, half_depth=0.20 * (1 - 0.2 * tk * tk))
bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-5)
finish(bm, "Golgi_Body", [MAT["golgi"]], "Golgi Body", loc=G_POS, rot=g_rot)
occupied.append((G_POS, 0.62))

# vesicles beside the golgi (same ones as before)
ves_count = 0
for i in range(10):
    side = random.choice((-1, 1))
    local = Vector((side * random.uniform(0.48, 0.62), random.uniform(-0.2, 0.2), random.uniform(-0.15, 0.35)))
    p = G_POS + g_mat @ local
    if in_wedge(p, 0.08) or p.length > R - 0.2:
        continue
    bm = sphere_bm(random.uniform(0.035, 0.055), 16, 10)
    finish(bm, "Vesicle_%02d" % (ves_count + 1), [MAT["vesicle"]], "Vacuoles/Vesicles", loc=p)
    occupied.append((p, 0.06))
    ves_count += 1

# ---------------------------------------------------------------- smooth ER
curve = bpy.data.curves.new("Smooth_ER_curve", 'CURVE')
curve.dimensions = '3D'
curve.bevel_depth = 0.032
curve.bevel_resolution = 3
curve.resolution_u = 8
curve.use_fill_caps = True
ser_pts_all = []
for k in range(9):
    sp = curve.splines.new('NURBS')
    n = 9
    sp.points.add(n - 1)
    az_start = random.uniform(195, 250)
    el_start = random.uniform(-40, 35)
    for i in range(n):
        az = az_start - i * random.uniform(6, 10)
        el = el_start + 14 * math.sin(i * 0.9 + k)
        r = 1.36 + 0.14 * math.sin(i * 1.3 + k * 2)
        p = sph(r, az, el)
        sp.points[i].co = (p.x, p.y, p.z, 1.0)
        ser_pts_all.append(p)
    sp.use_endpoint_u = True
    sp.order_u = 4
ser_obj = bpy.data.objects.new("Smooth_ER_tmp", curve)
scene.collection.objects.link(ser_obj)
bpy.context.view_layer.update()
dg = bpy.context.evaluated_depsgraph_get()
ser_mesh = bpy.data.meshes.new_from_object(ser_obj.evaluated_get(dg))
bpy.data.objects.remove(ser_obj, do_unlink=True)
bpy.data.curves.remove(curve)
ser_mesh.name = "Smooth_ER"
ser_mesh.materials.clear()
ser_mesh.materials.append(MAT["ser"])
for p in ser_mesh.polygons:
    p.use_smooth = True
ser = bpy.data.objects.new("Smooth_ER", ser_mesh)
sub["Smooth ER"].objects.link(ser)
ser["organelle"] = "Smooth ER"
ser["info"] = INFO["Smooth ER"]
for p in ser_pts_all:
    occupied.append((p, 0.07))

# ------------------------------------------------------------- mitochondria
def mitochondrion(idx, pos):
    L, W = 0.30, 0.12
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=32, v_segments=16, radius=1.0)
    for v in bm.verts:
        v.co = Vector((v.co.x * L, v.co.y * W, v.co.z * W))
    outer = set(bm.faces)
    for c in range(7):                         # cristae folds
        x = -L * 0.72 + c * (L * 1.44 / 6)
        rad = W * 0.80 * math.sqrt(max(0.15, 1 - (x / L) ** 2))
        off = (rad * 0.35) * (1 if c % 2 else -1)
        bmesh.ops.create_cone(bm, cap_ends=True, segments=20, radius1=rad, radius2=rad,
                              depth=0.012,
                              matrix=Matrix.Translation((x, off, 0)) @ Matrix.Rotation(math.radians(90), 4, 'Y'))
    for f in bm.faces:
        f.material_index = 0 if f in outer else 1
    # random tangential orientation (lie flat along the cell surface)
    radial = pos.normalized()
    tang = radial.cross(Vector((random.uniform(-1, 1), random.uniform(-1, 1), random.uniform(-1, 1)))).normalized()
    rot = Vector((1, 0, 0)).rotation_difference(tang)
    return finish(bm, "Mitochondrion_%02d" % idx, [MAT["mito"], MAT["cristae"]], "Mitochondria", loc=pos, rot=rot)


m_count = 0
for i in range(8):
    p = random_point(1.50, 1.66, 0.21)
    if p is None:
        continue
    m_count += 1
    mitochondrion(m_count, p)
    occupied.append((p, 0.24))

# ---------------------------------------------------------------- lysosomes
l_count = 0
for i in range(7):
    rad = random.uniform(0.08, 0.11)
    p = random_point(1.32, 1.72, rad)
    if p is None:
        continue
    l_count += 1
    bm = sphere_bm(rad, 24, 12)
    # speckled enzyme granules inside look: slight bumps
    for v in bm.verts:
        v.co *= 1 + 0.05 * math.sin(v.co.x * 90) * math.sin(v.co.y * 80)
    finish(bm, "Lysosome_%02d" % l_count, [MAT["lysosome"]], "Lysosome", loc=p)
    occupied.append((p, rad))

# ------------------------------------------------------ vacuoles / vesicles
for i in range(4):
    rad = random.uniform(0.15, 0.2)
    p = random_point(1.32, 1.65, rad)
    if p is None:
        continue
    bm = sphere_bm(rad, 32, 16)
    finish(bm, "Vacuole_%02d" % (i + 1), [MAT["vacuole"]], "Vacuoles/Vesicles", loc=p)
    occupied.append((p, rad))
for i in range(8):
    rad = random.uniform(0.04, 0.06)
    p = random_point(1.25, 1.8, rad)
    if p is None:
        continue
    ves_count += 1
    bm = sphere_bm(rad, 16, 10)
    finish(bm, "Vesicle_%02d" % ves_count, [MAT["vesicle"]], "Vacuoles/Vesicles", loc=p)
    occupied.append((p, rad))

# ------------------------------------------------------ free ribosomes
for _ in range(260):
    p = random_point(1.28, 1.85, 0.02, tries=200)
    if p is None:
        continue
    bmesh.ops.create_uvsphere(rib, u_segments=6, v_segments=4, radius=0.02,
                              matrix=Matrix.Translation(p))
    rib_count += 1
finish(rib, "Ribosomes", [MAT["ribosome"]], "Ribosomes")

# --------------------------------------------- camera, lights, background
cam_data = bpy.data.cameras.new("Camera")
cam_data.lens = 50
cam = bpy.data.objects.new("Camera", cam_data)
scene.collection.objects.link(cam)
cam.location = (6.6, -6.6, 5.2)
cam.rotation_euler = (Vector((0, 0, 0)) - cam.location).to_track_quat('-Z', 'Y').to_euler()
scene.camera = cam

for name, loc, energy, size in (("Key Light", (5, -4, 7), 900, 5), ("Fill Light", (-6, -3, 2), 300, 6),
                                ("Rim Light", (-2, 6, 5), 500, 4)):
    ld = bpy.data.lights.new(name, 'AREA')
    ld.energy = energy
    ld.size = size
    lo = bpy.data.objects.new(name, ld)
    lo.location = loc
    lo.rotation_euler = (Vector((0, 0, 0)) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    scene.collection.objects.link(lo)

if scene.world is None:
    scene.world = bpy.data.worlds.new("World")
scene.world.use_nodes = True
bg = scene.world.node_tree.nodes.get("Background")
if bg:
    bg.inputs[0].default_value = (0.02, 0.03, 0.06, 1)
    bg.inputs[1].default_value = 1.0

# ------------------------------------------------------------------ export
os.makedirs(OUTPUT_DIR, exist_ok=True)
cell_objs = list(cell_coll.all_objects)
for ob in scene.objects:
    ob.select_set(ob in cell_objs)
glb_path = os.path.join(OUTPUT_DIR, "animal_cell%s.glb" % SUFFIX)
try:
    bpy.ops.export_scene.gltf(filepath=glb_path, export_format='GLB', use_selection=True,
                              export_apply=True, export_extras=True, export_yup=True)
    print("Exported:", glb_path)
except Exception as e:
    print("GLB export failed:", e)
try:
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUTPUT_DIR, "animal_cell%s.blend" % SUFFIX))
except Exception as e:
    print("Save failed:", e)

print("Animal cell built: %d mitochondria, %d lysosomes, %d vesicles, %d ribosomes"
      % (m_count, l_count, ves_count, rib_count))
