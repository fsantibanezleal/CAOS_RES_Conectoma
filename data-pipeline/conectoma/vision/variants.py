"""Physical variants of a clip: each case varies one physical quantity over six levels, with units.

A transform acts where its physics happens. Light and optics act on the image at source resolution, before
the lattice: fog attenuates with each pixel's metric depth, blur integrates each pixel along its own motion
over the exposure, contrast and illumination scale the image. Photon noise acts on the column, because the
photoreceptor under each column is what counts photons. Speed changes only time. None changes the ground
truth except where the physics does: speed changes the frame interval, so flow per second, and nothing here
moves depth or figure.

- speed: the clip is shown at a shorter or longer frame interval. The camera passes through the same
  positions and sees the same images, only sooner, so this is exactly the same path flown faster; the speed
  in m/s is the camera step (from the poses) over the interval.
- illumination: a global gain on luminance (relative illuminance), with no adaptation: the image darkens.
- photons: Poisson noise on each column at a stated count of photons per column per frame at luminance 1.
- blur: each pixel averaged along its own image motion during the exposure; a pixel moving `f` pixels per
  frame is smeared over `f * exposure / interval` pixels, centred on the frame's instant.
- fog: `I' = I exp(-b d) + A (1 - exp(-b d))`, b in 1/m with the source's metric depth, airlight A. The
  meteorological visibility is 3.912 / b (Koschmieder, the distance where contrast falls to 2 percent).
- contrast: luminance scaled about each frame's mean, by the stated factor.
- crop: the central part of the frame, so each column sees a smaller angle (a longer lens).
"""

from __future__ import annotations

import math

import cv2
import numpy as np

AIRLIGHT = 0.7
KOSCHMIEDER = -math.log(0.02)   # 3.912: visibility is where exp(-b d) falls to 2 percent


def illumination(lum: np.ndarray, gain: float) -> np.ndarray:
    return np.clip(lum * gain, 0.0, 1.0).astype(np.float32)


def photons(lum: np.ndarray, count: float | None, seed: int) -> np.ndarray:
    """Poisson noise at `count` expected photons per column per frame at luminance 1; None for none.

    `lum` is the lattice luminance (frames, columns): each column's photoreceptor counts its own photons.
    """
    if not count:
        return lum.astype(np.float32)
    rng = np.random.default_rng(seed)
    return np.clip(rng.poisson(lum.astype(np.float64) * count) / count, 0.0, 1.0).astype(np.float32)


def fog(lum: np.ndarray, depth: np.ndarray, attenuation_per_m: float,
        airlight: float = AIRLIGHT) -> np.ndarray:
    """Depth-dependent haze with metric depth; masked (NaN) depth is treated as infinitely far."""
    if attenuation_per_m <= 0:
        return lum.astype(np.float32)
    d = np.where(np.isfinite(depth), depth, np.inf)
    transmission = np.exp(-attenuation_per_m * d)
    return np.clip(lum * transmission + airlight * (1.0 - transmission), 0.0, 1.0).astype(np.float32)


def visibility_m(attenuation_per_m: float) -> float | None:
    return KOSCHMIEDER / attenuation_per_m if attenuation_per_m > 0 else None


def contrast(lum: np.ndarray, factor: float) -> np.ndarray:
    mean = lum.mean(axis=(-2, -1), keepdims=True)
    return np.clip(mean + factor * (lum - mean), 0.0, 1.0).astype(np.float32)


def blur(lum: np.ndarray, flow_px: np.ndarray, exposure_s: float, interval_s: float) -> np.ndarray:
    """Motion blur over an exposure of `exposure_s`, each pixel along its own motion.

    Frame t moves by `flow_px[t]` pixels to the next frame (the last frame uses the motion into it); over the
    exposure a pixel sweeps `flow * exposure / interval`, centred on the frame. The sweep is sampled densely
    enough that no sample is more than half a pixel from the next, so the blur has no ghosts.
    """
    if exposure_s <= 0:
        return lum.astype(np.float32)
    frames, h, w = lum.shape
    v, u = np.mgrid[0:h, 0:w].astype(np.float32)
    fraction = exposure_s / interval_s
    out = np.empty((frames, h, w), dtype=np.float32)
    for t in range(frames):
        sweep = flow_px[min(t, len(flow_px) - 1)] * fraction
        samples = max(2, int(np.ceil(2 * np.abs(sweep).max())) + 1)
        acc = np.zeros((h, w), np.float32)
        frame = lum[t].astype(np.float32)
        for s in np.linspace(-0.5, 0.5, samples, dtype=np.float32):
            map_x = (u + s * sweep[0]).astype(np.float32)
            map_y = (v + s * sweep[1]).astype(np.float32)
            acc += cv2.remap(frame, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        out[t] = acc / samples
    return out


def blur_length_px(flow_px: np.ndarray, exposure_s: float, interval_s: float) -> float:
    """The median length of the blur, in source pixels, over every pixel of the clip."""
    return float(np.median(np.hypot(flow_px[:, 0], flow_px[:, 1])) * exposure_s / interval_s)


def speed_interval(interval_s: float, factor: float) -> float:
    """The frame interval that makes the clip's motion `factor` times as fast."""
    return interval_s / factor


def crop_for_fov(camera_fov_deg: float, target_fov_deg: float) -> float:
    """The crop fraction that takes a centred pinhole view of `camera_fov_deg` to `target_fov_deg`."""
    return math.tan(math.radians(target_fov_deg) / 2) / math.tan(math.radians(camera_fov_deg) / 2)
