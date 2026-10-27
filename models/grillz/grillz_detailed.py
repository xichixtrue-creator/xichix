"""
Diamond Grillz - HIGH DETAIL version.

Every stone is real faceted geometry (brilliant-style crown) set into a domed
gold cap with a raised bezel lip and gold beads between the stones, like a
real iced-out set. Two parts: gold body and diamonds.

  In Blender: Scripting tab > Open > this file > Run Script.
              Builds "Grillz Gold" and "Grillz Diamonds" with real gold and
              diamond (glass, IOR 2.42) materials. Best seen in Rendered view.

  Outside Blender:  python3 grillz_detailed.py
              Writes grillz_detailed.obj + .mtl next to this file (two objects,
              so Roblox's 3D Importer makes one MeshPart per material).

Axes follow Blender: X right, Y back (front faces -Y), Z up.
"""

import math
import os

PROFILE_POINTS = 40

# (width, height, point) from the middle outward; mirrored to the other side.
UPPER = [(0.34, 0.44, 0.13), (0.29, 0.38, 0.09), (0.26, 0.36, 0.0)]
LOWER = [(0.26, 0.36, 0.10), (0.26, 0.36, 0.10), (0.25, 0.38, 0.14)]

ARCH_RADIUS = 1.1
DEPTH = 0.16
BITE_GAP = 0.025
LOWER_SETBACK = 0.05

DOME_X = 0.030      # how much the front bulges side to side
DOME_Z = 0.012      # and top to bottom
FACE_Y = -0.035     # front surface at the tooth edge

STONE_PITCH = 0.066
STONE_R = 0.49 * STONE_PITCH
BEAD_R = 0.14 * STONE_PITCH


# ---------------------------------------------------------------- outline

def _fillet_polygon(corners, radius, per_corner):
    out = []
    n = len(corners)
    for i in range(n):
        px, pz = corners[i]
        ax, az = corners[i - 1]
        bx, bz = corners[(i + 1) % n]
        la = math.hypot(ax - px, az - pz)
        lb = math.hypot(bx - px, bz - pz)
        u1 = ((ax - px) / la, (az - pz) / la)
        u2 = ((bx - px) / lb, (bz - pz) / lb)
        half = math.acos(max(-1.0, min(1.0, u1[0] * u2[0] + u1[1] * u2[1]))) / 2
        t = min(radius / math.tan(half), la * 0.45, lb * 0.45)
        r = t * math.tan(half)
        bis = (u1[0] + u2[0], u1[1] + u2[1])
        bl = math.hypot(*bis)
        cd = r / math.sin(half)
        cx, cz = px + bis[0] / bl * cd, pz + bis[1] / bl * cd
        a0 = math.atan2(pz + u1[1] * t - cz, px + u1[0] * t - cx)
        a1 = math.atan2(pz + u2[1] * t - cz, px + u2[0] * t - cx)
        while a1 < a0:
            a1 += 2 * math.pi
        if a1 - a0 > math.pi:
            a1 -= 2 * math.pi
        for k in range(per_corner):
            a = a0 + (a1 - a0) * k / (per_corner - 1)
            out.append((cx + r * math.cos(a), cz + r * math.sin(a)))
    return out


def tooth_outline(width, height, point):
    w, h = width / 2, height / 2
    if point <= 0:
        corners = [(-w, -h), (w, -h), (w, h), (-w, h)]
        return _fillet_polygon(corners, width * 0.22, PROFILE_POINTS // 4)
    corners = [(-w, -h), (w, -h), (w, h - point), (0.0, h), (-w, h - point)]
    return _fillet_polygon(corners, width * 0.16, PROFILE_POINTS // 5)


def _inside(outline, x, z, margin):
    """True if a circle of radius `margin` at (x, z) fits in the convex CCW outline."""
    n = len(outline)
    for i in range(n):
        ax, az = outline[i]
        bx, bz = outline[(i + 1) % n]
        ex, ez = bx - ax, bz - az
        le = math.hypot(ex, ez)
        if le < 1e-9:
            continue
        if (ex * (z - az) - ez * (x - ax)) / le < margin:
            return False
    return True


# ---------------------------------------------------------------- mesh helpers

class Mesh:
    def __init__(self, name):
        self.name = name
        self.verts = []
        self.faces = []    # (indices, smooth)

    def add(self, p):
        self.verts.append(p)
        return len(self.verts) - 1

    def orient_from(self, start, centre):
        """Wind faces[start:] outward, away from `centre` (convex pieces)."""
        for k in range(start, len(self.faces)):
            idx, smooth = self.faces[k]
            p = [self.verts[i] for i in idx]
            e1 = [p[1][a] - p[0][a] for a in range(3)]
            e2 = [p[2][a] - p[0][a] for a in range(3)]
            nrm = (e1[1] * e2[2] - e1[2] * e2[1],
                   e1[2] * e2[0] - e1[0] * e2[2],
                   e1[0] * e2[1] - e1[1] * e2[0])
            c = [sum(q[a] for q in p) / len(p) - centre[a] for a in range(3)]
            if sum(nrm[a] * c[a] for a in range(3)) < 0:
                self.faces[k] = (idx[::-1], smooth)


def _norm(v):
    l = math.sqrt(sum(c * c for c in v))
    return tuple(c / l for c in v)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


# ---------------------------------------------------------------- one tooth

def _build_tooth(spec, flip, cx, cy, cz, angle, gold, ice):
    width, height, point = spec
    outline = tooth_outline(width, height, point)
    n = len(outline)
    sz = -1.0 if flip else 1.0
    ca, sa = math.cos(angle), math.sin(angle)
    hw, hh = width / 2, height / 2

    def world(x, y, z):
        z *= sz
        return (cx + x * ca - y * sa, cy + x * sa + y * ca, cz + z)

    def world_dir(x, y, z):
        z *= sz
        return (x * ca - y * sa, x * sa + y * ca, z)

    def surf_y(x, z):
        return FACE_Y - DOME_X * (1 - (x / hw) ** 2) - DOME_Z * (1 - (z / hh) ** 2)

    def surf_normal(x, z):  # local, pointing to the viewer
        return _norm((DOME_X * 2 * x / hw ** 2, -1.0, DOME_Z * 2 * z / hh ** 2))

    # ---- gold cap
    start = len(gold.faces)
    rings = []
    # (scale, y) with y=None meaning "on the domed surface", plus an offset
    ring_spec = [
        (0.90, DEPTH, 0.0),     # back
        (1.00, 0.000, 0.0),     # side
        (1.00, -0.020, 0.0),    # front edge of side
        (0.97, None, -0.010),   # raised bezel lip
        (0.93, None, 0.000),    # stone bed starts
        (0.70, None, 0.000),
        (0.45, None, 0.000),
        (0.20, None, 0.000),
    ]
    for s, y, off in ring_spec:
        ring = []
        for x, z in outline:
            x, z = x * s, z * s
            yy = (surf_y(x, z) + off) if y is None else y
            ring.append(gold.add(world(x, yy, z)))
        rings.append(ring)
    centre = gold.add(world(0.0, surf_y(0.0, 0.0), 0.0))
    for r in range(len(rings) - 1):
        smooth = r >= 4
        for j in range(n):
            a, b = rings[r], rings[r + 1]
            gold.faces.append(([a[j], a[(j + 1) % n], b[(j + 1) % n], b[j]], smooth))
    last = rings[-1]
    for j in range(n):
        gold.faces.append(([last[j], last[(j + 1) % n], centre], True))
    back = rings[0]
    for j in range(1, n - 1):
        gold.faces.append(([back[0], back[j], back[j + 1]], False))
    gold.orient_from(start, world(0.0, DEPTH * 0.4, 0.0))

    # ---- stones: one row hugging the outline, then a packed grid inside
    stones = _place_stones(outline)
    for x, z, r in stones:
        _add_stone(ice, x, z, r, surf_y, surf_normal, world, world_dir)
    for x, z in _place_beads(outline, stones):
        _add_bead(gold, x, z, BEAD_R, surf_y, surf_normal, world, world_dir)
    return len(stones)


def _place_stones(outline):
    """Honeycomb-pack stones into the tooth face, trying several grid phases."""
    lip = 0.010
    row = STONE_PITCH * math.sqrt(3) / 2
    best = []
    # ox of 0 or half a pitch keeps every row mirror-symmetric about the tooth centre
    for pi in range(2):
        for pj in range(16):
            ox, oz = pi / 2 * STONE_PITCH, pj / 16 * row
            fit = []
            for j in range(-10, 11):
                z = j * row + oz
                shift = STONE_PITCH / 2 if j % 2 else 0.0
                for i in range(-10, 11):
                    x = i * STONE_PITCH + shift + ox
                    if _inside(outline, x, z, lip + STONE_R):
                        fit.append((x, z))
            # prefer more stones, then the most centred layout
            key = (len(fit), -abs(sum(x for x, _ in fit)))
            if not best or key > best[0]:
                best = [key, fit]
    stones = [(x, z, STONE_R) for x, z in best[1]]

    # accent stones: smaller ones dropped into the leftover gold (tips, edges),
    # always added as mirrored pairs so the tooth stays symmetric
    clearance = STONE_PITCH * 0.03
    step = STONE_PITCH / 8
    for small in (STONE_R * 0.66, STONE_R * 0.48):
        cand = [(i * step, j * step) for i in range(0, 31) for j in range(-48, 49)]
        cand = [c for c in cand if _inside(outline, c[0], c[1], lip + small)]
        while True:
            best_pt, best_gap = None, 0.0
            for c in cand:
                gap = min(math.dist(c, (x, z)) - r for x, z, r in stones)
                if abs(c[0]) > 1e-9:  # its mirror twin must not clash with it
                    gap = min(gap, abs(c[0]) - small)
                if gap > best_gap:
                    best_pt, best_gap = c, gap
            if best_pt is None or best_gap < small + clearance:
                break
            x, z = best_pt
            stones.append((x, z, small))
            if abs(x) > 1e-9:
                stones.append((-x, z, small))
    return stones


def _place_beads(outline, stones):
    """Gold beads in the little triangle gaps between three stones."""
    beads = []
    gap = STONE_PITCH / (2 * math.sqrt(3))
    for i, a in enumerate(stones):
        for b in stones[i + 1:]:
            if a[2] != STONE_R or b[2] != STONE_R:
                continue
            d = math.dist(a[:2], b[:2])
            if d > STONE_PITCH * 1.05:
                continue
            mx, mz = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
            px, pz = -(b[1] - a[1]) / d, (b[0] - a[0]) / d
            for sgn in (1, -1):
                pt = (mx + px * gap * sgn, mz + pz * gap * sgn)
                if not _inside(outline, pt[0], pt[1], 0.012):
                    continue
                if min(math.dist(pt, q[:2]) - q[2] for q in stones) < BEAD_R * 0.5:
                    continue
                if any(math.dist(pt, q) < BEAD_R for q in beads):
                    continue
                beads.append(pt)
    return beads


def _frame(nrm):
    up = (0.0, 0.0, 1.0)
    t = _norm(_cross(up, nrm))
    b = _cross(nrm, t)
    return t, b


def _add_stone(mesh, x, z, r, surf_y, surf_normal, world, world_dir):
    """Brilliant-style crown: girdle(8) -> star ring(8, rotated) -> table(8)."""
    nrm = world_dir(*surf_normal(x, z))
    t, b = _frame(nrm)
    base = world(x, surf_y(x, z), z)
    seg = 8

    def pt(rad, ang, h):
        c, s = math.cos(ang) * rad, math.sin(ang) * rad
        return tuple(base[a] + t[a] * c + b[a] * s + nrm[a] * h for a in range(3))

    start = len(mesh.faces)
    girdle = [mesh.add(pt(r, k * 2 * math.pi / seg, 0.004)) for k in range(seg)]
    star = [mesh.add(pt(r * 0.80, (k + 0.5) * 2 * math.pi / seg, r * 0.24)) for k in range(seg)]
    table = [mesh.add(pt(r * 0.52, k * 2 * math.pi / seg, r * 0.36)) for k in range(seg)]
    bottom = mesh.add(pt(r * 0.2, 0.0, -r * 0.5))  # pavilion tip, hidden in the gold
    for k in range(seg):
        k1 = (k + 1) % seg
        mesh.faces.append(([girdle[k], girdle[k1], star[k]], False))
        mesh.faces.append(([star[k], girdle[k1], star[k1]], False))
        mesh.faces.append(([star[k], star[k1], table[k1]], False))
        mesh.faces.append(([star[k], table[k1], table[k]], False))
        mesh.faces.append(([girdle[k], girdle[k1], bottom], False))
    for k in range(1, seg - 1):
        mesh.faces.append(([table[0], table[k], table[k + 1]], False))
    mesh.orient_from(start, pt(0.0, 0.0, r * 0.1))


def _add_bead(mesh, x, z, r, surf_y, surf_normal, world, world_dir):
    nrm = world_dir(*surf_normal(x, z))
    t, b = _frame(nrm)
    base = world(x, surf_y(x, z), z)

    def pt(rad, ang, h):
        c, s = math.cos(ang) * rad, math.sin(ang) * rad
        return tuple(base[a] + t[a] * c + b[a] * s + nrm[a] * h for a in range(3))

    start = len(mesh.faces)
    ring = [mesh.add(pt(r, k * 2 * math.pi / 6, r * 0.2)) for k in range(6)]
    top = mesh.add(pt(0.0, 0.0, r * 0.9))
    for k in range(6):
        mesh.faces.append(([ring[k], ring[(k + 1) % 6], top], True))
    mesh.orient_from(start, pt(0.0, 0.0, 0.0))


# ---------------------------------------------------------------- whole set

def _build_row(spec, flip, z_edge, y_offset, gold, ice):
    teeth = list(reversed(spec)) + list(spec)
    widths = [t[0] * 0.96 for t in teeth]
    s = -sum(widths) / 2
    count = 0
    for tooth, step in zip(teeth, widths):
        mid = s + step / 2
        s += step
        phi = mid / ARCH_RADIUS
        cx = ARCH_RADIUS * math.sin(phi)
        cy = ARCH_RADIUS * (1 - math.cos(phi)) + y_offset
        cz = z_edge + (-tooth[1] / 2 if flip else tooth[1] / 2)
        count += _build_tooth(tooth, flip, cx, cy, cz, phi, gold, ice)
    return count


def build_grillz():
    gold, ice = Mesh("Grillz Gold"), Mesh("Grillz Diamonds")
    stones = _build_row(UPPER, False, BITE_GAP / 2, 0.0, gold, ice)
    stones += _build_row(LOWER, True, -BITE_GAP / 2, LOWER_SETBACK, gold, ice)
    return gold, ice, stones


def _tri_count(mesh):
    return sum(len(f[0]) - 2 for f in mesh.faces)


# ---------------------------------------------------------------- OBJ

def write_obj(path, meshes):
    mtl = os.path.splitext(os.path.basename(path))[0] + ".mtl"
    with open(path, "w") as f:
        f.write(f"# Diamond grillz (high detail)\nmtllib {mtl}\n")
        offset = 0
        for mesh, mat in meshes:
            f.write(f"o {mesh.name.replace(' ', '_')}\n")
            for x, y, z in mesh.verts:   # Blender Z-up -> OBJ Y-up
                f.write(f"v {x:.5f} {z:.5f} {-y:.5f}\n")
            f.write(f"usemtl {mat}\n")
            smooth = None
            for idx, sm in mesh.faces:
                if sm != smooth:
                    f.write("s 1\n" if sm else "s off\n")
                    smooth = sm
                f.write("f " + " ".join(str(i + 1 + offset) for i in idx) + "\n")
            offset += len(mesh.verts)
    with open(os.path.join(os.path.dirname(path), mtl), "w") as f:
        f.write("newmtl Gold\nKa 0.2 0.15 0.05\nKd 1.0 0.71 0.29\nKs 1.0 0.85 0.5\nNs 300\nillum 2\n\n"
                "newmtl Diamond\nKa 0.2 0.2 0.2\nKd 0.92 0.95 1.0\nKs 1 1 1\nNs 900\n"
                "Ni 2.42\nd 1\nillum 2\n")


# ---------------------------------------------------------------- Blender

def _set(node, names, value):
    for name in names:   # input names changed in Blender 4.0
        if name in node.inputs:
            node.inputs[name].default_value = value
            return


def _material(bpy, name, base, metallic, rough, transmission=0.0, ior=1.45):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    _set(bsdf, ["Base Color"], base)
    _set(bsdf, ["Metallic"], metallic)
    _set(bsdf, ["Roughness"], rough)
    _set(bsdf, ["IOR"], ior)
    _set(bsdf, ["Transmission Weight", "Transmission"], transmission)
    if transmission:
        _set(bsdf, ["Specular IOR Level", "Specular"], 1.0)
    return mat


def build_in_blender():
    import bpy

    gold, ice, stones = build_grillz()
    mats = {
        "Grillz Gold": _material(bpy, "Grillz Gold", (1.0, 0.71, 0.29, 1.0), 1.0, 0.12),
        "Grillz Diamonds": _material(bpy, "Grillz Diamond", (1.0, 1.0, 1.0, 1.0), 0.0, 0.0,
                                     transmission=1.0, ior=2.42),
    }
    for o in bpy.context.selected_objects:
        o.select_set(False)
    total = 0
    for m in (gold, ice):
        mesh = bpy.data.meshes.new(m.name)
        mesh.from_pydata(m.verts, [], [f[0] for f in m.faces])
        for poly, (_, smooth) in zip(mesh.polygons, m.faces):
            poly.use_smooth = smooth
        mesh.update()
        mesh.materials.append(mats[m.name])
        obj = bpy.data.objects.new(m.name, mesh)
        bpy.context.collection.objects.link(obj)
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        total += len(mesh.vertices)
    print(f"Grillz built: {stones} stones, {total} vertices")


if __name__ == "__main__":
    try:
        import bpy  # noqa: F401
    except ImportError:
        here = os.path.dirname(os.path.abspath(__file__))
        gold, ice, stones = build_grillz()
        write_obj(os.path.join(here, "grillz_detailed.obj"), [(gold, "Gold"), (ice, "Diamond")])
        print(f"Wrote grillz_detailed.obj: {stones} stones")
        for m in (gold, ice):
            print(f"  {m.name}: {len(m.verts)} vertices, {_tri_count(m)} triangles")
    else:
        build_in_blender()
