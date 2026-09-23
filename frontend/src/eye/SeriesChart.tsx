import { useEffect, useMemo, useRef } from 'react';
import uPlot from 'uplot';
import 'uplot/dist/uPlot.min.css';
import { useNumber } from '../lib/i18n';
import { LEVEL_COLOURS } from './TimeCourse';

export interface Series {
  label: string;
  values: number[];
  /** a series read on the right-hand axis, linear, beside errors on the left (e.g. a share of a peak) */
  right?: boolean;
}

/** The finite extent of some series, padded, and positive-only when the axis is logarithmic. */
function extent(data: uPlot.AlignedData, pick: (k: number) => boolean, log: boolean): [number, number] {
  let lo = Infinity;
  let hi = -Infinity;
  for (let k = 1; k < data.length; k++) {
    if (!pick(k)) continue;
    for (const v of data[k] as (number | null)[]) {
      if (v === null || !Number.isFinite(v) || (log && v <= 0)) continue;
      lo = Math.min(lo, v);
      hi = Math.max(hi, v);
    }
  }
  if (!Number.isFinite(lo)) return log ? [0.1, 1] : [0, 1];
  if (log) return [lo / 1.25, hi * 1.25];
  const pad = (hi - lo) * 0.06 || Math.abs(hi) * 0.1 || 1;
  return [lo - pad, hi + pad];
}

/**
 * Labelled series against a step axis, with the playing position marked and clickable.
 *
 * The same uPlot conventions as the eye's time course (theme colours read from the shell, a live legend,
 * a cursor line at the current step, click to jump), for data that is not an eye clip.
 *
 * The ranges are explicit. Left to itself uPlot kept the frame axis at null in the chain view (the failure
 * recorded from CardioPINN and Espira), and a chart whose x scale never ranged draws no line while its axes
 * look fine. A logarithmic left axis is offered because an error that jumps nine-fold for a few frames
 * flattens every other frame on a linear one.
 */
export default function SeriesChart({ series, frame, onFrame, xLabel, yLabel, logY = false, rightLabel }: {
  series: Series[];
  frame: number;
  onFrame: (value: number) => void;
  xLabel: string;
  yLabel: string;
  logY?: boolean;
  rightLabel?: string;
}) {
  const num = useNumber();
  const host = useRef<HTMLDivElement>(null);
  const plot = useRef<uPlot | null>(null);
  const current = useRef(frame);
  const pick = useRef(onFrame);
  pick.current = onFrame;

  const data = useMemo(() => {
    const length = series.reduce((most, one) => Math.max(most, one.values.length), 0);
    const x = Array.from({ length }, (_, i) => i);
    // a gap is null to uPlot, never NaN: NaN poisons its extents
    return [x, ...series.map((one) => one.values.map((v) => (Number.isFinite(v) ? v : null)))] as unknown as uPlot.AlignedData;
  }, [series]);

  useEffect(() => {
    const element = host.current;
    if (!element || !series.length) return undefined;
    const style = getComputedStyle(element);
    const fg = style.getPropertyValue('--color-fg-subtle').trim() || '#57606a';
    const grid = style.getPropertyValue('--color-border').trim() || '#d8dee4';
    const accent = style.getPropertyValue('--color-accent').trim() || '#0969da';
    const hasRight = series.some((one) => one.right);
    const frames = (data[0] as number[]).length;
    const left = extent(data, (k) => !series[k - 1].right, logY);
    const right = extent(data, (k) => !!series[k - 1].right, false);
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
    const axes: uPlot.Axis[] = [
      { stroke: fg, grid: { stroke: grid }, ticks: { stroke: grid }, label: xLabel,
        values: (_u, ticks) => ticks.map((v) => (v == null ? '' : num(v + 1))) },
      { stroke: fg, grid: { stroke: grid }, ticks: { stroke: grid }, label: yLabel, size: 70, scale: 'y',
        // a logarithmic axis leaves some ticks unlabelled by handing over null for them
        values: (_u, ticks) => ticks.map((v) => (v == null ? '' : num(v, Math.abs(v) >= 10 ? 0 : Math.abs(v) >= 1 ? 1 : 2))) },
    ];
    if (hasRight) {
      axes.push({ stroke: fg, grid: { show: false }, ticks: { stroke: grid }, label: rightLabel ?? '', side: 1,
        size: 60, scale: 'right', values: (_u, ticks) => ticks.map((v) => (v == null ? '' : num(v, 2))) });
    }
    const options: uPlot.Options = {
      width: element.clientWidth,
      height: Math.max(element.clientHeight - 36, 160),
      plugins: [marker],
      scales: {
        x: { time: false, range: () => [0, Math.max(frames - 1, 1)] },
        y: logY ? { distr: 3, range: () => left } : { range: () => left },
        ...(hasRight ? { right: { range: () => right } } : {}),
      },
      axes,
      series: [
        { label: xLabel, value: (_u, v) => (v === null || v === undefined ? '-' : num(v + 1)) },
        ...series.map((one, i) => ({
          label: one.label,
          scale: one.right ? 'right' : 'y',
          stroke: LEVEL_COLOURS[i % LEVEL_COLOURS.length],
          width: one.right ? 1.5 : 2,
          dash: one.right ? [5, 4] : undefined,
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
      const leftPx = u.cursor.left ?? -1;
      if (leftPx >= 0) pick.current(Math.round(u.posToVal(leftPx, 'x')));
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
  }, [data, num, series, xLabel, yLabel, logY, rightLabel]);

  useEffect(() => {
    current.current = frame;
    plot.current?.redraw();
  }, [frame]);

  return <div className="cx-timecourse" ref={host} />;
}
