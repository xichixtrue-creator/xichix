"""
Textures for the Crimson Reaper scythe: crimson crystal with bright fracture lines,
dark gothic metal, and the red / black aura layers (energy ribbons, smoke, shards,
drips, glow, slash). numpy only, so this also runs inside Blender's bundled Python.
Every function returns float32 RGBA in 0..1 (rows top to bottom).
"""

import math

import numpy as np

CRIMSON = np.array([0.78, 0.02, 0.06])
BLOOD = np.array([0.36, 0.0, 0.03])
HOT = np.array([1.0, 0.16, 0.2])
PINK = np.array([1.0, 0.62, 0.66])
EMBER = np.array([1.0, 0.3, 0.3])
SOOT = np.array([0.05, 0.0, 0.01])


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


def _voronoi_edges(h, w, count, seed):
    """Distance to the nearest Voronoi cell border (0 on the border), in pixels."""
    rng = np.random.default_rng(seed)
    pts = rng.random((count, 2)) * np.array([w, h])
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    best, second = np.full((h, w), 1e9, np.float32), np.full((h, w), 1e9, np.float32)
    for px, py in pts:
        for ox in (-w, 0, w):                       # tiles horizontally
            d = np.sqrt((x - px - ox) ** 2 + (y - py) ** 2)
            second = np.where(d < best, best, np.minimum(second, d))
            best = np.minimum(best, d)
    return (second - best) * 0.5


def _colour_ramp(t, stops):
    t = np.clip(t, 0, 1)
    out = np.zeros(t.shape + (3,), np.float32)
    for (p0, c0), (p1, c1) in zip(stops[:-1], stops[1:]):
        m = (t >= p0) & (t <= p1)
        f = ((t - p0) / (p1 - p0))[m][:, None]
        out[m] = np.array(c0) * (1 - f) + np.array(c1) * f
    return out


# ---------------------------------------------------------------- weapon surfaces

def crystal(size=1024, seed=1, alpha=0.86):
    """Crimson crystal: deep red depths, brighter cells, and thin pink-white fracture lines
    like the reference's corrupted crystal. Alpha < 1 so Roblox can show it translucent."""
    h = w = size
    edge = _voronoi_edges(h, w, 46, seed)
    fine = _voronoi_edges(h, w, 160, seed + 1)
    depth = fbm(h, w, 4, 4, seed + 2, periodic_x=True)
    cell = fbm(h, w, 10, 10, seed + 3, periodic_x=True)
    heat = 0.35 + 0.45 * depth + 0.2 * cell
    rgb = _colour_ramp(heat, [(0.0, BLOOD * 0.6), (0.45, BLOOD), (0.7, CRIMSON), (1.0, HOT)])
    crack = np.exp(-(edge / 1.6) ** 2)
    hair = np.exp(-(fine / 0.9) ** 2) * 0.45 * (cell > 0.45)
    glint = np.clip(crack + hair, 0, 1)[..., None]
    rgb = rgb * (1 - glint) + (PINK * 0.85 + HOT * 0.15) * glint
    a = np.full((h, w), alpha, np.float32) + 0.14 * glint[..., 0]
    return rgba(rgb, a)


def metal(size=1024, seed=5):
    """Dark gothic metal: near-black with a cold red cast, fine brushed streaks and scratches."""
    h = w = size
    base = fbm(h, w, 6, 6, seed, periodic_x=True)
    streak = fbm(h, w, 64, 3, seed + 1, octaves=3, periodic_x=True)
    rng = np.random.default_rng(seed + 2)
    scratch = np.zeros((h, w), np.float32)
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    for _ in range(90):
        x0, y0 = rng.random() * w, rng.random() * h
        a = rng.uniform(0, math.pi)
        ln = rng.uniform(20, 120)
        dx, dy = math.cos(a), math.sin(a)
        t = np.clip((x - x0) * dx + (y - y0) * dy, 0, ln)
        d = np.sqrt((x - x0 - t * dx) ** 2 + (y - y0 - t * dy) ** 2)
        scratch = np.maximum(scratch, np.exp(-(d / 0.7) ** 2) * rng.uniform(0.3, 1))
    v = 0.1 + 0.07 * base + 0.04 * streak + 0.22 * scratch
    rgb = np.stack([v * 1.18, v * 0.86, v * 0.9], axis=2)
    return rgba(rgb, np.ones((h, w), np.float32))


def metal_mr(size=512, seed=5):
    """glTF metallic-roughness map for the metal (G = roughness, B = metalness)."""
    h = w = size
    r = 0.2 + 0.16 * fbm(h, w, 8, 8, seed + 9, periodic_x=True)
    return rgba(np.stack([np.zeros((h, w)), r, np.full((h, w), 0.92)], axis=2), np.ones((h, w)))


def crystal_mr(size=64):
    return rgba(np.stack([np.zeros((size, size)), np.full((size, size), 0.12), np.zeros((size, size))], axis=2),
                np.ones((size, size)))


# ---------------------------------------------------------------- aura / VFX

def energy_ribbon(w=1024, h=128, seed=11):
    """A strand of crimson magic: a few bright thin threads inside a ragged red glow,
    fading out at both ends (u = along, v = across). Additive."""
    u = np.linspace(0, 1, w)[None, :] * np.ones((h, 1))
    v = np.linspace(-1, 1, h)[:, None] * np.ones((1, w))
    warp = (fbm(h, w, 2, 4, seed, periodic_x=True) - 0.5) * 0.9
    body = np.exp(-((v + warp * 0.6) / (0.45 + 0.25 * fbm(h, w, 2, 4, seed + 1, periodic_x=True))) ** 2)
    threads = np.zeros((h, w), np.float32)
    for k, (off, wd) in enumerate(((0.0, 0.06), (0.3, 0.035))):
        wob = (fbm(h, w, 1, 3, seed + 3 + k, octaves=2, periodic_x=True) - 0.5) * 0.7
        threads = np.maximum(threads, np.exp(-((v - off - wob) / wd) ** 2))
    breakup = _smooth(fbm(h, w, 2, 6, seed + 9, periodic_x=True), 0.3, 0.6)
    wisps = _smooth(fbm(1, w, 1, 7, seed + 12, octaves=2, periodic_x=True), 0.32, 0.62)   # whole stretches thin out
    ends = _smooth(u, 0.0, 0.18) * _smooth(1 - u, 0.0, 0.25)
    heat = np.clip(body * 0.7 * breakup + threads * (0.25 + 0.35 * breakup), 0, 1) * ends * (0.4 + 0.6 * wisps)
    rgb = _colour_ramp(heat, [(0.0, BLOOD * 0.5), (0.4, CRIMSON), (0.8, HOT), (1.0, PINK)])
    return rgba(rgb, np.clip(heat * 1.4, 0, 1))


def smoke_ribbon(w=1024, h=128, seed=27):
    """A dark red-black smoky strand (alpha-blended) that rides alongside the energy ribbons."""
    u = np.linspace(0, 1, w)[None, :] * np.ones((h, 1))
    v = np.linspace(-1, 1, h)[:, None] * np.ones((1, w))
    warp = (fbm(h, w, 2, 5, seed, periodic_x=True) - 0.5) * 1.0
    body = np.exp(-((v + warp * 0.5) / 0.55) ** 2)
    puffs = _smooth(fbm(h, w, 3, 10, seed + 1, periodic_x=True), 0.35, 0.7)
    ends = _smooth(u, 0.0, 0.2) * _smooth(1 - u, 0.0, 0.3)
    alpha = np.clip(body * puffs * 0.75, 0, 1) * ends
    tint = fbm(h, w, 4, 12, seed + 2, periodic_x=True)[..., None]
    rgb = SOOT * (1 - tint) + BLOOD * 0.8 * tint
    return rgba(rgb, alpha)


def smoke(frame=256, grid=4, seed=13):
    """Dark red-black smoke puffs that billow and thin out: 4x4 flipbook (alpha-blended)."""
    out = np.zeros((frame * grid, frame * grid, 4), np.float32)
    x, y = _grid(frame, frame)
    n1 = fbm(frame, frame, 4, 4, seed)
    n2 = fbm(frame, frame, 8, 8, seed + 1)
    for k in range(grid * grid):
        t = k / (grid * grid - 1)
        r = np.sqrt((x * (1.1 - 0.3 * t)) ** 2 + ((y + 0.1 * t) * (1.0 - 0.2 * t)) ** 2)
        shape = _smooth(0.75 + 0.2 * t - r - (n1 - 0.5) * (0.5 + 0.4 * t) - (n2 - 0.5) * 0.25, 0.0, 0.35)
        alpha = shape * (1 - t) ** 1.3 * 0.85 * _smooth(1 - np.maximum(np.abs(x), np.abs(y)), 0, 0.15)
        tint = np.clip(n2 * 1.3 - 0.35, 0, 1)[..., None] * (1 - t)
        rgb = BLOOD * 0.35 * (1 - tint) + (BLOOD * 0.7 + CRIMSON * 0.3) * tint
        cell = rgba(rgb, alpha)
        out[(k // grid) * frame:(k // grid + 1) * frame, (k % grid) * frame:(k % grid + 1) * frame] = cell
    return out


def shard(size=128):
    """A tiny floating crystal shard: bright faceted diamond with a white glint (additive)."""
    x, y = _grid(size, size)
    d = np.abs(x) / 0.42 + np.abs(y) / 0.95
    inside = _smooth(1 - d, 0.0, 0.08)
    facet = np.where(x > 0, 0.75, 1.0) * np.where(y < 0, 1.0, 0.8)
    glint = np.exp(-((x + 0.08) / 0.05) ** 2 - ((y + 0.25) / 0.3) ** 2)
    rgb = CRIMSON * facet[..., None] * 1.2 + PINK * glint[..., None]
    halo = np.exp(-(np.sqrt(x * x * 2 + y * y * 0.6) / 0.6) ** 2) * 0.35
    return rgba(np.clip(rgb * inside[..., None] + HOT * halo[..., None] * (1 - inside[..., None]), 0, 1),
                np.clip(inside + halo, 0, 1))


def glow(size=256):
    x, y = _grid(size, size)
    r = np.sqrt(x * x + y * y)
    a = np.exp(-(r / 0.45) ** 2) * _smooth(1 - r, 0, 0.2)
    rgb = _colour_ramp(np.exp(-(r / 0.25) ** 2), [(0.0, CRIMSON * 0.7), (1.0, HOT)])
    return rgba(rgb, a)


def spark(size=64):
    x, y = _grid(size, size)
    r = np.sqrt(x * x + y * y)
    core = np.exp(-(r / 0.18) ** 2)
    halo = np.exp(-(r / 0.5) ** 2) * 0.6
    rgb = HOT * (1 - core[..., None]) + PINK * core[..., None]
    return rgba(rgb, np.clip(core + halo, 0, 1) * _smooth(1 - r, 0, 0.2))


def drip(w=64, h=256, seed=17):
    """A drop of crimson magic hanging and stretching down (top = attached end). Additive."""
    x = np.linspace(-1, 1, w)[None, :] * np.ones((h, 1))
    v = np.linspace(0, 1, h)[:, None] * np.ones((1, w))
    width = 0.12 + 0.05 * np.sin(v * 9) * (1 - v)
    line = np.exp(-(x / width) ** 2) * _smooth(0.86 - v, 0, 0.1)
    drop_y = 0.88
    blob = np.exp(-((x / 0.34) ** 2 + ((v - drop_y) / 0.07) ** 2))
    heat = np.clip(line * (1 - 0.5 * v) + blob, 0, 1)
    rgb = _colour_ramp(heat, [(0.0, BLOOD), (0.6, CRIMSON), (1.0, HOT)])
    return rgba(rgb, np.clip(heat * 1.3, 0, 1) * _smooth(v, 0.0, 0.08))


def slash(size=1024, seed=19):
    """Crimson crescent slash for the swings: hot pink edge fading into dark red, with black
    smoky breakup on the inside (alpha-blended, so the dark wisps stay dark)."""
    x, y = _grid(size, size)
    r = np.sqrt(x * x + y * y)
    ang = (np.arctan2(y, x) + math.pi) / (2 * math.pi)            # 0..1 round the circle
    sweep = _smooth(ang, 0.05, 0.4) * _smooth(0.95 - ang, 0.0, 0.25)
    band = np.clip((r - (0.58 + 0.25 * (1 - sweep))) / 0.36, 0, 1)
    edge = np.exp(-((r - 0.93) / 0.03) ** 2) * sweep
    n = fbm(size, size, 8, 8, seed)
    body = band * (r < 0.95) * sweep * _smooth(n, 0.2, 0.55)
    heat = np.clip(body * (0.55 + 0.45 * band) + edge, 0, 1)
    rgb = _colour_ramp(heat, [(0.0, SOOT), (0.35, BLOOD), (0.7, CRIMSON), (0.92, HOT), (1.0, PINK)])
    return rgba(rgb, np.clip(heat * 1.6, 0, 1))


def slash_band(w=128, h=256, seed=29):
    """Cross-section of the crescent slash, the same all along (u): a hot pink cutting edge
    (top), a crimson body and a dark smoky inner side that frays out (bottom)."""
    v = np.linspace(0, 1, h)[:, None] * np.ones((1, w))
    n = fbm(h, w, 8, 2, seed, periodic_x=True)
    edge = np.exp(-((v - 0.08) / 0.045) ** 2)
    body = _smooth(v, 0.04, 0.2) * (1 - _smooth(v, 0.45, 0.95 - 0.25 * n))
    heat = np.clip(edge + body * (0.75 - 0.5 * v), 0, 1)
    rgb = _colour_ramp(heat, [(0.0, SOOT), (0.35, BLOOD), (0.7, CRIMSON), (0.9, HOT), (1.0, PINK)])
    return rgba(rgb, np.clip(edge + body * (1.1 - 0.6 * v) * (0.6 + 0.4 * n), 0, 1))


def trail(w=256, h=256, seed=21):
    """Swing trail (u = age along the trail, v = across the blade): pink edge, crimson body."""
    u = np.linspace(0, 1, w)[None, :] * np.ones((h, 1))
    v = np.linspace(0, 1, h)[:, None] * np.ones((1, w))
    n = fbm(h, w, 6, 4, seed)
    edge = np.exp(-((v - 0.08) / 0.05) ** 2)
    body = _smooth(v, 0.05, 0.3) * _smooth(1 - v, 0.0, 0.5) * _smooth(n, 0.25, 0.6)
    heat = np.clip(edge + body * 0.7, 0, 1) * (1 - u) ** 1.2
    rgb = _colour_ramp(heat, [(0.0, BLOOD), (0.5, CRIMSON), (0.85, HOT), (1.0, PINK)])
    return rgba(rgb, np.clip(heat * 1.4, 0, 1))


def ground_glow(size=512, seed=23):
    """The pool of crimson light under the scythe (reference's in-game view): soft red glow
    with a darker smoky ring and faint cracks."""
    x, y = _grid(size, size)
    r = np.sqrt(x * x + y * y)
    edge = _voronoi_edges(size, size, 30, seed)
    crack = np.exp(-(edge / 1.4) ** 2) * _smooth(0.75 - r, 0, 0.3)
    pool = np.exp(-(r / 0.42) ** 2)
    ring = np.exp(-((r - 0.62) / 0.12) ** 2) * fbm(size, size, 6, 6, seed + 1)
    heat = np.clip(pool * 0.75 + crack * 0.6 + ring * 0.3, 0, 1) * _smooth(1 - r, 0, 0.25)
    rgb = _colour_ramp(heat, [(0.0, SOOT), (0.4, BLOOD), (0.8, CRIMSON), (1.0, HOT)])
    return rgba(rgb, np.clip(heat * 1.2, 0, 1))


AURA = {
    "Ribbon": energy_ribbon,
    "SmokeRibbon": smoke_ribbon,
    "Smoke": smoke,
    "Shard": shard,
    "Glow": glow,
    "Spark": spark,
    "Drip": drip,
    "Slash": slash,
    "SlashBand": slash_band,
    "Trail": trail,
    "GroundGlow": ground_glow,
}
