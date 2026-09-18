import { useEffect, useMemo, useRef, useState } from 'react';
import type { Direction, Filter } from './model';
import { useNumber, useT } from '../lib/i18n';

export interface Panel {
  key: string;
  title: string;
  filter: Filter;
  sign: number;
}

interface Hovered {
  panel: string;
  u: number;
  v: number;
  n: number;
}

const SQRT3 = Math.sqrt(3);
const GAP = 16;
/** room kept clear of the filter for the title above it and the readout below it */
const OVERLAY = 30;

function hexDistance(u: number, v: number): number {
  return Math.max(Math.abs(u), Math.abs(v), Math.abs(u + v));
}

/**
 * A filter drawn on the hexagonal lattice. With `receives`, the target cell sits at the centre and every
 * hexagon is the column its source cells sit in, relative to it (the filter's offsets negated, because an
 * offset points from a source to its target); with `sends`, the source sits at the centre and each hexagon
 * is a column its targets sit in. Several panels share one colour scale so they compare by eye.
 *
 * The hexagon size is set so the whole filter fits the panel; the lattice then continues to the panel's
 * edges, because the eye's columns do: the columns beyond the filter's reach are drawn fainter, empty.
 */
export default function HexFilter({ panels, direction, minimum }: {
  panels: Panel[];
  direction: Direction;
  minimum: number;
}) {
  const t = useT();
  const num = useNumber();
  const host = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  const [hovered, setHovered] = useState<Hovered | null>(null);

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

  const flip = direction === 'receives' ? -1 : 1;
  const prepared = useMemo(
    () =>
      panels.map((panel) => {
        const cells = new Map<string, number>();
        panel.filter.du.forEach((du, i) => {
          if (panel.filter.n[i] < minimum) return;
          cells.set(`${flip * du},${flip * panel.filter.dv[i]}`, panel.filter.n[i]);
        });
        return { ...panel, cells };
      }),
    [panels, flip, minimum],
  );

  // the reach of the filter: the farthest column any panel draws, plus one ring of context
  const reach = useMemo(() => {
    let r = 3;
    for (const panel of prepared) {
      for (const key of panel.cells.keys()) {
        const [u, v] = key.split(',').map(Number);
        r = Math.max(r, hexDistance(u, v) + 1);
      }
    }
    return Math.min(r, 18);
  }, [prepared]);

  const maxValue = useMemo(
    () => Math.max(1e-9, ...prepared.flatMap((p) => [...p.cells.values()])),
    [prepared],
  );

  const count = Math.max(1, prepared.length);
  const panelWidth = Math.max(0, (size.width - GAP * (count - 1)) / count);
  const panelHeight = size.height;
  // a hexagon of size s spans sqrt(3)*s across and 1.5*s down per ring
  const hexSize = Math.max(
    3,
    Math.min(panelWidth / (SQRT3 * (2 * reach + 1)), (panelHeight - 2 * OVERLAY) / (3 * reach + 2)),
  );

  // every column whose hexagon reaches into the panel, in lattice coordinates around the centre
  const lattice = useMemo(() => {
    if (panelWidth <= 0 || panelHeight <= 0) return [];
    const out: [number, number][] = [];
    const rows = Math.ceil(panelHeight / 2 / (1.5 * hexSize)) + 1;
    const across = Math.ceil(panelWidth / 2 / (SQRT3 * hexSize)) + 1;
    for (let v = -rows; v <= rows; v++) {
      const shift = Math.round(v / 2);
      for (let k = -across - 1; k <= across + 1; k++) out.push([k - shift, v]);
    }
    return out;
  }, [panelWidth, panelHeight, hexSize]);

  function hexPoints(cx: number, cy: number): string {
    const points: string[] = [];
    for (let k = 0; k < 6; k++) {
      const angle = (Math.PI / 180) * (60 * k - 30);
      points.push(`${(cx + hexSize * 0.94 * Math.cos(angle)).toFixed(1)},${(cy + hexSize * 0.94 * Math.sin(angle)).toFixed(1)}`);
    }
    return points.join(' ');
  }

  return (
    <div className="cx-hex" ref={host}>
      {size.width > 0 && prepared.map((panel, p) => {
        const ox = panelWidth / 2;
        const oy = panelHeight / 2;
        const colour = panel.sign >= 0 ? 'var(--cx-exc)' : 'var(--cx-inh)';
        const hover = hovered?.panel === panel.key ? hovered : null;
        return (
          <div
            key={panel.key}
            className="cx-hex-panel"
            style={{ width: panelWidth, left: p * (panelWidth + GAP) }}
          >
            <svg
              width={panelWidth}
              height={panelHeight}
              role="img"
              aria-label={panel.title}
              onMouseLeave={() => setHovered(null)}
            >
              {lattice.map(([u, v]) => {
                const x = ox + hexSize * SQRT3 * (u + v / 2);
                const y = oy + hexSize * 1.5 * v;
                if (x < -hexSize || x > panelWidth + hexSize || y < -hexSize || y > panelHeight + hexSize) return null;
                const value = panel.cells.get(`${u},${v}`);
                const share = value === undefined ? 0 : Math.sqrt(value / maxValue);
                const fill = value === undefined
                  ? 'transparent'
                  : `color-mix(in srgb, ${colour} ${Math.round(18 + 82 * share)}%, var(--color-surface-2))`;
                const kind = u === 0 && v === 0
                  ? 'cx-hex-cell cx-hex-centre'
                  : hexDistance(u, v) > reach ? 'cx-hex-cell far' : 'cx-hex-cell';
                return (
                  <polygon
                    key={`${u},${v}`}
                    points={hexPoints(x, y)}
                    className={kind}
                    style={{ fill }}
                    onMouseEnter={() => setHovered({ panel: panel.key, u, v, n: value ?? 0 })}
                  />
                );
              })}
              <g className="cx-hex-axes" transform={`translate(${panelWidth - 52}, ${panelHeight - 14})`}>
                <line x1={0} y1={0} x2={28} y2={0} />
                <text x={32} y={4}>u</text>
                <line x1={0} y1={0} x2={14} y2={-24} />
                <text x={10} y={-28}>v</text>
              </g>
            </svg>
            <div className="cx-hex-title">{panel.title}</div>
            <div className="cx-hex-readout" aria-live="polite">
              {hover
                ? t(
                    `column (${hover.u}, ${hover.v}): ${num(hover.n, 2)} synapses per target cell`,
                    `columna (${hover.u}, ${hover.v}): ${num(hover.n, 2)} sinapsis por célula destino`,
                  )
                : t(
                    `${panel.cells.size} columns carry synapses, peak ${num(Math.max(0, ...panel.cells.values()), 2)}`,
                    `${panel.cells.size} columnas con sinapsis, máximo ${num(Math.max(0, ...panel.cells.values()), 2)}`,
                  )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
