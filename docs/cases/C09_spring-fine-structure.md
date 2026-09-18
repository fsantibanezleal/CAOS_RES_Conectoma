# C09, Spring, fine structure

**Category** transfer. **Source** Spring, the training split's left camera. **Varies** sampling, the frame
resampled from 436 up to its native 1080 rows before the lattice. **Grades** depth, sky.

## Why this case

Spring renders Blender's film "Spring" in high detail: hair, grass, thin branches, the fine structure that a
coarse sampling averages away. It gives metric depth through its stereo disparity. Resampling the frame to
more rows before the lattice makes each column see a smaller angle, so the case asks how much a method's depth
improves when the eye resolves finer structure: across Spring's shots, from 0.30 to 1.43 degrees per column
on the whole frame down to 0.12 to 0.58 at native resolution. Together with
[C04](C04_cluttered-room-single-image.md) it measures the geometry of the lattice rather than the scene.

## The clips

Spring's train split has 34 scenes; two clips of 32 consecutive frames are taken per scene where it is long
enough (67 clips). Eight are drawn with the registry's seed, spread over scenes, and the same eight are
rendered at every level.

## The variant

Resampling the 1080-row frame to $R$ rows and taking the central 436 rows is a central crop of $436 / R$ of the
frame, resized to 436 rows: from the whole frame at $R = 436$ to a crop at native resolution at $R = 1080$,
never upsampled. The focal length at 436 rows is $f_y R / 1080$, and the angle between neighbouring columns at
the centre is $2 \arctan(6.5 / (f_y R / 1080))$.

Depth is metric: $f_x B / d$ over the super-resolved disparity sampled at every second pixel, with the
stereo baseline $B = 0.065$ m (the dataset paper and the authors' own `get_depth`). Zero disparity, the sky, is
masked.

## What it grades

Metric depth and the sky share of each column. Spring's rigidity map, which marks pixels in independent
motion, is carried with each clip; it is sparse and is not graded here.

## Measured per level

<!-- measured: generated from data/derived/vision/cases.json by `run.py case-docs`; do not edit -->
<!-- /measured -->

## Caveats

- Spring's frame rate is not stated in its paper, on its benchmark site, in the RobustSpring paper, in the
  authors' utilities or on the film's page; no Spring clip carries a frame interval until a primary source
  states one.
- The film's lenses vary by shot, from 1,293 to 6,061 pixels of focal length at 1080 rows (median 2,182,
  over all 9,830 frames fetched), so the column spacing of a level depends on the clip; the table gives the
  median over the clips drawn.
