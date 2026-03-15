export type Layer = 'frontend' | 'backend' | 'database' | 'infra' | 'shared' | 'testing' | 'other'
export type Confidence = 'auto' | 'confirmed'
export type PlanStatus = 'todo' | 'in_progress' | 'done' | 'blocked' | 'cancelled'
export type PlanPriority = 'low' | 'medium' | 'high' | 'critical'
export type DepKind = 'runtime' | 'build' | 'test' | 'dev'

export interface Component {
  id: string
  name: string
  description: string
  layer: Layer
  tags: string[]
  color: string
  confidence: Confidence
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
}

export interface FileMapping {
  file_path: string
  component_id: string
  mapped_at: string
  mapped_by: string
  metadata: { description?: string; functions?: string[]; language?: string }
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
}

export interface GraphEdge {
  id: string
  source: string
  target: string
  label: string
  kind: string
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
  upstream: string[]    // components that depend ON this (would break if it changes)
  downstream: string[]  // components this depends ON
  cycles: string[]
  is_leaf: boolean
  is_root: boolean
  impact_score: number
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
