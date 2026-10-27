"""
Textures for the Starburst Blade, painted in the style of the reference sheet:
hot yellow-white cores, orange and red bands, dark crimson / black outlines and
white sparkles. numpy only, so this also runs inside Blender's bundled Python.

Every function returns float32 RGBA (H, W, 4) in 0..1, row 0 = top of the image.
These are PRE-COLOURED (the Roblox effects use them with a white tint), so the
dark outlines survive instead of being washed out by additive glow.
"""

import math

import numpy as np

YELLOW = np.array([1.0, 0.97, 0.72])
GOLD = np.array([1.0, 0.78, 0.25])
ORANGE = np.array([1.0, 0.45, 0.08])
RED = np.array([0.85, 0.08, 0.04])
CRIMSON = np.array([0.32, 0.03, 0.03])
INK = np.array([0.07, 0.01, 0.01])


# ---------------------------------------------------------------- helpers

def _grid(h, w):
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    return (x + 0.5) / w * 2 - 1, (y + 0.5) / h * 2 - 1


def _smooth(x, e0, e1):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def value_noise(h, w, cy, cx, seed, periodic_x=False):
    rng = np.random.default_rng(seed)
    g = rng.random((cy + 3, cx + 3)).astype(np.float32)
    if periodic_x:
        g[:, cx:cx + 3] = g[:, 0:3]
    ys = np.linspace(0, cy, h, endpoint=False) + 1
    xs = np.linspace(0, cx, w, endpoint=False) + 1
    y0, x0 = np.floor(ys).astype(int), np.floor(xs).astype(int)
    ty, tx = _smooth(ys - y0, 0, 1)[:, None], _smooth(xs - x0, 0, 1)[None, :]
    a, b = g[y0][:, x0], g[y0][:, x0 + 1]
    c, d = g[y0 + 1][:, x0], g[y0 + 1][:, x0 + 1]
    return (a * (1 - tx) + b * tx) * (1 - ty) + (c * (1 - tx) + d * tx) * ty


def fbm(h, w, cy, cx, seed, octaves=4, periodic_x=False):
    tot, amp, norm = np.zeros((h, w), np.float32), 1.0, 0.0
    for o in range(octaves):
        tot += amp * value_noise(h, w, cy * 2 ** o, cx * 2 ** o, seed + 7 * o, periodic_x)
        norm += amp
        amp *= 0.5
    return tot / norm


def heat_colour(heat):
    """Map 0..1 'heat' to ink -> crimson -> red -> orange -> gold -> yellow-white."""
    stops = [(0.0, INK), (0.18, CRIMSON), (0.38, RED), (0.58, ORANGE), (0.78, GOLD), (1.0, YELLOW)]
    heat = np.clip(heat, 0, 1)
    out = np.zeros(heat.shape + (3,), np.float32)
    for (p0, c0), (p1, c1) in zip(stops[:-1], stops[1:]):
        m = (heat >= p0) & (heat <= p1)
        t = ((heat - p0) / (p1 - p0))[m][:, None]
        out[m] = c0 * (1 - t) + c1 * t
    return out


def rgba(rgb, alpha):
    return np.concatenate([np.clip(rgb, 0, 1), np.clip(alpha, 0, 1)[..., None]], axis=2).astype(np.float32)


def sparkles(h, w, count, seed, size=1.5):
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w]
    out = np.zeros((h, w), np.float32)
    for _ in range(count):
        cx, cy = rng.uniform(0, w), rng.uniform(0, h)
        r = rng.uniform(0.6, 1.0) * size
        out = np.maximum(out, np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (r * r)))
    return out


def _layered(dist, width):
    """Signed-distance style layering: dist = 1 at the centre line, 0 at the outer edge.
    Returns (heat, alpha) giving a bright core, colour bands and a dark ink rim."""
    heat = _smooth(dist, 0.0, 1.0) ** 0.9
    alpha = _smooth(dist, 0.0, 0.06)
    return heat, alpha


# ---------------------------------------------------------------- sword surface textures

def blade_shell(w=512, h=1024, seed=3):
    """UV u across the blade (0 = rim edge, 1 = shadow edge), v along it (row 0 = tip)."""
    u = np.linspace(0, 1, w)[None, :] * np.ones((h, 1))
    n = fbm(h, w, 32, 4, seed)
    base = CRIMSON * (0.75 + 0.5 * n[..., None])
    rim = _smooth(0.16 - u, 0.0, 0.12)[..., None]                    # lit orange-brown rim
    rgb = base * (1 - rim) + np.array([0.82, 0.36, 0.1]) * rim
    shadow = _smooth(u, 0.62, 0.95)[..., None]                        # dark band
    rgb = rgb * (1 - shadow) + INK * 1.6 * shadow
    sp = sparkles(h, w, 45, seed + 1, 4.0) * _smooth(u, 0.6, 0.8)
    rgb = rgb * (1 - sp[..., None]) + sp[..., None]
    return rgba(rgb, np.ones((h, w)))


def ray_shell(w=256, h=1024, seed=5):
    """Star rays: black with a thin red edge glint; u across, v along (row 0 = tip)."""
    u = np.linspace(-1, 1, w)[None, :] * np.ones((h, 1))
    edge = _smooth(np.abs(u), 0.7, 1.0)[..., None]
    n = fbm(h, w, 24, 3, seed)[..., None]
    rgb = INK * (1.2 + 0.6 * n) * (1 - edge) + RED * 0.55 * edge
    sp = sparkles(h, w, 18, seed + 2, 2.0)[..., None]
    rgb = rgb * (1 - sp) + sp
    return rgba(rgb, np.ones((h, w)))


def handle_shell(w=256, h=1024, seed=7):
    """Handle: dark red-brown with an orange heat glow down the middle."""
    u = np.linspace(0, 1, w)[None, :] * np.ones((h, 1))
    around = np.cos((u - 0.25) * 2 * math.pi)                          # u=0.25 faces the front
    glow = _smooth(np.abs(around), 0.55, 1.0)[..., None]
    n = fbm(h, w, 40, 6, seed)[..., None]
    rgb = CRIMSON * (0.7 + 0.5 * n) * (1 - glow) + np.array([0.75, 0.22, 0.05]) * glow
    v = np.linspace(0, 1, h)[:, None, None]
    rgb = rgb * (0.55 + 0.45 * (1 - v))                                # darker towards the point
    return rgba(rgb, np.ones((h, w)))


def shell_atlas():
    """Blade shell on the left half, ray shell on the right half (one texture for the Shell mesh)."""
    a = blade_shell(512, 1024)
    b = ray_shell(512, 1024)
    return np.concatenate([a, b], axis=1)


# ---------------------------------------------------------------- VFX (pre-coloured)

def fire_lick_flipbook(frame=256, grid=4, seed=11):
    """16 frames of a flame tongue (sheet item 2): bright core, red body, dark outline."""
    out = np.zeros((frame * grid, frame * grid, 4), np.float32)
    x, y = _grid(frame, frame)
    warp1 = fbm(frame, frame, 3, 3, seed) - 0.5
    warp2 = fbm(frame, frame, 4, 4, seed + 3) - 0.5
    for k in range(grid * grid):
        t = k / (grid * grid - 1)
        sx = x * 0.85 + warp1 * (0.35 + 0.5 * t) + 0.18 * np.sin(y * 3.5 + t * 7)
        sy = y * 0.85 + 0.25 - 0.55 * t + warp2 * (0.3 + 0.4 * t)
        width = 0.55 * (1 - 0.4 * t) * _smooth(sy + 1.0, 0.0, 0.9) * (1 - _smooth(sy, -0.35, 0.85) * 0.85)
        dist = 1 - np.sqrt((sx / np.maximum(width, 1e-3)) ** 2 + ((sy + 0.25) / (0.95 + 0.4 * t)) ** 2)
        dist = np.clip(dist, -1, 1)
        heat = _smooth(dist, 0.05, 0.85) * (1 - 0.55 * t)
        alpha = _smooth(dist, -0.02, 0.06) * (1 - _smooth(t, 0.65, 1.0))
        # dark outline: heat near 0 where alpha is on
        rgb = heat_colour(heat * 1.15)
        out[(k // grid) * frame:(k // grid + 1) * frame, (k % grid) * frame:(k % grid + 1) * frame] = rgba(rgb, alpha)
    return out


def streak(w=1024, h=256, seed=2):
    """Tapered energy streak (sheet item 3 blade): u along (0 = thick end, 1 = needle tip)."""
    u = np.linspace(0, 1, w)[None, :] * np.ones((h, 1))
    v = np.linspace(-1, 1, h)[:, None] * np.ones((1, w))
    half = 0.7 * (1 - u) ** 1.35 * _smooth(u, 0.0, 0.05) + 0.01
    wobble = (fbm(h, w, 2, 10, seed) - 0.5) * 0.18
    dist = 1 - np.abs(v - wobble * (1 - u)) / half
    heat = _smooth(dist, 0.08, 0.9) * (0.75 + 0.25 * (1 - u))
    alpha = _smooth(dist, -0.02, 0.05)
    rgb = heat_colour(heat * 1.1)
    sp = sparkles(h, w, 40, seed + 1, 1.8) * _smooth(0.3 - dist, 0.0, 0.2) * alpha
    rgb = rgb * (1 - sp[..., None]) + sp[..., None]
    return rgba(rgb, alpha)


def crescent(size=1024, seed=4):
    """Slash arc card: a fiery crescent with a dark outer edge and sparkles."""
    x, y = _grid(size, size)
    r = np.sqrt(x * x + y * y)
    ang = np.arctan2(x, -y)                                          # 0 at the top, + clockwise
    f = np.clip((ang + 1.9) / 3.8, 0, 1)                               # tail (0) -> head (1)
    inside = (ang > -1.9) & (ang < 1.9)
    width = 0.3 * np.clip(np.sin(math.pi * f), 0, 1) ** 0.7 * (0.35 + 0.65 * f)
    centre = 0.86 - width * 0.5
    dist = 1 - np.abs(r - centre) / np.maximum(width * 0.5, 1e-3)
    dist = np.where(inside, dist, -1)
    # the bright core hugs the outer edge, like a blade's leading edge
    lead = 1 - np.clip((0.86 - r) / np.maximum(width, 1e-3), 0, 1)
    heat = _smooth(dist, 0.05, 0.8) * (0.45 + 0.55 * lead) * (0.6 + 0.4 * f)
    alpha = _smooth(dist, -0.02, 0.06)
    rgb = heat_colour(heat * 1.2)
    sp = sparkles(size, size, 60, seed, 2.5) * _smooth(0.35 - dist, 0, 0.2) * alpha
    rgb = rgb * (1 - sp[..., None]) + sp[..., None]
    return rgba(rgb, alpha)


def starburst(size=1024, seed=6):
    """Impact (sheet item 3 star): dark core, bright ring, tapered spikes, curling ribbons."""
    x, y = _grid(size, size)
    r = np.sqrt(x * x + y * y) + 1e-6
    ang = np.arctan2(y, x)
    rng = np.random.default_rng(seed)
    heat = np.zeros_like(r)
    alpha = np.zeros_like(r)
    for i in range(8):                                                   # spikes
        a0 = i * math.pi / 4 + rng.uniform(-0.3, 0.3)
        length = rng.uniform(0.62, 0.99)
        base = rng.uniform(0.045, 0.07)
        d = np.angle(np.exp(1j * (ang - a0)))
        halfw = base * np.clip(1 - r / length, 0, 1) / np.maximum(r, 0.05)
        dist = 1 - np.abs(d) / np.maximum(halfw, 1e-4)
        dist = np.where(r < length, dist, -1)
        heat = np.maximum(heat, _smooth(dist, 0.1, 0.9) * np.clip(1 - r / length, 0, 1) ** 0.6)
        alpha = np.maximum(alpha, _smooth(dist, -0.02, 0.08))
    ring = np.exp(-((r - 0.17) / 0.06) ** 2)
    heat = np.maximum(heat, ring)
    alpha = np.maximum(alpha, _smooth(0.32 - r, 0.0, 0.05))
    core = _smooth(0.11 - r, 0.0, 0.03)                                    # the dark eye
    rgb = heat_colour(heat * 1.15)
    rgb = rgb * (1 - core[..., None]) + INK * core[..., None]
    for _ in range(4):                                                   # curling ribbons
        a0 = rng.uniform(-math.pi, math.pi)
        r0 = rng.uniform(0.35, 0.6)
        d = np.abs(r - (r0 + 0.12 * np.sin(2 * (ang - a0)))) / 0.018
        span = np.angle(np.exp(1j * (ang - a0)))
        rib = _smooth(1 - d, 0.0, 0.5) * _smooth(1.6 - np.abs(span), 0, 0.6)
        rgb = rgb * (1 - rib[..., None]) + CRIMSON * 1.4 * rib[..., None]
        alpha = np.maximum(alpha, rib)
    glow = np.exp(-(r / 0.42) ** 2) * 0.35
    halo = (alpha < 0.05) & (core < 0.5)                                   # soft orange glow between spikes
    rgb[halo] = ORANGE
    alpha = np.maximum(alpha, glow * 0.6)
    return rgba(rgb, alpha)


def dart(w=512, h=128, seed=8):
    """Sheet item 1: thin streak that ends in a bright flare. u along (1 = head)."""
    u = np.linspace(0, 1, w)[None, :] * np.ones((h, 1))
    v = np.linspace(-1, 1, h)[:, None] * np.ones((1, w))
    half = 0.08 + 0.25 * u ** 3
    dist = 1 - np.abs(v) / half
    heat = _smooth(dist, 0.1, 0.9) * (0.3 + 0.7 * u ** 1.5)
    alpha = _smooth(dist, -0.05, 0.1) * _smooth(u, 0.0, 0.25)
    flare = np.exp(-(((u - 0.93) / 0.05) ** 2 + (v / 0.5) ** 2))
    heat = np.maximum(heat, flare)
    alpha = np.maximum(alpha, flare)
    return rgba(heat_colour(heat * 1.1), alpha)


def portal(size=1024, seed=9):
    """Sheet item 4: dark starry disc with a fiery rim."""
    x, y = _grid(size, size)
    r = np.sqrt(x * x + y * y)
    disc = _smooth(0.86 - r, 0.0, 0.02)
    stars = sparkles(size, size, 160, seed, 1.6) * disc
    rgb = np.ones((size, size, 3)) * np.array([0.02, 0.03, 0.06]) * (0.6 + 0.6 * fbm(size, size, 6, 6, seed))[..., None]
    rgb = rgb * (1 - stars[..., None]) + stars[..., None] * 0.9
    rim = np.exp(-((r - 0.87) / 0.035) ** 2)
    rgb = rgb * (1 - rim[..., None]) + heat_colour(rim * 0.85)[..., :3] * rim[..., None]
    alpha = np.maximum(disc, rim)
    return rgba(rgb, alpha)


def swirl(size=1024, seed=10):
    """Sheet item 4 trail: broken spiral bands of fire with dark gaps."""
    x, y = _grid(size, size)
    r = np.sqrt(x * x + y * y) + 1e-6
    ang = np.arctan2(y, x)
    phase = ang / (2 * math.pi) * 3 + r * 4.5
    band = 0.5 + 0.5 * np.cos(phase * 2 * math.pi)
    n = fbm(size, size, 5, 5, seed)
    dist = _smooth(band, 0.55, 0.95) * _smooth(0.95 - r, 0.0, 0.1) * _smooth(r, 0.2, 0.4)
    dist *= _smooth(n, 0.3, 0.6)
    heat = dist * (0.5 + 0.5 * r)
    alpha = _smooth(dist, 0.02, 0.15)
    return rgba(heat_colour(heat * 1.25), alpha)


def ember(size=128):
    x, y = _grid(size, size)
    r2 = x * x + y * y
    heat = np.exp(-r2 / 0.05)
    alpha = np.clip(np.exp(-r2 / 0.08) * 1.2, 0, 1)
    return rgba(heat_colour(heat * 1.1 + 0.25), alpha)


def glow(size=256):
    x, y = _grid(size, size)
    r2 = x * x + y * y
    a = np.exp(-r2 / 0.18) * _smooth(1 - np.sqrt(r2), 0, 0.15)
    return rgba(np.ones((size, size, 3)) * np.array([1.0, 0.55, 0.15]), a)


def heat_flow(w=256, h=1024, seed=12):
    """Grey flow streaks for the ForceField aura shell (tinted by the part colour)."""
    n1 = fbm(h, w, 3, 14, seed, periodic_x=True)
    n2 = fbm(h, w, 10, 28, seed + 3, periodic_x=True)
    s = np.clip((n1 - 0.5) * 3.2, 0, 1) * (0.4 + 0.8 * n2)
    return rgba(np.repeat(s[..., None], 3, axis=2), np.ones((h, w)))


def fire_trail(w=256, h=256, seed=13):
    """Swing trail. U along the trail (0 = newest), V across the blade span.
    Symmetric across V so it reads the same whichever way Roblox maps it."""
    u = np.linspace(0, 1, w)[None, :] * np.ones((h, 1))
    v = np.linspace(-1, 1, h)[:, None] * np.ones((1, w))
    n = fbm(h, w, 16, 3, seed)
    dist = 1 - np.abs(v) / (0.98 - 0.25 * u)
    heat = _smooth(dist, 0.06, 0.75) * (1 - 0.65 * u) * (0.8 + 0.3 * n)
    alpha = _smooth(dist, -0.02, 0.06) * (1 - _smooth(u, 0.55, 1.0))
    return rgba(heat_colour(heat * 1.15), alpha)


def slash_strip(w=512, h=128, seed=14):
    """One segment of a beam-built crescent: layered across V, even along U."""
    v = np.linspace(-1, 1, h)[:, None] * np.ones((1, w))
    n = fbm(h, w, 4, 12, seed, periodic_x=True)
    dist = 1 - np.abs(v) * (0.95 + 0.1 * n)
    heat = _smooth(dist, 0.12, 1.0) ** 1.3
    alpha = _smooth(dist, -0.02, 0.07)
    return rgba(heat_colour(heat * 1.1), alpha)


def spark(size=256, seed=15):
    """Fiery streak for VelocityParallel sparks (vertical)."""
    x, y = _grid(size, size)
    dist = 1 - np.sqrt((x / 0.09) ** 2 + (y / 0.85) ** 2)
    heat = _smooth(dist, 0.0, 0.8)
    alpha = _smooth(dist, -0.15, 0.1)
    return rgba(heat_colour(heat * 1.2 + 0.1), alpha)


def twinkle(size=128):
    """White four-point sparkle (the reference's white specks)."""
    x, y = _grid(size, size)
    r = np.sqrt(x * x + y * y)
    a = np.exp(-(x / 0.06) ** 2 - (y / 0.7) ** 2) + np.exp(-(y / 0.06) ** 2 - (x / 0.7) ** 2) + np.exp(-(r / 0.12) ** 2)
    a = np.clip(a, 0, 1) * _smooth(1 - r, 0, 0.1)
    return rgba(np.ones((size, size, 3)), a)


def red_swirl(w=512, h=128, seed=16):
    """Red swirl stroke for the ribbon trails. U along the stroke (0 = head, 1 = fading tail),
    V across (symmetric): hot red-orange centre line, red body, dark crimson edges."""
    u = np.linspace(0, 1, w)[None, :] * np.ones((h, 1))
    v = np.linspace(-1, 1, h)[:, None] * np.ones((1, w))
    n = fbm(h, w, 3, 18, seed)
    half = 0.92 - 0.35 * u
    dist = 1 - np.abs(v) / half
    centre = _smooth(dist, 0.55, 1.0)
    body = _smooth(dist, 0.05, 0.5)
    rgb = (CRIMSON[None, None] * (1 - body[..., None]) + np.array([0.95, 0.07, 0.04]) * body[..., None])
    rgb = rgb * (1 - centre[..., None] * 0.8) + np.array([1.0, 0.42, 0.18]) * centre[..., None] * 0.8
    breaks = _smooth(n, 0.25, 0.45)                                  # dry-brush gaps towards the tail
    alpha = _smooth(dist, -0.02, 0.12) * (1 - _smooth(u, 0.45, 1.0)) * (breaks + (1 - breaks) * (1 - u))
    return rgba(rgb, alpha)


# ---------------------------------------------------------------- pure-energy layers (soft, additive)

def energy_ring(size=512):
    """Soft energy ring: white-hot core line fading through gold and orange into a red glow.
    No hard edge anywhere, so overlapping rings melt into each other."""
    x, y = _grid(size, size)
    r = np.sqrt(x * x + y * y)
    d = np.abs(r - 0.62)
    core = np.exp(-(d / 0.05) ** 2) * 0.7
    body = np.exp(-(d / 0.13) ** 2)
    halo = np.exp(-(d / 0.26) ** 2) * 0.55
    rgb = (np.array([1.0, 0.98, 0.85]) * core[..., None] + GOLD * (body - core).clip(0)[..., None]
           + ORANGE * (halo - body * 0.5).clip(0)[..., None])
    alpha = np.clip(core + body * 0.85 + halo, 0, 1) * _smooth(1 - r, 0.0, 0.12)
    return rgba(np.clip(rgb / np.maximum(alpha[..., None], 1e-3), 0, 1), alpha)


def hot_core(size=256):
    """White-hot centre melting into gold and orange (for intersections and cores)."""
    x, y = _grid(size, size)
    r = np.sqrt(x * x + y * y)
    heat = np.exp(-(r / 0.28) ** 2)
    alpha = np.clip(np.exp(-(r / 0.5) ** 2) * 1.1, 0, 1) * _smooth(1 - r, 0, 0.15)
    return rgba(heat_colour(0.55 + 0.45 * heat), alpha)


def void(size=256):
    """The star's dark eye: a black core that melts through deep red into the glow round it,
    with no hard edge (alpha-blended, not additive)."""
    x, y = _grid(size, size)
    r = np.sqrt(x * x + y * y)
    alpha = _smooth(0.7 - r, 0.0, 0.42)
    heat = _smooth(r, 0.2, 0.7)
    rgb = np.array([0.02, 0.0, 0.0]) * (1 - heat[..., None]) + np.array([0.45, 0.05, 0.01]) * heat[..., None]
    return rgba(rgb, alpha)


def flow_stroke(w=512, h=128):
    """Light trail for the energy flowing round the figure-8: bright core, soft edges, fading tail."""
    u = np.linspace(0, 1, w)[None, :] * np.ones((h, 1))
    v = np.linspace(-1, 1, h)[:, None] * np.ones((1, w))
    core = np.exp(-(v / 0.18) ** 2)
    glow = np.exp(-(v / 0.6) ** 2)
    fade = (1 - u) ** 1.4
    rgb = np.array([1.0, 0.97, 0.8]) * core[..., None] + ORANGE * (glow - core).clip(0)[..., None]
    alpha = np.clip(core + glow * 0.6, 0, 1) * fade
    return rgba(np.clip(rgb / np.maximum((core + (glow - core).clip(0))[..., None], 1e-3), 0, 1), alpha)


def energy_band(w=64, h=128):
    """The same along its whole length: a white-hot line in a soft orange glow. The body of the
    energy stream round the figure-8 (a trail one lap long, so it covers the whole loop)."""
    v = np.linspace(-1, 1, h)[:, None] * np.ones((1, w))
    core = np.exp(-(v / 0.16) ** 2)
    glow = np.exp(-(v / 0.55) ** 2)
    rgb = np.array([1.0, 0.95, 0.75]) * core[..., None] + ORANGE * (glow - core).clip(0)[..., None]
    alpha = np.clip(core + glow * 0.55, 0, 1)
    return rgba(np.clip(rgb / np.maximum((core + (glow - core).clip(0))[..., None], 1e-3), 0, 1), alpha)


def energy_flow(w=512, h=128, seed=17):
    """Streaks of energy that scroll up the blade (tiles left-right)."""
    u = np.linspace(0, 1, w, endpoint=False)[None, :] * np.ones((h, 1))
    v = np.linspace(-1, 1, h)[:, None] * np.ones((1, w))
    n = fbm(h, w, 3, 6, seed, periodic_x=True)
    streak = np.clip((fbm(h, w, 12, 3, seed + 4, periodic_x=True) - 0.45) * 3, 0, 1)
    band = np.exp(-(v / (0.45 + 0.25 * n)) ** 2)
    heat = streak * band
    return rgba(heat_colour(0.5 + 0.5 * heat), np.clip(heat * 1.3, 0, 1))


def energy_wisp(frame=256, grid=4, seed=18):
    """Soft glowing wisps (no outline) that curl up and dissolve: 4x4 flipbook."""
    out = np.zeros((frame * grid, frame * grid, 4), np.float32)
    x, y = _grid(frame, frame)
    w1 = fbm(frame, frame, 3, 3, seed) - 0.5
    w2 = fbm(frame, frame, 3, 3, seed + 2) - 0.5
    for k in range(grid * grid):
        t = k / (grid * grid - 1)
        sx = x * 0.9 + w1 * (0.4 + 0.6 * t) + 0.25 * np.sin(y * 3 + t * 6)
        sy = y * 0.9 + 0.3 - 0.6 * t + w2 * (0.3 + 0.5 * t)
        d = np.sqrt((sx / (0.22 + 0.25 * t)) ** 2 + ((sy + 0.1) / (0.5 + 0.3 * t)) ** 2)
        heat = np.exp(-d ** 2 * 1.4) * (1 - t) ** 1.2
        alpha = np.clip(np.exp(-d ** 2) * 1.2, 0, 1) * (1 - t) ** 1.1
        alpha = alpha * _smooth(1 - np.maximum(np.abs(x), np.abs(y)), 0.0, 0.2)   # nothing reaches the cell edge
        cell = rgba(heat_colour(0.45 + 0.55 * heat), alpha)
        out[(k // grid) * frame:(k // grid + 1) * frame, (k % grid) * frame:(k % grid + 1) * frame] = cell
    return out


def energy_spike(w=512, h=128):
    """A star spike made of light: tapers from the base (left) to a needle tip (right), with a
    white-hot core, gold and orange body, a glowing red edge and a soft outer glow."""
    u = np.linspace(0, 1, w)[None, :] * np.ones((h, 1))
    v = np.abs(np.linspace(-1, 1, h))[:, None] * np.ones((1, w))
    hw = 0.62 * (1 - u) ** 0.85 * _smooth(u, 0.0, 0.06) + 0.012
    t = v / hw                                                      # 0 centre, 1 edge
    core = np.exp(-(t / 0.3) ** 2)
    inside = _smooth(1 - t, -0.05, 0.12)
    edge = np.exp(-((t - 0.92) / 0.14) ** 2)
    outer = np.exp(-((v - hw).clip(0) / 0.16) ** 2) * (1 - inside)
    rgb = heat_colour(np.clip(0.55 + 0.45 * core, 0, 1))
    rgb = rgb * (1 - edge[..., None] * 0.6) + RED * edge[..., None] * 0.6
    rgb = rgb * inside[..., None] + ORANGE * (1 - inside)[..., None]
    alpha = np.clip(inside * (0.75 + 0.25 * core) + outer * 0.45, 0, 1) * _smooth(1 - u, 0.0, 0.03)
    return rgba(np.clip(rgb, 0, 1), alpha)


VFX = {
    "EnergyRing": energy_ring,
    "EnergySpike": energy_spike,
    "HotCore": hot_core,
    "Void": void,
    "FlowStroke": flow_stroke,
    "EnergyBand": energy_band,
    "EnergyFlow": energy_flow,
    "EnergyWisp": energy_wisp,
    "RedSwirl": red_swirl,
    "Twinkle": twinkle,
    "Trail": fire_trail,
    "SlashStrip": slash_strip,
    "Spark": spark,
    "FireLick": fire_lick_flipbook,
    "Streak": streak,
    "Crescent": crescent,
    "Starburst": starburst,
    "Dart": dart,
    "Portal": portal,
    "Swirl": swirl,
    "Ember": ember,
    "Glow": glow,
}
