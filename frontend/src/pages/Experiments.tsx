import { Callout, Equation, SubTabs } from '@fasl-work/caos-app-shell';
import SectionRefs from '../components/SectionRefs';
import { useNumber, useT } from '../lib/i18n';
import { useReports } from '../lib/reports';

const MOTION = ['T4a', 'T4b', 'T4c', 'T4d', 'T5a', 'T5b', 'T5c', 'T5d'];

export default function Experiments() {
  const t = useT();
  const num = useNumber();
  const { reports, error } = useReports();

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
        ]}
      />
    </div>
  );
}
