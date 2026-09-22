import { useEffect, useMemo, useRef } from 'react';
import uPlot from 'uplot';
import 'uplot/dist/uPlot.min.css';
import { COLUMNS, depthOf, type DecodedLevel, type EyeClip } from '../lib/eye';
import { useNumber, useT } from '../lib/i18n';
import type { View } from './EyeLattice';

// Six levels, ordered from the first to the last: a cool-to-warm sequence that reads on both themes.
export const LEVEL_COLOURS = ['#2c7fb8', '#41b6c4', '#66a61e', '#e6ab02', '#f46d43', '#d73027'];

/** The per-frame statistic the chart draws for a view, and its axis label. */
export function statistic(view: View, clip: EyeClip, level: DecodedLevel, frame: number): number | null {
  const base = frame * COLUMNS;
  if (view === 'lum') {
    let sum = 0;
    for (let c = 0; c < COLUMNS; c++) sum += level.lum[base + c];
    return sum / COLUMNS / 255;
  }
  if (view === 'depth') {
    const values: number[] = [];
    for (let c = 0; c < COLUMNS; c++) {
      const d = depthOf(level.depth[base + c], clip.depth.near_m, clip.depth.far_m);
      if (!Number.isNaN(d)) values.push(d);
    }
    if (!values.length) return null;
    values.sort((a, b) => a - b);
    return values[Math.floor(values.length / 2)];
  }
  if (view === 'flow') {
    if (!level.flow || !clip.flow || frame >= clip.frames - 1) return null;
    const row = frame * 2 * COLUMNS;
    const s = clip.flow.scale / 127;
    let sum = 0;
    for (let c = 0; c < COLUMNS; c++) sum += Math.hypot(level.flow[row + c], level.flow[row + COLUMNS + c]) * s;
    return sum / COLUMNS;
  }
  const layer = view === 'boundary' ? level.boundary : level[view];
  if (!layer) return null;
  let count = 0;
  const threshold = view === 'boundary' ? 1 : 128;
  for (let c = 0; c < COLUMNS; c++) if (layer[base + c] >= threshold) count += 1;
  return count / COLUMNS;
}

export default function TimeCourse({ clip, levels, labels, view, frame, onFrame }: {
  clip: EyeClip;
  levels: DecodedLevel[];
  labels: string[];
  view: View;
  frame: number;
  onFrame: (frame: number) => void;
}) {
  const t = useT();
  const num = useNumber();
  const host = useRef<HTMLDivElement>(null);
  const plot = useRef<uPlot | null>(null);
  const current = useRef(frame);
  const pick = useRef(onFrame);
  pick.current = onFrame;

  const axis: Record<View, string> = {
    lum: t('mean luminance', 'luminancia media'),
    depth: clip.depth.units === 'metres' ? t('median depth (m)', 'profundidad mediana (m)') : t('median depth (scene units)', 'profundidad mediana (unidades de escena)'),
    flow: t('mean flow (engine units per frame)', 'flujo medio (unidades del motor por cuadro)'),
    figure: t('share of columns that are figure', 'fracción de columnas que son figura'),
    boundary: t('share of columns on a boundary', 'fracción de columnas en un borde'),
    sky: t('share of columns that are sky', 'fracción de columnas que son cielo'),
    labelled: t('share of columns labelled', 'fracción de columnas etiquetadas'),
  };

  const data = useMemo(() => {
    const x = Array.from({ length: clip.frames }, (_, i) => i);
    const series = levels.map((level) => x.map((f) => statistic(view, clip, level, f)));
    return [x, ...series] as uPlot.AlignedData;
  }, [clip, levels, view]);

  useEffect(() => {
    const element = host.current;
    if (!element) return;
    const style = getComputedStyle(element);
    const fg = style.getPropertyValue('--color-fg-subtle').trim() || '#57606a';
    const grid = style.getPropertyValue('--color-border').trim() || '#d8dee4';
    const accent = style.getPropertyValue('--color-accent').trim() || '#0969da';
    const marker: uPlot.Plugin = {
      hooks: {
        draw: (u) => {
          const x = u.valToPos(current.current, 'x', true);
          const ctx = u.ctx;
          ctx.save();
          ctx.strokeStyle = accent;
          ctx.lineWidth = 2 * devicePixelRatio;
          ctx.beginPath();
          ctx.moveTo(x, u.bbox.top);
          ctx.lineTo(x, u.bbox.top + u.bbox.height);
          ctx.stroke();
          ctx.restore();
        },
      },
    };
    const options: uPlot.Options = {
      width: element.clientWidth,
      height: Math.max(element.clientHeight - 36, 160),
      plugins: [marker],
      scales: { x: { time: false } },
      axes: [
        { stroke: fg, grid: { stroke: grid }, ticks: { stroke: grid }, label: t('frame', 'cuadro'),
          values: (_u, ticks) => ticks.map((v) => num(v + 1)) },
        { stroke: fg, grid: { stroke: grid }, ticks: { stroke: grid }, label: axis[view], size: 64,
          values: (_u, ticks) => ticks.map((v) => num(v, Math.abs(v) < 1 && v !== 0 ? 3 : Math.abs(v) < 10 ? 2 : 0)) },
      ],
      series: [
        { label: t('frame', 'cuadro'), value: (_u, v) => (v === null || v === undefined ? '-' : num(v + 1)) },
        ...labels.map((label, i) => ({
          label, stroke: LEVEL_COLOURS[i % LEVEL_COLOURS.length], width: 2, spanGaps: false,
          value: (_u: uPlot, v: number | null) => (v === null || v === undefined ? '-' : num(v, Math.abs(v) < 1 ? 3 : 2)),
        })),
      ],
      legend: { live: true },
      cursor: { drag: { x: false, y: false } },
    };
    const u = new uPlot(options, data, element);
    plot.current = u;
    u.over.addEventListener('click', () => {
      const left = u.cursor.left ?? -1;
      if (left >= 0) pick.current(Math.round(u.posToVal(left, 'x')));
    });
    const observer = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      if (width > 0 && height > 0) u.setSize({ width, height: Math.max(height - 36, 160) });
    });
    observer.observe(element);
    return () => {
      observer.disconnect();
      u.destroy();
      plot.current = null;
    };
    // the options depend on the language, the view and the labels; data changes are pushed below
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, labels.join('|'), t('frame', 'cuadro')]);

  useEffect(() => {
    plot.current?.setData(data);
  }, [data]);

  useEffect(() => {
    current.current = frame;
    plot.current?.redraw(false);
  }, [frame]);

  return <div className="cx-timecourse" ref={host} role="figure" aria-label={axis[view]} />;
}
