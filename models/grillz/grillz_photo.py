"""
Photo-textured grillz (under 1000 vertices).

Each tooth's outline is traced from the reference photo, and the tooth carries
its own piece of that photo as its texture, so the model looks like the photo.

    python3 grillz_photo.py path/to/photo.jpg

Writes next to this file:
    grillz_photo_texture.png   the texture (a crop of the photo)
    grillz_photo.obj / .mtl    model + material pointing at the texture
    grillz_photo.glb           the same model with the texture built in (one file)

Needs Pillow + numpy. The seam positions below were measured on the
1024x1024 reference photo; another photo needs its own seams.

Axes follow Blender: X right, Y back (the front faces -Y), Z up.
"""

import json
import math
import os
import struct
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------- photo layout

THRESHOLD = 40          # brightness that separates gold/stones from the black background
UPPER_SEAMS = [0, 157, 308, 524, 745, 883, 1024]   # x of the seams between upper teeth
LOWER_SEAMS = [0, 245, 376, 520, 663, 792, 1024]   # x of the seams between lower teeth
SPLIT_SEARCH = (505, 570)   # y range holding the dark line between the two rows
LOWER_LIMIT = 752           # below this is the mirror reflection, not teeth

TEX_BAND = (250, 762)       # rows of the photo kept as the texture (1024 x 512)

# ---------------------------------------------------------------- model

POINTS = 26           # outline points per tooth -> 3 rings + 2 centres = 80 verts/tooth
SCALE = 0.002         # model units per photo pixel
CENTER_X = 522        # photo x of the middle of the set
ARCH_UPPER = 1.15     # arch radius of each row
ARCH_LOWER = 1.0
LOWER_SETBACK = 0.06  # lower row sits a little behind the upper row
DEPTH = 0.15          # front-to-back thickness of a cap
DOME = 0.06           # how far the middle of a tooth bulges forward
EDGE_PX = 2.5         # keep texture lookups this far inside the traced edge
BAND_PX = 7.0         # side walls use the gold rim band just inside the edge


# ---------------------------------------------------------------- tracing

def _shift_max(m, r):
    out = m.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dx * dx + dy * dy <= r * r:
                out |= np.roll(np.roll(m, dy, 0), dx, 1)
    return out


def silhouette(rgb):
    """Solid mask of the grillz: bright pixels, small gaps closed, holes filled."""
    mask = rgb.max(axis=2) > THRESHOLD
    mask = ~_shift_max(~_shift_max(mask, 2), 2)          # closing
    outside = Image.fromarray(np.where(mask, 0, 255).astype(np.uint8)).copy()  # own buffer, so the fill sticks
    ImageDraw.floodfill(outside, (0, 0), 128)
    return np.asarray(outside) != 128                     # everything not reachable from the corner


def split_line(rgb):
    """y of the dark line between the rows, for every column."""
    v = rgb.max(axis=2).astype(float)
    y0, y1 = SPLIT_SEARCH
    band = v[y0:y1]
    k = np.ones(9) / 9
    band = np.apply_along_axis(lambda c: np.convolve(c, np.ones(5) / 5, "same"), 0, band)
    band = np.apply_along_axis(lambda r: np.convolve(r, k, "same"), 1, band)
    raw = band.argmin(axis=0) + y0
    # the bite line is a gentle curve: fit one through the darkest points where
    # both rows exist, ignoring dark spots between stones that pull it off course
    xs = np.arange(UPPER_SEAMS[1], UPPER_SEAMS[-2])
    ys = raw[xs]
    keep = np.abs(ys - np.median(ys)) < 8
    for _ in range(5):
        coef = np.polyfit(xs[keep], ys[keep], 2)
        keep = np.abs(ys - np.polyval(coef, xs)) < 5
    return np.round(np.polyval(coef, np.arange(rgb.shape[1]))).astype(int)


def _component(mask, seed):
    img = Image.fromarray(np.where(mask, 255, 0).astype(np.uint8)).copy()
    ImageDraw.floodfill(img, seed, 128)
    return np.asarray(img) == 128


def _trace(mask, rays=720, gap=4.0):
    """Star-shaped outline of a blob: walk out from the centroid along many rays."""
    ys, xs = np.nonzero(mask)
    cx, cy = xs.mean(), ys.mean()
    h, w = mask.shape
    pts = []
    for k in range(rays):
        a = 2 * math.pi * k / rays
        dx, dy = math.cos(a), -math.sin(a)      # CCW as seen in the photo (y down)
        r, last, outside = 0.0, 0.0, 0.0
        while outside < gap:
            r += 0.5
            x, y = int(round(cx + dx * r)), int(round(cy + dy * r))
            if 0 <= x < w and 0 <= y < h and mask[y, x]:
                last, outside = r, 0.0
            else:
                outside += 0.5
        pts.append((cx + dx * last, cy + dy * last))
    return (cx, cy), pts


def _simplify(pts, n):
    """Visvalingam: drop the least important point until n remain (keeps the corners)."""
    pts = list(pts)

    def area(i):
        ax, ay = pts[i - 1]
        bx, by = pts[i]
        cx, cy = pts[(i + 1) % len(pts)]
        return abs((bx - ax) * (cy - ay) - (cx - ax) * (by - ay))

    while len(pts) > n:
        i = min(range(len(pts)), key=area)
        pts.pop(i)
    return pts


def trace_teeth(rgb):
    """Returns [(row, centroid, outline)] for 12 teeth, outlines in photo pixels."""
    sil = silhouette(rgb)
    split = split_line(rgb)
    h, w = sil.shape
    yy, xx = np.mgrid[0:h, 0:w]
    teeth = []
    for row, seams in (("upper", UPPER_SEAMS), ("lower", LOWER_SEAMS)):
        side = (yy < split[None, :]) if row == "upper" else ((yy > split[None, :]) & (yy < LOWER_LIMIT))
        for i in range(6):
            region = sil & side & (xx >= seams[i]) & (xx < seams[i + 1])
            # seed the flood fill on a pixel of the region near its middle
            sx = int(np.median(np.nonzero(region)[1]))
            col = np.nonzero(region[:, sx])[0]
            seed = (sx, int(col[len(col) // 2]))
            blob = _component(region, seed)
            centroid, dense = _trace(blob)
            teeth.append((row, centroid, _simplify(dense, POINTS)))
    return teeth, split


# ---------------------------------------------------------------- mesh

def _toward(p, c, px):
    """Move point p toward c by px pixels."""
    dx, dy = c[0] - p[0], c[1] - p[1]
    d = math.hypot(dx, dy)
    if d <= px:
        return c
    return (p[0] + dx / d * px, p[1] + dy / d * px)


def build_mesh(teeth, split):
    verts, uvs, faces = [], [], []
    band0 = TEX_BAND[0]
    tex_h = TEX_BAND[1] - TEX_BAND[0]
    mid_y = float(np.median(split[UPPER_SEAMS[1]:UPPER_SEAMS[-2]]))

    def uv_of(p):
        return (p[0] / 1024.0, 1.0 - (p[1] - band0) / tex_h)

    for row, (pcx, pcy), outline in teeth:
        radius = ARCH_UPPER if row == "upper" else ARCH_LOWER
        setback = 0.0 if row == "upper" else LOWER_SETBACK
        x_mid = (pcx - CENTER_X) * SCALE
        phi = math.asin(max(-0.95, min(0.95, x_mid / radius)))
        cos_p = math.cos(phi)
        ca, sa = math.cos(phi), math.sin(phi)
        cx, cy = x_mid, radius * (1 - cos_p) + setback
        cz = -(pcy - mid_y) * SCALE
        base = len(verts)
        n = len(outline)

        def place(p, scale, y):
            # photo point -> tooth-local (un-foreshortened) -> world
            lx = (p[0] - pcx) * scale * SCALE / cos_p
            lz = -(p[1] - pcy) * scale * SCALE
            return (cx + lx * ca - y * sa, cy + lx * sa + y * ca, cz + lz)

        centre = (pcx, pcy)
        # ring 0: back (tapered), ring 1: front edge, ring 2: dome
        for p in outline:
            verts.append(place(p, 0.88, DEPTH))
            uvs.append(uv_of(_toward(p, centre, EDGE_PX + BAND_PX)))
        for p in outline:
            verts.append(place(p, 1.0, 0.0))
            uvs.append(uv_of(_toward(p, centre, EDGE_PX)))
        inner = 0.72
        for p in outline:
            q = _toward(p, centre, EDGE_PX)
            q = (pcx + (q[0] - pcx) * inner, pcy + (q[1] - pcy) * inner)
            verts.append(place(q, 1.0, -DOME * (1 - inner * inner)))
            uvs.append(uv_of(q))
        verts.append(place(centre, 1.0, -DOME))
        uvs.append(uv_of(centre))
        verts.append(place(centre, 1.0, DEPTH))
        uvs.append(uv_of(centre))
        front_c, back_c = base + 3 * n, base + 3 * n + 1

        def v(ring, j):
            return base + ring * n + j % n

        first = len(faces)
        for j in range(n):
            faces.append((v(0, j), v(0, j + 1), v(1, j + 1), v(1, j)))   # side wall
            faces.append((v(1, j), v(1, j + 1), v(2, j + 1), v(2, j)))   # front, outer
            faces.append((v(2, j), v(2, j + 1), front_c))               # front, middle
            faces.append((v(0, j + 1), v(0, j), back_c))                # back
        # wind every face outward from the middle of the cap
        mid = place(centre, 1.0, DEPTH * 0.4)
        for k in range(first, len(faces)):
            f = faces[k]
            p = [verts[i] for i in f]
            e1 = [p[1][a] - p[0][a] for a in range(3)]
            e2 = [p[2][a] - p[0][a] for a in range(3)]
            nrm = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0])
            c = [sum(q[a] for q in p) / len(p) - mid[a] for a in range(3)]
            if sum(nrm[a] * c[a] for a in range(3)) < 0:
                faces[k] = f[::-1]
    return verts, uvs, faces


def triangles(faces):
    out = []
    for f in faces:
        for k in range(1, len(f) - 1):
            out.append((f[0], f[k], f[k + 1]))
    return out


def smooth_normals(verts, tris):
    v = np.array(verts)
    t = np.array(tris)
    fn = np.cross(v[t[:, 1]] - v[t[:, 0]], v[t[:, 2]] - v[t[:, 0]])   # area weighted
    vn = np.zeros_like(v)
    for k in range(3):
        np.add.at(vn, t[:, k], fn)
    return vn / np.linalg.norm(vn, axis=1, keepdims=True)


# ---------------------------------------------------------------- export

def to_y_up(p):
    """Blender Z-up -> OBJ / glTF Y-up."""
    return (p[0], p[2], -p[1])


def write_texture(rgb, path):
    Image.fromarray(rgb[TEX_BAND[0]:TEX_BAND[1]]).save(path, optimize=True)


def write_obj(path, verts, uvs, faces, normals, texture_name):
    mtl = os.path.splitext(os.path.basename(path))[0] + ".mtl"
    with open(path, "w") as f:
        f.write(f"# Photo-textured diamond grillz, {len(verts)} vertices\nmtllib {mtl}\no Grillz\n")
        for p in verts:
            f.write("v %.5f %.5f %.5f\n" % to_y_up(p))
        for u, v in uvs:
            f.write(f"vt {u:.5f} {v:.5f}\n")
        for nrm in normals:
            f.write("vn %.4f %.4f %.4f\n" % to_y_up(nrm))
        f.write("usemtl GrillzPhoto\ns 1\n")
        for face in faces:
            f.write("f " + " ".join(f"{i + 1}/{i + 1}/{i + 1}" for i in face) + "\n")
    with open(os.path.join(os.path.dirname(path), mtl), "w") as f:
        f.write(f"newmtl GrillzPhoto\nKa 1 1 1\nKd 1 1 1\nKs 0.5 0.5 0.5\nNs 120\nillum 2\nmap_Kd {texture_name}\n")


def write_glb(path, verts, uvs, tris, normals, png_bytes):
    pos = np.array([to_y_up(p) for p in verts], np.float32)
    nrm = np.array([to_y_up(p) for p in normals], np.float32)
    tex = np.array([(u, 1.0 - v) for u, v in uvs], np.float32)   # glTF UVs start top-left
    idx = np.array(tris, np.uint16 if len(verts) < 65536 else np.uint32).reshape(-1)

    blob = bytearray()
    views = []

    def add_view(data, target=None):
        while len(blob) % 4:
            blob.append(0)
        view = {"buffer": 0, "byteOffset": len(blob), "byteLength": len(data)}
        if target:
            view["target"] = target
        blob.extend(data)
        views.append(view)
        return len(views) - 1

    v_pos = add_view(pos.tobytes(), 34962)
    v_nrm = add_view(nrm.tobytes(), 34962)
    v_tex = add_view(tex.tobytes(), 34962)
    v_idx = add_view(idx.tobytes(), 34963)
    v_img = add_view(png_bytes)
    while len(blob) % 4:
        blob.append(0)

    gltf = {
        "asset": {"version": "2.0", "generator": "grillz_photo.py"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0, "name": "Grillz"}],
        "meshes": [{"name": "Grillz", "primitives": [{
            "attributes": {"POSITION": 0, "NORMAL": 1, "TEXCOORD_0": 2},
            "indices": 3, "material": 0, "mode": 4}]}],
        "materials": [{"name": "GrillzPhoto", "pbrMetallicRoughness": {
            "baseColorTexture": {"index": 0}, "metallicFactor": 0.0, "roughnessFactor": 0.45}}],
        "textures": [{"sampler": 0, "source": 0}],
        "samplers": [{"magFilter": 9729, "minFilter": 9987, "wrapS": 33071, "wrapT": 33071}],
        "images": [{"bufferView": v_img, "mimeType": "image/png", "name": "grillz_photo_texture"}],
        "accessors": [
            {"bufferView": v_pos, "componentType": 5126, "count": len(pos), "type": "VEC3",
             "min": pos.min(axis=0).tolist(), "max": pos.max(axis=0).tolist()},
            {"bufferView": v_nrm, "componentType": 5126, "count": len(nrm), "type": "VEC3"},
            {"bufferView": v_tex, "componentType": 5126, "count": len(tex), "type": "VEC2"},
            {"bufferView": v_idx, "componentType": 5123 if idx.dtype == np.uint16 else 5125,
             "count": len(idx), "type": "SCALAR"},
        ],
        "bufferViews": views,
        "buffers": [{"byteLength": len(blob)}],
    }
    js = json.dumps(gltf, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    total = 12 + 8 + len(js) + 8 + len(blob)
    with open(path, "wb") as f:
        f.write(struct.pack("<4sII", b"glTF", 2, total))
        f.write(struct.pack("<I4s", len(js), b"JSON") + js)
        f.write(struct.pack("<I4s", len(blob), b"BIN\0") + bytes(blob))


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: python3 grillz_photo.py path/to/photo.jpg")
    rgb = np.asarray(Image.open(sys.argv[1]).convert("RGB"))
    if rgb.shape[:2] != (1024, 1024):
        sys.exit("expected the 1024x1024 reference photo (the seams are measured on it)")

    teeth, split = trace_teeth(rgb)
    verts, uvs, faces = build_mesh(teeth, split)
    tris = triangles(faces)
    normals = smooth_normals(verts, tris)

    tex_name = "grillz_photo_texture.png"
    tex_path = os.path.join(HERE, tex_name)
    write_texture(rgb, tex_path)
    write_obj(os.path.join(HERE, "grillz_photo.obj"), verts, uvs, faces, normals, tex_name)
    with open(tex_path, "rb") as f:
        write_glb(os.path.join(HERE, "grillz_photo.glb"), verts, uvs, tris, normals, f.read())
    print(f"grillz_photo: {len(verts)} vertices, {len(tris)} triangles")


if __name__ == "__main__":
    main()
