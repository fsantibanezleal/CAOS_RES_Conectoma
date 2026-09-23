import { useMemo } from 'react';
import { depthCode, depthRange, errorOverTime, logError, readoutIndex, type DecodedChain, type Row } from '../lib/chain';
import { COLUMNS, type DecodedLevel as EyeLevel, type EyeManifest } from '../lib/eye';
import { useNumber, useT } from '../lib/i18n';
import HexMap from './HexMap';
import SeriesChart from './SeriesChart';
import { depthColour, grey, signedColour, signedStops, DEPTH_LEGEND } from './colour';

// A readout off by this factor either way saturates the error map: far enough to see a gross miss, close
// enough that a network within a factor of two still shows its structure.
const ERROR_FACTOR = 4;

export default function ChainView({
  manifest, eyeLevel, frame, chain, regime, hovered, onHover, onFrame, liveliness,
}: {
  manifest: EyeManifest;
  eyeLevel: EyeLevel;
  frame: number;                 // the eye's frame, 0-based
  chain: DecodedChain;
  regime: Row;
  hovered: number | null;
  onHover: (column: number | null) => void;
  onFrame: (frame: number) => void;
  liveliness: number[];          // per frame, the pathway's mean distance from rest
}) {
  const t = useT();
  const num = useNumber();
  const row = chain.rows[regime];
  const truth = chain.truth;
  const index = readoutIndex(frame, chain.steps);
  const base = index * COLUMNS;
  const eyeBase = frame * COLUMNS;
  const range = useMemo(() => depthRange(truth, row?.depth), [truth, row]);

  const code = (metres: number) => depthCode(metres, range);
  const metres = (value: number) => num(value, value < 1 ? 2 : value < 100 ? 1 : 0);

  const series = useMemo(() => {
    const out = [] as { label: string; values: number[]; right?: boolean }[];
    if (truth) {
      for (const one of ['M05', 'M06'] as Row[]) {
        const data = chain.rows[one];
        if (data) out.push({
          label: one === 'M05' ? t('frozen network (M05), error', 'red congelada (M05), error')
            : t('trained biophysics (M06), error', 'biofísica entrenada (M06), error'),
          values: errorOverTime(data, truth, chain.steps),
        });
      }
    }
    if (liveliness.length) {
      const peak = Math.max(...liveliness.filter(Number.isFinite), 1e-9);
      out.push({ label: t('pathway activity (share of its peak)', 'actividad de la vía (fracción de su máximo)'),
        values: liveliness.slice(0, chain.steps).map((v) => v / peak), right: true });
    }
    return out;
  }, [chain, truth, liveliness, t]);

  if (!row) {
    return (
      <p className="cx-muted cx-chain-missing">
        {t('This network has no readout for this clip: ', 'Esta red no tiene lectura para este clip: ')}
        {chain.missing[regime] ?? t('not in the artifact', 'no está en el artefacto')}
      </p>
    );
  }

  const hover = hovered != null && hovered >= 0 ? hovered : null;
  const z = hover != null ? row.depth[base + hover] : Number.NaN;
  const d = hover != null && truth ? truth[base + hover] : Number.NaN;
  const e = logError(z, d);
  const refusedHere = hover != null ? row.refused[base + hover] === 1 : false;
  const reading = (what: 'input' | 'readout' | 'truth' | 'error') => {
    if (hover == null) return null;
    if (what === 'input') return `${t('column', 'columna')} ${hover}: ${t('luminance', 'luminancia')} ${num(eyeLevel.lum[eyeBase + hover] / 255, 2)}`;
    if (what === 'readout') {
      if (!(z > 0)) return t('no answer', 'sin respuesta');
      return `${metres(z)} m, ${t('spread', 'dispersión')} ${num(row.spread[base + hover], 2)}${refusedHere ? `, ${t('refused', 'rechazada')}` : ''}`;
    }
    if (what === 'truth') return d > 0 ? `${metres(d)} m` : t('no truth here', 'sin verdad aquí');
    if (!Number.isFinite(e)) return t('nothing to compare', 'nada que comparar');
    const factor = Math.exp(Math.abs(e));
    return e < 0 ? `${t('too near by', 'demasiado cerca por')} x${num(factor, 2)}` : `${t('too far by', 'demasiado lejos por')} x${num(factor, 2)}`;
  };

  const depthLegend = (
    <span className="cx-chain-legend">
      <span>{metres(Math.exp(range.lo))} m</span>
      <span className="cx-legend cx-legend-inline" aria-hidden="true">
        {DEPTH_LEGEND.map((colour, i) => <span key={i} className="cx-legend-stop" style={{ background: colour }} />)}
      </span>
      <span>{metres(Math.exp(range.hi))} m</span>
    </span>
  );
  const errorLegend = (
    <span className="cx-chain-legend">
      <span>{t('too near', 'muy cerca')} x{ERROR_FACTOR}</span>
      <span className="cx-legend cx-legend-inline" aria-hidden="true">
        {signedStops().map((colour, i) => <span key={i} className="cx-legend-stop" style={{ background: colour }} />)}
      </span>
      <span>{t('too far', 'muy lejos')} x{ERROR_FACTOR}</span>
    </span>
  );

  const revision = `${regime}|${frame}|${index}|${range.lo}|${range.hi}`;
  return (
    <div className="cx-chain">
      <div className="cx-chain-grid">
        <HexMap
          label="input" manifest={manifest} revision={`${frame}|${eyeLevel.lum.length}`}
          title={t('1. What the eye receives', '1. Lo que recibe el ojo')}
          subtitle={t('721 columns, this frame', '721 columnas, este cuadro')}
          colourOf={(c) => grey(eyeLevel.lum[eyeBase + c])}
          hovered={hover} onHover={onHover} reading={reading('input')}
        />
        <HexMap
          label="readout" manifest={manifest} revision={revision}
          title={regime === 'M05' ? t('2. What the frozen network concludes', '2. Lo que concluye la red congelada')
            : t('2. What the trained network concludes', '2. Lo que concluye la red entrenada')}
          subtitle={t('depth read out of its T4 and T5 cells', 'profundidad leída de sus células T4 y T5')}
          colourOf={(c) => (row.depth[base + c] > 0 ? depthColour(code(row.depth[base + c])) : null)}
          faintOf={(c) => row.refused[base + c] === 1}
          hovered={hover} onHover={onHover} legend={depthLegend} reading={reading('readout')}
        />
        <HexMap
          label="truth" manifest={manifest} revision={`${frame}|${index}|${range.lo}|${range.hi}`}
          title={t('3. What is really there', '3. Lo que realmente hay')}
          subtitle={t('the rendered ground truth', 'la verdad de terreno renderizada')}
          colourOf={(c) => (truth && truth[base + c] > 0 ? depthColour(code(truth[base + c])) : null)}
          hovered={hover} onHover={onHover} legend={depthLegend} reading={reading('truth')}
        />
        <HexMap
          label="error" manifest={manifest} revision={`e${revision}`}
          title={t('4. Where it is wrong', '4. Dónde se equivoca')}
          subtitle={t('readout against truth, per column', 'lectura contra verdad, por columna')}
          colourOf={(c) => {
            const value = truth ? logError(row.depth[base + c], truth[base + c]) : Number.NaN;
            return Number.isFinite(value) ? signedColour(value / Math.log(ERROR_FACTOR)) : null;
          }}
          faintOf={(c) => row.refused[base + c] === 1}
          hovered={hover} onHover={onHover} legend={errorLegend} reading={reading('error')}
        />
      </div>
      {series.length ? (
        <div className="cx-chain-time">
          <SeriesChart
            series={series}
            frame={index}
            onFrame={(value) => onFrame(value)}
            xLabel={t('frame', 'cuadro')}
            yLabel={t('mean relative error (log)', 'error relativo medio (log)')}
            rightLabel={t('pathway activity', 'actividad de la vía')}
            logY
          />
        </div>
      ) : null}
    </div>
  );
}
