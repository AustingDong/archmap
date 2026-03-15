/**
 * ArchMap REST API client — uses the new /api/* REST routes.
 */

const BASE = '/api'

async function get<T>(path: string, params?: Record<string, string>): Promise<T> {
  const url = new URL(path, window.location.origin)
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

async function patch<T>(path: string, params: Record<string, string>, body: unknown): Promise<T> {
  const url = new URL(path, window.location.origin)
  Object.entries(params).forEach(([k, v]) => v && url.searchParams.set(k, v))
  const res = await fetch(url.toString(), {
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
  const url = new URL(path, window.location.origin)
  if (params) Object.entries(params).forEach(([k, v]) => v && url.searchParams.set(k, v))
  const res = await fetch(url.toString(), { method: 'DELETE' })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || res.statusText)
  }
  return res.json()
}

// ─── Project ──────────────────────────────────────────────────────────────────

export const initProject = (project_path: string, name?: string) =>
  post<import('../types').ProjectStatus>('/project/init', { project_path, name: name ?? '' })

export const projectStatus = (project_path: string) =>
  get<import('../types').ProjectStatus>(`${BASE}/project/status`, { project_path })

// ─── Architecture ─────────────────────────────────────────────────────────────

export const getArchitecture = (project_path: string) =>
  get<{ components: import('../types').Component[]; dependencies: import('../types').Dependency[] }>(
    `${BASE}/architecture`, { project_path }
  )

export const listComponents = (project_path: string, layer?: string) =>
  get<import('../types').Component[]>(`${BASE}/components`, { project_path, layer: layer ?? '' })

export const addComponent = (project_path: string, data: Partial<import('../types').Component>) =>
  post<import('../types').Component>('/components', { project_path, ...data })

export const updateComponent = (project_path: string, component_id: string, data: Partial<import('../types').Component>) =>
  patch<import('../types').Component>(`${BASE}/components/${component_id}`, { project_path }, data)

export const deleteComponent = (project_path: string, component_id: string) =>
  del<string>(`${BASE}/components/${component_id}`, { project_path })

export const getDependencyGraph = (project_path: string) =>
  get<import('../types').DependencyGraph>(`${BASE}/graph`, { project_path })

export const addDependency = (project_path: string, from_component: string, to_component: string, label?: string, kind?: string) =>
  post<import('../types').Dependency>('/dependencies', { project_path, from_component, to_component, label: label ?? 'uses', kind: kind ?? 'runtime' })

export const removeDependency = (project_path: string, dep_id: string) =>
  del<string>(`${BASE}/dependencies/${dep_id}`, { project_path })

export const inferDependencies = (project_path: string, overwrite_auto = false) =>
  post<{ added: number; skipped: number; unmapped: string[]; dependencies: import('../types').Dependency[] }>(
    `/infer/dependencies?project_path=${encodeURIComponent(project_path)}&overwrite_auto=${overwrite_auto}`, {}
  )

export const confirmDependency = (project_path: string, dep_id: string) =>
  post<import('../types').Dependency>(
    `/dependencies/${dep_id}/confirm?project_path=${encodeURIComponent(project_path)}`, {}
  )

// ─── Mappings ─────────────────────────────────────────────────────────────────

export const listAllMappings = (project_path: string) =>
  get<import('../types').FileMapping[]>(`${BASE}/mappings`, { project_path })

export const listComponentFiles = (project_path: string, component_id: string) =>
  get<import('../types').FileMapping[]>(`${BASE}/mappings/component/${component_id}`, { project_path })

export const mapFile = (project_path: string, file_path: string, component_id: string) =>
  post<import('../types').FileMapping>('/mappings', { project_path, file_path, component_id })

export const unmapFile = (project_path: string, file_path: string) =>
  del<string>(`${BASE}/mappings`, { project_path, file_path })

export const annotateFile = (
  project_path: string,
  file_path: string,
  data: { description?: string; functions?: string[]; language?: string },
) =>
  patch<import('../types').FileMapping>(`${BASE}/mappings`, {}, { project_path, file_path, ...data })

// ─── Planning ─────────────────────────────────────────────────────────────────

export const listPlanItems = (project_path: string, component_id?: string, status?: string, priority?: string) =>
  get<import('../types').PlanItem[]>(`${BASE}/plan`, {
    project_path,
    component_id: component_id ?? '',
    status: status ?? '',
    priority: priority ?? '',
  })

export const createPlanItem = (project_path: string, data: Partial<import('../types').PlanItem>) =>
  post<import('../types').PlanItem>('/plan', { project_path, ...data })

export const updatePlanItem = (project_path: string, item_id: string, data: Partial<import('../types').PlanItem>) =>
  patch<import('../types').PlanItem>(`${BASE}/plan/${item_id}`, { project_path }, data)

export const deletePlanItem = (project_path: string, item_id: string) =>
  del<string>(`${BASE}/plan/${item_id}`, { project_path })

// ─── Scanner ──────────────────────────────────────────────────────────────────

export const scanProject = (project_path: string, overwrite_auto = false, depth = 2) =>
  post<{ components_created: number; components: string[]; files_mapped: number; message: string }>(
    '/scan', { project_path, overwrite_auto, depth }
  )

// ─── Metrics ──────────────────────────────────────────────────────────────────

export const getComponentMetrics = (project_path: string, component_id: string) =>
  get<import('../types').ComponentMetrics>(
    `${BASE}/metrics/component/${component_id}`, { project_path }
  )

export const getComponentImpact = (project_path: string, component_id: string) =>
  get<import('../types').ComponentImpact>(
    `${BASE}/impact/${component_id}`, { project_path }
  )

// ─── File content + symbol extraction ─────────────────────────────────────────

export const getFileContent = (project_path: string, file_path: string) =>
  get<import('../types').FileContent>(`${BASE}/file`, { project_path, file_path })

export const getFileSymbol = (project_path: string, file_path: string, symbol: string) =>
  get<import('../types').SymbolExtract>(`${BASE}/file/symbol`, { project_path, file_path, symbol })
