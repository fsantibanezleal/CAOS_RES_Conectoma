import { useEffect, useState } from 'react';
import { loadReport } from '../api/artifacts';

// The shapes of the committed reports the Experiments and Benchmark pages read. Only the fields the pages
// use are typed; every number on those pages comes from here, never from the page source.

export interface HoldoutRow {
  n: number;
  recovered: number;
  exact_fraction: number;
  within_one_fraction: number;
  median_error_columns: number;
  p95_error_columns: number;
}

export interface BuildReport {
  neurons: number;
  cell_types: number;
  edges: number;
  offsets: number;
  rows_scanned: number;
  rows_kept: number;
  column_assignment: number;
  column_inference: {
    inferred: number;
    unplaced: number;
    holdout: {
      per_type: Record<string, HoldoutRow>;
      summary: {
        types_tested: number;
        types_recovered: number;
        median_exact_fraction: number;
        median_within_one_fraction: number;
        worst_p95_error_columns: number;
      };
    };
  };
}

export interface Comparison {
  orientation: { filters_compared: number; identity: number; best: string; by_symmetry: Record<string, number | null> };
  types: { built: number; reference: number; reference_matched: number; reference_unmatched: string[] };
  connections: { reference_comparable: number; recovered: number; recovered_fraction: number; missing_here_total: number };
  signs: { compared: number; agreeing: number; agreement_fraction: number; disagreeing: { connection: string[]; reference: number; built: number }[] };
  central_synapse_counts: { spearman: number; n: number };
}

export interface TuningSummaryRow {
  networks: number;
  median_dsi: number;
  median_distance_to_known_degrees: number;
  share_within_45_degrees: number;
}

export interface VoltageParity {
  model: string;
  cells: number;
  stimuli: number[];
  frames: number[];
  values_compared: number;
  padding_values: number;
  same_padding: boolean;
  max_abs_difference: number;
  largest_voltage: number;
  tolerance: number;
  passed: boolean;
}

export interface Parity {
  voltage_parity: VoltageParity[];
  tuning: {
    models: string[];
    summary: Record<string, TuningSummaryRow>;
    quality: {
      criteria: { min_dsi: number; within_degrees: number; reversed_beyond: number };
      by_subtype: Record<string, { as_known: number; reversed: number; weak: number; other: number }>;
      by_rank: { models: string; as_known: number; of: number }[];
      rank_correlation: number;
    };
  };
  pipeline_crosscheck: { models: string[]; largest_dsi_difference: number; largest_direction_difference_degrees: number };
}

export interface Stability {
  finite: boolean;
  min: number;
  max: number;
  mean_abs: number;
  drift_last_half_second: number;
}

export interface Characterization {
  device: string;
  frozen: Record<'default' | 'transfer', {
    parameters: { trainable: number; frozen: number };
    transfer: { model: string; bias: { transferred: number; of: number }; time_const: { transferred: number; of: number }; syn_strength: { transferred: number; of: number } } | null;
    stability: Stability;
    settled: boolean;
    simulation: { simulated_seconds_per_wall_second_per_sample: number; batch_size: number; dt: number };
    tuning_summary: Record<string, TuningSummaryRow>;
    motion_activity: Record<string, { resting_voltage: number; peak_voltage: number; largest_change_from_rest: number; share_of_stimuli_driving_above_zero: number }>;
    loop_gain: { spectral_radius: number; largest_component: number; cells: number };
    compile: { nodes: number; edges: number; connections_unrealised: string[][] };
  }>;
  training_step: Record<string, { seconds_per_step: number; peak_memory_gb: number; trainable: number; batch_size: number; frames: number }>;
  controls: Record<string, { seeds: number[]; settled: boolean[]; stability: Stability[]; tuning_summary: Record<string, TuningSummaryRow> }>;
}

export interface VisualCnsCharacterization {
  gain_target: number;
  unnormalised: Record<'default' | 'transfer', { spectral_radius: { spectral_radius: number }; stability: Stability; settled: boolean }>;
  frozen: Record<'default' | 'transfer', {
    gain: { spectral_radius_before: number; scale: number; spectral_radius_after: number; largest_component: number; cells_in_recurrent_components: number };
    stability: Stability;
    settled: boolean;
    flash: { by_role: Record<'input' | 'intermediate' | 'output', { cells: number; responding_fraction: number; median_change: number; max_change: number }> };
    simulation: { simulated_seconds_per_wall_second_per_sample: number };
    peak_memory_gb: number;
    compile: { nodes: number; edges: number; input_neurons: number };
  }>;
  training_step_R1: { seconds_per_step: number; peak_memory_gb: number; trainable: number; batch_size: number };
}

export interface VisualCnsSummary {
  neurons: number;
  cell_types: number;
  connections: number;
  synapses: number;
  by_side: { L: number; R: number };
  by_superclass: Record<string, number>;
  photoreceptors: Record<'L' | 'R', { cells: number; placed: number }>;
  columns: Record<'L' | 'R', { optic_lobe_neurons: number; annotated: number; inferred: number; unplaced: number; holdout: { median_exact_fraction: number; median_within_one_fraction: number } }>;
}

export const REPORTS = {
  build: 'connectome/malecns-optic-lobe-r.report.json',
  comparison: 'connectome/malecns-optic-lobe-r.comparison.json',
  parity: 'network/parity-published.json',
  lattice: 'connectome/malecns-optic-lobe-r.characterization.json',
  visualCns: 'connectome/malecns-visual-cns.characterization.json',
  visualCnsSummary: 'connectome/malecns-visual-cns.summary.json',
} as const;

export interface Reports {
  build: BuildReport;
  comparison: Comparison;
  parity: Parity;
  lattice: Characterization;
  visualCns: VisualCnsCharacterization;
  visualCnsSummary: VisualCnsSummary;
}

/** All committed reports, loaded once per page. */
export function useReports(): { reports: Reports | null; error: string | null } {
  const [reports, setReports] = useState<Reports | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    Promise.all([
      loadReport<BuildReport>(REPORTS.build),
      loadReport<Comparison>(REPORTS.comparison),
      loadReport<Parity>(REPORTS.parity),
      loadReport<Characterization>(REPORTS.lattice),
      loadReport<VisualCnsCharacterization>(REPORTS.visualCns),
      loadReport<VisualCnsSummary>(REPORTS.visualCnsSummary),
    ])
      .then(([build, comparison, parity, lattice, visualCns, visualCnsSummary]) => {
        if (live) setReports({ build, comparison, parity, lattice, visualCns, visualCnsSummary });
      })
      .catch((e) => live && setError(String(e)));
    return () => {
      live = false;
    };
  }, []);
  return { reports, error };
}
