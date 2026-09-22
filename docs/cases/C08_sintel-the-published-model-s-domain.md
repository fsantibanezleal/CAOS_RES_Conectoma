# C08, Sintel, the published model's domain

**Category** transfer. **Source** MPI Sintel, the six sequences the published models held out. **Varies**
contrast, from the original down to 0.15 of it. **Grades** relative depth, flow.

## Why this case

The published connectome-constrained models (Lappalainen et al., Nature 2024,
doi:10.1038/s41586-024-07939-3) were trained on Sintel, rendered onto the lattice by the engine. This case is
the one place where every method is measured on the domain those models know, so a gap between them and the
product's own models here is a gap in the models, not in the data. The six sequences are the ones the
engine held out for validation (`original_train_and_validation_indices`: ambush_2, bamboo_1, bandage_1,
cave_4, market_2 and mountain_1), so the published models never trained on them. Lowering contrast asks how
far the models' competence reaches below the contrast they were trained at.

## The clips

The six held-out sequences, the central 32 frames of each (all 21 of ambush_2), rendered exactly as the
engine renders Sintel: the final pass, luminance through PIL's integer luma, and the frame cut to the
engine's middle strip with the engine's own crop and split arithmetic. On two of these sequences the
product's rendering matches the engine's own to $10^{-6}$ in luminance and $10^{-4}$ in flow. Six clips per
level: the source has no more to draw.

## The variant

Luminance scaled about each frame's mean, $I' = \bar I + c\,(I - \bar I)$, clipped to $[0, 1]$, with $c$ from 1
to 0.15. Depth and flow are the recorded ones.

## What it grades

Depth up to scale (Sintel's depth is in Blender scene units, not metres) and flow in the engine's unit. Flow
is valid where Sintel marks a pixel neither occluded in the next frame nor invalid.

## Measured per level

<!-- measured: generated from data/derived/vision/cases.json by `run.py case-docs`; do not edit -->
| level | clips | frame interval (ms) | RMS contrast | column spacing (deg) | flow per frame (engine units) |
|---|---|---|---|---|---|
| 1.00 factor on contrast about the mean | 6 of 6 | 41.7 | 0.36 | 0.881 | 1.48 |
| 0.7 factor on contrast about the mean | 6 of 6 | 41.7 | 0.251 | 0.881 | 1.48 |
| 0.5 factor on contrast about the mean | 6 of 6 | 41.7 | 0.179 | 0.881 | 1.48 |
| 0.35 factor on contrast about the mean | 6 of 6 | 41.7 | 0.125 | 0.881 | 1.48 |
| 0.25 factor on contrast about the mean | 6 of 6 | 41.7 | 0.0891 | 0.881 | 1.48 |
| 0.15 factor on contrast about the mean | 6 of 6 | 41.7 | 0.0534 | 0.881 | 1.48 |

Medians over the clips of each level. Drawn: `ambush_2`, `bamboo_1`, `bandage_1`, `cave_4`, `market_2`, `mountain_1`.
<!-- /measured -->

## Caveats

- The six sequences are shot with lenses from 640 to 3200 pixels of focal length, so their columns span
  0.23 to 1.16 degrees: the finest angular sampling in the registry apart from Spring.
- The product's flow row $t$ is the motion from frame $t$ to $t + 1$; the engine labels frame $t + 1$ with
  it. The values are the same, one index apart.
