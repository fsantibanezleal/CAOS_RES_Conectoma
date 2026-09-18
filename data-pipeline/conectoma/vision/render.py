"""Render fetched clips onto the lattice: one compact array file per clip, with what each column saw.

Two steps, kept apart so a case can change the physics in between. A loader (`load_*_clip`) reads a clip
archive into frames at source resolution; `lattice_clip` takes any such frames onto the lattice. Every planar
source goes through one geometry (`eye`): frames resized to 436 rows, the lattice on the central 391 x 391
pixels, the engine's box rules. Per lattice column and frame a rendering holds:
  lum          luminance in [0, 1], box mean                                   (frames, columns)
  depth        planar depth, box median; metres where the source is metric    (frames, columns)
and, where the source has them,
  flow         flow to the next frame, engine units (per image height, y up)   (frames - 1, 2, columns)
  flow_valid   share of the box whose flow the source marks valid             (frames - 1, columns)
  boundary     1 where the box holds more than one segment                    (frames, columns)
  sky          share of the box that is sky                                   (frames, columns)
  moving       share of the box in independent (non-rigid) motion             (frames - 1, columns)
  figure       share of the box that is figure (an object, not the ground)    (frames, columns)
  labelled     share of the box with a semantic label                         (frames, columns)
  semantic     the most common NYU40 label in the box (0 for none)            (frames, columns)
plus the camera poses and intrinsics where the source gives them. Depth is kept where the source gives a
finite positive value; a column whose box has none stays NaN, and the manifest counts it: masked, not dropped.
"""

from __future__ import annotations

import io
import warnings
import zipfile
from pathlib import Path

import cv2
import h5py
import numpy as np
from conectoma.vision import decode, eye

RENDER_VERSION = 2   # 2: every source through the engine's Sintel geometry (436 rows); 1 rendered at 640 rows

SPRING_BASELINE_M = 0.065  # the dataset paper and the authors' own spring_utils.get_depth
TARTANAIR_DEPTH_SATURATED = 65504.0   # float16's largest value: depth beyond TartanAir's range

# Arrays of a source clip that are images (frames or steps, then rows and columns), and so are cropped with
# the frame; everything else in a source clip is carried through to the rendering unchanged.
IMAGE_KEYS = ("lum", "depth", "flow_px", "flow_ok", "labels", "sky", "moving", "figure", "labelled",
              "semantic")
CARRIED = ("frames", "poses", "intrinsics", "strip")


def _luminance(bgr: np.ndarray) -> np.ndarray:
    b, g, r = (bgr[..., i].astype(np.float32) for i in range(3))
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255.0


def _nan_median(depth: np.ndarray, extent: int) -> np.ndarray:
    """Box median ignoring masked (NaN) pixels; identical to the plain median where none are masked."""
    boxes = eye._boxes(depth, extent, eye.KERNEL, "reflect")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)  # an all-NaN box is the case being kept
        return np.nanmedian(boxes, axis=-1).astype(np.float32)


def _box_mode(labels: np.ndarray, extent: int) -> np.ndarray:
    """The most common label in each column's box (ties to the smallest label)."""
    boxes = eye._boxes(labels, extent, eye.KERNEL, "reflect")
    flat = boxes.reshape(-1, boxes.shape[-1])
    modes = np.array([np.bincount(row).argmax() for row in flat.astype(np.int64)], dtype=np.int16)
    return modes.reshape(boxes.shape[:-1])


def _share(mask: np.ndarray, extent: int) -> np.ndarray:
    return eye.box_share(eye.resize_rows(mask.astype(np.uint8), nearest=True) > 0, extent)


def to_lattice(lum: np.ndarray, depth: np.ndarray, extent: int = eye.EXTENT, *,
               flow_px: np.ndarray | None = None, flow_ok: np.ndarray | None = None,
               labels: np.ndarray | None = None, sky: np.ndarray | None = None,
               moving: np.ndarray | None = None, figure: np.ndarray | None = None,
               labelled: np.ndarray | None = None, semantic: np.ndarray | None = None) -> dict:
    """Frames at source resolution (frames, H, W) to lattice arrays, through the one geometry."""
    height = lum.shape[-2]
    depth = np.where(np.isfinite(depth) & (depth > 0), depth, np.nan).astype(np.float32)
    out = {
        "lum": eye.box_mean(eye.resize_rows(lum), extent),
        "depth": _nan_median(eye.resize_rows(depth, nearest=True), extent),
    }
    if flow_px is not None:
        # engine units first (per source image height), so resizing the field leaves its values unchanged
        flow = eye.resize_rows(eye.engine_flow(flow_px, height))
        out["flow"] = np.stack([eye.box_sum(flow[:, c], extent) for c in (0, 1)], axis=1)
        out["flow_valid"] = _share(flow_ok, extent)
    if labels is not None:
        distinct = eye.box_distinct(eye.resize_rows(labels, nearest=True), extent)
        out["boundary"] = (distinct > 1).astype(np.uint8)
    for key, mask in (("sky", sky), ("moving", moving), ("figure", figure), ("labelled", labelled)):
        if mask is not None:
            out[key] = _share(mask, extent)
    if semantic is not None:
        out["semantic"] = _box_mode(eye.resize_rows(semantic.astype(np.int32), nearest=True), extent)
    return out


def lattice_clip(source: dict, extent: int = eye.EXTENT) -> dict:
    """A source clip (frames at source resolution, as a loader returns them) onto the lattice."""
    out = to_lattice(source["lum"], source["depth"], extent,
                     **{k: source[k] for k in IMAGE_KEYS[2:] if k in source})
    out.update({k: source[k] for k in CARRIED if k in source})
    return out


def crop_centre(source: dict, fraction: float) -> dict:
    """The central `fraction` of every image of a source clip, in both directions (the aspect is kept).

    The lattice then spans a narrower view: each column sees a smaller angle, as with a longer lens. Flow in
    pixels is unchanged by a crop; the lattice converts it per image height, which the crop shrinks.
    """
    if not 0 < fraction <= 1:
        raise ValueError(f"crop fraction {fraction} outside (0, 1]")
    h, w = source["lum"].shape[-2:]
    ch, cw = max(1, round(h * fraction)), max(1, round(w * fraction))
    top, left = (h - ch) // 2, (w - cw) // 2
    out = dict(source)
    for key in IMAGE_KEYS:
        if key in source:
            out[key] = source[key][..., top: top + ch, left: left + cw]
    return out


def _decode(archive: zipfile.ZipFile, name: str, flags: int, where: Path) -> np.ndarray:
    image = cv2.imdecode(np.frombuffer(archive.read(name), dtype=np.uint8), flags)
    if image is None:
        raise ValueError(f"{where}:{name}: not a readable image")
    return image


def _consecutive(names: list[str], number) -> list[int]:
    ids = [number(n) for n in names]
    if ids != list(range(ids[0], ids[0] + len(ids))):
        raise ValueError(f"frames are not consecutive: {ids[:3]}...")
    return ids


# ------------------------------------------------------------------------------------------------ TartanAir


def load_tartanair_clip(path: Path) -> dict:
    """One TartanAir clip archive at source resolution (640 x 640, front camera).

    TartanAir's depth has float16 precision, and float16's largest value (65504) marks depth beyond its
    range: the sky of an open scene (47 percent of a BrushifyMoon frame, measured). That depth is masked
    (NaN), as Spring's sky is. A sky modelled as a dome at a finite distance (3 to 57 km in the environments
    measured) keeps its value; depth metrics cap their range.
    """
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        images = sorted(n for n in names if n.endswith("_lcam_front.png"))
        depths = sorted(n for n in names if n.endswith("_lcam_front_depth.png"))
        segs = sorted(n for n in names if n.endswith("_lcam_front_seg.png"))
        flows = sorted(n for n in names if n.endswith("_flow.png"))
        pose_name = next(n for n in names if n.endswith("pose_lcam_front.txt"))
        if not (len(images) == len(depths) == len(segs) == len(flows) + 1):
            raise ValueError(f"{path}: {len(images)} images, {len(depths)} depths, {len(segs)} segs, "
                             f"{len(flows)} flows")
        lum = np.stack([_luminance(_decode(archive, n, cv2.IMREAD_COLOR, path)) for n in images])
        depth = np.stack([np.ascontiguousarray(_decode(archive, n, cv2.IMREAD_UNCHANGED, path))
                          .view("<f4")[..., 0] for n in depths])
        seg = np.stack([_decode(archive, n, cv2.IMREAD_UNCHANGED, path) for n in segs])
        seg = seg if seg.ndim == 3 else seg[..., 0]
        raw = [_decode(archive, n, cv2.IMREAD_UNCHANGED, path) for n in flows]
        poses = np.loadtxt(io.StringIO(archive.read(pose_name).decode("utf-8")), dtype=np.float64)
    if any(r.dtype != np.uint16 or r.ndim != 3 for r in raw):
        raise ValueError(f"{path}: flow is not a 16-bit three-channel PNG")
    flow_px = np.stack([np.moveaxis((r[..., :2].astype(np.float32) - decode.FLOW_OFFSET) / decode.FLOW_SCALE,
                                    -1, 0) for r in raw])
    frames = _consecutive(images, lambda n: int(Path(n).name[:6]))
    depth = np.where(depth >= TARTANAIR_DEPTH_SATURATED, np.nan, depth).astype(np.float32)
    return {"lum": lum, "depth": depth, "flow_px": flow_px,
            "flow_ok": np.stack([r[..., 2] == 0 for r in raw]),
            "labels": seg, "poses": poses[frames[0]: frames[0] + len(frames)],
            "frames": np.array(frames, dtype=np.int32)}


def render_tartanair_clip(path: Path, extent: int = eye.EXTENT) -> dict:
    """The lattice rendering of one TartanAir clip archive."""
    return lattice_clip(load_tartanair_clip(path), extent)


# ------------------------------------------------------------------------------------------------ Spring


def spring_depth(disparity: np.ndarray, fx: float, baseline: float = SPRING_BASELINE_M) -> np.ndarray:
    """Metric depth from Spring's reference-frame disparity, as the authors compute it (`get_depth`): the
    super-resolved disparity (2160 x 3840) is taken at every second pixel, in pixels of the 1920 x 1080 frame.
    """
    d = disparity[::2, ::2].astype(np.float32)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(np.isfinite(d) & (d > 0), fx * baseline / d, np.nan).astype(np.float32)


def load_spring_clip(path: Path) -> dict:
    """One Spring clip archive (left camera) at source resolution (1920 x 1080)."""
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        images = sorted(n for n in names if "/frame_left/" in n)
        disps = sorted(n for n in names if "/disp1_left/" in n)
        skies = sorted(n for n in names if "/skymap_left/" in n)
        rigid = sorted(n for n in names if "/rigidmap_FW_left/" in n)
        intrinsics_name = next(n for n in names if n.endswith("intrinsics.txt"))
        intrinsics = np.loadtxt(io.StringIO(archive.read(intrinsics_name).decode("utf-8")),
                                dtype=np.float64, ndmin=2)
        if not (len(images) == len(disps) == len(skies) and len(rigid) == len(images) - 1):
            raise ValueError(f"{path}: {len(images)} frames, {len(disps)} disparities, "
                             f"{len(skies)} sky maps, {len(rigid)} motion maps")
        frames = _consecutive(images, lambda n: int(Path(n).stem.rsplit("_", 1)[1]))
        lum = np.stack([_luminance(_decode(archive, n, cv2.IMREAD_COLOR, path)) for n in images])
        depth = []
        for n, frame in zip(disps, frames, strict=True):
            with h5py.File(io.BytesIO(archive.read(n)), "r") as handle:
                depth.append(spring_depth(handle["disparity"][()], intrinsics[frame - 1, 0]))
        sky = np.stack([_decode(archive, n, cv2.IMREAD_UNCHANGED, path)[::2, ::2] > 0 for n in skies])
        moving = np.stack([_decode(archive, n, cv2.IMREAD_UNCHANGED, path)[::2, ::2] > 0 for n in rigid])
    return {"lum": lum, "depth": np.stack(depth), "sky": sky, "moving": moving,
            "frames": np.array(frames, dtype=np.int32), "intrinsics": intrinsics[frames[0] - 1: frames[-1]]}


def render_spring_clip(path: Path, extent: int = eye.EXTENT) -> dict:
    """The lattice rendering of one Spring clip archive (left camera)."""
    return lattice_clip(load_spring_clip(path), extent)


# ------------------------------------------------------------------------------------------------ Hypersim

# The room shell counts as ground; every labelled instance of any other NYU40 class is figure. The ids are
# Hypersim's own table (code/cpp/tools/scene_annotation_tool/semantic_label_descs.csv).
HYPERSIM_GROUND = {1: "wall", 2: "floor", 8: "door", 9: "window", 20: "floormat", 22: "ceiling",
                   38: "otherstructure"}


def load_hypersim_clip(path: Path, camera: dict) -> dict:
    """One Hypersim scene archive at source resolution (1024 x 768): single images, not a video."""
    from conectoma.vision.hypersim import planar_factor

    factor = planar_factor(camera)
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        colors = sorted(n for n in names if n.endswith(".color.jpg"))
        frames = [int(Path(n).name.split(".")[1]) for n in colors]

        def hdf5(frame: int, kind: str) -> np.ndarray:
            name = next(n for n in names if n.endswith(f"frame.{frame:04d}.{kind}.hdf5"))
            with h5py.File(io.BytesIO(archive.read(name)), "r") as handle:
                return handle["dataset"][()]

        lum = np.stack([_luminance(_decode(archive, n, cv2.IMREAD_COLOR, path)) for n in colors])
        depth = np.stack([hdf5(f, "depth_meters").astype(np.float32) * factor for f in frames])
        semantic = np.stack([hdf5(f, "semantic") for f in frames]).astype(np.int32)
        instance = np.stack([hdf5(f, "semantic_instance") for f in frames]).astype(np.int32)
    labelled = semantic > 0
    ground = np.isin(semantic, list(HYPERSIM_GROUND))
    return {"lum": lum, "depth": depth, "labels": (instance + 1).astype(np.int32),
            "figure": labelled & ~ground & (instance >= 0), "labelled": labelled,
            "semantic": np.where(labelled, semantic, 0).astype(np.int32),
            "frames": np.array(frames, dtype=np.int32)}


def render_hypersim_clip(path: Path, camera: dict, extent: int = eye.EXTENT) -> dict:
    """The lattice rendering of one Hypersim scene archive."""
    return lattice_clip(load_hypersim_clip(path, camera), extent)
