# Cases

The case registry is the validation design of this product: sixteen cases in six categories, each varying
one physical quantity over six levels with units, so that every method is measured along an axis whose
meaning is physical, not a difficulty knob. The registry is `data-pipeline/config/cases.yaml`; the design,
the variants' physics and the per-source geometry are in [architecture/05](architecture/05_vision-data.md),
and the commands in [guide 05](guides/05_vision-data.md).

## How the registry is built

- **Test data only.** A TartanAir case draws from a geometry family that the split assigns to test, and
  every other source is test-only (Sintel's six sequences held out from the published models, Spring,
  Hypersim's official test partition, FlyGym, the synthetic scenes).
- **The same clips at every level.** A case draws its clips once (eight, or all its source has), and renders
  them at all six levels, so the levels differ only in the quantity the case varies.
- **Physics where it happens.** Light and optics act on the image at source resolution (fog with metric
  depth, blur along each pixel's motion, a crop as a longer lens), photon noise acts on each column's
  photoreceptor, speed acts on time. Ground truth changes only where the physics changes it.
- **Every level measured.** Each rendering records what its level means in the image (the speed in m/s, the
  visibility in metres, the blur in pixels, the column spacing in degrees), and every rendering passes
  contract 1. The tables on each page are generated from the committed `data/derived/vision/cases.json`.

## Taxonomy

| Category | Cases | What it asks |
|---|---|---|
| nominal-outdoor | C01, C02 | how depth from motion degrades with ego speed, in the conditions it is made for |
| nominal-indoor | C03, C04 | long corridors under less light; single indoor images, the non-native condition |
| extreme-lighting | C05 | the photon-noise regime of a night city |
| degradation | C06, C07 | the limits of temporal integration; contrast lost with distance |
| transfer | C08, C09 | the published model's own domain; fine structure at finer sampling |
| ethological | C10, C11, C12 | the fly's own tasks, seen through its own eye |
| controls | C13, C14, C15, C16 | depth unobservable by construction (C13, C14), exact ground truth (C15), the aperture problem (C16) |

## The registry

<!-- measured: generated from data/derived/vision/cases.json by `run.py case-docs`; do not edit -->
| case | category | source | varies | levels | grades | clips |
|---|---|---|---|---|---|---|
| [C01, forest flight](cases/C01_forest-flight.md) | nominal-outdoor | tartanair (SeasonalForest) | ego speed (times the recorded speed) | 0.5, 1.00, 2.00, 4.00, 8.00, 16.0 | depth, boundary, flow | 8 |
| [C02, urban street](cases/C02_urban-street.md) | nominal-outdoor | tartanair (VictorianStreet) | ego speed (times the recorded speed) | 0.5, 1.00, 2.00, 4.00, 8.00, 16.0 | depth, boundary, flow | 8 |
| [C03, hospital corridor](cases/C03_hospital-corridor.md) | nominal-indoor | tartanair (Hospital) | illumination (relative illuminance) | 1.00, 0.5, 0.25, 0.125, 0.0625, 0.0312 | depth, boundary, flow | 8 |
| [C04, cluttered room, single image](cases/C04_cluttered-room-single-image.md) | nominal-indoor | hypersim | field of view (degrees (vertical)) | full, 40.0, 32.0, 24.0, 18.0, 12.0 | depth, boundary, figure, semantic | 8 |
| [C05, city at night](cases/C05_city-at-night.md) | extreme-lighting | tartanair (HongKong) | photon noise (photons per column per frame at luminance 1) | none (no noise), 10,000, 1,000, 100, 10.0, 1.00 | depth, boundary, flow | 8 |
| [C06, motion blur](cases/C06_motion-blur.md) | degradation | tartanair (Office) | exposure (ms) | 0, 10.0, 20.0, 40.0, 80.0, 160 | depth, boundary, flow | 8 |
| [C07, marsh in fog](cases/C07_marsh-in-fog.md) | degradation | tartanair (GreatMarsh) | fog attenuation (1/m) | 0, 0.01, 0.02, 0.05, 0.1, 0.2 | depth, boundary, flow | 8 |
| [C08, Sintel, the published model's domain](cases/C08_sintel-the-published-model-s-domain.md) | transfer | sintel | contrast (factor on contrast about the mean) | 1.00, 0.7, 0.5, 0.35, 0.25, 0.15 | depth_relative, flow | 6 |
| [C09, Spring, fine structure](cases/C09_spring-fine-structure.md) | transfer | spring | sampling (rows the 1080-row frame is resampled to (the lattice sees 391 of 436)) | 436, 520, 620, 740, 880, 1,080 | depth, sky | 8 |
| [C10, gap crossing](cases/C10_gap-crossing.md) | ethological | flygym | gap width (mm) | 1.00, 2.00, 3.00, 4.00, 5.00, 6.00 | depth, figure | 8 |
| [C11, looming object](cases/C11_looming-object.md) | ethological | flygym | approach (l/v in ms) | 10.0, 20.0, 40.0, 80.0, 160, 320 | depth, figure | 8 |
| [C12, small moving target](cases/C12_small-moving-target.md) | ethological | flygym | target size (degrees) | 2.00, 4.00, 6.00, 8.00, 12.0, 16.0 | depth, figure | 8 |
| [C13, pure rotation](cases/C13_pure-rotation.md) | negative-control | panorama (BrushifyMoon) | rotation rate (deg/s) | 0, 15.0, 30.0, 60.0, 120, 240 | flow, uncertainty | 8 |
| [C14, static camera](cases/C14_static-camera.md) | negative-control | tartanair (GreatMarsh) | photon noise (photons per column per frame at luminance 1) | none (no noise), 10,000, 1,000, 100, 10.0, 1.00 | uncertainty | 8 |
| [C15, textured planes at known depths](cases/C15_textured-planes-at-known-depths.md) | positive-control | synthetic | nearest plane depth (m) | 0.5, 1.00, 2.00, 4.00, 8.00, 16.0 | depth, flow, figure | 8 |
| [C16, textureless surfaces](cases/C16_textureless-surfaces.md) | boundary | synthetic | texture contrast (RMS contrast) | 0.5, 0.2, 0.1, 0.05, 0.02, 0 | depth, flow, figure | 8 |
<!-- /measured -->

## Reading a case

Each page states why the case exists and which result would count against a method, where its clips come
from and how they were drawn, the physics of its variant with its units, which targets it grades and why
those, what each level measured, and its caveats. Two controls are negative by design: a method that reports
confident depth on C13 or C14 is reporting a prior, not a measurement.
