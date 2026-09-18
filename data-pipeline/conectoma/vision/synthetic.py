"""Synthetic cases with exact ground truth: pure rotation (C13), a static camera (C14), textured planes at
known depths (C15), and the same planes with their texture fading away (C16).

Each generator returns frames at source resolution (luminance, planar depth, forward flow in pixels, and
where it applies a figure mask), which the renderer takes onto the lattice like any other source. Every
quantity is computed, not estimated:

- C13 rotates the camera about its optical centre. The image of any scene then moves by the homography
  `H = K R K^-1`, whatever its depth: frames are a real frame warped by H, the flow is H applied to the pixel
  grid, and depth is carried along (the new depth of a point X is the z of R X). Depth from motion is
  unobservable here by construction; a model that reports structure is reporting a prior.
- C14 repeats one frame with photon noise, so there is no motion signal at all.
- C15 translates a camera past fronto-parallel planes. A pixel at depth z moves by f t / z, so depth and flow
  are exact, and the nearer planes are figure against the farthest one.
- C16 is C15 with the texture contrast reduced to nothing: where a plane has no texture, its motion cannot be
  seen (the aperture problem), while its depth is still defined.
"""

from __future__ import annotations

import cv2
import numpy as np


def intrinsics(width: int, height: int, fov_deg: float) -> np.ndarray:
    f = 0.5 * width / np.tan(np.radians(fov_deg) / 2)
    return np.array([[f, 0.0, (width - 1) / 2], [0.0, f, (height - 1) / 2], [0.0, 0.0, 1.0]])


def yaw(angle_rad: float) -> np.ndarray:
    """Rotation about the camera's vertical axis (y down), positive turning the view to the right."""
    c, s = np.cos(angle_rad), np.sin(angle_rad)
    return np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]])


# ------------------------------------------------------------------------------------------ C13 pure rotation


def pure_rotation(lum: np.ndarray, depth: np.ndarray, K: np.ndarray, rate_deg_s: float, frames: int,
                  interval_s: float) -> dict:
    """A frame seen by a camera turning in place at `rate_deg_s`: exact frames, flow, depth and validity."""
    h, w = lum.shape
    K_inv = np.linalg.inv(K)
    v, u = np.mgrid[0:h, 0:w].astype(np.float64)
    pixels = np.stack([u, v, np.ones_like(u)])
    out_lum, out_depth, out_valid, flows = [], [], [], []
    for t in range(frames):
        R = yaw(np.radians(rate_deg_s) * interval_s * t)
        # frame t sees world direction d at p ~ K R^T d; the source frame (R = I) sees it at K d, so the
        # source pixel of p is K R K^-1 p
        H_inv = K @ R @ K_inv
        source = np.tensordot(H_inv, pixels, axes=1)
        su, sv = source[0] / source[2], source[1] / source[2]
        valid = (source[2] > 0) & (su >= 0) & (su <= w - 1) & (sv >= 0) & (sv <= h - 1)
        maps = (su.astype(np.float32), sv.astype(np.float32))
        out_lum.append(cv2.remap(lum.astype(np.float32), *maps, cv2.INTER_LINEAR, borderValue=0.0))
        z = cv2.remap(depth.astype(np.float32), *maps, cv2.INTER_NEAREST, borderValue=np.nan)
        # the point seen at p in frame t sits at X_src = z K^-1 p_src in the source camera; in frame t its
        # depth is the z of R^T X_src (frame t is the source camera rotated by R)
        ray = np.tensordot(K_inv, np.stack([su, sv, np.ones_like(su)]), axes=1)
        z_t = z * np.tensordot(R.T, ray, axes=1)[2]
        out_depth.append(np.where(valid, z_t, np.nan).astype(np.float32))
        out_valid.append(valid)
        if t + 1 < frames:
            H_next = K @ yaw(np.radians(rate_deg_s) * interval_s).T @ K_inv
            moved = np.tensordot(H_next, pixels, axes=1)
            flows.append(np.stack([moved[0] / moved[2] - u, moved[1] / moved[2] - v]).astype(np.float32))
    return {"lum": np.stack(out_lum), "depth": np.stack(out_depth), "flow_px": np.stack(flows),
            "flow_ok": np.stack(out_valid[:-1]), "valid": np.stack(out_valid)}


# ------------------------------------------------------------------------------------------ C14 static camera


def static_camera(lum: np.ndarray, depth: np.ndarray, frames: int, photons: float | None,
                  seed: int) -> dict:
    """One frame held still, with Poisson photon noise at `photons` expected per pixel at full luminance."""
    rng = np.random.default_rng(seed)
    stack = np.repeat(lum[None].astype(np.float32), frames, axis=0)
    if photons:
        stack = (rng.poisson(stack * photons) / photons).astype(np.float32).clip(0, 1)
    h, w = lum.shape
    return {"lum": stack, "depth": np.repeat(depth[None].astype(np.float32), frames, axis=0),
            "flow_px": np.zeros((frames - 1, 2, h, w), np.float32),
            "flow_ok": np.ones((frames - 1, h, w), bool)}


# ------------------------------------------------------------------------------------- C15 and C16 planes


def pink_texture(size: int, seed: int) -> np.ndarray:
    """A 1/f texture (natural-image statistics), zero mean, unit standard deviation, periodic."""
    rng = np.random.default_rng(seed)
    fx = np.fft.fftfreq(size)[:, None]
    fy = np.fft.fftfreq(size)[None, :]
    radius = np.sqrt(fx**2 + fy**2)
    radius[0, 0] = 1.0
    spectrum = (rng.normal(size=(size, size)) + 1j * rng.normal(size=(size, size))) / radius
    spectrum[0, 0] = 0
    texture = np.real(np.fft.ifft2(spectrum))
    return ((texture - texture.mean()) / texture.std()).astype(np.float32)


def textured_planes(K: np.ndarray, width: int, height: int, depths: list[float], speed_m_s: float,
                    frames: int, interval_s: float, contrast: float, seed: int,
                    texture_period_m: float = 1.0) -> dict:
    """Fronto-parallel planes, the camera translating sideways at `speed_m_s`.

    Plane 0 (the farthest) fills the view; each nearer plane is a vertical band, nearer bands narrower and
    drawn over farther ones. Texture is fixed to each plane in metres (period `texture_period_m`), mean
    luminance 0.5, RMS contrast `contrast`. Returns exact luminance, depth, flow and the figure mask (any
    plane but the farthest).
    """
    f, cx, cy = K[0, 0], K[0, 2], K[1, 2]
    order = np.argsort(depths)[::-1]              # far to near
    textures = [pink_texture(256, seed + i) for i in range(len(depths))]
    v, u = np.mgrid[0:height, 0:width].astype(np.float64)
    lum, depth, figure = [], [], []
    for t in range(frames):
        shift = speed_m_s * interval_s * t        # camera x position in metres
        frame_lum = np.zeros((height, width), np.float32)
        frame_z = np.zeros((height, width), np.float32)
        frame_fig = np.zeros((height, width), bool)
        for rank, index in enumerate(order):
            z = depths[index]
            x_world = (u - cx) / f * z + shift    # where on the plane each pixel looks, in metres
            y_world = (v - cy) / f * z
            if rank == 0:
                inside = np.ones_like(u, dtype=bool)
            else:
                # a band fixed in the world ahead of the start: 0.7 of the view's width at its depth for the
                # first near plane, halved again for each nearer one
                half = 0.35 * z / f * width / (rank + 1)
                inside = np.abs(x_world - 0.0) < half
            tex = textures[index]
            n = tex.shape[0]
            ti = (np.floor(y_world / texture_period_m * n) % n).astype(np.int64)
            tj = (np.floor(x_world / texture_period_m * n) % n).astype(np.int64)
            value = np.clip(0.5 + contrast * 0.5 * tex[ti, tj], 0.0, 1.0)
            frame_lum = np.where(inside, value, frame_lum)
            frame_z = np.where(inside, z, frame_z)
            frame_fig = np.where(inside, rank > 0, frame_fig)
        lum.append(frame_lum.astype(np.float32))
        depth.append(frame_z)
        figure.append(frame_fig)
    depth = np.stack(depth)
    # a static scene under pure translation: every pixel moves by -f dx / z horizontally (dx the camera step)
    step = speed_m_s * interval_s
    flow = np.zeros((frames - 1, 2, height, width), np.float32)
    flow[:, 0] = -f * step / depth[:-1]
    # flow is valid where the surface is still the one seen at its new position (not occluded next frame)
    ok = np.zeros((frames - 1, height, width), bool)
    for t in range(frames - 1):
        target = np.rint(u + flow[t, 0]).astype(np.int64)
        inside = (target >= 0) & (target < width)
        seen = np.full((height, width), np.nan, np.float32)
        rows = v.astype(np.int64)
        seen[inside] = depth[t + 1][rows[inside], target[inside]]
        ok[t] = inside & np.isclose(seen, depth[t])
    return {"lum": np.stack(lum), "depth": depth, "flow_px": flow, "flow_ok": ok, "figure": np.stack(figure)}
