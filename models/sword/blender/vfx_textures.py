"""
Procedural VFX textures for the Mo Feng blade (numpy only, so it also runs
inside Blender's bundled Python).

Every function returns a float32 array of shape (H, W, 4), values 0..1,
row 0 = top of the image. Particle sprites are white with an alpha mask (the
Roblox emitter colours them). ForceField / beam textures are grey on black.
"""

import math

import numpy as np

RNG = np.random.default_rng(7)


# ---------------------------------------------------------------- helpers

def _grid(h, w):
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    return (x + 0.5) / w * 2 - 1, (y + 0.5) / h * 2 - 1   # -1..1, y down


def _rgba(intensity, alpha=None, tint=(1.0, 1.0, 1.0)):
    i = np.clip(intensity, 0, 1)
    out = np.zeros(i.shape + (4,), np.float32)
    for c in range(3):
        out[..., c] = np.clip(i * tint[c], 0, 1)
    out[..., 3] = np.clip(i if alpha is None else alpha, 0, 1)
    return out


def _sprite(alpha):
    """White sprite: colour stays white, alpha carries the shape."""
    a = np.clip(alpha, 0, 1)
    out = np.ones(a.shape + (4,), np.float32)
    out[..., 3] = a
    return out


def _smooth(x, e0, e1):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def _blur(img, sigma):
    """Gaussian blur through the FFT (wraps around, fine for our soft shapes)."""
    h, w = img.shape
    fy = np.fft.fftfreq(h)[:, None]
    fx = np.fft.fftfreq(w)[None, :]
    k = np.exp(-2 * (math.pi * sigma) ** 2 * (fx * fx + fy * fy))
    return np.real(np.fft.ifft2(np.fft.fft2(img) * k))


def value_noise(h, w, cells_y, cells_x, seed, periodic_x=True):
    """Smooth value noise in 0..1 (bicubic-ish), optionally tileable in x."""
    rng = np.random.default_rng(seed)
    g = rng.random((cells_y + 3, cells_x + 3)).astype(np.float32)
    if periodic_x:
        g[:, cells_x:cells_x + 3] = g[:, 0:3]
    ys = np.linspace(0, cells_y, h, endpoint=False) + 1
    xs = np.linspace(0, cells_x, w, endpoint=False) + 1
    y0 = np.floor(ys).astype(int)
    x0 = np.floor(xs).astype(int)
    ty = _smooth(ys - y0, 0, 1)[:, None]
    tx = _smooth(xs - x0, 0, 1)[None, :]
    a = g[y0][:, x0]
    b = g[y0][:, x0 + 1]
    c = g[y0 + 1][:, x0]
    d = g[y0 + 1][:, x0 + 1]
    return (a * (1 - tx) + b * tx) * (1 - ty) + (c * (1 - tx) + d * tx) * ty


def fbm(h, w, base_y, base_x, seed, octaves=4, periodic_x=True):
    total = np.zeros((h, w), np.float32)
    amp, norm = 1.0, 0.0
    for o in range(octaves):
        total += amp * value_noise(h, w, base_y * 2 ** o, base_x * 2 ** o, seed + o * 13, periodic_x)
        norm += amp
        amp *= 0.5
    return total / norm


# ---------------------------------------------------------------- particle sprites

def glow(size=256):
    x, y = _grid(size, size)
    r2 = x * x + y * y
    a = np.exp(-r2 / 0.16) * 0.85 + np.exp(-r2 / 0.02) * 0.5
    return _sprite(a * _smooth(1 - np.sqrt(r2), 0, 0.15))


def spark(size=256):
    """Vertical streak for VelocityParallel sparks."""
    x, y = _grid(size, size)
    core = np.exp(-(x / 0.035) ** 2 - (y / 0.75) ** 2)
    halo = np.exp(-(x / 0.12) ** 2 - (y / 0.9) ** 2) * 0.45
    return _sprite(np.clip(core + halo, 0, 1) * _smooth(1 - np.abs(y), 0, 0.2))


def star(size=256):
    x, y = _grid(size, size)
    r = np.sqrt(x * x + y * y)
    rays = np.exp(-(x / 0.03) ** 2 - (y / 0.9) ** 2) + np.exp(-(y / 0.03) ** 2 - (x / 0.9) ** 2)
    diag_x, diag_y = (x + y) * 0.7071, (x - y) * 0.7071
    rays += 0.35 * (np.exp(-(diag_x / 0.025) ** 2 - (diag_y / 0.45) ** 2) +
                    np.exp(-(diag_y / 0.025) ** 2 - (diag_x / 0.45) ** 2))
    core = np.exp(-(r / 0.12) ** 2)
    return _sprite(np.clip(rays + core, 0, 1) * _smooth(1 - r, 0, 0.1))


def ember(size=128):
    x, y = _grid(size, size)
    r2 = x * x + y * y
    return _sprite(np.clip(np.exp(-r2 / 0.012) + np.exp(-r2 / 0.12) * 0.35, 0, 1))


def smoke(size=256):
    x, y = _grid(size, size)
    r = np.sqrt(x * x + y * y)
    n = fbm(size, size, 4, 4, seed=21, periodic_x=False)
    a = _smooth(0.85 - r + (n - 0.5) * 0.7, 0, 0.45) * 0.8
    return _sprite(a)


def flash(size=512):
    x, y = _grid(size, size)
    r = np.sqrt(x * x + y * y) + 1e-6
    ang = np.arctan2(y, x)
    rays = np.zeros_like(r)
    rng = np.random.default_rng(3)
    for _ in range(14):
        a0 = rng.uniform(-math.pi, math.pi)
        length = rng.uniform(0.55, 0.95)
        d = np.angle(np.exp(1j * (ang - a0)))
        rays += np.exp(-(d / 0.035) ** 2) * _smooth(length - r, 0, length * 0.8)
    core = np.exp(-(r / 0.22) ** 2) + np.exp(-(r / 0.5) ** 2) * 0.4
    return _sprite(np.clip(core + rays * 0.8, 0, 1) * _smooth(1 - r, 0, 0.1))


def ring_sprite(size=256):
    x, y = _grid(size, size)
    r = np.sqrt(x * x + y * y)
    a = np.exp(-((r - 0.82) / 0.05) ** 2) + np.exp(-((r - 0.82) / 0.14) ** 2) * 0.35
    return _sprite(a)


def wisp_flipbook(frame=256, grid=4, seed=11):
    """4x4 flipbook of a flame wisp that licks upward and breaks apart."""
    frames = grid * grid
    out = np.zeros((frame * grid, frame * grid, 4), np.float32)
    x, y = _grid(frame, frame)
    warp_a = fbm(frame, frame, 3, 3, seed, periodic_x=False) - 0.5
    warp_b = fbm(frame, frame, 3, 3, seed + 5, periodic_x=False) - 0.5
    detail = fbm(frame, frame, 6, 6, seed + 9, periodic_x=False)
    for k in range(frames):
        t = k / (frames - 1)
        rise = 0.35 * t
        stretch = 0.55 + 0.6 * t
        sx, sy = x * 0.6, y * 0.6 + 0.12                          # fill the frame
        wx = sx + warp_a * (0.3 + 0.5 * t) + 0.1 * np.sin(sy * 4 + t * 6)
        wy = sy + rise + warp_b * (0.25 + 0.45 * t)
        # teardrop: wide at the bottom, pointed at the top
        width = 0.42 * (1 - 0.35 * t) * _smooth(wy + 0.9, 0, 1.2) * (1 - _smooth(wy, -0.2, 0.9) * 0.75)
        shape = 1 - (np.abs(wx) / np.maximum(width, 1e-3)) ** 2 - ((wy + 0.15) / stretch) ** 2
        a = _smooth(shape, 0, 0.55) * (0.65 + 0.7 * detail)
        a *= (1 - t) ** 1.1 * (0.55 + 0.45 * _smooth(t, 0.0, 0.15))   # quick fade in, slow fade out
        a = np.clip(a, 0, 1)
        gy, gx = divmod(k, grid)
        out[gy * frame:(gy + 1) * frame, gx * frame:(gx + 1) * frame] = _sprite(a)
    return out


# ---------------------------------------------------------------- beams / trails

def energy_beam(w=512, h=128, seed=4):
    """Wavy energy filaments; tiles left-right for TextureSpeed scrolling."""
    u = np.linspace(0, 1, w, endpoint=False)[None, :]
    v = np.linspace(0, 1, h)[:, None]
    rng = np.random.default_rng(seed)
    img = np.zeros((h, w), np.float32)
    for _ in range(9):
        n = rng.integers(1, 5)
        amp = rng.uniform(0.05, 0.25)
        phase = rng.uniform(0, 2 * math.pi)
        centre = 0.5 + amp * np.sin(2 * math.pi * n * u + phase)
        thick = rng.uniform(0.012, 0.035)
        bright = rng.uniform(0.4, 1.0)
        img += bright * np.exp(-((v - centre) / thick) ** 2)
    img *= np.exp(-((v - 0.5) / 0.32) ** 2)
    img = np.clip(img * 0.9, 0, 1)
    return _rgba(img, img)


def lightning(w=512, h=128, seed=8):
    u = np.linspace(0, 1, w, endpoint=False)
    rng = np.random.default_rng(seed)
    # periodic jagged path: sum of integer-frequency sines plus sharp kinks
    path = np.zeros_like(u)
    for f in range(1, 12):
        path += rng.uniform(-1, 1) / f * np.sin(2 * math.pi * f * u + rng.uniform(0, 6.28))
    path = 0.5 + path / np.abs(path).max() * 0.32
    v = np.linspace(0, 1, h)[:, None]
    d = np.abs(v - path[None, :])
    img = np.exp(-(d / 0.012) ** 2) + np.exp(-(d / 0.06) ** 2) * 0.35
    img = np.clip(img, 0, 1)
    return _rgba(img, img)


def trail(w=256, h=256, seed=2):
    """Swing trail: V runs base->tip of the blade, U runs along the trail."""
    u = np.linspace(0, 1, w)[None, :]
    v = np.linspace(1, 0, h)[:, None]           # row 0 = v 1 (blade tip side)
    streak = fbm(h, w, 24, 2, seed, periodic_x=False)
    core = np.exp(-((v - 0.88) / 0.07) ** 2)    # bright band along the blade tip's path
    body = _smooth(v, 0.05, 0.85) * 0.55
    head = 1 - _smooth(u, 0.0, 1.0) * 0.6        # Stretch mode: u 0 = newest
    img = np.clip((core + body * (0.6 + 0.6 * streak)) * head, 0, 1)
    return _rgba(img, img)


# ---------------------------------------------------------------- ForceField mesh textures

def slash_gradient(w=1024, h=256, seed=5):
    """For the SlashArc mesh: U along the arc (tail->head), V inner->outer edge."""
    u = np.linspace(0, 1, w)[None, :]
    v = np.linspace(1, 0, h)[:, None]           # row 0 = outer edge (v = 1)
    streaks = fbm(h, w, 6, 40, seed, periodic_x=False)
    edge = np.exp(-((v - 0.94) / 0.045) ** 2)
    fill = _smooth(v, 0.0, 0.9) ** 1.2 * (0.35 + 0.65 * streaks)
    along = _smooth(u, 0.0, 0.45) * (1 - _smooth(u, 0.93, 1.0))
    img = np.clip((edge * 0.95 + fill * 0.85) * along, 0, 1)
    return _rgba(img, np.ones_like(img))


def ring_gradient(w=1024, h=128, seed=6):
    """For the ShockRing mesh: U around the ring (tiles), V inner->outer."""
    v = np.linspace(1, 0, h)[:, None]
    streaks = fbm(h, w, 4, 48, seed, periodic_x=True)
    edge = np.exp(-((v - 0.9) / 0.08) ** 2)
    fill = _smooth(v, 0.0, 0.85) ** 2 * (0.3 + 0.7 * streaks)
    img = np.clip(edge + fill * 0.7, 0, 1)
    return _rgba(img, np.ones_like(img))


def aura_flow(w=256, h=1024, seed=9):
    """For the BladeAura ForceField hull: U around (tiles), V along the blade (tiles)."""
    n1 = fbm(h, w, 3, 14, seed, periodic_x=True)       # long along the blade, thin across
    n2 = fbm(h, w, 10, 28, seed + 3, periodic_x=True)
    streak = np.clip((n1 - 0.48) * 3.0, 0, 1) * (0.45 + 0.8 * n2)
    img = np.clip(streak, 0, 1)
    # make it tile top-bottom too by blending with a shifted copy near the seam
    blend = _smooth(np.linspace(0, 1, h), 0.85, 1.0)[:, None]
    img = img * (1 - blend) + np.roll(img, h // 2, axis=0) * blend
    return _rgba(img, np.ones_like(img))


ALL_SPRITES = {
    "Glow": glow,
    "Spark": spark,
    "Star": star,
    "Ember": ember,
    "Smoke": smoke,
    "Flash": flash,
    "RingSprite": ring_sprite,
    "Wisp": wisp_flipbook,
    "Beam": energy_beam,
    "Lightning": lightning,
    "Trail": trail,
}
