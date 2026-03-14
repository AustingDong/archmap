export interface Component {
  id: string
  name: string
  description: string
  layer: 'frontend' | 'backend' | 'database' | 'infra' | 'shared' | 'testing' | 'other'
  tags: string[]
  color: string
  confidence: 'auto' | 'confirmed'
  created_at: string
  updated_at: string
  metadata: Record<string, unknown>
}

export interface Dependency {
  id: string
  from_component: string
  to_component: string
  label: string
  kind: 'runtime' | 'build' | 'test' | 'dev'
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
  status: 'todo' | 'in_progress' | 'done' | 'blocked' | 'cancelled'
  priority: 'low' | 'medium' | 'high' | 'critical'
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
