export type NodeStatus = 'confirmed' | 'proposed' | 'removing'
export type TaskStatus = 'queued' | 'active' | 'done' | 'rejected'

export interface TreeNode {
  id: string
  name: string
  description: string
  status: NodeStatus
  user_notes: string
  children: TreeNode[]
  files: string[]
  file_snapshots: Record<string, number>
  cross_references: string[]
  created_at: string
  updated_at: string
}

export interface Task {
  id: string
  description: string
  target_node_id: string
  status: TaskStatus
  parent_task_id: string
  proposed_additions: string[]
  proposed_removals: string[]
  created_at: string
}

export interface ProjectStatus {
  initialized: boolean
  name: string
  node_count: number
  confirmed: number
  has_tree: boolean
}
