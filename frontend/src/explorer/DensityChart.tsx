import { useEffect, useMemo, useRef, useState } from 'react';
import type { CellType } from '../lib/contract.types';
import { useNumber, useT } from '../lib/i18n';

// The placement rule of the build (data-pipeline/conectoma/connectome/malecns.py, `placement`): a type with
// measured density rho (cells per column) goes on every k-th column along both axes with
// k = round(1 / sqrt(rho)), capped at MAX_STRIDE; below 1 / (MAX_STRIDE + 0.5)^2 it becomes one population
// node. The chart draws that rule and every type on it, so the reader sees why a type is where it is.
export const MAX_STRIDE = 4;
export const POPULATION_BELOW = 1 / (MAX_STRIDE + 0.5) ** 2;
export const LATTICE_COLUMNS = 721;

const X_MIN = 1e-3;
const X_MAX = 3;
const Y_MIN = 1e-3;
const Y_MAX = 3;
const MARGIN = { left: 56, right: 14, top: 8, bottom: 42 };

/** cells per column the network gives a type with this pattern */
export function networkDensity(type: CellType): number {
  return type.pattern[0] === 'stride' ? 1 / type.pattern[1][0] ** 2 : 1 / LATTICE_COLUMNS;
}

export default function DensityChart({ types, selected, caption, onSelect }: {
  types: CellType[];
  selected: string;
  /** what the header says about the selected type while no other type is pointed at */
  caption: string;
  onSelect: (name: string) => void;
}) {
  const t = useT();
  const num = useNumber();
  const [hovered, setHovered] = useState<CellType | null>(null);
  const body = useRef<HTMLDivElement>(null);
  const [{ width, height }, setSize] = useState({ width: 0, height: 0 });

  useEffect(() => {
    const element = body.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => {
      const { width: w, height: h } = entry.contentRect;
      if (w > 0 && h > 0) setSize({ width: w, height: h });
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const plotW = Math.max(0, width - MARGIN.left - MARGIN.right);
  const plotH = Math.max(0, height - MARGIN.top - MARGIN.bottom);
  const lx = (x: number) => MARGIN.left + (plotW * (Math.log10(x) - Math.log10(X_MIN))) / (Math.log10(X_MAX) - Math.log10(X_MIN));
  const ly = (y: number) => MARGIN.top + plotH - (plotH * (Math.log10(y) - Math.log10(Y_MIN))) / (Math.log10(Y_MAX) - Math.log10(Y_MIN));

  // the bands of the rule along the measured density, left to right
  const bands = useMemo(() => {
    const edges = [X_MIN, POPULATION_BELOW];
    for (let k = MAX_STRIDE - 1; k >= 1; k--) edges.push(1 / (k + 0.5) ** 2);
    edges.push(X_MAX);
    const labels = [t('population node', 'nodo de población'), ...[4, 3, 2, 1].map((k) => `k = ${k}`)];
    const levels = [1 / LATTICE_COLUMNS, ...[4, 3, 2, 1].map((k) => 1 / k ** 2)];
    return labels.map((label, i) => ({ from: edges[i], to: edges[i + 1], label, level: levels[i] }));
  }, [t]);

  const dots = useMemo(
    () =>
      types.map((type, i) => ({
        type,
        x: lx(Math.max(type.density ?? 0, X_MIN)),
        // spread a little vertically, so types with equal placement do not hide each other
        y: ly(networkDensity(type)) + ((i % 5) - 2) * 2.4,
      })),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [types, width, height],
  );
  const chosen = dots.find((d) => d.type.name === selected);

  const describe = (type: CellType) => {
    const where = type.pattern[0] === 'stride'
      ? type.pattern[1][0] === 1
        ? t('every column', 'cada columna')
        : t(`every ${type.pattern[1][0]}th column along both axes`, `cada ${type.pattern[1][0]} columnas en ambos ejes`)
      : t('one population node', 'un nodo de población');
    return t(
      `${type.name}: ${num(type.density ?? 0, 3)} cells per column in the eye; the network puts it on ${where}${type.photoreceptor ? ' (an input: always every column)' : ''}.`,
      `${type.name}: ${num(type.density ?? 0, 3)} células por columna en el ojo; la red lo ubica en ${where}${type.photoreceptor ? ' (una entrada: siempre cada columna)' : ''}.`,
    );
  };

  const ready = plotW >= 60 && plotH >= 60;
  const xTicks = [0.001, 0.01, 0.1, 1];
  const yTicks: [number, string][] = [[1 / LATTICE_COLUMNS, '1/721'], [1 / 16, '1/16'], [1 / 9, '1/9'], [1 / 4, '1/4'], [1, '1']];

  return (
    <div className="cx-density">
      <div className="cx-density-head">
        <div className="cx-density-title">{t('Why each type sits where it does', 'Por qué cada tipo está donde está')}</div>
        <p className="cx-density-readout" aria-live="polite">{hovered ? describe(hovered) : caption}</p>
        <p className="cx-density-hint">
          {t('Point at a type to read it; click to choose it. k is the stride; the dashed diagonal is where the network would match the eye.', 'Apunte a un tipo para leerlo; haga clic para elegirlo. k es el paso; la diagonal punteada es donde la red coincidiría con el ojo.')}
        </p>
      </div>
      <div className="cx-density-body" ref={body}>
        {ready && (
          <svg width={width} height={height} role="img" aria-label={t('Measured density and placement of every cell type', 'Densidad medida y ubicación de cada tipo celular')}>
            <rect className="cx-density-plot" x={MARGIN.left} y={MARGIN.top} width={plotW} height={plotH} />
            {bands.map((band, i) => (
              <g key={band.label}>
                <rect
                  className={i % 2 ? 'cx-density-band alt' : 'cx-density-band'}
                  x={lx(band.from)}
                  y={MARGIN.top}
                  width={lx(band.to) - lx(band.from)}
                  height={plotH}
                />
                {i > 0 && <line className="cx-density-threshold" x1={lx(band.from)} x2={lx(band.from)} y1={MARGIN.top} y2={MARGIN.top + plotH} />}
                <line className="cx-density-rule" x1={lx(band.from)} x2={lx(band.to)} y1={ly(band.level)} y2={ly(band.level)} />
                <text
                  className="cx-density-band-label"
                  x={(lx(band.from) + lx(band.to)) / 2}
                  y={MARGIN.top + 14}
                  textAnchor="middle"
                >
                  {lx(band.to) - lx(band.from) > 44 ? band.label : band.label.replace('k = ', '')}
                </text>
              </g>
            ))}
            <line className="cx-density-identity" x1={lx(X_MIN)} y1={ly(Y_MIN)} x2={lx(X_MAX)} y2={ly(Y_MAX)} />
            <g className="cx-density-axis">
              {xTicks.map((x) => (
                <g key={x}>
                  <line x1={lx(x)} x2={lx(x)} y1={MARGIN.top + plotH} y2={MARGIN.top + plotH + 5} />
                  <text x={lx(x)} y={MARGIN.top + plotH + 17} textAnchor="middle">{num(x, x < 0.01 ? 3 : x < 0.1 ? 2 : x < 1 ? 1 : 0)}</text>
                </g>
              ))}
              <text x={MARGIN.left + plotW / 2} y={height - 6} textAnchor="middle">
                {t('measured cells per column in the eye (log)', 'células medidas por columna en el ojo (log)')}
              </text>
              {yTicks.map(([y, label]) => (
                <g key={label}>
                  <line x1={MARGIN.left - 5} x2={MARGIN.left} y1={ly(y)} y2={ly(y)} />
                  <text x={MARGIN.left - 8} y={ly(y) + 4} textAnchor="end">{label}</text>
                </g>
              ))}
              <text transform={`translate(13, ${MARGIN.top + plotH / 2}) rotate(-90)`} textAnchor="middle">
                {t('cells per column in the network', 'células por columna en la red')}
              </text>
            </g>
            {dots.map(({ type, x, y }) =>
              type.photoreceptor ? (
                <rect
                  key={type.name}
                  className={`cx-density-dot ${type.sign > 0 ? 'exc' : type.sign < 0 ? 'inh' : 'none'}`}
                  x={x - 4.5}
                  y={y - 4.5}
                  width={9}
                  height={9}
                  onMouseEnter={() => setHovered(type)}
                  onMouseLeave={() => setHovered(null)}
                  onClick={() => onSelect(type.name)}
                />
              ) : (
                <circle
                  key={type.name}
                  className={`cx-density-dot ${type.sign > 0 ? 'exc' : type.sign < 0 ? 'inh' : 'none'}`}
                  cx={x}
                  cy={y}
                  r={4.5}
                  onMouseEnter={() => setHovered(type)}
                  onMouseLeave={() => setHovered(null)}
                  onClick={() => onSelect(type.name)}
                />
              ),
            )}
            {chosen && (
              <>
                <circle className="cx-density-selected" cx={chosen.x} cy={chosen.y} r={9} />
                <text
                  className="cx-density-label"
                  x={chosen.x > MARGIN.left + plotW - 80 ? chosen.x - 13 : chosen.x + 13}
                  y={chosen.y - 10}
                  textAnchor={chosen.x > MARGIN.left + plotW - 80 ? 'end' : 'start'}
                >
                  {chosen.type.name}
                </text>
              </>
            )}
          </svg>
        )}
      </div>
    </div>
  );
}
