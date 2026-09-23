# The response view: the connectome, playing

The App has three modes. The first is the wiring the network is built from, the second is what the eye's
721 columns receive in a case, and the third, this one, is what the measured connectome DOES with that
input while it plays. Its first view, the chain, is on [its own page](10_the-chain.md): the network's
answer beside the input and the truth, and the circuit carrying the signal. This page is the pathway view
and the playback both share.

It exists because the product was missing the thing it is about. The eye view could advance its frames,
but it did so by writing each frame into the URL, one router navigation per frame at five to ten frames a
second: a slide show with a history entry per slide. And nothing anywhere showed the network responding.
Meanwhile the engine this product is built on ships an animations package whose modules are exactly these
views (`hexscatter`, `activations.StimulusResponse`, `network.WholeNetworkAnimation`, `traces`), and the
2026 ecosystem of fly-connectome projects is full of browser apps with a live activity display beside the
behaviour.

## 1. What is drawn

The fly's own visual pathway, in the order the signal travels, each cell type on the same hexagonal
lattice the column that drove it looks through:

| Stage | Types | What they are |
|---|---|---|
| lamina | L1, L2, L3 | the first synapse: ON input, OFF input, sustained contrast |
| medulla | Mi1, Tm3, Tm1, Tm2, Mi9, Mi4 | the fast and slow arms of the motion detector, and its inhibition |
| output | T4a to T4d, T5a to T5d | direction selective, ON and OFF, four directions each |

`CT1` belongs to that pathway and is not drawn: this connectome carries ONE CT1 cell for the whole
lattice rather than one per column, so it has no map. The manifest names it under `wide_field` rather than
dropping it silently.

Above them is the eye's own input for the same clip, on the same clock, so a reader sees the stimulus and
the response together. That is the engine's own `StimulusResponse` view, in a browser.

## 2. Nothing is simulated in the browser

The network is 40,051 cells and 2.9 million connections. Simulating it client-side would be dishonest
performance and, worse, would show a visitor a different network from the one the numbers come from. The
frozen network is run in the pipeline (`run.py export-brainclips`) and its response is committed under
contract 2, verified against its SHA-256 before it is drawn, exactly as the eye clips are.

**The size budget, measured rather than guessed.** One case-level with 17 types at every simulated step is
1.96 MB of bytes, which gzips to 1.36 MB stored plainly and 0.74 MB delta-coded over time. All sixteen
cases at all six levels would therefore be 71 MB served, and a repository nobody wants to clone. The
artifact carries **the two ends of each case's sweep at every third step**, delta-coded, which is 20 MB and
the same order as the eye clips already committed. What is lost is the four middle levels of each sweep;
what is kept is its two ends, which is where a case's physical quantity actually bites.

The transport encoding is the delta: the first row of a type is a byte per column, every later row is its
signed difference from the row before. Activity moves smoothly between steps 20 ms apart, so the
differences are small and repetitive and gzip eats them.

## 3. How it is drawn, and the three defects that taught it

- **Each map is centred on its own cell type's resting level**, not on zero, with a spread taken as the
  95th percentile of the distance from it. Neurons rest at very different levels (measured on one clip:
  Mi1 near -2.7, T5a near +2.7), so a map centred on zero paints one type solid blue and another solid red
  and hides the only thing that moves.
- **The colour is a diverging, colour-blind-safe map**, cool below rest and warm above, with a legend in
  the rail drawn from the same stops the canvases use. Never a rainbow (the visualisation rubric's law 4).
- **A canvas belongs inside its card.** The eye's canvas class is absolutely positioned, because the eye
  view overlays a title and a readout on it; reusing that class without making the new wrapper a
  containing block sent every activity canvas to the viewport origin, where seventeen of them stacked and
  painted a blob over the page header.
- **A lattice is as wide as it is tall.** The first layout gave each type a wide, short card, so the
  hexagons drew an 81-pixel patch in a 411-pixel box and the view read as empty. Cards are square.

## 4. Playback

`usePlayback` holds the frame in local state and steps it with `requestAnimationFrame` against the real
clock, so a dropped frame shortens the next step instead of stretching the clip. Speed runs from 0.25x to
4x of the recorded rate, because the sources' rates differ by a factor of five. It is **paused by default**
and **stops when the tab is hidden**, and the URL is written only when the reader pauses, so a shared link
still opens on an exact step without a history entry per frame.

## 5. What the gate checks

The ADR-0071 fit gate covers this mode at every viewport, theme and language: the rail shows its controls,
the chrome stays on one row, the response verifies against its manifest, and every map paints 721 columns.
And the check an animation actually needs, which a screenshot cannot make:

```
press play  ->  the pixels of the activity canvases must CHANGE
press pause ->  they must stop changing
```

A gate that only looked at one frame would pass a view that never moves, which is the defect this mode was
built to fix.

## Sources

- `flyvis` 1.2.0, `flyvis/analysis/animations/`: the engine's own animation vocabulary (MIT).
- `conventions/interactive-visualization-rubric.md` in the management repo: no static picture, mark what
  matters, perceptually uniform colour, a value readout on every chart.
- The research behind this page: `wip/connectome-vision/11-dynamic-visualisation-what-the-field-shows-2026-09-22.md`.
