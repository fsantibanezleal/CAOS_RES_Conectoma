# C16, textureless surfaces

**Category** boundary. **Source** synthetic, computed here. **Varies** texture contrast, from 0.5 down to 0.
**Grades** depth, flow, figure-ground.

## Why this case

Motion can only be seen where the image has structure. A surface without texture moves without changing a
single pixel's brightness, so its motion is invisible (the aperture problem, in its extreme form), while its
depth is as defined as ever. The case fades the texture of the scene of [C15](C15_textured-planes-at-known-depths.md)
from clearly visible to nothing, and asks how a method's depth and flow degrade as the evidence disappears,
and whether its uncertainty rises as they do. At zero contrast the image is uniform grey: nothing can be
seen, and any structure a method reports comes from its prior.

## The scene

The planes of C15 at fixed depths of 2, 4 and 8 m, the camera sliding sideways at 1 m/s, 32 frames at 10 Hz.
Only the texture's RMS contrast changes: 0.5, 0.2, 0.1, 0.05, 0.02 and 0, around a mean luminance of 0.5.
Depth, flow and figure are exact and identical at every level; the boundaries between planes vanish with the
texture, since the planes differ only in texture.

Eight scenes per level, one per seed, the same seeds at every level.

## What it grades

Depth, flow and figure-ground, all exact; the calibration of uncertainty as contrast falls.

## Measured per level

<!-- measured: generated from data/derived/vision/cases.json by `run.py case-docs`; do not edit -->
<!-- /measured -->

## Caveats

- The lattice's box mean averages texture within each column, so the contrast a column sees is lower than
  the texture's own (the table's RMS contrast is measured on the lattice).
