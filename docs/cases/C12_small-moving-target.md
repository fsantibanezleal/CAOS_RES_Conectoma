# C12, small moving target

**Category** ethological. **Source** FlyGym, rendered through the fly's own right eye. **Varies** the
target's angular size, 2 to 16 degrees. **Grades** depth, figure-ground.

## Why this case

Flies see objects smaller than the angle between their ommatidia. The LC11 neurons of the lobula respond to
small dark moving objects, down to about 2 degrees, and weakly to gratings or long bars (Keles and Frye,
Current Biology 2017, doi:10.1016/j.cub.2017.01.012). FlyGym's eye puts neighbouring ommatidia 4.24 degrees
apart (measured), so a 2 degree target covers part of one column. The case asks whether a method can find a
target, and tell how far it is, as it shrinks from several columns to less than one.

## The scene

A dark sphere 20 mm from the right eye moves front to back across the eye's field at 90 degrees per second,
from a starting direction drawn per seed (30 to 60 degrees from straight ahead, 0 to 20 degrees up), over a
textured ground under a white sky. Its radius sets its angular size: $r = D \sin(\theta / 2)$ with
$D = 20$ mm, from 0.35 mm at 2 degrees to 2.8 mm at 16. Frames are 10 ms apart, 32 per clip, so the target
sweeps 28 degrees. The eye is FlyGym's, mapped onto the engine's lattice by the measured symmetry.

Eight scenes are drawn, one per seed; the six levels of a seed are the same scene and path, with only the
target's size changed.

## What it grades

Depth, as range in metres, and figure-ground, the target being the figure; the table shows how much of a
column the target fills at each size.

## Measured per level

<!-- measured: generated from data/derived/vision/cases.json by `run.py case-docs`; do not edit -->
| level | clips | frame interval (ms) | target radius (mm) | figure share | nearest depth (m) |
|---|---|---|---|---|---|
| 2.00 degrees | 8 of 8 | 10.0 | 0.349 | 0.000119 | 0.00104 |
| 4.00 degrees | 8 of 8 | 10.0 | 0.698 | 0.000463 | 0.00104 |
| 6.00 degrees | 8 of 8 | 10.0 | 1.05 | 0.00103 | 0.00104 |
| 8.00 degrees | 8 of 8 | 10.0 | 1.40 | 0.00186 | 0.00104 |
| 12.0 degrees | 8 of 8 | 10.0 | 2.09 | 0.00424 | 0.00104 |
| 16.0 degrees | 8 of 8 | 10.0 | 2.78 | 0.00762 | 0.00104 |

Medians over the clips of each level. Drawn: `20272918`, `20272919`, `20272920`, `20272921`, `20272922`, `20272923`, `20272924`, `20272925`.
<!-- /measured -->

## Caveats

- Below the ommatidial spacing, a target is a fraction of a column's light: a figure share below one half
  at every column, which a threshold at one half would never call figure.
- The target moves at a constant angular speed on a circle around the eye, so its size stays constant
  within a clip.
