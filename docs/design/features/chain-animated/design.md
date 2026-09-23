# The chain, animated: design

## What was wrong with what the App showed

Measured on the live site before this unit, at 1600 by 1000 in the dark theme:

- The Response mode opened on simulated step 1 of 54. That is the network's grey steady state: every map
  was flat, L1 to L3 uniformly pale, Mi1 uniform, and a reader concluded that nothing happens.
- The pathway was seventeen cards of about 120 pixels each, with the eye's own input 150 pixels wide above
  them. At that size a 721-column lattice is texture, not a picture.
- Nothing anywhere showed what the network CONCLUDES. The product is about a network that reads depth out
  of the fly's motion detectors, and the App never showed a depth it read.

One thing that looked like the obvious fix was measured and refused. T4 and T5 are the fly's
direction-selective cells, and an animated field of motion arrows read off them is what several connectome
demonstrations show. The frozen MaleCNS network's T4 and T5 are not direction selective: on the published
moving-edge protocol their largest direction selectivity index is 0.012. Arrows drawn from them would be
decoration presented as measurement, so the chain carries that measurement and the view refuses a motion
field below 0.1.

## Data flow

```
case clip (U4)          eyeclips (U4)        the input the columns receive, per frame
   |                     brainclips (U6)     the pathway's voltages, every third simulated step
   |
   +--> m05.run / m06.run, the scoring stage's own call, at the committed report's tolerance
   |        |
   |        v
   |    export-chain: per case, both ends of the sweep, per frame
   |        depth everywhere (one log byte), the head's own spread (one byte), refused (one bit)
   |        truth (one log byte)
   |
   +--> the committed connectome specification --> circuit.json
            the pathway's 19 cell types and every specification edge between them,
            with synapses onto one target cell and sign; the measured T4 and T5 selectivity
```

Why the readout is exported rather than computed in the browser: the head is small, but its input is the
T4 and T5 activity at frame resolution for five seeds of two networks, which is not in any artifact the web
has, and recomputing it client-side would be a second implementation of the scored readout. Exporting the
scoring stage's own output means the map a reader sees is, column for column, the number the Experiments
page reports.

Why the answer is carried everywhere and the refusal as a separate layer: the view shows what the network
answered AND whether it stood behind the answer. A refused column keeps its colour, faint, with a dot.

## The encodings, and what they cost

| Layer | Encoding | Resolution | Per case-level and network |
|---|---|---|---|
| depth | one byte, log-spaced from 0.1 m to 5 km, 0 is "no value" | 4.4 percent a step | 22 KB |
| spread | one byte, 0 to 4 in log depth | 0.016 | 22 KB |
| refused | one bit per column, packed | exact | 2.8 KB |
| truth | as depth, once per case-level | 4.4 percent | 22 KB |

Sixteen cases by two levels by two networks is about 4.9 MB of base64 before the transport compresses it,
inside the 6 MB budget the requirements set and the artifact gate enforces.

## The views

**The chain** (the default tab). Four maps left to right in the order the answer is produced: what the
eye receives, what the network concludes, what is really there, and where it is wrong. The readout and the
truth share one log scale per clip, taken from the truth's 2nd to 98th percentiles, so the two are read on
one ruler. The error map is the signed log ratio of readout to truth, saturating at a factor of four:
cool where the network puts a surface too near, warm where too far. Below them, the time course: each
network's mean relative error per frame and the pathway's activity, with the playing frame marked and
clickable.

**The circuit.** The pathway's cell types in their layers, retina to lamina to medulla to the
direction-selective outputs, and a fifth column for the trained head. Each node is a live miniature of its
type's map on the 721 columns. Each connection is drawn only if the specification has it, as wide as its
synapse count onto one target cell, warm if excitatory and cool if inhibitory, and pulsing with its drive
at the current step: the source's deviation from rest times the signed weight. The head is not wiring and
is drawn apart: dashed, grey, labelled. The pulses move only while the clock plays.

**The pathway** and **One column** are the existing views, the first enlarged (cards of 10.5 rem, the eye
above them at 13 rem).

## The clock

One clock drives all four views: the brain clip's rows, every third simulated step of 20 ms, which is what
makes the response move between frames. A row maps to the eye's frame it belongs to and the readout's row
for that frame. The view opens paused on the liveliest row, the one where the pathway is furthest from
rest in units of each type's own spread, unless the link names a step. Switching the network between the
frozen and the trained one keeps the step.

## What is deliberately not here

- No motion field, for the reason above.
- No readout for the four middle levels of a sweep: the brain clips carry only the two ends, and a chain
  with an answer but no pathway beside it would be half a chain.
- No simulation in the browser.
