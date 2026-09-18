import { Callout, Equation, Tabs } from '@fasl-work/caos-app-shell';
import SectionRefs from '../components/SectionRefs';
import { useNumber, useT } from '../lib/i18n';
import { useReports } from '../lib/reports';

export default function Benchmark() {
  const t = useT();
  const num = useNumber();
  const { reports, error } = useReports();

  const head = (
    <div className="page-head">
      <h1>{t('Benchmark', 'Benchmark')}</h1>
      <p className="lede">
        {t(
          'The benchmark crosses every method with every case and every metric. No vision method has been evaluated yet: the first rows arrive with the classical and untrained biological methods. What is measured today is the network itself: how faithful the build is to the release and to the published model, how the frozen networks behave, and what they cost to run and to train.',
          'El benchmark cruza cada método con cada caso y cada métrica. Ningún método de visión ha sido evaluado todavía: las primeras filas llegan con los métodos clásicos y los biológicos sin entrenar. Lo que se mide hoy es la red misma: qué tan fiel es la construcción a la liberación y al modelo publicado, cómo se comportan las redes congeladas, y cuánto cuesta simularlas y entrenarlas.',
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
  const hold = build.column_inference.holdout.summary;
  const worstParity = Math.max(...parity.voltage_parity.map((r) => r.max_abs_difference));
  const comparedParity = parity.voltage_parity.reduce((sum, r) => sum + r.values_compared, 0);
  const publishedCells = parity.voltage_parity[0].cells;
  const vcns = visualCns.frozen.default;

  const fidelity = (
    <section>
      <h2>{t('Fidelity of the build', 'Fidelidad de la construcción')}</h2>
      <p>
        {t(
          'One row per check, each read from the report of the experiment that measured it. The protocols are on the Experiments page.',
          'Una fila por verificación, cada una leída del reporte del experimento que la midió. Los protocolos están en la página de Experimentos.',
        )}
      </p>
      <div className="cx-table-wrap">
        <table className="cx-table">
          <thead><tr><th>{t('Check', 'Verificación')}</th><th className="num">{t('Measured', 'Medido')}</th></tr></thead>
          <tbody>
            <tr><td>{t('Held-out annotated types whose columns are recovered', 'Tipos anotados excluidos cuyas columnas se recuperan')}</td><td className="num">{hold.types_recovered} / {hold.types_tested}</td></tr>
            <tr><td>{t('Median held-out type, exact column', 'Tipo excluido mediano, columna exacta')}</td><td className="num">{pct(hold.median_exact_fraction, 2)}</td></tr>
            <tr><td>{t('Worst 95th percentile column error', 'Peor error de columna percentil 95')}</td><td className="num">{num(hold.worst_p95_error_columns, 0)}</td></tr>
            <tr><td>{t('Left optic lobe, median held-out type exact', 'Lóbulo óptico izquierdo, tipo excluido mediano exacto')}</td><td className="num">{pct(visualCnsSummary.columns.L.holdout.median_exact_fraction, 2)}</td></tr>
            <tr><td>{t('Published consensus connections recovered', 'Conexiones del consenso publicado recuperadas')}</td><td className="num">{pct(comparison.connections.recovered_fraction)}</td></tr>
            <tr><td>{t('Sign agreement with the consensus', 'Acuerdo de signo con el consenso')}</td><td className="num">{pct(comparison.signs.agreement_fraction)}</td></tr>
            <tr><td>{t('Rank correlation of central synapse counts', 'Correlación de rangos de conteos centrales')}</td><td className="num">{num(comparison.central_synapse_counts.spearman, 2)}</td></tr>
            <tr><td>{t('Best lattice symmetry for filter directions', 'Mejor simetría de retícula para las direcciones de filtro')}</td><td className="num">{comparison.orientation.best}</td></tr>
            <tr><td>{t('Largest voltage difference against the published model', 'Mayor diferencia de voltaje contra el modelo publicado')}</td><td className="num">{worstParity.toExponential(1)} ({t('over', 'sobre')} {num(comparedParity)} {t('values', 'valores')})</td></tr>
            <tr><td>{t('Largest tuning difference against the engine’s own pipeline', 'Mayor diferencia de ajuste contra el pipeline propio del motor')}</td><td className="num">{num(parity.pipeline_crosscheck.largest_dsi_difference, 4)}</td></tr>
          </tbody>
        </table>
      </div>
      <SectionRefs ids={['nern2025', 'lappalainen2024', 'flyvis']} />
    </section>
  );

  const networks = (
    <section>
      <h2>{t('The networks and what they cost', 'Las redes y lo que cuestan')}</h2>
      <p>
        {t(
          `Every cost is measured on ${lattice.device}: the time and peak memory of one training step through the engine, and simulated seconds per wall-clock second for one sample running forward. The sizes are what the compiler produced, cells and connections as simulated.`,
          `Cada costo se mide en ${lattice.device}: el tiempo y la memoria máxima de un paso de entrenamiento a través del motor, y segundos simulados por segundo de reloj para una muestra corriendo hacia adelante. Los tamaños son los que produjo el compilador, células y conexiones tal como se simulan.`,
        )}
      </p>
      <div className="cx-table-wrap">
        <table className="cx-table">
          <thead>
            <tr>
              <th>{t('Network', 'Red')}</th>
              <th className="num">{t('Cells', 'Células')}</th>
              <th className="num">{t('Connections', 'Conexiones')}</th>
              <th className="num">{t('Trainable, R1', 'Entrenables, R1')}</th>
              <th className="num">{t('Seconds per R1 step', 'Segundos por paso R1')}</th>
              <th className="num">{t('Peak memory (GB)', 'Memoria máxima (GB)')}</th>
              <th className="num">{t('Simulated s per s', 's simulados por s')}</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>{t('Published network', 'Red publicada')}</td>
              <td className="num">{num(publishedCells)}</td>
              <td className="num">-</td>
              <td className="num">{num(lattice.training_step.published_R1.trainable)}</td>
              <td className="num">{num(lattice.training_step.published_R1.seconds_per_step, 3)}</td>
              <td className="num">{num(lattice.training_step.published_R1.peak_memory_gb, 2)}</td>
              <td className="num">-</td>
            </tr>
            <tr>
              <td>{t('MaleCNS lattice, right optic lobe', 'Retícula MaleCNS, lóbulo óptico derecho')}</td>
              <td className="num">{num(lattice.frozen.default.compile.nodes)}</td>
              <td className="num">{num(lattice.frozen.default.compile.edges)}</td>
              <td className="num">{num(lattice.training_step.R1.trainable)}</td>
              <td className="num">{num(lattice.training_step.R1.seconds_per_step, 3)}</td>
              <td className="num">{num(lattice.training_step.R1.peak_memory_gb, 2)}</td>
              <td className="num">{num(lattice.frozen.default.simulation.simulated_seconds_per_wall_second_per_sample, 2)}</td>
            </tr>
            <tr>
              <td>{t('Whole visual system, neuron by neuron', 'Sistema visual completo, neurona por neurona')}</td>
              <td className="num">{num(vcns.compile.nodes)}</td>
              <td className="num">{num(vcns.compile.edges)}</td>
              <td className="num">{num(visualCns.training_step_R1.trainable)}</td>
              <td className="num">{num(visualCns.training_step_R1.seconds_per_step, 3)}</td>
              <td className="num">{num(visualCns.training_step_R1.peak_memory_gb, 2)}</td>
              <td className="num">{num(vcns.simulation.simulated_seconds_per_wall_second_per_sample, 2)}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p>
        {t(
          `The training steps run at batch ${lattice.training_step.R1.batch_size} for the lattices and ${visualCns.training_step_R1.batch_size} for the whole visual system, over ${lattice.training_step.R1.frames} frames. Per-connection training of the lattice (R2, ${num(lattice.training_step.R2.trainable)} trainable values) takes ${num(lattice.training_step.R2.seconds_per_step, 3)} s per step, about the same as R1: the cost is the simulation, not the number of trained values.`,
          `Los pasos de entrenamiento corren con lote ${lattice.training_step.R1.batch_size} para las retículas y ${visualCns.training_step_R1.batch_size} para el sistema visual completo, sobre ${lattice.training_step.R1.frames} cuadros. El entrenamiento por conexión de la retícula (R2, ${num(lattice.training_step.R2.trainable)} valores entrenables) toma ${num(lattice.training_step.R2.seconds_per_step, 3)} s por paso, casi lo mismo que R1: el costo es la simulación, no el número de valores entrenados.`,
        )}
      </p>
      <SectionRefs ids={['lappalainen2024', 'berg2026']} />
    </section>
  );

  const controlRows = Object.entries(lattice.controls);
  const controls = (
    <section>
      <h2>{t('The controls', 'Los controles')}</h2>
      <p>
        {t(
          'Every connectome result is set against three size-matched controls, five seeds each: N1 rewires the connections while preserving every cell type’s in- and out-degree, N2 draws connections at random with the same counts, N3 shuffles the signs. On the task benchmark they appear as rows of their own, so an effect can be credited to the measured wiring only when it exceeds all three.',
          'Cada resultado del conectoma se contrasta con tres controles igualados en tamaño, cinco semillas cada uno: N1 recablea las conexiones preservando el grado de entrada y salida de cada tipo celular, N2 sortea conexiones al azar con los mismos conteos, N3 permuta los signos. En el benchmark de tareas aparecen como filas propias, así que un efecto puede atribuirse al cableado medido solo cuando supera a los tres.',
        )}
      </p>
      <div className="cx-table-wrap">
        <table className="cx-table">
          <thead><tr><th>{t('Frozen lattice', 'Retícula congelada')}</th><th className="num">{t('Seeds settled', 'Semillas estables')}</th><th className="num">{t('Voltage range', 'Rango de voltaje')}</th><th className="num">{t('Largest median DSI, T4 and T5', 'Mayor DSI mediano, T4 y T5')}</th></tr></thead>
          <tbody>
            {(['default', 'transfer'] as const).map((init) => (
              <tr key={init}>
                <td>{init === 'default' ? t('measured wiring, engine initialisation', 'cableado medido, inicialización del motor') : t('measured wiring, published values', 'cableado medido, valores publicados')}</td>
                <td className="num">{lattice.frozen[init].settled ? '1 / 1' : '0 / 1'}</td>
                <td className="num">{num(lattice.frozen[init].stability.min, 2)} {t('to', 'a')} {num(lattice.frozen[init].stability.max, 2)}</td>
                <td className="num">{num(Math.max(...Object.values(lattice.frozen[init].tuning_summary).map((r) => r.median_dsi)), 3)}</td>
              </tr>
            ))}
            {controlRows.map(([kind, row]) => (
              <tr key={kind}>
                <td>{kind}</td>
                <td className="num">{row.settled.filter(Boolean).length} / {row.seeds.length}</td>
                <td className="num">{num(Math.min(...row.stability.map((s) => s.min)), 2)} {t('to', 'a')} {num(Math.max(...row.stability.map((s) => s.max)), 2)}</td>
                <td className="num">{num(Math.max(...Object.values(row.tuning_summary).map((r) => r.median_dsi)), 3)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Callout variant="honest" title={t('No separation before training', 'Sin separación antes del entrenamiento')}>
        {t(
          'Frozen and untrained, the measured wiring and its controls are all stable and all untuned to motion direction. Nothing here favours the connectome yet; the comparison that can is on the task, after training.',
          'Congelados y sin entrenar, el cableado medido y sus controles son todos estables y todos sin ajuste a la dirección del movimiento. Nada aquí favorece todavía al conectoma; la comparación que puede hacerlo es en la tarea, después del entrenamiento.',
        )}
      </Callout>
      <SectionRefs ids={['wang2026', 'lukosevicius2009']} />
    </section>
  );

  const protocol = (
    <section>
      <h2>{t('The task benchmark protocol', 'El protocolo del benchmark de tareas')}</h2>
      <Callout variant="note" title={t('Not run yet', 'Aún no corrido')}>
        {t(
          'This tab states how the task matrix will be measured. It holds no result: each row fills when its method ships, and the page never shows a number that was not produced by a committed run.',
          'Esta pestaña establece cómo se medirá la matriz de tareas. No contiene resultados: cada fila se llena cuando su método se entrega, y la página nunca muestra un número que no haya producido una corrida versionada.',
        )}
      </Callout>
      <h3>{t('Depth', 'Profundidad')}</h3>
      <p>
        {t(
          'Over the N valid pixels with true depth d and predicted depth d̂:',
          'Sobre los N píxeles válidos con profundidad real d y profundidad predicha d̂:',
        )}
      </p>
      <Equation
        tex="\mathrm{AbsRel} = \frac{1}{N}\sum_i \frac{|d_i-\hat d_i|}{d_i},\qquad \mathrm{RMSE} = \sqrt{\frac{1}{N}\sum_i (d_i-\hat d_i)^2}"
        caption={t('RMSE is in metres and is reported only for methods that predict metric depth.', 'El RMSE está en metros y se informa solo para métodos que predicen profundidad métrica.')}
      />
      <Equation
        tex="\delta_k = \frac{1}{N}\,\Big|\Big\{\, i : \max\!\Big(\frac{d_i}{\hat d_i}, \frac{\hat d_i}{d_i}\Big) < 1.25^k \Big\}\Big|,\quad k = 1, 2, 3"
        caption={t('The share of pixels within a ratio threshold.', 'La fracción de píxeles dentro de un umbral de razón.')}
      />
      <Equation
        tex="\mathrm{SILog} = \frac{1}{N}\sum_i g_i^2 - \frac{1}{N^2}\Big(\sum_i g_i\Big)^2,\qquad g_i = \log \hat d_i - \log d_i"
        caption={t('The scale-invariant error: it ignores a global scale and measures depth relations.', 'El error invariante a la escala: ignora una escala global y mide relaciones de profundidad.')}
      />
      <p>
        {t(
          'Methods that predict relative depth are aligned by least squares in scale and shift, in disparity space, before they are scored, and that alignment is named next to their numbers; relative and metric results never share a column. On cases where depth cannot be observed, the score is the calibration of the predicted uncertainty, not AbsRel.',
          'Los métodos que predicen profundidad relativa se alinean por mínimos cuadrados en escala y desplazamiento, en el espacio de disparidad, antes de puntuarse, y esa alineación se nombra junto a sus números; resultados relativos y métricos nunca comparten una columna. En los casos donde la profundidad no puede observarse, la puntuación es la calibración de la incertidumbre predicha, no AbsRel.',
        )}
      </p>
      <h3>{t('Segmentation', 'Segmentación')}</h3>
      <Equation
        tex="\mathrm{IoU}_c = \frac{|P_c \cap G_c|}{|P_c \cup G_c|},\qquad \mathrm{mIoU} = \frac{1}{C}\sum_{c=1}^{C} \mathrm{IoU}_c"
        caption={t('Per-class intersection over union, averaged over a documented reduced label set.', 'Intersección sobre unión por clase, promediada sobre un conjunto reducido de etiquetas documentado.')}
      />
      <p>
        {t(
          'Next to mIoU: the boundary F-score, the harmonic mean of boundary precision and recall within a pixel tolerance, and the figure-ground IoU for class-agnostic segmentation by motion, object against background.',
          'Junto a mIoU: el puntaje F de borde, la media armónica de precisión y exhaustividad de bordes dentro de una tolerancia en píxeles, y el IoU figura-fondo para la segmentación por movimiento sin clases, objeto contra fondo.',
        )}
      </p>
      <h3>{t('Speed and biology', 'Velocidad y biología')}</h3>
      <p>
        {t(
          'Fast is a measurement: trainable and total parameters (the connectome’s fixed values counted apart), latency per frame at a fixed resolution on the laptop GPU, on the CPU and in the browser, peak memory, and simulated steps per frame for recurrent models. After task training, the T4 and T5 direction selectivity is measured again with the same moving edges; if training destroys the biological tuning, this page reports it.',
          'Rápido es una medición: parámetros entrenables y totales (los valores fijos del conectoma contados aparte), latencia por cuadro a una resolución fija en la GPU del portátil, en la CPU y en el navegador, memoria máxima, y pasos simulados por cuadro para modelos recurrentes. Después del entrenamiento en la tarea, la selectividad a la dirección de T4 y T5 se mide otra vez con los mismos bordes en movimiento; si el entrenamiento destruye el ajuste biológico, esta página lo informa.',
        )}
      </p>
      <h3>{t('Fairness', 'Equidad')}</h3>
      <p>
        {t(
          'Every frozen backbone gets the same decoder head family, the same training budget and the same input resolution. Learned methods train with at least three seeds, the connectome regimes and controls with five, so each comparison is an effect size with an interval rather than a single run. When the arms differ in any protocol detail, the difference is stated, and the worse arm is reported.',
          'Cada backbone congelado recibe la misma familia de cabezal decodificador, el mismo presupuesto de entrenamiento y la misma resolución de entrada. Los métodos aprendidos entrenan con al menos tres semillas, los regímenes del conectoma y los controles con cinco, así que cada comparación es un tamaño de efecto con un intervalo y no una corrida única. Cuando los brazos difieren en algún detalle del protocolo, la diferencia se declara, y se informa el brazo peor.',
        )}
      </p>
      <SectionRefs ids={['eigen2014', 'lappalainen2024']} />
    </section>
  );

  return (
    <div className="page-body wide prose">
      {head}
      <Tabs
        ariaLabel={t('Benchmark', 'Benchmark')}
        tabs={[
          { id: 'fidelity', label: t('Fidelity', 'Fidelidad'), content: fidelity },
          { id: 'networks', label: t('Networks and cost', 'Redes y costo'), content: networks },
          { id: 'controls', label: t('Controls', 'Controles'), content: controls },
          { id: 'protocol', label: t('Task protocol', 'Protocolo de tareas'), content: protocol },
        ]}
      />
    </div>
  );
}
