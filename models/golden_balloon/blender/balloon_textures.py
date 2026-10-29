"""
Textures for the Golden King Balloon: the rich metallic gold of the balloon (with its painted
tones and glossy highlights), the crown's polished and recessed gold, the yellow gems, the
white / ivory feathers with gold bases, and the golden aura layers (glows, light rays, energy
trails, sparkles, tiny stars, motes, floating feathers). numpy only, so this also runs inside
Blender's bundled Python. Every function returns float32 RGBA in 0..1 (rows top to bottom).
"""

import math

import numpy as np

# the reference sheet's palette (sRGB): gold 243,180,19 / light gold 253,228,130 / white / dark 112,77,25
GOLD = np.array([0.98, 0.74, 0.1])
GOLD_DEEP = np.array([0.8, 0.52, 0.04])
GOLD_SHADOW = np.array([0.56, 0.36, 0.06])
GOLD_LIGHT = np.array([0.99, 0.89, 0.51])
GOLD_DARK = np.array([0.44, 0.3, 0.1])
WHITE = np.array([1.0, 0.99, 0.96])
IVORY = np.array([1.0, 0.96, 0.86])
CREAM = np.array([1.0, 0.9, 0.66])
GEM = np.array([1.0, 0.82, 0.12])


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


# ---------------------------------------------------------------- the balloon

# where the painted highlights sit on the balloon's UV map (u round from the front-left, see
# build_balloon.py: u = 0.5 faces the front, u < 0.5 is its right as you look at it;
# v = 0 at the top, 1 at the neck)
SHINE_U, SHINE_V = 0.41, 0.3


def balloon(size=1024, seed=3):
    """Rich metallic gold: lighter towards the top, deeper towards the neck, soft latex-like
    tone bands, a strong glossy highlight on the upper front (towards the right, like the
    reference) with a smaller sharp glint, and a warm bounce light low on the opposite side."""
    h = w = size
    u = (np.arange(w, dtype=np.float32) + 0.5)[None, :] / w * np.ones((h, 1), np.float32)
    v = (np.arange(h, dtype=np.float32) + 0.5)[:, None] / h * np.ones((1, w), np.float32)
    polar = np.clip(v, 0, 1) * math.pi * 0.92                     # roughly the angle down from the top
    ring = np.sin(polar) + 0.05                                    # u distances shrink towards the poles
    broad = fbm(h, w, 3, 6, seed, octaves=3, periodic_x=True)
    tone = 0.72 - 0.42 * v + 0.12 * (broad - 0.5)
    # soft vertical tone bands: the balloon's skin catching the light
    du = np.angle(np.exp(2j * math.pi * (u - SHINE_U))) / (2 * math.pi)
    bands = 0.08 * np.cos(2 * math.pi * du * 3) * np.sin(polar)
    rgb = _ramp(np.clip(tone + bands, 0, 1), [(0.0, GOLD_SHADOW), (0.3, GOLD_DEEP), (0.62, GOLD), (1.0, GOLD_LIGHT)])
    # the glossy highlight: a big soft lobe and a small hot glint
    dx, dy = du * ring * 2.6, (v - SHINE_V) * 1.25
    soft = np.exp(-(dx * dx + dy * dy) / 0.012)
    gx, gy = (du + 0.035) * ring * 2.6, (v - SHINE_V + 0.03) * 1.25
    glint = np.exp(-(gx * gx / 0.0011 + gy * gy / 0.0022))
    rim = np.exp(-((v - 0.9) / 0.06) ** 2) * np.exp(-(np.angle(np.exp(2j * math.pi * (u - SHINE_U - 0.5))) / 0.9) ** 2)
    rgb = rgb * (1 - soft[..., None] * 0.75) + GOLD_LIGHT * soft[..., None] * 0.75
    rgb = rgb * (1 - glint[..., None]) + WHITE * glint[..., None]
    rgb = rgb + GOLD_LIGHT * rim[..., None] * 0.08
    return rgba(rgb, np.ones((h, w), np.float32))


def balloon_mr(size=256, seed=3):
    """Metallic, glossy (glTF channels: G = roughness, B = metallic). The highlight is smoother."""
    h = w = size
    u = (np.arange(w) + 0.5)[None, :] / w * np.ones((h, 1))
    v = (np.arange(h) + 0.5)[:, None] / h * np.ones((1, w))
    du = np.angle(np.exp(2j * math.pi * (u - SHINE_U))) / (2 * math.pi)
    shine = np.exp(-((du * 2.6) ** 2 + ((v - SHINE_V) * 1.25) ** 2) / 0.012)
    rough = 0.2 + 0.05 * fbm(h, w, 6, 12, seed + 4, octaves=2, periodic_x=True) - 0.08 * shine
    return rgba(np.stack([np.zeros((h, w)), rough, np.full((h, w), 0.7)], axis=2), np.ones((h, w)))


# ---------------------------------------------------------------- the crown

def gold(size=512, seed=5):
    """Polished gold with a faint brushed grain."""
    h = w = size
    grain = fbm(h, w, 96, 4, seed, octaves=3, periodic_x=True)
    broad = fbm(h, w, 5, 5, seed + 1, periodic_x=True)
    v = 0.92 + 0.08 * grain + 0.05 * broad
    rgb = GOLD[None, None, :] * v[..., None]
    return rgba(rgb, np.ones((h, w), np.float32))


def gold_recess(size=512, seed=8):
    """The slightly darker gold between the crown's raised borders, with fine engraved rays."""
    x, y = _grid(size, size)
    grain = fbm(size, size, 64, 6, seed, octaves=3, periodic_x=True)
    ang = np.arctan2(y + 1.1, x)
    rays = 0.5 + 0.5 * np.cos(ang * 46)
    v = 0.66 + 0.1 * grain + 0.08 * _smooth(rays, 0.7, 1.0)
    rgb = _ramp(v, [(0.0, GOLD_DARK), (0.6, GOLD_DEEP), (1.0, GOLD)])
    return rgba(rgb, np.ones((size, size), np.float32))


def gold_mr(size=256, seed=5, rough=0.1):
    h = w = size
    r = rough + 0.08 * fbm(h, w, 12, 12, seed + 9, periodic_x=True)
    return rgba(np.stack([np.zeros((h, w)), r, np.ones((h, w))], axis=2), np.ones((h, w)))


def gem(size=512, seed=3):
    """A bright yellow-gold gem with facet glints."""
    h = w = size
    edge = _voronoi_edges(h, w, 18, seed)
    line = np.exp(-(edge / 1.4) ** 2)[..., None]
    depth = fbm(h, w, 4, 4, seed + 1, periodic_x=True)[..., None]
    rgb = GEM * (0.8 + 0.3 * depth) * (1 - line * 0.3) + GOLD_LIGHT * line * 0.3
    return rgba(rgb, np.full((h, w), 0.85, np.float32))


def gem_mr(size=64, rough=0.04):
    return rgba(np.stack([np.zeros((size, size)), np.full((size, size), rough), np.zeros((size, size))], axis=2),
                np.ones((size, size)))


# ---------------------------------------------------------------- the wings

def feather(w=256, h=1024, seed=12):
    """One feather, u across (0 / 1 the edges, 0.5 the quill), v along (0 at the base, 1 at the
    tip): gold at the base, ivory along the vane, bright white at the tip, fine barbs sweeping
    out from the quill and a soft warm shade along the edges."""
    u = (np.arange(w, dtype=np.float32) + 0.5)[None, :] / w * np.ones((h, 1), np.float32)
    v = (np.arange(h, dtype=np.float32) + 0.5)[:, None] / h * np.ones((1, w), np.float32)
    across = np.abs(u - 0.5) * 2
    tip = _smooth(v, 0.62, 0.95)
    rgb = _ramp(v, [(0.0, GOLD), (0.22, (GOLD + CREAM) / 2), (0.45, CREAM), (0.68, IVORY), (0.9, WHITE), (1.0, WHITE)])
    # the barbs: fine lines angled from the quill towards the tip
    phase = (v * 70 - across * 9 + fbm(h, w, 8, 2, seed, octaves=2) * 1.5) % 1.0
    barbs = np.exp(-((phase - 0.5) / 0.18) ** 2)
    rgb = rgb * (1 - 0.07 * barbs[..., None])
    # a few splits in the vane, like real feathers
    split = fbm(h, w, 14, 2, seed + 5, octaves=1)
    rgb = rgb * (1 - 0.08 * _smooth(split, 0.72, 0.8)[..., None] * _smooth(across, 0.4, 0.8)[..., None])
    # warm shade along the edges and the quill
    edge = _smooth(across, 0.72, 1.0)
    rgb = rgb * (1 - edge[..., None] * 0.18) + CREAM * edge[..., None] * 0.12
    quill = np.exp(-(across / 0.035) ** 2) * (1 - 0.6 * tip)
    rgb = rgb * (1 - quill[..., None] * 0.5) + GOLD_LIGHT * quill[..., None] * 0.5
    return rgba(rgb, np.ones((h, w), np.float32))


def feather_mr(size=64):
    return rgba(np.stack([np.zeros((size, size)), np.full((size, size), 0.55), np.zeros((size, size))], axis=2),
                np.ones((size, size)))


def string_tex(size=64):
    v = np.linspace(0, 1, size)[:, None] * np.ones((1, size))
    rgb = WHITE * (0.94 + 0.06 * np.cos(v * 40))[..., None]
    return rgba(rgb, np.ones((size, size), np.float32))


# ---------------------------------------------------------------- aura / VFX

def glow(size=256, colour=None, core=None):
    x, y = _grid(size, size)
    r = np.sqrt(x * x + y * y)
    a = np.exp(-(r / 0.42) ** 2) * _smooth(1 - r, 0, 0.2)
    c = GOLD_LIGHT if colour is None else colour
    k = WHITE if core is None else core
    m = np.exp(-(r / 0.22) ** 2)[..., None]
    return rgba(c * (1 - m) + k * m, a)


def glow_gold(size=256):
    return glow(size, GOLD, GOLD_LIGHT)


def glow_soft(size=256):
    """Soft yellow-white, for the bloom-like halo round the balloon."""
    return glow(size, (GOLD_LIGHT + WHITE) / 2, WHITE)


def rays(size=512, seed=7):
    """Small soft light rays fanning out from the centre."""
    x, y = _grid(size, size)
    r = np.sqrt(x * x + y * y)
    ang = np.arctan2(y, x)
    rng = np.random.default_rng(seed)
    streak = np.zeros_like(r)
    for _ in range(22):
        a0 = rng.uniform(-math.pi, math.pi)
        wdt = rng.uniform(0.015, 0.05)
        da = np.angle(np.exp(1j * (ang - a0)))
        streak = np.maximum(streak, np.exp(-(da / wdt) ** 2) * rng.uniform(0.4, 1.0))
    fade = np.exp(-(r / 0.6) ** 2) * _smooth(r, 0.05, 0.3)
    a = np.clip(streak * fade, 0, 1) * _smooth(1 - r, 0, 0.1)
    rgb = GOLD_LIGHT * (1 - streak[..., None] * 0.4) + WHITE * streak[..., None] * 0.4
    return rgba(rgb, a)


def trail(w=1024, h=96, seed=11):
    """A thin swirling strand of golden energy: a bright core, warm gold edges, broken up along
    its length and fading at both ends."""
    u = np.linspace(0, 1, w)[None, :] * np.ones((h, 1))
    v = np.linspace(-1, 1, h)[:, None] * np.ones((1, w))
    wob = (fbm(h, w, 1, 4, seed, octaves=2, periodic_x=True) - 0.5) * 0.4
    core = np.exp(-((v - wob) / 0.1) ** 2)
    body = np.exp(-((v - wob * 0.7) / 0.42) ** 2) * 0.55
    breakup = _smooth(fbm(1, w, 1, 6, seed + 3, octaves=2, periodic_x=True), 0.25, 0.55)
    ends = _smooth(u, 0.0, 0.18) * _smooth(1 - u, 0.0, 0.3)
    a = np.clip(core * (0.55 + 0.45 * breakup) + body * (0.35 + 0.65 * breakup), 0, 1) * ends
    rgb = GOLD * (1 - core[..., None]) + (GOLD_LIGHT + WHITE) / 2 * core[..., None]
    return rgba(rgb, np.clip(a * 1.2, 0, 1))


def sparkle(size=128):
    """A four-point star flash: white-gold core, thin spikes, soft halo (additive)."""
    x, y = _grid(size, size)
    ax, ay = np.abs(x), np.abs(y)
    star = np.exp(-ax / 0.03) * np.exp(-ay / 0.42) + np.exp(-ay / 0.03) * np.exp(-ax / 0.42)
    diag = (np.exp(-np.abs(x - y) / 0.035) + np.exp(-np.abs(x + y) / 0.035)) * np.exp(-np.sqrt(x * x + y * y) / 0.16) * 0.4
    core = np.exp(-(np.sqrt(x * x + y * y) / 0.09) ** 2)
    halo = np.exp(-(np.sqrt(x * x + y * y) / 0.3) ** 2) * 0.35
    a = np.clip(star + diag + core + halo, 0, 1) * _smooth(1 - np.maximum(ax, ay), 0, 0.1)
    m = np.clip(core + star * 0.5, 0, 1)[..., None]
    rgb = GOLD_LIGHT * (1 - m) + WHITE * m
    return rgba(rgb, a)


def star(size=64):
    """A tiny glowing star: a small diamond-shaped twinkle."""
    x, y = _grid(size, size)
    d = np.abs(x) ** 0.7 + np.abs(y) ** 0.7
    core = np.exp(-(d / 0.35) ** 2)
    halo = np.exp(-((x * x + y * y) / 0.25)) * 0.35
    a = np.clip(core + halo, 0, 1) * _smooth(1 - np.maximum(np.abs(x), np.abs(y)), 0, 0.15)
    m = core[..., None]
    return rgba(GOLD_LIGHT * (1 - m) + WHITE * m, a)


def mote(size=64):
    x, y = _grid(size, size)
    r = np.sqrt(x * x + y * y)
    core = np.exp(-(r / 0.2) ** 2)
    halo = np.exp(-(r / 0.55) ** 2) * 0.5
    rgb = GOLD * (1 - core[..., None]) + GOLD_LIGHT * core[..., None]
    return rgba(rgb, np.clip(core + halo, 0, 1) * _smooth(1 - r, 0, 0.2))


def feather_sprite(size=256, seed=4):
    """A small floating feather: a curved quill and a soft vane, white with a gold base."""
    x, y = _grid(size, size)
    # the quill runs diagonally, gently curved
    t = np.clip((x + y) / 2 * 0.95 / 0.95, -1, 1)
    bend = 0.18 * (1 - t * t)
    off = (y - x) / math.sqrt(2) - bend
    along = (x + y) / math.sqrt(2)
    f = np.clip((along + 1.15) / 2.3, 0, 1)                         # 0 at the base, 1 at the tip
    half = 0.24 * np.sin(np.clip(f, 0, 1) * math.pi) ** 0.7 * (f > 0.08)
    vane = _smooth(half - np.abs(off), 0.0, 0.03)
    barbs = 0.94 + 0.06 * np.cos((along * 30 - np.abs(off) * 22))
    quill = np.exp(-(off / 0.012) ** 2) * (f > 0.0) * (f < 1.0)
    base = 1 - _smooth(f, 0.1, 0.45)
    rgb = IVORY * (1 - base[..., None]) + GOLD * base[..., None]
    rgb = rgb * barbs[..., None]
    rgb = rgb * (1 - quill[..., None] * 0.4) + GOLD_LIGHT * quill[..., None] * 0.4
    a = np.clip(vane * (0.85 + 0.15 * barbs) + quill * 0.8, 0, 1) * (np.abs(along) < 1.12)
    return rgba(rgb, a)


def swirl_band(w=128, h=256, seed=29):
    """Cross-section of the wide golden swoosh round the balloon (top = bright edge)."""
    v = np.linspace(0, 1, h)[:, None] * np.ones((1, w))
    n = fbm(h, w, 8, 2, seed, periodic_x=True)
    edge = np.exp(-((v - 0.1) / 0.05) ** 2)
    body = _smooth(v, 0.05, 0.25) * (1 - _smooth(v, 0.4, 0.95 - 0.2 * n))
    heat = np.clip(edge + body * (0.75 - 0.5 * v), 0, 1)
    rgb = _ramp(heat, [(0.0, GOLD_DEEP), (0.45, GOLD), (0.8, GOLD_LIGHT), (1.0, WHITE)])
    return rgba(rgb, np.clip(edge + body * (0.9 - 0.6 * v) * (0.6 + 0.4 * n), 0, 1))


AURA = {
    "Glow": glow,
    "GlowGold": glow_gold,
    "GlowSoft": glow_soft,
    "Rays": rays,
    "Trail": trail,
    "Sparkle": sparkle,
    "Star": star,
    "Mote": mote,
    "Feather": feather_sprite,
    "Swirl": swirl_band,
}
