# The web: build, check and publish the site

How the companion site is built from the committed artifacts, how it is checked, and how it reaches
`conectoma.fasl-work.com`. The site is static: it computes nothing the pipeline has not already computed,
and every number it shows is read from a committed file at load time. The contract it reads is in
[architecture/08](../architecture/08_data-contracts.md).

## 1. The environment

Node 22 with the dependencies installed locally in `frontend/node_modules` (never globally). The only
browser dependency is the shared shell, `@fasl-work/caos-app-shell`, which provides the header, the six-route
navigation, the themes, the language toggle, the tabs, KaTeX equations, the per-section references and the
architecture modal.

```bash
cd frontend
npm ci
```

## 2. From the pipeline to the page

The pipeline writes the explorer artifact and its manifest:

```bash
.venv-pipeline/Scripts/python data-pipeline/run.py export-web
```

It reads the committed connectome specification and the published consensus that ships with the engine,
and writes `data/derived/explorer/malecns-optic-lobe-r.json` (one row per cell type, one row per connection
whose filter is three parallel arrays, and the published filters that match) and
`data/derived/manifests/explorer.json` (its size, its SHA-256, the digests of the specification and the
reference, the dataset, license and citation, and four counts). The output carries no timestamp: the same
inputs give the same bytes, and the pipeline's tests rebuild it and require exactly the committed bytes.

`npm run dev` and `npm run build` both start with `copy-data.mjs`, which copies the committed artifacts and
the reports the Experiments and Benchmark pages read into `public/data/`, and the documentation diagrams
into `public/svg/docs/`. It fails when a file it expects is missing, instead of building a site with a hole
in it. Nothing it copies is committed twice: `public/data/` and `public/svg/docs/` are ignored.

## 3. The build

```bash
npm run build
```

runs, in order and stopping at the first failure:

1. `tsc --noEmit`, the type check;
2. `vitest run`, the contract tests on the committed files: the explorer artifact against the runtime
   validator in `src/lib/contract.ts`, its bytes against the manifest's size and SHA-256, its counts against
   the manifest's, a set of deliberate corruptions the validator must catch, and every report field the
   Experiments and Benchmark pages read;
3. `vite build`, with the absolute base `/`, because a relative base resolves assets against a deep route;
4. `static-routes.mjs`, which gives each of the five documentation routes its own copy of `index.html`, so
   a deep link answers 200 with the application instead of a 404 page that happens to render it.

The page repeats the contract check at run time: `loadExplorer` validates the manifest and the artifact,
compares the counts, and computes the SHA-256 of the bytes it received, with WebCrypto where the page is a
secure context and with a plain implementation (`src/lib/sha256.ts`, tested against Node's) where it is
not, such as a page served over plain HTTP before its certificate exists. An artifact that does not match
is refused with the field that drifted; a digest mismatch is shown in the rail as "NOT verified".

## 4. The fit gate

```bash
npx playwright install chromium     # once; set PLAYWRIGHT_BROWSERS_PATH to keep browsers off the system disk
npm run gate
```

`e2e/fit.mjs` serves `dist/` with `vite preview` on port 4317 (or checks the URL given as its first
argument) and measures the ADR-0071 floors in a real browser at 1280x800, 1600x900 and 2560x1440, in both
themes and both languages:

- it first proves it is looking at this product: the brand reads Conectoma and the explorer artifact
  verified against its manifest;
- on the App, on both tabs: no horizontal drag and no scroll to the footer; the rail shows every control
  without scrolling (only the partner list scrolls, inside its own box); every horizontal tab bar is one
  row; and what is actually drawn covers at least half the viewport. "Drawn" is the union of the painted
  hexagons and the density chart's plot, each clipped to its own svg, not the size of an svg element,
  which can be larger than what it draws;
- on each documentation route: the document answers 200, the page mounted with its own heading, it takes
  the full width with one row of tabs, and on Experiments and Benchmark the tables are filled from the
  reports rather than left loading;
- with WebCrypto removed before the page loads (what a plain-HTTP page gets; localhost is a secure
  context, so the gate would never see it otherwise), the explorer must still verify its artifact;
- in the architecture modal: each diagram is the one its tab names (it waits for that diagram, not for any
  diagram), shows only the reader's language, and is drawn in the theme's colours.

Screenshots of every state land in `e2e-shots/` (ignored) or the directory given as the second argument.
They are the evidence for the visual review, which the gate does not replace.

## 5. Publish

`.github/workflows/deploy-pages.yml` runs on every push to `main`: the same build, the same gate, and only
then the upload to GitHub Pages. A site that fails the gate is never published. The custom domain is set
through the Pages API (a `CNAME` file alone does not set it for a workflow deploy); `public/CNAME` records it
in the site as well.

A deploy is verified on the live address, not on the build: every route must answer 200 with the product
mounted, and the explorer must load and verify. The gate accepts the live URL as its first argument:

```bash
npm run gate -- https://conectoma.fasl-work.com
```

## 6. The architecture diagrams

The five diagrams of the architecture modal (`public/svg/tech/`) are authored as SVG, one file per tab
with both languages inside (each text twice, classed `l-en` and `l-es`; the shell shows one). They take
every colour from the shell's tokens, so they follow the theme once the modal inlines them. Anything drawn
dashed is planned and not built yet, and the legend says so.
