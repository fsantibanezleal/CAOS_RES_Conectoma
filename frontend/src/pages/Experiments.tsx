import { Callout, Equation, SubTabs } from '@fasl-work/caos-app-shell';
import SectionRefs from '../components/SectionRefs';
import { useNumber, useT } from '../lib/i18n';
import { useState } from 'react';
import InlineSvg from '../components/InlineSvg';
import { CASE_NAMES, CATEGORIES, levelLabel, MEASURED, QUANTITIES } from '../eye/text';
import { useReports, type SpacingRange } from '../lib/reports';

const MOTION = ['T4a', 'T4b', 'T4c', 'T4d', 'T5a', 'T5b', 'T5c', 'T5d'];

export default function Experiments() {
  const t = useT();
  const num = useNumber();
  const { reports, error } = useReports();
  const [caseId, setCaseId] = useState('C01');

  const head = (
    <div className="page-head">
      <h1>{t('Experiments', 'Experimentos')}</h1>
      <p className="lede">
        {t(
          'Every experiment run so far, each with the question it answers, the protocol, and the measured result read from the committed report it produced. They validate the connectome and the network rather than any vision method: whether the inferred columns are right, whether the build agrees with the published consensus and points the right way, whether this product’s network is the published one when given the published connectome, what the published ensemble does, and what the frozen MaleCNS networks do before any training.',
          'Cada experimento corrido hasta ahora, cada uno con la pregunta que responde, el protocolo y el resultado medido leído del reporte versionado que produjo. Validan el conectoma y la red más que cualquier método de visión: si las columnas inferidas son correctas, si la construcción coincide con el consenso publicado y apunta en la dirección correcta, si la red de este producto es la publicada cuando recibe el conectoma publicado, qué hace el ensamble publicado, y qué hacen las redes MaleCNS congeladas antes de cualquier entrenamiento.',
        )}
      </p>
    </div>
  );

  if (error || !reports) {
    return (
      <div className="page-body wide prose">
        {head}
        <p className="cx-muted">{error ? t('A report could not be loaded: ', 'No se pudo cargar un reporte: ') + error : t('Loading the reports...', 'Cargando los reportes...')}</p>
      </div>
    );
  }
  const { build, comparison, parity, lattice, visualCns, visualCnsSummary } = reports;
  const pct = (x: number, d = 1) => `${num(100 * x, d)}%`;

  const holdout = (
    <section>
      <h2>{t('Are the inferred columns right?', '¿Son correctas las columnas inferidas?')}</h2>
      <p>
        {t(
          'The release annotates columns for 15 cell types, and the build infers the rest from connectivity. The protocol holds out each annotated type in turn, re-infers its columns from the other annotated types only, and measures the error in lattice columns. No held-out type contributes to its own inference, so the test is free of leakage by construction.',
          'La liberación anota columnas para 15 tipos celulares, y la construcción infiere el resto desde la conectividad. El protocolo excluye por turno cada tipo anotado, reinfiere sus columnas solo desde los otros tipos anotados, y mide el error en columnas de la retícula. Ningún tipo excluido contribuye a su propia inferencia, así que la prueba está libre de fuga por construcción.',
        )}
      </p>
      <div className="cx-table-wrap">
        <table className="cx-table">
          <thead>
            <tr>
              <th>{t('Held-out type', 'Tipo excluido')}</th>
              <th className="num">{t('Neurons', 'Neuronas')}</th>
              <th className="num">{t('Exact column', 'Columna exacta')}</th>
              <th className="num">{t('Within one', 'A una o menos')}</th>
              <th className="num">{t('95th percentile error', 'Error percentil 95')}</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(build.column_inference.holdout.per_type).map(([name, row]) => (
              <tr key={name}>
                <td>{name}</td>
                <td className="num">{num(row.n)}</td>
                <td className="num">{pct(row.exact_fraction, 2)}</td>
                <td className="num">{pct(row.within_one_fraction, 2)}</td>
                <td className="num">{num(row.p95_error_columns, 0)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p>
        {t(
          `Median over types: ${pct(build.column_inference.holdout.summary.median_exact_fraction, 2)} exact and ${pct(build.column_inference.holdout.summary.median_within_one_fraction, 2)} within one column; the worst 95th percentile error is ${num(build.column_inference.holdout.summary.worst_p95_error_columns, 0)} columns. The build placed ${num(build.column_inference.inferred)} neurons by inference, ${num(build.column_assignment)} carried an annotation, and ${num(build.column_inference.unplaced)} could not be placed.`,
          `Mediana sobre tipos: ${pct(build.column_inference.holdout.summary.median_exact_fraction, 2)} exactas y ${pct(build.column_inference.holdout.summary.median_within_one_fraction, 2)} a una columna o menos; el peor error de percentil 95 es de ${num(build.column_inference.holdout.summary.worst_p95_error_columns, 0)} columnas. La construcción ubicó ${num(build.column_inference.inferred)} neuronas por inferencia, ${num(build.column_assignment)} traían una anotación, y ${num(build.column_inference.unplaced)} no pudieron ubicarse.`,
        )}
      </p>
      <SectionRefs ids={['nern2025', 'berg2026']} />
    </section>
  );

  const consensus = (
    <section>
      <h2>{t('Does the build agree with the published consensus?', '¿Coincide la construcción con el consenso publicado?')}</h2>
      <p>
        {t(
          'The reference is the consensus connectome of the published model, distilled from the earlier FIB-25 and FIB-19 medulla reconstructions. It comes from other animals and another pipeline, so the question is agreement, not identity. Cross-release renames are mapped explicitly; reference types with no counterpart are reported as unmatched rather than mapped onto something similar.',
          'La referencia es el conectoma de consenso del modelo publicado, destilado de las reconstrucciones anteriores FIB-25 y FIB-19 de la médula. Viene de otros animales y de otro pipeline, así que la pregunta es de acuerdo, no de identidad. Los cambios de nombre entre liberaciones se mapean explícitamente; los tipos de referencia sin contraparte se informan como sin correspondencia en vez de mapearse a algo parecido.',
        )}
      </p>
      <div className="cx-table-wrap">
        <table className="cx-table">
          <tbody>
            <tr><td>{t('Reference types matched', 'Tipos de referencia con correspondencia')}</td><td className="num">{comparison.types.reference_matched} / {comparison.types.reference}</td></tr>
            <tr><td>{t('Comparable reference connections recovered', 'Conexiones de referencia comparables recuperadas')}</td><td className="num">{comparison.connections.recovered} / {comparison.connections.reference_comparable} ({pct(comparison.connections.recovered_fraction)})</td></tr>
            <tr><td>{t('Sign agreement on recovered connections', 'Acuerdo de signo en conexiones recuperadas')}</td><td className="num">{comparison.signs.agreeing} / {comparison.signs.compared} ({pct(comparison.signs.agreement_fraction)})</td></tr>
            <tr><td>{t('Rank correlation of central synapse counts', 'Correlación de rangos de conteos centrales')}</td><td className="num">{num(comparison.central_synapse_counts.spearman, 2)} ({t('over', 'sobre')} {comparison.central_synapse_counts.n})</td></tr>
            <tr><td>{t('Unmatched reference types', 'Tipos de referencia sin correspondencia')}</td><td>{comparison.types.reference_unmatched.join(', ')}</td></tr>
          </tbody>
        </table>
      </div>
      <Callout variant="note" title={t('The disagreements', 'Los desacuerdos')}>
        {t(
          `The ${comparison.signs.compared - comparison.signs.agreeing} sign disagreements are evidence conflicts rather than defects: the reference derives a connection’s sign from receptor expression per pair of types, this build from the per-synapse transmitter classifier of the release. The sign-shuffled control measures how much any result depends on them.`,
          `Los ${comparison.signs.compared - comparison.signs.agreeing} desacuerdos de signo son conflictos de evidencia más que defectos: la referencia deriva el signo de una conexión desde la expresión de receptores por par de tipos, esta construcción desde el clasificador de transmisor por sinapsis de la liberación. El control de signos permutados mide cuánto depende de ellos cualquier resultado.`,
        )}
      </Callout>
      <SectionRefs ids={['lappalainen2024', 'takemura2015', 'takemura2017', 'eckstein2024']} />
    </section>
  );

  const orientationRows = Object.entries(comparison.orientation.by_symmetry)
    .filter((entry): entry is [string, number] => entry[1] !== null)
    .sort((a, b) => b[1] - a[1]);
  const orientation = (
    <section>
      <h2>{t('Do the filters point the right way?', '¿Apuntan los filtros en la dirección correcta?')}</h2>
      <p>
        {t(
          'A count comparison cannot see a rotated or mirrored frame. This experiment compares the direction of every spatially extended filter shared with the reference, under each of the twelve symmetries of the hexagonal lattice, weighted by the length of the reference’s displacement. A build in the reference’s frame scores highest with the identity.',
          'Una comparación de conteos no puede ver un marco rotado o reflejado. Este experimento compara la dirección de cada filtro espacialmente extendido compartido con la referencia, bajo cada una de las doce simetrías de la retícula hexagonal, ponderada por la longitud del desplazamiento de la referencia. Una construcción en el marco de la referencia obtiene la mayor puntuación con la identidad.',
        )}
      </p>
      <Equation
        tex="A(g) = \frac{\sum_k \lVert d^{\mathrm{ref}}_k \rVert \cos\angle\big(d^{\mathrm{ref}}_k,\ g\cdot d^{\mathrm{here}}_k\big)}{\sum_k \lVert d^{\mathrm{ref}}_k \rVert}"
        caption={t('The directional agreement under a lattice symmetry g.', 'El acuerdo direccional bajo una simetría g de la retícula.')}
      />
      <div className="cx-table-wrap">
        <table className="cx-table">
          <thead><tr><th>{t('Symmetry (what (u, v) becomes)', 'Simetría (en qué se convierte (u, v))')}</th><th className="num">{t('Agreement', 'Acuerdo')}</th></tr></thead>
          <tbody>
            {orientationRows.map(([name, value]) => (
              <tr key={name}><td>{name === '+(u,v)' ? `${name} ${t('(identity)', '(identidad)')}` : name}</td><td className="num">{num(value, 3)}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
      <p>
        {t(
          `Over ${comparison.orientation.filters_compared} filters the best symmetry is ${comparison.orientation.best}. Before the build wrote its offsets half-turned, the identity was the worst of the twelve.`,
          `Sobre ${comparison.orientation.filters_compared} filtros la mejor simetría es ${comparison.orientation.best}. Antes de que la construcción escribiera sus desplazamientos con medio giro, la identidad era la peor de las doce.`,
        )}
      </p>
      <SectionRefs ids={['maisak2013']} />
    </section>
  );

  const parityTab = (
    <section>
      <h2>{t('Is this network the published one?', '¿Es esta red la publicada?')}</h2>
      <p>
        {t(
          'The published model is loaded twice from the same checkpoint: by the engine’s own loader, and through this product’s compiler and regime builder with the published connectome as the specification. Both are driven with the same moving edges and every voltage of every cell is compared. Faster edges are shorter and are padded with missing values to the longest one, so the comparison requires the padding to sit at the same places in both and compares every finite value.',
          'El modelo publicado se carga dos veces desde el mismo punto de control: con el cargador propio del motor, y a través del compilador y el constructor de regímenes de este producto con el conectoma publicado como especificación. Ambos se estimulan con los mismos bordes en movimiento y se compara cada voltaje de cada célula. Los bordes más rápidos son más cortos y se rellenan con valores faltantes hasta el más largo, así que la comparación exige que el relleno quede en los mismos lugares en ambos y compara cada valor finito.',
        )}
      </p>
      <div className="cx-table-wrap">
        <table className="cx-table">
          <thead><tr><th>{t('Model', 'Modelo')}</th><th className="num">{t('Cells', 'Células')}</th><th className="num">{t('Values compared', 'Valores comparados')}</th><th className="num">{t('Largest voltage', 'Mayor voltaje')}</th><th className="num">{t('Largest difference', 'Mayor diferencia')}</th><th>{t('Passed', 'Pasa')}</th></tr></thead>
          <tbody>
            {parity.voltage_parity.map((row) => (
              <tr key={row.model}>
                <td>{row.model}</td>
                <td className="num">{num(row.cells)}</td>
                <td className="num">{num(row.values_compared)}</td>
                <td className="num">{num(row.largest_voltage, 2)}</td>
                <td className="num">{row.max_abs_difference.toExponential(1)}</td>
                <td>{row.passed && row.same_padding ? t('yes', 'sí') : t('no', 'no')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p>
        {t(
          `The tuning analysis is checked the same way: models ${parity.pipeline_crosscheck.models.join(', ')} run through the engine’s own end-to-end pipeline give a largest direction-selectivity difference of ${num(parity.pipeline_crosscheck.largest_dsi_difference, 4)} and a largest direction difference of ${num(parity.pipeline_crosscheck.largest_direction_difference_degrees, 1)} degrees.`,
          `El análisis de ajuste se verifica igual: los modelos ${parity.pipeline_crosscheck.models.join(', ')} corridos por el pipeline completo del motor dan una mayor diferencia de selectividad a la dirección de ${num(parity.pipeline_crosscheck.largest_dsi_difference, 4)} y una mayor diferencia de dirección de ${num(parity.pipeline_crosscheck.largest_direction_difference_degrees, 1)} grados.`,
        )}
      </p>
      <SectionRefs ids={['lappalainen2024', 'flyvis']} />
    </section>
  );

  const q = parity.tuning.quality;
  const ensemble = (
    <section>
      <h2>{t('What does the published ensemble do with moving edges?', '¿Qué hace el ensamble publicado con bordes en movimiento?')}</h2>
      <p>
        {t(
          'Every model of the published ensemble, built through this product’s path, is shown edges of both polarities sweeping in twelve directions at six speeds. The direction selectivity index of a cell is the length of the vector sum of its peak responses over directions divided by their sum; the preferred direction is the angle of that sum. T4 is read at bright edges and T5 at dark edges.',
          'Cada modelo del ensamble publicado, construido por la ruta de este producto, recibe bordes de ambas polaridades barriendo en doce direcciones a seis velocidades. El índice de selectividad a la dirección de una célula es la longitud de la suma vectorial de sus respuestas máximas sobre direcciones dividida por su suma; la dirección preferida es el ángulo de esa suma. T4 se lee con bordes claros y T5 con bordes oscuros.',
        )}
      </p>
      <Equation
        tex="\mathrm{DSI} = \frac{\left|\sum_\theta r_\theta\, e^{i\theta}\right|}{\sum_\theta r_\theta}"
        caption={t('Direction selectivity: 0 for no preference, 1 for a response to a single direction.', 'Selectividad a la dirección: 0 sin preferencia, 1 para una respuesta a una sola dirección.')}
      />
      <div className="cx-table-wrap">
        <table className="cx-table">
          <thead><tr><th>{t('Subtype', 'Subtipo')}</th><th className="num">{t('Median DSI', 'DSI mediano')}</th><th className="num">{t('Tuned as known', 'Ajustado como se conoce')}</th><th className="num">{t('Strongly reversed', 'Fuertemente invertido')}</th><th className="num">{t('Weak', 'Débil')}</th></tr></thead>
          <tbody>
            {MOTION.map((name) => (
              <tr key={name}>
                <td>{name}</td>
                <td className="num">{num(parity.tuning.summary[name].median_dsi, 2)}</td>
                <td className="num">{q.by_subtype[name].as_known}</td>
                <td className="num">{q.by_subtype[name].reversed}</td>
                <td className="num">{q.by_subtype[name].weak}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p>
        {t(
          `Tuned as known means an index of at least ${num(q.criteria.min_dsi, 1)} with a direction within ${q.criteria.within_degrees} degrees of the known one; strongly reversed, as selective but more than ${q.criteria.reversed_beyond} degrees off. Counting the subtypes tuned as known per model, by task rank:`,
          `Ajustado como se conoce significa un índice de al menos ${num(q.criteria.min_dsi, 1)} con una dirección a ${q.criteria.within_degrees} grados o menos de la conocida; fuertemente invertido, igual de selectivo pero a más de ${q.criteria.reversed_beyond} grados. Contando los subtipos ajustados como se conoce por modelo, según el rango de la tarea:`,
        )}
      </p>
      <div className="cx-table-wrap">
        <table className="cx-table">
          <thead><tr><th>{t('Models, best first', 'Modelos, mejores primero')}</th><th className="num">{t('Subtypes tuned as known', 'Subtipos ajustados como se conoce')}</th></tr></thead>
          <tbody>
            {q.by_rank.map((row) => (
              <tr key={row.models}><td>{row.models}</td><td className="num">{row.as_known} / {row.of}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
      <p>
        {t(
          `The rank correlation between task rank and that count is ${num(q.rank_correlation, 2)}: models that solve the optic-flow task better show more realistic motion tuning, which is the published observation. The tuning is a property of the good solutions, not of every trained network.`,
          `La correlación de rangos entre el rango de la tarea y ese conteo es ${num(q.rank_correlation, 2)}: los modelos que resuelven mejor la tarea de flujo óptico muestran un ajuste al movimiento más realista, que es la observación publicada. El ajuste es una propiedad de las buenas soluciones, no de toda red entrenada.`,
        )}
      </p>
      <SectionRefs ids={['lappalainen2024', 'maisak2013']} />
    </section>
  );

  const frozen = (
    <section>
      <h2>{t('What does the frozen MaleCNS lattice do?', '¿Qué hace la retícula MaleCNS congelada?')}</h2>
      <p>
        {t(
          'The measured connectome, compiled on the lattice with no training, from two starting points: the engine’s initialisation, and the published model’s trained values transferred where cell types match. Each is checked for stability, timed, and shown the same moving edges as the published ensemble, next to five seeds of each size-matched control.',
          'El conectoma medido, compilado en la retícula sin entrenamiento, desde dos puntos de partida: la inicialización del motor, y los valores entrenados del modelo publicado transferidos donde los tipos coinciden. Cada uno se verifica en estabilidad, se cronometra, y recibe los mismos bordes en movimiento que el ensamble publicado, junto a cinco semillas de cada control igualado en tamaño.',
        )}
      </p>
      <div className="cx-table-wrap">
        <table className="cx-table">
          <thead><tr><th>{t('Network', 'Red')}</th><th>{t('Settled', 'Estable')}</th><th className="num">{t('Voltage range', 'Rango de voltaje')}</th><th className="num">{t('Loop gain', 'Ganancia de lazo')}</th></tr></thead>
          <tbody>
            {(['default', 'transfer'] as const).map((init) => (
              <tr key={init}>
                <td>{init === 'default' ? t('engine initialisation', 'inicialización del motor') : t('published values transferred', 'valores publicados transferidos')}</td>
                <td>{lattice.frozen[init].settled ? t('yes', 'sí') : t('no', 'no')}</td>
                <td className="num">{num(lattice.frozen[init].stability.min, 2)} {t('to', 'a')} {num(lattice.frozen[init].stability.max, 2)}</td>
                <td className="num">{num(lattice.frozen[init].loop_gain.spectral_radius, 2)}</td>
              </tr>
            ))}
            {Object.entries(lattice.controls).map(([kind, row]) => (
              <tr key={kind}>
                <td>{kind} ({row.seeds.length} {t('seeds', 'semillas')})</td>
                <td>{row.settled.every(Boolean) ? t('yes, all', 'sí, todas') : t('not all', 'no todas')}</td>
                <td className="num">{num(Math.min(...row.stability.map((s) => s.min)), 2)} {t('to', 'a')} {num(Math.max(...row.stability.map((s) => s.max)), 2)}</td>
                <td className="num">-</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="cx-table-wrap">
        <table className="cx-table">
          <thead><tr><th>{t('Subtype', 'Subtipo')}</th><th className="num">{t('DSI, engine init', 'DSI, init. del motor')}</th><th className="num">{t('DSI, transferred', 'DSI, transferidos')}</th><th className="num">{t('Largest change, engine init', 'Mayor cambio, init. del motor')}</th><th className="num">{t('Rest, transferred', 'Reposo, transferidos')}</th><th className="num">{t('Largest control DSI', 'Mayor DSI de control')}</th></tr></thead>
          <tbody>
            {MOTION.map((name) => (
              <tr key={name}>
                <td>{name}</td>
                <td className="num">{num(lattice.frozen.default.tuning_summary[name].median_dsi, 2)}</td>
                <td className="num">{num(lattice.frozen.transfer.tuning_summary[name].median_dsi, 2)}</td>
                <td className="num">{num(lattice.frozen.default.motion_activity[name].largest_change_from_rest, 4)}</td>
                <td className="num">{num(lattice.frozen.transfer.motion_activity[name].resting_voltage, 2)}</td>
                <td className="num">{num(Math.max(...Object.values(lattice.controls).map((c) => c.tuning_summary[name].median_dsi)), 3)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Callout variant="honest" title={t('The frozen network is not a motion detector', 'La red congelada no es un detector de movimiento')}>
        {t(
          'From the engine’s initialisation the edges barely reach T4 and T5; with the published values T4 sits below threshold and T5 is driven but equally for every direction. The controls are just as untuned, so tuning cannot tell the measured wiring from them. What separates them, if anything does, has to be a task result.',
          'Desde la inicialización del motor los bordes apenas llegan a T4 y T5; con los valores publicados T4 queda bajo el umbral y T5 es excitada pero igual para toda dirección. Los controles están igual de sin ajuste, así que el ajuste no puede distinguir el cableado medido de ellos. Lo que los separe, si algo lo hace, tiene que ser un resultado de tarea.',
        )}
      </Callout>
      <p>
        {t(
          `The cost of one training step, timed on ${lattice.device} with the engine at batch ${lattice.training_step.R1.batch_size} over ${lattice.training_step.R1.frames} frames. The whole lattice costs about twice the published network per step, and training every connection (R2) costs about the same as training per pair of types (R1).`,
          `El costo de un paso de entrenamiento, cronometrado en ${lattice.device} con el motor en lote ${lattice.training_step.R1.batch_size} sobre ${lattice.training_step.R1.frames} cuadros. La retícula completa cuesta cerca del doble que la red publicada por paso, y entrenar cada conexión (R2) cuesta casi lo mismo que entrenar por par de tipos (R1).`,
        )}
      </p>
      <div className="cx-table-wrap">
        <table className="cx-table">
          <thead><tr><th>{t('Network and regime', 'Red y régimen')}</th><th className="num">{t('Trainable', 'Entrenables')}</th><th className="num">{t('Seconds per step', 'Segundos por paso')}</th><th className="num">{t('Peak memory (GB)', 'Memoria máxima (GB)')}</th></tr></thead>
          <tbody>
            {Object.entries(lattice.training_step).map(([name, row]) => (
              <tr key={name}>
                <td>{name === 'published_R1' ? t('published network, R1', 'red publicada, R1') : `MaleCNS ${t('lattice', 'retícula')}, ${name}`}</td>
                <td className="num">{num(row.trainable)}</td>
                <td className="num">{num(row.seconds_per_step, 3)}</td>
                <td className="num">{num(row.peak_memory_gb, 2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <SectionRefs ids={['lappalainen2024', 'lukosevicius2009']} />
    </section>
  );

  const vd = visualCns.frozen.default;
  const vt = visualCns.frozen.transfer;
  const whole = (
    <section>
      <h2>{t('Is the whole visual system stable as a frozen network?', '¿Es estable el sistema visual completo como red congelada?')}</h2>
      <p>
        {t(
          `Both optic lobes and their projections, neuron by neuron: ${num(visualCnsSummary.neurons)} neurons in ${num(visualCnsSummary.cell_types)} types and ${num(visualCnsSummary.connections)} connections. The experiment measures the loop gain (the spectral radius of the absolute weights), whether the network settles as built and with the gain bounded, and whether a full-field flash on the photoreceptors reaches the readout neurons.`,
          `Ambos lóbulos ópticos y sus proyecciones, neurona por neurona: ${num(visualCnsSummary.neurons)} neuronas en ${num(visualCnsSummary.cell_types)} tipos y ${num(visualCnsSummary.connections)} conexiones. El experimento mide la ganancia de lazo (el radio espectral de los pesos absolutos), si la red se estabiliza tal como se construye y con la ganancia acotada, y si un destello de campo completo sobre los fotorreceptores llega a las neuronas lectoras.`,
        )}
      </p>
      <div className="cx-table-wrap">
        <table className="cx-table">
          <thead><tr><th>{t('Starting point', 'Punto de partida')}</th><th className="num">{t('Gain as built', 'Ganancia construida')}</th><th>{t('Settles as built', 'Estable construida')}</th><th className="num">{t('Scale to 0.9', 'Escala a 0,9')}</th><th>{t('Settles bounded', 'Estable acotada')}</th><th className="num">{t('Readouts reached', 'Lectoras alcanzadas')}</th></tr></thead>
          <tbody>
            {(['default', 'transfer'] as const).map((init) => (
              <tr key={init}>
                <td>{init === 'default' ? t('engine initialisation', 'inicialización del motor') : t('published values transferred', 'valores publicados transferidos')}</td>
                <td className="num">{num(visualCns.unnormalised[init].spectral_radius.spectral_radius, 2)}</td>
                <td>{visualCns.unnormalised[init].settled ? t('yes', 'sí') : t('no', 'no')}</td>
                <td className="num">{num(visualCns.frozen[init].gain.scale, 3)}</td>
                <td>{visualCns.frozen[init].settled ? t('yes', 'sí') : t('no', 'no')}</td>
                <td className="num">{pct(visualCns.frozen[init].flash.by_role.output.responding_fraction)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p>
        {t(
          `${num(vd.gain.largest_component)} of the ${num(vd.compile.nodes)} cells form a single strongly connected component. With the gain bounded, the median readout changes by ${vd.flash.by_role.output.median_change.toExponential(1)} (engine initialisation) and ${vt.flash.by_role.output.median_change.toExponential(1)} (transferred): the signal arrives, weakly. One R1 training step fits in ${num(visualCns.training_step_R1.seconds_per_step, 2)} s and ${num(visualCns.training_step_R1.peak_memory_gb, 1)} GB at a batch of one.`,
          `${num(vd.gain.largest_component)} de las ${num(vd.compile.nodes)} células forman una sola componente fuertemente conexa. Con la ganancia acotada, la lectora mediana cambia en ${vd.flash.by_role.output.median_change.toExponential(1)} (inicialización del motor) y ${vt.flash.by_role.output.median_change.toExponential(1)} (transferidos): la señal llega, débil. Un paso de entrenamiento R1 cabe en ${num(visualCns.training_step_R1.seconds_per_step, 2)} s y ${num(visualCns.training_step_R1.peak_memory_gb, 1)} GB con lote de uno.`,
        )}
      </p>
      <SectionRefs ids={['lukosevicius2009', 'lehoucq1998', 'berg2026']} />
    </section>
  );

  const { vision, cases } = reports;
  const sources = vision.sources;
  const gb = (bytes: number) => `${num(bytes / 1e9, 1)} GB`;
  const range = (r: SpacingRange | number) =>
    typeof r === 'number'
      ? num(r, 2)
      : t(`${num(r.min, 2)} to ${num(r.max, 2)} (median ${num(r.median, 2)})`, `${num(r.min, 2)} a ${num(r.max, 2)} (mediana ${num(r.median, 2)})`);
  const rendered = [
    ['TartanAir V2', sources.tartanair],
    ['Spring', sources.spring],
    ['Hypersim', sources.hypersim],
  ] as const;
  const splitNames: Record<string, [string, string]> = {
    train: ['train', 'entrenamiento'],
    validation: ['validation', 'validación'],
    calibration: ['calibration', 'calibración'],
    test: ['test', 'prueba'],
  };
  const visionTab = (
    <section>
      <h2>{t('What does the eye get, and from where?', '¿Qué recibe el ojo, y de dónde?')}</h2>
      <p>
        {t(
          'Every source fetched for the vision lane, rendered onto the 721-column lattice and checked by contract 1 before anything reads it. A clip that breaks the contract is rejected with its reasons, never repaired; masked depth is counted, never dropped.',
          'Cada fuente descargada para la línea de visión, renderizada sobre la retícula de 721 columnas y verificada por el contrato 1 antes de que algo la lea. Un clip que rompe el contrato se rechaza con sus razones, nunca se repara; la profundidad enmascarada se cuenta, nunca se descarta.',
        )}
      </p>
      <div className="cx-table-wrap">
        <table className="cx-table">
          <thead>
            <tr>
              <th>{t('Source', 'Fuente')}</th>
              <th className="num">{t('Clips', 'Clips')}</th>
              <th className="num">{t('Frames', 'Cuadros')}</th>
              <th className="num">{t('Accepted', 'Aceptados')}</th>
              <th className="num">{t('Rejected', 'Rechazados')}</th>
              <th className="num">{t('Masked depth', 'Profundidad enmascarada')}</th>
              <th className="num">{t('Fetched', 'Descargado')}</th>
              <th>{t('License', 'Licencia')}</th>
            </tr>
          </thead>
          <tbody>
            {rendered.map(([name, s]) => (
              <tr key={name}>
                <td>{name}</td>
                <td className="num">{num(s.clips)}</td>
                <td className="num">{num(s.frames)}</td>
                <td className="num">{num(s.accepted)}</td>
                <td className="num">{num(s.rejected + s.failed)}</td>
                <td className="num">{pct(s.depth_masked_share, 2)}</td>
                <td className="num">{gb(s.bytes)}</td>
                <td>{s.license}</td>
              </tr>
            ))}
            <tr>
              <td>MPI Sintel</td>
              <td className="num">{num(sources.sintel.sequences)}</td>
              <td className="num">{num(sources.sintel.frames)}</td>
              <td className="num">
                {t(`${num(sources.sintel.engine_rendering.strips)} strips, by the engine`, `${num(sources.sintel.engine_rendering.strips)} franjas, por el motor`)}
              </td>
              <td className="num">0</td>
              <td className="num">-</td>
              <td className="num">{t("the engine's download", 'descarga del motor')}</td>
              <td>{sources.sintel.license}</td>
            </tr>
            <tr>
              <td>{t('TartanAir panoramas (C13)', 'Panoramas de TartanAir (C13)')}</td>
              <td className="num">{num(sources.panorama.clips)}</td>
              <td className="num">{num(sources.panorama.clips)}</td>
              <td className="num">{num(sources.panorama.clips)}</td>
              <td className="num">0</td>
              <td className="num">-</td>
              <td className="num">{gb(sources.panorama.bytes)}</td>
              <td>{sources.panorama.license}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <h3>{t('What one column sees', 'Lo que ve una columna')}</h3>
      <p>
        {t(
          "Every planar frame goes through the engine's geometry: resized to 436 rows, the lattice on the central 391 x 391 pixels, neighbouring columns 13 pixels apart. What a column subtends then depends on the source's lens, measured at the centre over every frame's own intrinsics:",
          'Cada cuadro plano pasa por la geometría del motor: redimensionado a 436 filas, la retícula sobre los 391 x 391 píxeles centrales, columnas vecinas a 13 píxeles. Lo que abarca una columna depende entonces del lente de la fuente, medido en el centro sobre los intrínsecos propios de cada cuadro:',
        )}
      </p>
      <div className="cx-table-wrap">
        <table className="cx-table">
          <thead>
            <tr>
              <th>{t('Source', 'Fuente')}</th>
              <th className="num">{t('Degrees between neighbouring columns', 'Grados entre columnas vecinas')}</th>
            </tr>
          </thead>
          <tbody>
            <tr><td>{t("MPI Sintel, every training frame (the published model's domain)", 'MPI Sintel, cada cuadro de entrenamiento (el dominio del modelo publicado)')}</td><td className="num">{range(sources.sintel.column_spacing_deg)}</td></tr>
            <tr><td>Spring</td><td className="num">{range(sources.spring.column_spacing_deg)}</td></tr>
            <tr><td>{t('Hypersim, test scenes', 'Hypersim, escenas de prueba')}</td><td className="num">{range(sources.hypersim.column_spacing_deg)}</td></tr>
            <tr><td>{t('TartanAir (and the synthetic cases)', 'TartanAir (y los casos sintéticos)')}</td><td className="num">{range(sources.tartanair.column_spacing_deg)}</td></tr>
            <tr><td>{t("FlyGym, the fly's own compound eye", 'FlyGym, el propio ojo compuesto de la mosca')}</td><td className="num">{range(sources.flygym.column_spacing_deg)}</td></tr>
          </tbody>
        </table>
      </div>
      <InlineSvg src="svg/docs/lattice-geometry.svg" label={t('Degrees between neighbouring columns, per source', 'Grados entre columnas vecinas, por fuente')} />

      <h3>{t('Are the splits free of leakage?', '¿Están las particiones libres de fuga?')}</h3>
      <p>
        {t(
          `TartanAir reuses one geometry under several names, so the split unit is the geometry family: ${num(vision.splits.families)} families, assigned with a fixed seed, the families the cases draw from always in test. The leakage test fails if a family or an environment appears in two splits, or if two identical frames do (${num(vision.splits.leakage.frames_hashed)} frames hashed).`,
          `TartanAir reutiliza una geometría bajo varios nombres, así que la unidad de partición es la familia geométrica: ${num(vision.splits.families)} familias, asignadas con una semilla fija, y las familias de las que toman los casos siempre en prueba. La prueba de fuga falla si una familia o un entorno aparece en dos particiones, o si lo hacen dos cuadros idénticos (${num(vision.splits.leakage.frames_hashed)} cuadros con hash).`,
        )}
      </p>
      <div className="cx-table-wrap">
        <table className="cx-table">
          <thead>
            <tr>
              <th>{t('Split', 'Partición')}</th>
              <th className="num">{t('Families', 'Familias')}</th>
              <th className="num">{t('Environments', 'Entornos')}</th>
              <th className="num">{t('Clips', 'Clips')}</th>
              <th className="num">{t('Frames', 'Cuadros')}</th>
            </tr>
          </thead>
          <tbody>
            {(['train', 'validation', 'calibration', 'test'] as const).map((name) => (
              <tr key={name}>
                <td>{t(splitNames[name][0], splitNames[name][1])}</td>
                <td className="num">{num(vision.splits.counts[name].families)}</td>
                <td className="num">{num(vision.splits.counts[name].environments)}</td>
                <td className="num">{num(vision.splits.counts[name].clips)}</td>
                <td className="num">{num(vision.splits.counts[name].frames)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Callout variant={vision.splits.leakage.problems.length ? 'honest' : 'note'} title={vision.splits.leakage.problems.length ? t('Leakage', 'Fuga') : t('The leakage gate', 'La compuerta de fuga')}>
        {vision.splits.leakage.problems.length
          ? t(`Leakage found: ${vision.splits.leakage.problems.join('; ')}`, `Fuga encontrada: ${vision.splits.leakage.problems.join('; ')}`)
          : t('No leakage: no family, environment or identical frame appears in two splits.', 'Sin fuga: ninguna familia, entorno ni cuadro idéntico aparece en dos particiones.')}
      </Callout>
      <SectionRefs ids={['wang2020', 'butler2012', 'mehl2023', 'roberts2021', 'wangchen2024', 'lappalainen2024']} />
    </section>
  );

  const selected = cases.cases[caseId] ? caseId : 'C01';
  const chosen = cases.cases[selected];
  const measuredKeys = MEASURED[selected] ?? [];
  const casesTab = (
    <section>
      <h2>{t('What did each case level measure?', '¿Qué midió cada nivel de cada caso?')}</h2>
      <p>
        {t(
          `Sixteen cases, each one physical quantity over six levels, each drawing its clips once from test data and rendering the same clips at every level: ${num(vision.cases.accepted)} of ${num(vision.cases.renderings)} renderings accepted by contract 1. Each level records what it means in the image; the table shows the medians over the clips of each level.`,
          `Dieciséis casos, cada uno una cantidad física en seis niveles, cada uno tomando sus clips una vez de datos de prueba y renderizando los mismos clips en cada nivel: ${num(vision.cases.accepted)} de ${num(vision.cases.renderings)} renderizados aceptados por el contrato 1. Cada nivel registra lo que significa en la imagen; la tabla muestra las medianas sobre los clips de cada nivel.`,
        )}
      </p>
      <label className="cx-label" htmlFor="cx-exp-case">{t('Case', 'Caso')}</label>
      <select id="cx-exp-case" className="cx-select cx-select-inline" value={selected} onChange={(e) => setCaseId(e.target.value)}>
        {Object.keys(cases.cases).map((id) => (
          <option key={id} value={id}>{id} {t(CASE_NAMES[id]?.[0] ?? id, CASE_NAMES[id]?.[1] ?? id)}</option>
        ))}
      </select>
      <p>
        <strong>{t(CATEGORIES[chosen.category]?.[0] ?? chosen.category, CATEGORIES[chosen.category]?.[1] ?? chosen.category)}</strong>
        {'. '}
        {t(
          `Source: ${chosen.source}${chosen.family ? ` (${chosen.family})` : ''}. Grades: ${chosen.grades.join(', ')}. Clips drawn: ${chosen.items.length}.`,
          `Fuente: ${chosen.source}${chosen.family ? ` (${chosen.family})` : ''}. Evalúa: ${chosen.grades.join(', ')}. Clips tomados: ${chosen.items.length}.`,
        )}
      </p>
      <div className="cx-table-wrap">
        <table className="cx-table">
          <thead>
            <tr>
              <th>{t(QUANTITIES[selected]?.[0] ?? 'level', QUANTITIES[selected]?.[1] ?? 'nivel')}</th>
              <th className="num">{t('Accepted', 'Aceptados')}</th>
              <th className="num">{t('Frame interval (ms)', 'Intervalo (ms)')}</th>
              {measuredKeys.map(([key, label]) => <th key={key} className="num">{t(label[0], label[1])}</th>)}
              <th className="num">{t('Mean luminance', 'Luminancia media')}</th>
              <th className="num">{t('Median depth', 'Profundidad mediana')}</th>
            </tr>
          </thead>
          <tbody>
            {chosen.levels.map((level, i) => (
              <tr key={i}>
                <td>{levelLabel(selected, level.value, t, num)}</td>
                <td className="num">{num(level.accepted)} / {num(level.clips)}</td>
                <td className="num">{level.interval_s ? num(level.interval_s * 1000, level.interval_s < 0.01 ? 2 : 1) : '-'}</td>
                {measuredKeys.map(([key, , digits]) => {
                  const value = level.measured[key];
                  return <td key={key} className="num">{typeof value === 'number' ? num(value, digits) : '-'}</td>;
                })}
                <td className="num">{typeof level.statistics.lum_mean === 'number' ? num(level.statistics.lum_mean, 3) : '-'}</td>
                <td className="num">{typeof level.statistics.depth_median_m === 'number' ? num(level.statistics.depth_median_m, 2) : '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <SectionRefs ids={['pick2005', 'klapoetke2017', 'keles2017', 'wangchen2024']} />
    </section>
  );

  const { evaluation } = reports;
  const methodNames = Object.keys(evaluation.methods).filter((m) => m !== 'floor');
  const median = (values: number[]) => {
    const kept = values.filter((v) => Number.isFinite(v)).sort((a, b) => a - b);
    return kept.length ? kept[Math.floor(kept.length / 2)] : NaN;
  };
  const caseNumber = (method: string, caseId: string, key: 'abs_rel' | 'coverage' | 'refusal_correct') => {
    const found = evaluation.methods[method]?.cases[caseId];
    if (!found) return NaN;
    return median(found.levels.map((level) => level[key] as number));
  };
  const caseIds = Object.keys(evaluation.methods.floor?.cases ?? {}).sort();
  const methodsTab = (
    <section>
      <h2>{t('What do the first methods get from the eye?', '¿Qué obtienen los primeros métodos del ojo?')}</h2>
      <p>
        {t(
          'Every method is scored on the same clips, which come from geometry families that are always in the test split, and every number below is the median over that case’s six levels. The row called floor is not a method: it is the flow the corpus committed, put through the same readout, so it says what the arithmetic after the flow costs. A method’s distance from it is the part of the error the method owns.',
          'Cada método se evalúa sobre los mismos clips, que provienen de familias de geometría siempre en el conjunto de prueba, y cada número es la mediana sobre los seis niveles del caso. La fila llamada piso no es un método: es el flujo que el corpus comprometió, pasado por la misma lectura, así que dice cuánto cuesta la aritmética posterior al flujo. La distancia de un método a ella es la parte del error que le pertenece.',
        )}
      </p>
      <Callout variant="note" title={t('What each row is', 'Qué es cada fila')}>
        <ul>
          {Object.entries(evaluation.kind).map(([name, kind]) => (
            <li key={name}><strong>{name}</strong>: {kind}</li>
          ))}
        </ul>
      </Callout>
      <div className="cx-table-wrap">
        <table className="cx-table">
          <thead>
            <tr>
              <th>{t('Method', 'Método')}</th>
              <th className="num">{t('Clips scored', 'Clips evaluados')}</th>
              <th className="num">{t('Clips skipped', 'Clips omitidos')}</th>
              <th className="num">{t('AbsRel minus the floor, paired', 'AbsRel menos el piso, pareado')}</th>
              <th className="num">{t('Clips paired', 'Clips pareados')}</th>
            </tr>
          </thead>
          <tbody>
            {methodNames.map((name) => {
              const paired = evaluation.against_floor[name];
              return (
                <tr key={name}>
                  <td>{name}</td>
                  <td className="num">{num(evaluation.methods[name].clips_scored - evaluation.methods[name].clips_skipped)}</td>
                  <td className="num">{num(evaluation.methods[name].clips_skipped)}</td>
                  <td className="num">
                    {paired ? `${num(paired.median, 3)} [${num(paired.low, 3)}, ${num(paired.high, 3)}]` : '-'}
                  </td>
                  <td className="num">{paired ? num(paired.pairs) : '-'}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="cx-muted">
        {t(
          'The interval is a 10,000-resample bootstrap over clips of the paired difference, seed recorded in the report.',
          'El intervalo es un bootstrap de 10.000 remuestreos sobre clips de la diferencia pareada, con la semilla registrada en el reporte.',
        )}
      </p>
      {Object.keys(evaluation.against_nulls ?? {}).length > 0 ? (
        <>
          <h3>{t('A connectome row against its own nulls', 'Una fila del conectoma contra sus propios nulos')}</h3>
          <p>
            {t(
              'The same head, the same seeds and the same clips, on a network whose wiring was degree-preservingly rewired, replaced by a size-matched random sparse graph, or had its signs shuffled. A positive difference means the measured wiring did better than the control; an interval that crosses zero means the measurement does not separate them.',
              'La misma cabeza, las mismas semillas y los mismos clips, sobre una red cuyo cableado fue recableado preservando grados, reemplazado por un grafo disperso aleatorio del mismo tamaño, o con sus signos barajados. Una diferencia positiva significa que el cableado medido superó al control; un intervalo que cruza el cero significa que la medición no los separa.',
            )}
          </p>
          <div className="cx-table-wrap">
            <table className="cx-table">
              <thead>
                <tr>
                  <th>{t('Comparison', 'Comparación')}</th>
                  <th className="num">{t('AbsRel difference, paired', 'Diferencia de AbsRel, pareada')}</th>
                  <th className="num">{t('Clips paired', 'Clips pareados')}</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(evaluation.against_nulls ?? {}).map(([name, paired]) => (
                  <tr key={name}>
                    <td>{name}</td>
                    <td className="num">{num(-paired.median, 3)} [{num(-paired.high, 3)}, {num(-paired.low, 3)}]</td>
                    <td className="num">{num(paired.pairs)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="cx-muted">
            {t(
              'Reported as the null minus the connectome, so a positive number is the connectome being better.',
              'Reportado como el nulo menos el conectoma, así que un número positivo es el conectoma siendo mejor.',
            )}
          </p>
        </>
      ) : null}
      {Object.keys(evaluation.against_regimes ?? {}).length > 0 ? (
        <>
          <h3>{t('What the regime bought', 'Qué compró el régimen')}</h3>
          <p>
            {t(
              'The same wiring, the same head and the same seeds as the row before it, with one more thing allowed to train inside the network. Each arm is compared with its own predecessor, so the difference is what training that quantity bought on that wiring, and a null arm that gains as much as the measured one is saying that the gain is not about the connectome.',
              'El mismo cableado, la misma cabeza y las mismas semillas que la fila anterior, con una cosa más que puede entrenarse dentro de la red. Cada brazo se compara con su propio predecesor, de modo que la diferencia es lo que compró entrenar esa cantidad sobre ese cableado, y un brazo nulo que gana tanto como el medido está diciendo que la ganancia no es del conectoma.',
            )}
          </p>
          <div className="cx-table-wrap">
            <table className="cx-table">
              <thead>
                <tr>
                  <th>{t('Comparison', 'Comparación')}</th>
                  <th className="num">{t('AbsRel difference, paired', 'Diferencia de AbsRel, pareada')}</th>
                  <th className="num">{t('Clips paired', 'Clips pareados')}</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(evaluation.against_regimes ?? {}).map(([name, paired]) => (
                  <tr key={name}>
                    <td>{name}</td>
                    <td className="num">{num(-paired.median, 3)} [{num(-paired.high, 3)}, {num(-paired.low, 3)}]</td>
                    <td className="num">{num(paired.pairs)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="cx-muted">
            {t(
              'Reported as the earlier row minus the later one, so a positive number is the later regime being better.',
              'Reportado como la fila anterior menos la posterior, así que un número positivo es el régimen posterior siendo mejor.',
            )}
          </p>
        </>
      ) : null}
      <h3>{t('Per case: AbsRel, median over the six levels', 'Por caso: AbsRel, mediana sobre los seis niveles')}</h3>
      <div className="cx-table-wrap">
        <table className="cx-table">
          <thead>
            <tr>
              <th>{t('Case', 'Caso')}</th>
              <th>{t('What it varies', 'Qué varía')}</th>
              {['floor', ...methodNames].map((name) => <th key={name} className="num">{name}</th>)}
            </tr>
          </thead>
          <tbody>
            {caseIds.map((caseId) => {
              const info = evaluation.methods.floor.cases[caseId];
              return (
                <tr key={caseId}>
                  <td>{caseId} {info.name}</td>
                  <td className="cx-muted">{info.quantity} ({info.unit})</td>
                  {['floor', ...methodNames].map((name) => {
                    const present = evaluation.methods[name]?.cases[caseId];
                    if (!present || present.levels.every((level) => level.skipped)) {
                      return <td key={name} className="num cx-muted">-</td>;
                    }
                    if (!info.observable) {
                      const refused = caseNumber(name, caseId, 'refusal_correct');
                      return <td key={name} className="num">{Number.isFinite(refused) ? t(`refused ${pct(refused, 0)}`, `rechazó ${pct(refused, 0)}`) : '-'}</td>;
                    }
                    const value = caseNumber(name, caseId, 'abs_rel');
                    return <td key={name} className="num">{Number.isFinite(value) ? num(value, 3) : '-'}</td>;
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="cx-muted">
        {t(
          'A dash is a case the method cannot be run on, and the report says why for each: a source with no second camera, a clip with no flow, a clip with no camera motion, or a case variant that cannot be reproduced on the second camera. The two negative controls are graded by what was refused, not by an error.',
          'Un guion es un caso en el que el método no puede correr, y el reporte dice por qué en cada uno: una fuente sin segunda cámara, un clip sin flujo, un clip sin movimiento de cámara, o una variante que no puede reproducirse en la segunda cámara. Los dos controles negativos se califican por lo rechazado, no por un error.',
        )}
      </p>
      <SectionRefs ids={['lappalainen2024', 'pick2005']} />
    </section>
  );

  return (
    <div className="page-body wide prose">
      {head}
      <SubTabs
        orientation="vertical"
        ariaLabel={t('Experiments', 'Experimentos')}
        tabs={[
          { id: 'holdout', label: t('Column holdout', 'Exclusión de columnas'), content: holdout },
          { id: 'consensus', label: t('Published consensus', 'Consenso publicado'), content: consensus },
          { id: 'orientation', label: t('Orientation', 'Orientación'), content: orientation },
          { id: 'parity', label: t('Parity', 'Paridad'), content: parityTab },
          { id: 'ensemble', label: t('Published ensemble', 'Ensamble publicado'), content: ensemble },
          { id: 'lattice', label: t('Frozen lattice', 'Retícula congelada'), content: frozen },
          { id: 'visual-cns', label: t('Whole visual system', 'Sistema visual completo'), content: whole },
          { id: 'vision-data', label: t('Vision data', 'Datos de visión'), content: visionTab },
          { id: 'cases', label: t('Cases', 'Casos'), content: casesTab },
          { id: 'methods', label: t('Methods', 'Métodos'), content: methodsTab },
        ]}
      />
    </div>
  );
}
