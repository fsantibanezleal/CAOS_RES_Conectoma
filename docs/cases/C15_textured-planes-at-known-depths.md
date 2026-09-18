# C15, textured planes at known depths

**Category** positive control. **Source** synthetic, computed here. **Varies** the nearest plane's depth,
0.5 to 16 m. **Grades** depth, flow, figure-ground.

## Why this case

Every other case's ground truth was rendered or measured by someone else. This one is computed: flat,
textured planes facing the camera, the camera sliding sideways past them, so depth, flow and figure are known
exactly at every pixel. It is the case where a method's error cannot be blamed on the data. It also isolates
the scale of depth from motion: the same scene at twice the depth moves half as fast in the image, so a
method that only sees image motion confuses depth with speed, and a method told its speed should not.

## The scene

Three fronto-parallel planes at depths $d$, $2d$ and $4d$. The farthest fills the view; each nearer plane is a
set of vertical bands drawn over the farther ones, repeating with the view's width at its depth so that bands
stay in view however fast they pass (0.35 of that width for the middle plane, half as wide for the nearest).
Each plane carries a 1/f texture of RMS contrast 0.35 around a mean of 0.5, whose period is proportional to
the plane's depth, so every plane shows the same angular texture scale and texture size is no cue to depth.
The camera (TartanAir's front lens, 640 x 640, 90 degree field) translates sideways at 1 m/s, 32 frames at
10 Hz.

A pixel at depth $z$ moves by

$$\Delta u = -\frac{f\,\Delta x}{z},\qquad \Delta v = 0,$$

with $f = 320$ px and $\Delta x = 0.1$ m per frame: 64 pixels per frame at 0.5 m, 2 at 16 m. Flow is valid where
the surface a pixel sees is still the one it lands on in the next frame, not occluded by a nearer band.

Eight scenes per level, one per seed (the textures), the same seeds at every level.

## What it grades

Depth (exact), flow (exact) and figure-ground, the nearer planes being the figure against the farthest.

## Measured per level

<!-- measured: generated from data/derived/vision/cases.json by `run.py case-docs`; do not edit -->
<!-- /measured -->

## Caveats

- The texture is sampled at the nearest texel; flow constancy holds to a mean absolute luminance error below
  0.02 on valid pixels (a test).
- Planes are fronto-parallel: there is no slant, so depth within a plane is constant.
