import { useEffect, useMemo, useRef } from 'react';
import uPlot from 'uplot';
import 'uplot/dist/uPlot.min.css';
import { useNumber, useT } from '../lib/i18n';
import { LEVEL_COLOURS } from './TimeCourse';

export interface Series {
  label: string;
  values: number[];
}

/**
 * Labelled series against a step axis, with the playing position marked and clickable.
 *
 * The same uPlot conventions as the eye's time course (theme colours read from the shell, a live legend,
 * a cursor line at the current step, click to jump), for data that is not an eye clip: here, what one
 * column's cells did over a clip.
 */
export default function SeriesChart({ series, frame, onFrame, xLabel, yLabel }: {
  series: Series[];
  frame: number;
  onFrame: (value: number) => void;
  xLabel: string;
  yLabel: string;
}) {
  const t = useT();
  const num = useNumber();
  const host = useRef<HTMLDivElement>(null);
  const plot = useRef<uPlot | null>(null);
  const current = useRef(frame);
  const pick = useRef(onFrame);
  pick.current = onFrame;

  const data = useMemo(() => {
    const length = series.reduce((most, one) => Math.max(most, one.values.length), 0);
    const x = Array.from({ length }, (_, i) => i);
    return [x, ...series.map((one) => one.values)] as unknown as uPlot.AlignedData;
  }, [series]);

  useEffect(() => {
    const element = host.current;
    if (!element || !series.length) return undefined;
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
        { stroke: fg, grid: { stroke: grid }, ticks: { stroke: grid }, label: xLabel,
          values: (_u, ticks) => ticks.map((v) => num(v + 1)) },
        { stroke: fg, grid: { stroke: grid }, ticks: { stroke: grid }, label: yLabel, size: 70,
          values: (_u, ticks) => ticks.map((v) => num(v, Math.abs(v) < 1 && v !== 0 ? 3 : 2)) },
      ],
      series: [
        { label: xLabel, value: (_u, v) => (v === null || v === undefined ? '-' : num(v + 1)) },
        ...series.map((one, i) => ({
          label: one.label,
          stroke: LEVEL_COLOURS[i % LEVEL_COLOURS.length],
          width: 2,
          spanGaps: false,
          value: (_u: uPlot, v: number | null) => (v === null || v === undefined ? '-' : num(v, 3)),
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
  }, [data, num, series, t, xLabel, yLabel]);

  useEffect(() => {
    current.current = frame;
    plot.current?.redraw();
  }, [frame]);

  return <div className="cx-timecourse" ref={host} />;
}
