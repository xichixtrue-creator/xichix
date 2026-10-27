"""
Textures for the Seraph Blade: luminous white crystal, polished gold, engraved gold filigree,
clear diamond gems, and the white / gold divine aura and attack layers (glows, light rays,
halo, energy ribbons, sparkles, motes, slash, trail, light pillar, holy circle). numpy only,
so this also runs inside Blender's bundled Python. Every function returns float32 RGBA in 0..1
(rows top to bottom).
"""

import math

import numpy as np

WHITE = np.array([0.97, 0.97, 0.99])
PEARL = np.array([0.86, 0.87, 0.92])
ICE = np.array([0.78, 0.84, 0.95])
GOLD = np.array([1.0, 0.76, 0.3])
GOLD_HI = np.array([1.0, 0.93, 0.66])
GOLD_LO = np.array([0.5, 0.31, 0.07])
WARM = np.array([1.0, 0.95, 0.82])


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


def _dist_to_polyline(x, y, pts):
    d = np.full(x.shape, 1e9, np.float32)
    for (ax, ay), (bx, by) in zip(pts[:-1], pts[1:]):
        vx, vy = bx - ax, by - ay
        ln = vx * vx + vy * vy
        t = np.clip(((x - ax) * vx + (y - ay) * vy) / max(ln, 1e-9), 0, 1)
        d = np.minimum(d, np.sqrt((x - ax - t * vx) ** 2 + (y - ay - t * vy) ** 2))
    return d



# ---------------------------------------------------------------- weapon surfaces

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




def white_crystal(size=1024, seed=1, alpha=0.9):
    """Luminous white crystal: pearl-white with faint cool facet lines and soft inner light."""
    h = w = size
    edge = _voronoi_edges(h, w, 26, seed)
    depth = fbm(h, w, 4, 4, seed + 2, periodic_x=True)
    heat = 0.55 + 0.45 * depth
    rgb = _ramp(heat, [(0.0, PEARL), (0.6, WHITE * 0.96), (1.0, WHITE)])
    line = np.exp(-(edge / 1.3) ** 2)[..., None] * 0.35
    rgb = rgb * (1 - line) + ICE * line
    return rgba(rgb, np.full((h, w), alpha, np.float32))


def gem(size=512, seed=3):
    """Clear diamond: near-white with faint facet glints."""
    h = w = size
    edge = _voronoi_edges(h, w, 18, seed)
    line = np.exp(-(edge / 1.2) ** 2)[..., None]
    rgb = WHITE * (1 - line * 0.25) + ICE * line * 0.25
    return rgba(rgb, np.full((h, w), 0.8, np.float32))


def crystal_mr(size=64, rough=0.07):
    return rgba(np.stack([np.zeros((size, size)), np.full((size, size), rough), np.zeros((size, size))], axis=2),
                np.ones((size, size)))


def _leaf(cx, cy, length, width, angle, n=24):
    pts = []
    for k in range(n):
        a = 2 * math.pi * k / (n - 1)
        x, y = width * math.sin(a), length * math.cos(a) * (0.6 + 0.4 * math.cos(a))
        pts.append((cx + x * math.cos(angle) - y * math.sin(angle), cy + x * math.sin(angle) + y * math.cos(angle)))
    return pts


def _spiral(cx, cy, r0, turns, start, sign, n=40):
    pts = []
    for k in range(n):
        t = k / (n - 1)
        phi = start - sign * t * turns * 2 * math.pi
        r = r0 * (1 - 0.75 * t)
        pts.append((cx + r * math.cos(phi), cy + r * math.sin(phi)))
    return pts


def _filigree_curves():
    """One tile of mirrored gold filigree, in u, v from -1 to 1 (tiles top to bottom):
    a central stem, big and small scroll pairs, leaves and a teardrop, framed by border lines."""
    curves = [[(0.0, -1.0), (0.0, 1.0)], [(0.9, -1.0), (0.9, 1.0)], [(-0.9, -1.0), (-0.9, 1.0)]]
    dots = []
    for s in (-1, 1):
        curves.append([(s * x, y) for x, y in _spiral(0.47, -0.1, 0.42, 0.95, 2.5 if s > 0 else 2.5, 1)])
        curves.append([(s * x, y) for x, y in _spiral(0.25, 0.58, 0.2, 0.8, -0.6, -1)])
        curves.append([(s * x, y) for x, y in _leaf(0.17, -0.55, 0.16, 0.06, 0.9)])
        curves.append([(s * x, y) for x, y in _leaf(0.62, 0.62, 0.13, 0.05, -0.5)])
        curves.append([(0.0, 0.3), (s * 0.12, 0.36), (s * 0.2, 0.45)])
        curves.append([(0.0, -0.3), (s * 0.1, -0.36), (s * 0.15, -0.46)])
        dots += [(s * 0.68, -0.78), (s * 0.7, 0.2), (s * 0.08, 0.86)]
    curves.append(_leaf(0.0, -0.78, 0.15, 0.1, 0.0))
    return curves, dots


def filigree(size=512):
    """Engraved gold filigree: bright raised scrollwork on a darker recessed gold ground
    (u across the panel, tiles along it)."""
    x, y = _grid(size, size)
    d = np.full(x.shape, 1e9, np.float32)
    curves, dots = _filigree_curves()
    for c in curves:
        d = np.minimum(d, _dist_to_polyline(x, y, c))
    for cx, cy in dots:
        d = np.minimum(d, np.maximum(np.sqrt((x - cx) ** 2 + (y - cy) ** 2) - 0.03, 0))
    line = _smooth(0.036 - d, 0.0, 0.016)
    bevel = np.clip(1 - d / 0.036, 0, 1)
    ground = (GOLD * 0.74) * (0.9 + 0.2 * fbm(size, size, 8, 8, 4, periodic_x=True))[..., None]
    rgb = ground * (1 - line[..., None]) + GOLD[None, None, :] * (0.8 + 0.25 * bevel)[..., None] * line[..., None]
    return rgba(np.clip(rgb, 0, 1), np.ones((size, size), np.float32))


# ---------------------------------------------------------------- aura / VFX

def glow(size=256, colour=None):
    x, y = _grid(size, size)
    r = np.sqrt(x * x + y * y)
    a = np.exp(-(r / 0.42) ** 2) * _smooth(1 - r, 0, 0.2)
    c = WHITE if colour is None else colour
    rgb = c * (1 - 0.15 * (1 - np.exp(-(r / 0.25) ** 2)))[..., None]
    return rgba(rgb, a)


def glow_gold(size=256):
    return glow(size, GOLD_HI)


def rays(size=512, seed=7):
    """Soft divine light rays fanning out from the centre."""
    x, y = _grid(size, size)
    r = np.sqrt(x * x + y * y)
    ang = np.arctan2(y, x)
    rng = np.random.default_rng(seed)
    streak = np.zeros_like(r)
    for _ in range(26):
        a0 = rng.uniform(-math.pi, math.pi)
        wdt = rng.uniform(0.02, 0.07)
        da = np.angle(np.exp(1j * (ang - a0)))
        streak = np.maximum(streak, np.exp(-(da / wdt) ** 2) * rng.uniform(0.4, 1.0))
    fade = np.exp(-(r / 0.55) ** 2) * _smooth(r, 0.02, 0.15)
    a = np.clip(streak * fade + np.exp(-(r / 0.18) ** 2) * 0.5, 0, 1) * _smooth(1 - r, 0, 0.1)
    rgb = WARM * (1 - streak[..., None] * 0.3) + GOLD_HI * streak[..., None] * 0.3
    return rgba(rgb, a)


def halo(size=512):
    """A soft luminous ring with a white core and a warm gold rim."""
    x, y = _grid(size, size)
    r = np.sqrt(x * x + y * y)
    core = np.exp(-((r - 0.7) / 0.03) ** 2)
    body = np.exp(-((r - 0.7) / 0.12) ** 2) * 0.5
    rgb = GOLD_HI * (1 - core[..., None]) + WHITE * core[..., None]
    return rgba(rgb, np.clip(core + body, 0, 1) * _smooth(1 - r, 0, 0.1))


def ribbon(w=1024, h=96, seed=11):
    """A thin strand of divine light: white-hot core, soft gold edges, fading at both ends."""
    u = np.linspace(0, 1, w)[None, :] * np.ones((h, 1))
    v = np.linspace(-1, 1, h)[:, None] * np.ones((1, w))
    wob = (fbm(h, w, 1, 4, seed, octaves=2, periodic_x=True) - 0.5) * 0.4
    core = np.exp(-((v - wob) / 0.12) ** 2)
    body = np.exp(-((v - wob * 0.7) / 0.45) ** 2) * 0.5
    breakup = _smooth(fbm(1, w, 1, 5, seed + 3, octaves=2, periodic_x=True), 0.2, 0.5)
    ends = _smooth(u, 0.0, 0.2) * _smooth(1 - u, 0.0, 0.25)
    a = np.clip(core * (0.5 + 0.5 * breakup) + body * (0.4 + 0.6 * breakup), 0, 1) * ends
    rgb = GOLD_HI * (1 - core[..., None]) + WHITE * core[..., None]
    return rgba(rgb, np.clip(a * 1.2, 0, 1))


def ribbon_gold(w=1024, h=96, seed=13):
    """The same strand in warm gold (the secondary glow)."""
    out = ribbon(w, h, seed)
    out[..., :3] = out[..., :3] * 0.15 + GOLD[None, None, :] * 0.85 * out[..., :3].max(axis=2, keepdims=True)
    return out


def sparkle(size=128):
    """A four-point star flash: white core, thin gold spikes, soft halo (additive)."""
    x, y = _grid(size, size)
    ax, ay = np.abs(x), np.abs(y)
    star = np.exp(-ax / 0.025) * np.exp(-ay / 0.45) + np.exp(-ay / 0.025) * np.exp(-ax / 0.45)
    diag = (np.exp(-np.abs(x - y) / 0.03) + np.exp(-np.abs(x + y) / 0.03)) * np.exp(-np.sqrt(x * x + y * y) / 0.18) * 0.5
    core = np.exp(-(np.sqrt(x * x + y * y) / 0.08) ** 2)
    halo_ = np.exp(-(np.sqrt(x * x + y * y) / 0.3) ** 2) * 0.3
    a = np.clip(star + diag + core + halo_, 0, 1) * _smooth(1 - np.maximum(ax, ay), 0, 0.1)
    m = np.clip(core + star * 0.6, 0, 1)[..., None]
    rgb = GOLD_HI * (1 - m) + WHITE * m
    return rgba(rgb, a)


def mote(size=64):
    x, y = _grid(size, size)
    r = np.sqrt(x * x + y * y)
    core = np.exp(-(r / 0.2) ** 2)
    halo_ = np.exp(-(r / 0.55) ** 2) * 0.5
    rgb = GOLD_HI * (1 - core[..., None]) + WHITE * core[..., None]
    return rgba(rgb, np.clip(core + halo_, 0, 1) * _smooth(1 - r, 0, 0.2))


def slash_band(w=128, h=256, seed=29):
    """Cross-section of the light slash: a white-hot edge (top), a warm gold body fading out."""
    v = np.linspace(0, 1, h)[:, None] * np.ones((1, w))
    n = fbm(h, w, 8, 2, seed, periodic_x=True)
    edge = np.exp(-((v - 0.07) / 0.045) ** 2)
    body = _smooth(v, 0.03, 0.18) * (1 - _smooth(v, 0.4, 0.95 - 0.2 * n))
    heat = np.clip(edge + body * (0.8 - 0.5 * v), 0, 1)
    rgb = _ramp(heat, [(0.0, GOLD_LO), (0.45, GOLD), (0.8, GOLD_HI), (1.0, WHITE)])
    return rgba(rgb, np.clip(edge + body * (1.0 - 0.6 * v) * (0.6 + 0.4 * n), 0, 1))


def trail(w=256, h=256, seed=21):
    u = np.linspace(0, 1, w)[None, :] * np.ones((h, 1))
    v = np.linspace(0, 1, h)[:, None] * np.ones((1, w))
    n = fbm(h, w, 6, 4, seed)
    edge = np.exp(-((v - 0.08) / 0.05) ** 2)
    body = _smooth(v, 0.05, 0.3) * _smooth(1 - v, 0.0, 0.5) * _smooth(n, 0.25, 0.6)
    heat = np.clip(edge + body * 0.6, 0, 1) * (1 - u) ** 1.2
    rgb = _ramp(heat, [(0.0, GOLD_LO), (0.5, GOLD), (0.85, GOLD_HI), (1.0, WHITE)])
    return rgba(rgb, np.clip(heat * 1.4, 0, 1))


def pillar(w=128, h=512):
    """A column of heavenly light (u across, v along), soft at both ends."""
    u = np.linspace(-1, 1, w)[None, :] * np.ones((h, 1))
    v = np.linspace(0, 1, h)[:, None] * np.ones((1, w))
    core = np.exp(-(u / 0.18) ** 2)
    body = np.exp(-(u / 0.55) ** 2) * 0.6
    ends = _smooth(v, 0.0, 0.15) * _smooth(1 - v, 0.0, 0.3)
    rgb = GOLD_HI * (1 - core[..., None]) + WHITE * core[..., None]
    return rgba(rgb, np.clip(core + body, 0, 1) * ends)


def holy_circle(size=512):
    """A radiant circle of light on the ground: rings, rays and an eight-point star."""
    x, y = _grid(size, size)
    r = np.sqrt(x * x + y * y)
    ang = np.arctan2(y, x)
    rings_ = (np.exp(-((r - 0.9) / 0.012) ** 2) + np.exp(-((r - 0.84) / 0.008) ** 2) * 0.7
              + np.exp(-((r - 0.5) / 0.01) ** 2) * 0.6)
    ticks = np.exp(-((r - 0.87) / 0.03) ** 2) * (np.cos(ang * 36) > 0.9)
    star_r = 0.45 * (0.55 + 0.45 * np.abs(np.cos(ang * 4)) ** 8)
    star = np.exp(-((r - star_r) / 0.012) ** 2) * (r < 0.48)
    rays_ = np.exp(-(np.angle(np.exp(1j * ang * 8)) / 0.15) ** 2) * _smooth(r, 0.1, 0.3) * (1 - _smooth(r, 0.7, 0.8)) * 0.35
    fill = np.exp(-(r / 0.55) ** 2) * 0.3
    heat = np.clip(rings_ + ticks * 0.7 + star + rays_ + fill, 0, 1) * _smooth(1 - r, 0, 0.06)
    rgb = _ramp(heat, [(0.0, GOLD_LO), (0.4, GOLD), (0.8, GOLD_HI), (1.0, WHITE)])
    return rgba(rgb, heat)


AURA = {
    "GlowWhite": glow,
    "GlowGold": glow_gold,
    "Rays": rays,
    "Halo": halo,
    "Ribbon": ribbon,
    "RibbonGold": ribbon_gold,
    "Sparkle": sparkle,
    "Mote": mote,
    "SlashBand": slash_band,
    "Trail": trail,
    "Pillar": pillar,
    "HolyCircle": holy_circle,
}
