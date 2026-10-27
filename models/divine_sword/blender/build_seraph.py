"""
Seraph Blade - Blender build script.

Recreates the white-and-gold divine sword from the reference sheet: a long, slim white crystal
blade (with the reference's waist and leaf-shaped belly and layered white sections) carrying a
raised two-panel gold filigree channel set with small gems; a guard of gold crescents and white
scroll curls round a large teardrop gem that goes right through it; a slim tapered white
crystal grip with ornate gold collars; and a kite-shaped gem pommel in a gold frame. The white /
gold divine aura is built as five separate objects (WhiteAura, GoldAura, EnergyRibbons,
Sparkles, Particles).

Every outline was measured from the reference's front view:
    u = pixels across (right +, the sword's axis at 0), v = pixels down (the guard gem's centre at v = 160)

Run it either way:
  * Blender: Scripting tab > Open > build_seraph.py > Run Script (starts a new scene)
  * Headless: python build_seraph.py [--render] [--shots=front,angle]   (with the `bpy` module)

Writes ../export (SeraphBlade.fbx/.glb, SeraphAura.fbx/.glb, SeraphVFX.fbx/.glb, .blend,
sword_layout.json, mesh_report.json), ../textures and ../previews.

Units are Roblox studs (0.0075 studs per reference pixel, 4.9 studs long).
Axes: pommel up (+Z), blade pointing down, the front of the sword facing -Y (the front view).
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
import divine_textures as dt  # noqa: E402

ROOT = os.path.normpath(os.path.join(HERE, ".."))
EXPORT = os.path.join(ROOT, "export")
TEXTURES = os.path.join(ROOT, "textures")
PREVIEWS = os.path.join(ROOT, "previews")

S = 0.0075                       # studs per reference pixel
V0 = 160                         # reference row of the origin (the guard gem's centre)
X = Vector((1, 0, 0))
Y = Vector((0, 1, 0))
Z = Vector((0, 0, 1))

# the gold texture is an atlas: plain polished gold on the left half, engraved filigree on the right
UV_GOLD = (0.0, 0.0, 0.5, 1.0)
UV_FILIGREE = (0.5, 0.0, 0.5, 1.0)


def P(u, v, y=0.0):
    """Reference pixels (u across, v down, y depth towards the back) to Blender studs."""
    return Vector((u * S, y * S, (V0 - v) * S))


# ---------------------------------------------------------------- measurements (reference pixels)

POMMEL_TIP = 18
GRIP_TOP, GRIP_BOT = 56, 116
GRIP_R = [(56, 10.0), (62, 10.4), (75, 9.4), (90, 8.0), (104, 7.0), (116, 6.4)]
GEM_TOP, GEM_BOT, GEM_W, GEM_DEPTH = 141, 183, 11.5, 7.5      # the teardrop guard gem
BLADE_TIP = 677
# blade half width (px) down its length: wide at the guard, a waist, a leaf-shaped belly, the point
BLADE_W = [(196, 15), (225, 22), (262, 24), (305, 22), (345, 19), (382, 20.5), (425, 24), (462, 25.5),
           (500, 24), (540, 19.5), (580, 14), (620, 8.5), (655, 3.6), (677, 0.0)]
BLADE_T = [(196, 4.8), (300, 4.4), (450, 3.8), (580, 2.6), (660, 1.0), (677, 0.3)]   # half thickness
# the gold channel: upper and lower panels joined by a thin line (half widths, px)
ORN_A = [(184, 12.5), (196, 10.0), (214, 12.0), (250, 12.5), (296, 10.5), (328, 6.5), (350, 3.0)]
ORN_B = [(388, 3.0), (408, 8.0), (448, 12.0), (478, 11.0), (508, 6.0), (532, 0.0)]
# guard crescents (right side; mirrored): centre-line points and max width
CRESCENT_OUT = ([(13, 166), (28, 177), (46, 176), (59, 161), (66, 139), (67, 113)], 15.0)
CRESCENT_IN = ([(12, 156), (25, 163), (37, 158), (44, 146), (46, 131)], 10.0)
GRIP_V = 88


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
    for i, key in enumerate(dt.AURA):
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


# ---------------------------------------------------------------- small builders

def table(points):
    return pchip([p[0] for p in points], [p[1] for p in points])


BW, BT, OA, OB = table(BLADE_W), table(BLADE_T), table(ORN_A), table(ORN_B)
GR = table(GRIP_R)


def uv_region(mb, i0, rect, v_scale=1.0):
    """Squeeze the UVs of the vertices added since index i0 into one column of the gold atlas."""
    u0, _, du, _ = rect
    for i in range(i0, len(mb.uv)):
        u, v = mb.uv[i]
        mb.uv[i] = (u0 + du * (0.02 + 0.96 * min(max(u, 0.0), 1.0)), v * v_scale)


def lathe(mb, profile, sides=16, smooth=True, star=1.0):
    """Turned part from (v, radius px) pairs, top to bottom. star < 1 alternates the radii, for
    a faceted crystal look."""
    rings = []
    for v, r in profile:
        radii = [r * S * (1 if j % 2 == 0 or star == 1.0 else star) for j in range(sides)]
        rings.append(ring_pts(P(0, v), X, Y, radii))
    loft(mb, rings, uv_v=[(v - profile[0][0]) * 0.02 for v, _ in profile], smooth=smooth)


def loop_band(mb, pts, half_w, half_t, normal, smooth=False):
    """Closed band along a closed loop: rectangle cross-section, `half_w` in the loop's plane,
    `half_t` along `normal`."""
    pts = [Vector(p) for p in pts]
    n = len(pts)
    centre = sum(pts, Vector()) / n
    rings = []
    for k, p in enumerate(pts):
        tan = (pts[(k + 1) % n] - pts[k - 1]).normalized()
        out = Vector(normal).cross(tan).normalized()
        if out.dot(p - centre) < 0:
            out = -out
        rings.append([p + out * half_w + normal * half_t, p - out * half_w + normal * half_t,
                      p - out * half_w - normal * half_t, p + out * half_w - normal * half_t])
    idx = [[mb.add(q, (j / 4, k / n)) for j, q in enumerate(r)] for k, r in enumerate(rings)]
    for k in range(n):
        A, B = idx[k], idx[(k + 1) % n]
        c = (pts[k] + pts[(k + 1) % n]) / 2
        for j in range(4):
            mb.out_face([A[j], A[(j + 1) % 4], B[(j + 1) % 4], B[j]], c, smooth)


def gemstone(mb, outline, depth, table_scale=0.5, girdle=1.0):
    """A double-sided cut gem from a closed outline (points in the XZ plane at y = 0): table and
    crown facets on the front and the back, a thin girdle round the edge."""
    c = sum((Vector(p) for p in outline), Vector()) / len(outline)
    def ring(scale, y):
        return [c + (Vector(p) - c) * scale + Y * y * S for p in outline]
    rings = [[c - Y * depth * S], ring(table_scale, -depth * 0.82), ring(1.0, -girdle), ring(1.0, girdle),
             ring(table_scale, depth * 0.82), [c + Y * depth * S]]
    loft(mb, rings, tri=True)


def marquise(mb, centre, along, length, width, height, sgn):
    """A small pointed gem lying on a surface (sgn = -1 front, +1 back)."""
    a = Vector(along).normalized()
    side = Y.cross(a).normalized()
    c = Vector(centre)
    pts = [c + a * length / 2 * S, c - a * length / 2 * S]
    ring = []
    for k in range(6):
        t = 2 * math.pi * k / 6
        ring.append(c + side * math.cos(t) * width / 2 * S + Y * sgn * (0.6 + math.sin(t) * height) * S)
    idx_ring = [mb.add(q, (0.5, 0.5)) for q in ring]
    i_top, i_bot = mb.add(pts[0], (0.5, 1)), mb.add(pts[1], (0.5, 0))
    for k in range(6):
        mb.out_face([idx_ring[k], idx_ring[(k + 1) % 6], i_top], c)
        mb.out_face([idx_ring[k], idx_ring[(k + 1) % 6], i_bot], c)


def teardrop_outline(n=28, scale=1.0, cx=0.0):
    pts = []
    for k in range(n):
        t = 2 * math.pi * k / n
        x = GEM_W * math.sin(t) * math.sin(t / 2) * 1.32 * scale
        z = math.cos(t)
        v = (GEM_TOP + GEM_BOT) / 2 - z * (GEM_BOT - GEM_TOP) / 2 * scale
        pts.append(P(cx + x, v))
    return pts


def kite_outline(top, mid, bot, half_w, n=8):
    pts = [(0, top), (half_w * 0.55, top + (mid - top) * 0.45), (half_w, mid), (half_w * 0.55, mid + (bot - mid) * 0.5),
           (0, bot), (-half_w * 0.55, mid + (bot - mid) * 0.5), (-half_w, mid), (-half_w * 0.55, top + (mid - top) * 0.45)]
    return pts


# ---------------------------------------------------------------- blade

def blade_ring(v, scale=1.0):
    """Cross-section: a wide flat carrying the gold channel, bevelled to sharp edges; below the
    channel the flat rises into a central ridge, so the point reads as cut crystal."""
    w, t = BW(v) * scale, BT(v) * scale
    g = min(1.0, max(0.0, (v - 522) / 40))
    shoulder = 1 - 0.3 * g
    prof = [(1, 0), (0.72, 0.55), (0.5, shoulder), (0, 1), (-0.5, shoulder), (-0.72, 0.55), (-1, 0),
            (-0.72, -0.55), (-0.5, -shoulder), (0, -1), (0.5, -shoulder), (0.72, -0.55)]
    return [P(w * a, v, t * b) for a, b in prof]


def build_blade(blade):
    vs = list(np.linspace(196, BLADE_TIP - 3, 72))
    rings = [blade_ring(v) for v in vs] + [[P(0, BLADE_TIP)]]
    loft(blade, rings, uv_v=[(v - 196) * 0.004 for v in vs] + [2.0])
    # layered crystal sections along both edges: thin scalloped fins, like stacked light
    for s in (-1, 1):
        for v0, v1, reach, off in ((212, 334, 3.2, -0.5), (396, 572, 3.0, 0.5)):
            rings = []
            for k, v in enumerate(np.linspace(v0, v1, 40)):
                f = (v - v0) / (v1 - v0)
                env = math.sin(math.pi * f) ** 0.6
                phase = ((v - v0) / 44.0) % 1.0          # feather-like steps, each sweeping towards the tip
                scallop = 0.55 + 0.45 * (1 - phase) ** 0.6
                inner = BW(v) - 5
                outer = BW(v) + reach * env * scallop
                th = 1.0 * env + 0.15
                if k in (0, 39):
                    rings.append([P(s * BW(v), v, off)])
                    continue
                rings.append([P(s * inner, v, off - th), P(s * outer, v, off - th * 0.3), P(s * outer, v, off + th * 0.3),
                              P(s * inner, v, off + th)])
            loft(blade, rings)


def panel_slab(mb, half_w_fn, v0, v1, sgn, n=40, lift=0.7, ref_w=12.0):
    """The recessed filigree face of one gold panel on one side of the blade: its outward face is
    UV-mapped across the panel width (u) and along it in square tiles (v)."""
    vs = np.linspace(v0, v1, n)
    rows = []
    for v in vs:
        a = max(half_w_fn(v) - 1.5, 0.0)
        t = BT(v)
        rows.append((a, t, v))
    idx = []
    for a, t, v in rows:
        vv = (v - v0) / (2 * ref_w)
        f_out = sgn * (t + lift)
        f_in = sgn * (t - 0.4)
        idx.append([mb.add(P(-a, v, f_out), (0.0, vv)), mb.add(P(a, v, f_out), (1.0, vv)),
                    mb.add(P(a, v, f_in), (1.0, vv)), mb.add(P(-a, v, f_in), (0.0, vv))])
    centre_of = [P(0, v, sgn * t) for _, t, v in rows]
    for k in range(n - 1):
        A, B = idx[k], idx[k + 1]
        c = (centre_of[k] + centre_of[k + 1]) / 2
        for j in range(4):
            mb.out_face([A[j], A[(j + 1) % 4], B[(j + 1) % 4], B[j]], c)
    for k, nb in ((0, 1), (n - 1, n - 2)):
        if rows[k][0] > 1e-4:
            mb.out_face(idx[k], centre_of[nb])


def panel_outline(half_w_fn, v0, v1, sgn, n=34):
    right = [(half_w_fn(v), v) for v in np.linspace(v0, v1, n)]
    pts = right + [(-a, v) for a, v in reversed(right)]
    out = []
    for a, v in pts:                                 # drop the doubled point where the two sides meet
        p = P(a, v, sgn * (BT(v) + 0.8))
        if not out or (p - out[-1]).length > 1e-6:
            out.append(p)
    if (out[0] - out[-1]).length < 1e-6:
        out.pop()
    return out


def build_ornament(gold, gems, rng):
    for sgn in (-1, 1):
        for fn, v0, v1, v1_face in ((OA, 184, 350, 350), (OB, 388, 532, 524)):
            i0 = len(gold.uv)
            panel_slab(gold, fn, v0, v1_face, sgn)
            uv_region(gold, i0, UV_FILIGREE)
            i0 = len(gold.uv)
            loop_band(gold, panel_outline(fn, v0, v1, sgn), 1.15 * S, 0.9 * S, Y)
            uv_region(gold, i0, UV_GOLD)
        # the thin gold line joining the two panels
        i0 = len(gold.uv)
        rings = [[P(-1.4, v, sgn * (BT(v) + 0.2)), P(1.4, v, sgn * (BT(v) + 0.2)), P(1.4, v, sgn * (BT(v) + 1.5)),
                  P(-1.4, v, sgn * (BT(v) + 1.5))] for v in np.linspace(345, 393, 8)]
        loft(gold, rings)
        uv_region(gold, i0, UV_GOLD)
        # small gems down the middle of the panels, framed by little gold leaves
        for v, ln in ((232, 10), (276, 8), (440, 9), (472, 7)):
            marquise(gems, P(0, v, sgn * (BT(v) + 0.7)), Z, ln, 3.6, 1.1, sgn)
            for s in (-1, 1):
                i0 = len(gold.uv)
                c = P(s * 4.6, v - 3, sgn * (BT(v) + 0.9))
                d = (Vector((s * 0.8, 0, 1))).normalized()
                crystal(gold, c - d * 3.5 * S, c + d * 3.5 * S, 1.3 * S, rng, sides=4, body=(0.45, 0.55), flat=0.5,
                        wide=Y.cross(d))
                uv_region(gold, i0, UV_GOLD)


# ---------------------------------------------------------------- guard

def scroll(mb, pts_px, width, depth, rim=None, rim_side=1):
    """A scroll curl: a flattened tube along the curl, wide at its root, thin at its tip.
    rim (an MB) adds a thin gold edge along its outside."""
    pts = smooth_path([P(u, v) for u, v in pts_px], 4)
    n = len(pts)
    rings = []
    rim_pts = []
    for k, p in enumerate(pts):
        f = k / (n - 1)
        tan = (pts[min(n - 1, k + 1)] - pts[max(0, k - 1)]).normalized()
        side = Y.cross(tan).normalized()
        w = width * (1 - 0.65 * f) / 2 * S
        d = depth * (1 - 0.5 * f) * S
        rings.append([p + side * w * math.cos(2 * math.pi * j / 8) + Y * d * math.sin(2 * math.pi * j / 8)
                      for j in range(8)])
        rim_pts.append(p + side * w * rim_side)
    rings.append([pts[-1] + (pts[-1] - pts[-2]).normalized() * 0.8 * S])
    loft(mb, rings, smooth=True)
    if rim is not None:
        i0 = len(rim.uv)
        rr = []
        for k, p in enumerate(rim_pts):
            f = k / (n - 1)
            tan = (rim_pts[min(n - 1, k + 1)] - rim_pts[max(0, k - 1)]).normalized()
            s1, s2 = frame(tan, Y)
            r = 0.9 * (1 - 0.5 * f) * S
            rr.append(ring_pts(p, s1, s2, [r * 1.6, r, r * 1.6, r]))
        rr.append([rim_pts[-1]])
        loft(rim, rr, smooth=True)
        uv_region(rim, i0, UV_GOLD)


def crescent(gold, pts, width_fn, half_t):
    """A gold crescent band: an engraved filigree face on both sides inside a raised gold rim,
    pointed at its tip."""
    pts = [Vector(p) for p in pts]
    n = len(pts)
    left, right, idx = [], [], []
    length = sum((pts[k + 1] - pts[k]).length for k in range(n - 1))
    run = 0.0
    i0 = len(gold.uv)
    for k, p in enumerate(pts):
        if k:
            run += (pts[k] - pts[k - 1]).length
        f = k / (n - 1)
        tan = (pts[min(n - 1, k + 1)] - pts[max(0, k - 1)]).normalized()
        side = Y.cross(tan).normalized()
        w = width_fn(f)
        vv = run / max(width_fn(0.4) * 2, 1e-6)
        if w < 1e-6:
            idx.append([gold.add(p, (0.5, vv))])
        else:
            l, r = p - side * w / 2, p + side * w / 2
            left.append(l)
            right.append(r)
            idx.append([gold.add(l - Y * half_t, (0.0, vv)), gold.add(r - Y * half_t, (1.0, vv)),
                        gold.add(r + Y * half_t, (1.0, vv)), gold.add(l + Y * half_t, (0.0, vv))])
    for k in range(n - 1):
        A, B = idx[k], idx[k + 1]
        c = (pts[k] + pts[k + 1]) / 2
        if len(B) == 1:
            for j in range(4):
                gold.out_face([A[j], A[(j + 1) % 4], B[0]], c)
        else:
            for j in range(4):
                gold.out_face([A[j], A[(j + 1) % 4], B[(j + 1) % 4], B[j]], c)
    if len(idx[0]) == 4:
        gold.out_face(idx[0], pts[1])
    uv_region(gold, i0, UV_FILIGREE)
    # the raised rim round its outline
    outline = left + list(reversed(right))           # closed just short of the tip; the gold point caps it
    i0 = len(gold.uv)
    loop_band(gold, outline, 1.15 * S, half_t + 0.7 * S, Y)
    # a sharp gold point carrying the curve on past the rim
    tan = (pts[-1] - pts[-4]).normalized()
    thorn(gold, pts[-1] - tan * 3.5 * S, tan, 10 * S, 3.4 * S, (half_t / S + 0.7) * 2 * S, wide=Y.cross(tan))
    uv_region(gold, i0, UV_GOLD)
    return length


def build_guard(gold, white, gems, rng):
    # the big teardrop gem, right through the guard, in two gold frames
    gemstone(gems, teardrop_outline(), GEM_DEPTH)
    for scale, hw, ht in ((1.12, 1.7, 2.8), (1.36, 2.2, 3.9)):
        i0 = len(gold.uv)
        loop_band(gold, teardrop_outline(36, scale), hw * S, ht * S, Y)
        uv_region(gold, i0, UV_GOLD)
    for sgn in (-1, 1):                          # prongs holding the gem, front and back
        for p in (teardrop_outline(28, 1.06)[k] for k in (0, 7, 14, 21)):
            i0 = len(gold.uv)
            c = P(0, (GEM_TOP + GEM_BOT) / 2)
            d = (c - p).normalized()
            thorn(gold, p + Y * sgn * 2.2 * S, d + Y * sgn * 0.6, 4.5 * S, 2.6 * S, 1.4 * S, wide=Y.cross(d))
            uv_region(gold, i0, UV_GOLD)
    for s in (-1, 1):
        # the gold crescents: a big outer one sweeping up to a point, a smaller one inside it
        for (pts_px, maxw) in (CRESCENT_OUT, CRESCENT_IN):
            pts = smooth_path([P(s * u, v) for u, v in pts_px], 6)
            crescent(gold, pts, lambda f, maxw=maxw: maxw * S * math.sin(math.pi * (0.22 + 0.78 * f)) ** 0.5 *
                     (1 - f) ** 0.4 if f < 1 else 0, 2.2 * S)
        # gold strips running down from the frame into the blade's gold channel
        i0 = len(gold.uv)
        plate(gold, [P(s * u, v) for u, v in ((14.5, 181), (13.2, 192), (12.6, 204), (12.4, 214))],
              lambda f: 2.6 * S, lambda f: 4.6 * S * (1 - 0.3 * f), lambda f: Y)
        uv_region(gold, i0, UV_GOLD)
        # white scroll curls: two above the gem curling out and down, big ones under the crescents
        scroll(white, [(s * 5, 131), (s * 12, 123), (s * 21, 122), (s * 27, 129), (s * 25, 137), (s * 19, 139),
                       (s * 17, 134)], 7.0, 4.6, rim=gold, rim_side=-s)
        scroll(white, [(s * 12, 186), (s * 23, 190), (s * 33, 197), (s * 37, 208), (s * 32, 216), (s * 26, 213),
                       (s * 27, 207)], 10.0, 4.2)
        scroll(white, [(s * 9, 199), (s * 17, 208), (s * 22, 219), (s * 18, 228), (s * 14, 224)], 6.5, 3.6)
        # small diamonds studding the frame
        for u, v in ((17.5, 150), (17, 191)):
            for sgn in (-1, 1):
                marquise(gems, P(s * u, v, sgn * 3.6), Vector((0, 0, 1)), 5.5, 3.6, 1.2, sgn)
    # the little white crystal drop at the top, between the curls
    crystal(white, P(0, 120), P(0, 140), 4.2 * S, rng, sides=6, body=(0.3, 0.42), flat=0.6, wide=X, jitter=0.03)


# ---------------------------------------------------------------- grip and pommel

def build_grip(white, gold, rng):
    prof = [(v, GR(v)) for v in np.linspace(GRIP_TOP - 1, GRIP_BOT + 3, 16)]
    lathe(white, prof, sides=16, smooth=False, star=0.93)
    for v, r in ((72, 9.6), (93, 8.5)):            # thin gold rings
        i0 = len(gold.uv)
        lathe(gold, [(v - 1.6, r * 0.97), (v - 0.8, r * 1.07), (v + 0.8, r * 1.07), (v + 1.6, r * 0.97)], sides=20)
        uv_region(gold, i0, UV_GOLD)
    i0 = len(gold.uv)
    lathe(gold, [(110, 6.9), (113, 8.4), (117, 9.6), (120, 8.4), (122, 6.8)], sides=20)   # ornate collar on the guard
    for k in range(4):                              # leaves reaching up the grip from the collar
        a = math.radians(45 + 90 * k)
        radial = Vector((math.cos(a), math.sin(a), 0))
        pts = [P(0, v) + radial * (GR(v) + 0.5) * S for v in np.linspace(113, 98, 6)]
        plate(gold, pts, lambda f: 4.4 * S * (1 - f) ** 0.8 if f < 1 else 0, lambda f: 0.9 * S,
              lambda f, radial=radial: radial)
    uv_region(gold, i0, UV_GOLD)


def build_pommel(gold, gems, rng):
    # the kite gem, in crossed gold kite frames, under a gold point
    kite = kite_outline(27, 39, 51, 7.4)
    gemstone(gems, [P(u, v) for u, v in kite], 5.4, table_scale=0.45)
    frame_pts = kite_outline(24.5, 39, 53.5, 9.6)
    frame_pts = smooth_path([(u, 0, v) for u, v in frame_pts] + [(frame_pts[0][0], 0, frame_pts[0][1])], 3)[:-1]
    i0 = len(gold.uv)
    loop_band(gold, [P(p[0], p[2]) for p in frame_pts], 1.7 * S, 2.4 * S, Y)
    loop_band(gold, [P(0, p[2], p[0] * 0.75) for p in frame_pts], 1.5 * S, 1.8 * S, X)
    crystal(gold, P(0, 27), P(0, POMMEL_TIP), 3.6 * S, rng, sides=4, body=(0.2, 0.3), jitter=0.0, rot=math.pi / 4)
    for s in (-1, 1):                               # side points
        thorn(gold, P(s * 9.4, 39), Vector((s, 0, 0.15)), 5.5 * S, 3.0 * S, 1.8 * S, wide=Z)
    lathe(gold, [(50, 6.2), (52, 9.0), (55.5, 10.6), (58, 10.0), (59.5, 8.6)], sides=20)
    for k in range(4):                              # a little crown of points under the gem
        a = math.radians(90 * k + 45)
        radial = Vector((math.cos(a), math.sin(a), 0))
        thorn(gold, P(0, 52) + radial * 7.5 * S, Z + radial * 0.35, 5 * S, 2.6 * S, 1.3 * S, wide=Z.cross(radial))
    uv_region(gold, i0, UV_GOLD)


# ---------------------------------------------------------------- the weapon

PART_ORDER = ["Blade", "BladeOrnament", "Guard", "GuardCurls", "Gemstones", "Grip", "GripGold", "Pommel"]


def clean_mesh(ob):
    """Drop degenerate faces and make every normal point outward."""
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=1e-7)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(ob.data)
    bm.free()
    ob.data.update()


def build_weapon():
    rng = np.random.default_rng(5)
    mbs = {name: MB() for name in PART_ORDER}
    build_blade(mbs["Blade"])
    build_ornament(mbs["BladeOrnament"], mbs["Gemstones"], rng)
    build_guard(mbs["Guard"], mbs["GuardCurls"], mbs["Gemstones"], rng)
    build_grip(mbs["Grip"], mbs["GripGold"], rng)
    build_pommel(mbs["Pommel"], mbs["Gemstones"], rng)
    parts = {name: mbs[name].to_object(name) for name in PART_ORDER}
    for ob in parts.values():
        clean_mesh(ob)
    return parts


# ---------------------------------------------------------------- aura (five separate objects)

def ribbon(mb, pts, width_fn, normal_fn):
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


def crossed_card(mb, centre, width, height, yaw=0.0):
    c = Vector(centre)
    for k in range(2):
        a = yaw + math.pi / 2 * k
        side = Vector((math.cos(a), math.sin(a), 0))
        q = [mb.add(c - side * width / 2 - Z * height / 2, (0, 0)), mb.add(c + side * width / 2 - Z * height / 2, (1, 0)),
             mb.add(c + side * width / 2 + Z * height / 2, (1, 1)), mb.add(c - side * width / 2 + Z * height / 2, (0, 1))]
        mb.face(q)


# energy ribbons swirling round the blade: (start v, end v, turns, phase, base radius, bulge, width, gold?)
RIBBONS = [(640, 150, 1.35, 0.3, 0.08, 0.2, 0.035, False), (610, 175, 1.6, 3.4, 0.07, 0.16, 0.025, False),
           (655, 200, 1.2, 1.8, 0.09, 0.24, 0.03, True), (560, 230, 1.5, 5.0, 0.06, 0.14, 0.02, True)]


def ribbon_points(i, n=110):
    v0, v1, turns, phase, r0, bulge, _, _ = RIBBONS[i]
    pts = []
    for k in range(n):
        f = k / (n - 1)
        th = phase + 2 * math.pi * turns * f
        r = r0 + bulge * math.sin(math.pi * f) ** 0.8
        pts.append(Vector((math.cos(th) * r, math.sin(th) * r * 0.8, P(0, v0 + (v1 - v0) * f).z)))
    return pts


def build_aura(mats):
    rng = np.random.default_rng(17)
    obs = {}
    gem_c = P(0, (GEM_TOP + GEM_BOT) / 2)
    blade_mid = P(0, 430)
    # white: the main luminous glow, a halo and soft light rays behind the guard
    mb = MB()
    crossed_card(mb, gem_c, 1.05, 1.05)
    crossed_card(mb, blade_mid, 0.55, 3.7)
    obs["WhiteAura"] = mb.to_object("WhiteAura")
    set_material(obs["WhiteAura"], mats["WhiteGlow"])
    mb = MB()
    crossed_card(mb, gem_c, 0.82, 0.82)
    obs["WhiteHalo"] = mb.to_object("WhiteHalo")
    set_material(obs["WhiteHalo"], mats["Halo"])
    mb = MB()
    crossed_card(mb, gem_c, 1.5, 1.5, yaw=0.4)
    obs["WhiteRays"] = mb.to_object("WhiteRays")
    set_material(obs["WhiteRays"], mats["Rays"])
    # gold: the softer, secondary glow
    mb = MB()
    crossed_card(mb, gem_c, 1.5, 1.4)
    crossed_card(mb, blade_mid, 0.85, 4.0)
    crossed_card(mb, P(0, 38), 0.45, 0.5)
    obs["GoldAura"] = mb.to_object("GoldAura")
    set_material(obs["GoldAura"], mats["GoldGlow"])
    # energy ribbons: white strands and thinner gold ones swirling round the blade
    white_mb, gold_mb = MB(), MB()
    for i, rb in enumerate(RIBBONS):
        ribbon(gold_mb if rb[7] else white_mb, ribbon_points(i),
               lambda f, w=rb[6]: 0.008 + w * math.sin(math.pi * f) ** 0.8,
               lambda f, p: Vector((p.x, p.y, 0)).normalized())
    obs["EnergyRibbons"] = white_mb.to_object("EnergyRibbons")
    set_material(obs["EnergyRibbons"], mats["Ribbon"])
    obs["EnergyRibbonsGold"] = gold_mb.to_object("EnergyRibbonsGold")
    set_material(obs["EnergyRibbonsGold"], mats["RibbonGold"])
    # sparkles: star flashes close to the sword
    mb = MB()
    for k in range(18):
        v = rng.uniform(30, 640)
        reach = 0.75 if 110 < v < 240 else 0.32
        a = rng.uniform(0, 2 * math.pi)
        c = P(0, v) + Vector((math.cos(a) * rng.uniform(0.12, reach), math.sin(a) * 0.25, 0))
        sz = rng.uniform(0.05, 0.13)
        crossed_card(mb, c, sz, sz, rng.uniform(0, 3))
    obs["Sparkles"] = mb.to_object("Sparkles")
    set_material(obs["Sparkles"], mats["Sparkle"])
    # particles: tiny glowing motes riding the ribbons and drifting round the guard
    mb = MB()
    for k in range(60):
        if k < 44:
            pts = ribbon_points(k % len(RIBBONS), 60)
            c = pts[int(rng.integers(4, 56))] + Vector((rng.normal(0, 0.03), rng.normal(0, 0.03), rng.normal(0, 0.04)))
        else:
            a = rng.uniform(0, 2 * math.pi)
            c = gem_c + Vector((math.cos(a) * rng.uniform(0.2, 0.6), math.sin(a) * 0.3, rng.uniform(-0.35, 0.35)))
        sz = rng.uniform(0.015, 0.035)
        crossed_card(mb, c, sz, sz, rng.uniform(0, 3))
    obs["Particles"] = mb.to_object("Particles")
    set_material(obs["Particles"], mats["Mote"])
    return obs


# ---------------------------------------------------------------- textures, materials, layout

def textures():
    os.makedirs(TEXTURES, exist_ok=True)

    def save(name, arr, colorspace="sRGB"):
        return np_image(name, arr, os.path.join(TEXTURES, name + ".png"), colorspace)
    gold = dt.gold(512)
    fil = dt.filigree(512)
    atlas = np.concatenate([gold, fil], axis=1)
    gmr = dt.gold_mr(512)
    fmr = gmr.copy()
    fmr[..., 1] = np.clip(fmr[..., 1] + (1 - fil[..., 0]) * 0.35, 0, 1)      # the engraved ground is a little rougher
    imgs = {
        "gold": save("gold_color", atlas),
        "gold_mr": save("gold_mr", np.concatenate([gmr, fmr], axis=1), "Non-Color"),
        "crystal": save("white_crystal_color", dt.white_crystal()),
        "crystal_mr": save("white_crystal_mr", dt.crystal_mr(rough=0.1), "Non-Color"),
        "gem": save("gem_color", dt.gem()),
        "gem_mr": save("gem_mr", dt.crystal_mr(rough=0.02), "Non-Color"),
    }
    for key, fn in dt.AURA.items():
        imgs["fx_" + key] = save("fx_" + key.lower(), fn())
    return imgs


def gem_material(name, col, mr):
    mat = crystal_material(name, col, mr, glow_strength=0.15, transmission=0.95)
    for n in mat.node_tree.nodes:
        if n.type == "BSDF_PRINCIPLED":
            n.inputs["IOR"].default_value = 2.2
            n.inputs["Coat Weight"].default_value = 0.0
    return mat


def materials(imgs):
    gold = metal_material("PolishedGold", imgs["gold"], imgs["gold_mr"])
    white = crystal_material("WhiteCrystal", imgs["crystal"], imgs["crystal_mr"], glow_strength=0.1, transmission=0.15)
    for n in white.node_tree.nodes:
        if n.type == "BSDF_PRINCIPLED":
            n.inputs["Coat Weight"].default_value = 0.5
    return {
        "Blade": white, "GuardCurls": white, "Grip": white,
        "BladeOrnament": gold, "Guard": gold, "GripGold": gold, "Pommel": gold,
        "Gemstones": gem_material("Diamond", imgs["gem"], imgs["gem_mr"]),
        "WhiteGlow": fx_material("WhiteAura", imgs["fx_GlowWhite"], 0.22),
        "Halo": fx_material("WhiteHalo", imgs["fx_Halo"], 0.55),
        "Rays": fx_material("WhiteRays", imgs["fx_Rays"], 0.32),
        "GoldGlow": fx_material("GoldAura", imgs["fx_GlowGold"], 0.25),
        "Ribbon": fx_material("EnergyRibbons", imgs["fx_Ribbon"], 2.2),
        "RibbonGold": fx_material("EnergyRibbonsGold", imgs["fx_RibbonGold"], 1.8),
        "Sparkle": fx_material("Sparkles", imgs["fx_Sparkle"], 2.6),
        "Mote": fx_material("Particles", imgs["fx_Mote"], 2.2),
    }


def layout(report):
    info = {
        "units": "studs", "studsPerPixel": S,
        "points": {
            "Gem": list(P(0, (GEM_TOP + GEM_BOT) / 2)), "Grip": list(P(0, GRIP_V)), "Pommel": list(P(0, 39)),
            "BladeStart": list(P(0, 205)), "BladeTip": list(P(0, BLADE_TIP)), "BladeMid": list(P(0, 430)),
            "TrailBase": list(P(0, 260)),
        },
        "bladeVolume": {"centre": list(P(0, 440)), "size": [50 * S, 6 * S, 440 * S]},
        "ribbons": [[[round(c, 4) for c in p] for p in ribbon_points(i, 41)] for i in range(len(RIBBONS))],
        "ribbonWidths": [rb[6] for rb in RIBBONS],
        "ribbonGold": [rb[7] for rb in RIBBONS],
        "meshReport": report,
    }
    with open(os.path.join(EXPORT, "sword_layout.json"), "w") as f:
        json.dump(info, f, indent=1)
    return info


# ---------------------------------------------------------------- previews

def render_previews(parts, aura, imgs, only=None):
    os.makedirs(PREVIEWS, exist_ok=True)
    sc = bpy.context.scene
    sc.cycles.samples = 48
    sc.cycles.use_denoising = True
    sc.cycles.transparent_max_bounces = 64
    sc.cycles.max_bounces = 12
    sc.cycles.glossy_bounces = 6
    sc.cycles.transmission_bounces = 10
    sc.view_settings.view_transform = "Standard"
    world = bpy.data.worlds.new("Heaven")
    sc.world = world
    wnt = nodes_of(world)
    bg = wnt.nodes.new("ShaderNodeBackground")                     # what the camera sees
    bg.inputs["Color"].default_value = (0.026, 0.021, 0.015, 1)
    env = wnt.nodes.new("ShaderNodeBackground")                    # what the gold reflects: a warm studio
    coord = wnt.nodes.new("ShaderNodeTexCoord")
    sep = wnt.nodes.new("ShaderNodeSeparateXYZ")
    ramp = wnt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.3
    ramp.color_ramp.elements[0].color = (0.03, 0.025, 0.02, 1)
    ramp.color_ramp.elements[1].position = 0.85
    ramp.color_ramp.elements[1].color = (1.0, 0.97, 0.9, 1)
    el = ramp.color_ramp.elements.new(0.5)
    el.color = (0.75, 0.66, 0.5, 1)
    mapr = wnt.nodes.new("ShaderNodeMapRange")
    mapr.inputs["From Min"].default_value = -1
    wnt.links.new(coord.outputs["Normal"], sep.inputs[0])
    wnt.links.new(sep.outputs["Z"], mapr.inputs["Value"])
    wnt.links.new(mapr.outputs["Result"], ramp.inputs["Fac"])
    wnt.links.new(ramp.outputs["Color"], env.inputs["Color"])
    env.inputs["Strength"].default_value = 1.1
    lp = wnt.nodes.new("ShaderNodeLightPath")
    mix = wnt.nodes.new("ShaderNodeMixShader")
    wnt.links.new(lp.outputs["Is Camera Ray"], mix.inputs[0])
    wnt.links.new(env.outputs[0], mix.inputs[1])
    wnt.links.new(bg.outputs[0], mix.inputs[2])
    wo = wnt.nodes.new("ShaderNodeOutputWorld")
    wnt.links.new(mix.outputs[0], wo.inputs["Surface"])

    def light(name, loc, energy, color, size, target=(0, 0, -1.4)):
        ld = bpy.data.lights.new(name, "AREA")
        ld.energy, ld.color, ld.size = energy, color, size
        lo = bpy.data.objects.new(name, ld)
        lo.location = loc
        lo.rotation_euler = (Vector(target) - lo.location).to_track_quat("-Z", "Y").to_euler()
        sc.collection.objects.link(lo)

    light("Key", (-3, -4.5, 2.5), 420, (1.0, 0.96, 0.9), 3)
    light("Fill", (3.5, -4, -1.5), 160, (0.92, 0.95, 1.0), 4)
    light("RimL", (-3.5, 4, 1.5), 380, (1.0, 0.85, 0.55), 3)
    light("RimR", (3.5, 4, -1.5), 340, (1.0, 0.92, 0.75), 3)
    cam_d = bpy.data.cameras.new("Cam")
    cam = bpy.data.objects.new("Cam", cam_d)
    sc.collection.objects.link(cam)
    sc.camera = cam

    def shot(name, loc, target, res, ortho=None, lens=50, glow=0.5):
        if only and name not in only:
            return
        cam.location = loc
        cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
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
            bloom(path, strength=glow, threshold=0.7)
        print("rendered", path)

    def show_aura(on):
        for ob in aura.values():
            ob.hide_render = not on

    mid_z = P(0, 348).z
    full = (440, 1530)
    ortho = 690 * S
    show_aura(False)
    shot("model_front", (0, -20, mid_z), (0, 0, mid_z), full, ortho=ortho, glow=0.35)
    shot("model_back", (0, 20, mid_z), (0, 0, mid_z), full, ortho=ortho, glow=0.35)
    shot("model_angle", (-2.0, -4.8, 0.6), (0, 0, -1.0), (900, 1400), lens=42, glow=0.35)
    show_aura(True)
    shot("front", (0, -20, mid_z), (0, 0, mid_z), full, ortho=ortho)
    shot("back", (0, 20, mid_z), (0, 0, mid_z), full, ortho=ortho)
    shot("left", (-20, 0, mid_z), (0, 0, mid_z), full, ortho=ortho)
    shot("right", (20, 0, mid_z), (0, 0, mid_z), full, ortho=ortho)
    shot("angle", (-2.0, -4.8, 0.6), (0, 0, -1.0), (900, 1400), lens=42)
    gem_z = P(0, 162).z
    shot("head_closeup", (-0.5, -1.6, gem_z + 0.4), (0, 0, gem_z - 0.02), (1100, 1000), lens=50)
    shot("blade_closeup", (0.35, -1.25, P(0, 420).z + 0.25), (0, 0, P(0, 430).z), (800, 1000), lens=50)
    shot("pommel_closeup", (0.35, -1.0, P(0, 60).z + 0.2), (0, 0, P(0, 70).z), (800, 1000), lens=50)

    # in game: standing on a grey baseplate under a blue sky, like the reference sheet
    if only and "ingame" not in only:
        return
    floor_z = P(0, BLADE_TIP).z
    mb = MB()
    q = [mb.add((-12, -12, floor_z), (0, 0)), mb.add((12, -12, floor_z), (1, 0)), mb.add((12, 12, floor_z), (1, 1)),
         mb.add((-12, 12, floor_z), (0, 1))]
    mb.face(q)
    floor = mb.to_object("Floor")
    fm = bpy.data.materials.new("Floor")
    fnt = nodes_of(fm)
    fb = fnt.nodes.new("ShaderNodeBsdfPrincipled")
    fb.inputs["Roughness"].default_value = 0.6
    checker = fnt.nodes.new("ShaderNodeTexChecker")
    checker.inputs["Scale"].default_value = 20
    checker.inputs["Color1"].default_value = (0.3, 0.31, 0.36, 1)
    checker.inputs["Color2"].default_value = (0.33, 0.34, 0.39, 1)
    fnt.links.new(checker.outputs["Color"], fb.inputs["Base Color"])
    fo = fnt.nodes.new("ShaderNodeOutputMaterial")
    fnt.links.new(fb.outputs[0], fo.inputs["Surface"])
    set_material(floor, fm)
    mb = MB()
    r = 0.9
    q = [mb.add((-r, -r, floor_z + 0.004), (0, 0)), mb.add((r, -r, floor_z + 0.004), (1, 0)),
         mb.add((r, r, floor_z + 0.004), (1, 1)), mb.add((-r, r, floor_z + 0.004), (0, 1))]
    mb.face(q)
    circle = mb.to_object("HolyCircle")
    set_material(circle, fx_material("HolyCircle", imgs["fx_HolyCircle"], 1.4))
    bg.inputs["Color"].default_value = (0.25, 0.5, 0.95, 1)
    shot("ingame", (-1.8, -6.6, -0.9), (-0.05, 0, -1.9), (900, 1300), lens=40, glow=0.35)


def main(render=False, only=None):
    clean_scene()
    parts = build_weapon()
    imgs = textures()
    mats = materials(imgs)
    for name in PART_ORDER:
        set_material(parts[name], mats[name])
    report = mesh_report(parts)
    aura = build_aura(mats)
    marks = [marker("Mark_O", (0, 0, 0)), marker("Mark_Y", (0, 1, 0)), marker("Mark_Z", (0, 0, 1))]
    export([parts[n] for n in PART_ORDER] + marks, "SeraphBlade")
    for m in marks:
        bpy.data.objects.remove(m)
    export(list(aura.values()), "SeraphAura")
    carriers = build_vfx_carriers(imgs)
    export(list(carriers.values()), "SeraphVFX")
    for ob in carriers.values():
        ob.hide_render = True
        ob.hide_set(True)
    info = layout(report)
    with open(os.path.join(EXPORT, "mesh_report.json"), "w") as f:
        json.dump(report, f, indent=1)
    print(json.dumps(report, indent=1))
    for img in bpy.data.images:
        if img.filepath_raw and not img.packed_file and os.path.exists(bpy.path.abspath(img.filepath_raw)):
            img.pack()
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(EXPORT, "SeraphBlade.blend"), compress=True)
    if render:
        render_previews(parts, aura, imgs, only)
    return info


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    shots = next((a.split("=", 1)[1].split(",") for a in argv if a.startswith("--shots=")), None)
    main(render="--render" in argv or shots is not None, only=shots)
