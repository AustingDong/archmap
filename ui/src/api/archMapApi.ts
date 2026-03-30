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

export const resetGraph = (project_path: string) =>
  post<{ cleared_components: number; cleared_dependencies: number; cleared_file_mappings: number }>(
    `/project/reset?project_path=${encodeURIComponent(project_path)}`, {}
  )

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

// ─── Symbol sync + search + coding context ────────────────────────────────────

export const syncFileSymbols = (project_path: string, file_path: string) =>
  post<import('../types').FileMapping>('/mappings/sync-symbols', { project_path, file_path })

export const searchSymbol = (project_path: string, q: string) =>
  get<import('../types').SymbolSearchResult[]>(`${BASE}/symbols/search`, { project_path, q })

export const getCodingContext = (project_path: string, component_id: string) =>
  get<import('../types').CodingContext>(`${BASE}/coding-context/${component_id}`, { project_path })

// ─── Architecture intelligence ────────────────────────────────────────────────

export const describeArchitecture = (project_path: string, level?: number) =>
  get<{ text: string }>(`${BASE}/architecture/describe`, {
    project_path,
    ...(level != null ? { level: String(level) } : {}),
  })

export const findRelated = (project_path: string, q: string) =>
  get<import('../types').RelatedSearchResult>(`${BASE}/architecture/search`, { project_path, q })

// ─── Multi-level graph ────────────────────────────────────────────────────────

export const getDomainMap = (project_path: string) =>
  get<import('../types').DomainMap>(`${BASE}/graph/domain-map`, { project_path })

export const describeNode = (project_path: string, node_id: string, show_files = false) =>
  get<import('../types').NodeDetail>(`${BASE}/graph/node/${node_id}`, {
    project_path, show_files: String(show_files),
  })

export const listChildren = (project_path: string, parent_id: string) =>
  get<import('../types').Component[]>(`${BASE}/graph/children/${parent_id}`, { project_path })

export const getWorkContext = (project_path: string, node_id: string, task = '') =>
  get<import('../types').WorkContext>(`${BASE}/work-context/${node_id}`, { project_path, task })

// ─── Contracts ────────────────────────────────────────────────────────────────

export const listContracts = (project_path: string, node_level?: number) =>
  get<import('../types').Contract[]>(`${BASE}/contracts`, {
    project_path,
    ...(node_level != null ? { node_level: String(node_level) } : {}),
  })

export const getContract = (project_path: string, node_id: string) =>
  get<import('../types').Contract>(`${BASE}/contracts/${node_id}`, { project_path })

export const declareContract = (project_path: string, node_id: string, data: Partial<import('../types').Contract>) =>
  post<import('../types').Contract>('/contracts', { project_path, node_id, ...data })

export const checkContractBreak = (
  project_path: string,
  node_id: string,
  operation_name: string,
  new_input_type = '',
  new_output_type = '',
) =>
  get<{ breaking: boolean; reason: string; callers: unknown[] }>(`${BASE}/contracts/${node_id}/check-break`, {
    project_path, operation_name, new_input_type, new_output_type,
  })

// ─── Dependency annotation ────────────────────────────────────────────────────

export const annotateDependency = (
  project_path: string,
  dep_id: string,
  data: Partial<import('../types').Dependency>,
) =>
  patch<import('../types').Dependency>(`${BASE}/dependencies/${dep_id}/annotate`, {}, {
    project_path, ...data,
  })

// ─── Public API management ────────────────────────────────────────────────────

export const promoteToContract = (project_path: string, component_id: string, symbol_names: string[]) =>
  post<import('../types').Component>(`/components/${component_id}/promote`, { project_path, symbol_names })

// ─── File remapping ───────────────────────────────────────────────────────────

export const remapFiles = (project_path: string, file_paths: string[], target_component_id: string) =>
  post<{ remapped: string[]; not_found: string[]; target: string }>('/mappings/remap', {
    project_path, file_paths, target_component_id,
  })

// ─── Health data ──────────────────────────────────────────────────────────────

export const getCycles = (project_path: string) =>
  get<{
    cycle_count: number
    cycles: Array<{
      component_id: string
      component_name: string
      layer: string
      cycles_with: Array<{ component_id: string; component_name: string; layer: string }>
    }>
  }>(`${BASE}/cycles`, { project_path })

export const getValidate = (project_path: string) =>
  get<{
    valid: boolean
    violations: Array<{
      rule_id: string
      rule_type: string
      message: string
      from_component: string
      from_name: string
      to_component: string
      to_name: string
    }>
  }>(`${BASE}/validate`, { project_path })

export const getCodeQuality = (project_path: string, component_id: string) =>
  get<{
    component_id: string
    score: number
    error_count: number
    warning_count: number
    issue_count: number
    summary: string
    hotspots: string[]
    fix_priority: string[]
    files: Array<{ file_path: string; lines: number; complexity: number; lint_issues: unknown[]; format_ok: boolean }>
  }>(`${BASE}/quality/${component_id}`, { project_path })

// ─── Progressive knowledge ────────────────────────────────────────────────────

export type CompletenessScore = {
  score: number
  component_id: string
  name: string
  level?: number
  layer?: string
  missing: string[]
}

export const getCompleteness = (project_path: string) =>
  get<CompletenessScore[]>(`${BASE}/completeness`, { project_path })

export const getCompletenessForComponent = (project_path: string, component_id: string) =>
  get<CompletenessScore & { signals: Record<string, boolean | null> }>(
    `${BASE}/completeness/${component_id}`, { project_path }
  )

export const drillInto = (project_path: string, task: string, start_id = '') =>
  get<{
    path: Array<{ id: string; name: string; level: number; layer: string; score: number; why: string }>
    suggested_component: { id: string; name: string; level: number; layer: string }
    alternatives: Array<{ id: string; name: string; level: number; layer: string; score: number }>
    query_tokens: string[]
  }>(`${BASE}/drill-into`, { project_path, task, start_id })

export const getKnowledgeGaps = (project_path: string, min_score = 70) =>
  get<{
    total_components: number
    below_threshold: number
    threshold: number
    gaps: CompletenessScore[]
    unmapped_source_files: string[]
    stale_symbols: Array<{ file_path: string; issue: string }>
  }>(`${BASE}/knowledge-gaps`, { project_path, min_score: String(min_score) })

// ─── Migration ────────────────────────────────────────────────────────────────

export const migrateMultilevel = (project_path: string) =>
  post<{
    ok: boolean
    created_nodes: string[]
    updated_nodes: string[]
    annotated_edges: string[]
    contracts_declared: string[]
    summary: string
  }>('/migrate/multilevel', { project_path })
