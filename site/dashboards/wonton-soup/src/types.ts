export interface Run {
  run_key: string;
  run_id: string | null;
  provider: string | null;
  backend: string | null;
  mode: string | null;
  corpus: string | null;
  created_at: string | null;
  goal_sig_scheme: string | null;
  trace_mcts: boolean | null;
  config_whitelist_hash: string | null;
  config_full_hash: string | null;
}

export interface RunAggregate {
  run_key: string;
  theorem_count: number | null;
  crashed_count: number | null;
  wild_type_solve_rate: number | null;
  intervention_count: number | null;
  intervention_solve_rate: number | null;
}

export interface TheoremWild {
  run_key: string;
  theorem: string;
  solved: boolean | null;
  iterations: number | null;
  proof_term_hash: string | null;
  k_valid: boolean | null;
  k_null_model: string | null;
  k_tau_agent: number | null;
  k_tau_blind: number | null;
  k_K: number | null;
}

export interface TheoremIntervention {
  run_key: string;
  theorem: string;
  intervention: string;
  solved: boolean | null;
  status: string | null;
  is_control: boolean | null;
  baseline_solved: boolean | null;
  ged_search_value: number | null;
  ged_search_norm: number | null;
  ged_search_soft_value: number | null;
  ged_search_soft_norm: number | null;
  k_valid: boolean | null;
  k_null_model: string | null;
  k_tau_agent: number | null;
  k_tau_blind: number | null;
  k_K: number | null;
}

export interface TheoremInterventionComparison {
  run_key: string;
  theorem: string;
  intervention: string;
  solved: boolean | null;
  status: string | null;
  wild_type_hash: string | null;
  intervention_hash: string | null;
  hash_mismatch: boolean | null;
  axiom_delta_count: number | null;
  axiom_removed_count: number | null;
  trajectory_iteration_diff: number | null;
  trajectory_backtrack_diff: number | null;
  ged_search_value: number | null;
  ged_search_norm: number | null;
  ged_search_valid: boolean | null;
  ged_search_soft_value: number | null;
  ged_search_soft_norm: number | null;
  ged_search_soft_valid: boolean | null;
  ged_proof_value: number | null;
  ged_proof_norm: number | null;
  ged_proof_valid: boolean | null;
  ged_trace_value: number | null;
  ged_trace_norm: number | null;
  ged_trace_valid: boolean | null;
}

export interface TheoremVariantMetrics {
  run_key: string;
  theorem: string;
  variant: string;
  trajectory_total_iterations: number | null;
  trajectory_backtrack_count: number | null;
  trajectory_max_depth_reached: number | null;
  trajectory_depth_at_solution: number | null;
  trajectory_unique_goals_visited: number | null;
  trajectory_tactic_diversity: number | null;
  detour_total_iterations: number | null;
  detour_total_attempts: number | null;
  detour_success_count: number | null;
  detour_failure_count: number | null;
  detour_blocked_count: number | null;
  detour_failure_ratio: number | null;
  detour_max_depth: number | null;
  detour_depth_at_solution: number | null;
  detour_terminal_iteration: number | null;
  proof_term_node_count: number | null;
  proof_term_depth: number | null;
  proof_term_width: number | null;
  solution_path_len: number | null;
  tactic_fingerprint: string | null;
}

export interface GraphNode {
  run_key: string;
  theorem: string;
  variant: string | null;
  graph_kind: string;
  node_id: string;
  goal_sig: string | null;
  in_proof: boolean | null;
  goal_type: string | null;
}

export interface GraphEdge {
  run_key: string;
  theorem: string;
  variant: string | null;
  graph_kind: string;
  edge_idx: number;
  src_node_id: string;
  dst_node_id: string;
  tactic: string | null;
  tactic_family: string | null;
  in_proof: boolean | null;
}

export interface GoalTypeTactic {
  run_key: string;
  goal_type: string;
  tactic_norm: string;
  tactic_family: string | null;
  success: number;
  failure: number;
  blocked: number;
  total: number;
}

export interface KReferenceScore {
  run_key: string;
  theorem: string;
  variant: string;
  ref_id: string;
  valid: boolean | null;
  primary_null_model: string | null;
  tau_agent: number | null;
  tau_blind: number | null;
  K: number | null;
}

export interface MctsTraceStats {
  run_key: string;
  theorem: string;
  variant: string | null;
  line_count: number;
  bad_json_lines: number;
  event_count: number;
  iteration_event_count: number;
  tactic_attempt_event_count: number;
  max_iteration: number | null;
  unique_mvar_count: number;
  candidate_total: number;
  candidate_max: number;
}

export interface MctsTreeNode {
  run_key: string;
  theorem: string;
  variant: string | null;
  mvar_id: string;
  goal_type: string | null;
  goal_sig: string | null;
  depth: number;
  visit_count: number;
  success_count: number;
  is_terminal: boolean;
  is_dead: boolean;
  expansion_order: number | null;
}

export interface MctsTreeEdge {
  run_key: string;
  theorem: string;
  variant: string | null;
  parent_mvar_id: string;
  child_mvar_id: string;
  tactic: string;
  edge_order: number;
}

export interface Manifest {
  schema_version: number;
  format: string;
  release_id: string;
  compiled_at: string;
  tables: ManifestTable[];
}

export interface ManifestTable {
  name: string;
  file: string;
}

export type ViewId = "hero" | "proof-graph" | "rescue" | "explorer";
