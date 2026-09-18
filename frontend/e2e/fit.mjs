// Browser gate on the BUILT site against the ADR-0071 floors, measured rather than eyeballed.
//
//   node e2e/fit.mjs [baseUrl] [shotsDir]
//
// Without a base URL it serves dist/ itself with `vite preview` on port 4317 and stops it at the end.
// It first proves it is looking at this product (the brand reads "Conectoma" and the explorer artifact
// loaded and verified against its manifest), because a gate that passes against whatever else answers on
// the port is not evidence of anything. Then, at 1280x800, 1600x900 and 2560x1440, both themes and both
// languages:
//   App route   the document is exactly the viewport (no horizontal drag, no scroll to the footer); the
//               rail shows all its controls; every tab bar is one row; the hexagons actually PAINTED
//               cover at least half the viewport (their union box, not the stretched svg element).
//   doc routes  the page mounted with its own heading; full width; one tab row; no horizontal drag; the
//               Experiments and Benchmark tables are filled from the reports, not left loading.
//   eye mode    the same App floors on each of its three tabs, every lattice canvas holding a picture
//               (colours sampled inside the box it declares it painted), and at one size every one of the
//               sixteen cases loads a clip verified against its manifest and draws all its lattices.
//   modal       each architecture diagram is inlined, sized, in the reader's language, and drawn in the
//               theme's colours (a diagram that fell back to black text is a failure).
import { spawn } from 'node:child_process';
import { mkdirSync } from 'node:fs';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const { chromium } = require('playwright');

const PORT = 4317;
const given = process.argv[2] || null;
const base = (given ?? `http://localhost:${PORT}`).replace(/\/$/, '');
const out = process.argv[3] ?? 'e2e-shots';
mkdirSync(out, { recursive: true });

const VIEWPORTS = [
  { width: 1280, height: 800 },
  { width: 1600, height: 900 },
  { width: 2560, height: 1440 },
];
const THEMES = ['light', 'dark'];
const LANGS = ['en', 'es'];
const VIZ_FLOOR = 0.5;
const DOC_ROUTES = [
  { path: '/introduction', en: 'Introduction', es: 'Introducción' },
  { path: '/methodology', en: 'Methodology', es: 'Metodología' },
  { path: '/implementation', en: 'Implementation', es: 'Implementación' },
  { path: '/experiments', en: 'Experiments', es: 'Experimentos', tables: true },
  { path: '/benchmark', en: 'Benchmark', es: 'Benchmark', tables: true },
];

// each architecture tab's diagram, by a phrase of its aria-label, in tab order
const DIAGRAMS = ['a measured wiring', 'heavy work offline', 'the web build', 'from wiring to a network', 'the contracts'];

const failures = [];
const check = (ok, msg) => {
  if (!ok) {
    failures.push(msg);
    console.log(`FAIL ${msg}`);
  }
  return ok;
};
let passes = 0;
const pass = (ok, msg) => {
  if (check(ok, msg)) passes += 1;
};

async function serve() {
  if (given) return null;
  const root = fileURLToPath(new URL('..', import.meta.url));
  const vite = fileURLToPath(new URL('../node_modules/vite/bin/vite.js', import.meta.url));
  const child = spawn(process.execPath, [vite, 'preview', '--port', String(PORT), '--strictPort'], { cwd: root, stdio: 'ignore' });
  for (let i = 0; i < 60; i += 1) {
    try {
      const r = await fetch(`${base}/`);
      if (r.ok) return child;
    } catch {
      // not up yet
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  child.kill();
  throw new Error(`vite preview did not answer on ${base}`);
}

async function open(browser, viewport, theme, lang) {
  const ctx = await browser.newContext({ viewport });
  await ctx.addInitScript(([t, l]) => {
    localStorage.setItem('caos.theme', t);
    localStorage.setItem('caos.lang', l);
  }, [theme, lang]);
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
  return { ctx, page, errors };
}

// Layout facts measured in the page. Everything here is geometry the browser computed.
function measure() {
  const de = document.documentElement;
  const rows = (list) => {
    const tops = new Set([...list.querySelectorAll('[role="tab"], a')].map((el) => Math.round(el.getBoundingClientRect().top)));
    return tops.size;
  };
  // a vertical sub-tab rail is a column by design; the one-row rule is for horizontal tab bars
  const tablists = [...document.querySelectorAll('[role="tablist"]')]
    .filter((el) => el.getBoundingClientRect().width > 0 && el.getAttribute('aria-orientation') !== 'vertical');
  const nav = document.querySelector('.main-nav');
  const rail = document.querySelector('.cx-rail');
  const body = document.querySelector('.page-body');
  // The painted visualization: the union box of what is drawn (the lattice hexagons, the density chart's
  // plot), each shape clipped to its own svg and the whole to the viewport. The svg element can be larger
  // than what it draws; this is what the reader sees.
  const clip = (r, box) => ({
    left: Math.max(r.left, box.left), right: Math.min(r.right, box.right),
    top: Math.max(r.top, box.top), bottom: Math.min(r.bottom, box.bottom),
  });
  const drawn = [...document.querySelectorAll('.cx-hex-cell, .cx-place, .cx-density-plot')]
    .map((el) => clip(el.getBoundingClientRect(), el.closest('svg').getBoundingClientRect()));
  // canvases declare the box they painted (the eye's lattices); a chart's plot area is uPlot's .u-over
  for (const canvas of document.querySelectorAll('.cx-eye-canvas[data-painted]')) {
    const box = canvas.getBoundingClientRect();
    const [x0, y0, x1, y1] = canvas.dataset.painted.split(',').map(Number);
    drawn.push(clip({ left: box.left + x0, top: box.top + y0, right: box.left + x1, bottom: box.top + y1 }, box));
  }
  for (const over of document.querySelectorAll('.cx-timecourse .u-over')) drawn.push(over.getBoundingClientRect());
  drawn.splice(0, drawn.length, ...drawn.filter((r) => r.right > r.left && r.bottom > r.top));
  let viz = 0;
  if (drawn.length) {
    const left = Math.max(0, Math.min(...drawn.map((r) => r.left)));
    const right = Math.min(innerWidth, Math.max(...drawn.map((r) => r.right)));
    const top = Math.max(0, Math.min(...drawn.map((r) => r.top)));
    const bottom = Math.min(innerHeight, Math.max(...drawn.map((r) => r.bottom)));
    viz = Math.max(0, right - left) * Math.max(0, bottom - top);
  }
  return {
    scrollW: de.scrollWidth,
    scrollH: de.scrollHeight,
    vw: innerWidth,
    vh: innerHeight,
    tabRows: tablists.map(rows),
    navRows: nav ? rows(nav) : 0,
    rail: rail ? { scroll: rail.scrollHeight, client: rail.clientHeight } : null,
    bodyWidth: body ? body.getBoundingClientRect().width : 0,
    vizShare: viz / (innerWidth * innerHeight),
    brand: document.querySelector('.brand')?.textContent?.trim() ?? '',
    verified: document.querySelector('.cx-provenance')?.getAttribute('data-verified') ?? null,
  };
}

// Whether each eye canvas actually holds a picture: distinct colours sampled inside the box it declares it
// painted. A canvas that is sized and declared but left blank shows one or two colours.
function paintedCanvases() {
  return [...document.querySelectorAll('.cx-eye-canvas[data-painted]')].map((canvas) => {
    const [x0, y0, x1, y1] = canvas.dataset.painted.split(',').map(Number);
    const ratio = canvas.width / Math.max(canvas.getBoundingClientRect().width, 1);
    const ctx = canvas.getContext('2d');
    const colours = new Set();
    for (let i = 1; i < 24; i += 1) {
      for (let j = 1; j < 24; j += 1) {
        const x = Math.round((x0 + ((x1 - x0) * i) / 24) * ratio);
        const y = Math.round((y0 + ((y1 - y0) * j) / 24) * ratio);
        const d = ctx.getImageData(x, y, 1, 1).data;
        colours.add(`${d[0]},${d[1]},${d[2]},${d[3]}`);
      }
    }
    return { columns: Number(canvas.dataset.columns), colours: colours.size };
  });
}

const EYE_TABS = { en: ['Input and ground truth', 'All six levels', 'Over time'], es: ['Entrada y verdad de terreno', 'Los seis niveles', 'En el tiempo'] };
const EYE_CASES = Array.from({ length: 16 }, (_, i) => `C${String(i + 1).padStart(2, '0')}`);

async function openEye(page, caseId) {
  await page.goto(`${base}/?mode=eye&case=${caseId}`, { waitUntil: 'networkidle' });
  await page.waitForSelector('.cx-provenance[data-verified]', { timeout: 30000 });
  await page.waitForSelector('.cx-eye-canvas[data-painted]', { timeout: 30000 });
}

const server = await serve();
const browser = await chromium.launch();
try {
  for (const viewport of VIEWPORTS) {
    for (const theme of THEMES) {
      for (const lang of LANGS) {
        const tag = `${viewport.width}x${viewport.height}-${theme}-${lang}`;

        // ---- App route
        {
          const { ctx, page, errors } = await open(browser, viewport, theme, lang);
          await page.goto(`${base}/`, { waitUntil: 'networkidle' });
          await page.waitForSelector('.cx-provenance', { timeout: 30000 });
          for (const tab of lang === 'es' ? ['Filtros', 'Ubicación'] : ['Filters', 'Placement']) {
            await page.getByRole('tab', { name: tab, exact: true }).click();
            await page.waitForTimeout(300);
            const m = await page.evaluate(measure);
            const where = `${tag} App/${tab}`;
            pass(m.brand.includes('Conectoma'), `${where}: the brand reads Conectoma (got "${m.brand}")`);
            pass(m.verified === 'true', `${where}: the explorer artifact verified against its manifest (${m.verified})`);
            pass(m.scrollW <= m.vw, `${where}: no horizontal drag (${m.scrollW} > ${m.vw})`);
            pass(m.scrollH <= m.vh, `${where}: no scroll to the footer (${m.scrollH} > ${m.vh})`);
            pass(m.rail && m.rail.scroll <= m.rail.client + 1, `${where}: the rail shows its controls (${JSON.stringify(m.rail)})`);
            pass(m.navRows === 1 && m.tabRows.every((r) => r === 1), `${where}: chrome on one row (nav ${m.navRows}, tabs ${m.tabRows})`);
            pass(m.vizShare >= VIZ_FLOOR, `${where}: painted instrument covers ${(100 * m.vizShare).toFixed(1)}% of the viewport`);
            await page.screenshot({ path: `${out}/app-${tab.toLowerCase()}-${tag}.png` });
          }
          pass(errors.length === 0, `${tag} App: no page errors ${JSON.stringify(errors.slice(0, 3))}`);
          await ctx.close();
        }

        // ---- App route, eye mode: the same floors, and every canvas holds a picture
        {
          const { ctx, page, errors } = await open(browser, viewport, theme, lang);
          await openEye(page, 'C01');
          for (const tab of EYE_TABS[lang]) {
            await page.getByRole('tab', { name: tab, exact: true }).click();
            await page.waitForTimeout(500);
            const m = await page.evaluate(measure);
            const where = `${tag} App eye/${tab}`;
            pass(m.brand.includes('Conectoma'), `${where}: the brand reads Conectoma (got "${m.brand}")`);
            pass(m.verified === 'true', `${where}: the eye clip verified against its manifest (${m.verified})`);
            pass(m.scrollW <= m.vw, `${where}: no horizontal drag (${m.scrollW} > ${m.vw})`);
            pass(m.scrollH <= m.vh, `${where}: no scroll to the footer (${m.scrollH} > ${m.vh})`);
            pass(m.rail && m.rail.scroll <= m.rail.client + 1, `${where}: the rail shows its controls (${JSON.stringify(m.rail)})`);
            pass(m.navRows === 1 && m.tabRows.every((r) => r === 1), `${where}: chrome on one row (nav ${m.navRows}, tabs ${m.tabRows})`);
            pass(m.vizShare >= VIZ_FLOOR, `${where}: painted instrument covers ${(100 * m.vizShare).toFixed(1)}% of the viewport`);
            const canvases = await page.evaluate(paintedCanvases);
            canvases.forEach((c, k) => pass(c.columns === 721 && c.colours >= 8,
              `${where}: canvas ${k + 1} painted 721 columns in ${c.colours} sampled colours`));
            await page.screenshot({ path: `${out}/app-eye-${EYE_TABS.en[EYE_TABS[lang].indexOf(tab)].split(' ')[0].toLowerCase()}-${tag}.png` });
          }
          pass(errors.length === 0, `${tag} App eye: no page errors ${JSON.stringify(errors.slice(0, 3))}`);
          await ctx.close();
        }

        // ---- documentation routes
        for (const route of DOC_ROUTES) {
          const { ctx, page, errors } = await open(browser, viewport, theme, lang);
          const response = await page.goto(`${base}${route.path}`, { waitUntil: 'networkidle' });
          const where = `${tag} ${route.path}`;
          pass(response && response.status() === 200, `${where}: the document answers 200 (${response?.status()})`);
          const heading = route[lang];
          const mounted = await page.getByRole('heading', { level: 1, name: heading }).count();
          pass(mounted === 1, `${where}: the page mounted with its heading "${heading}"`);
          if (route.tables) {
            await page.waitForSelector('.cx-table td', { timeout: 30000 }).catch(() => {});
            const filled = await page.evaluate(() => ({
              cells: document.querySelectorAll('.cx-table td.num').length,
              loading: !!document.querySelector('.page-body .cx-muted'),
            }));
            pass(filled.cells > 0 && !filled.loading, `${where}: tables filled from the reports (${filled.cells} numeric cells)`);
          }
          // every figure on the page, in every top-level tab, shows only the reader's language
          const tabNames = await page.locator('.page-body .tablist [role="tab"]').allTextContents();
          for (const name of tabNames.length ? tabNames : ['']) {
            if (name) await page.getByRole('tab', { name, exact: true }).first().click();
            await page.waitForTimeout(150);
            const figures = await page.evaluate(async (l) => {
              for (let i = 0; i < 40 && document.querySelector('.cx-figure-placeholder'); i += 1) {
                await new Promise((r) => setTimeout(r, 100));
              }
              return [...document.querySelectorAll('.cx-figure')].map((f) => {
                const shown = [...f.querySelectorAll('text')].filter((t) => getComputedStyle(t).display !== 'none');
                return { shown: shown.length, wrong: shown.filter((t) => t.classList.contains(l === 'es' ? 'l-en' : 'l-es')).length };
              });
            }, lang);
            figures.forEach((f, k) => pass(f.shown > 0 && f.wrong === 0,
              `${where}${name ? ` [${name}]` : ''} figure ${k + 1}: only ${lang} text (${f.wrong} in the other language)`));
          }
          const m = await page.evaluate(measure);
          pass(m.scrollW <= m.vw, `${where}: no horizontal drag (${m.scrollW} > ${m.vw})`);
          pass(m.bodyWidth >= 0.98 * m.vw, `${where}: the page takes the full width (${Math.round(m.bodyWidth)} of ${m.vw})`);
          pass(m.navRows === 1 && m.tabRows.every((r) => r === 1), `${where}: chrome on one row (nav ${m.navRows}, tabs ${m.tabRows})`);
          pass(errors.length === 0, `${where}: no page errors ${JSON.stringify(errors.slice(0, 3))}`);
          if (viewport.width === 1600) await page.screenshot({ path: `${out}/page${route.path.replace('/', '-')}-${tag}.png` });
          await ctx.close();
        }
      }
    }
  }

  // ---- every case of the eye mode, at one size: its clip verifies, and both of its views draw a picture
  {
    const { ctx, page, errors } = await open(browser, { width: 1600, height: 900 }, 'light', 'en');
    for (const caseId of EYE_CASES) {
      await openEye(page, caseId);
      for (const tab of ['Input and ground truth', 'All six levels']) {
        await page.getByRole('tab', { name: tab, exact: true }).click();
        await page.waitForTimeout(400);
        const verified = await page.evaluate(() => document.querySelector('.cx-provenance')?.getAttribute('data-verified'));
        const canvases = await page.evaluate(paintedCanvases);
        const where = `eye ${caseId} ${tab}`;
        pass(verified === 'true', `${where}: clip verified (${verified})`);
        pass(canvases.length === (tab === 'All six levels' ? 12 : 2), `${where}: ${canvases.length} lattices drawn`);
        pass(canvases.every((c) => c.columns === 721 && c.colours >= 4),
          `${where}: every lattice holds a picture (${canvases.map((c) => c.colours).join(', ')} colours)`);
      }
      await page.screenshot({ path: `${out}/eye-${caseId}.png` });
    }
    pass(errors.length === 0, `eye cases: no page errors ${JSON.stringify(errors.slice(0, 3))}`);
    await ctx.close();
  }

  // ---- the artifact check without WebCrypto. A page served over plain HTTP is not a secure context and has no
  // crypto.subtle (the published site before its certificate); localhost is secure, so without this the gate
  // would never see that case. The explorer must still verify its artifact against the manifest.
  {
    const { ctx, page, errors } = await open(browser, { width: 1600, height: 900 }, 'light', 'en');
    await ctx.addInitScript(() => Object.defineProperty(window.crypto, 'subtle', { get: () => undefined }));
    await page.goto(`${base}/`, { waitUntil: 'networkidle' });
    await page.waitForSelector('.cx-provenance', { timeout: 30000 });
    const state = await page.evaluate(() => ({
      subtle: Boolean(window.crypto.subtle),
      verified: document.querySelector('.cx-provenance')?.getAttribute('data-verified'),
    }));
    pass(!state.subtle && state.verified === 'true', `without WebCrypto the artifact still verifies (${JSON.stringify(state)})`);
    pass(errors.length === 0, `without WebCrypto: no page errors ${JSON.stringify(errors.slice(0, 3))}`);
    await ctx.close();
  }

  // ---- the architecture modal, at one size, both themes and languages
  for (const theme of THEMES) {
    for (const lang of LANGS) {
      const tag = `${theme}-${lang}`;
      const { ctx, page, errors } = await open(browser, { width: 1600, height: 900 }, theme, lang);
      await page.goto(`${base}/`, { waitUntil: 'networkidle' });
      await page.getByRole('button', { name: lang === 'es' ? 'Arquitectura / Cómo funciona' : 'Architecture / How it works' }).click();
      const dialog = page.getByRole('dialog');
      await dialog.waitFor();
      const tabs = dialog.getByRole('tab');
      const count = await tabs.count();
      pass(count === 5, `modal ${tag}: five diagrams (${count})`);
      for (let i = 0; i < count; i += 1) {
        await tabs.nth(i).click();
        // the diagram is fetched and swapped in after the click: wait for THIS tab's diagram, identified by
        // its own label, or the checks below would measure the one that was on screen before
        await page
          .waitForFunction(
            (label) => document.querySelector('.caos-architecture-diagram svg')?.getAttribute('aria-label')?.includes(label),
            DIAGRAMS[i],
            { timeout: 15000 },
          )
          .catch(() => {});
        const d = await page.evaluate((l) => {
          const svg = document.querySelector('.caos-architecture-diagram svg');
          const label = svg?.getAttribute('aria-label') ?? '';
          if (!svg) return null;
          const box = svg.getBoundingClientRect();
          const shown = [...svg.querySelectorAll('text')].filter((t) => getComputedStyle(t).display !== 'none');
          const wrong = shown.filter((t) => t.classList.contains(l === 'es' ? 'l-en' : 'l-es')).length;
          const heading = svg.querySelector('text.hd');
          const fill = heading ? getComputedStyle(heading).fill : '';
          const bg = getComputedStyle(document.body).backgroundColor;
          return { label, width: box.width, height: box.height, shown: shown.length, wrong, fill, bg };
        }, lang);
        const where = `modal ${tag} diagram ${i + 1}`;
        pass(d && d.label.includes(DIAGRAMS[i]), `${where}: the diagram on screen is the tab's own ("${d?.label}")`);
        pass(d && d.width > 400 && d.height > 150, `${where}: inlined and sized (${d && `${Math.round(d.width)}x${Math.round(d.height)}`})`);
        pass(d && d.shown > 5 && d.wrong === 0, `${where}: shows only ${lang} text (${d?.wrong} in the other language)`);
        pass(d && d.fill && d.fill !== 'rgb(0, 0, 0)' && d.fill !== d.bg, `${where}: text drawn in theme colour (${d?.fill} on ${d?.bg})`);
        await page.screenshot({ path: `${out}/modal-${i + 1}-${tag}.png` });
      }
      pass(errors.length === 0, `modal ${tag}: no page errors ${JSON.stringify(errors.slice(0, 3))}`);
      await ctx.close();
    }
  }
} finally {
  await browser.close();
  server?.kill();
}

console.log(`\n${passes} checks passed, ${failures.length} failed`);
console.log(failures.length ? 'FIT GATE FAILED' : 'FIT GATE PASSED');
process.exit(failures.length ? 1 : 0);
