import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { EyeManifest } from '../lib/eye';
import { COLUMNS } from '../lib/eye';
import { useNumber, useT } from '../lib/i18n';
import { signedColour } from './colour';

// The same hexagonal geometry the eye's own view uses (the engine samples column (u, v) 13 pixels apart on
// the row axis and 13 v across, so the lattice is a hexagonal one stretched horizontally). Drawing the
// activity on exactly those hexagons is the point: a cell's response sits where the column that drove it
// looks.
const STEP = 13;
const R = STEP / Math.sqrt(3);
const STRETCH = STEP / (1.5 * R);
const HEX = Array.from({ length: 6 }, (_, k) => {
  const a = (Math.PI / 3) * k;
  return [Math.cos(a) * R * STRETCH, Math.sin(a) * R] as const;
});

export default function ActivityLattice({
  manifest, values, step, centre, spread, title, subtitle, onHover, hovered, compact = true,
}: {
  manifest: EyeManifest;
  values: Float32Array;          // (steps * columns) in the engine's units
  step: number;
  centre: number;                // this cell type's resting level over the clip
  spread: number;                // how far it moves from it (the 95th percentile of the distance)
  title: string;
  subtitle?: string;
  onHover?: (column: number | null) => void;
  hovered?: number | null;
  compact?: boolean;
}) {
  const t = useT();
  const num = useNumber();
  const host = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  const { row_px: rows, col_px: cols } = manifest.lattice;

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

  const fit = useMemo(() => {
    const reserve = compact ? 0 : 40;
    const spanX = Math.max(...cols) - Math.min(...cols) + 2 * R * STRETCH;
    const spanY = Math.max(...rows) - Math.min(...rows) + 2 * R;
    const value = Math.max(Math.min(size.width / spanX, (size.height - reserve) / spanY), 0.01);
    return { scale: value, cx: size.width / 2, cy: (size.height - reserve) / 2 + (compact ? 0 : 20) };
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
    const faint = style.getPropertyValue('--color-fg-faint').trim() || '#8b949e';
    ctx.clearRect(0, 0, size.width, size.height);

    const base = step * COLUMNS;
    const safe = Math.max(spread, 1e-9);
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
      ctx.fillStyle = signedColour(((values[base + c] ?? 0) - centre) / safe);
      ctx.fill();
      if (hovered === c) {
        ctx.strokeStyle = faint;
        ctx.lineWidth = 2;
        ctx.stroke();
      }
    }
    const left = fit.cx + (Math.min(...cols) - R * STRETCH) * fit.scale;
    const right = fit.cx + (Math.max(...cols) + R * STRETCH) * fit.scale;
    const top = fit.cy + (Math.min(...rows) - R) * fit.scale;
    const bottom = fit.cy + (Math.max(...rows) + R) * fit.scale;
    element.dataset.painted = [left, top, right, bottom].map((v) => v.toFixed(1)).join(',');
    element.dataset.columns = String(COLUMNS);
  }, [size, fit, values, step, centre, spread, hovered, cols, rows]);

  const locate = useCallback((event: React.PointerEvent) => {
    if (!onHover) return;
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

  const reading = hovered != null && hovered >= 0
    ? `${num(values[step * COLUMNS + hovered] ?? 0, 3)}`
    : null;

  return (
    <div className="cx-activity">
      <div className="cx-activity-head" title={subtitle ? `${title}: ${subtitle}` : title}>
        <strong>{title}</strong>
        {subtitle ? <span className="cx-muted">{subtitle}</span> : null}
        <span className="cx-activity-value">{reading ?? t('hover', 'apunte')}</span>
      </div>
      {/* the measured box is the canvas's OWN space, not the card's: a canvas sized from the card
          overflows it by the height of the heading and covers whatever is beside it */}
      <div className="cx-activity-canvas" ref={host}>
        <canvas
          ref={canvas}
          className="cx-eye-canvas"
          style={{ width: size.width, height: size.height }}
          onPointerMove={locate}
          onPointerLeave={() => onHover?.(null)}
          role="img"
          aria-label={`${title}${subtitle ? `, ${subtitle}` : ''}`}
        />
      </div>
    </div>
  );
}
