/**
 * ArchMap REST API client.
 * The MCP server doubles as a REST server on port 8765 via FastMCP SSE transport.
 * All endpoints accept/return JSON.
 */

const BASE = '/api'

async function call<T>(tool: string, params: Record<string, unknown> = {}): Promise<T> {
  const res = await fetch(`${BASE}/tools/${tool}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  })
  if (!res.ok) throw new Error(`ArchMap API error: ${res.status}`)
  const data = await res.json()
  if (data.error) throw new Error(data.error)
  return data as T
}

// ─── Project ──────────────────────────────────────────────────────────────────

export const projectStatus = (project_path: string) =>
  call<import('../types').ProjectStatus>('project_status', { project_path })

// ─── Architecture ─────────────────────────────────────────────────────────────

export const getArchitecture = (project_path: string) =>
  call<{ components: import('../types').Component[]; dependencies: import('../types').Dependency[] }>(
    'get_architecture', { project_path }
  )

export const listComponents = (project_path: string, layer?: string) =>
  call<import('../types').Component[]>('list_components', { project_path, layer: layer ?? '' })

export const addComponent = (project_path: string, data: Partial<import('../types').Component>) =>
  call<import('../types').Component>('add_component', { project_path, ...data })

export const updateComponent = (project_path: string, component_id: string, data: Partial<import('../types').Component>) =>
  call<import('../types').Component>('update_component', { project_path, component_id, ...data })

export const deleteComponent = (project_path: string, component_id: string) =>
  call<string>('delete_component', { project_path, component_id })

export const getDependencyGraph = (project_path: string) =>
  call<import('../types').DependencyGraph>('get_dependency_graph', { project_path })

export const addDependency = (project_path: string, from_component: string, to_component: string, label?: string, kind?: string) =>
  call<import('../types').Dependency>('add_dependency', { project_path, from_component, to_component, label, kind })

// ─── Mapping ──────────────────────────────────────────────────────────────────

export const mapFile = (project_path: string, file_path: string, component_id: string) =>
  call<import('../types').FileMapping>('map_file', { project_path, file_path, component_id })

export const listComponentFiles = (project_path: string, component_id: string) =>
  call<string[]>('list_component_files', { project_path, component_id })

export const getFileComponent = (project_path: string, file_path: string) =>
  call<import('../types').FileMapping | null>('get_file_component', { project_path, file_path })

// ─── Planning ─────────────────────────────────────────────────────────────────

export const listPlanItems = (project_path: string, component_id?: string, status?: string) =>
  call<import('../types').PlanItem[]>('list_plan_items', { project_path, component_id: component_id ?? '', status: status ?? '' })

export const createPlanItem = (project_path: string, data: Partial<import('../types').PlanItem>) =>
  call<import('../types').PlanItem>('create_plan_item', { project_path, ...data })

export const updatePlanItem = (project_path: string, item_id: string, data: Partial<import('../types').PlanItem>) =>
  call<import('../types').PlanItem>('update_plan_item', { project_path, item_id, ...data })

export const deletePlanItem = (project_path: string, item_id: string) =>
  call<string>('delete_plan_item', { project_path, item_id })

// ─── Scanner ──────────────────────────────────────────────────────────────────

export const scanProject = (project_path: string, overwrite_auto = false, depth = 2) =>
  call<{ components_created: number; components: string[]; files_mapped: number; message: string }>(
    'scan_project', { project_path, overwrite_auto, depth }
  )
