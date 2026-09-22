# FlyGym and MuJoCo

## What it is

FlyGym is the simulation framework of NeuroMechFly v2, a biomechanical model of the adult fruit fly with a
compound eye, built on the MuJoCo physics engine: Wang-Chen, Stimpfling, Lam, Özdil, Genoud, Hurtak and
Ramdya, "NeuroMechFly v2: simulating embodied sensorimotor control in adult Drosophila", Nature Methods,
2024, doi:10.1038/s41592-024-02497-y (preprint doi:10.1101/2023.09.18.556649).

- Repository: github.com/NeLy-EPFL/flygym; the package metadata states Apache-2.0.
- Distribution: `flygym` 2.1.0 on the Python package index, which requires `mujoco` 3.9 (Apache-2.0,
  github.com/google-deepmind/mujoco).
- Pinned in `data-pipeline/requirements.txt` (`flygym==2.1.0`; MuJoCo comes with it at 3.9.0).

## Why it is used

The ethological cases (C10 gap crossing, C11 looming, C12 small target) are defined by what a fly sees: the
angle an edge subtends, how fast a disk expands on the eye, how many ommatidia a target covers. Rendering
them through a planar camera would sample the world at the wrong angular spacing (0.2 to 3.4 degrees per
column for the planar sources, against 4.24 degrees between the ommatidia of FlyGym's eye, measured) and
with the wrong field. FlyGym's eye is a published model of the fly's own optics: a camera per eye with a
157 degree vertical field, a fisheye remap, and 721 ommatidia per eye, the same count as the engine's
lattice of radius 15.

## How it is used here

Three pieces of FlyGym and one of MuJoCo, all in `data-pipeline/conectoma/vision/`:

1. **The eye's geometry** (`flygym_eye.py`). FlyGym's `compound_eye.npz` assigns each fisheye pixel to an
   ommatidium, and its `vision.yaml` gives the camera and the fisheye's zoom (2.72) and distortion (3.8).
   The fisheye remap is reimplemented with FlyGym's own arithmetic, vectorised, so that it can move depth
   and segmentation images exactly as FlyGym moves colour.
2. **The eye on the engine's lattice.** The ommatidium centres are fitted to a hexagonal lattice (every one
   on an integer coordinate, the radius-15 hexagon filled exactly), and which of the twelve lattice
   symmetries takes FlyGym's axes to the engine's is measured by rendering markers in known directions. The
   result is committed as `data/derived/vision/flygym-eye.json` by `measure_flygym_eye`.
3. **The fly in a scene** (`flygym_scenes.py`). A `TetheredWorld` holds NeuroMechFly with its root as a
   mocap body, so the fly can be moved along an exact path with its eyes; the scene's surfaces and moving
   objects are added to the world's MuJoCo specification, drawn in their own geom group so the eye renders
   the world and not the fly's own body.
4. **MuJoCo's renderer.** `mujoco.Renderer` renders the right eye's camera three times per frame: colour,
   depth (converted to range along each pixel's ray) and segmentation (which geom each pixel sees). The same
   fisheye lookup and ommatidium pixel sets reduce all three to one value per ommatidium.

Scenes are kinematic: nothing is simulated physically. The world's time step never advances; each frame
sets the fly's or the object's pose and calls `mj_forward`, so a scene is exactly reproducible from its
seed.

## Caveats

- The renderer needs an OpenGL context. On a desktop one is created per process; on a headless machine
  MuJoCo needs an offscreen backend, and the FlyGym test skips where no context can be created.
- FlyGym's own vision pipeline splits each ommatidium into pale and yellow photoreceptor channels. The
  product uses one luminance per ommatidium, as the engine's photoreceptor input expects.
- A scene is built for each seed (about 13 seconds, most of it compiling the fly's model), and the six
  levels of a case are rendered in it by changing only the varied quantity.
