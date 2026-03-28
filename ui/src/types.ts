export type Layer = 'frontend' | 'backend' | 'database' | 'infra' | 'shared' | 'testing' | 'other'
export type Confidence = 'auto' | 'confirmed'
export type PlanStatus = 'todo' | 'in_progress' | 'done' | 'blocked' | 'cancelled'
export type PlanPriority = 'low' | 'medium' | 'high' | 'critical'
export type DepKind = 'runtime' | 'build' | 'test' | 'dev'
export type NodeLevel = 1 | 2 | 3 | 4 | 5
export type EdgeType = 'command' | 'query' | 'event' | 'import' | 'data_read' | 'data_write' | 'invoke' | 'stream'
export type EdgeLevel = 'domain' | 'service' | 'component' | 'module'
export type Stability = 'stable' | 'beta' | 'internal' | 'deprecated'

// Level labels for display
export const LEVEL_LABELS: Record<NodeLevel, string> = {
  1: 'System',
  2: 'Domain',
  3: 'Service',
  4: 'Component',
  5: 'Module',
}

// Edge type colors for visualization
export const EDGE_TYPE_COLOR: Record<string, string> = {
  command:    '#f97316',  // orange — write intent
  query:      '#3b82f6',  // blue — read request
  event:      '#22c55e',  // green — async notification
  import:     '#94a3b8',  // gray — static import
  data_read:  '#60a5fa',  // light blue — storage read
  data_write: '#fb923c',  // light orange — storage write
  invoke:     '#a78bfa',  // purple — generic call
  stream:     '#f472b6',  // pink — continuous flow
}

export interface Component {
  id: string
  name: string
  description: string
  layer: Layer
  tags: string[]
  color: string
  confidence: Confidence
  // Multi-level hierarchy
  level: NodeLevel
  parent_id: string
  // L3 service
  protocol: string
  port: number | null
  deploy_unit: boolean
  // L4 component interface
  public_api: string[]
  data_owned: string[]
  stability: Stability
  // Ownership
  owner: string
  tier: string
  onboarding_notes: string
  runbook_url: string
  slack_channel: string
  created_at: string
  updated_at: string
  metadata: Record<string, unknown>
}

export interface Dependency {
  id: string
  from_component: string
  to_component: string
  label: string
  kind: DepKind
  confidence: 'auto' | 'confirmed'
  created_at: string
  // Semantic edge typing
  edge_type: EdgeType
  edge_level: EdgeLevel
  crosses_boundary: boolean
  async_flag: boolean
  direction: 'uni' | 'bi'
  interface_points: string[]
  payload_types: string[]
  stability: Stability
}

export interface FileMapping {
  file_path: string
  component_id: string
  mapped_at: string
  mapped_by: string
  metadata: { description?: string; functions?: string[]; language?: string }
  symbols?: Array<{ name: string; display_name?: string; kind?: string; start_line?: number }>
}

export interface PlanItem {
  id: string
  title: string
  description: string
  component_id: string | null
  status: PlanStatus
  priority: PlanPriority
  tags: string[]
  created_at: string
  updated_at: string
  metadata: Record<string, unknown>
}

export interface GraphNode {
  id: string
  label: string
  layer: string
  color: string
  confidence: string
  level?: NodeLevel
  parent_id?: string
}

export interface GraphEdge {
  id: string
  source: string
  target: string
  label: string
  kind: string
  edge_type?: EdgeType
  crosses_boundary?: boolean
  async_flag?: boolean
  stability?: Stability
  interface_points?: string[]
  payload_types?: string[]
}

export interface DependencyGraph {
  nodes: GraphNode[]
  edges: GraphEdge[]
  adjacency: Record<string, string[]>
}

export interface ProjectStatus {
  name: string
  initialized: boolean
  components: number
  dependencies: number
  mapped_files: number
  plan_items: number
  plan_open: number
}

// ─── Contract types ───────────────────────────────────────────────────────────

export interface ContractOp {
  name: string
  description: string
  input_type: string
  output_type: string
  stability: Stability
}

export interface ContractEvent {
  name: string
  description: string
  payload_type: string
  stability: Stability
}

export interface DataType {
  type_name: string
  description: string
  schema: string
  stability: Stability
  authoritative: boolean
}

export interface Contract {
  node_id: string
  node_level: NodeLevel
  declared: boolean
  commands: ContractOp[]
  queries: ContractOp[]
  events_emitted: ContractEvent[]
  events_consumed: ContractEvent[]
  data_owned: DataType[]
  data_read: DataType[]
  api_spec_url: string
  sla: string
  declared_at?: string
  declared_by?: string
}

// ─── Work context types ───────────────────────────────────────────────────────

export interface WorkContextFile {
  file_path: string
  component_id: string
  language: string
  symbols: Array<{
    name: string
    kind: string
    signature: string
    visibility: string
    is_entry_point: boolean
    in_public_api: boolean
  }>
  symbol_count: number
}

export interface ConsumedNode {
  node_id: string
  node_name: string
  level: NodeLevel
  protocol: string
  port: number | null
  edge_type: EdgeType
  interface_points: string[]
  payload_types: string[]
  stability: Stability
  contract: Partial<Contract>
}

export interface WorkContext {
  working_on: {
    node_id: string
    name: string
    level: NodeLevel
    layer: string
    description: string
    public_api: string[]
    data_owned: string[]
    stability: Stability
    owner: string
    task: string
  }
  i_own: {
    files: WorkContextFile[]
    file_count: number
    descendant_nodes: string[]
  }
  i_consume: ConsumedNode[]
  coordination_needed: Array<{
    node_id: string
    node_name: string
    level: NodeLevel
    owner: string
    interface_points_used: string[]
    stability: Stability
    reason: string
  }>
  step_size: 'atomic' | 'local' | 'bounded' | 'service' | 'cross'
  step_explanation: string
  adr_recommended: boolean
}

// ─── Domain map types ─────────────────────────────────────────────────────────

export interface DomainMap {
  system: Component[]
  domains: Array<Component & { child_count: number; contract: Contract }>
  cross_domain_edges: Array<{
    from_domain: string
    from_name: string
    to_domain: string
    to_name: string
    edge_types: EdgeType[]
  }>
  summary: string
}

// ─── Node detail types ────────────────────────────────────────────────────────

export interface NodeDetail {
  node: Component
  contract: Contract
  children: Component[]
  child_count: number
  outgoing_edges: Array<{
    dep_id: string
    from_component: string
    from_name: string
    from_level: NodeLevel
    to_component: string
    to_name: string
    to_level: NodeLevel
    edge_type: EdgeType
    interface_points: string[]
    payload_types: string[]
    stability: Stability
    async_flag: boolean
    crosses_boundary: boolean
  }>
  incoming_edges: NodeDetail['outgoing_edges']
  files?: Array<{ file_path: string; language: string; symbol_count: number }>
}

// ─── Change surface types ─────────────────────────────────────────────────────

export interface ChangeSurface {
  symbols_queried: string[]
  owners: Array<{
    symbol: string
    component_id: string
    component_name: string
    component_level: NodeLevel
    file_path: string
    in_public_api: boolean
    visibility: string
  }>
  affected_edges: Array<{
    dep_id: string
    from_component: string
    from_name: string
    from_level: NodeLevel
    to_component: string
    to_name: string
    to_level: NodeLevel
    matched_symbols: string[]
    edge_type: EdgeType
    stability: Stability
    crosses_boundary: boolean
    will_break: boolean
  }>
  breaking_edge_count: number
  touched_components: Array<{ id: string; name: string; level: NodeLevel }>
  step_size: 'atomic' | 'local' | 'bounded' | 'service' | 'cross'
  step_explanation: string
  adr_recommended: boolean
  recommended_update_order: string[]
}

// ─── Existing types (unchanged) ───────────────────────────────────────────────

export interface FileMetrics {
  file_path: string
  lines: number
  complexity: number
  churn: number
  hotspot: boolean
}

export interface ComponentMetrics {
  component_id: string
  file_count: number
  total_lines: number
  avg_complexity: number
  total_churn: number
  hotspot: boolean
  files: FileMetrics[]
}

export interface ComponentImpact {
  component_id: string
  component_name: string
  level: NodeLevel
  stability: Stability
  public_api: string[]
  upstream: string[]
  upstream_names: string[]
  downstream: string[]
  downstream_names: string[]
  cycles: string[]
  is_leaf: boolean
  is_root: boolean
  impact_score: number
  step_size: string
  breaking_symbols: Array<{
    from_component: string
    from_name: string
    interface_points: string[]
    in_public_api: string[]
    not_in_public_api: string[]
    edge_type: EdgeType
    stability: Stability
    will_break_on_change: boolean
  }>
  breaking_symbol_count: number
}

export interface FileContent {
  file_path: string
  content: string
  lines: number
}

export interface SymbolExtract {
  symbol: string
  file_path: string
  code: string
  start_line: number
  end_line: number
  language: string
  fallback?: boolean
}

export interface SymbolSearchResult {
  symbol: string
  file_path: string
  component_id: string
}

export interface CodingContext {
  component: Component
  files: FileMapping[]
  dependencies: Array<Dependency & { from_name: string; to_name: string }>
  plan_items: PlanItem[]
}

export interface RelatedSearchResult {
  query: string
  summary: string
  components: Array<{ id: string; name: string; layer: string; description: string; confidence: string }>
  files: Array<{ file_path: string; component_id: string; component_name: string; language: string; description: string }>
  symbols: Array<{ symbol: string; file_path: string; component_id: string; component_name: string }>
}

export interface SymbolIndexEntry {
  symbol: string
  file_path: string
  language: string
  component_id: string
  component_name: string
  component_layer: string
}

export interface PathTrace {
  found: boolean
  length?: number
  text?: string
  error?: string
  from_component?: string
  from_name?: string
  to_component?: string
  to_name?: string
  path: Array<{
    component_id: string
    component_name: string
    layer: string
    via_dependency: { id: string; label: string; kind: string; confidence: string } | null
    files: string[]
  }>
}
