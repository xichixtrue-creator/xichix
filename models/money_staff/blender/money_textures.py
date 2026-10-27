"""
Textures for the Fortune Staff: faceted emerald, polished gold, dark green-black shaft metal,
and the green / gold aura and attack layers (energy wisps, sparkles, motes, money symbols,
coins, slash, trail, shockwave ring, ground circle). numpy only, so this also runs inside
Blender's bundled Python. Every function returns float32 RGBA in 0..1 (rows top to bottom).
"""

import math

import numpy as np

EMERALD_DEEP = np.array([0.0, 0.14, 0.05])
EMERALD = np.array([0.03, 0.55, 0.2])
GREEN = np.array([0.25, 0.95, 0.35])
MINT = np.array([0.7, 1.0, 0.72])
GOLD = np.array([1.0, 0.74, 0.27])
GOLD_HI = np.array([1.0, 0.93, 0.62])
GOLD_LO = np.array([0.55, 0.33, 0.08])
DARK = np.array([0.02, 0.035, 0.028])


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


def rgba(rgb, alpha):
    return np.concatenate([np.clip(rgb, 0, 1), np.clip(alpha, 0, 1)[..., None]], axis=2).astype(np.float32)


def _ramp(t, stops):
    t = np.clip(t, 0, 1)
    out = np.zeros(t.shape + (3,), np.float32)
    for (p0, c0), (p1, c1) in zip(stops[:-1], stops[1:]):
        m = (t >= p0) & (t <= p1)
        f = ((t - p0) / (p1 - p0))[m][:, None]
        out[m] = np.array(c0) * (1 - f) + np.array(c1) * f
    return out


def _voronoi_edges(h, w, count, seed):
    rng = np.random.default_rng(seed)
    pts = rng.random((count, 2)) * np.array([w, h])
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    best, second = np.full((h, w), 1e9, np.float32), np.full((h, w), 1e9, np.float32)
    for px, py in pts:
        for ox in (-w, 0, w):
            d = np.sqrt((x - px - ox) ** 2 + (y - py) ** 2)
            second = np.where(d < best, best, np.minimum(second, d))
            best = np.minimum(best, d)
    return (second - best) * 0.5


def dollar_centerline(n=40):
    """The $ symbol's S stroke and bar as polylines in units where the S is about 2 tall."""
    rx, rz = 0.53, 0.4
    pts = []
    for k in range(n):
        th = math.radians(25 + (270 - 25) * k / (n - 1))
        pts.append((rx * math.cos(th), 0.4 + rz * math.sin(th)))
    for k in range(1, n):
        th = math.radians(90 - (90 + 155) * k / (n - 1))
        pts.append((rx * math.cos(th), -0.4 + rz * math.sin(th)))
    return pts, [(0.0, 1.16), (0.0, -1.3)]


def _dist_to_polyline(x, y, pts):
    d = np.full(x.shape, 1e9, np.float32)
    for (ax, ay), (bx, by) in zip(pts[:-1], pts[1:]):
        vx, vy = bx - ax, by - ay
        ln = vx * vx + vy * vy
        t = np.clip(((x - ax) * vx + (y - ay) * vy) / max(ln, 1e-9), 0, 1)
        d = np.minimum(d, np.sqrt((x - ax - t * vx) ** 2 + (y - ay - t * vy) ** 2))
    return d


def dollar_distance(size, scale=0.42):
    """Distance (in sprite units) to the $ strokes, centred in a size x size image."""
    x, y = _grid(size, size)
    s_pts, bar = dollar_centerline()
    s_pts = [(px * scale, -py * scale) for px, py in s_pts]
    bar = [(px * scale, -py * scale) for px, py in bar]
    d_s = _dist_to_polyline(x, y, s_pts)
    d_bar = _dist_to_polyline(x, y, bar)
    return d_s, d_bar


# ---------------------------------------------------------------- weapon surfaces

def emerald(size=1024, seed=1, alpha=0.85):
    """Emerald: deep green depths, brighter facets and faint mint fracture lines."""
    h = w = size
    edge = _voronoi_edges(h, w, 30, seed)
    depth = fbm(h, w, 4, 4, seed + 2, periodic_x=True)
    cell = fbm(h, w, 9, 9, seed + 3, periodic_x=True)
    heat = 0.25 + 0.45 * depth + 0.25 * cell
    rgb = _ramp(heat, [(0.0, EMERALD_DEEP), (0.55, EMERALD), (0.9, GREEN), (1.0, MINT)])
    line = np.exp(-(edge / 1.4) ** 2)[..., None] * 0.4
    rgb = rgb * (1 - line) + MINT * line
    return rgba(rgb, np.full((h, w), alpha, np.float32) + 0.1 * line[..., 0])


def gold(size=1024, seed=5):
    """Polished gold with a faint brushed grain."""
    h = w = size
    grain = fbm(h, w, 96, 4, seed, octaves=3, periodic_x=True)
    broad = fbm(h, w, 5, 5, seed + 1, periodic_x=True)
    v = 0.86 + 0.1 * grain + 0.06 * broad
    rgb = GOLD[None, None, :] * v[..., None]
    return rgba(rgb, np.ones((h, w), np.float32))


def gold_mr(size=256, seed=5):
    h = w = size
    r = 0.1 + 0.08 * fbm(h, w, 12, 12, seed + 9, periodic_x=True)
    return rgba(np.stack([np.zeros((h, w)), r, np.ones((h, w))], axis=2), np.ones((h, w)))


def dark(size=1024, seed=7):
    """Dark green-black shaft metal with fine lengthwise streaks."""
    h = w = size
    streak = fbm(h, w, 3, 64, seed, octaves=3, periodic_x=True)
    broad = fbm(h, w, 4, 4, seed + 1, periodic_x=True)
    v = 0.8 + 0.25 * streak + 0.15 * broad
    rgb = DARK[None, None, :] * v[..., None] * 1.3
    return rgba(rgb, np.ones((h, w), np.float32))


def dark_mr(size=256, seed=7):
    h = w = size
    r = 0.26 + 0.1 * fbm(h, w, 3, 30, seed + 9, periodic_x=True)
    return rgba(np.stack([np.zeros((h, w)), r, np.full((h, w), 0.65)], axis=2), np.ones((h, w)))


def emerald_mr(size=64):
    return rgba(np.stack([np.zeros((size, size)), np.full((size, size), 0.06), np.zeros((size, size))], axis=2),
                np.ones((size, size)))


# ---------------------------------------------------------------- aura / VFX

def wisp(w=1024, h=96, seed=11):
    """A thin strand of emerald magic with a few gold flecks, fading at both ends (additive)."""
    u = np.linspace(0, 1, w)[None, :] * np.ones((h, 1))
    v = np.linspace(-1, 1, h)[:, None] * np.ones((1, w))
    wob = (fbm(h, w, 1, 4, seed, octaves=2, periodic_x=True) - 0.5) * 0.5
    core = np.exp(-((v - wob) / 0.12) ** 2)
    body = np.exp(-((v - wob * 0.7) / 0.5) ** 2) * 0.45
    breakup = _smooth(fbm(1, w, 1, 6, seed + 3, octaves=2, periodic_x=True), 0.2, 0.5)
    ends = _smooth(u, 0.0, 0.2) * _smooth(1 - u, 0.0, 0.25)
    heat = np.clip(core * (0.4 + 0.6 * breakup) + body * (0.5 + 0.5 * breakup), 0, 1) * ends
    rgb = _ramp(heat, [(0.0, EMERALD_DEEP), (0.45, EMERALD), (0.8, GREEN), (1.0, MINT)])
    rng = np.random.default_rng(seed + 5)
    for _ in range(18):                                   # gold flecks riding the strand
        cx, cy = rng.uniform(0.15, 0.85) * w, (0.5 + rng.uniform(-0.12, 0.12)) * h
        yy, xx = np.mgrid[0:h, 0:w]
        f = np.exp(-(((xx - cx) / 3.0) ** 2 + ((yy - cy) / 3.0) ** 2))
        rgb = rgb * (1 - f[..., None]) + GOLD_HI * f[..., None]
        heat = np.maximum(heat, f * ends)
    return rgba(rgb, np.clip(heat * 1.3, 0, 1))


def glow(size=256):
    x, y = _grid(size, size)
    r = np.sqrt(x * x + y * y)
    a = np.exp(-(r / 0.45) ** 2) * _smooth(1 - r, 0, 0.2)
    rgb = _ramp(np.exp(-(r / 0.3) ** 2), [(0.0, EMERALD), (0.8, GREEN), (1.0, MINT)])
    return rgba(rgb, a)


def sparkle(size=128):
    """A four-point star twinkle: gold-white core, green halo (additive)."""
    x, y = _grid(size, size)
    ax, ay = np.abs(x), np.abs(y)
    star = np.exp(-ax / 0.03) * np.exp(-ay / 0.42) + np.exp(-ay / 0.03) * np.exp(-ax / 0.42)
    core = np.exp(-(np.sqrt(x * x + y * y) / 0.1) ** 2)
    halo = np.exp(-(np.sqrt(x * x + y * y) / 0.35) ** 2) * 0.35
    a = np.clip(star + core + halo, 0, 1) * _smooth(1 - np.maximum(ax, ay), 0, 0.1)
    rgb = GREEN * (1 - np.clip(star + core, 0, 1))[..., None] + GOLD_HI * np.clip(star + core, 0, 1)[..., None]
    return rgba(rgb, a)


def mote(size=64):
    x, y = _grid(size, size)
    r = np.sqrt(x * x + y * y)
    core = np.exp(-(r / 0.2) ** 2)
    halo = np.exp(-(r / 0.55) ** 2) * 0.55
    rgb = GREEN * (1 - core[..., None]) + GOLD_HI * core[..., None]
    return rgba(rgb, np.clip(core + halo, 0, 1) * _smooth(1 - r, 0, 0.2))


def dollar(size=256):
    """A small glowing money symbol: gold-white strokes with an emerald glow (additive)."""
    d_s, d_bar = dollar_distance(size)
    d = np.minimum(d_s, d_bar)
    stroke = _smooth(0.075 - d, 0.0, 0.025)
    halo = np.exp(-(d / 0.12) ** 2) * 0.55
    rgb = GREEN * (1 - stroke[..., None]) + GOLD_HI * stroke[..., None]
    x, y = _grid(size, size)
    return rgba(rgb, np.clip(stroke + halo, 0, 1) * _smooth(1 - np.maximum(np.abs(x), np.abs(y)), 0, 0.1))


def coin(size=128):
    """A spinning gold coin seen face-on: rim, face and an embossed money symbol (alpha-blended)."""
    x, y = _grid(size, size)
    r = np.sqrt(x * x + y * y)
    disc = _smooth(0.92 - r, 0.0, 0.04)
    rim = np.exp(-((r - 0.82) / 0.06) ** 2)
    d_s, d_bar = dollar_distance(size, scale=0.27)
    emb = _smooth(0.06 - np.minimum(d_s, d_bar), 0.0, 0.02)
    light = 0.75 + 0.25 * (-x - y) / 1.4
    col = GOLD[None, None, :] * light[..., None]
    col = col * (1 - rim[..., None] * 0.4) + GOLD_HI * rim[..., None] * 0.4
    col = col * (1 - emb[..., None]) + GOLD_LO * emb[..., None] * 1.2
    return rgba(np.clip(col, 0, 1), disc)


def slash_band(w=128, h=256, seed=29):
    """Cross-section of the green slash, the same all along: a bright gold-white edge (top),
    an emerald body fading out (bottom)."""
    v = np.linspace(0, 1, h)[:, None] * np.ones((1, w))
    n = fbm(h, w, 8, 2, seed, periodic_x=True)
    edge = np.exp(-((v - 0.07) / 0.04) ** 2)
    body = _smooth(v, 0.03, 0.18) * (1 - _smooth(v, 0.4, 0.95 - 0.2 * n))
    heat = np.clip(edge + body * (0.8 - 0.5 * v), 0, 1)
    rgb = _ramp(heat, [(0.0, EMERALD_DEEP), (0.4, EMERALD), (0.75, GREEN), (0.92, GOLD_HI), (1.0, (1, 1, 0.9))])
    return rgba(rgb, np.clip(edge + body * (1.0 - 0.6 * v) * (0.6 + 0.4 * n), 0, 1))


def trail(w=256, h=256, seed=21):
    u = np.linspace(0, 1, w)[None, :] * np.ones((h, 1))
    v = np.linspace(0, 1, h)[:, None] * np.ones((1, w))
    n = fbm(h, w, 6, 4, seed)
    edge = np.exp(-((v - 0.08) / 0.05) ** 2)
    body = _smooth(v, 0.05, 0.3) * _smooth(1 - v, 0.0, 0.5) * _smooth(n, 0.25, 0.6)
    heat = np.clip(edge + body * 0.6, 0, 1) * (1 - u) ** 1.2
    rgb = _ramp(heat, [(0.0, EMERALD_DEEP), (0.5, EMERALD), (0.85, GREEN), (1.0, GOLD_HI)])
    return rgba(rgb, np.clip(heat * 1.4, 0, 1))


def shock_ring(size=512):
    """An expanding ring of emerald light with a gold inner edge (additive)."""
    x, y = _grid(size, size)
    r = np.sqrt(x * x + y * y)
    d = r - 0.78
    edge = np.exp(-(d / 0.025) ** 2)
    body = np.exp(-(np.minimum(d, 0) / 0.18) ** 2) * (r < 0.8) * 0.6
    heat = np.clip(edge + body, 0, 1) * _smooth(1 - r, 0, 0.1)
    rgb = _ramp(heat, [(0.0, EMERALD_DEEP), (0.5, EMERALD), (0.85, GREEN), (1.0, GOLD_HI)])
    return rgba(rgb, heat)


def ground_circle(size=512):
    """A glowing emerald magic circle with a money symbol at its heart (additive)."""
    x, y = _grid(size, size)
    r = np.sqrt(x * x + y * y)
    ang = np.arctan2(y, x)
    rings = (np.exp(-((r - 0.9) / 0.012) ** 2) + np.exp(-((r - 0.82) / 0.008) ** 2) * 0.8
             + np.exp(-((r - 0.55) / 0.01) ** 2) * 0.7)
    ticks = np.exp(-((r - 0.86) / 0.03) ** 2) * (np.cos(ang * 24) > 0.85)
    stars = np.zeros_like(r)
    for k in range(8):                                    # little diamonds round the circle
        a = 2 * math.pi * k / 8
        dx, dy = x - 0.7 * math.cos(a), y - 0.7 * math.sin(a)
        stars = np.maximum(stars, _smooth(0.05 - (np.abs(dx) + np.abs(dy) * 0.6), 0, 0.01))
    d_s, d_bar = dollar_distance(size, scale=0.2)
    sym = _smooth(0.035 - np.minimum(d_s, d_bar), 0.0, 0.012)
    fill = np.exp(-(r / 0.6) ** 2) * 0.25
    heat = np.clip(rings + ticks * 0.7 + stars + sym + fill, 0, 1) * _smooth(1 - r, 0, 0.06)
    rgb = _ramp(heat, [(0.0, EMERALD_DEEP), (0.4, EMERALD), (0.8, GREEN), (1.0, GOLD_HI)])
    return rgba(rgb, heat)


AURA = {
    "Wisp": wisp,
    "Glow": glow,
    "Sparkle": sparkle,
    "Mote": mote,
    "Dollar": dollar,
    "Coin": coin,
    "SlashBand": slash_band,
    "Trail": trail,
    "ShockRing": shock_ring,
    "GroundCircle": ground_circle,
}
