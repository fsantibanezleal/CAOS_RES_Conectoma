// Prebuild overlay: the committed contract-2 artifacts (../data/derived) and the documentation figures
// (../docs/assets/svg) are copied into public/ so the static site serves them. The canonical copies stay in
// data/ and docs/; public/data and public/svg/docs are generated and git-ignored.
import { cpSync, existsSync, mkdirSync, rmSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, '..');
const PUBLIC = join(HERE, 'public');

// Only what the web reads: the explorer artifact, the manifests, and the committed reports the Benchmark and
// Experiments pages read their numbers from. The engine-format specification (8 MB) stays out.
const ARTIFACTS = [
  'explorer',
  'manifests',
  'network/parity-published.json',
  'connectome/malecns-optic-lobe-r.comparison.json',
  'connectome/malecns-optic-lobe-r.report.json',
  'connectome/malecns-optic-lobe-r.characterization.json',
  'connectome/malecns-visual-cns.summary.json',
  'connectome/malecns-visual-cns.characterization.json',
];

const derived = join(ROOT, 'data', 'derived');
const target = join(PUBLIC, 'data');
rmSync(target, { recursive: true, force: true });
let copied = 0;
for (const item of ARTIFACTS) {
  const source = join(derived, item);
  if (!existsSync(source)) {
    console.error(`[copy-data] missing committed artifact: data/derived/${item}`);
    process.exit(1);
  }
  mkdirSync(dirname(join(target, item)), { recursive: true });
  cpSync(source, join(target, item), { recursive: true });
  copied += 1;
}
console.log(`[copy-data] ${copied} artifacts -> public/data`);

const figures = join(ROOT, 'docs', 'assets', 'svg');
const figuresTarget = join(PUBLIC, 'svg', 'docs');
rmSync(figuresTarget, { recursive: true, force: true });
if (existsSync(figures)) {
  mkdirSync(figuresTarget, { recursive: true });
  cpSync(figures, figuresTarget, { recursive: true });
  console.log('[copy-data] docs/assets/svg -> public/svg/docs');
}
