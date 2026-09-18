import { Callout, Equation, InlineMath, Tabs } from '@fasl-work/caos-app-shell';
import SectionRefs from '../components/SectionRefs';
import InlineSvg from '../components/InlineSvg';
import { useT } from '../lib/i18n';

export default function Methodology() {
  const t = useT();

  const construction = (
    <section>
      <h2>{t('Building the consensus connectome', 'Construir el conectoma de consenso')}</h2>
      <p>
        {t(
          'The build starts from three tables of the release: the body annotations (type, class, superclass, side), the neurotransmitter predictions, and the connection weights (151,856,684 ordered pairs of neurons with their synapse counts). It keeps the neurons of the optic-lobe superclasses on one side, resolves the side of the photoreceptors from their instance names because the release leaves their soma side empty, and scans the whole connection table once, in batches, keeping the 4.6 million pairs whose two ends are both selected.',
          'La construcción parte de tres tablas de la liberación: las anotaciones de cuerpos (tipo, clase, superclase, lado), las predicciones de neurotransmisor y los pesos de conexión (151.856.684 pares ordenados de neuronas con sus conteos de sinapsis). Conserva las neuronas de las superclases del lóbulo óptico de un lado, resuelve el lado de los fotorreceptores desde sus nombres de instancia porque la liberación deja vacío su lado de soma, y recorre toda la tabla de conexiones una vez, por lotes, conservando los 4,6 millones de pares cuyos dos extremos están seleccionados.',
        )}
      </p>
      <p>
        {t(
          'Two kinds of release type are changed before anything else. The inner photoreceptors are pooled across their spectral subtypes into R7 and R8, because no subtype tiles the eye on its own while an input of the network must, and the input is luminance, not colour. Placeholder types that the release could not call ("R7R8_unclear", "T4_unclear" and similar) are left out and counted, because as types of their own they would be network populations that do not exist.',
          'Dos clases de tipo de la liberación se modifican antes que nada. Los fotorreceptores internos se agrupan a través de sus subtipos espectrales en R7 y R8, porque ningún subtipo cubre el ojo por sí solo mientras que una entrada de la red debe hacerlo, y la entrada es luminancia, no color. Los tipos provisorios que la liberación no pudo clasificar ("R7R8_unclear", "T4_unclear" y similares) se excluyen y se cuentan, porque como tipos propios serían poblaciones de la red que no existen.',
        )}
      </p>
      <Equation
        tex="F_{t_i t_j}(\Delta u, \Delta v) = \frac{1}{|t_i|}\sum_{i \in t_i}\ \sum_{j \in t_j,\ c(i) - c(j) = (\Delta u, \Delta v)} N_{ij}"
        caption={t(
          'The average filter: for every ordered pair of types and column offset, the synapses of all contributing pairs, divided by the number of placed cells of the target type. c(i) is the column of cell i.',
          'El filtro medio: para cada par ordenado de tipos y desplazamiento de columna, las sinapsis de todos los pares que contribuyen, divididas por el número de células ubicadas del tipo destino. c(i) es la columna de la célula i.',
        )}
      />
      <p>
        {t(
          'Two thresholds keep noise out of the architecture: an entry must average at least half a synapse per target cell, and it must be supported by at least one connected pair of cells per fifty target cells. The support, averaged over a connection’s entries, is recorded with the connection in the field the engine reads as its certainty, so a filter seen across the whole eye is not presented like one seen twice; the engine stores it and does not use it in the dynamics. The values were chosen by a sweep against the published consensus, not by taste.',
          'Dos umbrales mantienen el ruido fuera de la arquitectura: una entrada debe promediar al menos media sinapsis por célula destino, y debe estar respaldada por al menos un par de células conectadas por cada cincuenta células destino. El respaldo, promediado sobre las entradas de una conexión, se registra con la conexión en el campo que el motor lee como su certeza, para que un filtro visto en todo el ojo no se presente como uno visto dos veces; el motor lo almacena y no lo usa en la dinámica. Los valores se eligieron con un barrido contra el consenso publicado, no por gusto.',
        )}
      </p>
      <Equation
        tex="\lambda_{t_i t_j}(\Delta u, \Delta v) = \frac{1}{|t_i|}\,\#\big\{(i,j):\ i \in t_i,\ j \in t_j,\ c(i) - c(j) = (\Delta u, \Delta v),\ N_{ij} > 0\big\}"
        caption={t(
          'The support of a filter entry: connected pairs of cells at that offset per placed target cell. With at most one source cell per column it is the share of target cells that receive from that offset; where two source cells share a column it exceeds 1.',
          'El respaldo de una entrada de filtro: pares de células conectadas en ese desplazamiento por célula destino ubicada. Con a lo más una célula fuente por columna es la proporción de células destino que reciben desde ese desplazamiento; donde dos células fuente comparten una columna supera 1.',
        )}
      />
      <p>
        {t(
          'The sign of a connection is the sign of its presynaptic type: the majority sign of the type’s neurons, each from its own transmitter prediction (acetylcholine excitatory; glutamate, GABA and histamine inhibitory). Where the neurons of a type disagree, the minority fraction is recorded, because disagreement inside a type is evidence about the predictions rather than about the biology.',
          'El signo de una conexión es el signo de su tipo presináptico: el signo mayoritario de las neuronas del tipo, cada una desde su propia predicción de transmisor (acetilcolina excitatoria; glutamato, GABA e histamina inhibitorios). Donde las neuronas de un tipo discrepan, se registra la fracción minoritaria, porque el desacuerdo dentro de un tipo es evidencia sobre las predicciones y no sobre la biología.',
        )}
      </p>
      <Callout variant="honest" title={t('What is measured and what is predicted', 'Qué se mide y qué se predice')}>
        {t(
          'The synapse counts are measured from electron microscopy; the signs are predictions of a classifier with a known error rate, and treating the modulatory amines as excitatory currents is a modelling choice. The sign-shuffled control exists to measure how much any result depends on them.',
          'Los conteos de sinapsis se miden desde microscopía electrónica; los signos son predicciones de un clasificador con una tasa de error conocida, y tratar las aminas moduladoras como corrientes excitatorias es una decisión de modelado. El control de signos permutados existe para medir cuánto depende de ellos cualquier resultado.',
        )}
      </Callout>
      <SectionRefs ids={['berg2026', 'eckstein2024', 'lappalainen2024']} />
    </section>
  );

  const columns = (
    <section>
      <h2>{t('Retinotopic columns, inferred and measured', 'Columnas retinotópicas, inferidas y medidas')}</h2>
      <p>
        {t(
          'A filter is defined by the offset between the column of a source and the column of its target, so every columnar neuron needs a column. The release annotates columns for the classic lamina and medulla set only, 15 cell types: L1 to L5, C2, C3, T1, Mi1, Mi4, Mi9, Tm1, Tm2, Tm4 and Tm20. The direction-selective T4 and T5 populations, the Dm and Pm families and most of the lobula carry none.',
          'Un filtro se define por el desplazamiento entre la columna de una fuente y la columna de su destino, así que cada neurona columnar necesita una columna. La liberación anota columnas solo para el conjunto clásico de lámina y médula, 15 tipos celulares: L1 a L5, C2, C3, T1, Mi1, Mi4, Mi9, Tm1, Tm2, Tm4 y Tm20. Las poblaciones selectivas a la dirección T4 y T5, las familias Dm y Pm y la mayor parte de la lóbula no llevan ninguna.',
        )}
      </p>
      <p>
        {t(
          'A neuron sits in the column its partners sit in. The column of an unannotated neuron is the synapse-weighted median of the columns of its already-placed partners, computed on compressed sparse arrays and repeated for four rounds so a neuron two steps from the annotated set can still be placed. A median, not a mean: an arbor that reaches a few distant columns must not drag the centre, and the result has to be a lattice position. A neuron is placed only when at least three of its partners are.',
          'Una neurona se ubica en la columna donde están sus socios. La columna de una neurona no anotada es la mediana ponderada por sinapsis de las columnas de sus socios ya ubicados, calculada sobre arreglos dispersos comprimidos y repetida durante cuatro rondas para que una neurona a dos pasos del conjunto anotado pueda ubicarse. Una mediana, no una media: una arborización que alcanza unas pocas columnas lejanas no debe arrastrar el centro, y el resultado tiene que ser una posición de la retícula. Una neurona se ubica solo cuando al menos tres de sus socios lo están.',
        )}
      </p>
      <Equation
        tex="\hat c(i) = \operatorname{median}_{w}\big\{\, c(j) : j \in \mathcal{N}(i),\ c(j)\ \text{placed} \,\big\},\qquad w_j = N_{ij} + N_{ji}"
        caption={t(
          'Column inference: the weighted median, coordinate by coordinate, of the placed partners’ columns, weighted by the synapses in both directions.',
          'Inferencia de columnas: la mediana ponderada, coordenada por coordenada, de las columnas de los socios ubicados, ponderada por las sinapsis en ambas direcciones.',
        )}
      />
      <p>
        {t(
          'The method is measured rather than asserted. Each annotated type is held out in turn, re-inferred from the other annotated types, and compared with its annotation using the hexagonal lattice distance. On the right optic lobe the median held-out type recovers 99.89 percent of its neurons in their exact annotated column and all of them within one column, and the worst 95th percentile error of any type is two columns. The left optic lobe, measured the same way for the whole-visual-system network, gives a median of 99.83 percent.',
          'El método se mide en vez de afirmarse. Cada tipo anotado se excluye por turno, se reinfiere desde los otros tipos anotados y se compara con su anotación usando la distancia de la retícula hexagonal. En el lóbulo óptico derecho el tipo excluido mediano recupera 99,89 por ciento de sus neuronas en su columna anotada exacta y todas dentro de una columna, y el peor percentil 95 de error de cualquier tipo es de dos columnas. El lóbulo óptico izquierdo, medido igual para la red del sistema visual completo, da una mediana de 99,83 por ciento.',
        )}
      </p>
      <Equation
        tex="d_{\mathrm{hex}}\big((u_1, v_1), (u_2, v_2)\big) = \max\big(|\Delta u|,\ |\Delta v|,\ |\Delta u + \Delta v|\big)"
        caption={t(
          'The distance on the hexagonal lattice in axial coordinates, the error unit of the holdout.',
          'La distancia en la retícula hexagonal en coordenadas axiales, la unidad de error de la exclusión.',
        )}
      />
      <Callout variant="honest" title={t('Where the check cannot reach', 'Dónde no llega la verificación')}>
        {t(
          'The holdout can only test types that are annotated, which are compact columnar types. Wide-arbor types are placed by the same rule but their error is not measured; a geometric cross-check from synapse positions is recorded as a follow-up.',
          'La exclusión solo puede probar tipos anotados, que son tipos columnares compactos. Los tipos de arborización amplia se ubican con la misma regla pero su error no se mide; una verificación geométrica desde las posiciones de sinapsis queda registrada como pendiente.',
        )}
      </Callout>
      <SectionRefs ids={['nern2025', 'berg2026']} />
    </section>
  );

  const placement = (
    <section>
      <h2>{t('Placement and expansion on the lattice', 'Ubicación y expansión en la retícula')}</h2>
      <p>
        {t(
          'A cell type is laid out on the network’s lattice at the density it has in the eye: on every column, or on every k-th column along both axes, with k the closest match to the measured cells per column. The right medulla has 893 columns. Types denser than 0.44 cells per column sit on every column (44 types), then on 2x2, 3x3 and 4x4 sublattices (27, 31 and 22 types), and a type sparser than one cell per twenty columns becomes one population node (129 types).',
          'Un tipo celular se dispone en la retícula de la red a la densidad que tiene en el ojo: en cada columna, o cada k columnas en ambos ejes, con k la mejor coincidencia con las células medidas por columna. La médula derecha tiene 893 columnas. Los tipos más densos que 0,44 células por columna van en cada columna (44 tipos), luego en subretículas de 2x2, 3x3 y 4x4 (27, 31 y 22 tipos), y un tipo más escaso que una célula cada veinte columnas se vuelve un nodo de población (129 tipos).',
        )}
      </p>
      <Equation
        tex="k(t) = \min\!\Big(4,\ \max\!\big(1,\ \operatorname{round}\big(1/\sqrt{\rho_t}\,\big)\big)\Big),\qquad \rho_t = \frac{\text{placed cells of } t}{\text{columns}}"
        caption={t(
          'The stride of a type from its measured density; below a density of 1/4.5 squared, about 0.049, the type is one population node instead.',
          'El paso de un tipo según su densidad medida; bajo una densidad de 1/4,5 al cuadrado, cerca de 0,049, el tipo es en cambio un nodo de población.',
        )}
      />
      <p>
        {t(
          'The published engine expands each filter from its sources: every source cell sends each entry to the column at its offset, if a target cell is there. That is exact when every type is on every column, and it loses entries between sublattices, because two sublattices that share the origin only meet at offsets that are multiples of both strides. This product expands every filter from its targets instead: every target cell receives every entry of its measured filter, from the nearest source cell of the source’s sublattice, and entries that land on the same source are summed.',
          'El motor publicado expande cada filtro desde sus fuentes: cada célula fuente envía cada entrada a la columna en su desplazamiento, si hay allí una célula destino. Eso es exacto cuando cada tipo está en cada columna, y pierde entradas entre subretículas, porque dos subretículas que comparten el origen solo coinciden en desplazamientos múltiplos de ambos pasos. Este producto expande cada filtro desde sus destinos: cada célula destino recibe cada entrada de su filtro medido, desde la célula fuente más cercana de la subretícula de la fuente, y las entradas que caen en la misma fuente se suman.',
        )}
      </p>
      <InlineSvg src="svg/docs/filter-expansion.svg" label={t('How a filter reaches its targets on sublattices', 'Cómo un filtro alcanza a sus destinos en subretículas')} />
      <Equation
        tex="N_{ij} = \sum_{(\Delta u, \Delta v)\,:\,\operatorname{snap}_{\mathcal{S}_{t_j}}(u_i - \Delta u,\ v_i - \Delta v) = (u_j, v_j)} F_{t_i t_j}(\Delta u, \Delta v)"
        caption={t(
          'Target-centric expansion: the synapses from source cell j onto target cell i are the filter entries whose source position snaps to j; summed over j they give each target its full filter.',
          'Expansión centrada en el destino: las sinapsis desde la célula fuente j sobre la célula destino i son las entradas del filtro cuya posición de fuente se ajusta a j; sumadas sobre j dan a cada destino su filtro completo.',
        )}
      />
      <p>
        {t(
          'A population node stands for the mean activity of its cells. It receives through its filter like a cell at the centre, and it drives every cell of each target type with the measured average synapses per target cell over the whole pair, counted over every selected neuron regardless of column or distance, because a windowed filter would understate exactly these wide-field types. Checked on the right optic lobe, every target cell of 2,873 connections receives its filter total to float32 precision.',
          'Un nodo de población representa la actividad media de sus células. Recibe a través de su filtro como una célula en el centro, y excita o inhibe a cada célula de cada tipo destino con el promedio medido de sinapsis por célula destino sobre todo el par, contado sobre cada neurona seleccionada sin importar columna ni distancia, porque un filtro con ventana subestimaría justamente a estos tipos de campo amplio. Verificado en el lóbulo óptico derecho, cada célula destino de 2.873 conexiones recibe el total de su filtro con precisión float32.',
        )}
      </p>
      <Callout variant="honest" title={t('An approximation, stated where it is made', 'Una aproximación, declarada donde se hace')}>
        {t(
          'A sublattice cell stands for the cells of its type around it, and a population node for all of its cells. Both are approximations of a real eye; the explorer on the App page shows every type’s placement next to its measured density.',
          'Una célula de subretícula representa a las células de su tipo a su alrededor, y un nodo de población a todas sus células. Ambas son aproximaciones de un ojo real; el explorador de la página App muestra la ubicación de cada tipo junto a su densidad medida.',
        )}
      </Callout>
      <SectionRefs ids={['lappalainen2024', 'flyvis']} />
    </section>
  );

  const orientation = (
    <section>
      <h2>{t('The frame of the release and the frame of the engine', 'El marco de la liberación y el marco del motor')}</h2>
      <p>
        {t(
          'A filter is a pattern in space. Mi9 sits on one side of a T4 dendrite and Mi4 on the other, and that asymmetry is what makes each T4 subtype prefer one direction. The pattern means something only in the frame of the lattice the network runs on, where the engine’s stimulus renderer and the published tuning are defined. The release’s column axes are not that frame, and a comparison of synapse counts cannot notice: a rotated or mirrored filter has the same central count.',
          'Un filtro es un patrón en el espacio. Mi9 se ubica a un lado de una dendrita de T4 y Mi4 al otro, y esa asimetría es la que hace que cada subtipo de T4 prefiera una dirección. El patrón significa algo solo en el marco de la retícula en que corre la red, donde se definen el renderizador de estímulos del motor y el ajuste publicado. Los ejes de columna de la liberación no son ese marco, y una comparación de conteos de sinapsis no puede notarlo: un filtro rotado o reflejado tiene el mismo conteo central.',
        )}
      </p>
      <p>
        {t(
          'So the frame is measured. For every connection shared with the published consensus whose filters both have at least three entries, the synapse-weighted mean offset, with the centre entry excluded, gives the direction the inputs sit in. Each of the twelve symmetries of the hexagonal lattice is applied to the release’s filters, and the directions are compared with the reference by the cosine of the angle between them, weighted by the reference’s displacement.',
          'Así que el marco se mide. Para cada conexión compartida con el consenso publicado cuyos filtros tienen ambos al menos tres entradas, el desplazamiento medio ponderado por sinapsis, sin la entrada central, da la dirección en que se ubican las entradas. Cada una de las doce simetrías de la retícula hexagonal se aplica a los filtros de la liberación, y las direcciones se comparan con la referencia por el coseno del ángulo entre ellas, ponderado por el desplazamiento de la referencia.',
        )}
      </p>
      <Equation
        tex="d(F) = \frac{\sum_{(\Delta u,\Delta v) \neq 0} F(\Delta u,\Delta v)\ \big(\sqrt{3}(\Delta u + \Delta v/2),\ \tfrac{3}{2}\Delta v\big)}{\sum_{(\Delta u,\Delta v) \neq 0} F(\Delta u,\Delta v)}"
        caption={t(
          'The displacement of a filter: its synapse-weighted mean offset in Cartesian lattice units, the direction its inputs sit in.',
          'El desplazamiento de un filtro: su desplazamiento medio ponderado por sinapsis en unidades cartesianas de la retícula, la dirección en que se ubican sus entradas.',
        )}
      />
      <Equation
        tex="A(g) = \frac{\sum_k \lVert d^{\mathrm{ref}}_k \rVert \cos\angle\big(d^{\mathrm{ref}}_k,\ g\cdot d^{\mathrm{here}}_k\big)}{\sum_k \lVert d^{\mathrm{ref}}_k \rVert}"
        caption={t(
          'The agreement of the two frames under a lattice symmetry g: +1 when every filter points the same way, -1 when every one points the opposite way.',
          'El acuerdo de los dos marcos bajo una simetría g de la retícula: +1 cuando cada filtro apunta igual, -1 cuando cada uno apunta al revés.',
        )}
      />
      <p>
        {t(
          'As first built, the identity scored -0.42 over 98 filters, the lowest of the twelve, and the half-turn scored +0.42, the highest; the inputs that define direction selectivity agreed (Mi9 onto T4a to T4d was turned by 141 to 170 degrees). The release’s axes point the opposite way from the engine’s, so the build writes every offset half-turned. The identity is now the best of the twelve, and the comparison report re-measures it on every build.',
          'Tal como se construyó primero, la identidad obtuvo -0,42 sobre 98 filtros, la más baja de las doce, y el medio giro +0,42, la más alta; las entradas que definen la selectividad a la dirección coincidieron (Mi9 sobre T4a a T4d estaba girado entre 141 y 170 grados). Los ejes de la liberación apuntan al revés que los del motor, así que la construcción escribe cada desplazamiento con medio giro. La identidad es ahora la mejor de las doce, y el reporte de comparación la vuelve a medir en cada construcción.',
        )}
      </p>
      <Callout variant="honest" title={t('Why it matters', 'Por qué importa')}>
        {t(
          'Without this step the network would have been built in a frame where T4a looks like T4b and T4c like T4d, and every direction read from it would have been reversed. The half-turn was measured on the right eye; the left eye’s frame is recorded as open.',
          'Sin este paso la red se habría construido en un marco donde T4a parece T4b y T4c parece T4d, y cada dirección leída de ella habría quedado invertida. El medio giro se midió en el ojo derecho; el marco del ojo izquierdo queda registrado como pendiente.',
        )}
      </Callout>
      <SectionRefs ids={['maisak2013', 'lappalainen2024']} />
    </section>
  );

  const dynamics = (
    <section>
      <h2>{t('Dynamics and the three regimes', 'Dinámica y los tres regímenes')}</h2>
      <p>
        {t(
          'The network is the engine’s passive point-neuron model with graded, instantaneous synapses. A cell’s voltage relaxes to rest with its time constant and is driven by the rectified voltages of its presynaptic partners, each through a weight that multiplies a sign, a synapse count and a strength. It is integrated with an explicit Euler step: 20 ms for training clips and 5 ms for the characterisation stimuli, after grey input to a steady state.',
          'La red es el modelo de neurona puntual pasiva del motor con sinapsis graduadas e instantáneas. El voltaje de una célula relaja al reposo con su constante de tiempo y es impulsado por los voltajes rectificados de sus socios presinápticos, cada uno a través de un peso que multiplica un signo, un conteo de sinapsis y una intensidad. Se integra con un paso de Euler explícito: 20 ms para clips de entrenamiento y 5 ms para los estímulos de caracterización, tras una entrada gris hasta un estado estacionario.',
        )}
      </p>
      <Equation
        tex="\tau_{t_i}\,\frac{dV_i}{dt} = -V_i + \sum_j \alpha_{t_i t_j}\,\sigma_{t_j}\,N_{ij}\,\operatorname{ReLU}(V_j) + V^{\mathrm{rest}}_{t_i} + e_i"
        caption={t(
          'The dynamics, with the strength initialised at 0.01 over the mean synapse count of its group and clamped non-negative, the time constant at 50 ms and the resting potential drawn around 0.5.',
          'La dinámica, con la intensidad inicializada en 0,01 sobre el conteo medio de sinapsis de su grupo y restringida a no negativa, la constante de tiempo en 50 ms y el potencial de reposo muestreado en torno a 0,5.',
        )}
      />
      <InlineSvg src="svg/docs/frozen-regimes.svg" label={t('What each regime may change', 'Lo que cada régimen puede cambiar')} />
      <p>
        {t(
          'The three regimes differ only in what else may learn. R0, the reservoir, trains nothing inside the network (0 parameters on the right optic lobe). R1, the regime of the published model, trains the strength per connected pair of types and the time constant and resting potential per type (8,409 parameters). R2 trains them per connection and per neuron (3,003,002 parameters). All three start from the same values, built per type and broadcast, so a comparison between regimes compares what training was allowed to change, never where it started.',
          'Los tres regímenes difieren solo en qué más puede aprender. R0, el reservorio, no entrena nada dentro de la red (0 parámetros en el lóbulo óptico derecho). R1, el régimen del modelo publicado, entrena la intensidad por par de tipos conectados y la constante de tiempo y el potencial de reposo por tipo (8.409 parámetros). R2 los entrena por conexión y por neurona (3.003.002 parámetros). Los tres parten de los mismos valores, construidos por tipo y difundidos, así que una comparación entre regímenes compara lo que el entrenamiento pudo cambiar, nunca desde dónde partió.',
        )}
      </p>
      <p>
        {t(
          'A starting point can also be borrowed. Where a MaleCNS type matches a type of the published model, its trained time constant and resting potential are copied, and its trained strength per pair is rescaled so that the total drive onto a central cell is preserved, because the two reconstructions count different numbers of synapses for the same connection. On the right optic lobe 53 of 253 types and 388 of 7,903 type pairs receive published values.',
          'Un punto de partida también puede tomarse prestado. Donde un tipo de MaleCNS coincide con un tipo del modelo publicado, se copian su constante de tiempo y su potencial de reposo entrenados, y su intensidad entrenada por par se reescala para preservar la excitación total sobre una célula central, porque las dos reconstrucciones cuentan números distintos de sinapsis para la misma conexión. En el lóbulo óptico derecho 53 de 253 tipos y 388 de 7.903 pares de tipos reciben valores publicados.',
        )}
      </p>
      <Equation
        tex="\alpha^{\mathrm{here}}_{t_i t_j} = \alpha^{\mathrm{pub}}_{t_i t_j}\,\frac{S^{\mathrm{pub}}_{t_i t_j}}{S^{\mathrm{here}}_{t_i t_j}},\qquad S_{t_i t_j} = \sum_{j \in t_j} N_{c(t_i),\,j}"
        caption={t(
          'Transfer that preserves drive: the published strength times the ratio of the synapses a central target cell receives in each reconstruction.',
          'Transferencia que preserva la excitación: la intensidad publicada por la razón de las sinapsis que una célula destino central recibe en cada reconstrucción.',
        )}
      />
      <Callout variant="honest" title={t('Frozen means stable only if the gain allows it', 'Congelado es estable solo si la ganancia lo permite')}>
        {t(
          'The lattice network settles although its loop gain is above one. The whole visual system, neuron by neuron, does not: from the engine’s initialisation its activity runs away, so it is built with every strength scaled by one factor until the spectral radius of its absolute weights is 0.9. That factor is recorded with the network.',
          'La red en retícula se estabiliza aunque su ganancia de lazo es mayor que uno. El sistema visual completo, neurona por neurona, no: desde la inicialización del motor su actividad se desboca, así que se construye con cada intensidad escalada por un solo factor hasta que el radio espectral de sus pesos absolutos es 0,9. Ese factor queda registrado con la red.',
        )}
      </Callout>
      <SectionRefs ids={['lappalainen2024', 'lukosevicius2009', 'lehoucq1998']} />
    </section>
  );

  const controls = (
    <section>
      <h2>{t('Null controls', 'Controles nulos')}</h2>
      <p>
        {t(
          'A claim that "the connectome helps" is only falsifiable against networks that share its size, sparsity and statistics but not its biology. Without them, an advantage could come from having a sparse recurrent graph of the right size, from the balance of excitation and inhibition, or from the filter shapes, and nothing could tell those apart. The precedent is the robot-navigation work that trained a network on the full fly brain, whose degree-matched random graph is what makes its out-of-distribution result readable at all.',
          'Una afirmación de que "el conectoma ayuda" solo es falsable frente a redes que comparten su tamaño, dispersión y estadísticas pero no su biología. Sin ellas, una ventaja podría venir de tener un grafo recurrente disperso del tamaño correcto, del balance entre excitación e inhibición, o de las formas de los filtros, y nada podría distinguirlas. El precedente es el trabajo de navegación robótica que entrenó una red sobre el cerebro completo de la mosca, cuyo grafo aleatorio con grados igualados es lo que hace legible su resultado fuera de distribución.',
        )}
      </p>
      <p>
        {t(
          'N1, degree-preserving rewiring, keeps every type’s in- and out-degree, every filter and the synapse total, and scrambles who connects to whom by double-edge swaps. N2, a size-matched random graph, keeps every connection with its filter but places each between a source and a target drawn at random. N3, a sign shuffle, keeps the wiring and the filters and permutes the signs across connections, so the excitation-to-inhibition ratio survives and which connections are inhibitory does not.',
          'N1, recableado que preserva grados, conserva el grado de entrada y salida de cada tipo, cada filtro y el total de sinapsis, y mezcla quién se conecta con quién mediante intercambios de dos aristas. N2, un grafo aleatorio del mismo tamaño, conserva cada conexión con su filtro pero ubica cada una entre una fuente y un destino elegidos al azar. N3, una permutación de signos, conserva el cableado y los filtros y permuta los signos entre conexiones, así que la razón entre excitación e inhibición sobrevive y cuáles conexiones son inhibitorias no.',
        )}
      </p>
      <Equation
        tex="\deg^{\mathrm{out}}_{N1}(t) = \deg^{\mathrm{out}}(t),\quad \deg^{\mathrm{in}}_{N1}(t) = \deg^{\mathrm{in}}(t),\quad \sum N_{N1} = \sum N"
        caption={t(
          'What N1 must preserve, asserted in the tests on every seed: the type-level degree sequences and the synapse total.',
          'Lo que N1 debe preservar, verificado en las pruebas para cada semilla: las secuencias de grados a nivel de tipo y el total de sinapsis.',
        )}
      />
      <p>
        {t(
          'Size has to match where the network is simulated, at the level of cells. Cell types sit on lattices of different densities, so a filter moved onto a denser target expands into more cell connections: an unconstrained rewiring of the measured connectome produced a control with 6.85 million connections and 3.3 times the synapses of the original 2.92 million. Both graph-changing controls therefore move a connection only between types of the same placement, and every control compiles to exactly the measured 2,922,900 cell connections and 10,281,886 synapses.',
          'El tamaño tiene que coincidir donde la red se simula, a nivel de células. Los tipos celulares están en retículas de distinta densidad, así que un filtro movido sobre un destino más denso se expande en más conexiones de células: un recableado sin restricciones del conectoma medido produjo un control con 6,85 millones de conexiones y 3,3 veces las sinapsis de los 2,92 millones originales. Por eso ambos controles que cambian el grafo mueven una conexión solo entre tipos de la misma ubicación, y cada control compila exactamente a las 2.922.900 conexiones de células y 10.281.886 sinapsis medidas.',
        )}
      </p>
      <Equation
        tex="\#\mathcal{E}_{\mathrm{cells}}(N_k) = \#\mathcal{E}_{\mathrm{cells}}(\text{measured}),\qquad k \in \{1, 2, 3\}"
        caption={t(
          'Cell-level size matching, which follows from moving connections only within a placement class: a connection’s placement pair and filter decide how many cell connections it becomes.',
          'La igualdad de tamaño a nivel de células, que se sigue de mover conexiones solo dentro de una clase de ubicación: el par de ubicaciones de una conexión y su filtro deciden en cuántas conexiones de células se convierte.',
        )}
      />
      <Callout variant="honest" title={t('What the controls can and cannot show', 'Lo que los controles pueden y no pueden mostrar')}>
        {t(
          'A control is a pure function of the measured connectome and a seed, and results are reported as a spread over seeds. A result that does not separate from the controls is reported as such; so far the frozen networks and their controls are equally untuned to motion, so tuning alone cannot separate them and only a task result can.',
          'Un control es una función pura del conectoma medido y una semilla, y los resultados se informan como una dispersión sobre semillas. Un resultado que no se separa de los controles se informa como tal; hasta ahora las redes congeladas y sus controles están igualmente sin ajuste al movimiento, así que el ajuste por sí solo no puede separarlos y solo un resultado de tarea puede.',
        )}
      </Callout>
      <SectionRefs ids={['wang2026', 'lappalainen2024']} />
    </section>
  );

  return (
    <div className="page-body wide prose">
      <div className="page-head">
        <h1>{t('Methodology', 'Metodología')}</h1>
        <p className="lede">
          {t(
            'How the measured connectome becomes a network and how that network is kept honest: the consensus filters and their signs, the inferred retinotopic columns, the placement of every cell type and the expansion of its filters, the frame the filters are written in, the dynamics and the three regimes, and the null controls. The method ladder for depth and segmentation joins this page as its units arrive. Throughout, a filter is ',
            'Cómo el conectoma medido se vuelve una red y cómo esa red se mantiene honesta: los filtros de consenso y sus signos, las columnas retinotópicas inferidas, la ubicación de cada tipo celular y la expansión de sus filtros, el marco en que se escriben los filtros, la dinámica y los tres regímenes, y los controles nulos. La escalera de métodos para profundidad y segmentación se suma a esta página a medida que llegan sus unidades. En todo momento, un filtro es ',
          )}
          <InlineMath tex="F_{t_i t_j}(\Delta u, \Delta v)" />.
        </p>
      </div>
      <Tabs
        ariaLabel={t('Methods', 'Métodos')}
        tabs={[
          { id: 'construction', label: t('Construction', 'Construcción'), content: construction },
          { id: 'columns', label: t('Columns', 'Columnas'), content: columns },
          { id: 'placement', label: t('Placement', 'Ubicación'), content: placement },
          { id: 'orientation', label: t('Orientation', 'Orientación'), content: orientation },
          { id: 'dynamics', label: t('Dynamics', 'Dinámica'), content: dynamics },
          { id: 'controls', label: t('Controls', 'Controles'), content: controls },
        ]}
      />
    </div>
  );
}
