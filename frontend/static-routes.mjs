// Post-build: give every route its own index.html so a deep link answers 200 with the app, rather than a
// 404 that happens to render it (GitHub Pages serves 404.html with status 404, which crawlers and link
// checkers read as a broken page). 404.html stays as the fallback for paths that are not routes.
import { copyFileSync, existsSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const DIST = join(dirname(fileURLToPath(import.meta.url)), 'dist');
const ROUTES = ['introduction', 'methodology', 'implementation', 'experiments', 'benchmark'];

const index = join(DIST, 'index.html');
if (!existsSync(index)) {
  console.error('[static-routes] dist/index.html is missing; run vite build first');
  process.exit(1);
}
for (const route of ROUTES) {
  mkdirSync(join(DIST, route), { recursive: true });
  copyFileSync(index, join(DIST, route, 'index.html'));
}
copyFileSync(index, join(DIST, '404.html'));
console.log(`[static-routes] ${ROUTES.length} route pages and 404.html`);
