# C11, looming object

**Category** ethological. **Source** FlyGym, rendered through the fly's own right eye. **Varies** the
approach, as l/v from 10 to 320 ms. **Grades** depth, figure-ground.

## Why this case

An object on a collision course expands on the eye at an accelerating rate, and flies escape it. The LPLC2
neurons of the lobula plate detect it by radial motion opponency, responding to motion outward in all
directions at once (Klapoetke et al., Nature 2017, doi:10.1038/nature24626). An approach is fully described
by one time constant, the object's half size over its speed, $l/v$: small $l/v$ is a fast approach that
explodes on the eye at the end, large $l/v$ a slow one that grows steadily. The case asks whether a method
tracks the object's distance as it approaches, and separates it from its background, across that range.

## The scene

A dark disk of radius $l = 2$ mm approaches the right eye head-on at constant speed $v$, its face always
toward the eye, from a direction drawn per seed within the right eye's field (40 to 110 degrees from straight
ahead, 30 to 60 degrees up), over a textured ground under a white sky. With $t_c$ the time of contact, the
disk's angular size is

$$\theta(t) = 2 \arctan\frac{l}{v\,(t_c - t)},$$

and each clip ends when it subtends 90 degrees, $t_c - t = l / v$. Frames are 10 ms apart, 32 per clip, so a
fast approach ($l/v = 10$ ms, $v = 200$ mm/s) spends most of the clip small and then fills the view, and a slow
one ($l/v = 320$ ms, $v = 6.25$ mm/s) is already large and grows steadily. The eye is FlyGym's, mapped onto the
engine's lattice by the measured symmetry.

Eight scenes are drawn, one per seed; the six levels of a seed are the same scene and direction, with only the
speed changed.

## What it grades

Depth, as range in metres, and figure-ground, the disk being the figure.

## Measured per level

<!-- measured: generated from data/derived/vision/cases.json by `run.py case-docs`; do not edit -->
| level | clips | frame interval (ms) | approach speed (mm/s) | angular size, first to last frame (deg) | figure share | nearest depth (m) |
|---|---|---|---|---|---|---|
| 10.0 l/v in ms | 8 of 8 | 10.0 | 200 | 3.58 to 90.0 | 0.0223 | 0.00104 |
| 20.0 l/v in ms | 8 of 8 | 10.0 | 100 | 6.94 to 90.0 | 0.0372 | 0.00104 |
| 40.0 l/v in ms | 8 of 8 | 10.0 | 50.0 | 13.0 to 90.0 | 0.0644 | 0.00104 |
| 80.0 l/v in ms | 8 of 8 | 10.0 | 25.0 | 23.2 to 90.0 | 0.108 | 0.00104 |
| 160 l/v in ms | 8 of 8 | 10.0 | 12.5 | 37.6 to 90.0 | 0.165 | 0.00104 |
| 320 l/v in ms | 8 of 8 | 10.0 | 6.25 | 53.9 to 90.0 | 0.228 | 0.00104 |

Medians over the clips of each level. Drawn: `20271918`, `20271919`, `20271920`, `20271921`, `20271922`, `20271923`, `20271924`, `20271925`.
<!-- /measured -->

## Caveats

- The disk is a thin cylinder facing the eye, so its angular size follows the $l/v$ law exactly; a sphere
  would differ at large angles.
- The sky is empty (no depth): columns that see only sky are masked in the depth target.
