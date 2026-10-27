"""
Starburst Blade - Blender build script.

Recreates the fiery sword from the reference sheet (item 3): a long needle
blade that swells into a flame-shaped leaf, a starburst guard (dark eye in two
blended energy circles, seven tapered spikes, flame petals, curling ribbons)
and a long tapering spike handle. The meshes are only a faint base: the
sword is drawn by layered energy effects (see render_previews and the Roblox installer). Every outline below was measured from the
reference after rotating the sword upright around its star:
    u = pixels across (right +), v = pixels along (tip at v = -748, handle end at +382)

Run it either way:
  * Blender: Scripting tab > Open > build_starburst.py > Run Script (starts a new scene)
  * Headless: python build_starburst.py [--render]   (with the `bpy` module installed)

Writes ../export (StarburstSword.fbx/.glb, StarburstVFX.fbx/.glb, .blend,
sword_layout.json), ../textures and ../previews.

Units are Roblox studs (0.004 studs per reference pixel, 4.5 studs long).
Axes: blade along +Z, star at the origin, flat of the blade facing -Y.
"""

import json
import math
import os
import sys
import warnings

import bpy  # noqa: I001  (bpy first: it makes bmesh/mathutils importable)
import bmesh
import numpy as np
from mathutils import Matrix, Vector

warnings.filterwarnings("ignore", category=DeprecationWarning)


def _script_dir():
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        if os.path.exists(os.path.join(here, "fire_textures.py")):
            return here
    except NameError:
        pass
    for text in bpy.data.texts:
        if text.filepath and text.filepath.endswith("build_starburst.py"):
            return os.path.dirname(bpy.path.abspath(text.filepath))
    return bpy.path.abspath("//")


HERE = _script_dir()
sys.path.insert(0, HERE)
import fire_textures as ft  # noqa: E402

ROOT = os.path.normpath(os.path.join(HERE, ".."))
EXPORT = os.path.join(ROOT, "export")
TEXTURES = os.path.join(ROOT, "textures")
PREVIEWS = os.path.join(ROOT, "previews")

S = 0.004                       # studs per reference pixel


def X(u):
    return u * S


def Z(v):
    return -v * S


# Neon colours, sampled from the reference
YELLOW = (1.0, 0.95, 0.62)
ORANGE = (1.0, 0.42, 0.06)
RED = (0.9, 0.07, 0.03)
CRIMSON = (0.22, 0.02, 0.02)
INK = (0.03, 0.005, 0.005)


# ---------------------------------------------------------------- measured profiles


def pchip(xs, ys):
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


V_TIP, V_END = -748, 382
BV = [-748, -700, -650, -600, -550, -500, -450, -400, -350, -300, -250, -200, -150, -100, -60, -30]
SHELL_L = pchip(BV, [1.5, -3, -6, -10, -14, -18, -22, -22, -22, -23, -28, -38, -46, -45, -40, -32])
SHELL_R = pchip(BV, [2.5, 7, 10, 12, 15, 20, 24, 26, 30, 34, 44, 50, 50, 46, 40, 32])
CORE_L = pchip(BV, [1.8, 0.2, -1.5, -2.5, -3.5, -5, -6.5, -7.5, -8.5, -10, -16, -23, -27, -25, -21, -18])
CORE_R = pchip(BV, [2.2, 2.8, 3.5, 4.5, 4.5, 5, 5.5, 7, 9, 14, 20, 25, 27, 25, 21, 18])
RIM_L = pchip(BV, [0.5, 1.5, 2, 2.5, 3, 3, 3, 3, 3, 3, 4, 5, 5, 5, 4, 3])        # lit orange-brown rim
DARK_R = pchip(BV, [1, 3, 4, 6, 8, 9, 10, 11, 12, 13, 14, 14, 12, 10, 8, 6])      # dark shadow band


def blade_ht(v):
    """Half thickness of the blade at its centre line (studs)."""
    f = (v - V_TIP) / (-30 - V_TIP)
    return 0.006 + 0.02 * f ** 0.8


# (tip u, tip v, base width px, has glowing core)
RAYS = [(-80, -145, 30, True), (95, -125, 20, True), (185, 48, 30, True), (-205, -28, 32, True),
        (-88, 88, 24, True), (97, 137, 24, True), (-170, 158, 12, False)]

# curling ribbons, as (u, v) paths around the star
RIBBONS = [
    [(-35, -45), (-95, -95), (-150, -150), (-172, -188), (-148, -207), (-112, -184), (-96, -150)],
    [(35, -30), (90, -60), (150, -86), (196, -76), (210, -50), (190, -30), (150, -24)],
    [(-35, 35), (-90, 70), (-126, 100), (-121, 126), (-95, 121), (-70, 96)],
    [(40, 40), (74, 80), (86, 120), (71, 141), (50, 126)],
]

# flame petals between the spikes: (angle deg, length px, width px, colour)
PETALS = [(-118, 95, 26, "red"), (-62, 80, 22, "orange"), (-18, 70, 20, "red"), (22, 74, 22, "orange"),
          (68, 78, 20, "red"), (112, 84, 24, "orange"), (158, 76, 22, "red"), (-162, 90, 26, "orange")]

HANDLE_V = [20, 60, 100, 150, 200, 250, 300, 340, 382]
HANDLE_R = pchip(HANDLE_V, [24, 24, 19, 15, 12, 9.5, 6, 3.5, 0.8])

# The two blended energy circles: one round the eye, one round the top of the handle.
# They overlap at the junction, and one stream of energy runs round both as a figure-8.
RING_R = X(34)
RING_A = (0.0, 0.0, 0.0)
RING_B = (0.0, 0.0, Z(60))
JUNCTION = (0.0, 0.0, Z(30))
EYE_R = X(18)


# ---------------------------------------------------------------- mesh helpers


class MB:
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
        a, b, c = (Vector(self.v[i]) for i in idx[:3])
        if (b - a).cross(c - a).dot(Vector(want)) < 0:
            idx = list(reversed(idx))
        self.face(idx, smooth)

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
            bm = bmesh.new()
            bm.from_mesh(me)
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
            bm.to_mesh(me)
            bm.free()
        return ob


def shade(ob, angle=35):
    for p in ob.data.polygons:
        p.use_smooth = True
    ob.data.set_sharp_from_angle(angle=math.radians(angle))


def tube(mb, pts, radius, sides=6, flatten=1.0, plane_normal=None, caps=True, uv_v=(0, 1)):
    n = len(pts)
    pts = [Vector(p) for p in pts]
    rings, prev = [], None
    for k, p in enumerate(pts):
        tan = (pts[min(n - 1, k + 1)] - pts[max(0, k - 1)]).normalized()
        if plane_normal is not None:
            b = Vector(plane_normal).normalized()
            nrm = tan.cross(b).normalized()
            b = nrm.cross(tan).normalized()
        else:
            if prev is None:
                ref = Vector((0, 0, 1)) if abs(tan.z) < 0.9 else Vector((1, 0, 0))
                nrm = tan.cross(ref).normalized()
            else:
                nrm = (prev - tan * prev.dot(tan)).normalized()
            prev = nrm
            b = tan.cross(nrm).normalized()
        r = radius(k / (n - 1))
        t = k / (n - 1)
        rings.append([mb.add(p + nrm * (r * math.cos(2 * math.pi * j / sides)) +
                             b * (r * flatten * math.sin(2 * math.pi * j / sides)),
                             (j / sides, uv_v[0] + (uv_v[1] - uv_v[0]) * t)) for j in range(sides)])
    for k in range(n - 1):
        for j in range(sides):
            j1 = (j + 1) % sides
            mb.face([rings[k][j], rings[k][j1], rings[k + 1][j1], rings[k + 1][j]])
    if caps:
        for ring, p in ((rings[0], pts[0]), (rings[-1], pts[-1])):
            c = mb.add(p)
            for j in range(sides):
                mb.face([ring[j], ring[(j + 1) % sides], c])


def smooth_path(pts, per=4):
    """Catmull-Rom through 3D points."""
    pts = [Vector(p) for p in pts]
    out = []
    for i in range(len(pts) - 1):
        p0, p1 = pts[max(0, i - 1)], pts[i]
        p2, p3 = pts[i + 1], pts[min(len(pts) - 1, i + 2)]
        for k in range(per):
            t = k / per
            t2, t3 = t * t, t * t * t
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 +
                              (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    out.append(pts[-1])
    return out


# ---------------------------------------------------------------- blade


def blade_rows():
    rows = []
    for k in range(70):
        f = k / 69
        rows.append(V_TIP + (-30 - V_TIP) * (1 - (1 - f) ** 1.25))   # denser near the tip
    return rows


def shell_surface(x, v):
    """Front-face height (positive number) of the blade shell at (x studs, v px)."""
    l, r = X(SHELL_L(v)), X(SHELL_R(v))
    mid, half = (l + r) / 2, max((r - l) / 2, 1e-5)
    t = min(1.0, abs((x - mid) / half))
    return blade_ht(v) * (1 - t ** 2.2)


def lens_layer(mb, left, right, lift, uv_fn=None, ts=(-1, -0.8, -0.55, -0.25, 0, 0.25, 0.55, 0.8, 1)):
    """Closed lens following the blade, sitting `lift` above the shell surface.
    left(v)/right(v) give the layer's edges in px."""
    rows = blade_rows()
    front, back = [], []
    for v in rows:
        l, r = X(left(v)), X(right(v))
        if r - l < X(0.6):                      # the needle tip: keep layers from crossing over
            mid = (l + r) / 2
            l, r = mid - X(0.3), mid + X(0.3)
        fr, bk = [], []
        for t in ts:
            x = (l + r) / 2 + t * (r - l) / 2
            edge = abs(t) ** 4
            h = shell_surface(x, v) + lift * (1 - 0.7 * edge)
            if lift == 0:
                h = shell_surface(x, v)
            uv = uv_fn(t, v) if uv_fn else ((t + 1) / 2, (v - V_TIP) / (-30 - V_TIP))
            fr.append(mb.add((x, -h, Z(v)), uv))
            bk.append(fr[-1] if (lift == 0 and abs(t) == 1) else mb.add((x, h, Z(v)), uv))
        front.append(fr)
        back.append(bk)
    tip_f = mb.add((X((left(V_TIP) + right(V_TIP)) / 2), 0, Z(V_TIP) + 0.004), (0.5, 0))
    n = len(ts)
    for i in range(len(rows) - 1):
        for j in range(n - 1):
            mb.face([front[i][j], front[i][j + 1], front[i + 1][j + 1], front[i + 1][j]])
            mb.face([back[i][j + 1], back[i][j], back[i + 1][j], back[i + 1][j + 1]])
        if lift != 0:          # side walls (inside the shell)
            for j in (0, n - 1):
                mb.face([front[i][j], front[i + 1][j], back[i + 1][j], back[i][j]])
    for j in range(n - 1):
        mb.face([front[0][j], front[0][j + 1], tip_f])
        mb.face([back[0][j + 1], back[0][j], tip_f])
    mb.face(front[-1] + list(reversed(back[-1][1:-1] if lift == 0 else back[-1])), smooth=False)


def build_blade(red):
    shell, glow, core = MB(), MB(), MB()
    # shell UVs live in the left half of the shell atlas: u 0 = lit rim edge, 0.5 = shadow edge
    lens_layer(shell, SHELL_L, SHELL_R, 0.0,
               uv_fn=lambda t, v: ((t + 1) / 4, 1 - (v - V_TIP) / (-30 - V_TIP)))
    lens_layer(glow, lambda v: SHELL_L(v) + RIM_L(v), lambda v: SHELL_R(v) - DARK_R(v), 0.0035)
    lens_layer(core, CORE_L, CORE_R, 0.0075)
    # red band between the hot core and the dark shadow edge (right side in the reference)
    lens_layer(red, lambda v: CORE_R(v) - 1.5, lambda v: SHELL_R(v) - DARK_R(v) - 0.5, 0.0055)
    return shell, glow, core


def blade_sparkles(mb):
    rng = np.random.default_rng(4)
    for face in (-1, 1):
        for _ in range(22):
            v = float(rng.uniform(-640, -140))
            u = SHELL_R(v) - DARK_R(v) * float(rng.uniform(0.2, 0.8))
            x = X(u)
            y = face * (shell_surface(x, v) + 0.0025)
            r = float(rng.uniform(0.005, 0.009))
            c = Vector((x, y, Z(v)))
            q = [mb.add(c + Vector((dx, 0, dz))) for dx, dz in ((r, 0), (0, r * 1.4), (-r, 0), (0, -r * 1.4))]
            mb.oriented_face(q, (0, face, 0), smooth=False)


# ---------------------------------------------------------------- star guard


def spike(mb, base_u, base_v, tip_u, tip_v, width_px, half_thick, uv_x=(0.5, 1.0), segs=6, core_frac=1.0):
    """Tapered spike with a diamond cross-section in the guard plane."""
    b = Vector((X(base_u), 0, Z(base_v)))
    t = Vector((X(tip_u), 0, Z(tip_v)))
    axis = t - b
    length = axis.length * core_frac
    d = axis.normalized()
    side = Vector((0, 1, 0)).cross(d).normalized()
    rings = []
    for k in range(segs + 1):
        f = k / segs
        c = b + d * (length * f)
        w = X(width_px) / 2 * (1 - f) ** 0.9
        h = half_thick * (1 - f) ** 0.8
        ring = [mb.add(c + side * w, (uv_x[1], 1 - f)), mb.add(c + Vector((0, -h, 0)), ((uv_x[0] + uv_x[1]) / 2, 1 - f)),
                mb.add(c - side * w, (uv_x[0], 1 - f)), mb.add(c + Vector((0, h, 0)), ((uv_x[0] + uv_x[1]) / 2, 1 - f))]
        rings.append(ring)
    for k in range(segs):
        for j in range(4):
            j1 = (j + 1) % 4
            mb.face([rings[k][j], rings[k][j1], rings[k + 1][j1], rings[k + 1][j]], smooth=False)
    mb.face(list(reversed(rings[0])), smooth=False)


def ribbon_paths():
    """The reference's curling ribbons as smooth 3D paths (star at the origin), drawn
    in Roblox by trails that trace them over and over."""
    out = []
    for i, path in enumerate(RIBBONS):
        bow = 0.05 * (1 if i % 2 == 0 else -1)
        n = len(path)
        pts = [(X(u), bow * math.sin(math.pi * k / (n - 1)), Z(v)) for k, (u, v) in enumerate(path)]
        out.append([tuple(round(c, 4) for c in p) for p in smooth_path(pts, 4)])
    return out


def _hermite(p0, m0, p1, m1, n):
    out = []
    for k in range(1, n):
        t = k / n
        out.append(p0 * (2 * t ** 3 - 3 * t ** 2 + 1) + m0 * (t ** 3 - 2 * t ** 2 + t) +
                   p1 * (3 * t ** 2 - 2 * t ** 3) + m1 * (t ** 3 - t ** 2))
    return out


def figure8_path(step=5, leave=25):
    """One closed stream of energy round both circles: anticlockwise round circle A, across
    the junction, clockwise round circle B and back across, so the two crossings meet in an X
    at the junction and the circles read as one flowing structure. Last point = first point.
    `leave` is how far (degrees) before the circles' meeting point the stream cuts across."""
    def on(centre, deg):
        a = math.radians(deg)
        return Vector((RING_R * math.cos(a), 0, centre[2] + RING_R * math.sin(a)))

    def tangent(deg, sign):                    # sign +1 = anticlockwise, -1 = clockwise
        a = math.radians(deg)
        return Vector((-math.sin(a), 0, math.cos(a))) * sign

    a0, a1 = -leave, 180 + leave               # arc on circle A (anticlockwise)
    b0, b1 = leave, -180 - leave               # arc on circle B (clockwise)
    arc_a = [on(RING_A, d) for d in range(a0, a1 + 1, step)]
    arc_b = [on(RING_B, d) for d in range(b0, b1 - 1, -step)]
    chord = (arc_b[0] - arc_a[-1]).length
    n = max(2, round(chord / (RING_R * math.radians(step))))
    m = chord * 0.9
    cross_1 = _hermite(arc_a[-1], tangent(a1, 1) * m, arc_b[0], tangent(b0, -1) * m, n)
    cross_2 = _hermite(arc_b[-1], tangent(b1, -1) * m, arc_a[0], tangent(a0, 1) * m, n)
    loop = arc_a + cross_1 + arc_b + cross_2
    loop.append(loop[0])
    return [tuple(round(c, 4) for c in p) for p in loop]


def spike_beams():
    """(base, tip, width) of the energy beam drawn over each spike, in studs.
    The width leaves room for the texture's soft glow round the spike."""
    out = []
    for tu, tv, w, _ in RAYS:
        length = math.hypot(tu, tv)
        base = (X(tu / length * 8), 0.0, Z(tv / length * 8))
        out.append((base, (X(tu * 1.04), 0.0, Z(tv * 1.04)), X(w) * 1.9))
    return out


def build_star(shell, yellow, orange, red, sparkle):
    # rays: black shell spike + narrower, taller glowing core spike
    for tu, tv, w, has_core in RAYS:
        length = math.hypot(tu, tv)
        bu, bv = tu / length * 20, tv / length * 20
        spike(shell, bu, bv, tu, tv, w, 0.02 if has_core else 0.012, uv_x=(0.5, 1.0))
        if has_core:
            spike(yellow, bu, bv, tu, tv, w * 0.7, 0.026, core_frac=0.9)
    # (the eye and its glowing rings are pure VFX now: see figure8_path() and the Roblox installer)
    # flame petals: flat curved tongues between the spikes
    for ang, length, width, colour in PETALS:
        mb = orange if colour == "orange" else red
        a = math.radians(ang)
        d = Vector((math.cos(a), 0, -math.sin(a)))
        side = Vector((0, 1, 0)).cross(d).normalized()
        bend = 0.25
        pts_l, pts_r = [], []
        for k in range(7):
            f = k / 6
            c = d * X(36 + length * f) + side * X(width) * bend * f * f
            w = X(width) / 2 * math.sin(math.pi * min(1, f * 1.15 + 0.08)) ** 0.8 * (1 - f) ** 0.4
            pts_l.append(c - side * w)
            pts_r.append(c + side * w)
        for face in (-1, 1):
            y = Vector((0, face * 0.016, 0))
            L = [mb.add(p + y) for p in pts_l]
            R = [mb.add(p + y) for p in pts_r]
            for k in range(6):
                mb.oriented_face([L[k], R[k], R[k + 1], L[k + 1]], (0, face, 0), smooth=False)
    # (the curling ribbons are red swirl VFX now: see ribbon_paths())
    # sparkles on the spikes
    rng = np.random.default_rng(9)
    for tu, tv, w, _ in RAYS[:6]:
        for face in (-1, 1):
            f = float(rng.uniform(0.45, 0.8))
            c = Vector((X(tu * f), face * 0.012, Z(tv * f)))
            r = 0.006
            q = [sparkle.add(c + Vector(o)) for o in ((r, 0, 0), (0, 0, r * 1.4), (-r, 0, 0), (0, 0, -r * 1.4))]
            sparkle.oriented_face(q, (0, face, 0), smooth=False)


# ---------------------------------------------------------------- handle


def build_handle(orange, yellow):
    hb = MB()
    sides = 16
    vs = [20 + (V_END - 20) * (k / 30) ** 1.0 for k in range(31)]
    rings = []
    for v in vs:
        r = X(HANDLE_R(v))
        rings.append([hb.add((r * math.cos(2 * math.pi * j / sides), r * math.sin(2 * math.pi * j / sides), Z(v)),
                             (j / sides, (v - 20) / (V_END - 20))) for j in range(sides + 1)])
    for k in range(len(vs) - 1):
        for j in range(sides):
            hb.face([rings[k][j], rings[k][j + 1], rings[k + 1][j + 1], rings[k + 1][j]])
    tip = hb.add((0, 0, Z(V_END) - 0.004), (0.5, 1))
    for j in range(sides):
        hb.face([rings[-1][j], rings[-1][j + 1], tip])
    top = hb.add((0, 0, Z(20)), (0.5, 0))
    for j in range(sides):
        hb.face([rings[0][j + 1], rings[0][j], top])
    # orange band and yellow line down the front and back, hugging the spindle
    for mb, frac, lift in ((orange, 0.62, 0.003), (yellow, 0.13, 0.006)):
        for face in (-1, 1):
            rows = []
            for v in vs[:-2]:
                if v < 24:                 # let the glow start inside the star
                    continue
                r = X(HANDLE_R(v))
                row = []
                for t in (-1, -0.5, 0, 0.5, 1):
                    x = t * frac * r
                    y = face * (math.sqrt(max(r * r - x * x, 0)) + lift * (1 - 0.6 * abs(t)))
                    row.append(mb.add((x, y, Z(v))))
                rows.append(row)
            for k in range(len(rows) - 1):
                for j in range(4):
                    mb.oriented_face([rows[k][j], rows[k][j + 1], rows[k + 1][j + 1], rows[k + 1][j]], (0, face, 0))
    return hb


# ---------------------------------------------------------------- aura & markers


def build_aura():
    mb = MB()
    rows, sides = 34, 10
    grid = []
    for k in range(rows):
        f = k / (rows - 1)
        v = -40 + (V_TIP - 50 + 40) * f
        vv = max(v, V_TIP)
        l, r = SHELL_L(vv) - 10, SHELL_R(vv) + 10
        mid, half = X((l + r) / 2), X((r - l) / 2) * (1 - f ** 6) + 0.01
        th = (0.06 * (1 - 0.6 * f)) * (1 - f ** 6) + 0.008
        grid.append([mb.add((mid + half * math.cos(2 * math.pi * j / sides), th * math.sin(2 * math.pi * j / sides), Z(v)),
                            (j / sides, f * 4)) for j in range(sides + 1)])
    for k in range(rows - 1):
        for j in range(sides):
            mb.face([grid[k][j], grid[k][j + 1], grid[k + 1][j + 1], grid[k + 1][j]])
    return mb.to_object("Aura", recalc=True)


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


# ---------------------------------------------------------------- materials


def nodes_of(mat):
    mat.use_nodes = True
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    return nt


def np_image(name, arr, path):
    h, w = arr.shape[:2]
    img = bpy.data.images.new(name, w, h, alpha=True)
    img.pixels.foreach_set(np.flipud(arr).astype(np.float32).ravel())
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    return img


def pbr_material(name, image=None, color=(1, 1, 1), metallic=0.0, rough=0.5, emission=None, strength=0.0,
                 alpha_from_image=False):
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
    if emission is not None:
        bsdf.inputs["Emission Color"].default_value = (*emission, 1)
    bsdf.inputs["Emission Strength"].default_value = strength
    return mat


def emission_material(name, image, strength=1.0, alpha=False, uv_rect=None, additive=False):
    """Unlit, painted look: the texture is the colour, lights don't shade it.
    Principled base colour = texture as well, so exporters still carry the texture.
    additive: light is added on top of what is behind (like Roblox LightEmission = 1)."""
    mat = bpy.data.materials.new(name)
    nt = nodes_of(mat)
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = image
    if uv_rect is not None:                         # pick one cell of a flipbook
        tc = nt.nodes.new("ShaderNodeTexCoord")
        mp = nt.nodes.new("ShaderNodeMapping")
        mp.inputs["Location"].default_value = (uv_rect[0], uv_rect[1], 0)
        mp.inputs["Scale"].default_value = (uv_rect[2], uv_rect[3], 1)
        nt.links.new(tc.outputs["UV"], mp.inputs["Vector"])
        nt.links.new(mp.outputs["Vector"], tex.inputs["Vector"])
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (0, 0, 0, 1)
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Emission Color"])
    bsdf.inputs["Emission Strength"].default_value = strength
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    if additive:
        em = nt.nodes.new("ShaderNodeEmission")
        nt.links.new(tex.outputs["Color"], em.inputs["Color"])
        mul = nt.nodes.new("ShaderNodeMath")
        mul.operation = "MULTIPLY"
        nt.links.new(tex.outputs["Alpha"], mul.inputs[0])
        mul.inputs[1].default_value = strength
        nt.links.new(mul.outputs[0], em.inputs["Strength"])
        tr = nt.nodes.new("ShaderNodeBsdfTransparent")
        add = nt.nodes.new("ShaderNodeAddShader")
        nt.links.new(tr.outputs[0], add.inputs[0])
        nt.links.new(em.outputs[0], add.inputs[1])
        nt.links.new(add.outputs[0], out.inputs["Surface"])
    elif alpha:
        tr = nt.nodes.new("ShaderNodeBsdfTransparent")
        mx = nt.nodes.new("ShaderNodeMixShader")
        nt.links.new(tex.outputs["Alpha"], mx.inputs[0])
        nt.links.new(tr.outputs[0], mx.inputs[1])
        nt.links.new(bsdf.outputs[0], mx.inputs[2])
        nt.links.new(mx.outputs[0], out.inputs["Surface"])
    else:
        nt.links.new(bsdf.outputs[0], out.inputs["Surface"])
    return mat


def set_material(ob, mat):
    ob.data.materials.clear()
    ob.data.materials.append(mat)


def ghost(ob, opacity):
    """See-through copy of the object's material (Roblox: Transparency = 1 - opacity)."""
    mat = ob.active_material.copy()
    nt = mat.node_tree
    out = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
    src = out.inputs["Surface"].links[0].from_socket
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mx = nt.nodes.new("ShaderNodeMixShader")
    mx.inputs[0].default_value = opacity
    nt.links.new(tr.outputs[0], mx.inputs[1])
    nt.links.new(src, mx.inputs[2])
    nt.links.new(mx.outputs[0], out.inputs["Surface"])
    set_material(ob, mat)


# ---------------------------------------------------------------- build / export


def clean_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.unit_settings.system = "NONE"


def tri_count(ob):
    return sum(len(p.vertices) - 2 for p in ob.data.polygons)


def build_sword():
    red_mb, sparkle_mb = MB(), MB()
    shell_mb, glow_mb, core_mb = build_blade(red_mb)
    blade_sparkles(sparkle_mb)
    build_star(shell_mb, core_mb, glow_mb, red_mb, sparkle_mb)
    handle_mb = build_handle(glow_mb, core_mb)
    parts = {
        "Handle": handle_mb.to_object("Handle", recalc=True),
        "Shell": shell_mb.to_object("Shell", recalc=True),
        "GlowOrange": glow_mb.to_object("GlowOrange"),
        "GlowYellow": core_mb.to_object("GlowYellow"),
        "FlameRed": red_mb.to_object("FlameRed"),
        "Sparkles": sparkle_mb.to_object("Sparkles"),
        "Aura": build_aura(),
    }
    for name in ("Handle", "Shell", "GlowYellow", "GlowOrange"):
        shade(parts[name], 40)
    return parts


def materials(imgs):
    return {
        "Handle": emission_material("HandleShell", imgs["handle"]),
        "Shell": emission_material("Shell", imgs["shell"]),
        # glowing parts are emission only (dark base), so they render exactly their colour
        "GlowOrange": pbr_material("GlowOrange", color=(0.02, 0.01, 0.0), emission=ORANGE, strength=1.0),
        "GlowYellow": pbr_material("GlowYellow", color=(0.02, 0.02, 0.0), emission=YELLOW, strength=1.0),
        "FlameRed": pbr_material("FlameRed", color=(0.02, 0.0, 0.0), emission=RED, strength=1.0),
        "Sparkles": pbr_material("Sparkles", color=(0.02, 0.02, 0.02), emission=(1, 1, 1), strength=1.5),
        "Aura": pbr_material("Aura", imgs["heat"], color=ORANGE),
    }


BLADE_PAINT_W = 0.42          # studs across the blade beam (covers the widest part with margin)
MESH_OPACITY = 0.2            # the meshes are a faint base under the effects (Roblox Transparency 0.8)
HANDLE_PAINT_W = 0.22


def _band(x, lo, hi, aa):
    """1 inside [lo, hi], soft edges `aa` wide."""
    return np.clip((x - lo) / aa + 0.5, 0, 1) * np.clip((hi - x) / aa + 0.5, 0, 1)


def blade_paint(w=1024, h=192, seed=31):
    """The blade exactly as drawn in the reference, for the camera-facing blade beam.
    Image x runs along the blade (0 = star end, 1 = tip); image y runs across it."""
    us = np.linspace(0, 1, w)
    vpx = -30 + (V_TIP + 30) * us                                   # reference v for each column
    xpx = (np.linspace(-0.5, 0.5, h) * BLADE_PAINT_W / S)[:, None]  # reference u for each row
    L, R = np.array([SHELL_L(v) for v in vpx])[None], np.array([SHELL_R(v) for v in vpx])[None]
    CL, CR = np.array([CORE_L(v) for v in vpx])[None], np.array([CORE_R(v) for v in vpx])[None]
    RIM, DARK = np.array([RIM_L(v) for v in vpx])[None], np.array([DARK_R(v) for v in vpx])[None]
    aa = 1.2
    shell = _band(xpx, L, R, aa)
    core = _band(xpx, CL, CR, aa * 1.5)
    rim = _band(xpx, L, L + RIM, aa)
    dark = _band(xpx, R - DARK, R, aa)
    red = _band(xpx, CR - 1.5, R - DARK, aa) * (1 - core)
    col = np.zeros((h, w, 3)) + np.array(ORANGE)
    col = col * (1 - red[..., None]) + np.array(RED) * red[..., None]
    hot = core * (0.55 + 0.45 * np.clip(1 - np.abs(xpx - (CL + CR) / 2) / np.maximum((CR - CL) / 2, 0.5), 0, 1))
    col = col * (1 - core[..., None]) + (np.array(YELLOW) * hot[..., None] + np.array(ft.GOLD) * (core - hot)[..., None])
    col = col * (1 - rim[..., None]) + np.array([0.75, 0.33, 0.08]) * rim[..., None]
    col = col * (1 - dark[..., None]) + np.array(ft.INK) * 1.4 * dark[..., None]
    sp = ft.sparkles(h, w, 60, seed, 1.8) * dark
    col = col * (1 - sp[..., None]) + sp[..., None]
    shell = shell * ft._smooth(us, 0.0, 0.04)[None]         # melts into the energy circles at the star
    return np.concatenate([np.clip(col, 0, 1), shell[..., None]], axis=2).astype(np.float32)


def handle_paint(w=1024, h=96):
    us = np.linspace(0, 1, w)
    vpx = 24 + (V_END - 24) * us
    xpx = (np.linspace(0.5, -0.5, h) * HANDLE_PAINT_W / S)[:, None]
    r = np.array([HANDLE_R(v) for v in vpx])[None]
    body = _band(xpx, -r, r, 1.0)
    band = _band(xpx, -0.62 * r, 0.62 * r, 1.0)
    line = _band(xpx, -0.13 * r - 0.4, 0.13 * r + 0.4, 0.8)
    col = np.zeros((h, w, 3)) + np.array(CRIMSON) * 1.4
    col = col * (1 - band[..., None]) + np.array(ORANGE) * band[..., None]
    col = col * (1 - line[..., None]) + np.array(YELLOW) * line[..., None]
    fade = (0.6 + 0.4 * (1 - us))[None, :, None]
    body = body * ft._smooth(us, 0.0, 0.07)[None]           # no hard edge where it leaves the circles
    return np.concatenate([np.clip(col * fade, 0, 1), body[..., None]], axis=2).astype(np.float32)


def textures():
    os.makedirs(TEXTURES, exist_ok=True)
    return {
        "blade_paint": np_image("fx_bladepaint", blade_paint(), os.path.join(TEXTURES, "fx_bladepaint.png")),
        "handle_paint": np_image("fx_handlepaint", handle_paint(), os.path.join(TEXTURES, "fx_handlepaint.png")),
        "shell": np_image("shell_atlas", ft.shell_atlas(), os.path.join(TEXTURES, "shell_atlas.png")),
        "handle": np_image("handle_shell", ft.handle_shell(), os.path.join(TEXTURES, "handle_shell.png")),
        "heat": np_image("heat_flow", ft.heat_flow(), os.path.join(TEXTURES, "heat_flow.png")),
    }


def build_vfx_carriers():
    """One tiny quad per VFX texture, so the Roblox importer uploads them."""
    out = {}
    sources = [(name, fn) for name, fn in ft.VFX.items()] + [("BladePaint", None), ("HandlePaint", None)]
    for i, (name, fn) in enumerate(sources):
        if fn is None:
            img = bpy.data.images[f"fx_{name.lower()}"]
        else:
            img = np_image(f"fx_{name.lower()}", fn(), os.path.join(TEXTURES, f"fx_{name.lower()}.png"))
        mb = MB()
        x = 2.0 + 0.3 * i
        q = [mb.add((x, 0, 0), (0, 0)), mb.add((x + 0.2, 0, 0), (1, 0)), mb.add((x + 0.2, 0, 0.2), (1, 1)),
             mb.add((x, 0, 0.2), (0, 1))]
        mb.face(q, smooth=False)
        ob = mb.to_object(f"Tex_{name}")
        set_material(ob, pbr_material(f"Tex_{name}", img, alpha_from_image=True))
        out[name] = ob
    return out


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


def layout(parts):
    info = {"units": "studs", "studsPerPixel": S, "parts": {}, "points": {
        "BladeStart": [0, 0, Z(-30)], "BladeTip": [0, 0, Z(V_TIP)], "BladeMid": [0, 0, Z(-380)],
        "TrailBase": [0, 0, Z(-90)], "Star": [0, 0, 0],
        "HandleStart": [0, 0, Z(24)], "HandleEnd": [0, 0, Z(V_END)], "Grip": [0, 0, Z(110)],
        "RingA": list(RING_A), "RingB": list(RING_B), "Junction": list(JUNCTION),
    }, "spikes": [[X(u), 0, Z(v)] for u, v, _, _ in RAYS],
       "spikeBeams": [{"base": [round(c, 4) for c in b], "tip": [round(c, 4) for c in t], "width": round(w, 4)}
                      for b, t, w in spike_beams()],
       "ringRadius": RING_R, "eyeRadius": EYE_R,
       "figure8": figure8_path(),
       "ribbons": ribbon_paths(),
       "bladePaintWidth": BLADE_PAINT_W, "handlePaintWidth": HANDLE_PAINT_W,
       "bladeVolume": {"centre": [0, 0, (Z(-60) + Z(V_TIP + 40)) / 2], "size": [X(80), 0.1, Z(V_TIP + 40) - Z(-60)]}}
    for name, ob in parts.items():
        info["parts"][name] = {"verts": len(ob.data.vertices), "tris": tri_count(ob)}
    with open(os.path.join(EXPORT, "sword_layout.json"), "w") as f:
        json.dump(info, f, indent=2)
    return info


# ---------------------------------------------------------------- previews


def _blur(img, sigma):
    h, w = img.shape
    fy = np.fft.fftfreq(h)[:, None]
    fx = np.fft.fftfreq(w)[None, :]
    k = np.exp(-2 * (math.pi * sigma) ** 2 * (fx * fx + fy * fy))
    return np.real(np.fft.ifft2(np.fft.fft2(img) * k))


def bloom(path, strength=0.45, threshold=0.8):
    img = bpy.data.images.load(path, check_existing=False)
    w, h = img.size
    a = np.array(img.pixels[:], np.float32).reshape(h, w, 4)[..., :3]
    lum = a.max(axis=2, keepdims=True)
    bright = a * np.clip((lum - threshold) / (1 - threshold), 0, 1)
    glow = np.zeros_like(a)
    for sigma, wgt in ((4, 0.45), (12, 0.35), (36, 0.25)):
        for c in range(3):
            glow[..., c] += _blur(bright[..., c], sigma) * wgt
    out = 1 - (1 - np.clip(a, 0, 1)) * (1 - np.clip(glow * strength, 0, 1))
    img.pixels.foreach_set(np.concatenate([out, np.ones((h, w, 1), np.float32)], axis=2).ravel())
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)


def render_previews(parts, carriers):
    os.makedirs(PREVIEWS, exist_ok=True)
    sc = bpy.context.scene
    sc.cycles.samples = 64
    sc.cycles.use_denoising = True
    sc.cycles.transparent_max_bounces = 128
    sc.view_settings.view_transform = "Standard"
    world = bpy.data.worlds.new("Grey")
    sc.world = world
    wnt = nodes_of(world)
    bg = wnt.nodes.new("ShaderNodeBackground")
    bg.inputs["Color"].default_value = (0.045, 0.045, 0.05, 1)       # the sheet's grey card
    wo = wnt.nodes.new("ShaderNodeOutputWorld")
    wnt.links.new(bg.outputs[0], wo.inputs["Surface"])
    for ob in carriers.values():
        ob.hide_render = True
    parts["Aura"].hide_render = True

    def light(name, loc, energy, color, size):
        ld = bpy.data.lights.new(name, "AREA")
        ld.energy, ld.color, ld.size = energy, color, size
        lo = bpy.data.objects.new(name, ld)
        lo.location = loc
        lo.rotation_euler = (Vector((0, 0, 0.6)) - lo.location).to_track_quat("-Z", "Y").to_euler()
        sc.collection.objects.link(lo)

    light("Key", (-3, -4, 3), 300, (1, 0.95, 0.9), 3)
    light("Rim", (3, 3, 2), 200, (1, 0.6, 0.4), 3)
    cam_d = bpy.data.cameras.new("Cam")
    cam = bpy.data.objects.new("Cam", cam_d)
    sc.collection.objects.link(cam)
    sc.camera = cam

    def shot(name, loc, target, res, ortho=None, lens=50, glow=0.45):
        cam.location = loc
        cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        face_camera()
        if ortho:
            cam_d.type, cam_d.ortho_scale = "ORTHO", ortho
        else:
            cam_d.type, cam_d.lens = "PERSP", lens
        sc.render.resolution_x, sc.render.resolution_y = res
        path = os.path.join(PREVIEWS, name + ".png")
        sc.render.filepath = path
        bpy.ops.render.render(write_still=True)
        bloom(path, strength=glow, threshold=0.8 if glow < 0.6 else 0.62)
        print("rendered", path)

    fx_imgs = {name: bpy.data.images.get(f"fx_{name.lower()}") for name in ft.VFX}
    overlays = []

    def card(name, image, centre, axis, width, length, mat=None, lift=0.06, taper=1.0, additive=True,
             strength=1.0, uv_rect=None, u_tiles=1.0, segs=8):
        """Plane centred on `centre`, long side along `axis` (u = 0 at the -axis end), turned to
        face the camera and lifted `lift` towards it. taper = width at the +axis end / width.
        additive = adds light like Roblox's LightEmission 1; otherwise alpha-blended."""
        mb = MB()
        rows = []
        for k in range(segs + 1):
            f = k / segs
            hw = width / 2 * (1 + (taper - 1) * f)
            x = -length / 2 + length * f
            rows.append((mb.add((x, -hw, 0), (f * u_tiles, 0)), mb.add((x, hw, 0), (f * u_tiles, 1))))
        for k in range(segs):
            mb.face([rows[k][0], rows[k + 1][0], rows[k + 1][1], rows[k][1]], smooth=False)
        ob = mb.to_object(name)
        set_material(ob, mat or emission_material(name, image, strength, alpha=True, uv_rect=uv_rect,
                                                  additive=additive))
        overlays.append((ob, Vector(centre), Vector(axis).normalized(), lift))
        return ob

    def strip(name, pts, width_fn, mat, lift=0.07, u_fn=None):
        """Ribbon in the guard plane along `pts`; u runs 1 (start) -> 0 (end) unless u_fn says otherwise."""
        pts = [Vector(p) for p in pts]
        n = len(pts)
        mb = MB()
        L, R = [], []
        off = Vector((0, -lift, 0))
        for k, p in enumerate(pts):
            tan = (pts[min(n - 1, k + 1)] - pts[max(0, k - 1)]).normalized()
            side = Vector((0, 1, 0)).cross(tan).normalized()
            f = k / (n - 1)
            w = width_fn(f)
            u = u_fn(f) if u_fn else 1 - f
            L.append(mb.add(p - side * w + off, (u, 0)))
            R.append(mb.add(p + side * w + off, (u, 1)))
        for k in range(n - 1):
            mb.face([L[k], R[k], R[k + 1], L[k + 1]], smooth=False)
        ob = mb.to_object(name)
        set_material(ob, mat)
        overlays.append((ob, None, None, 0))
        return ob

    def face_camera():
        for ob, centre, axis, lift in overlays:
            if centre is None:                          # strips stay in the guard plane
                continue
            to_cam = (cam.location - centre).normalized()
            if axis.length == 0:                       # sprite: square facing the camera
                x = Vector((0, 0, 1)).cross(to_cam).normalized()
                y = to_cam.cross(x)
            else:                                      # ribbon: long axis fixed, turned to the camera
                x = axis
                y = to_cam.cross(x).normalized()
            z = x.cross(y)
            ob.matrix_world = Matrix((x, y, z)).transposed().to_4x4()
            ob.location = centre + to_cam * lift

    def flip_cell(frame):
        return (frame % 4 * 0.25, 0.75 - frame // 4 * 0.25, 0.25, 0.25)

    loop = [Vector(p) for p in figure8_path()]
    seg_len = [(loop[k + 1] - loop[k]).length for k in range(len(loop) - 1)]
    loop_len = sum(seg_len)

    def loop_at(s):
        """Point and direction on the figure-8 at arc-length fraction s (wraps)."""
        t = (s % 1.0) * loop_len
        for k, seg in enumerate(seg_len):
            if t <= seg or k == len(seg_len) - 1:
                return loop[k].lerp(loop[k + 1], min(1.0, t / seg) if seg > 0 else 0), (loop[k + 1] - loop[k]).normalized()
            t -= seg
        return loop[0], Vector((1, 0, 0))

    rng = np.random.default_rng(21)
    ring_size = 2 * RING_R / 0.62              # EnergyRing's bright line sits at 62% of its radius
    centre_8 = (Vector(RING_A) + Vector(RING_B)) / 2
    blade_len = Z(V_TIP) - Z(-30)
    blade_mid = (0, 0, Z(-30) + blade_len / 2)
    hl = Z(24) - Z(V_END)
    handle_mid = (0, 0, Z(24) - hl / 2)

    # -- one big soft bloom the whole structure sits in
    card("FX_Bloom", fx_imgs["Glow"], tuple(centre_8), (0, 0, 0), 1.7, 1.7, lift=0.02, strength=0.75)
    card("FX_BladeBloom", fx_imgs["Glow"], (0, 0, Z(-340)), (0, 0, 1), 0.9, 3.3, lift=0.025, taper=0.3,
         strength=0.5)

    # -- blade and handle: painted from the reference, with energy flowing through them
    card("FX_BladePaint", bpy.data.images["fx_bladepaint"], blade_mid, (0, 0, 1), BLADE_PAINT_W, blade_len,
         lift=0.07, additive=False, strength=1.1)
    card("FX_HandlePaint", bpy.data.images["fx_handlepaint"], handle_mid, (0, 0, -1), HANDLE_PAINT_W, hl,
         lift=0.07, additive=False, strength=1.1)
    card("FX_BladeFlow", fx_imgs["EnergyFlow"], blade_mid, (0, 0, 1), 0.24, blade_len, lift=0.085, taper=0.06,
         strength=1.3, u_tiles=3.2)
    card("FX_BladeCore", fx_imgs["FlowStroke"], blade_mid, (0, 0, 1), 0.09, blade_len, lift=0.095, taper=0.15,
         strength=1.8)
    card("FX_HandleFlow", fx_imgs["EnergyFlow"], handle_mid, (0, 0, -1), 0.14, hl, lift=0.085, taper=0.1,
         strength=1.0, u_tiles=1.6)
    card("FX_HandleCore", fx_imgs["FlowStroke"], handle_mid, (0, 0, -1), 0.06, hl, lift=0.095, taper=0.2,
         strength=1.5)

    # -- the star's spikes as beams of light
    for i, (b, t, w) in enumerate(spike_beams()):
        b, t = Vector(b), Vector(t)
        card(f"FX_Spike{i}", fx_imgs["EnergySpike"], tuple((b + t) / 2), tuple(t - b), w, (t - b).length,
             lift=0.09, strength=1.4)
    for i, (ang, length, width, _) in enumerate(PETALS):
        a = math.radians(ang)
        d = Vector((math.cos(a), 0, -math.sin(a)))
        card(f"FX_Petal{i}", fx_imgs["EnergyWisp"], tuple(d * X(36 + length * 0.45)), (0, 0, 0), X(width) * 2.6,
             X(width) * 2.6, lift=0.088, strength=0.9, uv_rect=flip_cell(int(rng.integers(1, 7))))

    # -- the two blended circles: overlapping soft rings, one figure-8 stream of energy
    #    running round both, and a hot core where they meet
    card("FX_Void", fx_imgs["Void"], RING_A, (0, 0, 0), EYE_R / 0.3, EYE_R / 0.3, lift=0.128, additive=False)
    card("FX_RingInnerB", fx_imgs["HotCore"], RING_B, (0, 0, 0), RING_R * 1.5, RING_R * 1.5, lift=0.1, strength=0.7)
    card("FX_RingA", fx_imgs["EnergyRing"], RING_A, (0, 0, 0), ring_size, ring_size, lift=0.11, strength=0.6)
    card("FX_RingB", fx_imgs["EnergyRing"], RING_B, (0, 0, 0), ring_size, ring_size, lift=0.112, strength=0.6)
    band = fx_imgs["EnergyBand"]
    strip("FX_Figure8Body", loop, lambda f: 0.07, emission_material("FX_Figure8Body", band, 0.8, additive=True),
          lift=0.113, u_fn=lambda f: 0.5)
    strip("FX_Figure8", loop, lambda f: 0.022, emission_material("FX_Figure8", band, 1.2, additive=True),
          lift=0.115, u_fn=lambda f: 0.5)
    for k in range(7):                                         # wisps peeling off the stream
        p, _ = loop_at(k / 7 + 0.04)
        size = float(rng.uniform(0.09, 0.14))
        card(f"FX_LoopWisp{k}", fx_imgs["EnergyWisp"], tuple(p), (0, 0, 0), size, size, lift=0.117, strength=0.8,
             uv_rect=flip_cell(int(rng.integers(3, 9))))
    head_mat = emission_material("FX_FlowHead", fx_imgs["FlowStroke"], 2.4, additive=True)
    for i in range(3):
        head = i / 3 + 0.07
        pts = []
        for k in range(64):
            f = k / 63
            p, d = loop_at(head - 0.42 * (1 - f))
            side = Vector((0, 1, 0)).cross(d).normalized()
            pts.append(p + side * 0.011 * math.sin(2 * math.pi * (f * 2 + i / 3)))
        strip(f"FX_Flow{i}", pts, lambda f: 0.006 + 0.022 * f ** 0.8, head_mat, lift=0.12 + 0.002 * i)
    card("FX_Junction", fx_imgs["HotCore"], JUNCTION, (0, 0, 0), 0.26, 0.26, lift=0.124, strength=2.0)
    card("FX_JunctionWide", fx_imgs["HotCore"], JUNCTION, (0, 0, 0), 0.5, 0.5, lift=0.122, strength=0.45)
    for k in range(10):                                       # energy fragments flying off the junction
        a = 2 * math.pi * k / 10 + float(rng.uniform(-0.25, 0.25))
        d = Vector((math.cos(a), 0, math.sin(a)))
        r = float(rng.uniform(0.2, 0.36))
        ln = float(rng.uniform(0.07, 0.13))
        card(f"FX_Fragment{k}", fx_imgs["FlowStroke"], tuple(Vector(JUNCTION) + d * r), tuple(-d), 0.022, ln,
             lift=0.135, strength=2.0)

    # -- wisps curling off the blade, and sparkle dust over everything
    for k in range(8):
        v = float(rng.uniform(-470, -70))
        side = (SHELL_R(v) if k % 2 else SHELL_L(v)) * 1.08
        size = float(rng.uniform(0.13, 0.22))
        card(f"FX_Wisp{k}", fx_imgs["EnergyWisp"], (X(side), 0, Z(v) + size * 0.25), (0, 0, 0), size, size,
             lift=0.1, strength=1.0, uv_rect=flip_cell(int(rng.integers(2, 10))))
    dust = []
    for k in range(28):
        p, _ = loop_at(float(rng.uniform(0, 1)))
        dust.append(p + Vector((float(rng.normal(0, 0.03)), 0, float(rng.normal(0, 0.03)))))
    for k in range(18):
        v = float(rng.uniform(-650, -40))
        dust.append(Vector((X(float(rng.uniform(SHELL_L(v), SHELL_R(v))) * 1.2), 0, Z(v))))
    for b, t, _ in spike_beams():
        for f in rng.uniform(0.3, 0.95, 2):
            dust.append(Vector(b).lerp(Vector(t), float(f)) + Vector((0, 0, float(rng.normal(0, 0.02)))))
    for k, p in enumerate(dust):
        size = float(rng.uniform(0.025, 0.065))
        card(f"FX_Dust{k}", fx_imgs["Twinkle"], tuple(p), (0, 0, 0), size, size, lift=0.14, strength=2.0)

    # -- the curling ribbons, as red swirl strokes
    swirl_mat = emission_material("FX_RedSwirl", fx_imgs["RedSwirl"], alpha=True)
    for i, path in enumerate(ribbon_paths()):
        strip(f"FX_Swirl{i}", path, lambda f: 0.012 + 0.035 * math.sin(math.pi * min(1.0, f * 1.1)) ** 0.8,
              swirl_mat, lift=0.07)

    def show_overlays(on):
        for ob, _, _, _ in overlays:
            ob.hide_render = not on

    # the bare meshes, then the sword as it looks in game: the meshes are only a faint base
    # (Config.VFX.MeshTransparency) under the energy layers
    show_overlays(False)
    shot("model_front", (0, -10, Z(-183)), (0, 0, Z(-183)), (500, 1170), ortho=X(1170))
    shot("model_star", (0.7, -2.4, 0.15), (0, 0, 0.0), (1100, 1100), lens=50)
    for name, ob in parts.items():
        if name != "Aura":
            ghost(ob, MESH_OPACITY)
    show_overlays(True)
    shot("front", (0, -10, Z(-183)), (0, 0, Z(-183)), (500, 1170), ortho=X(1170), glow=0.7)
    shot("hero", (2.2, -6.5, 0.9), (0, 0, 0.75), (900, 1400), lens=50, glow=0.7)
    shot("star_detail", (0.7, -2.4, 0.15), (0, 0, -0.06), (1100, 1100), lens=50, glow=0.7)

    # the special attack, laid out like the reference sheet: streak from the sky into a
    # starburst, a portal opening behind it, flames on the ground, darts flying out,
    # and a slash crescent sweeping past the sword
    impact = Vector((2.6, -1.0, -1.4))
    sky = Vector((-1.6, 2.5, 6.0))
    d = (impact - sky)
    painted = {"additive": False}
    card("FX_SkyStreak", fx_imgs["Streak"], tuple(sky + d / 2), tuple(-d), 3.0, d.length, **painted)
    card("FX_Portal", fx_imgs["Portal"], tuple(impact + Vector((0.4, 1.2, 1.4))), (0, 0, 0), 4.4, 4.4, **painted)
    card("FX_PortalSwirl", fx_imgs["Swirl"], tuple(impact + Vector((0.3, 0.9, 1.4))), (0, 0, 0), 5.0, 5.0,
         **painted)
    card("FX_Impact", fx_imgs["Starburst"], tuple(impact + Vector((0, -0.3, 0.3))), (0, 0, 0), 4.2, 4.2, **painted)
    card("FX_ImpactGlow", fx_imgs["Glow"], tuple(impact + Vector((0, -0.2, 0.3))), (0, 0, 0), 5.5, 5.5, **painted)
    rng = np.random.default_rng(3)
    for k in range(12):
        a = 2 * math.pi * k / 12 + float(rng.uniform(-0.2, 0.2))
        pos = impact + Vector((math.cos(a) * 1.9, math.sin(a) * 1.0, -0.15))
        size = float(rng.uniform(0.8, 1.3))
        card(f"FX_Ground{k}", fx_imgs["FireLick"], tuple(pos + Vector((0, 0, size * 0.35))), (0, 0, 0), size, size,
             uv_rect=flip_cell(int(rng.integers(2, 9))), **painted)
    for k in range(8):
        a = 2 * math.pi * k / 8 + 0.3
        dvec = Vector((math.cos(a), -0.3, math.sin(a) * 0.8 + 0.3)).normalized()
        start = impact + dvec * 1.6
        card(f"FX_Dart{k}", fx_imgs["Dart"], tuple(start + dvec * 0.55), tuple(dvec), 0.35, 1.1, **painted)
    card("FX_Crescent", fx_imgs["Crescent"], (0.6, -0.8, 1.6), (0, 0, 0), 4.6, 4.6, **painted)
    shot("vfx_special", (3.2, -11.5, 1.8), (1.0, 0, 0.4), (1400, 1000), lens=38, glow=0.55)


def main(render=False):
    clean_scene()
    parts = build_sword()
    imgs = textures()
    for name, mat in materials(imgs).items():
        set_material(parts[name], mat)
    carriers = build_vfx_carriers()
    marks = [marker("Mark_O", (0, 0, 0)), marker("Mark_Y", (0, 1, 0)), marker("Mark_Z", (0, 0, 1))]
    export(list(parts.values()) + marks, "StarburstSword")
    for m in marks:
        bpy.data.objects.remove(m)
    export(list(carriers.values()), "StarburstVFX")
    info = layout(parts)
    print(f"sword: {sum(p['verts'] for p in info['parts'].values())} vertices, "
          f"{sum(p['tris'] for p in info['parts'].values())} triangles")
    for k, p in info["parts"].items():
        print(f"  {k:11s} {p['verts']:6d} verts {p['tris']:6d} tris")
    for img in bpy.data.images:
        if img.filepath_raw and not img.packed_file and os.path.exists(bpy.path.abspath(img.filepath_raw)):
            img.pack()
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(EXPORT, "StarburstSword.blend"), compress=True)
    if render:
        render_previews(parts, carriers)


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    main(render="--render" in argv)
