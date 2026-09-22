# From motion on the lattice to depth in metres

Every motion method in this product ends in the same two steps: measure how the 721 columns' view moved
between two frames, then turn that movement into a distance using the camera motion the corpus committed
with each clip. The methods differ only in the first step, which is the comparison the ladder exists to
make: the same readout reads a classical estimator (M01) and the published network's own decoder (M04),
so a difference between them is a difference in the flow, not in the arithmetic after it.

The code is `data-pipeline/conectoma/methods/readout.py` (the geometry) and
`data-pipeline/conectoma/methods/flow_lattice.py` (the estimator).

## 1. What a column can measure, and what it cannot

Longuet-Higgins and Prazdny ([1980](https://doi.org/10.1098/rspb.1980.0057)) split the motion field of a
rigid scene under a known camera motion into a part that carries no distance and a part that is the
distance. Written in this product's pinhole coordinates (x right, y down, z forward, the frame
`conectoma/vision/decode.py` already uses), a point at distance `Z` along a column's ray `d` lands at

```
p'(Z) = Z (R d) + t           R, t: the motion from this frame to the next, from the committed poses
x'(Z) = f p'_x / p'_z         f: the focal length of the 436-row frame the lattice sees
```

`Z` is PLANAR depth, the z coordinate in the camera frame, and `d` is the column's ray scaled so that its
own z is one. That is not a detail: the corpus records planar depth, because TartanAir, Spring and
Hypersim all distribute it, and solving for distance along the ray instead inflates every off-axis column,
by 1.41 at the corner of this lattice. The synthetic control (planes at a stated depth, camera translating
at a stated speed) caught that error before any number left the repository.

The measured displacement gives two equations in the single unknown `Z`, solved together:

```
Z = (A . b) / (A . A)     A = [x' a_z - f a_x,  y' a_z - f a_y]     b = [f t_x - x' t_z,  f t_y - y' t_z]
```

with `a = R d`. Nothing is linearised, so a large rotation between frames is handled exactly, and the
degeneracy of the problem is visible in one place.

**The baseline a column actually has.** Distance from motion needs translation ACROSS the line of sight:
`t_perp = |t - (t . d) d|`. The relative uncertainty of the distance follows from it,

```
sigma_Z / Z = Z sigma_px / (f t_perp)
```

so it grows with the SQUARE of distance for a fixed baseline. Two consequences the product reports rather
than hides:

- Under pure rotation `t_perp` is zero at every column and no column can report a distance. That is case
  C13, and it is graded by the share of columns a method flags unknown, not by a depth error.
- A column looking along the direction of travel has `t_perp = 0` for the same reason. That is the focus
  of expansion, and it is why a forward-flying camera cannot see the distance of what is straight ahead.

A distance is claimed only where the uncertainty is inside the caller's tolerance. Everywhere else the
readout returns unknown, which is a result, not a gap.

**Moving objects, without knowing any distance.** For a rigid scene the displacement must lie along the
epipolar direction whatever `Z` is, so the ANGLE between the measured displacement and that direction
tests rigidity on its own. The readout returns that deviation and the distance of the measurement from
the epipolar line in pixels; M01's segmentation arm thresholds them. A displacement too small to have a
direction is never called moving.

## 2. Measuring the movement on a hexagonal lattice

A dense estimator written for a pixel grid does not apply to the eye: its columns are a hexagonal lattice
with 13 pixels between neighbours, and between two columns there is nothing. The estimator is therefore
the classical differential one (the brightness-constancy constraint of Horn and Schunck,
[1981](https://doi.org/10.1016/0004-3702(81)90024-2), solved over a patch as Lucas and Kanade's method
does), rewritten on that lattice:

- a column's patch is itself and its six hexagonal neighbours, its own equation weighted double;
- the confidence is the smaller eigenvalue of the patch's normal matrix, which collapses on an edge (every
  gradient parallel: the aperture problem) and on a flat patch. Below the caller's threshold the estimator
  returns no velocity rather than the arbitrary one a pseudo-inverse would produce. Cases C16 (textureless
  surfaces) and C07 (contrast) grade exactly that refusal;
- the displacement is found by refinement: each step solves for the correction that makes the second frame,
  sampled where the columns are predicted to have moved, match the first over the patch, and a step is
  taken only when it lowers the residual.

Two details decide whether the numbers are right, and both were measured rather than assumed.

**Interpolation happens where the columns really are.** The engine truncates each column centre to a whole
pixel (`int(13 (u + v/2))`), which moves it by up to one pixel in thirteen. Interpolating on the ideal
lattice does not even return a column its own value: the error there was 2.3e-2 of a signal whose spread
is 0.79. The estimator therefore builds each triangle from the columns' real pixel positions, and
interpolation at a column is then exact to 1e-16.

**A gradient read across the lattice is too small, and the velocity comes out too large.** A difference
over 13 pixels under-reads the slope of any structure that is not much wider than that. Solving once with
that gradient returned a velocity 12 to 24 percent too large, in the direction of the motion, on a
band-limited test texture: a scale error that would have multiplied every distance by the same factor.
The refinement uses the interpolant's own gradient, exact inside each lattice triangle, so the step size
matches the objective it minimises.

Measured on that texture after the fix, taking the median over the columns whose confidence is in the top
40 percent:

| True displacement | Recovered | Scale |
|---|---|---|
| (1.0, 0.0) px | (0.96, 0.00) | 0.96 |
| (0.0, -1.5) px | (0.00, -1.45) | 0.97 |
| (0.8, 0.6) px | (0.67, 0.47) | 0.82 |
| (4.0, -3.0) px | (4.00, -2.82) | 0.98 |

A displacement of one and a half pixels or more comes back within 5 percent. A displacement of one pixel,
which is 8 percent of a lattice step, comes back within 20 percent. The objective's own minimum sits at
0.95 of the true displacement for that case, so most of what remains is the information the lattice
carries, not the solver. The tests hold these bounds (`tests/test_methods_flow.py`).

## 3. What it costs, measured

On a TartanAir forest clip, 32 frames, against the depth the corpus committed:

| Row | Columns it claims | Median relative error |
|---|---|---|
| the committed flow, inverted by this readout | 88 percent | 0.9 percent |
| M01, its own estimate of the flow | 43 percent | 8.1 percent |

The first row is not a method. It is what the readout returns when the flow is exactly right, and it says
that the arithmetic after the flow costs essentially nothing: a motion method's error IS its flow's error.
Every flow-based row of the ladder is reported against it.

## 4. What the corpus provides and what is assumed

| Quantity | Where it comes from |
|---|---|
| the camera motion `R`, `t` between frames | the poses committed with each clip, through `decode.relative_motion` |
| the focal length `f` of the 436-row frame | the column spacing each rendering records, inverted in `readout.focal_px` |
| the ray of each column | the engine's own receptor centres, as pinhole directions |
| the flow, in pixels | `readout.pixel_flow`, undoing the engine's storage (per image height, y up, summed over the 169-pixel box) |

The column spacing a rendering records is the on-axis subtense `2 atan(6.5 / f)`, which is not the angle
between two neighbouring rays away from the axis: a pinhole camera is not linear in angle. The readout
uses the exact rays throughout, so that difference (0.003 degrees at the centre for TartanAir, more at the
rim) never enters a distance.

## References

- Longuet-Higgins, H. C. and Prazdny, K. (1980). The interpretation of a moving retinal image.
  *Proceedings of the Royal Society of London B* 208(1173):385-397.
  [doi:10.1098/rspb.1980.0057](https://doi.org/10.1098/rspb.1980.0057)
- Horn, B. K. P. and Schunck, B. G. (1981). Determining optical flow. *Artificial Intelligence*
  17(1-3):185-203. [doi:10.1016/0004-3702(81)90024-2](https://doi.org/10.1016/0004-3702(81)90024-2)
