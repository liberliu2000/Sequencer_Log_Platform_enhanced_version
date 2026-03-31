export type User = {
  id: number;
  username: string;
  email: string;
  status: string;
  roles: string[];
  is_admin: boolean;
  is_reviewer: boolean;
  email_verified: boolean;
  force_password_change: boolean;
  approval_requested_at?: string | null;
  approved_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  registration_note?: string | null;
};

export type ModuleConfig = {
  id: number;
  module_key: string;
  display_name: string;
  prefix: string;
  description?: string | null;
  is_active: boolean;
  is_system: boolean;
};

export type TaskCluster = {
  id: number;
  cluster_key: string;
  display_name: string;
  description?: string | null;
  review_status: string;
  is_active: boolean;
  is_system: boolean;
  created_by?: string | null;
};

export type SolutionRecord = {
  id: number;
  error_name: string;
  error_category?: string | null;
  module: string;
  submodule?: string | null;
  error_code?: string | null;
  error_code_prefix?: string | null;
  message?: string | null;
  normalized_signature?: string | null;
  exception_description?: string | null;
  trigger_scenario?: string | null;
  impact_scope?: string | null;
  report_source?: string | null;
  root_cause_analysis?: string | null;
  verified_solution?: string | null;
  workaround?: string | null;
  owner_department?: string | null;
  submitter?: string | null;
  source?: string | null;
  review_status: string;
  reusable: boolean;
  tags?: string[];
  task_clusters?: string[];
  message_keywords?: string[];
  created_at?: string | null;
  updated_at?: string | null;
  solution_summary?: string | null;
  root_cause_summary?: string | null;
  trigger_scenario_summary?: string | null;
};

export type SolutionReview = {
  id: number;
  task_uuid?: string | null;
  normalized_signature?: string | null;
  module?: string | null;
  submodule?: string | null;
  submission_type: string;
  proposed_payload: Record<string, unknown>;
  review_status: string;
  review_reason?: string | null;
  revision_suggestions?: string[];
  advisory_review_status?: string | null;
  advisory_review_reason?: string | null;
  created_by?: string | null;
  reviewed_by?: string | null;
  linked_solution_id?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type RepositoryConfig = {
  module_tree: Array<Record<string, unknown>>;
  module_prefixes: Record<string, string>;
  modules: ModuleConfig[];
  task_clusters: TaskCluster[];
  fts_enabled: boolean;
  analysis_depths: Record<string, unknown>;
};

export type PaginatedItems<T> = {
  items: T[];
  total: number;
};
