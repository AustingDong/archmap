/**
 * ArchMap v2 API client — purpose tree operations.
 */
import type { TreeNode, Task, ProjectStatus } from '../types'

const BASE = '/api'

async function get<T>(path: string, params?: Record<string, string>): Promise<T> {
  const url = new URL(`${BASE}${path}`, window.location.origin)
  if (params) Object.entries(params).forEach(([k, v]) => v && url.searchParams.set(k, v))
  const res = await fetch(url.toString())
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || res.statusText)
  }
  return res.json()
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || res.statusText)
  }
  return res.json()
}

async function patch<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || res.statusText)
  }
  return res.json()
}

async function del<T>(path: string, params?: Record<string, string>): Promise<T> {
  const url = new URL(`${BASE}${path}`, window.location.origin)
  if (params) Object.entries(params).forEach(([k, v]) => v && url.searchParams.set(k, v))
  const res = await fetch(url.toString(), { method: 'DELETE' })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || res.statusText)
  }
  return res.json()
}

// ─── Project ─────────────────────────────────────────────────────────────────

export const initProject = (project_path: string, name?: string) =>
  post<{ ok: boolean; meta: Record<string, string> }>('/init', { project_path, name: name ?? '' })

export const getStatus = (project_path: string) =>
  get<ProjectStatus>('/status', { project_path })

// ─── Tree ────────────────────────────────────────────────────────────────────

export const getTree = (project_path: string) =>
  get<TreeNode | null>('/tree', { project_path })

export const createRoot = (project_path: string, name: string, description?: string) =>
  post<TreeNode>('/tree/root', { project_path, name, description: description ?? '' })

export const resetTree = (project_path: string) =>
  post<{ ok: boolean }>(`/tree/reset?project_path=${encodeURIComponent(project_path)}`, {})

// ─── Nodes ───────────────────────────────────────────────────────────────────

export const addNode = (project_path: string, parent_id: string, name: string, description?: string) =>
  post<TreeNode>('/node', { project_path, parent_id, name, description: description ?? '' })

export const updateNode = (project_path: string, node_id: string, data: { name?: string; description?: string; user_notes?: string }) =>
  patch<TreeNode>('/node', { project_path, node_id, ...data })

export const removeNode = (project_path: string, node_id: string) =>
  del<{ ok: boolean; removed: string }>('/node', { project_path, node_id })

export const moveNode = (project_path: string, node_id: string, new_parent_id: string) =>
  post<TreeNode>('/node/move', { project_path, node_id, new_parent_id })

// ─── Files ───────────────────────────────────────────────────────────────────

export const attachFiles = (project_path: string, node_id: string, file_paths: string[]) =>
  post<TreeNode>('/node/files', { project_path, node_id, file_paths })

export const detachFile = (project_path: string, node_id: string, file_path: string) =>
  del<TreeNode>('/node/file', { project_path, node_id, file_path })

export const suggestFiles = (project_path: string) =>
  get<{ files: string[] }>('/suggest-files', { project_path })

// ─── Tasks ───────────────────────────────────────────────────────────────────

export const listTasks = (project_path: string) =>
  get<Task[]>('/tasks', { project_path })

export const getActiveTask = (project_path: string) =>
  get<Task | null>('/task/active', { project_path })

export const createTask = (project_path: string, description: string, target_node_id?: string) =>
  post<Task>('/task', { project_path, description, target_node_id: target_node_id ?? '' })

export const completeTask = (project_path: string, task_id: string, auto_advance?: boolean) =>
  post<Task>(`/task/complete?project_path=${encodeURIComponent(project_path)}&task_id=${encodeURIComponent(task_id)}&auto_advance=${auto_advance ?? false}`, {})

export const rejectTask = (project_path: string, task_id: string, auto_advance?: boolean) =>
  post<Task>(`/task/reject?project_path=${encodeURIComponent(project_path)}&task_id=${encodeURIComponent(task_id)}&auto_advance=${auto_advance ?? false}`, {})

export const approveProposal = (project_path: string, node_id: string) =>
  post<TreeNode>(`/node/approve?project_path=${encodeURIComponent(project_path)}&node_id=${encodeURIComponent(node_id)}`, {})

export const rejectProposal = (project_path: string, node_id: string) =>
  post<{ ok: boolean; name: string }>(`/node/reject-proposal?project_path=${encodeURIComponent(project_path)}&node_id=${encodeURIComponent(node_id)}`, {})
