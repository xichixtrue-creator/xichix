"""
Mo Feng Blade - Blender build script.

Builds the whole sword (blade, crystal edges, runes, energy veins, guard,
handle, pommel, gems, aura hull), the VFX meshes (slash arcs, shockwave
rings, crystal shards, rock fragments) and every texture, bakes the
procedural materials to images, and exports Roblox-ready files.

Run it either way:
  * Blender: Scripting tab > Open > build_mofeng.py > Run Script
  * Headless: python build_mofeng.py [--render]   (with the `bpy` module installed)

Output (next to this folder, in ../export, ../textures, ../previews):
  MoFengSword.fbx / .glb   the sword, one mesh per material
  MoFengVFX.fbx / .glb     slash / ring / shard / rock meshes + VFX textures
  MoFengSword.blend        the full scene
  sword_layout.json        attachment points + part info for the Roblox installer

Units are Roblox studs. Axes: blade along +Z, blade width along X,
front of the blade facing -Y. The grip's top sits at the origin.
"""

import json
import math
import os
import sys
import warnings

import bpy  # noqa: I001  (bpy must come first: it makes bmesh/mathutils importable)
import bmesh
import numpy as np
from mathutils import Matrix, Vector, noise

warnings.filterwarnings("ignore", category=DeprecationWarning)


def _script_dir():
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        if os.path.exists(os.path.join(here, "vfx_textures.py")):
            return here
    except NameError:
        pass
    for text in bpy.data.texts:      # run from Blender's text editor
        if text.filepath and text.filepath.endswith("build_mofeng.py"):
            return os.path.dirname(bpy.path.abspath(text.filepath))
    return bpy.path.abspath("//")


HERE = _script_dir()
sys.path.insert(0, HERE)
import vfx_textures as vt  # noqa: E402

ROOT = os.path.normpath(os.path.join(HERE, ".."))
EXPORT = os.path.join(ROOT, "export")
TEXTURES = os.path.join(ROOT, "textures")
PREVIEWS = os.path.join(ROOT, "previews")

# ---------------------------------------------------------------- colours

THEMES = {
    "Cyan": {"edge": (0.0, 0.72, 1.0), "rune": (0.75, 1.0, 1.0), "vein": (0.15, 1.0, 0.95),
             "gem": (0.45, 0.3, 1.0), "aura": (0.1, 0.9, 1.0), "hilt": "silver"},
    "Gold": {"edge": (1.0, 0.58, 0.06), "rune": (1.0, 0.95, 0.7), "vein": (1.0, 0.8, 0.25),
             "gem": (1.0, 0.35, 0.08), "aura": (1.0, 0.75, 0.2), "hilt": "gold"},
}

# ---------------------------------------------------------------- shape curves


def pchip(xs, ys):
    """Monotone cubic interpolation (no overshoot)."""
    n = len(xs)
    h = [xs[i + 1] - xs[i] for i in range(n - 1)]
    d = [(ys[i + 1] - ys[i]) / h[i] for i in range(n - 1)]
    m = [0.0] * n
    m[0], m[-1] = d[0], d[-1]
    for i in range(1, n - 1):
        if d[i - 1] * d[i] <= 0:
            m[i] = 0.0
        else:
            w1, w2 = 2 * h[i] + h[i - 1], h[i] + 2 * h[i - 1]
            m[i] = (w1 + w2) / (w1 / d[i - 1] + w2 / d[i])

    def f(x):
        x = min(max(x, xs[0]), xs[-1])
        i = min(n - 2, max(0, next(k for k in range(n - 1) if x <= xs[k + 1])))
        t = (x - xs[i]) / h[i]
        t2, t3 = t * t, t * t * t
        return ((2 * t3 - 3 * t2 + 1) * ys[i] + (t3 - 2 * t2 + t) * h[i] * m[i] +
                (-2 * t3 + 3 * t2) * ys[i + 1] + (t3 - t2) * h[i] * m[i + 1])
    return f


BZ0, BZ1 = 0.35, 3.25            # blade root (inside the guard) and tip
BL = BZ1 - BZ0
_HW = pchip([0.0, 0.10, 0.35, 0.62, 0.78, 0.90, 1.0], [0.25, 0.27, 0.285, 0.278, 0.252, 0.16, 0.0])


def hw(s):
    return max(0.0, _HW(s))


def crystal_ht(t, s):
    """Half thickness of the crystal blade, 0 at the cutting edge."""
    return 0.034 * (1 - min(1.0, abs(t)) ** 1.8) * (1 - 0.35 * s)


def nz(x, y=0.0, z=0.0):
    return noise.noise(Vector((x, y, z)))


CORE_W = 0.62


def core_end(u):
    return 0.70 + 0.10 * (1 - abs(u)) ** 1.3 + 0.03 * nz(u * 2.7, 0.3, 1.7)


def core_halfwidth(s, side):
    return CORE_W * hw(s) * (1 + 0.08 * nz(s * 9.0, side * 3.1, 0.5))


def core_thick(u, s):
    se = core_end(u)
    f = min(1.0, s / se)
    base = 0.058 * (1 - 0.35 * u * u) * (1 - 0.25 * s)
    rock = (0.010 * noise.fractal(Vector((u * 2.2, s * 14.0, 0.0)), 1.0, 2.0, 3) +
            0.009 * (abs(nz(u * 3.0, s * 9.0, 2.0)) * 2 - 0.6))           # chunky plates
    return max(0.0, (base + rock * (1 - u * u)) * (1 - abs(u) ** 3) * (1 - f ** 6))


def core_point(u, s, face, lift=0.0):
    side = 1 if u >= 0 else -1
    x = u * core_halfwidth(s, side)
    return Vector((x, face * (core_thick(u, s) + lift), BZ0 + s * BL))


# ---------------------------------------------------------------- mesh building


class MB:
    """Tiny mesh builder: vertices, faces and one UV per vertex."""

    def __init__(self):
        self.v, self.f, self.uv, self.smooth = [], [], [], []

    def add(self, p, uv=(0.0, 0.0)):
        self.v.append(tuple(p))
        self.uv.append(tuple(uv))
        return len(self.v) - 1

    def face(self, idx, smooth=True):
        self.f.append(tuple(idx))
        self.smooth.append(smooth)

    def oriented_face(self, idx, want, smooth=True):
        """Add a face, flipping it so its normal points along `want`."""
        a, b, c = (Vector(self.v[i]) for i in idx[:3])
        if (b - a).cross(c - a).dot(Vector(want)) < 0:
            idx = list(reversed(idx))
        self.face(idx, smooth)

    def merge(self, other):
        off = len(self.v)
        self.v += other.v
        self.uv += other.uv
        self.f += [tuple(i + off for i in f) for f in other.f]
        self.smooth += other.smooth

    def to_object(self, name, recalc=False):
        me = bpy.data.meshes.new(name)
        me.from_pydata(self.v, [], self.f)
        me.validate()
        uvl = me.uv_layers.new(name="UVMap")
        for poly, sm in zip(me.polygons, self.smooth):
            poly.use_smooth = sm
            for li in poly.loop_indices:
                uvl.data[li].uv = self.uv[me.loops[li].vertex_index]
        me.update()
        ob = bpy.data.objects.new(name, me)
        bpy.context.scene.collection.objects.link(ob)
        if recalc:
            recalc_normals(ob)
        return ob


def recalc_normals(ob):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(ob.data)
    bm.free()


def bake_modifiers(ob):
    """Apply the modifier stack without operators."""
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    old = ob.data
    ob.modifiers.clear()
    ob.data = me
    bpy.data.meshes.remove(old)


def bevel(ob, width, segments=2, angle=40):
    m = ob.modifiers.new("Bevel", "BEVEL")
    m.width = width
    m.segments = segments
    m.limit_method = "ANGLE"
    m.angle_limit = math.radians(angle)
    m.use_clamp_overlap = True
    bake_modifiers(ob)


def join(objects, name):
    """Merge several objects into one new mesh object."""
    bm = bmesh.new()
    for ob in objects:
        me = ob.data.copy()
        me.transform(ob.matrix_world)
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for ob in objects:
        bpy.data.objects.remove(ob)
    out = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(out)
    return out


def shade(ob, angle=35):
    for p in ob.data.polygons:
        p.use_smooth = True
    ob.data.set_sharp_from_angle(angle=math.radians(angle))


def smart_uv(ob, margin=0.01):
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    if not ob.data.uv_layers:
        ob.data.uv_layers.new(name="UVMap")
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=margin)
    bpy.ops.object.mode_set(mode="OBJECT")


def strip(mb, pts, width, want, taper=True):
    """Flat ribbon along a 3D polyline, facing `want`."""
    want = Vector(want)
    n = len(pts)
    L, R = [], []
    for k, p in enumerate(pts):
        a = pts[max(0, k - 1)]
        b = pts[min(n - 1, k + 1)]
        tan = (Vector(b) - Vector(a)).normalized()
        side = tan.cross(want).normalized()
        w = width * 0.5
        if taper:
            edge = min(k, n - 1 - k) / max(1, (n - 1) / 2)
            w *= 0.35 + 0.65 * min(1.0, edge * 2.5)
        L.append(mb.add(Vector(p) - side * w, (k / (n - 1), 0)))
        R.append(mb.add(Vector(p) + side * w, (k / (n - 1), 1)))
    for k in range(n - 1):
        mb.oriented_face([L[k], R[k], R[k + 1], L[k + 1]], want, smooth=False)


def tube(mb, pts, radius, sides=6, flatten=1.0, plane_normal=None, caps=True):
    """Tube along a polyline. radius(t) for t in 0..1. Optional flattening."""
    n = len(pts)
    pts = [Vector(p) for p in pts]
    rings = []
    prev_n = None
    for k, p in enumerate(pts):
        tan = (pts[min(n - 1, k + 1)] - pts[max(0, k - 1)]).normalized()
        if plane_normal is not None:
            b = Vector(plane_normal).normalized()
            nrm = tan.cross(b).normalized()
        else:
            if prev_n is None:
                ref = Vector((0, 0, 1)) if abs(tan.z) < 0.9 else Vector((1, 0, 0))
                nrm = tan.cross(ref).normalized()
            else:                      # parallel transport
                nrm = (prev_n - tan * prev_n.dot(tan)).normalized()
            prev_n = nrm
            b = tan.cross(nrm).normalized()
        r = radius(k / (n - 1))
        ring = []
        for j in range(sides):
            a = 2 * math.pi * j / sides
            ring.append(mb.add(p + nrm * (r * math.cos(a)) + b * (r * flatten * math.sin(a)),
                               (j / sides, k / (n - 1))))
        rings.append(ring)
    for k in range(n - 1):
        for j in range(sides):
            j1 = (j + 1) % sides
            mb.face([rings[k][j], rings[k][j1], rings[k + 1][j1], rings[k + 1][j]])
    if caps:
        for ring, p in ((rings[0], pts[0]), (rings[-1], pts[-1])):
            c = mb.add(p)
            for j in range(sides):
                mb.face([ring[j], ring[(j + 1) % sides], c])


def lathe(mb, profile, segments=16, cap_top=True, cap_bottom=True):
    """Revolve [(radius, z)] around the Z axis."""
    rings = []
    for k, (r, z) in enumerate(profile):
        ring = []
        for j in range(segments):
            a = 2 * math.pi * j / segments
            ring.append(mb.add((r * math.cos(a), r * math.sin(a), z), (j / segments, k / len(profile))))
        rings.append(ring)
    for k in range(len(rings) - 1):
        for j in range(segments):
            j1 = (j + 1) % segments
            mb.face([rings[k][j], rings[k][j1], rings[k + 1][j1], rings[k + 1][j]])
    for ring, z, use in ((rings[0], profile[0][1], cap_top), (rings[-1], profile[-1][1], cap_bottom)):
        if use:
            c = mb.add((0, 0, z))
            for j in range(segments):
                mb.face([ring[j], ring[(j + 1) % segments], c])


def slab(outline, ht, name, bevel_width=0.0):
    """Extrude a CCW (seen from the front) outline both ways; ht(x, z) = half thickness."""
    mb = MB()
    front = [mb.add((x, -ht(x, z), z)) for x, z in outline]
    back = [mb.add((x, ht(x, z), z)) for x, z in outline]
    n = len(outline)
    mb.face(front, smooth=False)
    mb.face(list(reversed(back)), smooth=False)
    for k in range(n):
        k1 = (k + 1) % n
        mb.face([front[k], back[k], back[k1], front[k1]], smooth=False)
    ob = mb.to_object(name, recalc=True)
    if bevel_width:
        bevel(ob, bevel_width)
    return ob


def mirror_x(pts):
    return [(-x, z) for x, z in pts]


def point_in_poly(x, z, poly):
    inside = False
    n = len(poly)
    for i in range(n):
        x1, z1 = poly[i]
        x2, z2 = poly[(i + 1) % n]
        if (z1 > z) != (z2 > z) and x < (x2 - x1) * (z - z1) / (z2 - z1) + x1:
            inside = not inside
    return inside


# ---------------------------------------------------------------- blade


def build_blade_crystal():
    """Full blade silhouette: glowing crystal with sharp edges (Neon in Roblox)."""
    mb = MB()
    N = 46
    S = [math.sin(math.pi / 2 * i / N) for i in range(N + 1)]
    T = [-1, -0.9, -0.76, -0.58, -0.32, 0, 0.32, 0.58, 0.76, 0.9, 1]
    front, back = [], []
    for i in range(N):
        s = S[i]
        z, w = BZ0 + s * BL, hw(s)
        fr, bk = [], []
        for j, t in enumerate(T):
            h = crystal_ht(t, s)
            uv = ((t + 1) / 2, s)
            fr.append(mb.add((t * w, -h, z), uv))
            bk.append(fr[-1] if j in (0, len(T) - 1) else mb.add((t * w, h, z), uv))
        front.append(fr)
        back.append(bk)
    tip = mb.add((0, 0, BZ1), (0.5, 1))
    for i in range(N - 1):
        for j in range(len(T) - 1):
            mb.face([front[i][j], front[i][j + 1], front[i + 1][j + 1], front[i + 1][j]])
            mb.face([back[i][j + 1], back[i][j], back[i + 1][j], back[i + 1][j + 1]])
    for j in range(len(T) - 1):
        mb.face([front[N - 1][j], front[N - 1][j + 1], tip])
        mb.face([back[N - 1][j + 1], back[N - 1][j], tip])
    mb.face(front[0] + list(reversed(back[0][1:-1])), smooth=False)
    ob = mb.to_object("BladeEdge", recalc=True)
    shade(ob, 50)
    return ob


def build_blade_core():
    """Broken stone slab set into the crystal (textured)."""
    mb = MB()
    U = [-1, -0.86, -0.7, -0.55, -0.38, -0.19, 0, 0.19, 0.38, 0.55, 0.7, 0.86, 1]
    M = 34
    front, back = [], []
    for j, u in enumerate(U):
        se = core_end(u)
        fr, bk = [], []
        for i in range(M + 1):
            s = se * i / M
            pf = core_point(u, s, -1)
            uv = (0.5 + pf.x / 0.7, s)
            fr.append(mb.add(pf, uv))
            if j in (0, len(U) - 1) or i == M:
                bk.append(fr[-1])
            else:
                bk.append(mb.add(core_point(u, s, 1), uv))
        front.append(fr)
        back.append(bk)
    for j in range(len(U) - 1):
        for i in range(M):
            mb.face([front[j][i], front[j + 1][i], front[j + 1][i + 1], front[j][i + 1]])
            mb.face([back[j + 1][i], back[j][i], back[j][i + 1], back[j + 1][i + 1]])
    mb.face([front[j][0] for j in range(len(U))] + [back[j][0] for j in range(len(U) - 2, 0, -1)], smooth=False)
    ob = mb.to_object("BladeCore", recalc=True)
    shade(ob, 60)
    return ob


def rune_paths():
    paths = []
    for side in (-1, 1):
        edge = [(side * 0.80, 0.04 + 0.80 * k / 23) for k in range(24)]
        vee = [(side * 0.80 * (1 - k / 7), 0.84 + 0.125 * k / 7) for k in range(1, 8)]
        paths.append(edge + vee)
        for s in (0.22, 0.40, 0.58):
            paths.append([(side * 0.68, s - 0.03), (side * 0.89, s), (side * 0.68, s + 0.03)])
        paths.append([(side * 0.86, 0.06 + 0.03 * k) for k in range(5)])   # ladder near the guard
    paths.append([(0.0, 0.82 + 0.135 * k / 5) for k in range(6)])         # tip centre line
    return paths


def build_blade_runes():
    """Pale engraved lines on the crystal edges (bright Neon in Roblox)."""
    mb = MB()
    for path in rune_paths():
        for face in (-1, 1):
            pts = []
            for t, s in path:
                pts.append((t * hw(s), face * (crystal_ht(t, s) + 0.0035), BZ0 + s * BL))
            strip(mb, pts, 0.011, (0, face, 0), taper=len(path) > 3)
    return mb.to_object("BladeRunes")


# ---------------------------------------------------------------- guard

GUARD_RIGHT = [
    (0.000, -0.030), (0.085, 0.035), (0.150, 0.070), (0.290, 0.085), (0.420, 0.070),
    (0.520, 0.030), (0.600, -0.040), (0.640, -0.095), (0.635, -0.020), (0.605, 0.070),
    (0.560, 0.140), (0.460, 0.200), (0.360, 0.225), (0.300, 0.265), (0.320, 0.360),
    (0.375, 0.440), (0.315, 0.470), (0.300, 0.580), (0.270, 0.700), (0.215, 0.880),
    (0.195, 0.700), (0.165, 0.560), (0.110, 0.520), (0.075, 0.640), (0.040, 0.820),
    (0.000, 1.000),
]
GUARD_OUTLINE = GUARD_RIGHT + mirror_x(list(reversed(GUARD_RIGHT[1:-1])))

ARM_PLATE = [(0.12, 0.08), (0.29, 0.10), (0.42, 0.085), (0.50, 0.07), (0.555, 0.10),
             (0.53, 0.14), (0.45, 0.175), (0.35, 0.195), (0.22, 0.20), (0.14, 0.17)]
WING_PLATE = [(0.215, 0.29), (0.285, 0.30), (0.29, 0.42), (0.28, 0.56), (0.25, 0.68),
              (0.215, 0.80), (0.20, 0.66), (0.185, 0.52), (0.19, 0.38)]
MEDALLION = [(0.0, -0.03), (0.135, 0.11), (0.0, 0.27), (-0.135, 0.11)]
MEDALLION_INNER = [(0.0, 0.0), (0.095, 0.11), (0.0, 0.22), (-0.095, 0.11)]
SPIKE_RIDGE = [(0.0, 0.30), (0.05, 0.45), (0.06, 0.62), (0.035, 0.80), (0.0, 0.95),
               (-0.035, 0.80), (-0.06, 0.62), (-0.05, 0.45)]

PLATES = [  # (outline, extra half thickness, bevel)
    (ARM_PLATE, 0.012, 0.005), (mirror_x(list(reversed(ARM_PLATE))), 0.012, 0.005),
    (WING_PLATE, 0.010, 0.005), (mirror_x(list(reversed(WING_PLATE))), 0.010, 0.005),
    (SPIKE_RIDGE, 0.009, 0.004), (MEDALLION, 0.022, 0.006), (MEDALLION_INNER, 0.032, 0.005),
]


def guard_ht(x, z):
    return 0.042 * (1 - 0.45 * min(1.0, abs(x) / 0.64)) * (1 - 0.35 * max(0.0, (z - 0.3) / 0.7))


def guard_surface(x, z):
    extra = 0.0
    for outline, e, _ in PLATES:
        if point_in_poly(x, z, outline):
            extra = max(extra, e)
    return guard_ht(x, z) + extra


def spiral_pts(cx, cz, r0, r1, turns, phase, face, lift, mirror=1, steps=24):
    pts = []
    for k in range(steps):
        t = k / (steps - 1)
        a = phase + mirror * t * turns * 2 * math.pi
        r = r0 + (r1 - r0) * t
        x, z = cx + r * math.cos(a), cz + r * math.sin(a)
        pts.append((x, face * (guard_surface(x, z) + lift), z))
    return pts


def build_guard_parts():
    objs = [slab(GUARD_OUTLINE, guard_ht, "GuardBase", 0.010)]
    for i, (outline, extra, bw) in enumerate(PLATES):
        objs.append(slab(outline, lambda x, z, e=extra: guard_ht(x, z) + e, f"GuardPlate{i}", bw))
    deco = MB()
    for face in (-1, 1):
        for mx in (1, -1):
            for cx, cz, r1, turns in ((0.26, 0.14, 0.040, 1.5), (0.43, 0.125, 0.036, 1.4), (0.243, 0.43, 0.028, 1.3)):
                pts = spiral_pts(mx * cx, cz, 0.006, r1, turns, 0.4, face, 0.006, mirror=mx)
                tube(deco, pts, lambda t: 0.0075 - 0.0035 * (1 - t), sides=5)
            ico = bmesh.new()
            bmesh.ops.create_icosphere(ico, subdivisions=1, radius=0.02)
            sx, sz = mx * 0.505, 0.11
            sy = face * (guard_surface(sx, sz) + 0.008)
            me = bpy.data.meshes.new("stud")
            ico.to_mesh(me)
            ico.free()
            stud = MB()
            for v in me.vertices:
                stud.add((v.co.x + sx, v.co.y + sy, v.co.z + sz))
            for p in me.polygons:
                stud.face(list(p.vertices))
            bpy.data.meshes.remove(me)
            deco.merge(stud)
    for mx in (1, -1):
        pts = []
        for k in range(28):
            t = k / 27
            a = math.radians(200) - mx * 0 + (-1 if mx > 0 else 1) * t * 1.3 * 2 * math.pi
            r = 0.052 - 0.040 * t
            pts.append((mx * 0.585 + r * math.cos(a) * mx, 0.0, 0.055 + r * math.sin(a)))
        tube(deco, pts, lambda t: 0.017 - 0.010 * t, sides=7)
    objs.append(deco.to_object("GuardDeco"))
    return objs


def build_crystals():
    """Guard crystal + glowing cracks on the blade core and guard (Neon in Roblox)."""
    mb = MB()
    # guard crystal: hexagonal prism with pointed ends, piercing the guard
    rings = []
    for z, r in ((0.355, 1.0), (0.585, 1.0)):
        ring = [mb.add((0.062 * r * math.cos(a), 0.086 * r * math.sin(a), z))
                for a in (k * math.pi / 3 for k in range(6))]
        rings.append(ring)
    top, bot = mb.add((0, 0, 0.70)), mb.add((0, 0, 0.255))
    for j in range(6):
        j1 = (j + 1) % 6
        mb.face([rings[0][j], rings[0][j1], rings[1][j1], rings[1][j]], smooth=False)
        mb.face([rings[1][j], rings[1][j1], top], smooth=False)
        mb.face([rings[0][j1], rings[0][j], bot], smooth=False)
    # main crack down the stone core, plus branches
    for face in (-1, 1):
        main = []
        for k in range(30):
            s = 0.03 + 0.70 * k / 29
            u = 0.07 * nz(s * 11.0, 4.2) + 0.03 * math.sin(s * 70)
            main.append(core_point(u, s, face, 0.007))
        strip(mb, main, 0.017, (0, face, 0))
        for s0, du in ((0.17, 0.55), (0.30, -0.5), (0.43, 0.6), (0.56, -0.55), (0.66, 0.45)):
            br = []
            for k in range(7):
                t = k / 6
                br.append(core_point(du * t + 0.02 * nz(t * 5, s0 * 9), s0 + 0.05 * t, face, 0.007))
            strip(mb, br, 0.011, (0, face, 0))
        # veins on the guard spike and wings
        for path in ([(0.0, 0.70), (0.012, 0.78), (-0.006, 0.86), (0.004, 0.93)],
                     [(0.03, 0.47), (0.10, 0.53), (0.15, 0.60), (0.20, 0.70)],
                     [(-0.03, 0.47), (-0.10, 0.53), (-0.15, 0.60), (-0.20, 0.70)]):
            pts = [(x, face * (guard_surface(x, z) + 0.005), z) for x, z in path]
            strip(mb, pts, 0.012, (0, face, 0))
    return mb.to_object("EnergyVeins")


# ---------------------------------------------------------------- hilt


GRIP_TOP, GRIP_BOTTOM = -0.26, -0.86
GEM_Z = -1.10


def build_hilt_metal():
    mb = MB()
    lathe(mb, [(0.11, 0.035), (0.165, 0.0), (0.15, -0.025), (0.105, -0.045), (0.095, -0.075),
               (0.11, -0.09), (0.115, -0.11), (0.098, -0.125), (0.092, -0.135), (0.092, -0.20),
               (0.104, -0.21), (0.108, -0.235), (0.098, -0.255), (0.085, -0.27)])
    lathe(mb, [(0.085, -0.845), (0.098, -0.86), (0.106, -0.88), (0.096, -0.895), (0.094, -0.94),
               (0.108, -0.955), (0.118, -0.975), (0.112, -0.995), (0.09, -1.01), (0.06, -1.02)])
    for k in range(4):           # prongs holding the pommel gem
        a = math.pi / 4 + k * math.pi / 2
        prof = [(0.100, -1.00), (0.106, -1.05), (0.104, -1.10), (0.094, -1.15), (0.078, -1.185), (0.058, -1.205)]
        pts = [(r * math.cos(a), r * math.sin(a), z) for r, z in prof]
        tube(mb, pts, lambda t: 0.014 - 0.005 * t, sides=6)
    lathe(mb, [(0.055, -1.195), (0.076, -1.205), (0.072, -1.225), (0.047, -1.245), (0.03, -1.255)])
    # curled horn finial (ref: the hooked tip above the gem)
    finial = [(0, 0, -1.245), (0, 0, -1.30), (0.012, 0, -1.355), (0.04, 0, -1.40),
              (0.08, 0, -1.425), (0.115, 0, -1.41), (0.135, 0, -1.375)]
    smooth_pts = []
    for k in range(len(finial) - 1):
        a, b = Vector(finial[k]), Vector(finial[k + 1])
        for j in range(3):
            smooth_pts.append(a.lerp(b, j / 3))
    smooth_pts.append(Vector(finial[-1]))
    tube(mb, smooth_pts, lambda t: 0.042 * (1 - t) ** 0.85 + 0.003, sides=8, flatten=0.6,
         plane_normal=(0, 1, 0))
    ob = mb.to_object("HiltLathe", recalc=True)
    return ob


def build_handle():
    """The grip (becomes the Tool's Handle in Roblox)."""
    mb = MB()
    rings, sides = 14, 16
    grid = []
    for i in range(rings + 1):
        v = i / rings
        z = GRIP_BOTTOM + (GRIP_TOP - GRIP_BOTTOM) * v
        r = 0.078 * (1 + 0.06 * math.sin(math.pi * v))
        row = []
        for j in range(sides + 1):
            a = 2 * math.pi * j / sides
            row.append(mb.add((r * math.cos(a), r * math.sin(a), z), (j / sides, v)))
        grid.append(row)
    for i in range(rings):
        for j in range(sides):
            mb.face([grid[i][j], grid[i][j + 1], grid[i + 1][j + 1], grid[i + 1][j]])
    ob = mb.to_object("Handle", recalc=True)
    shade(ob, 80)
    return ob


def dome(mb, cx, cz, rx, rz, height, face, teardrop=0.0, sides=10):
    """Cabochon gem sitting on the guard face; teardrop > 0 stretches it toward +z."""
    base_y = face * guard_surface(cx, cz)
    ring, mid = [], []
    for k in range(sides):
        a = 2 * math.pi * k / sides
        stretch = 1 + teardrop * max(0.0, math.sin(a)) ** 3
        x, z = cx + rx * math.cos(a), cz + rz * math.sin(a) * stretch
        ring.append(mb.add((x, base_y, z)))
        mid.append(mb.add((cx + 0.62 * (x - cx), base_y + face * height * 0.75, cz + 0.62 * (z - cz))))
    apex = mb.add((cx, base_y + face * height, cz + rz * teardrop * 0.15))
    for k in range(sides):
        k1 = (k + 1) % sides
        mb.oriented_face([ring[k], ring[k1], mid[k1], mid[k]], (0, face, 0), smooth=False)
        mb.oriented_face([mid[k], mid[k1], apex], (0, face, 0), smooth=False)


def build_accent_gems():
    mb = MB()
    for face in (-1, 1):
        dome(mb, 0.0, 0.11, 0.042, 0.042, 0.03, face)
        for mx in (1, -1):
            dome(mb, mx * 0.175, 0.125, 0.020, 0.024, 0.022, face, teardrop=0.9, sides=8)
    n = 8
    gird = [mb.add((0.072 * math.cos(a), 0.072 * math.sin(a), GEM_Z))
            for a in (2 * math.pi * k / n for k in range(n))]
    crown = [mb.add((0.046 * math.cos(a), 0.046 * math.sin(a), GEM_Z + 0.045))
             for a in (2 * math.pi * (k + 0.5) / n for k in range(n))]
    top, bot = mb.add((0, 0, GEM_Z + 0.105)), mb.add((0, 0, GEM_Z - 0.11))
    for k in range(n):
        k1 = (k + 1) % n
        mb.face([gird[k], gird[k1], crown[k]], smooth=False)
        mb.face([crown[k], gird[k1], crown[k1]], smooth=False)
        mb.face([crown[k], crown[k1], top], smooth=False)
        mb.face([gird[k1], gird[k], bot], smooth=False)
    return mb.to_object("AccentGems")


def build_aura():
    """Hull around the blade for the ForceField energy shimmer."""
    mb = MB()
    z0, z1 = 0.62, BZ1 + 0.10
    rows, sides = 26, 10
    grid = []
    for i in range(rows):
        f = math.sin(math.pi / 2 * i / rows)
        z = z0 + (z1 - z0) * f
        s = min(1.0, (z - BZ0) / BL)
        w = hw(s) * 1.10 + 0.04 * (1 - f ** 4)
        th = 0.078 * (1 - 0.4 * s) * (1 - f ** 6) + 0.01
        row = []
        for j in range(sides + 1):
            a = 2 * math.pi * j / sides
            row.append(mb.add((w * math.cos(a), th * math.sin(a), z), (j / sides, f * 3.0)))
        grid.append(row)
    tip = mb.add((0, 0, z1), (0.5, 3.0))
    for i in range(rows - 1):
        for j in range(sides):
            mb.face([grid[i][j], grid[i][j + 1], grid[i + 1][j + 1], grid[i + 1][j]])
    for j in range(sides):
        mb.face([grid[-1][j], grid[-1][j + 1], tip])
    ob = mb.to_object("BladeAura", recalc=True)
    return ob


# ---------------------------------------------------------------- VFX meshes


def arc_mesh(name, width_fn, r_out=1.0, z=0.0, segs=48, rows=4, span=210):
    mb = MB()
    grid = []
    for i in range(segs + 1):
        f = i / segs
        th = math.radians(-span / 2 + span * f)
        w = width_fn(f)
        row = []
        for k in range(rows):
            v = k / (rows - 1)
            r = r_out - w * (1 - v)
            row.append(mb.add((r * math.sin(th), r * math.cos(th), z), (f, v)))
        grid.append(row)
    for i in range(segs):
        for k in range(rows - 1):
            q = [grid[i][k], grid[i + 1][k], grid[i + 1][k + 1], grid[i][k + 1]]
            mb.oriented_face(q, (0, 0, 1), smooth=False)
            mb.oriented_face(q, (0, 0, -1), smooth=False)     # double sided
    return mb.to_object(name)


def ring_mesh(name, r_in, r_out, z=0.0, segs=64, tile=4):
    mb = MB()
    inner, outer = [], []
    for j in range(segs + 1):
        a = 2 * math.pi * j / segs
        inner.append(mb.add((r_in * math.cos(a), r_in * math.sin(a), z), (tile * j / segs, 0)))
        outer.append(mb.add((r_out * math.cos(a), r_out * math.sin(a), z), (tile * j / segs, 1)))
    for j in range(segs):
        q = [inner[j], inner[j + 1], outer[j + 1], outer[j]]
        mb.oriented_face(q, (0, 0, 1), smooth=False)
        mb.oriented_face(q, (0, 0, -1), smooth=False)
    return mb.to_object(name)


def shard_mesh(name, length=0.24, radius=0.045, seed=0):
    mb = MB()
    rnd = np.random.default_rng(seed)
    ring = []
    for k in range(6):
        a = k * math.pi / 3 + rnd.uniform(-0.2, 0.2)
        r = radius * rnd.uniform(0.75, 1.15)
        ring.append(mb.add((r * math.cos(a), r * math.sin(a), rnd.uniform(-0.02, 0.02))))
    top = mb.add((rnd.uniform(-0.01, 0.01), 0, length * 0.6))
    bot = mb.add((0, rnd.uniform(-0.01, 0.01), -length * 0.4))
    for k in range(6):
        k1 = (k + 1) % 6
        mb.face([ring[k], ring[k1], top], smooth=False)
        mb.face([ring[k1], ring[k], bot], smooth=False)
    return mb.to_object(name, recalc=True)


def rock_mesh(name, seed, scale):
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=1, radius=1.0)
    for v in bm.verts:
        d = 1 + 0.28 * noise.noise(v.co * 1.7 + Vector((seed * 3.1, seed, 0)))
        v.co = Vector((v.co.x * scale[0], v.co.y * scale[1], v.co.z * scale[2])) * d
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    for p in me.polygons:
        p.use_smooth = False
    return ob


def marker(name, pos):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=0.05)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.transform(Matrix.Translation(pos))
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


# ---------------------------------------------------------------- materials & baking


def nodes_of(mat):
    mat.use_nodes = True
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    return nt


def sock(node, ident, out=False):
    for s in (node.outputs if out else node.inputs):
        if s.identifier == ident or s.name == ident:
            return s
    raise KeyError(ident)


def mix(nt, fac, a, b, blend="MIX"):
    m = nt.nodes.new("ShaderNodeMix")
    m.data_type = "RGBA"
    m.blend_type = blend
    for target, src in ((sock(m, "Factor_Float"), fac), (sock(m, "A_Color"), a), (sock(m, "B_Color"), b)):
        if isinstance(src, (int, float)):
            target.default_value = src
        elif isinstance(src, tuple):
            target.default_value = src if len(src) == 4 else (*src, 1.0)
        else:
            nt.links.new(src, target)
    return sock(m, "Result_Color", out=True)


def math_node(nt, op, a, b=None, clamp=False):
    m = nt.nodes.new("ShaderNodeMath")
    m.operation = op
    m.use_clamp = clamp
    for k, src in enumerate((a, b)):
        if src is None:
            continue
        if isinstance(src, (int, float)):
            m.inputs[k].default_value = src
        else:
            nt.links.new(src, m.inputs[k])
    return m.outputs[0]


def ramp(nt, src, stops):
    r = nt.nodes.new("ShaderNodeValToRGB")
    nt.links.new(src, r.inputs["Fac"])
    els = r.color_ramp.elements
    while len(els) < len(stops):
        els.new(0.5)
    for el, (pos, col) in zip(els, stops):
        el.position = pos
        el.color = (*col, 1.0) if len(col) == 3 else col
    return r.outputs["Color"]


def coords(nt, kind="Object", scale=(1, 1, 1)):
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = scale
    nt.links.new(tc.outputs[kind], mp.inputs["Vector"])
    return mp.outputs["Vector"]


def ao(nt, distance, samples=16):
    n = nt.nodes.new("ShaderNodeAmbientOcclusion")
    n.samples = samples
    n.inputs["Distance"].default_value = distance
    return n.outputs["AO"]


def emit_out(nt, color):
    e = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(color, e.inputs["Color"])
    o = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(e.outputs[0], o.inputs["Surface"])


def stone_bake_material():
    mat = bpy.data.materials.new("Bake_Stone")
    nt = nodes_of(mat)
    co = coords(nt, "Object", (1.0, 1.0, 0.35))       # long fractures down the blade
    warp = nt.nodes.new("ShaderNodeTexNoise")
    warp.inputs["Scale"].default_value = 9.0
    warp.inputs["Detail"].default_value = 4.0
    nt.links.new(co, warp.inputs["Vector"])
    warped = nt.nodes.new("ShaderNodeVectorMath")
    warped.operation = "MULTIPLY_ADD"
    nt.links.new(warp.outputs["Color"], warped.inputs[0])
    warped.inputs[1].default_value = (0.12, 0.12, 0.12)
    nt.links.new(co, warped.inputs[2])
    vor = nt.nodes.new("ShaderNodeTexVoronoi")
    vor.feature = "DISTANCE_TO_EDGE"
    vor.inputs["Scale"].default_value = 7.0
    nt.links.new(warped.outputs[0], vor.inputs["Vector"])
    crack_mask = ramp(nt, vor.outputs["Distance"], [(0.0, (0, 0, 0)), (0.03, (1, 1, 1))])
    rim = ramp(nt, vor.outputs["Distance"], [(0.025, (0, 0, 0)), (0.045, (1, 1, 1)), (0.09, (0, 0, 0))])
    nz1 = nt.nodes.new("ShaderNodeTexNoise")
    nz1.inputs["Scale"].default_value = 16.0
    nz1.inputs["Detail"].default_value = 8.0
    nz1.inputs["Roughness"].default_value = 0.62
    nt.links.new(coords(nt, "Object"), nz1.inputs["Vector"])
    stone = ramp(nt, nz1.outputs["Fac"], [(0.3, (0.010, 0.010, 0.016)), (0.5, (0.035, 0.032, 0.048)),
                                          (0.7, (0.075, 0.068, 0.095))])
    nz2 = nt.nodes.new("ShaderNodeTexNoise")
    nz2.inputs["Scale"].default_value = 3.0
    nt.links.new(coords(nt, "Object"), nz2.inputs["Vector"])
    tint = ramp(nt, nz2.outputs["Fac"], [(0.35, (0.8, 0.85, 1.0)), (0.65, (1.05, 0.95, 1.1))])
    col = mix(nt, 1.0, stone, tint, "MULTIPLY")
    col = mix(nt, 0.12, col, rim, "ADD")
    col = mix(nt, crack_mask, (0.004, 0.004, 0.006), col)
    occl = ao(nt, 0.04)
    col = mix(nt, 1.0, col, ramp(nt, occl, [(0.0, (0.3, 0.3, 0.3)), (1.0, (1, 1, 1))]), "MULTIPLY")
    emit_out(nt, col)
    return mat


def metal_bake_material(gold=False):
    mat = bpy.data.materials.new("Bake_Metal_Gold" if gold else "Bake_Metal_Silver")
    nt = nodes_of(mat)
    if gold:
        base, mid, edge, line = (0.10, 0.055, 0.012), (0.36, 0.20, 0.045), (1.0, 0.72, 0.30), (0.04, 0.02, 0.005)
    else:
        base, mid, edge, line = (0.016, 0.017, 0.021), (0.075, 0.078, 0.09), (0.55, 0.58, 0.66), (0.006, 0.006, 0.008)
    grain = nt.nodes.new("ShaderNodeTexNoise")
    grain.inputs["Scale"].default_value = 45.0
    grain.inputs["Detail"].default_value = 6.0
    nt.links.new(coords(nt, "Object"), grain.inputs["Vector"])
    col = mix(nt, grain.outputs["Fac"], base, mid)
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    edges = ramp(nt, geo.outputs["Pointiness"], [(0.52, (0, 0, 0)), (0.58, (1, 1, 1))])
    col = mix(nt, edges, col, edge)
    # engraved scrollwork on the faces that look forward/back
    vor = nt.nodes.new("ShaderNodeTexVoronoi")
    vor.feature = "DISTANCE_TO_EDGE"
    vor.inputs["Scale"].default_value = 26.0
    warp = nt.nodes.new("ShaderNodeTexNoise")
    warp.inputs["Scale"].default_value = 6.0
    nt.links.new(coords(nt, "Object"), warp.inputs["Vector"])
    warped = nt.nodes.new("ShaderNodeVectorMath")
    warped.operation = "ADD"
    nt.links.new(coords(nt, "Object"), warped.inputs[0])
    nt.links.new(warp.outputs["Color"], warped.inputs[1])
    nt.links.new(warped.outputs[0], vor.inputs["Vector"])
    lines = ramp(nt, vor.outputs["Distance"], [(0.0, (0.55, 0.55, 0.55)), (0.04, (0, 0, 0))])
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(geo.outputs["Normal"], sep.inputs["Vector"])
    facing = math_node(nt, "ABSOLUTE", sep.outputs["Y"])
    facing = ramp(nt, facing, [(0.6, (0, 0, 0)), (0.85, (1, 1, 1))])
    engrave = mix(nt, 1.0, lines, facing, "MULTIPLY")
    col = mix(nt, engrave, col, line)
    occl = ao(nt, 0.03)
    col = mix(nt, 1.0, col, ramp(nt, occl, [(0.0, (0.15, 0.15, 0.15)), (1.0, (1, 1, 1))]), "MULTIPLY")
    emit_out(nt, col)
    return mat


def wrap_bake_material():
    mat = bpy.data.materials.new("Bake_Wrap")
    nt = nodes_of(mat)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["UV"], sep.inputs["Vector"])
    diag = math_node(nt, "ADD", math_node(nt, "MULTIPLY", sep.outputs["X"], 4.0),
                     math_node(nt, "MULTIPLY", sep.outputs["Y"], 9.0))
    f = math_node(nt, "FRACT", diag)
    strap = ramp(nt, f, [(0.06, (0, 0, 0)), (0.12, (1, 1, 1)), (0.86, (1, 1, 1)), (0.94, (0, 0, 0))])
    shade_band = ramp(nt, f, [(0.1, (0.55, 0.55, 0.55)), (0.5, (1, 1, 1)), (0.9, (0.6, 0.6, 0.6))])
    grain = nt.nodes.new("ShaderNodeTexNoise")
    grain.inputs["Scale"].default_value = 60.0
    nt.links.new(tc.outputs["Object"], grain.inputs["Vector"])
    leather = ramp(nt, grain.outputs["Fac"], [(0.3, (0.010, 0.010, 0.014)), (0.7, (0.03, 0.028, 0.036))])
    leather = mix(nt, 1.0, leather, shade_band, "MULTIPLY")
    metal = (0.05, 0.052, 0.06)
    emit_out(nt, mix(nt, strap, metal, leather))
    return mat


def bake(ob, bake_mat, size, path):
    img = bpy.data.images.new(os.path.splitext(os.path.basename(path))[0], size, size, alpha=False)
    old = list(ob.data.materials)
    ob.data.materials.clear()
    ob.data.materials.append(bake_mat)
    nt = bake_mat.node_tree
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    nt.nodes.active = tex
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    bpy.ops.object.bake(type="EMIT", margin=6, use_clear=True)
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    nt.nodes.remove(tex)
    ob.data.materials.clear()
    for m in old:
        ob.data.materials.append(m)
    return img


def np_image(name, arr, path):
    h, w = arr.shape[:2]
    img = bpy.data.images.new(name, w, h, alpha=True)
    img.pixels.foreach_set(np.flipud(arr).astype(np.float32).ravel())
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    return img


def pbr_material(name, image=None, color=(1, 1, 1), metallic=0.0, rough=0.5,
                 emission=None, strength=0.0, alpha_from_image=False):
    """Principled material that exports cleanly to glTF/FBX and renders in Cycles."""
    mat = bpy.data.materials.new(name)
    nt = nodes_of(mat)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(bsdf.outputs[0], out.inputs["Surface"])
    bsdf.inputs["Base Color"].default_value = (*color, 1)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = rough
    if image is not None:
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = image
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        if alpha_from_image:
            nt.links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
            if hasattr(mat, "blend_method"):
                mat.blend_method = "BLEND"
        if emission == "image":
            nt.links.new(tex.outputs["Color"], bsdf.inputs["Emission Color"])
    if isinstance(emission, tuple):
        bsdf.inputs["Emission Color"].default_value = (*emission, 1)
    bsdf.inputs["Emission Strength"].default_value = strength
    return mat


def glow_render_material(name, image, color, strength=3.0, opacity=0.9):
    """See-through additive glow (render only): brightness of `image` drives both."""
    mat = bpy.data.materials.new(name)
    nt = nodes_of(mat)
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = image
    bw = nt.nodes.new("ShaderNodeRGBToBW")
    nt.links.new(tex.outputs["Color"], bw.inputs[0])
    level = math_node(nt, "POWER", bw.outputs[0], 0.4545)    # back to the PNG's own grey levels
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*color, 1)
    nt.links.new(math_node(nt, "MULTIPLY", level, strength), em.inputs["Strength"])
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mx = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(math_node(nt, "MULTIPLY", level, opacity, clamp=True), mx.inputs[0])
    nt.links.new(tr.outputs[0], mx.inputs[1])
    nt.links.new(em.outputs[0], mx.inputs[2])
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(mx.outputs[0], out.inputs["Surface"])
    return mat


def aura_render_material(name, image, color):
    mat = bpy.data.materials.new(name)
    nt = nodes_of(mat)
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = image
    bw = nt.nodes.new("ShaderNodeRGBToBW")
    nt.links.new(tex.outputs["Color"], bw.inputs[0])
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*color, 1)
    nt.links.new(math_node(nt, "MULTIPLY", bw.outputs[0], 2.5), em.inputs["Strength"])
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mx = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(math_node(nt, "MULTIPLY", bw.outputs[0], 0.45, clamp=True), mx.inputs[0])
    nt.links.new(tr.outputs[0], mx.inputs[1])
    nt.links.new(em.outputs[0], mx.inputs[2])
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(mx.outputs[0], out.inputs["Surface"])
    return mat


def set_material(ob, mat):
    ob.data.materials.clear()
    ob.data.materials.append(mat)


# ---------------------------------------------------------------- build everything


def clean_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = 24
    sc.unit_settings.system = "NONE"


def tri_count(ob):
    return sum(len(p.vertices) - 2 for p in ob.data.polygons)


def build_sword():
    edge = build_blade_crystal()
    core = build_blade_core()
    runes = build_blade_runes()
    veins = build_crystals()
    guard = build_guard_parts()
    lathe_ob = build_hilt_metal()
    hilt = join(guard + [lathe_ob], "Hilt")
    shade(hilt, 40)
    handle = build_handle()
    gem = build_accent_gems()
    aura = build_aura()
    return {"Handle": handle, "Hilt": hilt, "BladeCore": core, "BladeEdge": edge,
            "BladeRunes": runes, "EnergyVeins": veins, "AccentGems": gem, "BladeAura": aura}


def texture_sword(parts):
    os.makedirs(TEXTURES, exist_ok=True)
    smart_uv(parts["Hilt"], 0.006)
    smart_uv(parts["BladeCore"], 0.01)
    imgs = {
        "core": bake(parts["BladeCore"], stone_bake_material(), 1024, os.path.join(TEXTURES, "blade_core.png")),
        "silver": bake(parts["Hilt"], metal_bake_material(False), 1024, os.path.join(TEXTURES, "hilt_silver.png")),
        "gold": bake(parts["Hilt"], metal_bake_material(True), 1024, os.path.join(TEXTURES, "hilt_gold.png")),
        "wrap": bake(parts["Handle"], wrap_bake_material(), 512, os.path.join(TEXTURES, "handle_wrap.png")),
        "aura": np_image("aura_flow", vt.aura_flow(), os.path.join(TEXTURES, "aura_flow.png")),
    }
    return imgs


def theme_materials(imgs, theme, for_render=False):
    t = THEMES[theme]
    hilt_img = imgs[t["hilt"]]
    mats = {
        "Handle": pbr_material("Wrap", imgs["wrap"], rough=0.7),
        "Hilt": pbr_material(f"Hilt_{theme}", hilt_img, metallic=0.8, rough=0.33),
        "BladeCore": pbr_material("BladeStone", imgs["core"], rough=0.8),
        "BladeEdge": pbr_material(f"Crystal_{theme}", color=t["edge"], emission=t["edge"], strength=1.5),
        "BladeRunes": pbr_material(f"Runes_{theme}", color=t["rune"], emission=t["rune"], strength=4.0),
        "EnergyVeins": pbr_material(f"Veins_{theme}", color=t["vein"], emission=t["vein"], strength=4.5),
        "AccentGems": pbr_material(f"Gem_{theme}", color=t["gem"], emission=t["gem"], strength=1.8),
        "BladeAura": pbr_material(f"Aura_{theme}", imgs["aura"], color=t["aura"]),
    }
    if for_render:
        mats["BladeAura"] = aura_render_material(f"AuraFX_{theme}", imgs["aura"], t["aura"])
    return mats


def build_vfx(imgs):
    vfx = {}
    vfx["SlashArc"] = arc_mesh("SlashArc", lambda f: 0.32 * math.sin(math.pi * f) ** 0.8 * (0.45 + 0.55 * f))
    vfx["SlashCore"] = arc_mesh("SlashCore", lambda f: 0.07 * math.sin(math.pi * f) ** 0.9 * (0.5 + 0.5 * f),
                                z=0.003, rows=2)
    vfx["ShockRing"] = ring_mesh("ShockRing", 0.78, 1.0)
    vfx["RingCore"] = ring_mesh("RingCore", 0.965, 1.0, z=0.003, tile=1)
    for i in range(2):
        vfx[f"Shard{i + 1}"] = shard_mesh(f"Shard{i + 1}", seed=i)
    for i, sc in enumerate(((0.12, 0.09, 0.07), (0.09, 0.07, 0.06), (0.15, 0.08, 0.065))):
        r = rock_mesh(f"Rock{i + 1}", i + 1, sc)
        smart_uv(r, 0.02)
        vfx[f"Rock{i + 1}"] = r
    slash_img = np_image("slash_gradient", vt.slash_gradient(), os.path.join(TEXTURES, "slash_gradient.png"))
    ring_img = np_image("ring_gradient", vt.ring_gradient(), os.path.join(TEXTURES, "ring_gradient.png"))
    set_material(vfx["SlashArc"], pbr_material("SlashArc", slash_img, emission="image", strength=4.0))
    set_material(vfx["ShockRing"], pbr_material("ShockRing", ring_img, emission="image", strength=4.0))
    neon = pbr_material("VFXNeon", color=(0.7, 1, 1), emission=(0.7, 1, 1), strength=8.0)
    for k in ("SlashCore", "RingCore", "Shard1", "Shard2"):
        set_material(vfx[k], neon)
    stone = pbr_material("RockStone", imgs["core"], rough=0.85)
    for k in ("Rock1", "Rock2", "Rock3"):
        set_material(vfx[k], stone)
    # texture carriers: one tiny quad per particle texture, so the importer uploads them
    for i, (name, fn) in enumerate(vt.ALL_SPRITES.items()):
        img = np_image(f"vfx_{name.lower()}", fn(), os.path.join(TEXTURES, f"vfx_{name.lower()}.png"))
        mb = MB()
        x = 2.0 + 0.3 * i
        q = [mb.add((x, 0, 0), (0, 0)), mb.add((x + 0.2, 0, 0), (1, 0)),
             mb.add((x + 0.2, 0, 0.2), (1, 1)), mb.add((x, 0, 0.2), (0, 1))]
        mb.face(q, smooth=False)
        ob = mb.to_object(f"Tex_{name}")
        set_material(ob, pbr_material(f"Tex_{name}", img, alpha_from_image=True))
        vfx[f"Tex_{name}"] = ob
    mb = MB()
    q = [mb.add((5.6, 0, 0), (0, 0)), mb.add((5.8, 0, 0), (1, 0)), mb.add((5.8, 0, 0.2), (1, 1)), mb.add((5.6, 0, 0.2), (0, 1))]
    mb.face(q, smooth=False)
    gold_carrier = mb.to_object("Tex_HiltGold")
    set_material(gold_carrier, pbr_material("Tex_HiltGold", imgs["gold"]))
    vfx["Tex_HiltGold"] = gold_carrier
    return vfx


def bbox(ob):
    vs = [ob.matrix_world @ v.co for v in ob.data.vertices]
    lo = Vector((min(v.x for v in vs), min(v.y for v in vs), min(v.z for v in vs)))
    hi = Vector((max(v.x for v in vs), max(v.y for v in vs), max(v.z for v in vs)))
    return lo, hi


def export(objs, name):
    os.makedirs(EXPORT, exist_ok=True)
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.export_scene.gltf(filepath=os.path.join(EXPORT, name + ".glb"), export_format="GLB",
                              use_selection=True, export_apply=True, export_yup=True,
                              export_cameras=False, export_lights=False, export_extras=False)
    bpy.ops.export_scene.fbx(filepath=os.path.join(EXPORT, name + ".fbx"), use_selection=True,
                             object_types={"MESH"}, use_mesh_modifiers=True, mesh_smooth_type="FACE",
                             axis_forward="-Z", axis_up="Y", bake_space_transform=True,
                             apply_scale_options="FBX_SCALE_UNITS", path_mode="COPY", embed_textures=True)


def layout_json(parts, vfx):
    info = {"units": "studs", "axes": "blade +Z, width X, front -Y (Blender)", "parts": {}, "vfx": {},
            "points": {
                "BladeBase": [0, 0, 0.80], "BladeTip": [0, 0, BZ1 - 0.04], "BladeMid": [0, 0, 1.9],
                "FlowStart": [0, 0, 0.85], "FlowEnd": [0, 0, 3.05], "GuardCenter": [0, 0, 0.42],
                "Pommel": [0, 0, GEM_Z], "Grip": [0, 0, -0.47],
                "BladeHalfWidth": 0.285, "BladeHalfThickness": 0.06,
            }}
    for name, ob in list(parts.items()) + list(vfx.items()):
        lo, hi = bbox(ob)
        entry = {"verts": len(ob.data.vertices), "tris": tri_count(ob),
                 "bboxMin": [round(c, 4) for c in lo], "bboxMax": [round(c, 4) for c in hi]}
        (info["parts"] if name in parts else info["vfx"])[name] = entry
    lo, hi = bbox(vfx["SlashArc"])
    c = (lo + hi) / 2
    info["vfx"]["SlashArc"]["pivotFromCenter"] = [round(-c.x, 4), round(-c.y, 4), round(-c.z, 4)]
    lo, hi = bbox(vfx["SlashCore"])
    c = (lo + hi) / 2
    info["vfx"]["SlashCore"]["pivotFromCenter"] = [round(-c.x, 4), round(-c.y, 4), round(-c.z, 4)]
    with open(os.path.join(EXPORT, "sword_layout.json"), "w") as f:
        json.dump(info, f, indent=2)
    return info


# ---------------------------------------------------------------- preview renders


def bloom(path, strength=0.9, threshold=0.55):
    img = bpy.data.images.load(path, check_existing=False)
    w, h = img.size
    a = np.array(img.pixels[:], np.float32).reshape(h, w, 4)[..., :3]
    lum = a.max(axis=2, keepdims=True)
    bright = a * np.clip((lum - threshold) / (1 - threshold), 0, 1)
    glow = np.zeros_like(a)
    for sigma, wgt in ((4, 0.5), (14, 0.35), (40, 0.25)):
        for c in range(3):
            glow[..., c] += vt._blur(bright[..., c], sigma) * wgt
    out = 1 - (1 - np.clip(a, 0, 1)) * (1 - np.clip(glow * strength, 0, 1))      # screen blend
    rgba = np.concatenate([out, np.ones((h, w, 1), np.float32)], axis=2)
    img.pixels.foreach_set(rgba.ravel())
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)


def render_previews(parts, vfx, imgs):
    os.makedirs(PREVIEWS, exist_ok=True)
    sc = bpy.context.scene
    sc.cycles.samples = 64
    sc.cycles.use_denoising = True
    sc.view_settings.view_transform = "Standard"     # keeps the neon colours saturated
    sc.render.film_transparent = False
    world = bpy.data.worlds.new("Dark")
    sc.world = world
    wnt = nodes_of(world)
    bg = wnt.nodes.new("ShaderNodeBackground")
    bg.inputs["Color"].default_value = (0.004, 0.007, 0.009, 1)
    wo = wnt.nodes.new("ShaderNodeOutputWorld")
    wnt.links.new(bg.outputs[0], wo.inputs["Surface"])

    sword = list(parts.values())
    for ob in vfx.values():
        ob.hide_render = True

    def light(name, kind, loc, energy, color, size=1.0, rot=(0, 0, 0)):
        ld = bpy.data.lights.new(name, kind)
        ld.energy = energy
        ld.color = color
        if kind == "AREA":
            ld.size = size
        lo = bpy.data.objects.new(name, ld)
        lo.location = loc
        lo.rotation_euler = rot
        sc.collection.objects.link(lo)
        return lo

    def look_at(ob, target):
        d = Vector(target) - ob.location
        ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()

    lights = [light("Key", "AREA", (-2.5, -3.5, 3.0), 260, (1, 0.97, 0.94), 2.5),
              light("Rim", "AREA", (2.5, 2.5, 2.0), 300, (0.5, 0.9, 1.0), 2.0),
              light("Fill", "AREA", (2.0, -3.0, -0.5), 60, (0.7, 0.8, 1.0), 3.0)]
    for lo in lights:
        look_at(lo, (0, 0, 0.9))

    cam_d = bpy.data.cameras.new("Cam")
    cam = bpy.data.objects.new("Cam", cam_d)
    sc.collection.objects.link(cam)
    sc.camera = cam

    # decorative energy motes and orbiting rocks for the hero shots
    rng = np.random.default_rng(5)
    deco = []
    mote_mat = pbr_material("Mote", color=(0.3, 1, 1), emission=(0.3, 1, 1), strength=6)
    for k in range(70):
        bm = bmesh.new()
        bmesh.ops.create_icosphere(bm, subdivisions=1, radius=float(rng.uniform(0.006, 0.02)))
        me = bpy.data.meshes.new("mote")
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new("Mote", me)
        z = float(rng.uniform(0.8, 3.4))
        r = float(rng.uniform(0.25, 0.6))
        a = float(rng.uniform(0, 2 * math.pi))
        ob.location = (r * math.cos(a), r * math.sin(a) * 0.6, z)
        ob.data.materials.append(mote_mat)
        sc.collection.objects.link(ob)
        deco.append(ob)
    for k, name in enumerate(("Rock1", "Rock2", "Rock3", "Rock1", "Rock2")):
        ob = vfx[name].copy()
        ob.data = vfx[name].data
        ob.hide_render = False
        side = -1 if k % 2 else 1
        ob.location = (side * float(rng.uniform(0.38, 0.5)), float(rng.uniform(-0.15, 0.15)), 1.0 + 0.45 * k)
        ob.rotation_euler = tuple(float(x) for x in rng.uniform(0, 3, 3))
        sc.collection.objects.link(ob)
        deco.append(ob)

    def shot(name, loc, target, lens, res, theme="Cyan"):
        mats = theme_materials(imgs, theme, for_render=True)
        for k, ob in parts.items():
            set_material(ob, mats[k])
        mote_mat.node_tree.nodes["Principled BSDF"].inputs["Emission Color"].default_value = (*THEMES[theme]["vein"], 1)
        mote_mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (*THEMES[theme]["vein"], 1)
        cam.location = loc
        look_at(cam, target)
        cam_d.lens = lens
        sc.render.resolution_x, sc.render.resolution_y = res
        path = os.path.join(PREVIEWS, name + ".png")
        sc.render.filepath = path
        bpy.ops.render.render(write_still=True)
        bloom(path)
        print("rendered", path)

    shot("hero_cyan", (1.8, -7.0, 1.05), (0, 0, 0.95), 50, (900, 1500))
    shot("hero_gold", (1.8, -7.0, 1.05), (0, 0, 0.95), 50, (900, 1500), theme="Gold")
    for ob in deco:
        ob.hide_render = True
    shot("detail_hilt", (1.2, -3.0, 0.3), (0, 0, -0.2), 50, (1100, 1100))

    # action shot: the slash arc and shockwave meshes around the sword
    for k in ("SlashArc", "SlashCore", "ShockRing", "RingCore", "Shard1", "Shard2"):
        vfx[k].hide_render = False
    t = THEMES["Cyan"]
    set_material(vfx["SlashArc"], glow_render_material("SlashFX", vfx["SlashArc"].data.materials[0].node_tree.nodes["Image Texture"].image, t["edge"], 3.5))
    set_material(vfx["ShockRing"], glow_render_material("RingFX", vfx["ShockRing"].data.materials[0].node_tree.nodes["Image Texture"].image, t["edge"], 3.0))
    core_mat = pbr_material("CoreFX", color=t["rune"], emission=t["rune"], strength=4.0)
    for k in ("SlashCore", "RingCore", "Shard1", "Shard2"):
        set_material(vfx[k], core_mat)
    vfx["SlashArc"].location = (0.2, -0.5, 1.75)
    vfx["SlashArc"].scale = (2.5, 2.5, 2.5)
    vfx["SlashArc"].rotation_euler = (math.radians(90), math.radians(-38), 0)
    vfx["SlashCore"].location = vfx["SlashArc"].location
    vfx["SlashCore"].scale = vfx["SlashArc"].scale
    vfx["SlashCore"].rotation_euler = vfx["SlashArc"].rotation_euler
    vfx["ShockRing"].location = (0, 0, -1.6)
    vfx["ShockRing"].scale = (3.0, 3.0, 3.0)
    vfx["RingCore"].location = vfx["ShockRing"].location
    vfx["RingCore"].scale = vfx["ShockRing"].scale
    vfx["Shard1"].location, vfx["Shard2"].location = (0.9, -0.3, 2.6), (-1.0, 0.2, 2.0)
    for ob in deco:
        ob.hide_render = False
    shot("vfx_special", (2.6, -8.5, 1.4), (0, 0, 0.7), 40, (1400, 1000))


def main(render=False):
    clean_scene()
    parts = build_sword()
    imgs = texture_sword(parts)
    for k, mat in theme_materials(imgs, "Cyan").items():
        set_material(parts[k], mat)
    vfx = build_vfx(imgs)
    sword_markers = [marker("Mark_O", (0, 0, 0)), marker("Mark_Y", (0, 1, 0)), marker("Mark_Z", (0, 0, 1))]
    export(list(parts.values()) + sword_markers, "MoFengSword")
    for m in sword_markers:
        bpy.data.objects.remove(m)
    vfx_markers = [marker("Mark_O", (0, 0, 0)), marker("Mark_Y", (0, 1, 0)), marker("Mark_Z", (0, 0, 1))]
    export(list(vfx.values()) + vfx_markers, "MoFengVFX")
    for m in vfx_markers:
        bpy.data.objects.remove(m)
    info = layout_json(parts, vfx)
    total_v = sum(p["verts"] for p in info["parts"].values())
    total_t = sum(p["tris"] for p in info["parts"].values())
    print(f"sword: {total_v} vertices, {total_t} triangles")
    for k, p in info["parts"].items():
        print(f"  {k:12s} {p['verts']:6d} verts {p['tris']:6d} tris")
    for img in bpy.data.images:
        if img.filepath_raw and not img.packed_file and os.path.exists(bpy.path.abspath(img.filepath_raw)):
            img.pack()
    bpy.context.preferences.filepaths.save_version = 0      # no .blend1 backup next to the export
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(EXPORT, "MoFengSword.blend"), compress=True)
    if render:
        render_previews(parts, vfx, imgs)


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    main(render="--render" in argv)
