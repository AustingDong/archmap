import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { useStore } from './store'
import { t } from './i18n'
import type { TreeNode, Task } from './types'
import {
  getStatus, getTree, initProject, createRoot, resetTree,
  addNode, updateNode, removeNode,
  attachFiles, suggestFiles,
  listTasks, createTask, completeTask, rejectTask,
  approveProposal, rejectProposal,
} from './api/archMapApi'

// ─── Status config ──────────────────────────────────────────────────────────

const STATUS_CFG: Record<string, { dot: string; css: string }> = {
  confirmed:   { dot: '\u25cf', css: 'confirmed' },
  proposed:    { dot: '\u25cc', css: 'proposed' },
  removing:    { dot: '\u25cf', css: 'removing' },
}

// ─── Helpers ────────────────────────────────────────────────────────────────

/** Count nodes by status in a tree */
function countNodes(node: TreeNode): { total: number; confirmed: number; proposed: number } {
  let total = 1, confirmed = 0, proposed = 0
  if (node.status === 'confirmed') confirmed++
  else if (node.status === 'proposed' || node.status === 'removing') proposed++
  for (const c of node.children) {
    const sub = countNodes(c)
    total += sub.total
    confirmed += sub.confirmed
    proposed += sub.proposed
  }
  return { total, confirmed, proposed }
}

/** Check if a node or any descendant matches the search query */
function nodeMatchesFilter(node: TreeNode, query: string): boolean {
  if (node.name.toLowerCase().includes(query)) return true
  return node.children.some(c => nodeMatchesFilter(c, query))
}

/** Find a node name by id in the tree */
function findNodeName(node: TreeNode, id: string): string | null {
  if (node.id === id) return node.name
  for (const c of node.children) {
    const found = findNodeName(c, id)
    if (found) return found
  }
  return null
}

// ─── Progress Ring ──────────────────────────────────────────────────────────

function ProgressRing({ confirmed, total, locale }: { confirmed: number; total: number; locale: string }) {
  const size = 64
  const strokeWidth = 4
  const radius = (size - strokeWidth) / 2
  const circumference = 2 * Math.PI * radius
  const ratio = total > 0 ? confirmed / total : 0
  const offset = circumference * (1 - ratio)
  const pct = total > 0 ? Math.round(ratio * 100) : 0

  return (
    <div className="progress-ring-wrapper">
      <svg width={size} height={size}>
        <circle className="progress-ring-bg" cx={size / 2} cy={size / 2} r={radius} />
        <circle
          className="progress-ring-fill"
          cx={size / 2} cy={size / 2} r={radius}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
        />
      </svg>
      <span className="progress-ring-text">{pct}%</span>
      <span className="progress-ring-label">
        {t(locale as any, 'progress.confirmed_of_total', { confirmed: String(confirmed), total: String(total) })}
      </span>
    </div>
  )
}

// ─── Hover Card ─────────────────────────────────────────────────────────────

function NodeHoverCard({ node, locale }: { node: TreeNode; locale: string }) {
  const created = node.created_at ? new Date(node.created_at).toLocaleDateString() : '—'
  return (
    <div className="node-hover-card">
      <div className="hc-row">
        <span className="hc-label">{t(locale as any, 'hover.status')}</span>
        <span className="hc-value">{t(locale as any, `status.${node.status}`)}</span>
      </div>
      {node.description && (
        <div className="hc-row">
          <span className="hc-label">{t(locale as any, 'hover.description')}</span>
          <span className="hc-value">{node.description}</span>
        </div>
      )}
      <div className="hc-row">
        <span className="hc-label">{t(locale as any, 'hover.files')}</span>
        <span className="hc-value">{node.files.length}</span>
      </div>
      <div className="hc-row">
        <span className="hc-label">{t(locale as any, 'hover.created')}</span>
        <span className="hc-value">{created}</span>
      </div>
    </div>
  )
}

// ─── Tree Node Component ────────────────────────────────────────────────────

function TreeNodeView({
  node, depth, projectPath, onReload, expandAll, filterQuery,
}: {
  node: TreeNode; depth: number; projectPath: string; onReload: () => void
  expandAll: boolean | null; filterQuery: string
}) {
  const [expanded, setExpanded] = useState(depth < 2)
  const [adding, setAdding] = useState(false)
  const [newName, setNewName] = useState('')
  const [newDesc, setNewDesc] = useState('')
  const [editing, setEditing] = useState(false)
  const [editName, setEditName] = useState(node.name)
  const [editDesc, setEditDesc] = useState(node.description)
  const [editNotes, setEditNotes] = useState(node.user_notes)
  const [showFiles, setShowFiles] = useState(false)
  const [unmapped, setUnmapped] = useState<string[]>([])
  const [hoverVisible, setHoverVisible] = useState(false)
  const hoverTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const { toast, locale } = useStore()

  const cfg = STATUS_CFG[node.status] || STATUS_CFG.confirmed
  const isProposal = node.status === 'proposed' || node.status === 'removing'
  const hasChildren = node.children.length > 0
  const hasFiles = node.files.length > 0
  const canExpand = hasChildren || hasFiles

  // Respond to expand/collapse all
  useEffect(() => {
    if (expandAll === true) setExpanded(true)
    else if (expandAll === false) setExpanded(false)
  }, [expandAll])

  // Auto-expand when filter matches children
  useEffect(() => {
    if (filterQuery && hasChildren) {
      const childMatch = node.children.some(c => nodeMatchesFilter(c, filterQuery))
      if (childMatch) setExpanded(true)
    }
  }, [filterQuery]) // eslint-disable-line

  const handleHoverEnter = () => {
    hoverTimer.current = setTimeout(() => setHoverVisible(true), 500)
  }
  const handleHoverLeave = () => {
    if (hoverTimer.current) clearTimeout(hoverTimer.current)
    setHoverVisible(false)
  }

  const handleAdd = async () => {
    if (!newName.trim()) return
    try {
      await addNode(projectPath, node.id, newName.trim(), newDesc.trim())
      setNewName(''); setNewDesc(''); setAdding(false); setExpanded(true)
      onReload()
    } catch (e: any) { toast('error', e.message) }
  }


  const handleRemove = async () => {
    if (!confirm(t(locale, 'node.remove_confirm', { name: node.name }))) return
    try { await removeNode(projectPath, node.id); onReload() }
    catch (e: any) { toast('error', e.message) }
  }

  const handleSave = async () => {
    try {
      await updateNode(projectPath, node.id, { name: editName, description: editDesc, user_notes: editNotes })
      setEditing(false); onReload()
    } catch (e: any) { toast('error', e.message) }
  }

  const handleApprove = async () => {
    try { await approveProposal(projectPath, node.id); onReload(); toast('success', t(locale, 'toast.approved', { name: node.name })) }
    catch (e: any) { toast('error', e.message) }
  }

  const handleReject = async () => {
    try { await rejectProposal(projectPath, node.id); onReload(); toast('info', t(locale, 'toast.rejected', { name: node.name })) }
    catch (e: any) { toast('error', e.message) }
  }

  const handleSuggestFiles = async () => {
    try { const r = await suggestFiles(projectPath); setUnmapped(r.files); setShowFiles(true) }
    catch (e: any) { toast('error', e.message) }
  }

  const handleAttach = async (fp: string) => {
    try {
      await attachFiles(projectPath, node.id, [fp])
      setUnmapped(prev => prev.filter(f => f !== fp)); onReload()
    } catch (e: any) { toast('error', e.message) }
  }

  // Filter: hide nodes that don't match
  if (filterQuery && !nodeMatchesFilter(node, filterQuery)) {
    return null
  }

  return (
    <div className="tree-node">
      {/* Node row */}
      <div className={`node-row ${depth === 0 ? 'root-node' : ''} ${isProposal ? 'proposal' : ''}`}>
        {/* Expand toggle */}
        <button
          className={`node-expand ${canExpand ? '' : 'muted'}`}
          onClick={() => canExpand && setExpanded(!expanded)}
        >
          {canExpand ? (expanded ? '\u25be' : '\u25b8') : '\u00b7'}
        </button>

        {/* Status dot */}
        <span
          className={`status-dot ${cfg.css}`}
          title={t(locale, `status.${node.status}`)}
          onClick={undefined}
        >
          {cfg.dot}
        </span>

        {/* Content */}
        <div style={{ flex: 1, minWidth: 0 }}>
          {editing ? (
            <div className="edit-form">
              <input value={editName} onChange={e => setEditName(e.target.value)}
                style={{ fontWeight: 600 }} autoFocus />
              <input value={editDesc} onChange={e => setEditDesc(e.target.value)}
                placeholder={t(locale, 'node.description')} />
              <input value={editNotes} onChange={e => setEditNotes(e.target.value)}
                placeholder={t(locale, 'node.your_notes')} />
              <div className="actions">
                <button className="btn btn-sm" onClick={handleSave}>{t(locale, 'node.save')}</button>
                <button className="btn btn-sm btn-ghost" onClick={() => setEditing(false)}>{t(locale, 'node.cancel')}</button>
              </div>
            </div>
          ) : (
            <div
              className="node-hover-anchor"
              onMouseEnter={handleHoverEnter}
              onMouseLeave={handleHoverLeave}
            >
              <span
                className="node-name"
                style={{ textDecoration: node.status === 'removing' ? 'line-through' : 'none' }}
                onClick={() => { setEditName(node.name); setEditDesc(node.description); setEditNotes(node.user_notes); setEditing(true) }}
              >
                {node.name}
              </span>
              {node.description && (
                <span className="node-desc" style={{ textDecoration: node.status === 'removing' ? 'line-through' : 'none' }}>
                  &mdash; {node.description}
                </span>
              )}
              {hasFiles && !expanded && (
                <span className="badge grey" style={{ marginLeft: 8 }}>
                  {node.files.length} {t(locale, 'tree.files')}
                </span>
              )}
              {node.user_notes && (
                <div className="node-notes">{node.user_notes}</div>
              )}
              {hoverVisible && !editing && (
                <NodeHoverCard node={node} locale={locale} />
              )}
            </div>
          )}
        </div>

        {/* Actions */}
        {!editing && isProposal && (
          <div className="proposal-actions">
            <button className="btn btn-sm btn-approve" onClick={handleApprove}>
              {node.status === 'proposed' ? t(locale, 'node.approve') : t(locale, 'node.approve_del')}
            </button>
            <button className="btn btn-sm btn-reject" onClick={handleReject}>
              {t(locale, 'node.reject')}
            </button>
          </div>
        )}
        {!editing && !isProposal && (
          <div className="node-actions">
            <button className="btn-icon" onClick={() => setAdding(!adding)} title={t(locale, 'node.add_child')}>+</button>
            <button className="btn-icon" onClick={handleSuggestFiles} title={t(locale, 'node.attach')}>
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M14 5L7.5 11.5a3.5 3.5 0 01-5-5L9 0l4 4-6.5 6.5a1.5 1.5 0 01-2-2L11 2"/>
              </svg>
            </button>
            {depth > 0 && (
              <button className="btn-icon danger" onClick={handleRemove} title={t(locale, 'node.remove')}>
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M4 4l8 8M12 4l-8 8"/>
                </svg>
              </button>
            )}
          </div>
        )}
      </div>

      {/* Add child form */}
      {adding && (
        <div className="add-form">
          <input value={newName} onChange={e => setNewName(e.target.value)}
            placeholder={t(locale, 'node.purpose_name')}
            onKeyDown={e => e.key === 'Enter' && handleAdd()} autoFocus />
          <input value={newDesc} onChange={e => setNewDesc(e.target.value)}
            placeholder={t(locale, 'node.what_it_does')}
            onKeyDown={e => e.key === 'Enter' && handleAdd()} />
          <button className="btn btn-sm" onClick={handleAdd}>{t(locale, 'node.save')}</button>
          <button className="btn btn-sm btn-ghost" onClick={() => { setAdding(false); setNewName(''); setNewDesc('') }}>
            {t(locale, 'node.cancel')}
          </button>
        </div>
      )}

      {/* File picker */}
      {showFiles && (
        <div className="file-picker">
          <div className="file-picker-header">
            <span>{t(locale, 'node.unmapped_files')} ({unmapped.length})</span>
            <button className="btn-icon" onClick={() => setShowFiles(false)}>
              <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M4 4l8 8M12 4l-8 8"/>
              </svg>
            </button>
          </div>
          {unmapped.length === 0 ? (
            <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{t(locale, 'node.all_mapped')}</div>
          ) : unmapped.map(f => (
            <div key={f} className="file-picker-item">
              <span>{f}</span>
              <button className="btn btn-sm" onClick={() => handleAttach(f)}>{t(locale, 'node.attach')}</button>
            </div>
          ))}
        </div>
      )}

      {/* Children + files */}
      {expanded && (hasChildren || hasFiles) && (
        <div className="tree-children tree-children-animated">
          {node.children.map(child => (
            <TreeNodeView
              key={child.id} node={child} depth={depth + 1}
              projectPath={projectPath} onReload={onReload}
              expandAll={expandAll} filterQuery={filterQuery}
            />
          ))}
          {hasFiles && (
            <div className="node-files">
              {node.files.map(f => (
                <div key={f} className="node-file">{f}</div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}


// ─── Task Panel ─────────────────────────────────────────────────────────────

function TaskPanel({ projectPath, tasks, onReload, tree }: {
  projectPath: string; tasks: Task[]; onReload: () => void; tree: TreeNode | null
}) {
  const [newDesc, setNewDesc] = useState('')
  const { toast, locale } = useStore()

  const handleCreate = async () => {
    if (!newDesc.trim()) return
    try {
      await createTask(projectPath, newDesc.trim())
      setNewDesc('')
      onReload()
    } catch (e: any) { toast('error', e.message) }
  }

  const handleComplete = async (id: string) => {
    try { await completeTask(projectPath, id, true); onReload() }
    catch (e: any) { toast('error', e.message) }
  }

  const handleReject = async (id: string) => {
    try { await rejectTask(projectPath, id, true); onReload() }
    catch (e: any) { toast('error', e.message) }
  }

  const active = tasks.filter(t => t.status === 'active')
  const queued = tasks.filter(t => t.status === 'queued')
  const done = tasks.filter(t => t.status === 'done' || t.status === 'rejected')

  const TASK_ICON: Record<string, string> = { active: '\u25cf', queued: '\u25cb', done: '\u2713', rejected: '\u2717' }

  // Progress ring data
  const counts = tree ? countNodes(tree) : { total: 0, confirmed: 0, proposed: 0 }

  return (
    <>
      {/* Progress ring */}
      {tree && (
        <>
          <div className="card-title">{t(locale, 'progress.title')}</div>
          <ProgressRing confirmed={counts.confirmed} total={counts.total} locale={locale} />
          <div className="divider" />
        </>
      )}

      <div className="card-title">{t(locale, 'task.title')}</div>

      {/* Create task */}
      <div className="task-input-group">
        <input
          value={newDesc} onChange={e => setNewDesc(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleCreate()}
          placeholder={t(locale, 'task.placeholder')}
        />
        <button className="btn btn-sm" onClick={handleCreate}>{t(locale, 'task.add')}</button>
      </div>

      {/* Task list */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 8 }}>
        {[...active, ...queued, ...done].map(task => (
          <div key={task.id} className={`task-item task-${task.status}`}>
            <span className={`task-status ${task.status}`} title={t(locale, `task.${task.status === 'done' ? 'completed' : task.status}`)}>
              {TASK_ICON[task.status]}
            </span>
            <span className={`task-desc ${task.status === 'done' ? 'dimmed' : ''} ${task.status === 'rejected' ? 'struck' : ''}`}>
              {task.description}
            </span>
            {task.status === 'active' && (
              <div className="task-actions">
                <button className="btn btn-sm btn-approve" onClick={() => handleComplete(task.id)}>
                  {t(locale, 'task.done')}
                </button>
                <button className="btn btn-sm btn-reject" onClick={() => handleReject(task.id)}>
                  {t(locale, 'task.reject')}
                </button>
              </div>
            )}
          </div>
        ))}

        {tasks.length === 0 && (
          <div style={{ fontSize: 12, color: 'var(--text-muted)', textAlign: 'center', padding: '16px 0' }}>
            {t(locale, 'task.empty')}
          </div>
        )}
      </div>
    </>
  )
}


// ─── App ────────────────────────────────────────────────────────────────────

export default function App() {
  const { projectPath, setProjectPath, theme, setTheme, locale, setLocale, toasts, dismissToast, toast } = useStore()
  const [input, setInput] = useState(projectPath)
  const [tree, setTree] = useState<TreeNode | null>(null)
  const [tasks, setTasks] = useState<Task[]>([])
  const [loading, setLoading] = useState(false)
  const [rootName, setRootName] = useState('')
  const [rootDesc, setRootDesc] = useState('')
  const [expandAll, setExpandAll] = useState<boolean | null>(null)
  const [filterQuery, setFilterQuery] = useState('')

  const load = useCallback(async (path: string) => {
    if (!path.trim()) return
    setLoading(true)
    try {
      const status = await getStatus(path.trim())
      if (!status.initialized) await initProject(path.trim())
      setProjectPath(path.trim())
      const [t, ts] = await Promise.all([getTree(path.trim()), listTasks(path.trim())])
      setTree(t)
      setTasks(ts)
    } catch (e: any) { toast('error', e.message) }
    finally { setLoading(false) }
  }, [setProjectPath, toast])

  const reload = useCallback(() => { if (projectPath) load(projectPath) }, [projectPath, load])

  useEffect(() => { if (projectPath) load(projectPath) }, []) // eslint-disable-line

  const handleCreateRoot = async () => {
    if (!rootName.trim()) return
    try {
      await createRoot(projectPath, rootName.trim(), rootDesc.trim())
      setRootName(''); setRootDesc(''); reload()
    } catch (e: any) { toast('error', e.message) }
  }

  const handleReset = async () => {
    if (!confirm(t(locale, 'tree.reset_confirm'))) return
    try { await resetTree(projectPath); setTree(null); setTasks([]); toast('info', t(locale, 'toast.tree_reset')) }
    catch (e: any) { toast('error', e.message) }
  }

  // Stats
  const stats = useMemo(() => tree ? countNodes(tree) : null, [tree])

  // Active task
  const activeTask = useMemo(() => tasks.find(t => t.status === 'active') || null, [tasks])
  const activeTaskTargetName = useMemo(() => {
    if (!activeTask || !tree || !activeTask.target_node_id) return null
    return findNodeName(tree, activeTask.target_node_id)
  }, [activeTask, tree])

  // Expand/collapse all toggle
  const handleExpandAll = () => { setExpandAll(true); setTimeout(() => setExpandAll(null), 100) }
  const handleCollapseAll = () => { setExpandAll(false); setTimeout(() => setExpandAll(null), 100) }

  // Sun/Moon SVG icons
  const SunIcon = () => (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <circle cx="8" cy="8" r="3"/>
      <path d="M8 1v2M8 13v2M1 8h2M13 8h2M3.05 3.05l1.41 1.41M11.54 11.54l1.41 1.41M3.05 12.95l1.41-1.41M11.54 4.46l1.41-1.41"/>
    </svg>
  )
  const MoonIcon = () => (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M13.5 8.5a5.5 5.5 0 01-8-5 5.5 5.5 0 108 5z"/>
    </svg>
  )

  const normalizedFilter = filterQuery.toLowerCase()

  return (
    <div className="app-layout">
      {/* Header */}
      <header className="app-header">
        <div className="logo">
          <div className="logo-icon">A</div>
          <span>ArchMap</span>
        </div>

        <div className="path-input-group">
          <input
            value={input} onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && load(input)}
            placeholder={t(locale, 'app.enter_path')}
            style={{ flex: 1, fontSize: 12 }}
          />
          <button className="btn btn-sm" onClick={() => load(input)} disabled={loading}>
            {loading ? t(locale, 'app.loading') : t(locale, 'app.load')}
          </button>
        </div>

        <div className="header-controls">
          <select
            className="lang-select"
            value={locale}
            onChange={e => setLocale(e.target.value as any)}
          >
            <option value="en">EN</option>
            <option value="cn">{'\u4e2d\u6587'}</option>
          </select>

          <button
            className="toggle-btn"
            onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
            title={theme === 'dark' ? t(locale, 'app.theme_light') : t(locale, 'app.theme_dark')}
          >
            {theme === 'dark' ? <SunIcon /> : <MoonIcon />}
          </button>
        </div>
      </header>

      {/* Stats bar */}
      {stats && (
        <div className="stats-bar">
          <span className="stat-pill total">
            <span className="stat-dot" />
            {stats.total} {t(locale, 'stats.total')}
          </span>
          <span className="stat-pill confirmed">
            <span className="stat-dot" />
            {stats.confirmed} {t(locale, 'stats.confirmed')}
          </span>
          <span className="stat-pill proposed">
            <span className="stat-dot" />
            {stats.proposed} {t(locale, 'stats.proposed')}
          </span>
        </div>
      )}

      {/* Body */}
      <div className="app-body">
        {/* Main: Tree */}
        <main className="main-panel">
          {/* No project loaded */}
          {!projectPath && !loading && (
            <div className="empty-state" style={{ minHeight: '60vh' }}>
              <div className="icon">
                <svg width="48" height="48" viewBox="0 0 48 48" fill="none" stroke="currentColor" strokeWidth="1.5" opacity="0.4">
                  <path d="M24 4v16M16 12l8-8 8 8M8 24h32M12 32l12 12 12-12"/>
                </svg>
              </div>
              <div className="title">{t(locale, 'app.title')}</div>
              <div className="desc">{t(locale, 'app.no_project')}</div>
            </div>
          )}

          {/* Empty tree */}
          {projectPath && !tree && !loading && (
            <div className="card" style={{ maxWidth: 520, margin: '60px auto', textAlign: 'center' }}>
              <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 4 }}>
                {t(locale, 'tree.empty_title')}
              </div>
              <div style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 16 }}>
                {t(locale, 'tree.empty_desc')}
              </div>
              <div style={{ display: 'flex', gap: 8, justifyContent: 'center', flexWrap: 'wrap' }}>
                <input value={rootName} onChange={e => setRootName(e.target.value)}
                  placeholder={t(locale, 'tree.project_name')} style={{ width: 160 }}
                  onKeyDown={e => e.key === 'Enter' && handleCreateRoot()} />
                <input value={rootDesc} onChange={e => setRootDesc(e.target.value)}
                  placeholder={t(locale, 'tree.one_line')} style={{ width: 260 }}
                  onKeyDown={e => e.key === 'Enter' && handleCreateRoot()} />
                <button className="btn btn-sm" onClick={handleCreateRoot}>{t(locale, 'tree.create_root')}</button>
              </div>
            </div>
          )}

          {/* Tree */}
          {tree && (
            <div style={{ maxWidth: 800 }}>
              {/* Active task banner */}
              {activeTask && (
                <div className="active-task-banner">
                  <div className="atb-icon">{'\u25b6'}</div>
                  <div className="atb-body">
                    <div className="atb-label">{t(locale, 'task.active_banner')}</div>
                    <div className="atb-desc">{activeTask.description}</div>
                    {activeTaskTargetName && (
                      <div className="atb-target">{t(locale, 'task.target_node')}: {activeTaskTargetName}</div>
                    )}
                  </div>
                </div>
              )}

              {/* Tree toolbar: search + expand/collapse */}
              <div className="tree-toolbar">
                <input
                  className="search-input"
                  value={filterQuery}
                  onChange={e => setFilterQuery(e.target.value)}
                  placeholder={t(locale, 'tree.search_placeholder')}
                />
                <button className="btn btn-sm btn-ghost" onClick={handleExpandAll}>
                  {t(locale, 'tree.expand_all')}
                </button>
                <button className="btn btn-sm btn-ghost" onClick={handleCollapseAll}>
                  {t(locale, 'tree.collapse_all')}
                </button>
              </div>

              <TreeNodeView
                node={tree} depth={0} projectPath={projectPath} onReload={reload}
                expandAll={expandAll} filterQuery={normalizedFilter}
              />

              <div style={{ marginTop: 24, display: 'flex', justifyContent: 'flex-end' }}>
                <button className="btn btn-sm btn-ghost" onClick={handleReset} style={{ fontSize: 11, opacity: 0.6 }}>
                  {t(locale, 'tree.reset')}
                </button>
              </div>
            </div>
          )}
        </main>

        {/* Sidebar: Tasks */}
        {projectPath && (
          <aside className="side-panel">
            <TaskPanel projectPath={projectPath} tasks={tasks} onReload={reload} tree={tree} />
          </aside>
        )}
      </div>

      {/* Toasts */}
      <div className="toast-container">
        {toasts.map(t => (
          <div key={t.id} className={`toast ${t.type}`} onClick={() => dismissToast(t.id)}>
            {t.message}
          </div>
        ))}
      </div>
    </div>
  )
}
