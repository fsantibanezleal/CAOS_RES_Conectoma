import { useEffect, useMemo, useRef, useState } from 'react';
import type { CellType } from '../lib/contract.types';
import { useNumber, useT } from '../lib/i18n';
import DensityChart, { LATTICE_COLUMNS } from './DensityChart';

const SQRT3 = Math.sqrt(3);
const EXTENT = 15; // the network's lattice radius: 721 columns, the published model's size
const GAP = 16;
const CHART_MIN = 280;

/**
 * Where the network places the cells of one type on its lattice (every column, every k-th column along
 * both axes, or one population node at the centre), beside the rule that decided it for every type. The
 * lattice takes the height of the stage; the chart, whose header explains the selected type, takes the rest.
 */
export default function Placement({ type, types, eyeColumns, onSelect }: {
  type: CellType;
  types: CellType[];
  eyeColumns: number;
  onSelect: (name: string) => void;
}) {
  const t = useT();
  const num = useNumber();
  const host = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });

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

  const stride = type.pattern[0] === 'stride' ? type.pattern[1][0] : 0;
  const columns = useMemo(() => {
    const out: [number, number, boolean][] = [];
    for (let u = -EXTENT; u <= EXTENT; u++) {
      for (let v = Math.max(-EXTENT, -EXTENT - u); v <= Math.min(EXTENT, EXTENT - u); v++) {
        const occupied = stride === 0 ? u === 0 && v === 0 : u % stride === 0 && v % stride === 0;
        out.push([u, v, occupied]);
      }
    }
    return out;
  }, [stride]);

  // the lattice spans sqrt(3)*(2E+1) hexagon sizes across and 3E+2 down
  const aspect = (SQRT3 * (2 * EXTENT + 1)) / (3 * EXTENT + 2);
  const latticeWidth = Math.max(0, Math.min(size.height * aspect, size.width - GAP - CHART_MIN));
  const chartWidth = Math.max(0, size.width - latticeWidth - GAP);
  const hexSize = Math.max(1, Math.min(latticeWidth / (SQRT3 * (2 * EXTENT + 1)), size.height / (3 * EXTENT + 2)));
  const ox = latticeWidth / 2;
  const oy = size.height / 2;
  const occupied = columns.filter((c) => c[2]).length;
  const tone = type.sign > 0 ? '' : type.sign < 0 ? ' inh' : ' none';

  const caption = stride === 0
    ? t(
        `${type.name} has ${num(type.cells ?? 0)} cells in the eye (${num(100 * (type.density ?? 0), 1)} per hundred columns), fewer than one per twenty columns, so it is one population node at the centre: it stands for the mean activity of its cells and drives every cell of its targets.`,
        `${type.name} tiene ${num(type.cells ?? 0)} células en el ojo (${num(100 * (type.density ?? 0), 1)} por cada cien columnas), menos de una cada veinte columnas, así que es un nodo de población en el centro: representa la actividad media de sus células y excita o inhibe a todas las células de sus destinos.`,
      )
    : t(
        `${type.name}: ${num(type.cells_placed ?? 0)} placed cells over ${num(eyeColumns)} columns, ${num(type.density ?? 0, 2)} per column, laid out on ${occupied} of the ${LATTICE_COLUMNS} lattice columns (${num(1 / (stride * stride), 2)} per column).`,
        `${type.name}: ${num(type.cells_placed ?? 0)} células ubicadas en ${num(eyeColumns)} columnas, ${num(type.density ?? 0, 2)} por columna, dispuestas en ${occupied} de las ${LATTICE_COLUMNS} columnas de la retícula (${num(1 / (stride * stride), 2)} por columna).`,
      );

  function hexPoints(cx: number, cy: number): string {
    const points: string[] = [];
    for (let k = 0; k < 6; k++) {
      const angle = (Math.PI / 180) * (60 * k - 30);
      points.push(`${(cx + hexSize * 0.92 * Math.cos(angle)).toFixed(1)},${(cy + hexSize * 0.92 * Math.sin(angle)).toFixed(1)}`);
    }
    return points.join(' ');
  }

  return (
    <div className="cx-placement">
      <div className="cx-placement-stage" ref={host}>
        {size.width > 0 && (
          <>
            <svg
              width={latticeWidth}
              height={size.height}
              style={{ position: 'absolute', left: 0, top: 0 }}
              role="img"
              aria-label={t(`Placement of ${type.name} on the lattice`, `Ubicación de ${type.name} en la retícula`)}
            >
              {columns.map(([u, v, filled]) => (
                <polygon
                  key={`${u},${v}`}
                  points={hexPoints(ox + hexSize * SQRT3 * (u + v / 2), oy + hexSize * 1.5 * v)}
                  className={filled ? `cx-place filled${tone}` : 'cx-place'}
                />
              ))}
            </svg>
            <div style={{ position: 'absolute', left: latticeWidth + GAP, top: 0, width: chartWidth, height: size.height }}>
              <DensityChart types={types} selected={type.name} caption={caption} onSelect={onSelect} />
            </div>
          </>
        )}
      </div>
    </div>
  );
}
