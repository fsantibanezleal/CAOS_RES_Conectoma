# C03, hospital corridor

**Category** nominal-indoor. **Source** TartanAir V2, environment Hospital (its own geometry family).
**Varies** illumination, 1 down to 1/32 of the recorded luminance. **Grades** depth, segment boundaries, flow.

## Why this case

A corridor has the longest depth range an indoor scene offers, from the wall beside the camera to the far
end, and the least texture: painted walls, floors and ceilings where motion is hard to see. Dimming it asks
whether a method's depth depends on the absolute light level. The network's photoreceptors receive
luminance itself, not a normalised image, so a method built on it may respond to a darker scene as if the
scene were different; a method whose depth changes when only the light changes has confused brightness with
structure.

## The clips

Hospital is a geometry family of one environment, always in the test split. Eight clips of 32 consecutive
frames are drawn with the registry's seed, and the same eight are rendered at every level.

## The variant

A gain on luminance at source resolution, $I' = \min(g I, 1)$, with $g$ halving from 1 to 1/32 (five stops),
and no adaptation: the image simply darkens. Nothing else changes, so depth, boundaries and flow are the
recorded ones at every level. Darkness alone adds no noise here; the photon noise that real darkness brings
is the variable of [C05](C05_city-at-night.md) and [C14](C14_static-camera.md), so the two effects can be
told apart.

## What it grades

Metric depth, segment boundaries and flow.

## Measured per level

<!-- measured: generated from data/derived/vision/cases.json by `run.py case-docs`; do not edit -->
| level | clips | frame interval (ms) | mean luminance | luminance SD | median depth (m) |
|---|---|---|---|---|---|
| 1.00 relative illuminance | 8 of 8 | 100 | 0.394 | 0.225 | 2.35 |
| 0.5 relative illuminance | 8 of 8 | 100 | 0.197 | 0.112 | 2.35 |
| 0.25 relative illuminance | 8 of 8 | 100 | 0.0986 | 0.0562 | 2.35 |
| 0.125 relative illuminance | 8 of 8 | 100 | 0.0493 | 0.0281 | 2.35 |
| 0.0625 relative illuminance | 8 of 8 | 100 | 0.0247 | 0.014 | 2.35 |
| 0.0312 relative illuminance | 8 of 8 | 100 | 0.0123 | 0.00702 | 2.35 |

Medians over the clips of each level. Drawn: `Hospital/hard/P004/000250`, `Hospital/hard/P002/000269`, `Hospital/hard/P009/000206`, `Hospital/hard/P010/000176`, `Hospital/hard/P003/001208`, `Hospital/hard/P010/000562`, `Hospital/hard/P000/000325`, `Hospital/easy/P004/000378`.
<!-- /measured -->

## Caveats

- The gain is applied before the lattice, so the box mean of a column scales exactly with it (luminance
  below saturation); the table's mean luminance shows it.
- The case holds contrast ratios fixed while lowering the level; a sensor with a noise floor would lose
  contrast too, which is what C05 adds.
