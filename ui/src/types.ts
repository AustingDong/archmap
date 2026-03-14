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
  created_at: string
}

export interface FileMapping {
  file_path: string
  component_id: string
  mapped_at: string
  mapped_by: string
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
