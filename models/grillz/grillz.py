"""
Diamond Grillz - low-poly generator (972 vertices).

Two ways to use this file:

  1. In Blender: open the Scripting tab, click Open, pick this file, press
     Run Script. It builds a "Grillz" object with a gold material and a
     procedural iced-out diamond pave material (no image files needed).

  2. Outside Blender:  python3 grillz.py
     Writes grillz.obj + grillz.mtl next to this file. Together with
     grillz_diamond_pave.png (made by make_texture.py) that is ready for the
     Roblox Studio 3D Importer or Blender's File > Import > Wavefront (.obj).

Axes follow Blender: X right, Y back (the front of the grillz faces -Y), Z up.
"""

import math

PROFILE_POINTS = 20  # outline points per tooth; 4 rings + 1 centre -> 81 verts/tooth

# UV layout of grillz_diamond_pave.png: u 0..0.9 is diamond pave, u 0.92..1 is plain gold.
PAVE_UV_CENTER = (0.45, 0.5)
PAVE_UV_SCALE = 2.0  # UV units per model unit on the tooth face
GOLD_UV = (0.96, 0.5)


# ---------------------------------------------------------------- 2D outline

def _fillet_polygon(corners, radius, per_corner):
    """Round every corner of a convex CCW polygon with `per_corner` points."""
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
        bis = (bis[0] / bl, bis[1] / bl)
        cd = r / math.sin(half)
        cx, cz = px + bis[0] * cd, pz + bis[1] * cd
        s = (px + u1[0] * t - cx, pz + u1[1] * t - cz)
        e = (px + u2[0] * t - cx, pz + u2[1] * t - cz)
        a0 = math.atan2(s[1], s[0])
        a1 = math.atan2(e[1], e[0])
        # walk the short way round (CCW polygon -> CCW arcs)
        while a1 < a0:
            a1 += 2 * math.pi
        if a1 - a0 > math.pi:
            a1 -= 2 * math.pi
        for k in range(per_corner):
            a = a0 + (a1 - a0) * k / (per_corner - 1)
            out.append((cx + r * math.cos(a), cz + r * math.sin(a)))
    return out


def tooth_outline(width, height, point):
    """Front outline of one tooth, CCW seen from the front. Bite edge at -height/2.

    point = 0 gives a rounded block, larger values give the pointed
    "house" shape toward the gum side (+height/2).
    """
    w, h = width / 2, height / 2
    if point <= 0:
        corners = [(-w, -h), (w, -h), (w, h), (-w, h)]
        pts = _fillet_polygon(corners, width * 0.22, PROFILE_POINTS // 4)
    else:
        corners = [(-w, -h), (w, -h), (w, h - point), (0.0, h), (-w, h - point)]
        pts = _fillet_polygon(corners, width * 0.16, PROFILE_POINTS // 5)
    assert len(pts) == PROFILE_POINTS
    return pts


# ---------------------------------------------------------------- 3D teeth

# (width, height, point) from the middle outward; mirrored to the other side.
UPPER = [(0.34, 0.44, 0.13), (0.29, 0.38, 0.09), (0.26, 0.36, 0.0)]
LOWER = [(0.26, 0.36, 0.10), (0.26, 0.36, 0.10), (0.25, 0.38, 0.14)]

ARCH_RADIUS = 1.1
DEPTH = 0.16       # front-to-back thickness of a cap
BITE_GAP = 0.025   # vertical gap between the two rows
LOWER_SETBACK = 0.05


def _build_tooth(outline, flip, cx, cy, cz, angle, verts, faces):
    """Append one capped tooth. Faces are (indices, uvs, material)."""
    base = len(verts)
    sz = -1.0 if flip else 1.0
    ca, sa = math.cos(angle), math.sin(angle)

    def place(x, y, z):
        z *= sz
        return (cx + x * ca - y * sa, cy + x * sa + y * ca, cz + z)

    # ring: (outline scale, y offset); negative y = toward the viewer
    rings = [
        (0.90, DEPTH),    # 0 back, tapered
        (1.00, 0.0),      # 1 front outer edge
        (0.86, -0.030),   # 2 gold bezel / start of stones
        (0.50, -0.052),   # 3 dome
    ]
    for s, y in rings:
        for x, z in outline:
            verts.append(place(x * s, y, z * s))
    verts.append(place(0.0, -0.060, 0.0))  # 4 dome centre
    centre = len(verts) - 1
    n = len(outline)

    def vid(ring, j):
        return base + ring * n + (j % n)

    def pave_uv(ring, j):
        s = rings[ring][0]
        x, z = outline[j % n]
        z *= sz
        return (PAVE_UV_CENTER[0] + x * s * PAVE_UV_SCALE,
                PAVE_UV_CENTER[1] + z * s * PAVE_UV_SCALE)

    gold = [GOLD_UV] * 4
    for j in range(n):
        faces.append(([vid(0, j), vid(0, j + 1), vid(1, j + 1), vid(1, j)], gold, "gold"))
        faces.append(([vid(1, j), vid(1, j + 1), vid(2, j + 1), vid(2, j)], gold, "gold"))
        faces.append(([vid(2, j), vid(2, j + 1), vid(3, j + 1), vid(3, j)],
                      [pave_uv(2, j), pave_uv(2, j + 1), pave_uv(3, j + 1), pave_uv(3, j)], "pave"))
        faces.append(([vid(3, j), vid(3, j + 1), centre],
                      [pave_uv(3, j), pave_uv(3, j + 1), PAVE_UV_CENTER], "pave"))
    # back cap as a triangle fan (outline is convex), no extra vertices
    for j in range(1, n - 1):
        faces.append(([vid(0, 0), vid(0, j), vid(0, j + 1)], [GOLD_UV] * 3, "gold"))

    # wind every face outward from the tooth's own centre (the cap is convex)
    tooth_centre = place(0.0, DEPTH * 0.4, 0.0)
    for k in range(len(faces) - (n * 4 + n - 2), len(faces)):
        idx, uvs, mat = faces[k]
        p = [verts[i] for i in idx]
        e1 = [p[1][a] - p[0][a] for a in range(3)]
        e2 = [p[2][a] - p[0][a] for a in range(3)]
        nrm = (e1[1] * e2[2] - e1[2] * e2[1],
               e1[2] * e2[0] - e1[0] * e2[2],
               e1[0] * e2[1] - e1[1] * e2[0])
        c = [sum(q[a] for q in p) / len(p) - tooth_centre[a] for a in range(3)]
        if nrm[0] * c[0] + nrm[1] * c[1] + nrm[2] * c[2] < 0:
            faces[k] = (idx[::-1], uvs[::-1], mat)


def _build_row(spec, flip, z_edge, y_offset, verts, faces):
    teeth = list(reversed(spec)) + list(spec)  # outer-left ... centre ... outer-right
    widths = [t[0] * 0.96 for t in teeth]      # slight overlap so the caps join
    s = -sum(widths) / 2
    for (w, h, point), step in zip(teeth, widths):
        mid = s + step / 2
        s += step
        phi = mid / ARCH_RADIUS
        cx = ARCH_RADIUS * math.sin(phi)
        cy = ARCH_RADIUS * (1 - math.cos(phi)) + y_offset
        cz = z_edge + (-h / 2 if flip else h / 2)
        _build_tooth(tooth_outline(w, h, point), flip, cx, cy, cz, phi, verts, faces)


def build_grillz():
    verts, faces = [], []
    _build_row(UPPER, False, BITE_GAP / 2, 0.0, verts, faces)
    _build_row(LOWER, True, -BITE_GAP / 2, LOWER_SETBACK, verts, faces)
    return verts, faces


# ---------------------------------------------------------------- OBJ export

def write_obj(path, verts, faces):
    import os
    mtl_name = os.path.splitext(os.path.basename(path))[0] + ".mtl"
    uv_index, uv_list, lines = {}, [], []
    for idx, uvs, _ in faces:
        refs = []
        for v, uv in zip(idx, uvs):
            key = (round(uv[0], 6), round(uv[1], 6))
            if key not in uv_index:
                uv_index[key] = len(uv_list) + 1
                uv_list.append(key)
            refs.append(f"{v + 1}/{uv_index[key]}")
        lines.append("f " + " ".join(refs))
    with open(path, "w") as f:
        f.write(f"# Diamond grillz, {len(verts)} vertices\nmtllib {mtl_name}\no Grillz\n")
        # OBJ is Y-up: (x, y, z) Blender -> (x, z, -y)
        for x, y, z in verts:
            f.write(f"v {x:.5f} {z:.5f} {-y:.5f}\n")
        for u, v in uv_list:
            f.write(f"vt {u:.5f} {v:.5f}\n")
        f.write("usemtl GrillzDiamondGold\ns 1\n")
        f.write("\n".join(lines) + "\n")
    with open(os.path.join(os.path.dirname(path), mtl_name), "w") as f:
        f.write("newmtl GrillzDiamondGold\nKa 1 1 1\nKd 1 1 1\nKs 1 0.9 0.6\nNs 250\n"
                "illum 2\nmap_Kd grillz_diamond_pave.png\n")


# ---------------------------------------------------------------- Blender

def _principled(mat):
    mat.use_nodes = True
    return mat.node_tree.nodes.get("Principled BSDF")


def _set(node, names, value):
    for name in names:  # input names changed in Blender 4.0
        if name in node.inputs:
            node.inputs[name].default_value = value
            return


def _gold_material(bpy):
    mat = bpy.data.materials.new("Grillz Gold")
    bsdf = _principled(mat)
    _set(bsdf, ["Base Color"], (1.0, 0.71, 0.29, 1.0))
    _set(bsdf, ["Metallic"], 1.0)
    _set(bsdf, ["Roughness"], 0.18)
    return mat


def _pave_material(bpy):
    """Gold setting with a grid of domed brilliant stones, all procedural."""
    mat = bpy.data.materials.new("Grillz Diamond Pave")
    bsdf = _principled(mat)
    nt = mat.node_tree
    N, L = nt.nodes, nt.links
    out = N.get("Material Output")

    uv = N.new("ShaderNodeTexCoord")
    scale = N.new("ShaderNodeVectorMath"); scale.operation = "SCALE"
    scale.inputs[3].default_value = 1.0 / 0.16  # stone pitch in UV units
    frac = N.new("ShaderNodeVectorMath"); frac.operation = "FRACTION"
    sub = N.new("ShaderNodeVectorMath"); sub.operation = "SUBTRACT"
    sub.inputs[1].default_value = (0.5, 0.5, 0.0)
    flat = N.new("ShaderNodeVectorMath"); flat.operation = "MULTIPLY"
    flat.inputs[1].default_value = (1.0, 1.0, 0.0)
    dist = N.new("ShaderNodeVectorMath"); dist.operation = "LENGTH"
    height = N.new("ShaderNodeMath"); height.operation = "SUBTRACT"
    height.inputs[0].default_value = 0.42
    height.use_clamp = True
    mask = N.new("ShaderNodeMath"); mask.operation = "GREATER_THAN"
    mask.inputs[1].default_value = 0.0
    bump = N.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.6
    bump.inputs["Distance"].default_value = 0.02

    L.new(uv.outputs["UV"], scale.inputs[0])
    L.new(scale.outputs[0], frac.inputs[0])
    L.new(frac.outputs[0], sub.inputs[0])
    L.new(sub.outputs[0], flat.inputs[0])
    L.new(flat.outputs[0], dist.inputs[0])
    L.new(dist.outputs["Value"], height.inputs[1])
    L.new(height.outputs[0], mask.inputs[0])
    L.new(height.outputs[0], bump.inputs["Height"])

    # gold = existing Principled; diamond = a second Principled
    _set(bsdf, ["Base Color"], (1.0, 0.71, 0.29, 1.0))
    _set(bsdf, ["Metallic"], 1.0)
    _set(bsdf, ["Roughness"], 0.2)
    diamond = N.new("ShaderNodeBsdfPrincipled")
    _set(diamond, ["Base Color"], (1.0, 1.0, 1.0, 1.0))
    _set(diamond, ["Roughness"], 0.0)
    _set(diamond, ["IOR"], 2.42)
    _set(diamond, ["Transmission Weight", "Transmission"], 1.0)
    _set(diamond, ["Specular IOR Level", "Specular"], 1.0)
    L.new(bump.outputs["Normal"], diamond.inputs["Normal"])
    L.new(bump.outputs["Normal"], bsdf.inputs["Normal"])

    mix = N.new("ShaderNodeMixShader")
    L.new(mask.outputs[0], mix.inputs["Fac"])
    L.new(bsdf.outputs[0], mix.inputs[1])
    L.new(diamond.outputs[0], mix.inputs[2])
    L.new(mix.outputs[0], out.inputs["Surface"])
    return mat


def build_in_blender():
    import bpy

    verts, faces = build_grillz()
    mesh = bpy.data.meshes.new("Grillz")
    mesh.from_pydata(verts, [], [f[0] for f in faces])
    mesh.update()

    uv_layer = mesh.uv_layers.new(name="UVMap")
    for poly, (_, uvs, mat) in zip(mesh.polygons, faces):
        poly.material_index = 0 if mat == "gold" else 1
        poly.use_smooth = mat == "pave"
        for loop_index, uv in zip(poly.loop_indices, uvs):
            uv_layer.data[loop_index].uv = uv

    mesh.materials.append(_gold_material(bpy))
    mesh.materials.append(_pave_material(bpy))

    obj = bpy.data.objects.new("Grillz", mesh)
    bpy.context.collection.objects.link(obj)
    for o in bpy.context.selected_objects:
        o.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    print(f"Grillz built: {len(mesh.vertices)} vertices, {len(mesh.polygons)} faces")


if __name__ == "__main__":
    try:
        import bpy  # noqa: F401
    except ImportError:
        import os
        here = os.path.dirname(os.path.abspath(__file__))
        v, f = build_grillz()
        write_obj(os.path.join(here, "grillz.obj"), v, f)
        print(f"Wrote grillz.obj: {len(v)} vertices, {len(f)} faces")
    else:
        build_in_blender()
