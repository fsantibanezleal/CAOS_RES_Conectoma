import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import type { EyeManifest } from '../lib/eye';
import { COLUMNS } from '../lib/eye';
import { parseRgb } from './colour';

// The eye's own hexagonal geometry (see EyeLattice): columns sampled 13 px apart on the row axis and
// 13 v across, tiled exactly by flat-topped hexagons stretched horizontally. Every map of the chain is
// drawn on it, so a column sits in the same place in every map and a reader's eye can travel between them.
const STEP = 13;
const R = STEP / Math.sqrt(3);
const STRETCH = STEP / (1.5 * R);
const HEX = Array.from({ length: 6 }, (_, k) => {
  const a = (Math.PI / 3) * k;
  return [Math.cos(a) * R * STRETCH, Math.sin(a) * R] as const;
});

/**
 * One map of the chain: a colour per column, the columns the network refused drawn faint and dotted, and
 * a pointed column marked in every map at once.
 *
 * The colours arrive as a function and a `revision` that changes whenever they do, so the canvas redraws
 * exactly when the picture changes and never on a render that changed nothing.
 */
export default function HexMap({
  manifest, colourOf, faintOf, revision, hovered, onHover, title, subtitle, legend, reading, label,
}: {
  manifest: EyeManifest;
  colourOf: (column: number) => string | null;
  faintOf?: (column: number) => boolean;
  revision: string;
  hovered: number | null;
  onHover: (column: number | null) => void;
  title: string;
  subtitle?: string;
  legend?: ReactNode;
  reading?: string | null;
  label: string;
}) {
  const host = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  const { row_px: rows, col_px: cols } = manifest.lattice;

  useEffect(() => {
    const element = host.current;
    if (!element) return undefined;
    const observer = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      if (width > 0 && height > 0) setSize({ width, height });
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const fit = useMemo(() => {
    const spanX = Math.max(...cols) - Math.min(...cols) + 2 * R * STRETCH;
    const spanY = Math.max(...rows) - Math.min(...rows) + 2 * R;
    const scale = Math.max(Math.min(size.width / spanX, size.height / spanY), 0.01);
    return { scale, cx: size.width / 2, cy: size.height / 2 };
  }, [cols, rows, size]);

  // one path per column, built once per size rather than once per frame
  const paths = useMemo(() => {
    if (typeof Path2D === 'undefined' || size.width === 0) return [];
    return Array.from({ length: COLUMNS }, (_, c) => {
      const path = new Path2D();
      const x = fit.cx + cols[c] * fit.scale;
      const y = fit.cy + rows[c] * fit.scale;
      HEX.forEach(([dx, dy], k) => {
        const px = x + dx * fit.scale * 0.95;
        const py = y + dy * fit.scale * 0.95;
        if (k === 0) path.moveTo(px, py);
        else path.lineTo(px, py);
      });
      path.closePath();
      return path;
    });
  }, [fit, cols, rows, size.width]);

  useEffect(() => {
    const element = canvas.current;
    if (!element || size.width === 0 || !paths.length) return;
    const ratio = window.devicePixelRatio || 1;
    if (element.width !== Math.round(size.width * ratio)) element.width = Math.round(size.width * ratio);
    if (element.height !== Math.round(size.height * ratio)) element.height = Math.round(size.height * ratio);
    const ctx = element.getContext('2d');
    if (!ctx) return;
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    const style = getComputedStyle(element);
    const surface = style.getPropertyValue('--color-surface').trim() || '#ffffff';
    const faint = style.getPropertyValue('--color-fg-faint').trim() || '#8b949e';
    const accent = parseRgb(style.getPropertyValue('--color-accent'), [9, 105, 218]);
    ctx.clearRect(0, 0, size.width, size.height);
    for (let c = 0; c < COLUMNS; c++) {
      const fill = colourOf(c);
      const path = paths[c];
      if (fill === null) {
        ctx.fillStyle = surface;
        ctx.fill(path);
        ctx.strokeStyle = faint;
        ctx.globalAlpha = 0.5;
        ctx.lineWidth = 0.6;
        ctx.stroke(path);
        ctx.globalAlpha = 1;
        continue;
      }
      const refused = faintOf?.(c) ?? false;
      ctx.globalAlpha = refused ? 0.28 : 1;
      ctx.fillStyle = fill;
      ctx.fill(path);
      ctx.globalAlpha = 1;
      if (refused) {
        // a refused column keeps its colour, faint, with a dot: the network answered and then said it
        // could not stand behind the answer
        const x = fit.cx + cols[c] * fit.scale;
        const y = fit.cy + rows[c] * fit.scale;
        ctx.fillStyle = faint;
        ctx.beginPath();
        ctx.arc(x, y, Math.max(fit.scale * 1.4, 0.8), 0, Math.PI * 2);
        ctx.fill();
      }
    }
    if (hovered != null && hovered >= 0 && paths[hovered]) {
      ctx.strokeStyle = `rgb(${accent.join(',')})`;
      ctx.lineWidth = 2.5;
      ctx.stroke(paths[hovered]);
    }
    const left = fit.cx + (Math.min(...cols) - R * STRETCH) * fit.scale;
    const right = fit.cx + (Math.max(...cols) + R * STRETCH) * fit.scale;
    const top = fit.cy + (Math.min(...rows) - R) * fit.scale;
    const bottom = fit.cy + (Math.max(...rows) + R) * fit.scale;
    element.dataset.painted = [left, top, right, bottom].map((v) => v.toFixed(1)).join(',');
    element.dataset.columns = String(COLUMNS);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [paths, revision, hovered, size]);

  const locate = useCallback((event: React.PointerEvent) => {
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
    onHover(distance <= (STEP * 0.8) ** 2 ? best : null);
  }, [cols, fit, onHover, rows]);

  return (
    <figure className="cx-chain-map" data-map={label}>
      <figcaption className="cx-chain-head">
        <strong>{title}</strong>
        {subtitle ? <span className="cx-muted">{subtitle}</span> : null}
      </figcaption>
      <div className="cx-chain-canvas" ref={host}>
        <canvas
          ref={canvas}
          className="cx-eye-canvas"
          style={{ width: size.width, height: size.height }}
          onPointerMove={locate}
          onPointerLeave={() => onHover(null)}
          role="img"
          aria-label={subtitle ? `${title}, ${subtitle}` : title}
        />
      </div>
      <div className="cx-chain-foot">
        {legend}
        <span className="cx-chain-reading" aria-live="polite">{reading ?? ' '}</span>
      </div>
    </figure>
  );
}
