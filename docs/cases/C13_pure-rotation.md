# C13, pure rotation

**Category** negative control. **Source** TartanAir V2 panoramas, family BrushifyMoon. **Varies** the
rotation rate, 0 to 240 degrees per second. **Grades** flow, uncertainty.

## Why this case

A camera that turns about its own optical centre sees no parallax. Every scene point moves by the same
homography,

$$p' = K\,R\,K^{-1} p,$$

whatever its depth, so the images carry no information about depth at all: depth from motion is unobservable
by construction. A method that reports a confident depth map here is reporting a prior, what scenes usually
look like, not a measurement. The case is graded on flow, which is exactly defined, and on whether a method's
uncertainty rises where depth cannot be known. Level 0 does not move at all, which is unobservable too.

## The clips

Eight clips of the BrushifyMoon family (in the test split), drawn with the case's seed. For each, TartanAir's
panorama at the clip's first pose (a 2048 x 1024 equirectangular image with its range) is fetched, and a
camera with TartanAir's front lens (640 x 640, 90 degree field) turns right in place for 32 frames at 10 Hz.
Rendering a single ordinary frame through the homography would run out of image after a quarter turn; the
panorama covers every direction, so the camera can turn for the whole clip at any rate, up to 768 degrees at
240 degrees per second, and every frame is real imagery.

## The variant

The rotation rate $\omega$, with a turn of $\omega \Delta t$ per frame. The flow is exact: pixel $p$ of frame
$t$ is at $K\,Y(\omega \Delta t)^\top K^{-1} p$ in frame $t + 1$, with $Y$ the yaw of one step, and it is
valid where that point is still in front of the camera and inside the image. Depth is carried along: the
panorama's range, made planar for the rotated camera.

Measured on the source, the panorama's conventions (longitude +90 degrees for the front camera, range rather
than planar depth) reproduce the front camera's own depth to 0.16 percent; warped by the exact flow,
consecutive frames agree to a mean absolute error of 0.008.

## What it grades

Flow, and the calibration of a method's uncertainty on depth: high uncertainty is the correct answer.

## Measured per level

<!-- measured: generated from data/derived/vision/cases.json by `run.py case-docs`; do not edit -->
| level | clips | frame interval (ms) | turn per frame (deg) | flow per frame (engine units) | median depth (m) |
|---|---|---|---|---|---|
| 0 deg/s | 8 of 8 | 100 | 0 | 0 | 9.38 |
| 15.0 deg/s | 8 of 8 | 100 | 1.50 | 2.57 | 10.3 |
| 30.0 deg/s | 8 of 8 | 100 | 3.00 | 5.13 | 11.1 |
| 60.0 deg/s | 8 of 8 | 100 | 6.00 | 10.1 | 9.24 |
| 120 deg/s | 8 of 8 | 100 | 12.0 | 20.0 | 8.98 |
| 240 deg/s | 8 of 8 | 100 | 24.0 | 39.2 | 8.99 |

Medians over the clips of each level. Drawn: `BrushifyMoon/hard/P004/002991`, `BrushifyMoon/hard/P004/000986`, `BrushifyMoon/easy/P005/000577`, `BrushifyMoon/hard/P003/002170`, `BrushifyMoon/hard/P005/000280`, `BrushifyMoon/hard/P003/000713`, `BrushifyMoon/hard/P001/000643`, `BrushifyMoon/easy/P004/001833`.
<!-- /measured -->

## Caveats

- BrushifyMoon's sky is beyond TartanAir's depth range and is masked (47 percent of a frame measured); the
  flow there is exact all the same, since rotational flow does not depend on depth.
- The panorama is one pose: the rotation is about that pose's centre, with nothing in the scene moving.
