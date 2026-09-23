# Architecture

- [01, overview](architecture/01_overview.md): the lanes, the flow, what is frozen and what is learned
- [02, connectome construction](architecture/02_connectome-construction.md): from the release tables to the
  average filters, including how the missing retinotopic columns are inferred and measured
- [03, the network, its regimes and its controls](architecture/03_network-and-regimes.md): the compiler,
  placement and target-centric expansion, the dynamics, the three frozen regimes, the null controls, and
  parity with the published model
- [04, the whole visual system as a network](architecture/04_the-whole-visual-system.md): both optic lobes
  and their projections neuron by neuron, the photoreceptor input, and the loop-gain bound that keeps it
  stable
- [05, the vision data](architecture/05_vision-data.md): the sources and their licenses, fetching members
  over HTTP ranges, the fly's eye over a frame and the fly's own eye, what each source can grade, contract 1,
  splits by geometry family, and the sixteen cases with their physical variants
- [06, from motion on the lattice to distance](architecture/06_from-flow-to-distance.md): the readout every
  motion method shares, what a column cannot measure (pure rotation, the focus of expansion), finding a
  moving object without knowing any distance, and the flow estimator on the hexagonal lattice with its
  measured accuracy
- [07, how a method is scored](architecture/07_how-a-method-is-scored.md): the metrics and the conventions
  behind them, the floor every flow-based row is read against, the cases where refusing IS the right
  answer, the motion a case declares when it records no poses, and why a comparison is paired on the clip
- [09, the response view](architecture/09_the-response-view.md): the connectome's own pathway playing
  beside the eye's input, why the response is precomputed rather than simulated in the browser, the
  measured size budget behind what the artifact carries, and the gate check that an animation moves
- [08, the data contracts](architecture/08_data-contracts.md): connectome and vision ingestion, the
  connectome specification, and the artifact contract the web consumes
- [10, the chain](architecture/10_the-chain.md): the network's answer beside what the eye receives and
  what is really there, the measured circuit carrying the signal, why no motion arrows are drawn, the
  clock and where it opens, and a defect this view exposed in every chart of the App

Pages for determinism, the live gate, training, evaluation and deploy are written by the units that build
those parts, so a page here always describes something that exists.
