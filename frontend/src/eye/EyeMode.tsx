import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { useSearchParams } from 'react-router';
import { Tabs } from '@fasl-work/caos-app-shell';
import { loadEyeClip, loadEyeManifest, type VerifiedClip } from '../api/artifacts';
import { decodeLevel, type EyeManifest } from '../lib/eye';
import { useNumber, useT } from '../lib/i18n';
import EyeLattice, { type View } from './EyeLattice';
import TimeCourse, { LEVEL_COLOURS } from './TimeCourse';
import { CASE_NAMES, CATEGORIES, levelLabel, MEASURED, QUANTITIES } from './text';

const DEFAULT_CASE = 'C01';
const TARGETS: View[] = ['depth', 'figure', 'boundary', 'flow', 'sky', 'labelled'];

/**
 * The App's second mode: what the eye's 721 columns receive in each case, level by level, frame by frame,
 * beside the ground truth the case grades. Every array is the committed case rendering (contract 2),
 * checked against its manifest's SHA-256 before it is drawn. Nothing plays until asked, and playback stops
 * when the tab is hidden.
 */
export default function EyeMode({ switcher }: { switcher: ReactNode }) {
  const t = useT();
  const num = useNumber();
  const [params, setParams] = useSearchParams();
  const [manifest, setManifest] = useState<EyeManifest | null>(null);
  const [loaded, setLoaded] = useState<VerifiedClip | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [playing, setPlaying] = useState(false);

  const requested = params.get('case') ?? DEFAULT_CASE;
  const caseId = manifest && manifest.cases[requested] ? requested : DEFAULT_CASE;

  useEffect(() => {
    loadEyeManifest().then(setManifest).catch((e) => setError(String(e)));
  }, []);
  useEffect(() => {
    if (!manifest) return;
    setLoaded(null);
    loadEyeClip(manifest, caseId).then(setLoaded).catch((e) => setError(String(e)));
  }, [manifest, caseId]);

  const clip = loaded?.clip ?? null;
  const levels = useMemo(() => (clip ? clip.levels.map((_, i) => decodeLevel(clip, i)) : []), [clip]);
  const levelIndex = Math.min(Math.max(Number(params.get('level') ?? '0') || 0, 0), 5);
  const frames = clip?.frames ?? 1;
  const frame = Math.min(Math.max(Number(params.get('frame') ?? '0') || 0, 0), frames - 1);
  const available: View[] = clip ? TARGETS.filter((v) => (v === 'depth' ? true : v in (levels[0] ?? {}))) : ['depth'];
  const requestedLayer = (params.get('layer') ?? 'depth') as View;
  const target: View = available.includes(requestedLayer) ? requestedLayer : 'depth';
  const level = levels[levelIndex];
  const interval = clip?.levels[levelIndex].interval_s ?? null;

  function update(changes: Record<string, string | null>) {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(changes)) {
      if (value === null) next.delete(key);
      else next.set(key, value);
    }
    setParams(next, { replace: true });
  }

  // playback: one frame per recorded interval (never faster than 25 per second on screen), paused by
  // default, and stopped whenever the page is hidden
  useEffect(() => {
    if (!playing || !clip) return;
    const step = Math.max((interval ?? 0.5) * 1000, 40);
    const timer = window.setTimeout(() => update({ frame: String((frame + 1) % frames) }), step);
    return () => window.clearTimeout(timer);
    // one timeout per frame shown; `update` is this render's
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing, clip, frame, frames, interval]);
  useEffect(() => {
    const stop = () => { if (document.hidden) setPlaying(false); };
    document.addEventListener('visibilitychange', stop);
    return () => document.removeEventListener('visibilitychange', stop);
  }, []);

  const name = (id: string) => t(CASE_NAMES[id]?.[0] ?? id, CASE_NAMES[id]?.[1] ?? id);
  const layerName: Record<View, string> = {
    lum: t('luminance', 'luminancia'), depth: t('depth', 'profundidad'), figure: t('figure', 'figura'),
    boundary: t('boundaries', 'bordes'), flow: t('flow', 'flujo'), sky: t('sky', 'cielo'),
    labelled: t('labelled', 'etiquetado'),
  };

  if (error) {
    return (
      <div className="page-body wide cx-app">
        <aside className="cx-rail">{switcher}</aside>
        <section className="cx-main"><p className="cx-muted">{t('The eye artifact could not be loaded: ', 'No se pudo cargar el artefacto del ojo: ')}{error}</p></section>
      </div>
    );
  }
  if (!manifest || !loaded || !clip || !level) {
    return (
      <div className="page-body wide cx-app">
        <aside className="cx-rail">{switcher}</aside>
        <section className="cx-main"><p className="cx-muted">{t('Loading what the eye sees...', 'Cargando lo que ve el ojo...')}</p></section>
      </div>
    );
  }

  const labels = clip.variant.levels.map((v) => levelLabel(caseId, v, t, num));
  const measured = clip.levels[levelIndex].measured;
  const byCategory = Object.entries(manifest.cases).reduce<Record<string, string[]>>((acc, [id, entry]) => {
    (acc[entry.category] ??= []).push(id);
    return acc;
  }, {});
  const time = interval ? `${num(frame * interval, interval < 0.1 ? 3 : 2)} s` : t(`image ${frame + 1}`, `imagen ${frame + 1}`);

  const stage = (
    <div className="cx-eye-pair">
      <EyeLattice manifest={manifest} clip={clip} level={level} frame={frame} view="lum"
        title={t('Input: what the columns receive', 'Entrada: lo que reciben las columnas')} />
      <EyeLattice manifest={manifest} clip={clip} level={level} frame={frame} view={target}
        title={t(`Ground truth: ${layerName[target]}`, `Verdad de terreno: ${layerName[target]}`)} />
    </div>
  );

  const strip = (
    <div className="cx-strip" aria-live="polite">
      <span><strong>{caseId}</strong> {name(caseId)}</span>
      <span>{t('level', 'nivel')} <strong>{levelIndex + 1}</strong> {t('of 6', 'de 6')}: <strong>{labels[levelIndex]}</strong></span>
      <span>{t('frame', 'cuadro')} <strong>{frame + 1}</strong> / {frames} ({time})</span>
      <span className="cx-muted">{/^\d+$/.test(clip.item) ? t('seed', 'semilla') : t('clip', 'clip')} <code>{clip.item}</code></span>
    </div>
  );

  const acrossLevels = (
    <div className="cx-eye-grid" style={{ ['--cx-grid-cols' as string]: 6 }}>
      {levels.map((lv, i) => (
        <EyeLattice key={`in-${i}`} manifest={manifest} clip={clip} level={lv} frame={frame} view="lum" compact
          title={labels[i]} />
      ))}
      {levels.map((lv, i) => (
        <EyeLattice key={`gt-${i}`} manifest={manifest} clip={clip} level={lv} frame={frame} view={target} compact
          title={`${layerName[target]}, ${labels[i]}`} />
      ))}
    </div>
  );

  const overTime = (
    <div className="cx-eye-charts">
      <TimeCourse clip={clip} levels={levels} labels={labels} view="lum" frame={frame}
        onFrame={(f) => update({ frame: String(f) })} />
      <TimeCourse clip={clip} levels={levels} labels={labels} view={target} frame={frame}
        onFrame={(f) => update({ frame: String(f) })} />
    </div>
  );

  return (
    <div className="page-body wide cx-app">
      <aside className="cx-rail" aria-label={t('Eye input controls', 'Controles de la entrada del ojo')}>
        {switcher}
        <section className="cx-rail-section">
          <label className="cx-label" htmlFor="cx-case">{t('Case', 'Caso')}</label>
          <select id="cx-case" className="cx-select" value={caseId}
            onChange={(e) => update({ case: e.target.value, level: null, frame: null })}>
            {Object.entries(byCategory).map(([category, ids]) => (
              <optgroup key={category} label={t(CATEGORIES[category]?.[0] ?? category, CATEGORIES[category]?.[1] ?? category)}>
                {ids.map((id) => <option key={id} value={id}>{id} {name(id)}</option>)}
              </optgroup>
            ))}
          </select>

          <span className="cx-label">{t(QUANTITIES[caseId]?.[0] ?? '', QUANTITIES[caseId]?.[1] ?? '')}</span>
          <div className="cx-levels" role="radiogroup" aria-label={t('Level', 'Nivel')}>
            {labels.map((label, i) => (
              <button key={i} type="button" role="radio" aria-checked={i === levelIndex}
                className={i === levelIndex ? 'active' : ''} onClick={() => update({ level: i ? String(i) : null })}>
                <span className="cx-level-dot" style={{ background: LEVEL_COLOURS[i] }} />{label}
              </button>
            ))}
          </div>

          <span className="cx-label">{t('Ground truth', 'Verdad de terreno')}</span>
          <div className="cx-segmented cx-wrap" role="radiogroup" aria-label={t('Ground truth', 'Verdad de terreno')}>
            {available.map((v) => (
              <button key={v} type="button" role="radio" aria-checked={v === target}
                className={v === target ? 'active' : ''} onClick={() => update({ layer: v === 'depth' ? null : v })}>
                {layerName[v]}
              </button>
            ))}
          </div>

          <label className="cx-label" htmlFor="cx-frame">{t('Frame', 'Cuadro')}: <strong>{frame + 1}</strong> / {frames}</label>
          <div className="cx-frame-row">
            <button type="button" className="cx-play" aria-pressed={playing} onClick={() => setPlaying(!playing)}>
              {playing ? t('Pause', 'Pausa') : t('Play', 'Reproducir')}
            </button>
            <input id="cx-frame" type="range" min={0} max={frames - 1} step={1} value={frame}
              onChange={(e) => update({ frame: e.target.value === '0' ? null : e.target.value })} />
          </div>
        </section>

        <section className="cx-rail-section cx-readout" aria-label={t('What this level measured', 'Lo que midió este nivel')}>
          {(MEASURED[caseId] ?? []).map(([key, label, digits]) => {
            const value = measured[key];
            return (
              <div className="cx-readout-row" key={key}>
                <span>{t(label[0], label[1])}</span>
                <strong>{typeof value === 'number' ? num(value, digits) : value === null || value === undefined ? t('none', 'ninguno') : String(value)}</strong>
              </div>
            );
          })}
          <div className="cx-readout-row"><span>{t('Category', 'Categoría')}</span><strong>{t(CATEGORIES[clip.category]?.[0] ?? clip.category, CATEGORIES[clip.category]?.[1] ?? clip.category)}</strong></div>
          <div className="cx-readout-row"><span>{t('Grades', 'Evalúa')}</span><strong>{clip.grades.join(', ')}</strong></div>
        </section>

        <p className="cx-provenance" data-verified={loaded.verified ? 'true' : 'false'}>
          {clip.license}.{' '}
          {loaded.verified
            ? t('Clip verified against its manifest (SHA-256).', 'Clip verificado contra su manifiesto (SHA-256).')
            : t('Clip NOT verified against its manifest.', 'Clip NO verificado contra su manifiesto.')}
        </p>
      </aside>

      <section className="cx-main" aria-label={t('What the eye sees', 'Lo que ve el ojo')}>
        <Tabs
          ariaLabel={t('Eye views', 'Vistas del ojo')}
          tabs={[
            { id: 'eye', label: t('Input and ground truth', 'Entrada y verdad de terreno'), content: <>{stage}{strip}</> },
            { id: 'levels', label: t('All six levels', 'Los seis niveles'), content: <>{acrossLevels}{strip}</> },
            { id: 'time', label: t('Over time', 'En el tiempo'), content: <>{overTime}{strip}</> },
          ]}
        />
      </section>
    </div>
  );
}
