"""
Crimson Reaper scythe - Blender build script.

Recreates the crimson crystal scythe from the reference sheet: a faceted crimson
crystal blade growing out of a black gothic metal spine, a layered armoured head
round a glowing crystal core, a long fluted black shaft with crystal nodes, hanging
crystal pendants and a crystal-claw pommel. The red / black aura (energy ribbons,
smoke, floating shards, drips, glow) is built as separate objects.

Every outline was measured from the reference's front view:
    u = pixels across (right +, shaft axis at 0), v = pixels down (core at v = 100)

Run it either way:
  * Blender: Scripting tab > Open > build_scythe.py > Run Script (starts a new scene)
  * Headless: python build_scythe.py [--render] [--shots=front,angle]   (with the `bpy` module installed)

Writes ../export (Scythe.fbx/.glb, ScytheAura.fbx/.glb, ScytheVFX.fbx/.glb, .blend,
scythe_layout.json, mesh_report.json), ../textures and ../previews.

Units are Roblox studs (0.01 studs per reference pixel, 7 studs long).
Axes: shaft along Z, blade sweeping to -X, flat of the blade facing -Y (the front view).
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
    if "__file__" in globals():
        return os.path.dirname(os.path.abspath(__file__))
    try:
        txt = bpy.context.space_data.text
        if txt and txt.filepath:
            return os.path.dirname(bpy.path.abspath(txt.filepath))
    except AttributeError:
        pass
    return os.getcwd()


HERE = _script_dir()
sys.path.insert(0, HERE)
import scythe_textures as st  # noqa: E402

ROOT = os.path.normpath(os.path.join(HERE, ".."))
EXPORT = os.path.join(ROOT, "export")
TEXTURES = os.path.join(ROOT, "textures")
PREVIEWS = os.path.join(ROOT, "previews")

S = 0.01                         # studs per reference pixel
V0 = 100                         # reference row of the origin (the core's height)
Y = Vector((0, 1, 0))


def P(u, v, y=0.0):
    """Reference pixel (u across, v down) to Blender studs."""
    return Vector((u * S, y, (V0 - v) * S))


def dir_xz(deg):
    """Unit vector in the front view's plane, `deg` anticlockwise from +X (as seen from the front)."""
    a = math.radians(deg)
    return Vector((math.cos(a), 0, math.sin(a)))


# ---------------------------------------------------------------- measurements (reference pixels)

CORE = (22, 100)                 # the glowing crystal core
CORE_R = 13
BEZEL_R = 15.5

# blade: top of the crystal (under the metal spine) and the cutting edge, root to tip
BLADE_TOP = [(-6, 86), (-28, 88), (-53, 92), (-78, 98), (-101, 106), (-121, 120), (-138, 138),
             (-151, 160), (-161, 185), (-168, 212), (-173, 245)]
BLADE_EDGE = [(-6, 126), (-28, 126), (-53, 123), (-78, 127), (-98, 134), (-118, 146), (-135, 165),
              (-148, 188), (-160, 214), (-168, 233), (-173, 245)]
SPINE_END = 0.64                 # the metal spine covers the blade's top up to here (0 root .. 1 tip)

# the head's thorny arms branching out of the core's frame, as measured from the reference:
# (path through (u, v) points, base width px, crystal tip point or None)
HEAD_ARMS = [
    ([(12, 90), (4, 70), (-5, 50), (-11, 36)], 13, (-18, 12)),        # the tall top spike
    ([(30, 88), (40, 76), (50, 68)], 10, (64, 50)),                   # upper right, crystal pointing up-out
    ([(24, 86), (30, 68), (37, 52), (40, 44)], 7, None),              # thin horn behind it
    ([(36, 101), (50, 104), (60, 108)], 10, (77, 116)),               # right, crystal pointing out
    ([(33, 112), (42, 124), (49, 136), (53, 146)], 8, None),          # lower right (a crystal hangs off it)
    ([(10, 114), (-2, 122), (-14, 127), (-24, 128)], 7, None),        # lower left (a crystal hangs off it)
    ([(9, 92), (-4, 82), (-18, 76), (-30, 74)], 10, None),            # over the blade's root
    ([(18, 86), (14, 72), (16, 58)], 6, None),                        # small horn between the top spikes
]
# armour scales layered round the core between the arms: (angle, length px, width px, bend, -1 front / +1 back)
HEAD_PLATES = [(95, 22, 11, 0.3, -1), (35, 20, 10, 0.3, -1), (-15, 20, 10, 0.25, -1), (-65, 18, 10, 0.25, -1),
               (150, 22, 11, 0.2, -1), (-120, 16, 9, 0.2, -1),
               (120, 24, 12, -0.3, 1), (65, 22, 11, -0.3, 1), (10, 22, 10, -0.25, 1), (-40, 20, 10, -0.25, 1),
               (-90, 18, 10, -0.2, 1), (175, 22, 11, -0.2, 1)]

NECK = [(10, 114), (4, 134), (0, 160), (0, 302)]
CROWNS = [(168, 13), (210, 19), (252, 17), (292, 11)]          # (v, thorn length px)
# crystal nodes along the shaft: (centre v, half length px, radius px, thorn length px)
NODES = [(320, 18, 5.0, 8), (418, 21, 5.0, 10), (520, 15, 4.5, 7), (584, 14, 5.2, 14), (612, 12, 5.0, 12)]
SHAFT_R = 5.0
BARBS = [358, 380, 456, 484, 552]                             # small thorn rings on the long shaft runs
POMMEL_V = 626
POMMEL_TIP = 720
# hanging crystals: (anchor u, anchor v, crystal top v, crystal length px, radius px)
PENDANTS = [(-23, 130, 152, 40, 6.0), (52, 146, 164, 40, 6.0), (18, 256, 264, 32, 5.0)]
GRIP_V = 540
# aura strands spiralling up the shaft: (start v, end v, turns, phase, base radius, bulge, max width)
SPIRALS = [(712, 215, 1.0, -0.35, 0.16, 0.5, 0.3), (690, 250, 1.15, 2.9, 0.1, 0.3, 0.1),
           (720, 600, 0.9, 1.2, 0.08, 0.16, 0.07)]
# aura flares sweeping off the blade's back: (lift studs, max width, start t, end t, depth offset)
FLARES = [(0.12, 0.13, 0.0, 0.95, -0.04), (0.26, 0.17, 0.05, 0.8, 0.05), (0.42, 0.11, 0.1, 0.6, -0.06),
          (0.2, 0.09, 0.3, 1.0, 0.07)]


# ---------------------------------------------------------------- mesh builder


class MB:
    def __init__(self):
        self.v, self.f, self.uv, self.smooth = [], [], [], []

    def add(self, p, uv=(0.0, 0.0)):
        self.v.append(tuple(p))
        self.uv.append(tuple(uv))
        return len(self.v) - 1

    def face(self, idx, smooth=False):
        self.f.append(tuple(idx))
        self.smooth.append(smooth)

    def newell(self, idx):
        n = Vector()
        for i in range(len(idx)):
            p, q = Vector(self.v[idx[i]]), Vector(self.v[idx[(i + 1) % len(idx)]])
            n += Vector(((p.y - q.y) * (p.z + q.z), (p.z - q.z) * (p.x + q.x), (p.x - q.x) * (p.y + q.y)))
        return n

    def out_face(self, idx, centre, smooth=False):
        """Add a face, wound so its normal points away from `centre`."""
        mid = sum((Vector(self.v[i]) for i in idx), Vector()) / len(idx)
        if self.newell(idx).dot(mid - Vector(centre)) < 0:
            idx = list(reversed(idx))
        self.face(idx, smooth)

    def to_object(self, name):
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
        return ob


def frame(axis, wide=None):
    """Two unit vectors perpendicular to `axis`; the first leans towards `wide` when given."""
    a = Vector(axis).normalized()
    ref = Vector(wide) if wide is not None else (Y if abs(a.y) < 0.9 else Vector((1, 0, 0)))
    s1 = ref - a * ref.dot(a)
    if s1.length < 1e-6:
        s1 = a.orthogonal()
    s1.normalize()
    return s1, a.cross(s1).normalized()


def ring_pts(centre, s1, s2, radii, rot=0.0, flat=1.0):
    m = len(radii)
    return [centre + (s1 * math.cos(rot + 2 * math.pi * j / m) + s2 * math.sin(rot + 2 * math.pi * j / m) * flat)
            * radii[j] for j in range(m)]


def loft(mb, rings, uv_v=None, tri=False, smooth=False, uv_u=1.0):
    """Skin rings (lists of points, equal length; a one-point list is an apex) into a closed solid.
    tri=True splits quads into triangles with alternating diagonals (crisp crystal facets)."""
    rings = [r for k, r in enumerate(rings) if not (len(r) == 1 and k and len(rings[k - 1]) == 1)]
    n = len(rings)
    idx = []
    for k, ring in enumerate(rings):
        vv = uv_v[k] if uv_v else k / (n - 1)
        if len(ring) == 1:
            idx.append([mb.add(ring[0], (0.5 * uv_u, vv))])
        else:
            idx.append([mb.add(p, (j / len(ring) * uv_u, vv)) for j, p in enumerate(ring)])
    centres = [sum((Vector(p) for p in ring), Vector()) / len(ring) for ring in rings]
    for k in range(n - 1):
        A, B = idx[k], idx[k + 1]
        c = (centres[k] + centres[k + 1]) / 2
        if len(A) == 1 and len(B) == 1:
            continue
        if len(A) == 1:
            for j in range(len(B)):
                mb.out_face([A[0], B[j], B[(j + 1) % len(B)]], c, smooth)
        elif len(B) == 1:
            for j in range(len(A)):
                mb.out_face([A[j], A[(j + 1) % len(A)], B[0]], c, smooth)
        else:
            m = len(A)
            for j in range(m):
                a, b, cc, d = A[j], A[(j + 1) % m], B[(j + 1) % m], B[j]
                if tri:
                    if (j + k) % 2:
                        mb.out_face([a, b, cc], c, smooth)
                        mb.out_face([a, cc, d], c, smooth)
                    else:
                        mb.out_face([a, b, d], c, smooth)
                        mb.out_face([b, cc, d], c, smooth)
                else:
                    mb.out_face([a, b, cc, d], c, smooth)
    for k, nb in ((0, 1), (n - 1, n - 2)):
        ring = idx[k]
        if len(ring) > 2:
            ce = mb.add(centres[k], (0.5 * uv_u, uv_v[k] if uv_v else k / (n - 1)))
            for j in range(len(ring)):
                mb.out_face([ce, ring[j], ring[(j + 1) % len(ring)]], centres[nb], smooth)


def thorn(mb, base, direction, length, width, depth=None, wide=None, bend=None,
          stations=((0.0, 1.0), (0.45, 0.62), (0.8, 0.26)), sides=4):
    """Curved spike with a diamond (or n-gon) cross-section: `width` across `wide`, `depth` the other way."""
    d = Vector(direction).normalized()
    s1, s2 = frame(d, wide)
    depth = width * 0.7 if depth is None else depth
    bend = Vector(bend) if bend is not None else Vector()
    rings = []
    for f, t in stations:
        c = Vector(base) + d * length * f + bend * length * f * f
        radii = [(width if j % 2 == 0 else depth) / 2 * t for j in range(sides)] if sides == 4 else \
            [width / 2 * t] * sides
        rings.append(ring_pts(c, s1, s2, radii))
    rings.append([Vector(base) + d * length + bend * length])
    loft(mb, rings)


def crystal(mb, base, tip, radius, rng, sides=6, body=(0.2, 0.62), jitter=0.12, flat=1.0, wide=None,
            base_point=True, rot=None):
    """Faceted crystal point: short pyramid at the base, a prism body and a long pyramid tip."""
    base, tip = Vector(base), Vector(tip)
    axis = tip - base
    s1, s2 = frame(axis, wide)
    rot = rng.uniform(0, math.pi) if rot is None else rot
    rings = [[base]] if base_point else []
    for f in body:
        radii = [radius * (1 + rng.uniform(-jitter, jitter)) for _ in range(sides)]
        rings.append(ring_pts(base + axis * f, s1, s2, radii, rot + rng.uniform(-0.12, 0.12), flat))
    rings.append([tip])
    loft(mb, rings, tri=True)


def plate(mb, pts, width_fn, thick_fn, normal_fn, uv_u=1.0):
    """Armour plate / leaf along a path: diamond cross-section (sharp side edges, a raised ridge
    on both faces), pointed where width and thickness reach 0. normal_fn(f) gives the plate's normal."""
    pts = [Vector(p) for p in pts]
    n = len(pts)
    rings = []
    for k, p in enumerate(pts):
        f = k / (n - 1)
        tan = (pts[min(n - 1, k + 1)] - pts[max(0, k - 1)]).normalized()
        nrm = Vector(normal_fn(f))
        side = nrm.cross(tan).normalized()
        nrm = tan.cross(side).normalized()
        w, t = width_fn(f), thick_fn(f)
        if w < 1e-5:
            rings.append([p])
        else:
            rings.append([p - side * w / 2, p - nrm * t, p + side * w / 2, p + nrm * t])
    loft(mb, rings, uv_u=uv_u)


def torus(mb, centre, axis, R, r, seg=8, sides=4, wide=None):
    s1, s2 = frame(axis, wide)
    a = Vector(axis).normalized()
    rings = []
    for k in range(seg):
        t = 2 * math.pi * k / seg
        c = Vector(centre) + (s1 * math.cos(t) + s2 * math.sin(t)) * R
        out = (c - Vector(centre)).normalized()
        rings.append([c + (out * math.cos(2 * math.pi * j / sides) + a * math.sin(2 * math.pi * j / sides)) * r
                      for j in range(sides)])
    idx = [[mb.add(p, (j / sides, k / seg)) for j, p in enumerate(ring)] for k, ring in enumerate(rings)]
    for k in range(seg):
        A, B = idx[k], idx[(k + 1) % seg]
        c = (sum((Vector(p) for p in rings[k]), Vector()) + sum((Vector(p) for p in rings[(k + 1) % seg]),
                                                                  Vector())) / (2 * sides)
        for j in range(sides):
            mb.out_face([A[j], A[(j + 1) % sides], B[(j + 1) % sides], B[j]], c)


def pchip(xs, ys):
    """Shape-preserving piecewise cubic through (xs, ys)."""
    n = len(xs)
    h = [xs[i + 1] - xs[i] for i in range(n - 1)]
    d = [(ys[i + 1] - ys[i]) / h[i] for i in range(n - 1)]
    m = [0.0] * n
    m[0], m[-1] = d[0], d[-1]
    for i in range(1, n - 1):
        if d[i - 1] * d[i] > 0:
            w1, w2 = 2 * h[i] + h[i - 1], h[i] + 2 * h[i - 1]
            m[i] = (w1 + w2) / (w1 / d[i - 1] + w2 / d[i])

    def f(x):
        x = min(max(x, xs[0]), xs[-1])
        i = max(0, min(n - 2, next((k for k in range(n - 1) if x <= xs[k + 1]), n - 2)))
        t = (x - xs[i]) / h[i]
        h00, h10, h01, h11 = 2 * t ** 3 - 3 * t ** 2 + 1, t ** 3 - 2 * t ** 2 + t, -2 * t ** 3 + 3 * t ** 2, t ** 3 - t ** 2
        return h00 * ys[i] + h10 * h[i] * m[i] + h01 * ys[i + 1] + h11 * h[i] * m[i + 1]
    return f


def smooth_path(pts, per=6):
    """Catmull-Rom through points."""
    pts = [Vector(p) for p in pts]
    out = []
    for i in range(len(pts) - 1):
        p0, p1 = pts[max(0, i - 1)], pts[i]
        p2, p3 = pts[i + 1], pts[min(len(pts) - 1, i + 2)]
        for k in range(per):
            t = k / per
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t +
                              (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    out.append(pts[-1])
    return out


def resample(pts, n):
    """n points evenly spaced along a polyline."""
    pts = [Vector(p) for p in pts]
    seg = [(pts[i + 1] - pts[i]).length for i in range(len(pts) - 1)]
    total = sum(seg)
    out = []
    for k in range(n):
        t = total * k / (n - 1)
        for i, s in enumerate(seg):
            if t <= s or i == len(seg) - 1:
                out.append(pts[i].lerp(pts[i + 1], min(1.0, t / s) if s > 0 else 0))
                break
            t -= s
    return out


# ---------------------------------------------------------------- blade

BLADE_ROWS = 46
BLADE_H = pchip([0, 0.25, 0.55, 0.8, 0.94, 1.0], [0.058, 0.052, 0.04, 0.026, 0.012, 0.004])   # half thickness
BLADE_F = [0.0, 0.2, 0.46, 0.74, 1.0]                                           # edge .. ridge .. top
BLADE_PROFILE = [0.0, 0.42, 1.0, 0.88, 0.62]


def blade_frame():
    """Rows along the blade: (edge point, top point, half thickness, along-direction)."""
    top = resample(smooth_path([P(u, v) for u, v in BLADE_TOP]), BLADE_ROWS)
    edge = resample(smooth_path([P(u, v) for u, v in BLADE_EDGE]), BLADE_ROWS)
    rows = []
    for k in range(BLADE_ROWS):
        t = k / (BLADE_ROWS - 1)
        mid_a = (top[max(0, k - 1)] + edge[max(0, k - 1)]) / 2
        mid_b = (top[min(BLADE_ROWS - 1, k + 1)] + edge[min(BLADE_ROWS - 1, k + 1)]) / 2
        rows.append((edge[k], top[k], BLADE_H(t), (mid_b - mid_a).normalized()))
    return rows


def blade_at(rows, t):
    x = t * (len(rows) - 1)
    k = min(len(rows) - 2, int(x))
    f = x - k
    a, b = rows[k], rows[k + 1]
    return a[0].lerp(b[0], f), a[1].lerp(b[1], f), a[2] * (1 - f) + b[2] * f, a[3].lerp(b[3], f).normalized()


def build_blade(blade, glow, metal, rng):
    rows = blade_frame()
    rings = []
    for k, (E, T, h, _) in enumerate(rows[:-1]):
        jit = [0, rng.uniform(-0.04, 0.04), rng.uniform(-0.07, 0.07), rng.uniform(-0.05, 0.05), 0]
        hj = [0] + [1 + rng.uniform(-0.14, 0.14) for _ in range(4)]
        across = T - E
        front, back = [], []
        for j in range(1, 5):
            p = E + across * min(1.0, BLADE_F[j] + jit[j])
            hh = h * BLADE_PROFILE[j] * hj[j]
            front.append(p - Y * hh)
            back.append(p + Y * hh)
        rings.append([E] + front + list(reversed(back)))
    rings.append([rows[-1][0]])
    loft(blade, rings, uv_v=[k / (BLADE_ROWS - 1) * 2.4 for k in range(BLADE_ROWS)], tri=True)

    # crystal growths: faceted slabs pushing out of both faces, swept towards the tip
    for t, f, ln, rad in [(0.08, 0.6, 28, 6.0), (0.2, 0.42, 24, 5.0), (0.33, 0.62, 22, 4.6), (0.46, 0.45, 20, 4.2),
                          (0.58, 0.58, 16, 3.6)]:
        E, T, h, along = blade_at(rows, t)
        across = (T - E).normalized()
        for sgn in (-1, 1):
            base = E + (T - E) * f + Y * sgn * h * 0.45
            d = (along * 0.92 + across * rng.uniform(0.05, 0.22) + Y * sgn * 0.22).normalized()
            crystal(blade, base, base + d * ln * S, rad * S, rng, sides=5, body=(0.12, 0.5), flat=0.38,
                    wide=across, rot=0.0)

    # jagged crystal shards breaking out of the top, past the spine and between its barbs
    for t, ln, rad in [(0.11, 26, 5.0), (0.24, 28, 5.0), (0.37, 24, 4.5), (0.5, 20, 4.0), (0.62, 15, 3.4)]:
        E, T, h, along = blade_at(rows, t)
        across = (T - E).normalized()
        d = (across * 0.7 + along * 0.72).normalized()
        base = T - across * 4 * S
        crystal(blade, base, base + d * ln * S, rad * S, rng, sides=5, body=(0.15, 0.45), flat=0.6, wide=along,
                rot=0.0)

    # bright line along the cutting edge
    pts = [rows[k][0] for k in range(1, BLADE_ROWS - 1)]
    n = len(pts)
    edge_rings = []
    for k, p in enumerate(pts):
        f = k / (n - 1)
        tan = (pts[min(n - 1, k + 1)] - pts[max(0, k - 1)]).normalized()
        s1, s2 = frame(tan, Y)
        r = 0.0065 * (1 - 0.6 * f)
        edge_rings.append(ring_pts(p, s1, s2, [r] * 4, math.pi / 4))
    edge_rings = [[pts[0] - (pts[1] - pts[0]) * 0.5]] + edge_rings + [[rows[-1][0]]]
    loft(glow, edge_rings)

    # black metal spine capping the crystal's top, with barbs swept towards the tip
    k_end = int(SPINE_END * (BLADE_ROWS - 1))
    path = []
    for k in range(k_end + 1):
        E, T, h, _ = rows[k]
        path.append(T + (T - E).normalized() * 4 * S)
    path = [P(4, 84)] + path
    m = len(path)
    plate(metal, path, lambda f: 17 * S * (1 - f) ** 0.7 if f < 1 else 0,
          lambda f: (0.046 * (1 - f) + 0.012 * f) if f < 1 else 0, lambda f: Y)
    for t, ln, w in [(0.04, 30, 9), (0.17, 28, 8), (0.3, 25, 7.5), (0.43, 20, 6.5), (0.55, 14, 5)]:
        E, T, h, along = blade_at(rows, t)
        across = (T - E).normalized()
        base = T + across * 7 * S
        thorn(metal, base, across * 0.7 + along * 0.72, ln * S, w * S, 4 * S, wide=along,
              bend=across * 0.15)

    # armour plates gripping the blade root on both faces: the crystal grows out of the metal
    for sgn in (-1, 1):
        E0, T0, h0, _ = rows[0]
        pts = []
        for f in np.linspace(0, 1, 9):
            E, T, h, _ = blade_at(rows, 0.22 * f)
            pts.append((E + T) / 2 + Y * sgn * (h * 0.9 + 1.5 * S))
        pts = [P(10, 104, sgn * 4 * S)] + pts
        plate(metal, pts, lambda f: 34 * S * math.sin(math.pi * min(1, 0.15 + f * 0.85)) ** 0.6 * (1 - f) ** 0.5,
              lambda f: 2.6 * S * (1 - f) + 0.5 * S, lambda f: Y)
        # a ridge of small thorns along the plate
        for f in (0.3, 0.6):
            E, T, h, along = blade_at(rows, 0.22 * f)
            base = (E + T) / 2 + Y * sgn * (h + 2.5 * S)
            thorn(metal, base, along * 0.6 + Y * sgn * 0.8, 10 * S, 4 * S, wide=along)
    return rows


# ---------------------------------------------------------------- head

def build_head(core, glow, metal, cryst, rng):
    C = P(*CORE)
    # faceted core gem (front-back flattened) and its inner glow
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=2, radius=CORE_R * S)
    for v in bm.verts:
        v.co.y *= 0.72
        v.co *= 1 + rng.uniform(-0.05, 0.05)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    base = len(core.v)
    for v in bm.verts:
        n = v.co.normalized()
        core.add(C + v.co, (0.5 + n.x * 0.5, 0.5 + n.z * 0.5))
    for f in bm.faces:
        core.out_face([base + v.index for v in f.verts], C)
    bm.free()
    rings = [[C + Vector((0, 0, 1)) * 8.5 * S]]
    for k in range(1, 6):
        a = math.pi * k / 6
        rings.append(ring_pts(C + Vector((0, 0, math.cos(a))) * 8.5 * S, Vector((1, 0, 0)), Y,
                              [math.sin(a) * 8.5 * S] * 10, flat=0.7))
    rings.append([C - Vector((0, 0, 1)) * 8.5 * S])
    loft(glow, rings)

    # bezel and the prongs holding the gem
    torus(metal, C, Y, BEZEL_R * S, 2.8 * S, seg=28, sides=6)
    for sgn in (-1, 1):
        for k in range(6):
            a = 30 + 60 * k
            d = dir_xz(a)
            thorn(metal, C + d * BEZEL_R * S + Y * sgn * 2 * S, -d + Y * sgn * 0.55, 7.5 * S, 3.5 * S, 2 * S,
                  wide=dir_xz(a + 90))

    # an angular outer frame behind the bezel, bristling with short spikes front and back
    torus(metal, C, Y, (BEZEL_R + 4.5) * S, 3.6 * S, seg=8, sides=4)
    for k in range(10):
        a = 18 + 36 * k
        d = dir_xz(a)
        for sgn in (-1, 1):
            thorn(metal, C + d * (BEZEL_R + 5) * S + Y * sgn * 2.5 * S, d + Y * sgn * 0.35, 11 * S, 4 * S,
                  wide=dir_xz(a + 90))

    # thorny arms branching out of the frame, the big ones ending in crystal points
    for pts_px, w, tip in HEAD_ARMS:
        pts = smooth_path([P(u, v) for u, v in pts_px], 4)
        n = len(pts)
        plate(metal, pts, lambda f, w=w: w * S * (1 - 0.72 * f) if f < 1 else 0,
              lambda f, w=w: w * 0.42 * S * (1 - 0.6 * f) if f < 1 else 0, lambda f: Y)
        # thorns along the outer side, swept towards the arm's end
        for f in (0.38, 0.68):
            k = int(f * (n - 1))
            p = pts[k]
            tan = (pts[min(n - 1, k + 1)] - pts[max(0, k - 1)]).normalized()
            out = Y.cross(tan).normalized()
            if out.dot(p - C) < 0:
                out = -out
            thorn(metal, p + out * w * 0.3 * S, out * 0.8 + tan * 0.6, w * 0.95 * S, w * 0.38 * S, wide=tan)
        if tip:
            end_p = pts[int(0.8 * (n - 1))]
            crystal(cryst, end_p, P(*tip), w * 0.42 * S, rng, sides=5, body=(0.16, 0.4), flat=0.75)
            tan = (P(*tip) - end_p).normalized()
            side = Y.cross(tan).normalized()
            for sgn in (-1, 1):                 # two short horns cradling the crystal
                thorn(metal, end_p + side * sgn * w * 0.25 * S, tan + side * sgn * 0.7, w * 0.9 * S, w * 0.3 * S,
                      wide=tan)

    # armour scales layered round the core between the arms, front and back
    for ang, ln, w, bend, layer in HEAD_PLATES:
        d, side = dir_xz(ang), dir_xz(ang + 90)
        pts = [C + d * (12 + ln * f) * S + side * bend * ln * f * f * S + Y * layer * (5 + 5 * f) * S
               for f in np.linspace(0, 1, 7)]
        tilt = Y * layer
        plate(metal, pts, lambda f, w=w: w * S * math.sin(math.pi * (0.2 + 0.8 * f)) ** 0.7 if f < 1 else 0,
              lambda f: 2.4 * S * (1 - f * 0.7) if f < 1 else 0,
              lambda f, tilt=tilt, d=d: (tilt * 0.9 - d * 0.45))

    # spikes reaching out of the front and back, so the head bristles from the side as well
    for sgn in (-1, 1):
        for a, ln in ((75, 26), (160, 22), (-35, 24), (15, 16)):
            d = dir_xz(a)
            thorn(metal, C + d * 12 * S + Y * sgn * 7 * S, d * 0.55 + Y * sgn, ln * S, 7 * S, wide=dir_xz(a + 90))

    # a crescent hook curling down beside the neck (the reference's "C" under the head)
    pts = [P(u, v) for u, v in ((4, 126), (-12, 148), (-22, 176), (-19, 204), (-7, 228))]
    pts = smooth_path(pts, 3)
    plate(metal, pts, lambda f: 10 * S * math.sin(math.pi * f) ** 0.7, lambda f: 3 * S * math.sin(math.pi * f) ** 0.4,
          lambda f: Y)
    for f in (0.3, 0.55, 0.78):
        p = resample(pts, 21)[int(f * 20)]
        thorn(metal, p, Vector((-1, 0, -0.35)), 11 * S, 4 * S, wide=Vector((0, 0, 1)))


# ---------------------------------------------------------------- shaft, nodes, pommel

def star_ring(centre, radius, points=8, inner=0.74, rot=0.0):
    radii = [radius * (1 if j % 2 == 0 else inner) for j in range(points * 2)]
    return ring_pts(centre, Vector((1, 0, 0)), Y, radii, rot)


def shaft_run(metal, v0, v1, radius=SHAFT_R, points=8):
    """Fluted black shaft from v0 down to v1, the flutes slowly twisting."""
    n = max(2, int((v1 - v0) / 6) + 1)
    rings = []
    for k in range(n):
        v = v0 + (v1 - v0) * k / (n - 1)
        rings.append(star_ring(P(0, v), radius * S, points, 0.74, v * 0.025))
    loft(metal, rings, uv_v=[(v0 + (v1 - v0) * k / (n - 1)) * 0.01 for k in range(n)])


def collar(metal, v, r, h=5.0, sides=8):
    """Flared octagonal band round the shaft."""
    rings = [ring_pts(P(0, v + dv), Vector((1, 0, 0)), Y, [rr * S] * sides, math.pi / sides)
             for dv, rr in ((-h / 2, r * 0.85), (-h / 4, r * 1.12), (h / 4, r * 1.12), (h / 2, r * 0.85))]
    loft(metal, rings)


def build_neck(metal, cryst, rng):
    path = smooth_path([P(u, v) for u, v in NECK], 5)
    rad = pchip([114, 140, 180, 240, 302], [7.5, 7.0, 6.2, 5.8, 5.4])
    rings = []
    for p in path:
        v = V0 - p.z / S
        rings.append(star_ring(p, rad(v) * S, 6, 0.8, v * 0.02))
    loft(metal, rings)
    for i, (v, ln) in enumerate(CROWNS):
        collar(metal, v, 8.0, 5.0)
        for k in range(4):
            a = math.radians(45 + 90 * k)
            radial = Vector((math.cos(a), math.sin(a), 0))
            up = 0.35 if (k + v // 40) % 2 else -0.3
            if i in (1, 2) and k % 2 == 0:
                # crystal thorns: a metal base with a crimson point growing out of it
                d = (radial + Vector((0, 0, up))).normalized()
                thorn(metal, P(0, v) + radial * 6 * S, d, ln * 0.5 * S, 6 * S, wide=Vector((0, 0, 1)))
                b = P(0, v) + radial * 6 * S + d * ln * 0.3 * S
                crystal(cryst, b, b + d * ln * 0.9 * S, 2.6 * S, rng, sides=5, body=(0.15, 0.4))
            else:
                thorn(metal, P(0, v) + radial * 6 * S, radial + Vector((0, 0, up)), ln * S, 5.5 * S,
                      wide=Vector((0, 0, 1)), bend=Vector((0, 0, up * 0.3)))


def build_node(metal, cryst, v, h, r, spike, rng):
    collar(metal, v - h, r + 1.5, 5.0)
    collar(metal, v + h, r + 1.5, 5.0)
    # a long pointed diamond crystal, its ends sunk into the collars
    rings = [[P(0, v + h + 1.5)]]
    for f in (0.42, 0.58):
        radii = [r * S * (1 + rng.uniform(-0.08, 0.08)) for _ in range(6)]
        rings.append(ring_pts(P(0, v + h - 2 * h * f), Vector((1, 0, 0)), Y, radii, 0.3))
    rings.append([P(0, v - h - 1.5)])
    loft(cryst, rings, tri=True)
    # cage of four curved prongs hugging the crystal, each with a thorn at its widest point
    for k in range(4):
        a = math.radians(45 + 90 * k)
        radial = Vector((math.cos(a), math.sin(a), 0))
        tang = Vector((-math.sin(a), math.cos(a), 0))
        pts = [P(0, v - h + 2 * h * f) + radial * (r * 0.9 + 0.6 + r * 0.45 * math.sin(math.pi * f) ** 1.5) * S
               for f in np.linspace(0, 1, 9)]
        plate(metal, pts, lambda f: 3.6 * S * (0.4 + 0.6 * math.sin(math.pi * f)), lambda f: 1.3 * S,
              lambda f, radial=radial: radial)
        apex = P(0, v) + radial * (r * 0.9 + 0.6 + r * 0.45) * S
        thorn(metal, apex, radial + Vector((0, 0, 0.3)), spike * S, 4 * S, wide=tang)


def build_shaft(metal, cryst, rng):
    build_neck(metal, cryst, rng)
    edges = [302]
    for v, h, r, spike in NODES:
        build_node(metal, cryst, v, h, r, spike, rng)
        edges += [v - h, v + h]
    edges.append(POMMEL_V)
    for a, b in zip(edges[0::2], edges[1::2]):
        if b - a > 2:
            shaft_run(metal, a - 1, b + 1)
    for v in BARBS:
        collar(metal, v, 6.5, 4.0)
        for k in range(4):
            a = math.radians(45 + 90 * k)
            radial = Vector((math.cos(a), math.sin(a), 0))
            thorn(metal, P(0, v) + radial * 5 * S, radial + Vector((0, 0, -0.55)), 9 * S, 3.6 * S,
                  wide=Vector((0, 0, 1)))


def build_pommel(metal, cryst, rng):
    collar(metal, POMMEL_V, 8.5, 6.0)
    rings = [ring_pts(P(0, v), Vector((1, 0, 0)), Y, [r * S] * 8, math.pi / 8)
             for v, r in ((629, 6.5), (636, 8.5), (643, 10.5), (647, 9.0))]
    loft(metal, rings)
    for k in range(4):
        a = math.radians(45 + 90 * k)
        radial = Vector((math.cos(a), math.sin(a), 0))
        tang = Vector((-math.sin(a), math.cos(a), 0))
        # crown claws flaring out and up
        thorn(metal, P(0, 640) + radial * 8 * S, radial + Vector((0, 0, 0.25)), 26 * S, 6.5 * S, 4.5 * S,
              wide=Vector((0, 0, 1)), bend=Vector((0, 0, 0.35)))
        # side crystals angled down and out between the claws
        b = P(0, 650) + radial * 5 * S
        crystal(cryst, b, b + (radial * 0.55 + Vector((0, 0, -1))).normalized() * 30 * S, 4.6 * S, rng,
                sides=5, body=(0.15, 0.45), wide=tang)
        # small upward thorns on the collar
        thorn(metal, P(0, POMMEL_V) + radial * 7 * S, radial * 0.6 + Vector((0, 0, 1)), 10 * S, 3.5 * S, wide=tang)
    crystal(cryst, P(0, 638), P(0, POMMEL_TIP), 12 * S, rng, sides=6, body=(0.2, 0.4), jitter=0.06,
            base_point=True, rot=0.3)


def build_pendants(metal, cryst, rng):
    for au, av, top, ln, rad in PENDANTS:
        a, b = P(au, av), P(au, top)
        dist = (a - b).length
        count = max(2, round(dist / (4.4 * S)))
        for k in range(count):
            c = a.lerp(b, (k + 0.5) / count)
            axis = Vector((1, 0, 0)) if k % 2 else Y
            s1 = Vector((0, 0, 1))
            torus(metal, c, axis, 2.6 * S, 0.8 * S, seg=8, sides=4, wide=s1)
        tip = P(au, top + ln)
        rings = [[P(au, top)]]
        for f in (0.32, 0.52):
            radii = [rad * S * (1 + rng.uniform(-0.1, 0.1)) for _ in range(6)]
            rings.append(ring_pts(P(au, top + ln * f), Vector((1, 0, 0)), Y, radii, rng.uniform(0, 1)))
        rings.append([tip])
        loft(cryst, rings, tri=True)


# ---------------------------------------------------------------- the weapon

PART_ORDER = ["Shaft", "HeadArmor", "Blade", "Crystals", "Core", "Glow"]


def build_weapon():
    rng = np.random.default_rng(7)
    mbs = {name: MB() for name in PART_ORDER}
    rows = build_blade(mbs["Blade"], mbs["Glow"], mbs["HeadArmor"], rng)
    build_head(mbs["Core"], mbs["Glow"], mbs["HeadArmor"], mbs["Crystals"], rng)
    build_shaft(mbs["Shaft"], mbs["Crystals"], rng)
    build_pommel(mbs["Shaft"], mbs["Crystals"], rng)
    build_pendants(mbs["Shaft"], mbs["Crystals"], rng)
    parts = {name: mbs[name].to_object(name) for name in PART_ORDER}
    for ob in parts.values():
        clean_mesh(ob)
    return parts, rows


def clean_mesh(ob):
    """Merge exact duplicates, drop degenerate faces, make every normal point outward."""
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=1e-7)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(ob.data)
    bm.free()
    ob.data.update()


# ---------------------------------------------------------------- aura (separate objects)

def spiral_points(i, n=120, dv=(0, 0), dphase=0.0, grow=1.0, extra=0.0):
    """Centre line of aura strand i (see SPIRALS), from the pommel end up to the head."""
    v0, v1, turns, phase, r0, rmax, _ = SPIRALS[i]
    v0, v1 = v0 + dv[0], v1 + dv[1]
    pts = []
    for k in range(n):
        f = k / (n - 1)
        th = phase + dphase + 2 * math.pi * turns * f
        r = (r0 + extra + rmax * grow * math.sin(math.pi * f) ** 0.8) * (1 + 0.12 * math.sin(f * 6 + i * 2))
        pts.append(Vector((math.cos(th) * r, math.sin(th) * r, P(0, v0 + (v1 - v0) * f).z)))
    return pts


def flare_points(rows, i, n=50):
    """Centre line of aura flare i (see FLARES) sweeping off the blade's back."""
    off, _, t0, t1, ysh = FLARES[i]
    pts = []
    for k in range(n):
        t = t0 + (t1 - t0) * k / (n - 1)
        E, T, h, along = blade_at(rows, min(t, 0.99))
        lift = off * math.sin(math.pi * (k / (n - 1))) ** 0.8 + 0.02
        pts.append(T + (T - E).normalized() * lift + Y * ysh)
    return pts


def helix_ribbon(name, pts, width_fn, mat):
    """Energy ribbon spiralling up round the shaft; its face turns towards the viewer as it
    passes in front, so it reads as a band wrapping the weapon."""
    mb = MB()
    n = len(pts)
    L, R = [], []
    for k, p in enumerate(pts):
        f = k / (n - 1)
        tan = (pts[min(n - 1, k + 1)] - pts[max(0, k - 1)]).normalized()
        radial = Vector((p.x, p.y, 0)).normalized()
        wdir = radial.cross(tan).normalized()
        w = width_fn(f)
        L.append(mb.add(p - wdir * w / 2, (f, 0)))
        R.append(mb.add(p + wdir * w / 2, (f, 1)))
    for k in range(n - 1):
        mb.face([L[k], L[k + 1], R[k + 1], R[k]])
    ob = mb.to_object(name)
    set_material(ob, mat)
    return ob


def path_ribbon(name, pts, width_fn, normal_fn, mat, mb=None):
    """Flat ribbon along a path. Pass `mb` to add it to a shared mesh instead of making an object."""
    own = mb is None
    mb = mb or MB()
    pts = [Vector(p) for p in pts]
    n = len(pts)
    L, R = [], []
    for k, p in enumerate(pts):
        f = k / (n - 1)
        tan = (pts[min(n - 1, k + 1)] - pts[max(0, k - 1)]).normalized()
        side = Vector(normal_fn(f, p)).cross(tan).normalized()
        w = width_fn(f)
        L.append(mb.add(p - side * w / 2, (f, 0)))
        R.append(mb.add(p + side * w / 2, (f, 1)))
    for k in range(n - 1):
        mb.face([L[k], L[k + 1], R[k + 1], R[k]])
    if not own:
        return None
    ob = mb.to_object(name)
    set_material(ob, mat)
    return ob


def crossed_card(mb, centre, width, height, uv_rect=(0, 0, 1, 1), yaw=0.0, up=None):
    """Two quads crossed at 90 degrees, so a sprite reads from every side."""
    up = Vector(up) if up is not None else Vector((0, 0, 1))
    u0, v0, du, dv = uv_rect
    for k in range(2):
        a = yaw + math.pi / 2 * k
        side = Vector((math.cos(a), math.sin(a), 0))
        side = (side - up * side.dot(up)).normalized()
        c = Vector(centre)
        q = [mb.add(c - side * width / 2 - up * height / 2, (u0, v0)), mb.add(c + side * width / 2 - up * height / 2, (u0 + du, v0)),
             mb.add(c + side * width / 2 + up * height / 2, (u0 + du, v0 + dv)), mb.add(c - side * width / 2 + up * height / 2, (u0, v0 + dv))]
        mb.face(q)


def build_aura(rows, mats):
    rng = np.random.default_rng(31)
    obs = {}
    # three energy strands spiralling up the shaft from the pommel into the head
    for i, sp in enumerate(SPIRALS):
        wmax = sp[6]
        obs[f"AuraSpiral{i + 1}"] = helix_ribbon(
            f"AuraSpiral{i + 1}", spiral_points(i), lambda f, wmax=wmax: 0.03 + wmax * math.sin(math.pi * f) ** 0.8,
            mats["Ribbon"])
        # a dark smoky strand riding just outside each energy strand
        obs[f"AuraSmokeSpiral{i + 1}"] = helix_ribbon(
            f"AuraSmokeSpiral{i + 1}", spiral_points(i, dv=(-10, 10), dphase=-0.35, grow=1.1, extra=0.03),
            lambda f, wmax=wmax: 0.05 + wmax * 1.6 * math.sin(math.pi * f) ** 0.8, mats["SmokeRibbon"])
        # a wide, faint mist under each strand gives the swirl its volume
        obs[f"AuraMist{i + 1}"] = helix_ribbon(
            f"AuraMist{i + 1}", spiral_points(i, dv=(6, -6), dphase=0.12),
            lambda f, wmax=wmax: 0.08 + wmax * 2.6 * math.sin(math.pi * f) ** 0.8, mats["Mist"])
    # strands wrapping the blade, and a flare arcing over its back
    for i in range(2):
        pts, normals = [], []
        for k in range(70):
            t = k / 69 * 0.97
            E, T, h, along = blade_at(rows, t)
            mid = (E + T) / 2
            n_in = (T - E).normalized()
            phi = math.pi * i + 2 * math.pi * 2.3 * t
            a = (T - E).length * 0.5 + 0.06 + 0.05 * math.sin(math.pi * t)
            off = n_in * math.cos(phi) * a + Y * math.sin(phi) * a
            pts.append(mid + off)
            normals.append(off.normalized())
        obs[f"AuraBladeWrap{i + 1}"] = path_ribbon(
            f"AuraBladeWrap{i + 1}", pts, lambda f: 0.025 + 0.04 * math.sin(math.pi * f),
            lambda f, p, normals=normals: normals[min(69, int(f * 69))], mats["Ribbon"])
    # flame-like flares sweeping off the blade's back towards the tip, front and back of the blade
    mb = MB()
    for i, fl in enumerate(FLARES):
        path_ribbon("", flare_points(rows, i), lambda f, w=fl[1]: w * math.sin(math.pi * f) ** 0.7, lambda f, p: Y,
                    None, mb)
    obs["AuraBladeFlares"] = mb.to_object("AuraBladeFlares")
    set_material(obs["AuraBladeFlares"], mats["Ribbon"])
    # wisps rising out of the crystal core and curling away: the energy starts at the crystal
    mb = MB()
    C = P(*CORE)
    for i, (ang, ln, curl) in enumerate(((100, 0.6, 0.7), (45, 0.5, -0.6), (-15, 0.45, 0.8), (150, 0.55, -0.5),
                                         (-70, 0.4, 0.6), (75, 0.7, -0.4))):
        pts = []
        for k in range(30):
            f = k / 29
            a = math.radians(ang) + curl * f * 1.6
            r = 0.1 + ln * f
            pts.append(C + Vector((math.cos(a) * r, (0.06 if i % 2 else -0.06) * f, math.sin(a) * r)))
        path_ribbon("", pts, lambda f: 0.02 + 0.08 * math.sin(math.pi * f) ** 0.8, lambda f, p: Y, None, mb)
    obs["AuraCoreWisps"] = mb.to_object("AuraCoreWisps")
    set_material(obs["AuraCoreWisps"], mats["Ribbon"])
    # floating crystal fragments close round the head, blade and upper shaft
    mb = MB()
    spots = []
    for k in range(18):
        if k < 7:
            c = P(*CORE) + Vector((rng.uniform(-0.45, 0.55), rng.uniform(-0.3, 0.3), rng.uniform(-0.4, 0.5)))
        elif k < 13:
            E, T, h, along = blade_at(rows, rng.uniform(0.1, 0.9))
            c = (E + T) / 2 + (E - T).normalized() * rng.uniform(0.12, 0.32) + Y * rng.uniform(-0.15, 0.15)
        else:
            c = P(0, rng.uniform(180, 520)) + Vector((rng.uniform(-0.35, 0.35), rng.uniform(-0.3, 0.3), 0))
        spots.append(c)
        d = Vector((rng.normal(), rng.normal(), rng.normal())).normalized()
        ln = rng.uniform(0.04, 0.09)
        crystal(mb, c - d * ln / 2, c + d * ln / 2, ln * 0.22, rng, sides=4, body=(0.45, 0.55), jitter=0.1)
    obs["AuraShards"] = mb.to_object("AuraShards")
    set_material(obs["AuraShards"], mats["ShardMesh"])
    # glowing sparks drifting along the swirl and round the blade
    mb = MB()
    for k in range(60):
        if k < 40:
            f = rng.uniform(0.05, 0.95)
            th = -0.35 + 2 * math.pi * f
            r = (0.16 + 0.5 * math.sin(math.pi * f) ** 0.8) * rng.uniform(0.8, 1.25)
            c = Vector((math.cos(th) * r, math.sin(th) * r, P(0, 712 + (215 - 712) * f).z + rng.uniform(-0.1, 0.1)))
        else:
            E, T, h, along = blade_at(rows, rng.uniform(0.05, 0.95))
            c = (E + T) / 2 + (T - E).normalized() * rng.uniform(0.1, 0.5) + Y * rng.uniform(-0.1, 0.1)
        sz = rng.uniform(0.025, 0.06)
        crossed_card(mb, c, sz, sz, yaw=rng.uniform(0, 3))
    obs["AuraSparks"] = mb.to_object("AuraSparks")
    set_material(obs["AuraSparks"], mats["Spark"])
    # dark red / black smoke hugging the head, blade root and pommel
    mb = MB()
    for k in range(14):
        if k < 6:
            c = P(*CORE) + Vector((rng.uniform(-0.6, 0.5), 0, rng.uniform(-0.45, 0.4)))
        elif k < 10:
            E, T, h, along = blade_at(rows, rng.uniform(0.1, 0.7))
            c = (E + T) / 2 + (E - T).normalized() * 0.12
        else:
            c = P(0, rng.uniform(600, 700)) + Vector((rng.uniform(-0.2, 0.2), 0, 0))
        cell = int(rng.integers(0, 8))
        size = rng.uniform(0.35, 0.6)
        crossed_card(mb, c, size, size, (cell % 4 * 0.25, 0.75 - cell // 4 * 0.25, 0.25, 0.25), rng.uniform(0, 3))
    obs["AuraSmoke"] = mb.to_object("AuraSmoke")
    set_material(obs["AuraSmoke"], mats["Smoke"])
    # magical drips hanging off the blade's edge and the head
    mb = MB()
    for t in (0.18, 0.33, 0.47, 0.6, 0.74):
        E, T, h, along = blade_at(rows, t)
        ln = rng.uniform(0.12, 0.26)
        crossed_card(mb, E + Vector((0, 0, -ln / 2 + 0.01)), 0.035, ln, yaw=rng.uniform(0, 3))
    for u, v in ((-30, 128), (40, 128), (10, 300)):
        ln = rng.uniform(0.1, 0.18)
        crossed_card(mb, P(u, v) + Vector((0, 0, -ln / 2)), 0.03, ln, yaw=rng.uniform(0, 3))
    obs["AuraDrips"] = mb.to_object("AuraDrips")
    set_material(obs["AuraDrips"], mats["Drip"])
    # faint red glow round the head, along the blade and at the pommel
    mb = MB()
    crossed_card(mb, P(*CORE), 0.95, 0.95)
    E, T, h, along = blade_at(rows, 0.45)
    crossed_card(mb, (E + T) / 2, 1.1, 0.9, yaw=0.0)
    crossed_card(mb, P(0, 680), 0.45, 0.6)
    obs["AuraGlow"] = mb.to_object("AuraGlow")
    set_material(obs["AuraGlow"], mats["Glow"])
    return obs, spots


# ---------------------------------------------------------------- materials

def nodes_of(owner):
    owner.use_nodes = True
    nt = owner.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    return nt


def np_image(name, arr, path=None, colorspace="sRGB"):
    h, w = arr.shape[:2]
    img = bpy.data.images.new(name, w, h, alpha=True)
    img.colorspace_settings.name = colorspace
    img.pixels.foreach_set(np.flipud(arr).astype(np.float32).ravel())
    if path:
        img.filepath_raw = path
        img.file_format = "PNG"
        img.save()
    return img


def set_material(ob, mat):
    ob.data.materials.clear()
    ob.data.materials.append(mat)


def metal_material(name, col, mr):
    mat = bpy.data.materials.new(name)
    nt = nodes_of(mat)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    tc = nt.nodes.new("ShaderNodeTexImage")
    tc.image = col
    tm = nt.nodes.new("ShaderNodeTexImage")
    tm.image = mr
    sep = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(tc.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(tm.outputs["Color"], sep.inputs["Color"])
    nt.links.new(sep.outputs["Green"], bsdf.inputs["Roughness"])
    nt.links.new(sep.outputs["Blue"], bsdf.inputs["Metallic"])
    nt.links.new(bsdf.outputs[0], out.inputs["Surface"])
    return mat


def crystal_material(name, col, mr, glow_strength=0.9, transmission=0.45):
    """Translucent faceted crimson crystal that glows from inside. The base colour (and its alpha)
    and the metallic-roughness map are what the glTF / FBX export carries to Roblox."""
    mat = bpy.data.materials.new(name)
    nt = nodes_of(mat)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    tc = nt.nodes.new("ShaderNodeTexImage")
    tc.image = col
    tm = nt.nodes.new("ShaderNodeTexImage")
    tm.image = mr
    sep = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(tc.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(tm.outputs["Color"], sep.inputs["Color"])
    nt.links.new(sep.outputs["Green"], bsdf.inputs["Roughness"])
    nt.links.new(sep.outputs["Blue"], bsdf.inputs["Metallic"])
    nt.links.new(tc.outputs["Color"], bsdf.inputs["Emission Color"])
    bsdf.inputs["Emission Strength"].default_value = glow_strength
    bsdf.inputs["Transmission Weight"].default_value = transmission
    bsdf.inputs["IOR"].default_value = 1.6
    bsdf.inputs["Coat Weight"].default_value = 0.12
    nt.links.new(bsdf.outputs[0], out.inputs["Surface"])
    return mat


def glow_material(name, colour, strength):
    mat = bpy.data.materials.new(name)
    nt = nodes_of(mat)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (*colour, 1)
    bsdf.inputs["Emission Color"].default_value = (*colour, 1)
    bsdf.inputs["Emission Strength"].default_value = strength
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(bsdf.outputs[0], out.inputs["Surface"])
    return mat


def fx_material(name, image, strength=1.0, additive=True, uv_rect=None):
    """Effect material: Principled base colour + alpha carries the texture to exporters;
    the surface itself adds light (additive) or covers what is behind (alpha-blended smoke)."""
    mat = bpy.data.materials.new(name)
    nt = nodes_of(mat)
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = image
    if uv_rect is not None:
        tc = nt.nodes.new("ShaderNodeTexCoord")
        mp = nt.nodes.new("ShaderNodeMapping")
        mp.inputs["Location"].default_value = (uv_rect[0], uv_rect[1], 0)
        mp.inputs["Scale"].default_value = (uv_rect[2], uv_rect[3], 1)
        nt.links.new(tc.outputs["UV"], mp.inputs["Vector"])
        nt.links.new(mp.outputs["Vector"], tex.inputs["Vector"])
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    if additive:
        em = nt.nodes.new("ShaderNodeEmission")
        mul = nt.nodes.new("ShaderNodeMath")
        mul.operation = "MULTIPLY"
        nt.links.new(tex.outputs["Color"], em.inputs["Color"])
        nt.links.new(tex.outputs["Alpha"], mul.inputs[0])
        mul.inputs[1].default_value = strength
        nt.links.new(mul.outputs[0], em.inputs["Strength"])
        add = nt.nodes.new("ShaderNodeAddShader")
        nt.links.new(tr.outputs[0], add.inputs[0])
        nt.links.new(em.outputs[0], add.inputs[1])
        nt.links.new(add.outputs[0], out.inputs["Surface"])
    else:
        em = nt.nodes.new("ShaderNodeEmission")
        nt.links.new(tex.outputs["Color"], em.inputs["Color"])
        em.inputs["Strength"].default_value = strength
        mx = nt.nodes.new("ShaderNodeMixShader")
        nt.links.new(tex.outputs["Alpha"], mx.inputs[0])
        nt.links.new(tr.outputs[0], mx.inputs[1])
        nt.links.new(em.outputs[0], mx.inputs[2])
        nt.links.new(mx.outputs[0], out.inputs["Surface"])
    return mat


def textures():
    os.makedirs(TEXTURES, exist_ok=True)

    def save(name, arr, colorspace="sRGB"):
        return np_image(name, arr, os.path.join(TEXTURES, name + ".png"), colorspace)
    imgs = {
        "crystal": save("crystal_color", st.crystal()),
        "crystal_mr": save("crystal_mr", st.crystal_mr(), "Non-Color"),
        "metal": save("metal_color", st.metal()),
        "metal_mr": save("metal_mr", st.metal_mr(), "Non-Color"),
    }
    for key, fn in st.AURA.items():
        imgs["fx_" + key] = save("fx_" + key.lower(), fn())
    return imgs


def materials(imgs):
    return {
        "Shaft": metal_material("DarkMetal", imgs["metal"], imgs["metal_mr"]),
        "HeadArmor": None,
        "Blade": crystal_material("CrimsonCrystal", imgs["crystal"], imgs["crystal_mr"]),
        "Crystals": None,
        "Core": crystal_material("CoreCrystal", imgs["crystal"], imgs["crystal_mr"], glow_strength=2.2,
                                 transmission=0.3),
        "Glow": glow_material("CrimsonGlow", (1.0, 0.05, 0.08), 8.0),
        "Ribbon": fx_material("AuraRibbon", imgs["fx_Ribbon"], 2.6),
        "SmokeRibbon": fx_material("AuraSmokeRibbon", imgs["fx_SmokeRibbon"], 1.0, additive=False),
        "Mist": fx_material("AuraMist", imgs["fx_Ribbon"], 0.7),
        "Spark": fx_material("AuraSpark", imgs["fx_Spark"], 3.0),
        "Smoke": fx_material("AuraSmoke", imgs["fx_Smoke"], 1.0, additive=False),
        "Drip": fx_material("AuraDrip", imgs["fx_Drip"], 2.0),
        "Glow2": fx_material("AuraGlow", imgs["fx_Glow"], 0.9),
        "ShardMesh": glow_material("AuraShardGlow", (1.0, 0.07, 0.1), 5.0),
    }


# ---------------------------------------------------------------- integrity checks + export

def components(ob):
    """Connected pieces of a mesh, as (vertex index set, bbox min, bbox max)."""
    me = ob.data
    parent = list(range(len(me.vertices)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for e in me.edges:
        a, b = find(e.vertices[0]), find(e.vertices[1])
        if a != b:
            parent[a] = b
    groups = {}
    for i in range(len(me.vertices)):
        groups.setdefault(find(i), []).append(i)
    out = []
    for g in groups.values():
        cs = np.array([me.vertices[i].co[:] for i in g])
        out.append((g, cs.min(axis=0), cs.max(axis=0)))
    return out


def mesh_report(parts):
    """Normals, manifoldness, degenerate faces, transforms and floating pieces, per part."""
    report = {"parts": {}, "floatingPieces": 0}
    pieces = []
    for name, ob in parts.items():
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        non_manifold = sum(1 for e in bm.edges if not e.is_manifold)
        loose = sum(1 for v in bm.verts if not v.link_edges)
        zero = sum(1 for f in bm.faces if f.calc_area() < 1e-10)
        # outward normals: signed volume of each closed piece must be positive
        bm.free()
        comps = components(ob)
        inverted = 0
        me = ob.data
        vol_by_comp = {}
        lookup = {}
        for ci, (g, _, _) in enumerate(comps):
            for i in g:
                lookup[i] = ci
        for poly in me.polygons:
            vs = [me.vertices[i].co for i in poly.vertices]
            for k in range(1, len(vs) - 1):
                vol_by_comp[lookup[poly.vertices[0]]] = vol_by_comp.get(lookup[poly.vertices[0]], 0.0) + \
                    vs[0].dot(vs[k].cross(vs[k + 1])) / 6
        inverted = sum(1 for v in vol_by_comp.values() if v < 0)
        report["parts"][name] = {
            "verts": len(me.vertices), "tris": sum(len(p.vertices) - 2 for p in me.polygons),
            "pieces": len(comps), "nonManifoldEdges": non_manifold, "looseVerts": loose,
            "zeroAreaFaces": zero, "invertedPieces": inverted,
            "transformApplied": ob.matrix_world == Matrix.Identity(4),
        }
        pieces += [(name, lo, hi) for _, lo, hi in comps]
    # a piece is floating when its bounding box touches no other piece's
    pad = 0.004
    for i, (name, lo, hi) in enumerate(pieces):
        touching = any(np.all(lo - pad <= hi2) and np.all(lo2 - pad <= hi) for j, (_, lo2, hi2) in enumerate(pieces)
                       if j != i)
        if not touching:
            report["floatingPieces"] += 1
            report.setdefault("floating", []).append({"part": name, "centre": ((lo + hi) / 2).round(3).tolist()})
    report["totalTris"] = sum(p["tris"] for p in report["parts"].values())
    lo = np.min([p[1] for p in pieces], axis=0)
    hi = np.max([p[2] for p in pieces], axis=0)
    report["size"] = (hi - lo).round(3).tolist()
    return report


def marker(name, pos):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=0.02)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    ob.location = pos
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.update()
    me.transform(ob.matrix_world)
    ob.matrix_world = Matrix.Identity(4)
    return ob


def build_vfx_carriers(imgs):
    """One tiny quad per effect texture, so the Roblox importer uploads them for the installer."""
    out = {}
    for i, key in enumerate(st.AURA):
        mb = MB()
        x = 3.0 + 0.3 * i
        q = [mb.add((x, 0, 0), (0, 0)), mb.add((x + 0.2, 0, 0), (1, 0)), mb.add((x + 0.2, 0, 0.2), (1, 1)),
             mb.add((x, 0, 0.2), (0, 1))]
        mb.face(q)
        ob = mb.to_object(f"Tex_{key}")
        mat = bpy.data.materials.new(f"Tex_{key}")
        nt = nodes_of(mat)
        bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = imgs["fx_" + key]
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        nt.links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
        out_n = nt.nodes.new("ShaderNodeOutputMaterial")
        nt.links.new(bsdf.outputs[0], out_n.inputs["Surface"])
        set_material(ob, mat)
        out[key] = ob
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


def layout(rows, report, spots):
    """Points the Roblox installer and effects script need (Blender studs)."""
    top = [list(map(lambda c: round(c, 4), r[1])) for r in rows[::3]] + [list(map(lambda c: round(c, 4), rows[-1][1]))]
    edge = [list(map(lambda c: round(c, 4), r[0])) for r in rows[::3]] + [list(map(lambda c: round(c, 4), rows[-1][0]))]
    info = {
        "units": "studs", "studsPerPixel": S,
        "points": {
            "Core": list(P(*CORE)), "Grip": list(P(0, GRIP_V)), "ShaftTop": list(P(0, 130)),
            "ShaftBottom": list(P(0, POMMEL_V)), "PommelTip": list(P(0, POMMEL_TIP)),
            "BladeRoot": [round(c, 4) for c in (rows[2][0] + rows[2][1]) / 2],
            "BladeTip": [round(c, 4) for c in rows[-1][0]],
            "BladeMid": [round(c, 4) for c in (rows[len(rows) // 2][0] + rows[len(rows) // 2][1]) / 2],
        },
        "bladeTop": top, "bladeEdge": edge,
        "spirals": [[[round(c, 4) for c in p] for p in spiral_points(i, 41)] for i in range(len(SPIRALS))],
        "spiralWidths": [sp[6] for sp in SPIRALS],
        "flares": [[[round(c, 4) for c in p] for p in flare_points(rows, i, 13)] for i in range(len(FLARES))],
        "flareWidths": [fl[1] for fl in FLARES],
        "shardSpots": [[round(c, 4) for c in p] for p in spots],
        "meshReport": report,
    }
    with open(os.path.join(EXPORT, "scythe_layout.json"), "w") as f:
        json.dump(info, f, indent=1)
    return info


def clean_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.unit_settings.system = "NONE"


# ---------------------------------------------------------------- previews

def _blur(img, sigma):
    h, w = img.shape
    fy = np.fft.fftfreq(h)[:, None]
    fx = np.fft.fftfreq(w)[None, :]
    k = np.exp(-2 * (math.pi * sigma) ** 2 * (fx * fx + fy * fy))
    return np.real(np.fft.ifft2(np.fft.fft2(img) * k))


def bloom(path, strength=0.6, threshold=0.55):
    img = bpy.data.images.load(path, check_existing=False)
    w, h = img.size
    a = np.array(img.pixels[:], np.float32).reshape(h, w, 4)[..., :3]
    lum = a.max(axis=2, keepdims=True)
    bright = a * np.clip((lum - threshold) / (1 - threshold), 0, 1)
    glow = np.zeros_like(a)
    for sigma, wgt in ((3, 0.4), (10, 0.35), (30, 0.3)):
        for c in range(3):
            glow[..., c] += _blur(bright[..., c], sigma * w / 600) * wgt
    out = 1 - (1 - np.clip(a, 0, 1)) * (1 - np.clip(glow * strength, 0, 1))
    img.pixels.foreach_set(np.concatenate([out, np.ones((h, w, 1), np.float32)], axis=2).ravel())
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)


def render_previews(parts, aura, imgs, rows, only=None):
    os.makedirs(PREVIEWS, exist_ok=True)
    sc = bpy.context.scene
    sc.cycles.samples = 48
    sc.cycles.use_denoising = True
    sc.cycles.transparent_max_bounces = 64
    sc.cycles.max_bounces = 8
    sc.view_settings.view_transform = "Standard"
    world = bpy.data.worlds.new("Void")
    sc.world = world
    wnt = nodes_of(world)
    bg = wnt.nodes.new("ShaderNodeBackground")                     # what the camera sees
    bg.inputs["Color"].default_value = (0.006, 0.002, 0.003, 1)
    env = wnt.nodes.new("ShaderNodeBackground")                    # what the metal reflects: dim red light above
    coord = wnt.nodes.new("ShaderNodeTexCoord")
    sep = wnt.nodes.new("ShaderNodeSeparateXYZ")
    ramp = wnt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.35
    ramp.color_ramp.elements[0].color = (0.02, 0.0, 0.005, 1)
    ramp.color_ramp.elements[1].position = 0.8
    ramp.color_ramp.elements[1].color = (0.55, 0.16, 0.18, 1)
    mapr = wnt.nodes.new("ShaderNodeMapRange")
    mapr.inputs["From Min"].default_value = -1
    wnt.links.new(coord.outputs["Normal"], sep.inputs[0])
    wnt.links.new(sep.outputs["Z"], mapr.inputs["Value"])
    wnt.links.new(mapr.outputs["Result"], ramp.inputs["Fac"])
    wnt.links.new(ramp.outputs["Color"], env.inputs["Color"])
    env.inputs["Strength"].default_value = 0.8
    lp = wnt.nodes.new("ShaderNodeLightPath")
    mix = wnt.nodes.new("ShaderNodeMixShader")
    wnt.links.new(lp.outputs["Is Camera Ray"], mix.inputs[0])
    wnt.links.new(env.outputs[0], mix.inputs[1])
    wnt.links.new(bg.outputs[0], mix.inputs[2])
    wo = wnt.nodes.new("ShaderNodeOutputWorld")
    wnt.links.new(mix.outputs[0], wo.inputs["Surface"])

    lights = []

    def light(name, loc, energy, color, size, target=(0, 0, -1.5)):
        ld = bpy.data.lights.new(name, "AREA")
        ld.energy, ld.color, ld.size = energy, color, size
        lo = bpy.data.objects.new(name, ld)
        lo.location = loc
        lo.rotation_euler = (Vector(target) - lo.location).to_track_quat("-Z", "Y").to_euler()
        sc.collection.objects.link(lo)
        lights.append(lo)

    light("Key", (-3.5, -5, 3), 420, (1.0, 0.86, 0.86), 3)
    light("Fill", (4, -4, -2), 90, (1.0, 0.5, 0.5), 4)
    light("RimL", (-4, 5, 2), 700, (1.0, 0.12, 0.12), 3)
    light("RimR", (4, 5, -1), 600, (1.0, 0.1, 0.12), 3)
    light("Under", (0, -2, -8), 250, (1.0, 0.1, 0.1), 4)
    cam_d = bpy.data.cameras.new("Cam")
    cam = bpy.data.objects.new("Cam", cam_d)
    sc.collection.objects.link(cam)
    sc.camera = cam

    # smoke and glow are sprites in the render: turn them to the camera every shot
    sprites = [aura["AuraSmoke"], aura["AuraGlow"]]

    def shot(name, loc, target, res, ortho=None, lens=50, glow=0.6, roll=0.0):
        if only and name not in only:
            return
        cam.location = loc
        q = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y")
        cam.rotation_euler = q.to_euler()
        if roll:
            cam.rotation_euler.rotate_axis("Z", math.radians(roll))
        if ortho:
            cam_d.type, cam_d.ortho_scale = "ORTHO", ortho
        else:
            cam_d.type, cam_d.lens = "PERSP", lens
        cam_d.clip_start, cam_d.clip_end = 0.05, 100
        sc.render.resolution_x, sc.render.resolution_y = res
        path = os.path.join(PREVIEWS, name + ".png")
        sc.render.filepath = path
        bpy.ops.render.render(write_still=True)
        if glow:
            bloom(path, strength=glow)
        print("rendered", path)

    def show_aura(on):
        for ob in aura.values():
            ob.hide_render = not on

    for ob in sprites:                       # sprites are crossed cards; fine from every side
        ob.hide_render = False
    mid_z = P(0, 368).z
    cx = P(-48, 0).x
    full = (580, 1480)
    show_aura(False)
    shot("model_front", (cx, -20, mid_z), (cx, 0, mid_z), full, ortho=7.4, glow=0.45)
    shot("model_angle", (-3.2, -6.2, 0.6), (-0.2, 0, -2.4), (900, 1400), lens=42, glow=0.45)
    show_aura(True)
    shot("front", (cx, -20, mid_z), (cx, 0, mid_z), full, ortho=7.4)
    shot("back", (cx, 20, mid_z), (cx, 0, mid_z), full, ortho=7.4)
    shot("left", (-20, 0, mid_z), (0, 0, mid_z), full, ortho=7.4)
    shot("right", (20, 0, mid_z), (0, 0, mid_z), full, ortho=7.4)
    shot("angle", (-3.2, -6.2, 0.6), (-0.2, 0, -2.4), (900, 1400), lens=42)
    shot("head_closeup", (-0.9, -2.6, 0.55), (-0.25, 0, -0.05), (1100, 900), lens=50)
    E, T, h, along = blade_at(rows, 0.5)
    bm = (E + T) / 2
    shot("blade_closeup", tuple(bm + Vector((0.5, -2.2, 0.4))), tuple(bm + Vector((0.05, 0, 0))), (1100, 800), lens=50)
    shot("bottom_closeup", (0.55, -1.7, P(0, 640).z + 0.25), (0, 0, P(0, 668).z), (800, 900), lens=50)

    # in game: standing on a grey studio floor in a pool of crimson light, like the reference sheet
    if only and "ingame" not in only:
        return
    floor_z = P(0, POMMEL_TIP).z
    mb = MB()
    q = [mb.add((-12, -12, floor_z), (0, 0)), mb.add((12, -12, floor_z), (1, 0)), mb.add((12, 12, floor_z), (1, 1)),
         mb.add((-12, 12, floor_z), (0, 1))]
    mb.face(q)
    floor = mb.to_object("Floor")
    fm = bpy.data.materials.new("Floor")
    fnt = nodes_of(fm)
    fb = fnt.nodes.new("ShaderNodeBsdfPrincipled")
    fb.inputs["Base Color"].default_value = (0.09, 0.095, 0.11, 1)
    fb.inputs["Roughness"].default_value = 0.45
    checker = fnt.nodes.new("ShaderNodeTexChecker")
    checker.inputs["Scale"].default_value = 24
    checker.inputs["Color1"].default_value = (0.08, 0.085, 0.1, 1)
    checker.inputs["Color2"].default_value = (0.1, 0.105, 0.12, 1)
    fnt.links.new(checker.outputs["Color"], fb.inputs["Base Color"])
    fo = fnt.nodes.new("ShaderNodeOutputMaterial")
    fnt.links.new(fb.outputs[0], fo.inputs["Surface"])
    set_material(floor, fm)
    mb = MB()
    r = 1.3
    q = [mb.add((-r, -r, floor_z + 0.005), (0, 0)), mb.add((r, -r, floor_z + 0.005), (1, 0)),
         mb.add((r, r, floor_z + 0.005), (1, 1)), mb.add((-r, r, floor_z + 0.005), (0, 1))]
    mb.face(q)
    pool = mb.to_object("GroundGlow")
    set_material(pool, fx_material("GroundGlow", imgs["fx_GroundGlow"], 2.0))
    bg.inputs["Color"].default_value = (0.1, 0.11, 0.14, 1)
    shot("ingame", (-2.4, -8.5, -2.6), (-0.3, 0, -2.9), (900, 1300), lens=40, glow=0.5)


def main(render=False, only=None):
    clean_scene()
    parts, rows = build_weapon()
    imgs = textures()
    mats = materials(imgs)
    mats["HeadArmor"] = mats["Shaft"]
    mats["Crystals"] = mats["Blade"]
    for name in PART_ORDER:
        set_material(parts[name], mats[name])
    report = mesh_report(parts)
    aura_mats = {"Ribbon": mats["Ribbon"], "SmokeRibbon": mats["SmokeRibbon"], "Smoke": mats["Smoke"],
                 "Mist": mats["Mist"], "Spark": mats["Spark"],
                 "Drip": mats["Drip"], "Glow": mats["Glow2"], "ShardMesh": mats["ShardMesh"]}
    aura, spots = build_aura(rows, aura_mats)
    marks = [marker("Mark_O", (0, 0, 0)), marker("Mark_Y", (0, 1, 0)), marker("Mark_Z", (0, 0, 1))]
    export([parts[n] for n in PART_ORDER] + marks, "Scythe")
    for m in marks:
        bpy.data.objects.remove(m)
    export(list(aura.values()), "ScytheAura")
    carriers = build_vfx_carriers(imgs)
    export(list(carriers.values()), "ScytheVFX")
    for ob in carriers.values():
        ob.hide_render = True
        ob.hide_set(True)
    info = layout(rows, report, spots)
    with open(os.path.join(EXPORT, "mesh_report.json"), "w") as f:
        json.dump(report, f, indent=1)
    print(json.dumps(report, indent=1))
    for img in bpy.data.images:
        if img.filepath_raw and not img.packed_file and os.path.exists(bpy.path.abspath(img.filepath_raw)):
            img.pack()
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(EXPORT, "Scythe.blend"), compress=True)
    if render:
        render_previews(parts, aura, imgs, rows, only)
    return info


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    shots = next((a.split("=", 1)[1].split(",") for a in argv if a.startswith("--shots=")), None)
    main(render="--render" in argv or shots is not None, only=shots)
