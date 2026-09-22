import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { useSearchParams } from 'react-router';
import { Tabs } from '@fasl-work/caos-app-shell';
import { loadExplorer, type Verified } from '../api/artifacts';
import type { CellType, Explorer, TypeGroup } from '../lib/contract.types';
import { useNumber, useT } from '../lib/i18n';
import HexFilter, { type Panel } from '../explorer/HexFilter';
import PartnerList from '../explorer/PartnerList';
import Placement from '../explorer/Placement';
import EyeMode from '../eye/EyeMode';
import {
  angleBetween,
  buildModel,
  centralCount,
  cosine,
  displacement,
  partnersOf,
  placementLabel,
  publishedFor,
  type Direction,
} from '../explorer/model';

const GROUPS: { id: TypeGroup; en: string; es: string }[] = [
  { id: 'input', en: 'Photoreceptors (inputs)', es: 'Fotorreceptores (entradas)' },
  { id: 'output', en: 'T4 and T5 (motion outputs)', es: 'T4 y T5 (salidas de movimiento)' },
  { id: 'stride1', en: 'On every column', es: 'En cada columna' },
  { id: 'stride2', en: 'On every second column', es: 'Cada dos columnas' },
  { id: 'stride3', en: 'On every third column', es: 'Cada tres columnas' },
  { id: 'stride4', en: 'On every fourth column', es: 'Cada cuatro columnas' },
  { id: 'population', en: 'Population nodes (sparse types)', es: 'Nodos de población (tipos escasos)' },
];

const DEFAULT_TYPE = 'T4a';

type Mode = 'connectome' | 'eye';

/**
 * The App has two modes, switched in the rail so the page keeps one row of tabs: the connectome explorer
 * (the wiring the network is built from) and the eye's input (what its 721 columns see in each case).
 */
export default function AppPage() {
  const t = useT();
  const [params, setParams] = useSearchParams();
  const mode: Mode = params.get('mode') === 'eye' ? 'eye' : 'connectome';
  const switcher = (
    <div className="cx-segmented cx-mode" role="radiogroup" aria-label={t('App mode', 'Modo de la aplicación')}>
      {(['connectome', 'eye'] as Mode[]).map((m) => (
        <button
          key={m}
          type="button"
          role="radio"
          aria-checked={mode === m}
          className={mode === m ? 'active' : ''}
          onClick={() => {
            const next = new URLSearchParams(params);
            if (m === 'eye') next.set('mode', 'eye');
            else next.delete('mode');
            setParams(next, { replace: true });
          }}
        >
          {m === 'connectome' ? t('Connectome', 'Conectoma') : t('Eye input', 'Entrada del ojo')}
        </button>
      ))}
    </div>
  );
  return mode === 'eye' ? <EyeMode switcher={switcher} /> : <ConnectomeMode switcher={switcher} />;
}

function ConnectomeMode({ switcher }: { switcher: ReactNode }) {
  const t = useT();
  const num = useNumber();
  const [loaded, setLoaded] = useState<Verified<Explorer> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [params, setParams] = useSearchParams();

  useEffect(() => {
    loadExplorer().then(setLoaded).catch((e) => setError(String(e)));
  }, []);

  const model = useMemo(() => (loaded ? buildModel(loaded.data) : null), [loaded]);

  const typeName = params.get('type') ?? DEFAULT_TYPE;
  const direction: Direction = params.get('view') === 'sends' ? 'sends' : 'receives';
  const minimum = Number(params.get('min') ?? '0') || 0;
  const compare = params.get('compare') !== 'off';

  const typeIndex = model?.byName.get(typeName) ?? model?.byName.get(DEFAULT_TYPE) ?? 0;
  const type: CellType | null = model ? model.explorer.types[typeIndex] : null;
  const partners = useMemo(
    () => (model ? partnersOf(model, typeIndex, direction).filter((p) => p.total >= minimum) : []),
    [model, typeIndex, direction, minimum],
  );
  const requested = params.get('partner');
  const partner =
    partners.find((p) => model?.explorer.types[p.type].name === requested) ?? partners[0] ?? null;

  function update(changes: Record<string, string | null>) {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(changes)) {
      if (value === null) next.delete(key);
      else next.set(key, value);
    }
    setParams(next, { replace: true });
  }

  if (error) {
    return (
      <div className="page-body wide cx-app">
        <aside className="cx-rail">{switcher}</aside>
        <section className="cx-main"><p className="cx-muted">{t('The connectome artifact could not be loaded: ', 'No se pudo cargar el artefacto del conectoma: ')}{error}</p></section>
      </div>
    );
  }
  if (!model || !type || !loaded) {
    return (
      <div className="page-body wide cx-app">
        <aside className="cx-rail">{switcher}</aside>
        <section className="cx-main"><p className="cx-muted">{t('Loading the connectome...', 'Cargando el conectoma...')}</p></section>
      </div>
    );
  }

  const other = partner ? model.explorer.types[partner.type] : null;
  const source = direction === 'receives' ? other?.name ?? '' : type.name;
  const target = direction === 'receives' ? type.name : other?.name ?? '';
  const published = partner ? publishedFor(model, source, target) : undefined;
  const allIncoming = model.incoming[typeIndex].reduce((a, p) => a + p.total, 0);

  const panels: Panel[] = [];
  if (partner) {
    panels.push({
      key: 'malecns',
      title: t(`MaleCNS: ${source} onto ${target}`, `MaleCNS: ${source} sobre ${target}`),
      filter: partner.filter,
      sign: partner.sign,
    });
    if (compare && published) {
      panels.push({
        key: 'published',
        title: t(
          `Published consensus: ${published.src} onto ${published.tar}`,
          `Consenso publicado: ${published.src} sobre ${published.tar}`,
        ),
        filter: { du: published.du, dv: published.dv, n: published.n },
        sign: published.sign,
      });
    }
  }

  const similarity = partner && published ? cosine(partner.filter, { du: published.du, dv: published.dv, n: published.n }) : null;
  const ours = partner ? displacement(partner.filter) : null;
  const theirs = published ? displacement({ du: published.du, dv: published.dv, n: published.n }) : null;
  const turn = ours && theirs && Math.hypot(...ours) >= 0.4 && Math.hypot(...theirs) >= 0.4 ? angleBetween(ours, theirs) : null;

  const typesByGroup = GROUPS.map((g) => ({
    ...g,
    types: model.explorer.types.filter((x) => x.group === g.id).sort((a, b) => a.name.localeCompare(b.name)),
  })).filter((g) => g.types.length);

  const strip = partner && other ? (
    <div className="cx-strip" aria-live="polite">
      <span><strong>{source}</strong> {t('onto', 'sobre')} <strong>{target}</strong>: <strong>{num(partner.total, 2)}</strong> {t('synapses per target cell', 'sinapsis por célula destino')}</span>
      <span title={t('Connected cell pairs per target cell, averaged over the filter entries', 'Pares de células conectadas por célula destino, promediados sobre las entradas del filtro')}>
        {t('support', 'respaldo')} <strong>{num(partner.certainty, 2)}</strong>
      </span>
      {published ? (
        <>
          <span>{t('central column', 'columna central')} <strong>{num(centralCount(partner.filter), 1)}</strong> {t('vs', 'vs')} <strong>{num(centralCount({ du: published.du, dv: published.dv, n: published.n }), 1)}</strong> {t('published', 'publicado')}</span>
          <span>{t('cosine', 'coseno')} <strong>{similarity === null ? '-' : num(similarity, 2)}</strong></span>
          <span>{t('directions differ by', 'direcciones difieren en')} <strong>{turn === null ? t('no clear direction', 'sin dirección clara') : `${num(turn, 0)}°`}</strong></span>
        </>
      ) : (
        <span>{t('no published counterpart for this pair', 'este par no tiene contraparte publicada')}</span>
      )}
    </div>
  ) : null;

  const filterView = (
    <>
      <div className="cx-filter-stage">
        {partner ? (
          <HexFilter panels={panels} direction={direction} minimum={0} />
        ) : (
          <p className="cx-muted">
            {t('No connection of this type passes the minimum.', 'Ninguna conexión de este tipo supera el mínimo.')}
          </p>
        )}
      </div>
      {strip}
    </>
  );

  return (
    <div className="page-body wide cx-app">
      <aside className="cx-rail" aria-label={t('Explorer controls', 'Controles del explorador')}>
        {switcher}
        <section className="cx-rail-section">
          <label className="cx-label" htmlFor="cx-type">{t('Cell type', 'Tipo celular')}</label>
          <select
            id="cx-type"
            className="cx-select"
            value={type.name}
            onChange={(e) => update({ type: e.target.value, partner: null })}
          >
            {typesByGroup.map((g) => (
              <optgroup key={g.id} label={`${t(g.en, g.es)} (${g.types.length})`}>
                {g.types.map((x) => (
                  <option key={x.name} value={x.name}>{x.name}</option>
                ))}
              </optgroup>
            ))}
          </select>

          <div className="cx-segmented" role="radiogroup" aria-label={t('Direction', 'Dirección')}>
            {(['receives', 'sends'] as Direction[]).map((d) => (
              <button
                key={d}
                type="button"
                role="radio"
                aria-checked={direction === d}
                className={direction === d ? 'active' : ''}
                onClick={() => update({ view: d === 'receives' ? null : d, partner: null })}
              >
                {d === 'receives' ? t('what it receives', 'lo que recibe') : t('what it sends', 'lo que envía')}
              </button>
            ))}
          </div>

          <label className="cx-label" htmlFor="cx-min">
            {t('Minimum synapses per target cell', 'Mínimo de sinapsis por célula destino')}: <strong>{num(minimum, 1)}</strong>
          </label>
          <input
            id="cx-min"
            type="range"
            min={0}
            max={20}
            step={0.5}
            value={minimum}
            onChange={(e) => update({ min: e.target.value === '0' ? null : e.target.value, partner: null })}
            title={t(
              'Hides partners whose whole filter carries fewer synapses per target cell than this.',
              'Oculta los socios cuyo filtro completo aporta menos sinapsis por célula destino que esto.',
            )}
          />

          <label className="cx-check">
            <input
              type="checkbox"
              checked={compare}
              disabled={!published}
              onChange={(e) => update({ compare: e.target.checked ? null : 'off' })}
            />
            {published
              ? t('Compare with the published consensus', 'Comparar con el consenso publicado')
              : t('No published counterpart for this pair', 'Este par no tiene contraparte publicada')}
          </label>
        </section>

        <section className="cx-rail-section cx-readout" aria-label={type.name}>
          <div className="cx-readout-row"><span>{t('Placement', 'Ubicación')}</span><strong>{placementLabel(type, t)}</strong></div>
          <div className="cx-readout-row"><span>{t('Cells in the eye', 'Células en el ojo')}</span><strong>{num(type.cells ?? 0)}</strong></div>
          <div className="cx-readout-row"><span>{t('Transmitter sign', 'Signo del transmisor')}</span><strong>{type.sign > 0 ? t('excitatory', 'excitatorio') : type.sign < 0 ? t('inhibitory', 'inhibitorio') : t('sends nothing', 'no envía')}</strong></div>
          <div className="cx-readout-row"><span>{t('Synapses received per cell', 'Sinapsis recibidas por célula')}</span><strong>{num(allIncoming, 1)}</strong></div>
        </section>

        <PartnerList
          model={model}
          partners={partners}
          selected={partner?.connection ?? null}
          direction={direction}
          onSelect={(connection) => {
            const p = partners.find((x) => x.connection === connection);
            if (p) update({ partner: model.explorer.types[p.type].name });
          }}
        />

        <p className="cx-provenance" data-verified={loaded.verified ? 'true' : 'false'}>
          {t('MaleCNS v1.0 (CC-BY), right optic lobe; ', 'MaleCNS v1.0 (CC-BY), lóbulo óptico derecho; ')}
          {loaded.verified
            ? t('artifact verified against its manifest (SHA-256).', 'artefacto verificado contra su manifiesto (SHA-256).')
            : t('artifact NOT verified against its manifest.', 'artefacto NO verificado contra su manifiesto.')}
        </p>
      </aside>

      <section className="cx-main" aria-label={t('Connectome views', 'Vistas del conectoma')}>
        <Tabs
          ariaLabel={t('Connectome views', 'Vistas del conectoma')}
          tabs={[
            { id: 'filters', label: t('Filters', 'Filtros'), content: filterView },
            {
              id: 'placement',
              label: t('Placement', 'Ubicación'),
              content: (
                <Placement
                  type={type}
                  types={model.explorer.types}
                  eyeColumns={model.explorer.placement?.columns ?? 0}
                  onSelect={(name) => update({ type: name, partner: null })}
                />
              ),
            },
          ]}
        />
      </section>
    </div>
  );
}
