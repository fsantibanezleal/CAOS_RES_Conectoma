import { useEffect, useMemo, useRef, useState } from 'react';
import { deviation, driveOf, type Circuit, type CircuitEdge } from '../lib/chain';
import { STAGES } from '../lib/brain';
import { COLUMNS, type EyeManifest } from '../lib/eye';
import { useNumber, useT } from '../lib/i18n';
import { depthColour, parseRgb, signedColour } from './colour';

type Layer = 'retina' | 'lamina' | 'medulla' | 'output' | 'head';
const LAYERS: Layer[] = ['retina', 'lamina', 'medulla', 'output', 'head'];

interface Placed { type: string; layer: Layer; x: number; y: number; size: number }

/**
 * The measured circuit, carrying the signal.
 *
 * Every connection drawn is one the committed connectome specification contains, between the pathway's
 * cell types, with its synapse count onto one target cell and its sign; nothing is laid out by hand except
 * where the nodes sit. Each node is a live miniature of its type's map on the 721 columns, and each
 * connection pulses with its drive: the source's deviation from rest times the connection's signed weight.
 * The last column is the trained head, which is NOT wiring, and is drawn apart from it: dashed, grey, and
 * labelled as what it is.
 *
 * The pulses move only while the chain plays; paused, the drawing is the current step, still.
 */
export default function CircuitView({
  circuit, manifest, values, centre, spread, step, lum, frame, playing, head: conclusion,
}: {
  circuit: Circuit;
  manifest: EyeManifest;
  values: Record<string, Float32Array>;
  centre: Record<string, number>;
  spread: Record<string, number>;
  step: number;
  lum: Uint8Array;               // the eye's input at this frame, which is what the photoreceptors carry
  frame: number;
  playing: boolean;
  /** what the network concludes at this frame, drawn inside the head: depth codes 0 to 254, null for none */
  head?: { code: (column: number) => number | null; label: string } | null;
}) {
  const t = useT();
  const num = useNumber();
  const host = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  const [hovered, setHovered] = useState<string | null>(null);
  const phase = useRef(0);

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

  // the lattice in a unit box, for the miniature maps
  const unit = useMemo(() => {
    const { row_px: rows, col_px: cols } = manifest.lattice;
    const x0 = Math.min(...cols); const x1 = Math.max(...cols);
    const y0 = Math.min(...rows); const y1 = Math.max(...rows);
    const span = Math.max(x1 - x0, y1 - y0);
    return { x: cols.map((v) => (v - (x0 + x1) / 2) / span), y: rows.map((v) => (v - (y0 + y1) / 2) / span) };
  }, [manifest]);

  // where each node sits: one column per layer, nodes spread down it, the head alone at the end
  const placed = useMemo(() => {
    const out: Record<string, Placed> = {};
    const byLayer: Record<Layer, string[]> = { retina: [], lamina: [], medulla: [], output: [], head: ['head'] };
    for (const node of circuit.nodes) byLayer[node.layer as Layer].push(node.type);
    const width = size.width;
    const height = size.height;
    const margin = 24;
    const most = Math.max(...LAYERS.map((layer) => byLayer[layer].length));
    const node = Math.max(Math.min((height - 2 * margin) / most - 10, width / 9, 110), 18);
    LAYERS.forEach((layer, i) => {
      const x = margin + node / 2 + ((width - 2 * margin - node) * i) / (LAYERS.length - 1);
      const names = byLayer[layer];
      names.forEach((type, k) => {
        const y = names.length === 1 ? height / 2 : margin + node / 2 + ((height - 2 * margin - node) * k) / (names.length - 1);
        out[type] = { type, layer, x, y, size: node };
      });
    });
    return out;
  }, [circuit, size]);

  // each type's deviation from rest at this step, in units of its own spread
  const deviations = useMemo(() => {
    const out: Record<string, number> = {};
    for (const node of circuit.nodes) {
      if (values[node.type]) out[node.type] = deviation(values[node.type], centre[node.type] ?? 0, spread[node.type] ?? 1, step);
    }
    // the photoreceptors carry the eye's input: their deviation is the frame's contrast about mid grey
    if (lum.length) {
      let sum = 0;
      for (let c = 0; c < COLUMNS; c++) sum += lum[frame * COLUMNS + c] / 255 - 0.5;
      out['R1-R6'] = (sum / COLUMNS) / 0.25;
    }
    return out;
  }, [circuit, values, centre, spread, step, lum, frame]);

  const drives = useMemo(() => {
    const raw = circuit.edges.map((edge) => driveOf(edge, deviations[edge.source] ?? 0));
    const peak = Math.max(...raw.map((v) => Math.abs(v)), 1e-9);
    return raw.map((v) => v / peak);
  }, [circuit, deviations]);

  const heaviest = useMemo(() => Math.max(...circuit.edges.map((e) => e.synapses), 1), [circuit]);

  useEffect(() => {
    const element = canvas.current;
    if (!element || size.width === 0) return undefined;
    const ratio = window.devicePixelRatio || 1;
    element.width = Math.round(size.width * ratio);
    element.height = Math.round(size.height * ratio);
    const ctx = element.getContext('2d');
    if (!ctx) return undefined;
    const style = getComputedStyle(element);
    const fg = style.getPropertyValue('--color-fg').trim() || '#1f2328';
    const faint = style.getPropertyValue('--color-fg-faint').trim() || '#8b949e';
    const surface = style.getPropertyValue('--color-surface').trim() || '#ffffff';
    const accent = parseRgb(style.getPropertyValue('--color-accent'), [9, 105, 218]);
    const warm = signedColour(0.85);
    const cool = signedColour(-0.85);

    const curve = (edge: CircuitEdge) => {
      const a = placed[edge.source];
      const b = placed[edge.target];
      if (!a || !b) return null;
      const forward = b.x > a.x + 1;
      const x0 = a.x + (forward ? a.size / 2 : 0);
      const x1 = b.x - (forward ? b.size / 2 : 0);
      const bend = forward ? (x1 - x0) * 0.45 : Math.max(a.size, 40) * (a.y < b.y ? 1 : -1) * 0.9;
      // forward edges sweep right; lateral and backward ones bow out to the side so they stay readable
      const c0 = forward ? [x0 + bend, a.y] : [x0 + bend * 1.2, a.y];
      const c1 = forward ? [x1 - bend, b.y] : [x1 + bend * 1.2, b.y];
      return { from: [x0, a.y], c0, c1, to: [x1, b.y] };
    };
    const pointOn = (g: NonNullable<ReturnType<typeof curve>>, s: number) => {
      const u = 1 - s;
      const x = u * u * u * g.from[0] + 3 * u * u * s * g.c0[0] + 3 * u * s * s * g.c1[0] + s * s * s * g.to[0];
      const y = u * u * u * g.from[1] + 3 * u * u * s * g.c0[1] + 3 * u * s * s * g.c1[1] + s * s * s * g.to[1];
      return [x, y];
    };

    const draw = () => {
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      ctx.clearRect(0, 0, size.width, size.height);
      // wiring, heaviest drawn last so it reads on top
      const order = circuit.edges.map((_, i) => i).sort((i, j) => Math.abs(drives[i]) - Math.abs(drives[j]));
      for (const i of order) {
        const edge = circuit.edges[i];
        const g = curve(edge);
        if (!g) continue;
        const touches = hovered == null || edge.source === hovered || edge.target === hovered;
        const strength = Math.abs(drives[i]);
        ctx.strokeStyle = edge.sign > 0 ? warm : cool;
        // every measured connection stays visible; the drive decides how much more it shows
        ctx.globalAlpha = touches ? 0.16 + 0.7 * Math.sqrt(strength) : 0.05;
        ctx.lineWidth = 0.6 + 4.5 * Math.sqrt(edge.synapses / heaviest);
        ctx.beginPath();
        ctx.moveTo(g.from[0], g.from[1]);
        ctx.bezierCurveTo(g.c0[0], g.c0[1], g.c1[0], g.c1[1], g.to[0], g.to[1]);
        ctx.stroke();
        // the signal travelling: a few pulses per connection, faster where the drive is stronger
        if (touches && strength > 0.05) {
          ctx.globalAlpha = Math.min(1, 0.25 + strength);
          ctx.fillStyle = edge.sign > 0 ? warm : cool;
          const pulses = 3;
          for (let k = 0; k < pulses; k++) {
            const s = (phase.current * (0.4 + 1.6 * strength) + k / pulses + i * 0.137) % 1;
            const [px, py] = pointOn(g, drives[i] >= 0 ? s : 1 - s);
            ctx.beginPath();
            ctx.arc(px, py, 1.2 + 2.2 * strength, 0, Math.PI * 2);
            ctx.fill();
          }
        }
      }
      ctx.globalAlpha = 1;

      // the head is not wiring: its inputs are drawn dashed and grey
      const head = placed.head;
      if (head) {
        ctx.setLineDash([4, 5]);
        ctx.strokeStyle = faint;
        ctx.lineWidth = 1;
        for (const node of circuit.nodes.filter((n) => n.layer === 'output')) {
          const p = placed[node.type];
          if (!p) continue;
          ctx.beginPath();
          ctx.moveTo(p.x + p.size / 2, p.y);
          ctx.bezierCurveTo(p.x + p.size, p.y, head.x - head.size, head.y, head.x - head.size / 2, head.y);
          ctx.stroke();
        }
        ctx.setLineDash([]);
      }

      // the nodes: each a miniature of its type's map on the 721 columns
      for (const node of [...circuit.nodes, { type: 'head', layer: 'head' as const }]) {
        const p = placed[node.type];
        if (!p) continue;
        const r = p.size / 2;
        const dim = hovered != null && hovered !== node.type
          && !circuit.edges.some((e) => (e.source === hovered && e.target === node.type) || (e.target === hovered && e.source === node.type));
        ctx.globalAlpha = dim ? 0.3 : 1;
        ctx.fillStyle = surface;
        ctx.beginPath();
        ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
        ctx.fill();
        const map = values[node.type];
        if (node.type === 'head' && conclusion) {
          // the network's conclusion: depth, near bright and far dark, on the same lattice
          const dot = Math.max(r / 17, 0.8);
          for (let c = 0; c < COLUMNS; c++) {
            const code = conclusion.code(c);
            if (code === null) continue;
            ctx.fillStyle = depthColour(code) ?? surface;
            ctx.fillRect(p.x + unit.x[c] * r * 1.55 - dot / 2, p.y + unit.y[c] * r * 1.55 - dot / 2, dot, dot);
          }
        } else if (map || node.type === 'R1-R6') {
          const dot = Math.max(r / 17, 0.8);
          const c0 = centre[node.type] ?? 0;
          const sp = Math.max(spread[node.type] ?? 1, 1e-9);
          for (let c = 0; c < COLUMNS; c++) {
            const value = map ? (map[step * COLUMNS + c] - c0) / sp : (lum[frame * COLUMNS + c] / 255 - 0.5) / 0.25;
            ctx.fillStyle = signedColour(value);
            ctx.fillRect(p.x + unit.x[c] * r * 1.55 - dot / 2, p.y + unit.y[c] * r * 1.55 - dot / 2, dot, dot);
          }
        }
        ctx.strokeStyle = node.type === hovered ? `rgb(${accent.join(',')})` : faint;
        ctx.lineWidth = node.type === hovered ? 2.5 : 1;
        ctx.setLineDash(node.layer === 'head' ? [4, 4] : []);
        ctx.beginPath();
        ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
        ctx.stroke();
        ctx.setLineDash([]);
        if (!map && node.type !== 'R1-R6' && node.type !== 'head') {
          // a wide-field type: one cell for the whole lattice, so there is no map to draw
          ctx.fillStyle = faint;
          ctx.font = `${Math.max(Math.min(r * 0.3, 11), 8)}px system-ui, sans-serif`;
          ctx.textAlign = 'center';
          ctx.fillText(t('one cell', 'una célula'), p.x, p.y + 3);
        }
        ctx.fillStyle = fg;
        ctx.font = `600 ${Math.max(Math.min(r * 0.42, 13), 9)}px system-ui, sans-serif`;
        const label = node.type === 'head' ? (conclusion?.label ?? t('head', 'cabeza')) : node.type;
        // in a crowded column the label goes beside its node, never onto the next one
        const beside = p.layer === 'medulla' || p.layer === 'output';
        const lx = beside ? p.x + r + 6 : p.x;
        const ly = beside ? p.y + 4 : p.y + r + 14;
        ctx.textAlign = beside ? 'left' : 'center';
        // a plate under the label, so the wiring that crosses it does not cross the letters
        const width = ctx.measureText(label).width;
        const plateX = beside ? lx - 3 : lx - width / 2 - 3;
        ctx.globalAlpha = dim ? 0.3 : 0.85;
        ctx.fillStyle = surface;
        ctx.fillRect(plateX, ly - 11, width + 6, 15);
        ctx.globalAlpha = dim ? 0.3 : 1;
        ctx.fillStyle = fg;
        ctx.fillText(label, lx, ly);
        ctx.globalAlpha = 1;
      }
      element.dataset.painted = `0,0,${size.width.toFixed(1)},${size.height.toFixed(1)}`;
      element.dataset.edges = String(circuit.edges.length);
    };

    draw();
    if (!playing) return undefined;
    let frameId = 0;
    let last = performance.now();
    const tick = (now: number) => {
      phase.current = (phase.current + (now - last) / 1600) % 1000;
      last = now;
      draw();
      frameId = requestAnimationFrame(tick);
    };
    frameId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frameId);
  }, [circuit, placed, drives, heaviest, hovered, size, values, centre, spread, step, lum, frame, playing, unit, t, conclusion]);

  const locate = (event: React.PointerEvent) => {
    const rect = canvas.current?.getBoundingClientRect();
    if (!rect) return;
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    const hit = Object.values(placed).find((p) => (p.x - x) ** 2 + (p.y - y) ** 2 <= (p.size / 2) ** 2);
    setHovered(hit ? hit.type : null);
  };

  const detail = (() => {
    if (!hovered) return null;
    if (hovered === 'head') {
      return t('The trained head: not wiring. It reads all eight T4 and T5 types over two frames and outputs a depth, its own spread, and a boundary per column.',
        'La cabeza entrenada: no es cableado. Lee los ocho tipos T4 y T5 en dos cuadros y entrega una profundidad, su propia dispersión y un borde por columna.');
    }
    const inputs = circuit.edges.filter((e) => e.target === hovered).sort((a, b) => b.synapses - a.synapses).slice(0, 4);
    const stage = STAGES[hovered];
    const parts = [hovered];
    if (stage) parts.push(t(stage.en, stage.es));
    if (hovered === 'R1-R6') parts.push(t('the photoreceptors: they carry the eye’s input', 'los fotorreceptores: llevan la entrada del ojo'));
    if (!values[hovered] && hovered !== 'R1-R6') parts.push(t('one cell for the whole lattice, not recorded', 'una célula para toda la retícula, no registrada'));
    if (Number.isFinite(deviations[hovered])) parts.push(`${t('deviation from rest', 'desviación del reposo')} ${num(deviations[hovered], 2)}`);
    if (inputs.length) parts.push(`${t('strongest inputs', 'entradas más fuertes')}: ${inputs.map((e) => `${e.source} ${e.sign > 0 ? '+' : '-'}${num(e.synapses, 0)}`).join(', ')}`);
    return parts.join('  ·  ');
  })();

  return (
    <div className="cx-circuit">
      <div className="cx-circuit-legend">
        <span><i className="cx-swatch" style={{ background: signedColour(0.85) }} /> {t('excitatory', 'excitatoria')}</span>
        <span><i className="cx-swatch" style={{ background: signedColour(-0.85) }} /> {t('inhibitory', 'inhibitoria')}</span>
        <span>{t('width: synapses onto one target cell', 'grosor: sinapsis sobre una célula blanco')}</span>
        <span>{t('pulses: drive at this step', 'pulsos: impulso en este paso')}</span>
        <span className="cx-muted">
          {t(`${circuit.edges.length} measured connections among ${circuit.nodes.length} cell types`,
             `${circuit.edges.length} conexiones medidas entre ${circuit.nodes.length} tipos celulares`)}
        </span>
      </div>
      <div className="cx-circuit-canvas" ref={host}>
        <canvas
          ref={canvas}
          className="cx-circuit-drawing"
          style={{ width: size.width, height: size.height }}
          onPointerMove={locate}
          onPointerLeave={() => setHovered(null)}
          role="img"
          aria-label={t('The measured circuit of the fly’s visual pathway, carrying the signal', 'El circuito medido de la vía visual de la mosca, llevando la señal')}
        />
      </div>
      <p className="cx-circuit-detail" aria-live="polite">
        {detail ?? t('Point at a cell type to see what drives it.', 'Apunte a un tipo celular para ver qué lo impulsa.')}
      </p>
    </div>
  );
}
