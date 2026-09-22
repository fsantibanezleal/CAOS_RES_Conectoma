# OpenCV

## What it is

OpenCV is the open computer vision library (github.com/opencv/opencv). The product installs the headless
Python build, `opencv-python-headless` 5.0.0.93 (Apache-2.0 per its package metadata), pinned in
`data-pipeline/requirements.txt`. Headless means no GUI modules, which the pipeline never uses.

## Why it is used

Two reasons, one of correctness and one of speed.

1. **Decoding TartanAir as its reference reader does.** TartanAir V2 packs float32 depth into the four 8-bit
   channels of a PNG and 16-bit flow with its validity mask into three channels. The dataset's own reader
   (tartanairpy) decodes them with OpenCV, whose channel order is blue, green, red. A PIL decode returns red,
   green, blue: the depth bytes come out in another order, and the flow comes out swapped with its mask.
   Decoding with OpenCV is decoding the file as its authors wrote it; the reprojection check (flow recomputed
   from depth and poses against the released flow, median error 0.08 pixels) confirms it.
2. **Resampling and warping at the speed the corpus needs.** Every planar frame is resized to 436 rows
   before the lattice (area averaging for images, `INTER_NEAREST_EXACT` for depth and labels). Measured,
   rendering one TartanAir clip took 12 seconds with torchvision's resize and 3 to 4 seconds with OpenCV's,
   over a corpus of thousands of clips. `cv2.remap` renders the pure-rotation frames from the panoramas, the
   motion blur along each pixel's own flow, and the checks of flow constancy in the tests.

## How it is used here

| Where | What |
|---|---|
| `vision/decode.py`, `vision/render.py` | `imdecode` of TartanAir, Spring and Hypersim images, depth and flow |
| `vision/eye.py` | `resize` to 436 rows (`INTER_AREA`; `INTER_NEAREST_EXACT` for depth and labels) |
| `vision/panorama.py` | `remap` of the panorama through a rotating pinhole camera (`BORDER_WRAP` across longitude) |
| `vision/variants.py` | `remap` along each pixel's motion for exposure blur |
| `vision/sintel.py` | `imread` of Sintel's frames and masks (luminance then computed with PIL's integer luma) |

## Caveats

- Maps passed to `remap` must be float32; float64 coordinates are refused (a blur test caught one before any
  case used it).
- Sintel's luminance is not OpenCV's: the engine converts Sintel through PIL's integer luma, so the product
  reads Sintel's pixels with OpenCV and converts them with PIL's exact formula, to feed the published model
  what it was trained on.
