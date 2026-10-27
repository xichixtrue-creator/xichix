"""
Fortune Staff - Blender build script.

Recreates the green / gold money staff from the reference sheet: a tall staff crowned by a
big three-dimensional money symbol (faceted emerald set in polished gold), a gold spear
finial, two gold rings orbiting the symbol, a dark green-black shaft with gold bands and
emerald inserts, and a gold-framed emerald diamond at the foot. The subtle green / gold aura
(wisps, sparkles, motes, little money symbols, glow) is built as separate objects.

Every outline was measured from the reference's front view:
    u = pixels across (right +, shaft axis at 0), v = pixels down (money symbol's centre at v = 112)

Run it either way:
  * Blender: Scripting tab > Open > build_moneystaff.py > Run Script (starts a new scene)
  * Headless: python build_moneystaff.py [--render] [--shots=front,angle]   (with the `bpy` module)

Writes ../export (MoneyStaff.fbx/.glb, MoneyStaffAura.fbx/.glb, MoneyStaffVFX.fbx/.glb, .blend,
staff_layout.json, mesh_report.json), ../textures and ../previews.

Units are Roblox studs (0.0095 studs per reference pixel, 6.6 studs tall).
Axes: shaft along Z, money symbol facing -Y (the front view).
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
import money_textures as mt  # noqa: E402

ROOT = os.path.normpath(os.path.join(HERE, ".."))
EXPORT = os.path.join(ROOT, "export")
TEXTURES = os.path.join(ROOT, "textures")
PREVIEWS = os.path.join(ROOT, "previews")

S = 0.0095                       # studs per reference pixel
V0 = 112                         # reference row of the origin (the money symbol's centre)
X = Vector((1, 0, 0))
Y = Vector((0, 1, 0))
Z = Vector((0, 0, 1))


def P(u, v, y=0.0):
    """Reference pixels (u across, v down, y depth towards the back) to Blender studs."""
    return Vector((u * S, y * S, (V0 - v) * S))


def D(u, z, y=0.0):
    """Money-symbol pixels (u across, z up from its centre, y depth) to Blender studs."""
    return Vector((u * S, y * S, z * S))


# ---------------------------------------------------------------- measurements (reference pixels)

# the money symbol: an S of two stacked elliptical bowls, crossed by one vertical bar
S_RX, S_RZ = 25.0, 17.0          # bowl radii of the S's centre line
S_W = 19.0                       # S stroke width
BAR_W = 12.5
BAR_TOP, BAR_BOT = 50.0, -56.0   # the bar runs from v = 62 to v = 168
EM_FRONT = 7.0                   # how far the emerald face stands out in front
EM_EDGE = 4.5
GOLD_BACK = 6.5                  # depth of the gold setting behind it

RING_R = 72.0                    # main orbit ring radius
RING_TILT, RING_ROLL = 40.0, 4.0
RING2 = (63.0, -24.0, 70.0)      # second, thinner ring: radius, tilt, yaw

SHAFT_TOP, SHAFT_BOT = 287, 583
SHAFT_R = 6.2
BAND_NODES = [318, 487]
TIP_V = 712
GRIP_V = 470

# aura strands spiralling up the shaft: (start v, end v, turns, phase, base radius, bulge, max width) in studs
SPIRALS = [(690, 205, 1.6, 0.4, 0.07, 0.15, 0.05), (676, 232, 1.9, 3.6, 0.06, 0.12, 0.035)]


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
    for i, key in enumerate(mt.AURA):
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


# ---------------------------------------------------------------- turned gold and simple solids

def lathe(mb, profile, sides=20, smooth=True, u=0.0):
    """Turned (round) part from (v, radius px) pairs, top to bottom."""
    rings = [ring_pts(P(u, v), X, Y, [r * S] * sides) for v, r in profile]
    loft(mb, rings, uv_v=[(v - profile[0][0]) * 0.02 for v, _ in profile], smooth=smooth)


def box(mb, centre, ax, ay, az, hx, hy, hz):
    c = Vector(centre)
    idx = [mb.add(c + ax * sx * hx + ay * sy * hy + az * sz * hz, ((sx + 1) / 2, (sz + 1) / 2))
           for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
    for f in ((0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)):
        mb.out_face([idx[i] for i in f], c)


def loop_band(mb, pts, half_w, half_t, normal, smooth=False):
    """Closed band along a closed loop of points: rectangle cross-section, `half_w` in the
    loop's plane, `half_t` along `normal`."""
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


def gem(mb, base, tip, radius, rng, sides=8, mid=0.5, flat=1.0, wide=None):
    """Faceted bipyramid gem (widest at `mid`)."""
    crystal(mb, base, tip, radius, rng, sides=sides, body=(mid - 0.06, mid + 0.06), jitter=0.04, flat=flat,
            wide=wide, rot=math.pi / sides)


# ---------------------------------------------------------------- the money symbol

def s_centerline(n=30):
    pts = []
    for k in range(n):
        th = math.radians(25 + 245 * k / (n - 1))
        pts.append((S_RX * math.cos(th), S_RZ + S_RZ * math.sin(th)))
    for k in range(1, n):
        th = math.radians(90 - 245 * k / (n - 1))
        pts.append((S_RX * math.cos(th), -S_RZ + S_RZ * math.sin(th)))
    return pts


def stroke(em, gold, glow, pts2d, width, front=EM_FRONT, clip=None, caps=(True, True)):
    """One stroke of the money symbol: a faceted emerald face, framed by gold rails on both
    edges, held in a gold setting behind, gold caps on its ends and a glowing heart inside.
    clip (px, signed) flattens the stroke against the plane u = clip, where it meets the bar."""
    pts = [D(u, z) for u, z in pts2d]
    n = len(pts)
    rail = front + 1.0
    em_r, back_r, rail_l, rail_r, core_r = [], [], [], [], []
    for k, p in enumerate(pts):
        tan = (pts[min(n - 1, k + 1)] - pts[max(0, k - 1)]).normalized()
        side = Y.cross(tan).normalized()

        def at(s, y, p=p, side=side):
            return p + side * s * S + Y * y * S
        a, b, c = width / 2 - 0.8, width / 4, width / 2 + 1.3
        em_r.append([at(-a, -EM_EDGE), at(-b, -front), at(b, -front), at(a, -EM_EDGE), at(a, 0.6), at(-a, 0.6)])
        back_r.append([at(-c, -1.0), at(c, -1.0), at(c, 4.0), at(c * 0.55, GOLD_BACK), at(-c * 0.55, GOLD_BACK),
                       at(-c, 4.0)])
        for rl, sgn in ((rail_l, -1), (rail_r, 1)):
            s0 = sgn * (width / 2 + 0.1)
            rl.append([at(s0 - 1.25, -rail), at(s0 + 1.25, -rail), at(s0 + 1.25, -0.5), at(s0 - 1.25, -0.5)])
        core_r.append([at(-width * 0.2, -front * 0.62), at(width * 0.2, -front * 0.62), at(width * 0.2, -front * 0.2),
                       at(-width * 0.2, -front * 0.2)])
    # pull the emerald back from the gold end caps, so the two never share a face
    for k, sgn, capped in ((0, 1, caps[0]), (n - 1, -1, caps[1])):
        if capped:
            tan = (pts[min(n - 1, k + 1)] - pts[max(0, k - 1)]).normalized() * sgn
            em_r[k] = [q + tan * 1.6 * S for q in em_r[k]]
            core_r[k] = [q + tan * 1.6 * S for q in core_r[k]]
    if clip is not None:
        lim = clip * S

        def flat(q):
            return Vector((max(q.x, lim) if clip > 0 else min(q.x, lim), q.y, q.z))
        em_r, back_r, rail_l, rail_r, core_r = ([[flat(q) for q in r] for r in rings]
                                                for rings in (em_r, back_r, rail_l, rail_r, core_r))
    loft(em, em_r, uv_v=[k / (n - 1) * 2 for k in range(n)])
    for rings in (back_r, rail_l, rail_r):
        loft(gold, rings)
    loft(glow, core_r)
    for k, sgn in ((0, -1), (n - 1, 1)):
        if not caps[0 if k == 0 else 1]:
            continue
        tan = (pts[min(n - 1, k + 1)] - pts[max(0, k - 1)]).normalized() * sgn
        side = Y.cross(tan).normalized()
        box(gold, pts[k] + tan * 0.4 * S + Y * (GOLD_BACK - rail) / 2 * S, tan, side, Y,
            1.4 * S, (width / 2 + 1.35) * S, (GOLD_BACK + rail) / 2 * S)


def build_symbol(em, gold, glow):
    # the S is cut where the bar crosses it, so the bar sits cleanly on top (as in the reference);
    # each piece ends exactly under the bar's gold rail, so no gap shows
    edge = BAR_W / 2 - 0.4
    pts = s_centerline(60)
    runs, run = [], []
    for k, (u, z) in enumerate(pts):
        if abs(u) > edge:
            if not run and k > 0 and abs(pts[k - 1][0]) <= edge:
                pu, pz = pts[k - 1]
                t = (math.copysign(edge, u) - pu) / (u - pu)
                run.append((pu + (u - pu) * t, pz + (z - pz) * t))
            run.append((u, z))
        elif run:
            pu, pz = run[-1]
            t = (math.copysign(edge, pu) - pu) / (u - pu)
            run.append((pu + (u - pu) * t, pz + (z - pz) * t))
            runs.append(run)
            run = []
    if run:
        runs.append(run)
    for run in runs:
        if len(run) > 1:
            side = 1 if sum(u for u, _ in run) > 0 else -1
            caps = (abs(run[0][0]) > edge + 0.01, abs(run[-1][0]) > edge + 0.01)   # the S's own ends only
            stroke(em, gold, glow, run, S_W, clip=side * edge, caps=caps)
    bar = [(0.0, BAR_TOP + (BAR_BOT - BAR_TOP) * k / 11) for k in range(12)]
    stroke(em, gold, glow, bar, BAR_W, front=EM_FRONT + 1.2)


# ---------------------------------------------------------------- finial, neck, shaft, foot

def build_finial(gold, rng):
    lathe(gold, [(54, 6.6), (55.5, 8.4), (60.5, 8.4), (62, 7.0)], sides=12, smooth=False)
    lathe(gold, [(46.5, 6.0), (49, 8.6), (52, 8.2), (54, 6.6)], sides=12, smooth=False)
    # the spearhead: an eight-sided star-cut point
    radii = [(9.5 if j % 2 == 0 else 6.6) * S for j in range(8)]
    rings = [ring_pts(P(0, 47.5), X, Y, [5.5 * S] * 8), ring_pts(P(0, 37), X, Y, radii, math.pi / 8), [P(0, 11)]]
    loft(gold, rings)
    # fleur-de-lis leaves curling out and up, and small spikes between them
    for k in range(4):
        a = math.radians(90 * k)
        radial = Vector((math.cos(a), math.sin(a), 0))
        tang = Z.cross(radial)
        pts = [P(0, v) + radial * r * S for v, r in ((50, 4.5), (48, 10), (45, 15.5), (40, 18.5), (34, 17))]
        plate(gold, smooth_path(pts, 3), lambda f: 9.5 * S * (1 - f) ** 0.6 * min(1, f * 5 + 0.35) if f < 1 else 0,
              lambda f: 1.6 * S * (1 - f * 0.6) if f < 1 else 0, lambda f, tang=tang: tang)
        b = math.radians(45 + 90 * k)
        rd = Vector((math.cos(b), math.sin(b), 0))
        thorn(gold, P(0, 50) + rd * 7 * S, rd * 0.5 + Z, 8 * S, 3.2 * S, wide=Z.cross(rd))


def gem_node(gold, em, glow, v, h, r, rng):
    """An emerald diamond set in a gold sleeve: cups at both ends and four prongs hugging the
    gem's diagonal edges, leaving diamond-shaped windows front, back and at the sides."""
    lathe(gold, [(v - h - 3.5, r + 1.6), (v - h - 1.5, r + 3.4), (v - h + 1.2, r + 2.4)], sides=16)
    lathe(gold, [(v + h - 1.2, r + 2.4), (v + h + 1.5, r + 3.4), (v + h + 3.5, r + 1.6)], sides=16)
    gem(em, P(0, v + h + 0.5), P(0, v - h - 0.5), r * S, rng, sides=8)
    gem(glow, P(0, v + h * 0.55), P(0, v - h * 0.55), r * 0.45 * S, rng, sides=6)
    for k in range(4):
        a = math.radians(45 + 90 * k)
        radial = Vector((math.cos(a), math.sin(a), 0))
        pts = [P(0, v - h - 1 + (2 * h + 2) * f) + radial * (r * 0.7 + r * 0.55 * math.sin(math.pi * f) + 0.8) * S
               for f in np.linspace(0, 1, 9)]
        plate(gold, pts, lambda f: 3.6 * S * (0.6 + 0.4 * math.sin(math.pi * f)), lambda f: 1.1 * S,
              lambda f, radial=radial: radial)


def build_neck(gold, em, glow, rng):
    lathe(gold, [(166, 7.6), (168, 9.2), (172, 9.0), (175, 7.0), (177, 6.4)], sides=16)
    lathe(gold, [(177, 6.4), (180, 7.8), (184, 8.2), (188, 7.6), (191, 6.0)], sides=16)
    for k in range(4):                       # little emeralds round the knot
        a = math.radians(90 * k)
        radial = Vector((math.cos(a), math.sin(a), 0))
        gem(em, P(0, 188) + radial * 7.6 * S, P(0, 179) + radial * 7.6 * S, 2.6 * S, rng, sides=4, flat=0.6,
            wide=Z.cross(radial))
    # four pointed wings flaring out under the knot
    for k in range(4):
        a = math.radians(90 * k)
        radial = Vector((math.cos(a), math.sin(a), 0))
        tang = Z.cross(radial)
        pts = [P(0, v) + radial * r * S for v, r in ((196, 4), (197, 10), (199, 16), (201, 20))]
        plate(gold, pts, lambda f: 9 * S * (1 - f) ** 0.8 if f < 1 else 0, lambda f: 1.8 * S * (1 - f * 0.6),
              lambda f, tang=tang: tang)
    lathe(gold, [(191, 6.0), (194, 8.0), (199, 7.2), (203, 6.0)], sides=16)
    gem_node(gold, em, glow, 219, 13, 5.2, rng)
    lathe(gold, [(236, 6.8), (238, 8.0), (241, 7.6), (243, 6.2)], sides=16)
    gem_node(gold, em, glow, 254, 8, 4.0, rng)
    lathe(gold, [(265, 6.2), (267, 8.0), (270, 8.0), (272, 6.6), (275, 7.4), (278, 7.4), (280, 6.6),
                 (283, 7.8), (286, 7.8), (289, 6.4)], sides=20)


def band_node(gold, em, v, rng):
    """A gold barrel band on the shaft with four small emeralds and pointed leaves above and below."""
    lathe(gold, [(v - 6, 6.8), (v - 4, 8.6), (v - 1.5, 9.3), (v + 1.5, 9.3), (v + 4, 8.6), (v + 6, 6.8)], sides=20)
    for k in range(4):
        a = math.radians(90 * k)
        radial = Vector((math.cos(a), math.sin(a), 0))
        tang = Z.cross(radial)
        gem(em, P(0, v + 4.5) + radial * 8.9 * S, P(0, v - 4.5) + radial * 8.9 * S, 2.5 * S, rng, sides=4, flat=0.55,
            wide=tang)
        for sgn in (-1, 1):
            pts = [P(0, v + sgn * (5 + 14 * f)) + radial * (6.9 - 0.4 * f) * S for f in np.linspace(0, 1, 6)]
            plate(gold, pts, lambda f: 6.5 * S * (1 - f) ** 0.8 if f < 1 else 0, lambda f: 1.1 * S,
                  lambda f, radial=radial: radial)


def build_shaft(dark, gold, em, glow, rng):
    sides = 20
    vs = np.linspace(SHAFT_TOP, SHAFT_BOT, 31)
    rings = [ring_pts(P(0, v), X, Y, [SHAFT_R * S] * sides) for v in vs]
    loft(dark, rings, uv_v=[(v - SHAFT_TOP) * 0.01 for v in vs], smooth=True)
    for v in BAND_NODES:
        band_node(gold, em, v, rng)
    # thin gold rings partway down, so the dark shaft is never plain
    for v in (400, 540):
        lathe(gold, [(v - 2, 6.4), (v - 1, 7.4), (v + 1, 7.4), (v + 2, 6.4)], sides=20)


def build_foot(gold, em, glow, rng):
    lathe(gold, [(580, 6.6), (582, 8.2), (588, 8.2), (590, 6.6)], sides=16)
    for k in range(4):                       # a small crown of points round the top of the foot
        a = math.radians(45 + 90 * k)
        radial = Vector((math.cos(a), math.sin(a), 0))
        thorn(gold, P(0, 582) + radial * 7 * S, Z * 1.0 + radial * 0.2, 9 * S, 3.4 * S, 1.6 * S, wide=Z.cross(radial))
    gem_node(gold, em, glow, 602, 9, 4.2, rng)
    lathe(gold, [(612, 6.6), (614, 8.0), (617, 8.0), (619, 6.2), (624, 7.0), (630, 8.8), (636, 7.4), (640, 6.2),
                 (642, 7.6), (645, 7.6), (647, 6.4), (650, 9.0), (653, 9.6)], sides=20)
    # the emerald diamond in its gold kite frames, front-back and side-side
    gem(em, P(0, 652), P(0, 699), 12.5 * S, rng, sides=8, mid=0.49)
    gem(glow, P(0, 663), P(0, 689), 5.5 * S, rng, sides=6)
    kite = [(0, 650), (8, 662), (14.4, 675), (8, 688), (0, 701), (-8, 688), (-14.4, 675), (-8, 662)]
    kite = smooth_path([(u, 0, v) for u, v in kite] + [(0, 0, 650)], 3)[:-1]
    for normal, flip in ((Y, False), (X, True)):
        pts = [P(0, p[2], p[0]) if flip else P(p[0], p[2]) for p in kite]
        loop_band(gold, pts, 1.7 * S, 2.2 * S, normal)
        for sgn in (-1, 1):                  # studs on the frame's side corners
            c = P(0, 675, sgn * 14.6) if flip else P(sgn * 14.6, 675)
            gem(gold, c - Z * 3.2 * S, c + Z * 3.2 * S, 2.6 * S, rng, sides=4)
    gem(gold, P(0, 695), P(0, TIP_V), 4.2 * S, rng, sides=4, mid=0.2)


# ---------------------------------------------------------------- orbit rings

def ring_basis(tilt, roll=0.0, yaw=0.0):
    """Unit vectors (a, b, normal) of a ring tilted `tilt` degrees about X (front part lower),
    then rolled about Y and turned about Z."""
    t, r, w = math.radians(tilt), math.radians(roll), math.radians(yaw)
    rot = Matrix.Rotation(w, 3, "Z") @ Matrix.Rotation(r, 3, "Y")
    a = rot @ X
    b = rot @ Vector((0, math.cos(t), math.sin(t)))
    return a, b, a.cross(b).normalized()


def orbit_ring(mb, R, basis, half_radial, half_axial, seg=72):
    a, b, n = basis
    c = D(0, 0)
    prof = [(1, 0), (0.5, 1), (-0.5, 1), (-1, 0), (-0.5, -1), (0.5, -1)]
    rings = []
    for k in range(seg):
        ph = 2 * math.pi * k / seg
        radial = a * math.cos(ph) + b * math.sin(ph)
        p = c + radial * R * S
        rings.append([p + radial * dr * half_radial * S + n * dn * half_axial * S for dr, dn in prof])
    idx = [[mb.add(q, (j / 6, k / seg)) for j, q in enumerate(rr)] for k, rr in enumerate(rings)]
    for k in range(seg):
        A, B = idx[k], idx[(k + 1) % seg]
        ph = 2 * math.pi * (k + 0.5) / seg
        cc = c + (a * math.cos(ph) + b * math.sin(ph)) * R * S
        for j in range(6):
            mb.out_face([A[j], A[(j + 1) % 6], B[(j + 1) % 6], B[j]], cc, True)


def build_rings(ring, rng):
    basis = ring_basis(RING_TILT, RING_ROLL)
    orbit_ring(ring, RING_R, basis, 1.3, 2.8)
    r2, tilt2, yaw2 = RING2
    orbit_ring(ring, r2, ring_basis(tilt2, 0, yaw2), 0.8, 1.4)
    # four-pointed gold stars riding the main ring
    a, b, n = basis
    for ph in (150, 30, -35, -125):
        p = math.radians(ph)
        radial = a * math.cos(p) + b * math.sin(p)
        tang = n.cross(radial)
        c = D(0, 0) + radial * (RING_R + 1.5) * S
        pts = [c + tang * 7 * S, c - tang * 7 * S, c + Z * 11 * S, c - Z * 11 * S,
               c + radial * 3.5 * S, c - radial * 2 * S]
        idx = [ring.add(q, (0.5, 0.5)) for q in pts]
        for i, j in ((0, 2), (2, 1), (1, 3), (3, 0)):
            for k in (4, 5):
                ring.out_face([idx[i], idx[j], idx[k]], c)
    return basis[2]


# ---------------------------------------------------------------- the weapon

PART_ORDER = ["Shaft", "Gold", "Ring", "Emerald", "Glow"]


def clean_mesh(ob):
    """Drop degenerate faces and make every normal point outward. (No vertex merging: pieces
    are built without duplicates, and the money symbol's strokes are flattened against the bar,
    where merging would weld separate pieces together.)"""
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=1e-7)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(ob.data)
    bm.free()
    ob.data.update()


def build_weapon():
    rng = np.random.default_rng(11)
    mbs = {name: MB() for name in PART_ORDER}
    build_symbol(mbs["Emerald"], mbs["Gold"], mbs["Glow"])
    build_finial(mbs["Gold"], rng)
    build_neck(mbs["Gold"], mbs["Emerald"], mbs["Glow"], rng)
    build_shaft(mbs["Shaft"], mbs["Gold"], mbs["Emerald"], mbs["Glow"], rng)
    build_foot(mbs["Gold"], mbs["Emerald"], mbs["Glow"], rng)
    ring_axis = build_rings(mbs["Ring"], rng)
    parts = {name: mbs[name].to_object(name) for name in PART_ORDER}
    for ob in parts.values():
        clean_mesh(ob)
    return parts, ring_axis


# ---------------------------------------------------------------- aura (separate objects)

def spiral_points(i, n=120):
    v0, v1, turns, phase, r0, rmax, _ = SPIRALS[i]
    pts = []
    for k in range(n):
        f = k / (n - 1)
        th = phase + 2 * math.pi * turns * f
        r = (r0 + rmax * math.sin(math.pi * f) ** 0.8) * (1 + 0.1 * math.sin(f * 6 + i * 2))
        pts.append(Vector((math.cos(th) * r, math.sin(th) * r, P(0, v0 + (v1 - v0) * f).z)))
    return pts


def ribbon(mb, pts, width_fn, normal_fn):
    """Flat ribbon along a path; normal_fn(f, p) gives the ribbon's face direction."""
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
    """Two quads crossed at 90 degrees, so a sprite reads from every side."""
    c = Vector(centre)
    for k in range(2):
        a = yaw + math.pi / 2 * k
        side = Vector((math.cos(a), math.sin(a), 0))
        q = [mb.add(c - side * width / 2 - Z * height / 2, (0, 0)), mb.add(c + side * width / 2 - Z * height / 2, (1, 0)),
             mb.add(c + side * width / 2 + Z * height / 2, (1, 1)), mb.add(c - side * width / 2 + Z * height / 2, (0, 1))]
        mb.face(q)


def build_aura(mats):
    rng = np.random.default_rng(23)
    obs = {}
    # thin emerald strands spiralling up the shaft into the head
    mb = MB()
    for i, sp in enumerate(SPIRALS):
        ribbon(mb, spiral_points(i), lambda f, w=sp[6]: 0.012 + w * math.sin(math.pi * f) ** 0.8,
               lambda f, p: Vector((p.x, p.y, 0)).normalized())
    obs["AuraSpirals"] = mb.to_object("AuraSpirals")
    set_material(obs["AuraSpirals"], mats["Wisp"])
    # a faint, wider mist under the strands, for a soft glow rather than hard lines
    mb = MB()
    for i, sp in enumerate(SPIRALS):
        ribbon(mb, spiral_points(i), lambda f, w=sp[6]: 0.04 + w * 3.2 * math.sin(math.pi * f) ** 0.8,
               lambda f, p: Vector((p.x, p.y, 0)).normalized())
    obs["AuraMist"] = mb.to_object("AuraMist")
    set_material(obs["AuraMist"], mats["Mist"])
    # energy arcs orbiting the money symbol alongside the gold rings
    mb = MB()
    for R, tilt, yaw, start, span, w in ((0.82, 34, 15, 0.3, 4.1, 0.05), (0.9, -18, 100, 2.2, 3.6, 0.035),
                                         (0.74, 55, -40, 4.0, 3.2, 0.03)):
        a, b, n = ring_basis(tilt, 0, yaw)
        pts = [D(0, 0) + (a * math.cos(start + span * f) + b * math.sin(start + span * f)) * R * RING_R * S
               for f in np.linspace(0, 1, 60)]
        ribbon(mb, pts, lambda f, w=w: w * math.sin(math.pi * f) ** 0.7, lambda f, p, n=n: n)
    obs["AuraOrbits"] = mb.to_object("AuraOrbits")
    set_material(obs["AuraOrbits"], mats["Wisp"])
    # sparkles, motes and little money symbols, close to the weapon
    spark, motes, dollars = MB(), MB(), MB()
    head = D(0, 0)
    for k in range(14):
        if k < 9:
            a = rng.uniform(0, 2 * math.pi)
            c = head + Vector((math.cos(a) * rng.uniform(0.45, 0.8), math.sin(a) * rng.uniform(0.2, 0.5),
                               rng.uniform(-0.6, 0.6)))
        else:
            c = P(0, rng.uniform(220, 640)) + Vector((rng.uniform(-0.25, 0.25), rng.uniform(-0.2, 0.2), 0))
        sz = rng.uniform(0.06, 0.13)
        crossed_card(spark, c, sz, sz, rng.uniform(0, 3))
    for k in range(40):
        i = k % len(SPIRALS)
        pts = spiral_points(i, 60)
        c = pts[int(rng.integers(5, 55))] + Vector((rng.normal(0, 0.03), rng.normal(0, 0.03), rng.normal(0, 0.05)))
        if k >= 30:
            a = rng.uniform(0, 2 * math.pi)
            c = head + Vector((math.cos(a) * rng.uniform(0.3, 0.75), math.sin(a) * rng.uniform(0.2, 0.5),
                               rng.uniform(-0.5, 0.5)))
        sz = rng.uniform(0.025, 0.05)
        crossed_card(motes, c, sz, sz, rng.uniform(0, 3))
    for k in range(5):
        a = math.radians(30 + 72 * k)
        c = head + Vector((math.cos(a) * 0.62, math.sin(a) * 0.35, rng.uniform(-0.35, 0.5)))
        sz = rng.uniform(0.11, 0.16)
        crossed_card(dollars, c, sz, sz, rng.uniform(0, 3))
    for name, mb, mat in (("AuraSparkles", spark, "Sparkle"), ("AuraMotes", motes, "Mote"),
                          ("AuraDollars", dollars, "Dollar")):
        obs[name] = mb.to_object(name)
        set_material(obs[name], mats[mat])
    # a soft emerald glow round the head and the foot gem
    mb = MB()
    crossed_card(mb, head, 1.45, 1.45)
    crossed_card(mb, P(0, 676), 0.38, 0.45)
    obs["AuraGlow"] = mb.to_object("AuraGlow")
    set_material(obs["AuraGlow"], mats["Glow"])
    return obs


# ---------------------------------------------------------------- textures, materials, layout

def textures():
    os.makedirs(TEXTURES, exist_ok=True)

    def save(name, arr, colorspace="sRGB"):
        return np_image(name, arr, os.path.join(TEXTURES, name + ".png"), colorspace)
    imgs = {
        "emerald": save("emerald_color", mt.emerald()),
        "emerald_mr": save("emerald_mr", mt.emerald_mr(), "Non-Color"),
        "gold": save("gold_color", mt.gold()),
        "gold_mr": save("gold_mr", mt.gold_mr(), "Non-Color"),
        "dark": save("dark_color", mt.dark()),
        "dark_mr": save("dark_mr", mt.dark_mr(), "Non-Color"),
    }
    for key, fn in mt.AURA.items():
        imgs["fx_" + key] = save("fx_" + key.lower(), fn())
    return imgs


def materials(imgs):
    gold = metal_material("PolishedGold", imgs["gold"], imgs["gold_mr"])
    return {
        "Shaft": metal_material("DarkMetal", imgs["dark"], imgs["dark_mr"]),
        "Gold": gold,
        "Ring": gold,
        "Emerald": crystal_material("Emerald", imgs["emerald"], imgs["emerald_mr"], glow_strength=0.22,
                                    transmission=0.5),
        "Glow": glow_material("EmeraldGlow", (0.2, 1.0, 0.32), 2.2),
        "Wisp": fx_material("AuraWisp", imgs["fx_Wisp"], 1.5),
        "Mist": fx_material("AuraMist", imgs["fx_Wisp"], 0.35),
        "Sparkle": fx_material("AuraSparkle", imgs["fx_Sparkle"], 2.5),
        "Mote": fx_material("AuraMote", imgs["fx_Mote"], 2.0),
        "Dollar": fx_material("AuraDollar", imgs["fx_Dollar"], 1.8),
        "AuraGlow": fx_material("AuraGlow", imgs["fx_Glow"], 0.45),
    }


def layout(report, ring_axis):
    info = {
        "units": "studs", "studsPerPixel": S,
        "points": {
            "Head": list(D(0, 0)), "Grip": list(P(0, GRIP_V)), "ShaftTop": list(P(0, SHAFT_TOP)),
            "ShaftBottom": list(P(0, SHAFT_BOT)), "Tip": list(P(0, TIP_V)), "Finial": list(P(0, 11)),
            "FootGem": list(P(0, 676)), "UpperGem": list(P(0, 219)),
        },
        "ringAxis": [round(c, 5) for c in ring_axis],
        "spirals": [[[round(c, 4) for c in p] for p in spiral_points(i, 41)] for i in range(len(SPIRALS))],
        "spiralWidths": [sp[6] for sp in SPIRALS],
        "meshReport": report,
    }
    with open(os.path.join(EXPORT, "staff_layout.json"), "w") as f:
        json.dump(info, f, indent=1)
    return info


# ---------------------------------------------------------------- previews

def render_previews(parts, aura, imgs, only=None):
    os.makedirs(PREVIEWS, exist_ok=True)
    sc = bpy.context.scene
    sc.cycles.samples = 48
    sc.cycles.use_denoising = True
    sc.cycles.transparent_max_bounces = 64
    sc.cycles.max_bounces = 10
    sc.cycles.glossy_bounces = 6
    sc.view_settings.view_transform = "Standard"
    world = bpy.data.worlds.new("Studio")
    sc.world = world
    wnt = nodes_of(world)
    bg = wnt.nodes.new("ShaderNodeBackground")                     # what the camera sees
    bg.inputs["Color"].default_value = (0.022, 0.026, 0.024, 1)
    env = wnt.nodes.new("ShaderNodeBackground")                    # what the gold reflects: a soft studio
    coord = wnt.nodes.new("ShaderNodeTexCoord")
    sep = wnt.nodes.new("ShaderNodeSeparateXYZ")
    ramp = wnt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.3
    ramp.color_ramp.elements[0].color = (0.02, 0.025, 0.02, 1)
    ramp.color_ramp.elements[1].position = 0.85
    ramp.color_ramp.elements[1].color = (1.0, 0.95, 0.85, 1)
    el = ramp.color_ramp.elements.new(0.55)
    el.color = (0.12, 0.3, 0.16, 1)
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

    def light(name, loc, energy, color, size, target=(0, 0, -1.2)):
        ld = bpy.data.lights.new(name, "AREA")
        ld.energy, ld.color, ld.size = energy, color, size
        lo = bpy.data.objects.new(name, ld)
        lo.location = loc
        lo.rotation_euler = (Vector(target) - lo.location).to_track_quat("-Z", "Y").to_euler()
        sc.collection.objects.link(lo)

    light("Key", (-3.5, -5, 3), 520, (1.0, 0.94, 0.85), 3)
    light("Fill", (4, -4, -1), 160, (0.85, 1.0, 0.88), 4)
    light("RimL", (-4, 5, 2), 420, (0.4, 1.0, 0.5), 3)
    light("RimR", (4, 5, -1), 380, (1.0, 0.85, 0.5), 3)
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
            bloom(path, strength=glow, threshold=0.62)
        print("rendered", path)

    def show_aura(on):
        for ob in aura.values():
            ob.hide_render = not on

    mid_z = P(0, 362).z
    full = (480, 1460)
    ortho = 730 * S
    show_aura(False)
    shot("model_front", (0, -20, mid_z), (0, 0, mid_z), full, ortho=ortho, glow=0.35)
    show_aura(True)
    shot("front", (0, -20, mid_z), (0, 0, mid_z), full, ortho=ortho)
    shot("back", (0, 20, mid_z), (0, 0, mid_z), full, ortho=ortho)
    shot("left", (-20, 0, mid_z), (0, 0, mid_z), full, ortho=ortho)
    shot("right", (20, 0, mid_z), (0, 0, mid_z), full, ortho=ortho)
    shot("angle", (-2.8, -7.0, 0.9), (0, 0, -2.25), (900, 1400), lens=40)
    shot("head_closeup", (-0.75, -2.5, 0.45), (0, 0, -0.08), (1000, 1100), lens=50)
    shot("shaft_closeup", (0.45, -1.35, P(0, 225).z + 0.12), (0, 0, P(0, 236).z), (800, 1000), lens=50)
    shot("bottom_closeup", (0.5, -1.45, P(0, 615).z + 0.2), (0, 0, P(0, 650).z), (800, 1000), lens=50)
    shot("aura_full", (2.6, -7.0, 0.5), (0, 0, -2.25), (900, 1400), lens=40, glow=0.6)

    # in game: standing on a grey baseplate under a blue sky, like the reference sheet
    if only and "ingame" not in only:
        return
    floor_z = P(0, TIP_V).z
    mb = MB()
    q = [mb.add((-14, -14, floor_z), (0, 0)), mb.add((14, -14, floor_z), (1, 0)), mb.add((14, 14, floor_z), (1, 1)),
         mb.add((-14, 14, floor_z), (0, 1))]
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
    bg.inputs["Color"].default_value = (0.25, 0.5, 0.95, 1)
    shot("ingame", (-2.2, -8.8, -1.4), (-0.1, 0, -2.6), (900, 1300), lens=40, glow=0.35)


def main(render=False, only=None):
    clean_scene()
    parts, ring_axis = build_weapon()
    imgs = textures()
    mats = materials(imgs)
    for name in PART_ORDER:
        set_material(parts[name], mats[name])
    report = mesh_report(parts)
    aura = build_aura({"Wisp": mats["Wisp"], "Mist": mats["Mist"], "Sparkle": mats["Sparkle"], "Mote": mats["Mote"],
                       "Dollar": mats["Dollar"], "Glow": mats["AuraGlow"]})
    marks = [marker("Mark_O", (0, 0, 0)), marker("Mark_Y", (0, 1, 0)), marker("Mark_Z", (0, 0, 1))]
    export([parts[n] for n in PART_ORDER] + marks, "MoneyStaff")
    for m in marks:
        bpy.data.objects.remove(m)
    export(list(aura.values()), "MoneyStaffAura")
    carriers = build_vfx_carriers(imgs)
    export(list(carriers.values()), "MoneyStaffVFX")
    for ob in carriers.values():
        ob.hide_render = True
        ob.hide_set(True)
    info = layout(report, ring_axis)
    with open(os.path.join(EXPORT, "mesh_report.json"), "w") as f:
        json.dump(report, f, indent=1)
    print(json.dumps(report, indent=1))
    for img in bpy.data.images:
        if img.filepath_raw and not img.packed_file and os.path.exists(bpy.path.abspath(img.filepath_raw)):
            img.pack()
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(EXPORT, "MoneyStaff.blend"), compress=True)
    if render:
        render_previews(parts, aura, imgs, only)
    return info


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    shots = next((a.split("=", 1)[1].split(",") for a in argv if a.startswith("--shots=")), None)
    main(render="--render" in argv or shots is not None, only=shots)
