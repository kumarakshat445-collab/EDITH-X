export type View = "dashboard" | "ide" | "privacy" | "npu" | "settings";

export type Engine = {
  backend_id: string;
  label: string;
  level: string;
  model: string;
  precision: string;
  execution: string;
  network: string;
  detail: string;
  npu_active: boolean;
  npu_library_present: boolean;
  onnx_installed: boolean;
  onnx_providers: string[];
  cloud_allowed: boolean;
  cloud_configured: boolean;
  model_loaded: boolean;
  telemetry: {
    inference_latency_ms: number | null;
    tokens_per_sec: number | null;
    cpu_utilization_pct: number | null;
    npu_utilization_pct: number | null;
    memory_mb: number | null;
    note: string;
  };
  rule_engine_latency_ms: number | null;
};

export type ToolInfo = { detected: boolean; path: string | null; version: string; hint: string | null };
export type Tools = Record<string, ToolInfo>;

export type Settings = {
  theme: string;
  font_size: number;
  tab_size: number;
  minimap: boolean;
  word_wrap: boolean;
  engineering_mode: string;
  temperature: number;
  context_size: number;
  backend_preference: string;
  allow_cloud: boolean;
  telemetry: boolean;
  crash_reports: boolean;
  icarus_path: string;
  verilator_path: string;
  yosys_path: string;
  autosave: boolean;
  workspace: string;
};

export type Project = {
  id: string;
  name: string;
  template: string;
  description: string;
  rtl_files: number;
  testbenches: number;
  tests: number | null;
  passing: number | null;
  failing: number | null;
  synthesizability: number | null;
  simulation: string | null;
  updated: string | null;
};

export type TreeNode = { type: "dir" | "file"; name: string; path: string; children?: TreeNode[] };

export type Diagnostic = {
  severity: string;
  file: string;
  line: number;
  problem: string;
  why: string;
  fix: string;
  rule: string;
};

export type Proposal = {
  root_cause: string;
  evidence: string[];
  proposed_fix: string;
  why: string;
  diff: string;
  path: string | null;
  updated: string | null;
  rule: string;
  backend: string;
  can_apply: boolean;
};

export type Step = {
  id: string;
  label: string;
  status: string;
  detail?: string;
  log?: string;
  path?: string;
  analysis?: Proposal;
  diagnostics?: Diagnostic[];
  waveform?: boolean;
  passed?: number | null;
  failed?: number | null;
};

export type Report = {
  project: string;
  generated_at: string;
  errors: number;
  warnings: number;
  synthesizability: number;
  compilation: string;
  simulation: string;
  tests: number | null;
  passed: number | null;
  failed: number | null;
  assertions_passed: number | null;
  assertions_failed: number | null;
  assertions_note: string;
  synthesis: string;
  synthesis_cells: string | null;
  ai_rule: string;
  ai_summary: string;
  backend: string;
};

export type Wave = {
  available: boolean;
  reason?: string;
  timescale?: string;
  end?: number;
  truncated?: boolean;
  signals?: { name: string; width: number; id: string; changes: [number, string][] }[];
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
  route?: string;
  code?: string | null;
  suggested_path?: string | null;
};

export type Generated = {
  ok: boolean;
  backend: string;
  title: string;
  message: string;
  assumptions: string[];
  interface: string[];
  files: { path: string; content: string }[];
};

export type ModelRow = {
  id: string;
  name: string;
  kind: string;
  quantization: string;
  format: string;
  backend: string;
  device: string;
  status: string;
  installed?: boolean;
  size_bytes: number | null;
  notes: string;
};
