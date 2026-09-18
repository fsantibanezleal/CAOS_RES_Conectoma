# C10, gap crossing

**Category** ethological. **Source** FlyGym, rendered through the fly's own right eye. **Varies** the width
of the gap, 1 to 6 mm. **Grades** depth, figure-ground.

## Why this case

Flies judge whether a gap can be crossed before they climb it, and they judge its width from motion
parallax: they "chiefly use the vertical edges on the targeted side to distill the gap width from the
parallax motion generated during the approach" (Pick and Strauss, Current Biology 2005,
doi:10.1016/j.cub.2005.07.022). That is depth from motion in the fly's own task, at the fly's own scale and
with the fly's own optics. The case asks whether a method reads the distance to the far side from the
parallax of its edges, as the fly does, across gaps from 1 to 6 mm.

## The scene

Two catwalks 6 mm wide, their surfaces at the same height, with a gap between them over a pit 10 mm deep;
every surface carries a 1/f texture drawn from the scene's seed. The far catwalk's sides are the vertical
edges on the targeted side. NeuroMechFly walks along the near catwalk toward the gap at 20 mm/s with its right
eye 1 mm above the surface, starting 8.2 mm before the near edge and walking 6.2 mm, on a heading drawn up to
15 degrees off the catwalk's axis (the fly is held as a mocap body and moved along the path exactly; no
physics is simulated). Frames are 10 ms apart, 32 per clip, rendered through FlyGym's eye: its camera, its
fisheye, its 721 ommatidia, mapped onto the engine's lattice by the measured symmetry.

Eight scenes are drawn, one per seed; the six levels of a seed are the same scene with the far catwalk
moved, so they differ only in the gap.

## What it grades

Depth, as range along each ommatidium's pixels (a compound eye has no image plane), in metres; and
figure-ground, the far catwalk being the figure, as the surface the fly would have to reach. The near edge
hides the pit, so the far side's wall fills the view below its edge: its apparent size changes with the gap
less than its depth does, which is the point of the case.

## Measured per level

<!-- measured: generated from data/derived/vision/cases.json by `run.py case-docs`; do not edit -->
<!-- /measured -->

## Caveats

- The scene's geometry (catwalk width, pit depth, walking speed, eye height) is a design of this case, not a
  reproduction of the published assay's apparatus.
- The fly's body is left out of the eye's render; a walking fly sees its own legs in its lower field.
- The light is MuJoCo's headlight, along the eye's axis; the fly only translates within a clip, so every
  surface keeps its shading from frame to frame.
