import { useEffect, useMemo, useRef, useState } from 'react';
import { COLUMNS, depthOf, type DecodedLevel, type EyeClip, type EyeManifest } from '../lib/eye';
import { useNumber, useT } from '../lib/i18n';
import { depthColour, flowColour, grey, parseRgb, shareColour } from './colour';

export type View = 'lum' | 'depth' | 'figure' | 'boundary' | 'flow' | 'sky' | 'labelled';

// The engine samples column (u, v) at pixel row 13 (u + v/2) and column 13 v from the frame centre, so its
// columns sit on a hexagonal lattice stretched horizontally: vertical neighbours 13 px apart, diagonal ones
// at (13, 6.5). A flat-topped hexagon of circumradius 13 / sqrt(3), stretched by 13 / (1.5 R), tiles it
// exactly, so every column is drawn where the eye samples it and the picture reads as the frame did.
const STEP = 13;
const R = STEP / Math.sqrt(3);
const STRETCH = STEP / (1.5 * R);
const HEX = Array.from({ length: 6 }, (_, k) => {
  const a = (Math.PI / 3) * k;
  return [Math.cos(a) * R * STRETCH, Math.sin(a) * R] as const;
});

interface Hovered { column: number }

export default function EyeLattice({ manifest, clip, level, frame, view, title, compact = false }: {
  manifest: EyeManifest;
  clip: EyeClip;
  level: DecodedLevel;
  frame: number;
  view: View;
  title?: string;
  compact?: boolean;
}) {
  const t = useT();
  const num = useNumber();
  const host = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  const [hovered, setHovered] = useState<Hovered | null>(null);
  const { row_px: rows, col_px: cols, u, v } = manifest.lattice;

  useEffect(() => {
    const element = host.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      if (width > 0 && height > 0) setSize({ width, height });
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  // world extent of the lattice in pixels, with a hexagon's reach on every side
  const fit = useMemo(() => {
    const reserve = compact ? 0 : 44;   // a compact panel's title is an overlay, not a band
    const spanX = Math.max(...cols) - Math.min(...cols) + 2 * R * STRETCH;
    const spanY = Math.max(...rows) - Math.min(...rows) + 2 * R;
    const scale = Math.max(Math.min(size.width / spanX, (size.height - reserve) / spanY), 0.01);
    return { scale, cx: size.width / 2, cy: (size.height - reserve) / 2 + (compact ? 0 : 22) };
  }, [cols, rows, size, compact]);

  useEffect(() => {
    const element = canvas.current;
    if (!element || size.width === 0) return;
    const ratio = window.devicePixelRatio || 1;
    element.width = Math.round(size.width * ratio);
    element.height = Math.round(size.height * ratio);
    const ctx = element.getContext('2d');
    if (!ctx) return;
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    const style = getComputedStyle(element);
    const surface = style.getPropertyValue('--color-surface').trim() || '#ffffff';
    const faint = style.getPropertyValue('--color-fg-faint').trim() || '#8b949e';
    const accent = parseRgb(style.getPropertyValue('--color-accent'), [9, 105, 218]);
    ctx.clearRect(0, 0, size.width, size.height);

    const base = frame * COLUMNS;
    const steps = Math.max(clip.frames - 1, 1);
    const flowRow = Math.min(frame, steps - 1) * 2 * COLUMNS;
    for (let c = 0; c < COLUMNS; c++) {
      const x = fit.cx + cols[c] * fit.scale;
      const y = fit.cy + rows[c] * fit.scale;
      ctx.beginPath();
      HEX.forEach(([dx, dy], k) => {
        const px = x + dx * fit.scale * 0.96;
        const py = y + dy * fit.scale * 0.96;
        if (k === 0) ctx.moveTo(px, py);
        else ctx.lineTo(px, py);
      });
      ctx.closePath();
      const lum = level.lum[base + c];
      let fill: string | null = grey(lum);
      if (view === 'depth') fill = depthColour(level.depth[base + c]);
      else if ((view === 'figure' || view === 'sky' || view === 'labelled') && level[view]) {
        fill = shareColour(level[view]![base + c], lum, accent);
      } else if (view === 'flow' && level.flow && clip.flow) {
        fill = flowColour(level.flow[flowRow + c], level.flow[flowRow + COLUMNS + c], 127);
      }
      if (fill === null) {
        // masked depth: no value to show, drawn as an outline on the page's own surface
        ctx.fillStyle = surface;
        ctx.fill();
        ctx.strokeStyle = faint;
        ctx.lineWidth = 0.6;
        ctx.stroke();
      } else {
        ctx.fillStyle = fill;
        ctx.fill();
        // a hairline in the page's faint colour, so a column as light as the page still shows its edge
        ctx.strokeStyle = faint;
        ctx.globalAlpha = 0.35;
        ctx.lineWidth = 0.5;
        ctx.stroke();
        ctx.globalAlpha = 1;
      }
      if (view === 'boundary' && level.boundary && level.boundary[base + c]) {
        ctx.strokeStyle = `rgb(${accent.join(',')})`;
        ctx.lineWidth = Math.max(1, fit.scale * 1.6);
        ctx.stroke();
      }
      if (hovered?.column === c) {
        ctx.strokeStyle = `rgb(${accent.join(',')})`;
        ctx.lineWidth = 2;
        ctx.stroke();
      }
    }
    // the renderer declares what it drew: the box of the painted hexagons (CSS pixels, relative to the
    // canvas) and how many columns it filled, so a gate measures the drawing, not the element
    const left = fit.cx + (Math.min(...cols) - R * STRETCH) * fit.scale;
    const right = fit.cx + (Math.max(...cols) + R * STRETCH) * fit.scale;
    const top = fit.cy + (Math.min(...rows) - R) * fit.scale;
    const bottom = fit.cy + (Math.max(...rows) + R) * fit.scale;
    element.dataset.painted = [left, top, right, bottom].map((x) => x.toFixed(1)).join(',');
    element.dataset.columns = String(COLUMNS);
  }, [size, fit, level, frame, view, clip, hovered, cols, rows]);

  function locate(event: React.PointerEvent) {
    const rect = canvas.current?.getBoundingClientRect();
    if (!rect) return;
    const x = (event.clientX - rect.left - fit.cx) / fit.scale;
    const y = (event.clientY - rect.top - fit.cy) / fit.scale;
    let best = -1;
    let distance = Infinity;
    for (let c = 0; c < COLUMNS; c++) {
      const d = (cols[c] - x) ** 2 + (rows[c] - y) ** 2;
      if (d < distance) { distance = d; best = c; }
    }
    setHovered(distance <= (STEP * 0.8) ** 2 ? { column: best } : null);
  }

  const readout = (() => {
    if (!hovered || compact) return null;
    const c = hovered.column;
    const base = frame * COLUMNS;
    const parts = [`(u ${u[c]}, v ${v[c]})`, `${t('luminance', 'luminancia')} ${num(level.lum[base + c] / 255, 2)}`];
    const d = depthOf(level.depth[base + c], clip.depth.near_m, clip.depth.far_m);
    parts.push(Number.isNaN(d) ? t('depth masked', 'profundidad enmascarada')
      : `${t('depth', 'profundidad')} ${num(d, d < 1 ? 3 : d < 100 ? 2 : 0)}${clip.depth.units === 'metres' ? ' m' : ''}`);
    if (level.figure) parts.push(`${t('figure', 'figura')} ${num(level.figure[base + c] / 255, 2)}`);
    if (level.sky) parts.push(`${t('sky', 'cielo')} ${num(level.sky[base + c] / 255, 2)}`);
    if (level.boundary) parts.push(level.boundary[base + c] ? t('on a boundary', 'en un borde') : t('inside a segment', 'dentro de un segmento'));
    if (level.flow && clip.flow) {
      const row = Math.min(frame, clip.frames - 2) * 2 * COLUMNS;
      const s = clip.flow.scale / 127;
      parts.push(`${t('flow', 'flujo')} (${num(level.flow[row + c] * s, 2)}, ${num(level.flow[row + COLUMNS + c] * s, 2)})`);
    }
    return parts.join('  ·  ');
  })();

  return (
    <div className={compact ? 'cx-eye cx-eye-compact' : 'cx-eye'} ref={host}>
      {title ? <div className="cx-eye-title">{title}</div> : null}
      <canvas
        ref={canvas}
        className="cx-eye-canvas"
        style={{ width: size.width, height: size.height }}
        onPointerMove={locate}
        onPointerLeave={() => setHovered(null)}
        role="img"
        aria-label={title ?? t('What the eye sees', 'Lo que ve el ojo')}
      />
      {!compact ? (
        <div className="cx-eye-readout" aria-live="polite">
          {readout ?? t('Point at a column to read what it sees.', 'Apunte a una columna para leer lo que ve.')}
        </div>
      ) : null}
    </div>
  );
}
