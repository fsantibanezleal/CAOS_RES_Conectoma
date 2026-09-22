import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { useSearchParams } from 'react-router';
import { Tabs } from '@fasl-work/caos-app-shell';
import { loadBrainClip, loadBrainManifest, loadEyeClip, loadEyeManifest } from '../api/artifacts';
import { decodeLevel, STAGES, type BrainClip, type BrainManifest, type DecodedActivity } from '../lib/brain';
import { COLUMNS, decodeLevel as decodeEyeLevel, type EyeClip, type EyeManifest } from '../lib/eye';
import { useNumber, useT } from '../lib/i18n';
import ActivityLattice from './ActivityLattice';
import EyeLattice from './EyeLattice';
import SeriesChart from './SeriesChart';
import { signedStops } from './colour';
import { usePlayback } from './usePlayback';

const SPEEDS = [0.25, 0.5, 1, 2, 4];

/**
 * What the measured connectome DOES with what the eye receives, playing.
 *
 * The eye's input and the network's pathway advance on one clock: the lamina, the medulla types that feed
 * motion detection, and the direction-selective outputs, each on the same hexagonal lattice the column
 * that drove it looks through. Nothing is simulated here: the response was computed by the frozen network
 * in the pipeline and is verified against its digest before it is drawn, so what moves on screen is the
 * same network the Experiments page reports numbers for.
 */
export default function BrainMode({ switcher }: { switcher: ReactNode }) {
  const t = useT();
  const num = useNumber();
  const [params, setParams] = useSearchParams();
  const [manifests, setManifests] = useState<{ brain: BrainManifest; eye: EyeManifest } | null>(null);
  const [loaded, setLoaded] = useState<{ brain: BrainClip; eye: EyeClip; verified: boolean } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [hovered, setHovered] = useState<number | null>(null);
  const [speed, setSpeed] = useState(1);

  const caseId = params.get('case') ?? 'C01';
  const level = params.get('level') ?? '0';

  useEffect(() => {
    let live = true;
    Promise.all([loadBrainManifest(), loadEyeManifest()])
      .then(([brain, eye]) => live && setManifests({ brain, eye }))
      .catch((e) => live && setError(String(e)));
    return () => { live = false; };
  }, []);

  useEffect(() => {
    if (!manifests) return undefined;
    let live = true;
    setLoaded(null);
    Promise.all([loadBrainClip(manifests.brain, caseId), loadEyeClip(manifests.eye, caseId)])
      .then(([brain, eye]) => live && setLoaded({
        brain: brain.clip, eye: eye.clip, verified: brain.verified && eye.verified,
      }))
      .catch((e) => live && setError(String(e)));
    return () => { live = false; };
  }, [manifests, caseId]);

  const levels = loaded ? Object.keys(loaded.brain.levels).sort((a, b) => Number(a) - Number(b)) : [];
  const chosen = levels.includes(level) ? level : (levels[0] ?? '0');
  const activity: DecodedActivity | null = useMemo(
    () => (loaded && loaded.brain.levels[chosen] ? decodeLevel(loaded.brain, chosen) : null),
    [loaded, chosen],
  );
  const eyeLevel = useMemo(
    () => (loaded ? decodeEyeLevel(loaded.eye, Number(chosen)) : null),
    [loaded, chosen],
  );

  const detail = loaded?.brain.levels[chosen];
  const steps = activity?.steps ?? 0;
  const stepSeconds = detail?.step_s ?? 0.06;
  const clock = usePlayback(steps, stepSeconds, {
    speed,
    onPause: (at) => {
      const next = new URLSearchParams(params);
      next.set('step', String(at));
      setParams(next, { replace: true });
    },
  });

  const update = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(changes)) {
      if (value === null) next.delete(key);
      else next.set(key, value);
    }
    setParams(next, { replace: true });
  };

  if (error) {
    return (
      <div className="page-body wide cx-app">
        <aside className="cx-rail">{switcher}</aside>
        <section className="cx-main">
          <p className="cx-muted">{t('The response could not be loaded: ', 'No se pudo cargar la respuesta: ')}{error}</p>
        </section>
      </div>
    );
  }
  if (!manifests || !loaded || !activity || !eyeLevel || !detail) {
    return (
      <div className="page-body wide cx-app">
        <aside className="cx-rail">{switcher}</aside>
        <section className="cx-main"><p className="cx-muted">{t('Loading the response...', 'Cargando la respuesta...')}</p></section>
      </div>
    );
  }

  const types = loaded.brain.types.filter((type) => activity.values[type]);
  const stages: Array<'lamina' | 'medulla' | 'output'> = ['lamina', 'medulla', 'output'];
  const stageName = {
    lamina: t('Lamina: the first synapse', 'Lámina: la primera sinapsis'),
    medulla: t('Medulla: the arms of the detector', 'Médula: los brazos del detector'),
    output: t('T4 and T5: direction selective', 'T4 y T5: selectivas a la dirección'),
  };
  // the frame of the eye that this simulated step belongs to
  const frame = Math.min(Math.floor((clock.frame * detail.stride) / detail.steps_per_frame),
                         detail.frames - 1);
  const seconds = clock.frame * stepSeconds;

  const eyePanel = (
    <div className="cx-brain-eye">
      <EyeLattice
        manifest={manifests.eye}
        clip={loaded.eye}
        level={eyeLevel}
        frame={frame}
        view="lum"
        title={t('The eye', 'El ojo')}
        compact
      />
    </div>
  );

  const grid = (stage: 'lamina' | 'medulla' | 'output') => {
    const mine = types.filter((type) => STAGES[type]?.stage === stage);
    if (!mine.length) return null;
    return (
      <div className="cx-brain-stage" key={stage}>
        <h3 className="cx-brain-stage-title">{stageName[stage]}</h3>
        <div className="cx-brain-grid">
          {mine.map((type) => (
            <ActivityLattice
              key={type}
              manifest={manifests.eye}
              values={activity.values[type]}
              step={clock.frame}
              centre={activity.centre[type] ?? 0}
              spread={activity.spread[type] ?? 1}
              title={type}
              subtitle={t(STAGES[type]?.en ?? '', STAGES[type]?.es ?? '')}
              hovered={hovered}
              onHover={setHovered}
            />
          ))}
        </div>
      </div>
    );
  };

  const pathway = (
    <div className="cx-brain-stage-wrap">
      {eyePanel}
      {stages.map((stage) => grid(stage))}
    </div>
  );

  const outputs = types.filter((type) => STAGES[type]?.stage === 'output');
  const traces = hovered != null && hovered >= 0 ? outputs.map((type) => ({
    label: type,
    values: Array.from({ length: steps }, (_, s) => activity.values[type][s * COLUMNS + hovered]),
  })) : [];

  const overTime = (
    <div className="cx-brain-traces">
      {hovered != null && hovered >= 0 && traces.length ? (
        <SeriesChart
          series={traces}
          frame={clock.frame}
          onFrame={(value) => clock.setFrame(value)}
          xLabel={t('simulated step', 'paso simulado')}
          yLabel={t('response (engine units)', 'respuesta (unidades del motor)')}
        />
      ) : (
        <p className="cx-muted">
          {t('Point at a column in any map above to read what its T4 and T5 cells did over the clip.',
             'Apunte a una columna en cualquier mapa de arriba para leer lo que hicieron sus células T4 y T5 durante el clip.')}
        </p>
      )}
    </div>
  );

  return (
    <div className="page-body wide cx-app">
      <aside className="cx-rail" aria-label={t('Response controls', 'Controles de la respuesta')}>
        {switcher}
        <section className="cx-rail-section">
          <label className="cx-label" htmlFor="cx-brain-case">{t('Case', 'Caso')}</label>
          <select id="cx-brain-case" className="cx-select" value={caseId}
            onChange={(e) => update({ case: e.target.value, step: null })}>
            {Object.keys(manifests.brain.cases).sort().map((id) => (
              <option key={id} value={id}>{id}</option>
            ))}
          </select>

          <span className="cx-label">{loaded.brain.quantity} ({loaded.brain.unit})</span>
          <div className="cx-segmented cx-wrap" role="radiogroup" aria-label={t('Level', 'Nivel')}>
            {levels.map((one) => (
              <button key={one} type="button" role="radio" aria-checked={one === chosen}
                className={one === chosen ? 'active' : ''}
                onClick={() => update({ level: one, step: null })}>
                {String(loaded.brain.levels[one].value)}
              </button>
            ))}
          </div>

          <label className="cx-label" htmlFor="cx-brain-step">
            {t('Step', 'Paso')}: <strong>{clock.frame + 1}</strong> / {steps} ({num(seconds, 2)} s)
          </label>
          <div className="cx-frame-row">
            <button type="button" className="cx-play" aria-pressed={clock.playing} onClick={clock.toggle}>
              {clock.playing ? t('Pause', 'Pausa') : t('Play', 'Reproducir')}
            </button>
            <input id="cx-brain-step" type="range" min={0} max={Math.max(steps - 1, 0)} step={1}
              value={clock.frame} onChange={(e) => clock.setFrame(Number(e.target.value))} />
          </div>
          <span className="cx-label">{t('Speed', 'Velocidad')}</span>
          <div className="cx-segmented" role="radiogroup" aria-label={t('Speed', 'Velocidad')}>
            {SPEEDS.map((one) => (
              <button key={one} type="button" role="radio" aria-checked={one === speed}
                className={one === speed ? 'active' : ''} onClick={() => setSpeed(one)}>
                {one}x
              </button>
            ))}
          </div>
        </section>

        <div className="cx-rail-give">
          <section className="cx-rail-section cx-readout" aria-label={t('The colour scale', 'La escala de color')}>
            <div className="cx-readout-row">
              <span>{t('Response', 'Respuesta')}</span>
              <strong>{t('signed, centred on rest', 'con signo, centrada en reposo')}</strong>
            </div>
            <div className="cx-legend" aria-hidden="true">
              {signedStops().map((colour, i) => (
                <span key={i} className="cx-legend-stop" style={{ background: colour }} />
              ))}
            </div>
            <div className="cx-readout-row"><span>{t('below rest', 'bajo reposo')}</span><span>{t('above', 'sobre')}</span></div>
            <div className="cx-readout-row">
              <span>{t('Frame', 'Cuadro')}</span><strong>{frame + 1} / {detail.frames}</strong>
            </div>
            <div className="cx-readout-row">
              <span>{t('Step', 'Paso')}</span><strong>{num(detail.step_s * 1000, 0)} ms</strong>
            </div>
            <div className="cx-readout-row">
              <span>{t('Column', 'Columna')}</span>
              <strong>{hovered != null && hovered >= 0 ? hovered : t('none', 'ninguna')}</strong>
            </div>
          </section>
          <p className="cx-provenance" data-verified={loaded.verified ? 'true' : 'false'}>
            {t('The frozen network, run in the pipeline on this clip; nothing is simulated in the browser.',
               'La red congelada, ejecutada en el pipeline sobre este clip; nada se simula en el navegador.')}{' '}
            {loaded.verified
              ? t('Response verified against its manifest (SHA-256).', 'Respuesta verificada contra su manifiesto (SHA-256).')
              : t('Response NOT verified against its manifest.', 'Respuesta NO verificada contra su manifiesto.')}
          </p>
        </div>
      </aside>

      <section className="cx-main" aria-label={t('What the connectome does', 'Lo que hace el conectoma')}>
        <Tabs
          ariaLabel={t('Response views', 'Vistas de la respuesta')}
          tabs={[
            { id: 'pathway', label: t('The pathway', 'La vía'), content: pathway },
            { id: 'traces', label: t('One column over time', 'Una columna en el tiempo'), content: overTime },
          ]}
        />
      </section>
    </div>
  );
}
