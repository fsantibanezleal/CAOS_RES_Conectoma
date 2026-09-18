import type { Direction, Model, Partner } from './model';
import { useNumber, useT } from '../lib/i18n';

/**
 * The partners of the selected type, strongest first, as bars of synapses per target cell. Choosing one
 * shows its filter in the lattice view, so the list and the filter are one instrument.
 */
export default function PartnerList({ model, partners, selected, direction, onSelect }: {
  model: Model;
  partners: Partner[];
  selected: number | null;
  direction: Direction;
  onSelect: (connection: number) => void;
}) {
  const t = useT();
  const num = useNumber();
  const peak = Math.max(1e-9, ...partners.map((p) => p.total));
  return (
    <section className="cx-rail-section cx-partners" aria-label={direction === 'receives' ? t('Sources', 'Fuentes') : t('Targets', 'Destinos')}>
      <div className="cx-partners-head">
        <span>{direction === 'receives' ? t('Sources', 'Fuentes') : t('Targets', 'Destinos')}</span>
        <span className="cx-muted">{t('synapses per target cell', 'sinapsis por célula destino')}</span>
      </div>
      <ol className="cx-partners-list">
        {partners.map((p) => {
          const type = model.explorer.types[p.type];
          return (
            <li key={p.connection}>
              <button
                type="button"
                className={p.connection === selected ? 'cx-partner active' : 'cx-partner'}
                onClick={() => onSelect(p.connection)}
                title={t(
                  `${type.name}: ${num(p.total, 2)} synapses per target cell, ${p.sign > 0 ? 'excitatory' : 'inhibitory'}, support ${num(p.certainty, 2)} connected cell pairs per target cell`,
                  `${type.name}: ${num(p.total, 2)} sinapsis por célula destino, ${p.sign > 0 ? 'excitatoria' : 'inhibitoria'}, respaldo ${num(p.certainty, 2)} pares de células conectadas por célula destino`,
                )}
              >
                <span className="cx-partner-name">{type.name}</span>
                <span className="cx-partner-bar">
                  <span
                    className={p.sign > 0 ? 'cx-bar exc' : 'cx-bar inh'}
                    style={{ width: `${Math.max(2, (100 * p.total) / peak)}%` }}
                  />
                </span>
                <span className="cx-partner-value">{num(p.total, p.total < 10 ? 2 : 1)}</span>
              </button>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
