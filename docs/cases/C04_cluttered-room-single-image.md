# C04, cluttered room, single image

**Category** nominal-indoor. **Source** Hypersim, official test partition. **Varies** the vertical field of
view, from each scene's full field (45 to 47 degrees) down to 12 degrees. **Grades** depth, segment
boundaries, figure-ground, semantic labels.

## Why this case

Everything else in the registry moves; this case does not. A single image carries no parallax, so depth has
to come from what the image looks like: perspective, occlusion, familiar sizes. That is the non-native
condition for a system built around motion, and the case measures how much of its depth survives without
it. Hypersim is also the one source with object instances and NYU40 semantic labels, so it is where
figure-ground and semantics are graded on real indoor clutter. Narrowing the field of view asks the second
question of the lattice's geometry: at the full field each column spans 1.43 degrees, and cropping makes each
column see a smaller angle, as a longer lens would, down to 0.36 degrees.

## The clips

Hypersim's own scene-level split is respected: only its test partition is used, camera cam_00, every fifth
frame. Its semantic labels are incomplete in some test scenes (20 of the 46 have less than 90 percent of the
lattice view labelled, and one volume is large open spaces with no objects at all), so the case draws only
scenes whose labelled share is at least 0.9 and whose figure share is at least 0.1: rooms that are both
annotated and cluttered. Eight such scenes are drawn with the registry's seed, spread over Hypersim's
volumes, and each scene's images are its clip.

## The variant

A central crop whose vertical field is the level. Hypersim's cameras are tilt-shifted, so the crop is solved
from each scene's own rays ($d = M_{\text{cam from uv}}[u, v, 1]^\top$): the fraction $c$ of the image such
that the rays through $(0, \pm c)$ subtend the stated angle, found by bisection. The crop keeps the aspect,
and every target is cropped with the image. Planar depth was already computed from the scene's rays before
the crop.

## What it grades

Metric depth (planar, from Hypersim's Euclidean distance), segment boundaries (instances), figure-ground (the
room shell, meaning wall, floor, door, window, floormat, ceiling and other structure, is ground; every other
labelled instance is figure) and the NYU40 label of each column.

## Measured per level

<!-- measured: generated from data/derived/vision/cases.json by `run.py case-docs`; do not edit -->
| level | clips | frame interval (ms) | vertical field (deg) | column spacing (deg) | figure share | median depth (m) |
|---|---|---|---|---|---|---|
| full | 8 of 8 | n/a (single images) | 46.8 | 1.48 | 0.362 | 6.01 |
| 40.0 degrees (vertical) | 8 of 8 | n/a (single images) | 40.0 | 1.24 | 0.38 | 6.29 |
| 32.0 degrees (vertical) | 8 of 8 | n/a (single images) | 32.0 | 0.98 | 0.392 | 6.69 |
| 24.0 degrees (vertical) | 8 of 8 | n/a (single images) | 24.0 | 0.726 | 0.403 | 7.36 |
| 18.0 degrees (vertical) | 8 of 8 | n/a (single images) | 18.0 | 0.541 | 0.399 | 7.63 |
| 12.0 degrees (vertical) | 8 of 8 | n/a (single images) | 12.0 | 0.359 | 0.382 | 7.95 |

Medians over the clips of each level. Drawn: `ai_053_010`, `ai_051_001`, `ai_037_009`, `ai_030_001`, `ai_054_007`, `ai_008_007`, `ai_048_008`, `ai_023_005`.
<!-- /measured -->

## Caveats

- Hypersim is CC BY-SA 3.0: anything derived from it that the site publishes is ShareAlike.
- Single images have no frame interval; they are not a video, and their frame numbers are ids.
- The requirement on labels selects annotated scenes, which is the point; it is declared in the registry
  and applies to this case only.
- A narrow crop can land on a surface with no structure at all (a lit wall, a blown-out window), and that
  image shows nothing. These are single images, not a video, so such an image is dropped from every level of
  its scene, which keeps all six levels on the same images; the table records how many were dropped.
