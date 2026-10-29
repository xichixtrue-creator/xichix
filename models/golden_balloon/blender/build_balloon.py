"""
Golden King Balloon - Blender build script.

Recreates the golden balloon from the reference sheet as a Roblox balloon cosmetic: a large,
slightly tall metallic gold balloon with a glossy highlight, a gold nozzle and string; a royal
king's crown of polished gold (a grooved band set with diamond-shaped gems, tall framed points
with gems, gold balls on every tip); and two big layered angel wings of white / ivory feathers
with gold bases, sweeping back and out. The golden aura is built as separate objects
(GoldenAura, GoldenParticles, Sparkles, EnergyTrails).

Every outline was measured from the reference sheet's front view:
    u = pixels across (right +, the balloon's axis at 0), v = pixels down (the balloon's centre at v = 0)

Run it either way:
  * Blender: Scripting tab > Open > build_balloon.py > Run Script (starts a new scene)
  * Headless: python build_balloon.py [--render] [--shots=front,angle]   (with the `bpy` module)

Writes ../export (GoldenKingBalloon.fbx/.glb, GoldenBalloonAura.fbx/.glb, GoldenBalloonVFX.fbx/.glb,
.blend, balloon_layout.json, mesh_report.json), ../textures and ../previews.

Units are Roblox studs (0.017 studs per reference pixel: the balloon is 1.8 studs across).
Axes: up +Z, the front (the crown's big gem) facing -Y. The origin is the balloon's centre,
which is the model's pivot.
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
import balloon_textures as bt  # noqa: E402

ROOT = os.path.normpath(os.path.join(HERE, ".."))
EXPORT = os.path.join(ROOT, "export")
TEXTURES = os.path.join(ROOT, "textures")
PREVIEWS = os.path.join(ROOT, "previews")

S = 0.017                        # studs per reference pixel
X = Vector((1, 0, 0))
Y = Vector((0, 1, 0))
Z = Vector((0, 0, 1))

# the crown's gold texture is an atlas: polished gold on the left half, the darker recessed gold
# between the raised borders on the right
UV_GOLD = (0.0, 0.0, 0.5, 1.0)
UV_RECESS = (0.5, 0.0, 0.5, 1.0)


def P(u, v, y=0.0):
    """Reference pixels (u across, v down, y depth towards the back) to Blender studs."""
    return Vector((u * S, y * S, -v * S))


# ---------------------------------------------------------------- measurements (reference pixels)

# the balloon's radius down its height: a little taller than wide, fullest just above the middle,
# tapering to the neck
BALLOON_R = [(-64, 0.0), (-62.5, 11), (-59, 21), (-52, 32), (-41, 42), (-27, 49.5), (-10, 52.2), (6, 51.4),
             (20, 47), (32, 39.5), (42, 30), (49, 21), (53.5, 14), (56, 9.5), (57.5, 7.6), (59.5, 7.0)]
BALLOON_BOTTOM = 60.5
NOZZLE = [(55, 5.8), (57, 7.4), (59.5, 7.9), (63, 7.6), (65.5, 7.9), (67, 9.0), (69, 9.4), (70.8, 8.6),
          (71.6, 6.6), (71.6, 3.2), (70.6, 1.8)]
STRING = [(0, 66), (-0.6, 80), (-1.4, 96), (0.4, 112), (2.2, 128), (2.0, 144), (3.6, 158), (7.0, 170), (10.5, 176)]
STRING_R = 2.0
# the crown: band from v -43.5 to -66.5 on a slight flare, points rising from the band's top
BAND_BOT, BAND_TOP = -43.5, -66.5
# crown points: (angle round from the front, degrees; height above the band; half angle at the base;
# ball radius; gem)
CROWN_POINTS = [(0, 48, 27, 5.6, "big"), (180, 48, 27, 5.6, "big"),
                (60, 35, 27, 4.6, "small"), (-60, 35, 27, 4.6, "small"),
                (120, 35, 27, 4.6, "small"), (-120, 35, 27, 4.6, "small")]
CROWN_MINOR = [(a, 22, 12, 3.4) for a in (30, -30, 90, -90, 150, -150)]
BAND_GEMS = 18
# the wings: root (inside the balloon's side), sweep back, and the outline of the feather fan:
# (direction in the wing's plane, degrees up from straight out; reach from the root)
WING_ROOT = (40, -22, 14)
WING_SWEEP = 24
WING_CURL = 0.0011
WING_OUTLINE = [(-80, 74), (-56, 86), (-35, 96), (-15, 108), (0, 117), (15, 121), (28, 127), (37, 134), (46, 126)]
# ---------------------------------------------------------------- mesh builder


class MB:
    def __init__(self):
        self.v, self.f, self.uv, self.smooth, self.fuv = [], [], [], [], []

    def add(self, p, uv=(0.0, 0.0)):
        self.v.append(tuple(p))
        self.uv.append(tuple(uv))
        return len(self.v) - 1

    def face(self, idx, smooth=False, uvs=None):
        """uvs: optional UV per corner (overrides the vertices' UVs, for texture seams)."""
        self.f.append(tuple(idx))
        self.smooth.append(smooth)
        self.fuv.append(tuple(uvs) if uvs else None)

    def newell(self, idx):
        n = Vector()
        for i in range(len(idx)):
            p, q = Vector(self.v[idx[i]]), Vector(self.v[idx[(i + 1) % len(idx)]])
            n += Vector(((p.y - q.y) * (p.z + q.z), (p.z - q.z) * (p.x + q.x), (p.x - q.x) * (p.y + q.y)))
        return n

    def out_face(self, idx, centre, smooth=False, uvs=None):
        """Add a face, wound so its normal points away from `centre`."""
        mid = sum((Vector(self.v[i]) for i in idx), Vector()) / len(idx)
        if self.newell(idx).dot(mid - Vector(centre)) < 0:
            idx = list(reversed(idx))
            uvs = list(reversed(uvs)) if uvs else None
        self.face(idx, smooth, uvs)

    def to_object(self, name):
        me = bpy.data.meshes.new(name)
        me.from_pydata(self.v, [], self.f)
        me.validate()
        uvl = me.uv_layers.new(name="UVMap")
        for poly, sm, fu in zip(me.polygons, self.smooth, self.fuv):
            poly.use_smooth = sm
            for k, li in enumerate(poly.loop_indices):
                uvl.data[li].uv = fu[k] if fu else self.uv[me.loops[li].vertex_index]
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


def loft(mb, rings, uv_v=None, tri=False, smooth=False, uv_u=1.0, uvs=None):
    """Skin rings (lists of points, equal length; a one-point list is an apex) into a closed solid.
    tri=True splits quads into triangles with alternating diagonals (crisp crystal facets).
    uvs: optional explicit UV per point (same shape as rings)."""
    keep = [k for k, r in enumerate(rings) if not (len(r) == 1 and k and len(rings[k - 1]) == 1)]
    rings = [rings[k] for k in keep]
    uvs = [uvs[k] for k in keep] if uvs else None
    n = len(rings)
    idx = []
    for k, ring in enumerate(rings):
        vv = uv_v[k] if uv_v else k / (n - 1)
        if uvs:
            idx.append([mb.add(p, uvs[k][j]) for j, p in enumerate(ring)])
        elif len(ring) == 1:
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
    for i, key in enumerate(bt.AURA):
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


def uv_region(mb, i0, rect):
    """Squeeze the UVs of the vertices added since index i0 into one column of the gold atlas."""
    u0, _, du, _ = rect
    for i in range(i0, len(mb.uv)):
        u, v = mb.uv[i]
        mb.uv[i] = (u0 + du * (0.02 + 0.96 * min(max(u, 0.0), 1.0)), v)


def clean_mesh(ob):
    """Drop degenerate faces and make every normal point outward."""
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=1e-7)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(ob.data)
    bm.free()
    ob.data.update()


def around(a_deg, r, v):
    """A point on a circle round the balloon's axis, `a_deg` degrees from the front towards its
    right as you look at it (+X), radius r and height v (pixels)."""
    a = math.radians(a_deg)
    return P(r * math.sin(a), v, -r * math.cos(a))


def outward(a_deg):
    a = math.radians(a_deg)
    return Vector((math.sin(a), -math.cos(a), 0))


def rightward(a_deg):
    """Right, for someone outside the crown looking at it from angle a."""
    a = math.radians(a_deg)
    return Vector((math.cos(a), math.sin(a), 0))


def lathe(mb, profile, sides=24, smooth=True):
    """Turned part from (v, radius px) pairs, top to bottom; radius 0 is a pole."""
    rings = [[P(0, v)] if r < 1e-6 else ring_pts(P(0, v), X, Y, [r * S] * sides) for v, r in profile]
    loft(mb, rings, uv_v=[(v - profile[0][0]) * 0.02 for v, _ in profile], smooth=smooth)


def revolve(mb, loop, sides=64, smooth=None):
    """A ring-shaped solid: the closed (radius, v) outline `loop` swept round the balloon's axis.
    smooth: indices of the outline segments to shade smooth (the rounded rims)."""
    n = len(loop)
    rc = sum(r for r, _ in loop) / n
    vc = sum(v for _, v in loop) / n
    idx = [[mb.add(around(360 * j / sides, r, v), (j / sides, k / n)) for j in range(sides)]
           for k, (r, v) in enumerate(loop)]
    for k in range(n):
        A, B = idx[k], idx[(k + 1) % n]
        sm = smooth is not None and k in smooth
        for j in range(sides):
            mb.out_face([A[j], A[(j + 1) % sides], B[(j + 1) % sides], B[j]],
                        around(360 * (j + 0.5) / sides, rc, vc), sm)


def tube(mb, pts, radius, sides=8, smooth=True):
    """Round tube along a path (parallel-transported cross-sections, flat ends)."""
    pts = [Vector(p) for p in pts]
    n = len(pts)
    rings, s1 = [], None
    for k, p in enumerate(pts):
        t = (pts[min(k + 1, n - 1)] - pts[max(k - 1, 0)]).normalized()
        if s1 is None:
            s1, _ = frame(t)
        s1 = (s1 - t * s1.dot(t)).normalized()
        rings.append(ring_pts(p, s1, t.cross(s1), [radius] * sides))
    loft(mb, rings, smooth=smooth)


def rail(mb, pts, normals, half_w, half_t, closed=False):
    """A raised border: a bar with a bevelled six-sided cross-section along a path, lying on the
    surface whose outward normals are given."""
    pts = [Vector(p) for p in pts]
    n = len(pts)
    rings = []
    for k, p in enumerate(pts):
        if closed:
            t = (pts[(k + 1) % n] - pts[k - 1]).normalized()
        else:
            t = (pts[min(k + 1, n - 1)] - pts[max(k - 1, 0)]).normalized()
        nrm = Vector(normals[k])
        nrm = (nrm - t * nrm.dot(t)).normalized()
        side = t.cross(nrm).normalized()
        rings.append([p + side * half_w, p + side * half_w * 0.5 + nrm * half_t, p - side * half_w * 0.5 + nrm * half_t,
                      p - side * half_w, p - side * half_w * 0.5 - nrm * half_t, p + side * half_w * 0.5 - nrm * half_t])
    if not closed:
        loft(mb, rings)
        return
    idx = [[mb.add(q, (j / 6, k / n)) for j, q in enumerate(r)] for k, r in enumerate(rings)]
    for k in range(n):
        A, B = idx[k], idx[(k + 1) % n]
        c = (pts[k] + pts[(k + 1) % n]) / 2
        for j in range(6):
            mb.out_face([A[j], A[(j + 1) % 6], B[(j + 1) % 6], B[j]], c)


def sphere(mb, centre, r, seg=12, rows=7):
    c = Vector(centre)
    rings = [[c + Z * r]]
    for k in range(1, rows):
        a = math.pi * k / rows
        rings.append(ring_pts(c + Z * r * math.cos(a), X, Y, [r * math.sin(a)] * seg))
    rings.append([c - Z * r])
    loft(mb, rings, smooth=True)


def facet_gem(mb, centre, right, up, normal, outline, height, depth, table_scale=0.5):
    """A cut gem set on a surface: a pointed pavilion sunk into it, a girdle, crown facets and a
    flat table. outline: (x, y) pixels in the right / up plane."""
    c = Vector(centre)

    def ring(scale, lift):
        return [c + (right * x + up * y) * scale * S + normal * lift * S for x, y in outline]
    loft(mb, [[c - normal * depth * S], ring(1.0, 0.0), ring(1.0, height * 0.3), ring(table_scale, height)], tri=True)


def rhombus(half_w, half_h, n_side=2):
    """A diamond (rhombus) outline with extra points along each side, so the cut has more facets."""
    corners = [(0, half_h), (half_w, 0), (0, -half_h), (-half_w, 0)]
    pts = []
    for i in range(4):
        (x0, y0), (x1, y1) = corners[i], corners[(i + 1) % 4]
        for k in range(n_side):
            t = k / n_side
            pts.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t))
    return pts


# ---------------------------------------------------------------- the balloon

def build_balloon(mb, sides=48, n=46):
    """Turned balloon with a clean UV seam at the back: u round (0.5 = the front), v down (by arc
    length), so the painted tones and highlight sit where they should."""
    f = table(BALLOON_R)
    v0, v1 = BALLOON_R[0][0], BALLOON_R[-1][0]
    vs = [v0 + (v1 - v0) * (0.5 - 0.5 * math.cos(math.pi * k / (n - 1))) for k in range(n)]
    prof = [(v, f(v)) for v in vs]
    prof[0] = (v0, 0.0)
    prof.append((BALLOON_BOTTOM, 0.0))
    arc = [0.0]
    for (va, ra), (vb, rb) in zip(prof, prof[1:]):
        arc.append(arc[-1] + math.hypot(vb - va, rb - ra))
    vv = [a / arc[-1] for a in arc]
    rings = []
    for v, r in prof:
        if r < 1e-6:
            rings.append([mb.add(P(0, v), (0.5, 0.0))])
        else:
            rings.append([mb.add(P(r * math.sin(2 * math.pi * j / sides), v, r * math.cos(2 * math.pi * j / sides)))
                          for j in range(sides)])
    for k in range(len(rings) - 1):
        A, B = rings[k], rings[k + 1]
        c = P(0, (prof[k][0] + prof[k + 1][0]) / 2)
        for j in range(sides):
            j1 = (j + 1) % sides
            u0, u1 = j / sides, (j + 1) / sides
            if len(A) == 1:
                mb.out_face([A[0], B[j], B[j1]], c, True, [((u0 + u1) / 2, vv[k]), (u0, vv[k + 1]), (u1, vv[k + 1])])
            elif len(B) == 1:
                mb.out_face([A[j], A[j1], B[0]], c, True, [(u0, vv[k]), (u1, vv[k]), ((u0 + u1) / 2, vv[k + 1])])
            else:
                mb.out_face([A[j], A[j1], B[j1], B[j]], c, True,
                            [(u0, vv[k]), (u1, vv[k]), (u1, vv[k + 1]), (u0, vv[k + 1])])


def build_nozzle(mb):
    lathe(mb, [(NOZZLE[0][0], 0.0)] + NOZZLE + [(NOZZLE[-1][0], 0.0)], sides=24)


def string_points():
    pts = smooth_path([(u, 0, v) for u, v in STRING], 5)
    return [P(p[0], p[2], 1.5 * math.sin(p[2] * 0.06)) for p in pts]


def build_string(mb):
    tube(mb, string_points(), STRING_R * S, sides=8)


# ---------------------------------------------------------------- the crown

def band_radius(v):
    return 42.0 + (BAND_BOT - v) * 0.1          # the band flares out a little towards the top


def cone_r(h):
    return band_radius(BAND_TOP) - 0.6 + 0.17 * h   # the points lean outward as they rise


def cone_pt(a, h, dr=0.0):
    return around(a, cone_r(h) + dr, BAND_TOP - h)


def surface_normal(p):
    """Outward normal of the crown's flared surface at a point."""
    return (Vector((p.x, p.y, 0)).normalized() - Z * 0.17).normalized()


def cone_frame(a, h):
    right = rightward(a)
    up = (cone_pt(a, h + 1) - cone_pt(a, h)).normalized()
    return right, up, right.cross(up).normalized()


def build_band(gold, gems):
    """The circlet: rounded rims top and bottom, a fine groove inside each, a flat face set with a
    row of diamond-shaped gems in raised gold bezels."""
    prof = [(0.0, -43.5), (1.4, -44.5), (2.0, -46.5), (1.4, -48.5), (0.3, -49.5), (0.9, -50.5), (0.9, -59.5),
            (0.3, -60.5), (1.4, -61.5), (2.0, -63.5), (1.4, -65.5), (0.0, -66.5)]
    loop = [(band_radius(v) + dr, v) for dr, v in prof]
    loop += [(band_radius(-66.5) - 3.0, -66.5), (band_radius(-55) - 3.2, -55), (band_radius(-43.5) - 3.0, -43.5)]
    i0 = len(gold.uv)
    revolve(gold, loop, sides=72, smooth={0, 1, 2, 3, 8, 9, 10})
    gem_v = -55
    outline = rhombus(2.7, 3.9)
    for i in range(BAND_GEMS):
        a = 360 * i / BAND_GEMS
        r = band_radius(gem_v) + 0.9
        c = around(a, r, gem_v)
        right, up, nrm = rightward(a), Z, outward(a)
        facet_gem(gems, c, right, up, nrm, outline, 1.9, 1.0)
        bez = [c + (right * x + up * y) * 1.28 * S + nrm * 0.15 * S for x, y in rhombus(2.7, 3.9, 2)]
        rail(gold, bez, [nrm] * len(bez), 0.6 * S, 0.55 * S, closed=True)
    uv_region(gold, i0, UV_GOLD)


def crown_plate(gold, a, beta0, H, t=1.2, m=5, n=7, h0=-3.0, dr=0.0):
    """One point of the crown: a curved triangular plate following the band's flare (the darker
    recessed gold)."""
    i0 = len(gold.uv)

    def beta(h):
        return beta0 * (1 - max(h, 0.0) / H)
    hs = [h0 + (H - h0) * k / n for k in range(n)]
    idx = []
    for h in hs:
        angs = [a + beta(h) * (2 * j / (m - 1) - 1) for j in range(m)]
        vv = (h - h0) / (H - h0)
        idx.append(([gold.add(cone_pt(q, h, dr + t), (j / (m - 1), vv)) for j, q in enumerate(angs)],
                    [gold.add(cone_pt(q, h, dr - t), (j / (m - 1), vv)) for j, q in enumerate(angs)], angs))
    apex = gold.add(cone_pt(a, H, dr), (0.5, 1.0))
    for k in range(n):
        F, B, angs = idx[k]
        hm = hs[k] + (H - h0) / n * 0.5
        for j in range(m - 1):
            c = cone_pt((angs[j] + angs[j + 1]) / 2, hm, dr)
            if k < n - 1:
                F2, B2, _ = idx[k + 1]
                gold.out_face([F[j], F[j + 1], F2[j + 1], F2[j]], c)
                gold.out_face([B[j], B[j + 1], B2[j + 1], B2[j]], c)
            else:
                gold.out_face([F[j], F[j + 1], apex], c)
                gold.out_face([B[j], B[j + 1], apex], c)
        c = cone_pt(a, hm, dr)
        for e in (0, m - 1):
            if k < n - 1:
                F2, B2, _ = idx[k + 1]
                gold.out_face([F[e], B[e], B2[e], F2[e]], c)
            else:
                gold.out_face([F[e], B[e], apex], c)
    F, B, angs = idx[0]
    for j in range(m - 1):
        gold.out_face([F[j], F[j + 1], B[j + 1], B[j]], cone_pt((angs[j] + angs[j + 1]) / 2, hs[1], dr))
    uv_region(gold, i0, UV_RECESS)

    def edge(h, s, inset=0.0, lift=0.0):
        """A point on the plate's left (s = -1) or right edge, `inset` pixels in from it."""
        r = cone_r(h) + dr + t + lift
        ang = a + s * (beta(h) - math.degrees(inset / r))
        return around(ang, r, BAND_TOP - h)
    return edge, beta


def build_point(gold, gems, a, H, beta0, ball_r, gem, dr=0.0, rail_w=1.7):
    edge, beta = crown_plate(gold, a, beta0, H, dr=dr)
    i0 = len(gold.uv)
    # the raised gold border up both sides, meeting under the ball
    hs = list(np.linspace(-2.0, H - 2.5, 9))
    path = [edge(h, -1, rail_w * 0.55, 0.5) for h in hs] + [cone_pt(a, H, dr + 1.7)] + \
        [edge(h, 1, rail_w * 0.55, 0.5) for h in reversed(hs)]
    rail(gold, path, [surface_normal(p) for p in path], rail_w * S, 1.1 * S)
    # the gold ball on the tip
    sphere(gold, cone_pt(a, H + ball_r * 0.6, dr + 0.4), ball_r * S, seg=12 if ball_r > 4 else 10, rows=7 if ball_r > 4 else 6)
    if gem:
        big = gem == "big"
        hc = H * (0.36 if big else 0.34)
        hw, hh = (7.0, 10.5) if big else (4.8, 7.4)
        right, up, nrm = cone_frame(a, hc)
        c = cone_pt(a, hc, dr + 1.0)
        facet_gem(gems, c, right, up, nrm, rhombus(hw, hh, 3), 3.0 if big else 2.4, 1.6, 0.48)
        bez = [c + (right * x + up * y) * 1.22 * S + nrm * 0.3 * S for x, y in rhombus(hw, hh, 3)]
        rail(gold, bez, [nrm] * len(bez), 0.85 * S, 0.75 * S, closed=True)
        if big:
            # an inner raised triangle round the gem, like the reference's crown detail
            r = cone_r(1.5) + dr + 1.4
            off = beta(1.5) - math.degrees(6.2 / r)
            tri = [edge(h, -1, 6.2, 0.2) for h in np.linspace(1.5, H - 11, 6)] + \
                  [edge(h, 1, 6.2, 0.2) for h in np.linspace(H - 11, 1.5, 6)[1:]] + \
                  [around(a + off * k / 3, r, BAND_TOP - 1.5) for k in (2, 1, 0, -1, -2)]
            rail(gold, tri, [surface_normal(p) for p in tri], 0.8 * S, 0.6 * S, closed=True)
    uv_region(gold, i0, UV_GOLD)


def build_crown(gold, gems):
    build_band(gold, gems)
    for a, H, beta0, ball_r, gem in CROWN_POINTS:
        build_point(gold, gems, a, H, beta0, ball_r, gem)
    for a, H, beta0, ball_r in CROWN_MINOR:
        build_point(gold, gems, a, H, beta0, ball_r, None, dr=-1.8, rail_w=1.3)


# ---------------------------------------------------------------- the wings

WT = table([(0.0, 0.0), (0.05, 0.32), (0.18, 0.72), (0.38, 0.97), (0.58, 1.0), (0.76, 0.86), (0.9, 0.55),
            (0.97, 0.24), (1.0, 0.0)])
STATIONS_BIG = [0, 0.05, 0.12, 0.22, 0.35, 0.5, 0.64, 0.76, 0.86, 0.93, 0.975, 1.0]
STATIONS_SMALL = [0, 0.08, 0.25, 0.48, 0.7, 0.88, 1.0]
LOUT = table(WING_OUTLINE)

# the wing's layers, back to front: (part, count, top / bottom direction, reach (x the outline),
# top / bottom width, depth (+ towards the front), where along the root they start, detailed?, bend)
WING_ROWS = [
    ("feathers", 6, 26, -64, 0.42, 16.0, 14.0, -5.0, 11, False, 0.05),    # back coverts (seen from behind)
    ("feathers", 8, 28, -72, 0.63, 19.0, 17.0, -2.8, 7, False, 0.06),
    ("wing", 10, 33, -78, 0.97, 24.0, 19.0, 0.0, 3, True, 0.07),          # the large outer flight feathers
    ("feathers", 9, 29, -74, 0.68, 21.0, 18.0, 2.8, 7, True, 0.06),       # the layered inner feathers
    ("feathers", 8, 28, -68, 0.47, 17.5, 15.0, 5.0, 11, False, 0.05),
    ("feathers", 7, 32, -58, 0.30, 14.0, 12.0, 7.0, 15, False, 0.04),
]
# the large base feather along the top edge: direction, reach, width, depth, bend
BASE_FEATHER = (38, 134, 27.0, 1.6, 0.14)
# small feathers layered along the inner part of the top edge: (distance along it, length, width)
EDGE_COVERTS = [(16, 30, 13.0), (30, 33, 13.5), (44, 34, 13.0), (58, 32, 12.0), (71, 28, 10.5)]


def wing_frame(side):
    """side -1 = -X (on your left as you look at the balloon's front), +1 = +X.
    Returns (root, out, front normal)."""
    rx, rv, ry = WING_ROOT
    sw = math.radians(WING_SWEEP)
    out = Vector((side * math.cos(sw), math.sin(sw), 0))
    front = Z.cross(out) if side < 0 else out.cross(Z)
    return P(side * rx, rv, ry), out, front


def wing_map(side):
    """(a out from the root, b up, z towards the front) in pixels, on the wing's swept, gently
    back-curled surface, to Blender studs."""
    root, out, front = wing_frame(side)

    def to3d(a, b, z):
        return root + (out * a + Z * b + front * (z - WING_CURL * (a * a + 0.6 * b * b))) * S
    return to3d


def feather(mb, to3d, a0, b0, z0, theta, L, W, bend, big=True, cup=0.12, thick=1.1, asym=0.44, vmax=1.0):
    """One feather: a pointed vane along a gently bending quill, with a raised quill ridge on both
    faces and its edges cupped back (so it's a real 3D shape, not a flat card). vmax < 1 maps it
    onto less of the feather texture, so the small inner feathers stay golden cream and only the
    big outer ones reach the bright white tips."""
    th = math.radians(theta)
    d = (math.cos(th), math.sin(th))
    s = (-math.sin(th), math.cos(th))
    rings, uvs = [], []
    for f in (STATIONS_BIG if big else STATIONS_SMALL):
        ca = a0 + d[0] * L * f + s[0] * L * bend * f * f
        cb = b0 + d[1] * L * f + s[1] * L * bend * f * f
        ta, tb = d[0] + s[0] * 2 * bend * f, d[1] + s[1] * 2 * bend * f
        ln = math.hypot(ta, tb)
        pa, pb = -tb / ln, ta / ln
        w = W * WT(f)
        if w < 1e-3:
            rings.append([to3d(ca, cb, z0)])
            uvs.append([(0.5, f * vmax)])
            continue
        wl, wr = w * asym, w * (1 - asym)
        t = thick * (1 - 0.6 * f)
        tv = t * 0.55
        if big:
            sec = [(-wr, -cup * wr), (-wr * 0.5, -cup * 0.3 * wr + tv), (0, t), (wl * 0.5, -cup * 0.3 * wl + tv),
                   (wl, -cup * wl), (wl * 0.5, -cup * 0.3 * wl - tv), (0, -t), (-wr * 0.5, -cup * 0.3 * wr - tv)]
            us = [0, 0.25, 0.5, 0.75, 1, 0.75, 0.5, 0.25]
        else:
            sec = [(-wr, -cup * wr), (-wr * 0.35, tv), (wl * 0.35, tv), (wl, -cup * wl), (wl * 0.35, -tv),
                   (-wr * 0.35, -tv)]
            us = [0, 0.33, 0.67, 1, 0.67, 0.33]
        rings.append([to3d(ca + pa * x, cb + pb * x, z0 + zz) for x, zz in sec])
        uvs.append([(u, f * vmax) for u in us])
    loft(mb, rings, uvs=uvs)


def feather_specs():
    """Every feather of one wing: (part, a0, b0, z, direction, length, width, bend, detailed?, vmax)."""
    rng = np.random.default_rng(9)
    specs = []
    th, reach, W, z, bend = BASE_FEATHER
    specs.append(("wing", 2.0 * math.cos(math.radians(th)), 2.0 * math.sin(math.radians(th)), z, th, reach - 2.0, W,
                  bend, True, 1.0))
    a = math.radians(th - 3)
    for k, (dist, length, width) in enumerate(EDGE_COVERTS):
        specs.append(("feathers", dist * math.cos(a), dist * math.sin(a) - 4.0, 3.6 + 0.6 * (k % 2), th - 10, length,
                      width, 0.06, False, 0.6))
    for part, n, t0, t1, scale, w0, w1, z, start, big, bend in WING_ROWS:
        for i in range(n):
            f = i / (n - 1)
            theta = t0 + (t1 - t0) * f + rng.uniform(-1.2, 1.2)
            reach = LOUT(theta) * scale * rng.uniform(0.97, 1.03)
            a = math.radians(theta)
            specs.append((part, start * math.cos(a), start * math.sin(a), z + (0.7 if i % 2 else 0.0), theta,
                          reach - start, w0 + (w1 - w0) * f, bend * (1.4 if theta > 10 else 1.0), big,
                          min(1.0, 0.35 + 0.65 * scale)))
    return specs


def build_wing(side, wing_mb, feathers_mb):
    to3d = wing_map(side)
    for part, a0, b0, z, theta, L, W, bend, big, vmax in feather_specs():
        feather(wing_mb if part == "wing" else feathers_mb, to3d, a0, b0, z, theta, L, W, bend, big, vmax=vmax)


# ---------------------------------------------------------------- the model

PART_ORDER = ["Balloon", "BalloonNozzle", "String", "Crown", "CrownGems", "LeftWing", "RightWing",
              "LeftWingFeathers", "RightWingFeathers"]


def build_model():
    mbs = {name: MB() for name in PART_ORDER}
    build_balloon(mbs["Balloon"])
    build_nozzle(mbs["BalloonNozzle"])
    build_string(mbs["String"])
    build_crown(mbs["Crown"], mbs["CrownGems"])
    build_wing(-1, mbs["LeftWing"], mbs["LeftWingFeathers"])
    build_wing(1, mbs["RightWing"], mbs["RightWingFeathers"])
    parts = {name: mbs[name].to_object(name) for name in PART_ORDER}
    for ob in parts.values():
        clean_mesh(ob)
    return parts


# ---------------------------------------------------------------- the golden aura (separate objects)

def crossed_card(mb, centre, width, height, yaw=0.0):
    c = Vector(centre)
    for k in range(2):
        a = yaw + math.pi / 2 * k
        side = Vector((math.cos(a), math.sin(a), 0))
        q = [mb.add(c - side * width / 2 - Z * height / 2, (0, 0)), mb.add(c + side * width / 2 - Z * height / 2, (1, 0)),
             mb.add(c + side * width / 2 + Z * height / 2, (1, 1)), mb.add(c - side * width / 2 + Z * height / 2, (0, 1))]
        mb.face(q)


def facing_card(mb, centre, width, height, roll=0.0, normal=None):
    """A single card facing the front (or `normal`), rolled in its plane."""
    c = Vector(centre)
    n = Vector(normal) if normal is not None else -Y
    s1, s2 = frame(n, Z.cross(n) if abs(n.z) < 0.9 else X)
    r1 = s1 * math.cos(roll) + s2 * math.sin(roll)
    r2 = -s1 * math.sin(roll) + s2 * math.cos(roll)
    q = [mb.add(c - r1 * width / 2 - r2 * height / 2, (0, 0)), mb.add(c + r1 * width / 2 - r2 * height / 2, (1, 0)),
         mb.add(c + r1 * width / 2 + r2 * height / 2, (1, 1)), mb.add(c - r1 * width / 2 + r2 * height / 2, (0, 1))]
    mb.face(q)


# thin swirling energy trails round the balloon: (radius px, tilt (front dips) deg, roll deg,
# start deg, span deg, width px, gold?)
TRAILS = [(94, 24, 16, 205, 250, 7.0, False), (80, -16, -22, 25, 215, 5.5, True), (108, 12, 32, 110, 170, 4.4, True)]
TRAIL_CENTRE = (0, 6)


def trail_frame(i):
    _, tilt, roll, _, _, _, _ = TRAILS[i]
    m = Matrix.Rotation(math.radians(roll), 3, "Y") @ Matrix.Rotation(math.radians(tilt), 3, "X")
    return m @ X, m @ Y, m @ Z


def trail_points(i, n=72, full=False):
    radius, _, _, start, span, _, _ = TRAILS[i]
    e1, e2, _ = trail_frame(i)
    c = P(*TRAIL_CENTRE)
    if full:
        start, span = 0.0, 360.0 * (n - 1) / n
    pts = []
    for k in range(n):
        phi = math.radians(start + span * k / (n - 1))
        pts.append(c + (e1 * math.cos(phi) + e2 * math.sin(phi)) * radius * S)
    return pts


def band_ribbon(mb, pts, width_fn, side_vec):
    """A ribbon along pts, its width along side_vec (so a trail round the balloon reads from the front)."""
    n = len(pts)
    L, R = [], []
    for k, p in enumerate(pts):
        f = k / (n - 1)
        w = width_fn(f)
        L.append(mb.add(p - side_vec * w / 2, (f, 0)))
        R.append(mb.add(p + side_vec * w / 2, (f, 1)))
    for k in range(n - 1):
        mb.face([L[k], L[k + 1], R[k + 1], R[k]])


def wing_glow_centre(side):
    return wing_map(side)(62, 8, 0)


def build_aura(mats):
    rng = np.random.default_rng(23)
    obs = {}
    centre = P(0, 0, 4)
    # golden aura: a soft yellow-white glow round the balloon, a bigger gold glow, a glow behind
    # each wing and small light rays behind the balloon
    mb = MB()
    crossed_card(mb, centre, 2.5, 2.7)
    obs["GoldenAura"] = mb.to_object("GoldenAura")
    set_material(obs["GoldenAura"], mats["GlowSoft"])
    mb = MB()
    crossed_card(mb, P(0, -10, 6), 3.9, 3.7)
    for side in (-1, 1):
        crossed_card(mb, wing_glow_centre(side) + Y * 0.12, 2.1, 2.3)
    obs["GoldenAuraGold"] = mb.to_object("GoldenAuraGold")
    set_material(obs["GoldenAuraGold"], mats["GlowGold"])
    mb = MB()
    facing_card(mb, P(0, -6, 30), 3.0, 3.0, 0.3)
    obs["LightRays"] = mb.to_object("LightRays")
    set_material(obs["LightRays"], mats["Rays"])
    # energy trails: thin swirling strands of gold light, close round the balloon
    white_mb, gold_mb = MB(), MB()
    for i, tr in enumerate(TRAILS):
        _, _, n = trail_frame(i)
        band_ribbon(gold_mb if tr[6] else white_mb, trail_points(i), lambda f, w=tr[5]: (1.5 + w * math.sin(math.pi * f) ** 0.7) * S,
                    n)
    obs["EnergyTrails"] = white_mb.to_object("EnergyTrails")
    set_material(obs["EnergyTrails"], mats["Trail"])
    obs["EnergyTrailsGold"] = gold_mb.to_object("EnergyTrailsGold")
    set_material(obs["EnergyTrailsGold"], mats["TrailGold"])
    mb = MB()
    for i, tr in enumerate(TRAILS[:2]):
        _, _, n = trail_frame(i)
        band_ribbon(mb, trail_points(i), lambda f, w=tr[5]: (0.3 + w * 2.6 * math.sin(math.pi * f) ** 1.2) * S, n)
    obs["EnergyTrailsGlow"] = mb.to_object("EnergyTrailsGlow")
    set_material(obs["EnergyTrailsGlow"], mats["Swirl"])
    # sparkles and tiny glowing stars
    mb = MB()
    for k in range(13):
        a = rng.uniform(0, 2 * math.pi)
        rad = rng.uniform(1.3, 2.9)
        c = Vector((math.cos(a) * rad, rng.uniform(-0.4, 0.4), math.sin(a) * rad * 0.8 + 0.2))
        sz = rng.uniform(0.12, 0.26)
        crossed_card(mb, c, sz, sz, rng.uniform(0, 3))
    obs["Sparkles"] = mb.to_object("Sparkles")
    set_material(obs["Sparkles"], mats["Sparkle"])
    mb = MB()
    for k in range(22):
        a = rng.uniform(0, 2 * math.pi)
        rad = rng.uniform(1.0, 2.8)
        c = Vector((math.cos(a) * rad, rng.uniform(-0.6, 0.6), math.sin(a) * rad * 0.85))
        sz = rng.uniform(0.05, 0.1)
        crossed_card(mb, c, sz, sz, rng.uniform(0, 3))
    obs["Stars"] = mb.to_object("Stars")
    set_material(obs["Stars"], mats["Star"])
    # golden particles: tiny motes drifting round it, and a few floating golden feathers
    mb = MB()
    for k in range(46):
        if k < 26:
            pts = trail_points(k % len(TRAILS), 40)
            c = pts[int(rng.integers(3, 37))] + Vector((rng.normal(0, 0.06), rng.normal(0, 0.06), rng.normal(0, 0.06)))
        else:
            a = rng.uniform(0, 2 * math.pi)
            c = Vector((math.cos(a) * rng.uniform(0.9, 2.6), rng.uniform(-0.5, 0.5), math.sin(a) * rng.uniform(0.9, 2.2)))
        sz = rng.uniform(0.03, 0.06)
        crossed_card(mb, c, sz, sz, rng.uniform(0, 3))
    obs["GoldenParticles"] = mb.to_object("GoldenParticles")
    set_material(obs["GoldenParticles"], mats["Mote"])
    mb = MB()
    for c, roll, sz in (((-2.35, -0.3, 1.25), 0.6, 0.42), ((2.15, -0.2, 1.5), -0.9, 0.36), ((-1.95, -0.4, -1.45), 2.2, 0.44),
                        ((1.55, -0.5, -1.65), 1.4, 0.38), ((0.95, -0.3, 2.0), -0.3, 0.3), ((-2.7, 0.2, -0.3), 2.9, 0.3)):
        facing_card(mb, c, sz, sz, roll)
    obs["FloatingFeathers"] = mb.to_object("FloatingFeathers")
    set_material(obs["FloatingFeathers"], mats["FeatherSprite"])
    return obs


# which aura objects make up each VFX group
AURA_GROUPS = {
    "GoldenAura": ["GoldenAura", "GoldenAuraGold", "LightRays"],
    "GoldenParticles": ["GoldenParticles", "FloatingFeathers"],
    "Sparkles": ["Sparkles", "Stars"],
    "EnergyTrails": ["EnergyTrails", "EnergyTrailsGold", "EnergyTrailsGlow"],
}


# ---------------------------------------------------------------- textures, materials, layout

def textures():
    os.makedirs(TEXTURES, exist_ok=True)

    def save(name, arr, colorspace="sRGB"):
        return np_image(name, arr, os.path.join(TEXTURES, name + ".png"), colorspace)
    gmr = bt.gold_mr(256)
    rmr = bt.gold_mr(256, seed=6, rough=0.22)
    imgs = {
        "balloon": save("balloon_color", bt.balloon()),
        "balloon_mr": save("balloon_mr", bt.balloon_mr(), "Non-Color"),
        "gold": save("gold_color", np.concatenate([bt.gold(512), bt.gold_recess(512)], axis=1)),
        "gold_mr": save("gold_mr", np.concatenate([gmr, rmr], axis=1), "Non-Color"),
        "gem": save("gem_color", bt.gem()),
        "gem_mr": save("gem_mr", bt.gem_mr(), "Non-Color"),
        "feather": save("feather_color", bt.feather()),
        "feather_mr": save("feather_mr", bt.feather_mr(), "Non-Color"),
        "string": save("string_color", bt.string_tex()),
    }
    for key, fn in bt.AURA.items():
        imgs["fx_" + key] = save("fx_" + key.lower(), fn())
    return imgs


def principled_tex(name, col, mr=None, roughness=0.5, emission=0.0, coat=0.0, sheen=0.0, metallic=None):
    mat = bpy.data.materials.new(name)
    nt = nodes_of(mat)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    tc = nt.nodes.new("ShaderNodeTexImage")
    tc.image = col
    nt.links.new(tc.outputs["Color"], bsdf.inputs["Base Color"])
    if mr is not None:
        tm = nt.nodes.new("ShaderNodeTexImage")
        tm.image = mr
        sep = nt.nodes.new("ShaderNodeSeparateColor")
        nt.links.new(tm.outputs["Color"], sep.inputs["Color"])
        nt.links.new(sep.outputs["Green"], bsdf.inputs["Roughness"])
        nt.links.new(sep.outputs["Blue"], bsdf.inputs["Metallic"])
    else:
        bsdf.inputs["Roughness"].default_value = roughness
    if metallic is not None and mr is None:
        bsdf.inputs["Metallic"].default_value = metallic
    if emission:
        nt.links.new(tc.outputs["Color"], bsdf.inputs["Emission Color"])
        bsdf.inputs["Emission Strength"].default_value = emission
    bsdf.inputs["Coat Weight"].default_value = coat
    bsdf.inputs["Coat Roughness"].default_value = 0.04
    bsdf.inputs["Sheen Weight"].default_value = sheen
    nt.links.new(bsdf.outputs[0], out.inputs["Surface"])
    return mat


def materials(imgs):
    gold = metal_material("PolishedGold", imgs["gold"], imgs["gold_mr"])
    gem = crystal_material("YellowGem", imgs["gem"], imgs["gem_mr"], glow_strength=0.9, transmission=0.25)
    for n in gem.node_tree.nodes:
        if n.type == "BSDF_PRINCIPLED":
            n.inputs["IOR"].default_value = 1.9
            n.inputs["Coat Weight"].default_value = 0.6
    feathers = principled_tex("Feathers", imgs["feather"], roughness=0.5, emission=0.14, sheen=0.4)
    return {
        "Balloon": principled_tex("BalloonGold", imgs["balloon"], imgs["balloon_mr"], emission=0.04, coat=0.45),
        "BalloonNozzle": gold, "Crown": gold, "CrownGems": gem,
        "String": principled_tex("String", imgs["string"], roughness=0.35, emission=0.35),
        "LeftWing": feathers, "RightWing": feathers, "LeftWingFeathers": feathers, "RightWingFeathers": feathers,
        "GlowSoft": fx_material("GoldenAura", imgs["fx_GlowSoft"], 0.42),
        "GlowGold": fx_material("GoldenAuraGold", imgs["fx_GlowGold"], 0.4),
        "Rays": fx_material("LightRays", imgs["fx_Rays"], 0.3),
        "Trail": fx_material("EnergyTrails", imgs["fx_Trail"], 2.2),
        "TrailGold": fx_material("EnergyTrailsGold", imgs["fx_Trail"], 1.8),
        "Sparkle": fx_material("Sparkles", imgs["fx_Sparkle"], 2.6),
        "Star": fx_material("Stars", imgs["fx_Star"], 2.4),
        "Mote": fx_material("GoldenParticles", imgs["fx_Mote"], 2.2),
        "FeatherSprite": fx_material("FloatingFeathers", imgs["fx_Feather"], 1.6),
        "Swirl": fx_material("EnergyTrailsGlow", imgs["fx_Swirl"], 0.9),
    }


def layout(report):
    def vec(p):
        return [round(c, 4) for c in p]
    hinges = {}
    for name, side in (("Left", -1), ("Right", 1)):
        root, out, front = wing_frame(side)
        hinges[name] = {"pos": vec(root), "out": vec(out), "front": vec(front), "glow": vec(wing_glow_centre(side))}
    info = {
        "units": "studs", "studsPerPixel": S,
        "points": {
            "Pivot": [0, 0, 0], "Nozzle": vec(P(0, 71.6)), "StringEnd": vec(string_points()[-1]),
            "CrownTop": vec(cone_pt(0, 48 + 5.6 * 1.6)), "CrownGem": vec(cone_pt(0, 48 * 0.36, 1.0)),
            "TrailCentre": vec(P(*TRAIL_CENTRE)),
        },
        "balloonRadius": round(52.2 * S, 4),
        "wings": hinges,
        "trails": [[vec(p) for p in trail_points(i, 25)] for i in range(len(TRAILS))],
        "trailOrbits": [[vec(p) for p in trail_points(i, 24, full=True)] for i in range(len(TRAILS))],
        "trailWidths": [round(tr[5] * S, 4) for tr in TRAILS],
        "trailGold": [tr[6] for tr in TRAILS],
        "meshReport": report,
    }
    with open(os.path.join(EXPORT, "balloon_layout.json"), "w") as f:
        json.dump(info, f, indent=1)
    return info


# ---------------------------------------------------------------- previews

def r15_mannequin(origin, mat_skin, mat_shirt, mat_pants):
    """A blocky R15 character (scale 1, facing -Y) standing with its feet at origin, for the
    in-game shots."""
    obs = []
    o = Vector(origin)
    blocks = [  # name, centre, size, material
        ("Head", (0, 0, 4.6), (1.2, 1.2, 1.2), mat_skin), ("UpperTorso", (0, 0, 3.2), (2.0, 1.0, 1.6), mat_shirt),
        ("LowerTorso", (0, 0, 2.2), (2.0, 1.0, 0.4), mat_pants),
        ("RightUpperArm", (-1.5, 0, 3.4), (1.0, 1.0, 1.2), mat_shirt), ("LeftUpperArm", (1.5, 0, 3.4), (1.0, 1.0, 1.2), mat_shirt),
        ("RightLowerArm", (-1.5, 0, 2.45), (1.0, 1.0, 0.7), mat_skin), ("LeftLowerArm", (1.5, 0, 2.45), (1.0, 1.0, 0.7), mat_skin),
        ("RightHand", (-1.5, 0, 1.95), (1.0, 1.0, 0.3), mat_skin), ("LeftHand", (1.5, 0, 1.95), (1.0, 1.0, 0.3), mat_skin),
        ("RightUpperLeg", (-0.5, 0, 1.45), (1.0, 1.0, 1.1), mat_pants), ("LeftUpperLeg", (0.5, 0, 1.45), (1.0, 1.0, 1.1), mat_pants),
        ("RightLowerLeg", (-0.5, 0, 0.6), (1.0, 1.0, 0.6), mat_pants), ("LeftLowerLeg", (0.5, 0, 0.6), (1.0, 1.0, 0.6), mat_pants),
        ("RightFoot", (-0.5, -0.05, 0.15), (1.0, 1.1, 0.3), mat_pants), ("LeftFoot", (0.5, -0.05, 0.15), (1.0, 1.1, 0.3), mat_pants),
    ]
    for name, c, size, mat in blocks:
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0)
        bmesh.ops.scale(bm, vec=size, verts=bm.verts)
        bmesh.ops.bevel(bm, geom=list(bm.edges), offset=0.06 if name != "Head" else 0.2, segments=3, affect="EDGES",
                        profile=0.5)
        bmesh.ops.translate(bm, vec=o + Vector(c), verts=bm.verts)
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        bm.free()
        for p in me.polygons:
            p.use_smooth = True
        ob = bpy.data.objects.new("R15_" + name, me)
        bpy.context.scene.collection.objects.link(ob)
        set_material(ob, mat)
        obs.append(ob)
    # a simple face
    face = MB()
    for s in (-1, 1):
        sphere(face, o + Vector((s * 0.22, -0.6, 4.72)), 0.075, seg=10, rows=6)
    q = smooth_path([(-0.24, 0, 4.4), (0, 0, 4.32), (0.24, 0, 4.4)], 4)
    tube(face, [o + Vector((p[0], -0.6, p[2])) for p in q], 0.03, sides=6)
    fo = face.to_object("R15_Face")
    fm = bpy.data.materials.new("Face")
    fnt = nodes_of(fm)
    fb = fnt.nodes.new("ShaderNodeBsdfPrincipled")
    fb.inputs["Base Color"].default_value = (0.02, 0.02, 0.02, 1)
    fout = fnt.nodes.new("ShaderNodeOutputMaterial")
    fnt.links.new(fb.outputs[0], fout.inputs["Surface"])
    set_material(fo, fm)
    obs.append(fo)
    return obs


def flat_material(name, rgb, rough=0.6):
    m = bpy.data.materials.new(name)
    nt = nodes_of(m)
    b = nt.nodes.new("ShaderNodeBsdfPrincipled")
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Roughness"].default_value = rough
    o = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(b.outputs[0], o.inputs["Surface"])
    return m


# where the balloon floats on an R15 character (studs from the HumanoidRootPart: its right, up, back)
INGAME_OFFSET = (1.6, 3.6, 1.9)


def render_previews(parts, aura, imgs, only=None):
    os.makedirs(PREVIEWS, exist_ok=True)
    sc = bpy.context.scene
    sc.cycles.samples = 48
    sc.cycles.use_denoising = True
    sc.cycles.transparent_max_bounces = 64
    sc.cycles.max_bounces = 10
    sc.cycles.glossy_bounces = 6
    sc.cycles.transmission_bounces = 8
    sc.view_settings.view_transform = "Standard"
    if os.environ.get("QUICK"):                                    # fast drafts while tuning
        sc.cycles.samples = 12
        sc.render.resolution_percentage = 50
    world = bpy.data.worlds.new("Heaven")
    sc.world = world
    wnt = nodes_of(world)
    bg = wnt.nodes.new("ShaderNodeBackground")                     # what the camera sees
    bg.inputs["Color"].default_value = (0.012, 0.009, 0.005, 1)
    env = wnt.nodes.new("ShaderNodeBackground")                    # what the gold reflects: a warm studio
    coord = wnt.nodes.new("ShaderNodeTexCoord")
    sep = wnt.nodes.new("ShaderNodeSeparateXYZ")
    ramp = wnt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.25
    ramp.color_ramp.elements[0].color = (0.05, 0.035, 0.015, 1)
    ramp.color_ramp.elements[1].position = 0.85
    ramp.color_ramp.elements[1].color = (1.0, 0.95, 0.82, 1)
    el = ramp.color_ramp.elements.new(0.52)
    el.color = (0.62, 0.48, 0.26, 1)
    mapr = wnt.nodes.new("ShaderNodeMapRange")
    mapr.inputs["From Min"].default_value = -1
    wnt.links.new(coord.outputs["Normal"], sep.inputs[0])
    wnt.links.new(sep.outputs["Z"], mapr.inputs["Value"])
    wnt.links.new(mapr.outputs["Result"], ramp.inputs["Fac"])
    wnt.links.new(ramp.outputs["Color"], env.inputs["Color"])
    env.inputs["Strength"].default_value = 1.0
    lp = wnt.nodes.new("ShaderNodeLightPath")
    mix = wnt.nodes.new("ShaderNodeMixShader")
    wnt.links.new(lp.outputs["Is Camera Ray"], mix.inputs[0])
    wnt.links.new(env.outputs[0], mix.inputs[1])
    wnt.links.new(bg.outputs[0], mix.inputs[2])
    wo = wnt.nodes.new("ShaderNodeOutputWorld")
    wnt.links.new(mix.outputs[0], wo.inputs["Surface"])

    lights = []

    def light(name, loc, energy, color, size, target=(0, 0, 0)):
        ld = bpy.data.lights.new(name, "AREA")
        ld.energy, ld.color, ld.size = energy, color, size
        ld.shape = "DISK"
        lo = bpy.data.objects.new(name, ld)
        lo.location = loc
        lo.rotation_euler = (Vector(target) - lo.location).to_track_quat("-Z", "Y").to_euler()
        sc.collection.objects.link(lo)
        lights.append(lo)

    light("Key", (3.5, -5, 4), 620, (1.0, 0.95, 0.85), 7)
    light("Fill", (-4.5, -4, 0.5), 220, (1.0, 0.92, 0.8), 8)
    light("RimL", (-4, 4.5, 2.5), 420, (1.0, 0.85, 0.55), 5)
    light("RimR", (4, 4.5, 2), 380, (1.0, 0.9, 0.7), 5)
    light("Under", (0, -3, -4), 60, (1.0, 0.8, 0.4), 6)
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
        cam_d.clip_start, cam_d.clip_end = 0.05, 200
        sc.render.resolution_x, sc.render.resolution_y = res
        path = os.path.join(PREVIEWS, name + ".png")
        sc.render.filepath = path
        bpy.ops.render.render(write_still=True)
        if glow:
            bloom(path, strength=glow, threshold=0.72)
        print("rendered", path)

    def show_aura(on):
        for ob in aura.values():
            ob.hide_render = not on

    mid = Vector((0, 0, -0.35))
    sq = (1100, 1100)
    ortho = 6.3
    show_aura(False)
    shot("model_front", mid - Y * 20, mid, sq, ortho=ortho, glow=0.3)
    shot("model_back", mid + Y * 20, mid, sq, ortho=ortho, glow=0.3)
    shot("model_left", mid - X * 20, mid, sq, ortho=ortho, glow=0.3)
    shot("model_right", mid + X * 20, mid, sq, ortho=ortho, glow=0.3)
    shot("model_angle", (3.6, -7.2, 2.4), (0, 0, -0.1), (1100, 1100), lens=42, glow=0.3)
    shot("crown_closeup", (0.9, -3.0, 2.2), (0, 0, 1.25), (1100, 900), lens=55, glow=0.3)
    shot("wing_closeup", (-3.4, -3.6, 0.9), (-1.6, 0, 0.35), (1100, 900), lens=50, glow=0.3)
    shot("balloon_closeup", (0.6, -2.4, -1.0), (0, 0, -0.95), (1000, 900), lens=55, glow=0.3)
    show_aura(True)
    shot("front", mid - Y * 20, mid, sq, ortho=ortho)
    shot("back", mid + Y * 20, mid, sq, ortho=ortho)
    shot("left", mid - X * 20, mid, sq, ortho=ortho)
    shot("right", mid + X * 20, mid, sq, ortho=ortho)
    shot("angle", (3.6, -7.2, 2.4), (0, 0, -0.1), (1100, 1100), lens=42)

    # in game: floating beside an R15 character on a baseplate under a blue sky
    if only and not any(s.startswith("ingame") for s in only):
        return
    right, up, back = INGAME_OFFSET
    hrp = Vector((0, 0, 3.0))
    feet = Vector((0, 0, 0))
    # the character faces -Y, so its right is -X and its back is +Y
    offset = hrp + Vector((-right, back, up))
    move = Matrix.Translation(offset)
    for ob in list(parts.values()) + list(aura.values()):
        ob.matrix_world = move
    mb = MB()
    q = [mb.add((-30, -30, 0), (0, 0)), mb.add((30, -30, 0), (1, 0)), mb.add((30, 30, 0), (1, 1)),
         mb.add((-30, 30, 0), (0, 1))]
    mb.face(q)
    floor = mb.to_object("Floor")
    fm = bpy.data.materials.new("Floor")
    fnt = nodes_of(fm)
    fb = fnt.nodes.new("ShaderNodeBsdfPrincipled")
    fb.inputs["Roughness"].default_value = 0.6
    checker = fnt.nodes.new("ShaderNodeTexChecker")
    checker.inputs["Scale"].default_value = 30
    checker.inputs["Color1"].default_value = (0.3, 0.31, 0.36, 1)
    checker.inputs["Color2"].default_value = (0.33, 0.34, 0.39, 1)
    fnt.links.new(checker.outputs["Color"], fb.inputs["Base Color"])
    fo = fnt.nodes.new("ShaderNodeOutputMaterial")
    fnt.links.new(fb.outputs[0], fo.inputs["Surface"])
    set_material(floor, fm)
    r15_mannequin(feet, flat_material("Skin", (0.8, 0.6, 0.45)), flat_material("Shirt", (0.08, 0.12, 0.35)),
                  flat_material("Pants", (0.06, 0.06, 0.07)))
    bg.inputs["Color"].default_value = (0.25, 0.5, 0.95, 1)
    env.inputs["Strength"].default_value = 1.2
    for lo in lights:
        lo.location += Vector((0, 0, 4))
        lo.data.energy *= 0.6
    sun_d = bpy.data.lights.new("Sun", "SUN")
    sun_d.energy, sun_d.angle, sun_d.color = 3.0, math.radians(8), (1.0, 0.97, 0.9)
    sun = bpy.data.objects.new("Sun", sun_d)
    sun.rotation_euler = (math.radians(50), 0, math.radians(35))
    sc.collection.objects.link(sun)
    shot("ingame", (7.5, -12.5, 7.4), (-0.7, 0.4, 4.1), (1100, 1300), lens=50, glow=0.3)
    shot("ingame_back", (-6.5, 13.5, 8.6), (-0.8, 0.6, 4.3), (1100, 1300), lens=50, glow=0.3)


def main(render=False, only=None):
    clean_scene()
    parts = build_model()
    imgs = textures()
    mats = materials(imgs)
    for name in PART_ORDER:
        set_material(parts[name], mats[name])
    report = mesh_report(parts)
    aura = build_aura(mats)
    marks = [marker("Mark_O", (0, 0, 0)), marker("Mark_Y", (0, 1, 0)), marker("Mark_Z", (0, 0, 1))]
    export([parts[n] for n in PART_ORDER] + marks, "GoldenKingBalloon")
    for m in marks:
        bpy.data.objects.remove(m)
    export(list(aura.values()), "GoldenBalloonAura")
    carriers = build_vfx_carriers(imgs)
    export(list(carriers.values()), "GoldenBalloonVFX")
    for ob in carriers.values():
        ob.hide_render = True
        ob.hide_set(True)
    info = layout(report)
    with open(os.path.join(EXPORT, "mesh_report.json"), "w") as f:
        json.dump(report, f, indent=1)
    print(json.dumps({k: v for k, v in report.items() if k != "parts"}, indent=1))
    for name, p in report["parts"].items():
        print(f"  {name:18s} tris {p['tris']:6d} pieces {p['pieces']:4d} nonManifold {p['nonManifoldEdges']} "
              f"loose {p['looseVerts']} zero {p['zeroAreaFaces']} inverted {p['invertedPieces']}")
    for img in bpy.data.images:
        if img.filepath_raw and not img.packed_file and os.path.exists(bpy.path.abspath(img.filepath_raw)):
            img.pack()
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(EXPORT, "GoldenKingBalloon.blend"), compress=True)
    if render:
        render_previews(parts, aura, imgs, only)
    return info


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    shots = next((a.split("=", 1)[1].split(",") for a in argv if a.startswith("--shots=")), None)
    main(render="--render" in argv or shots is not None, only=shots)
