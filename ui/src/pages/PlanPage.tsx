import React, { useEffect, useState, useCallback } from 'react'
import { Plus, Trash2, X, ClipboardList, ChevronDown } from 'lucide-react'
import { useStore } from '../store'
import { listPlanItems, createPlanItem, updatePlanItem, deletePlanItem, listComponents } from '../api/archMapApi'
import type { PlanItem, PlanStatus, PlanPriority, Component } from '../types'

const COLUMNS: { status: PlanStatus; label: string; color: string }[] = [
  { status: 'todo',        label: 'To Do',       color: '#64748b' },
  { status: 'in_progress', label: 'In Progress',  color: '#4f7cff' },
  { status: 'blocked',     label: 'Blocked',      color: '#f59e0b' },
  { status: 'done',        label: 'Done',         color: '#22c55e' },
]

const PRIORITY_COLOR: Record<string, string> = {
  low: '#64748b', medium: '#4f7cff', high: '#f59e0b', critical: '#ef4444',
}

export default function PlanPage() {
  const { projectPath, toast } = useStore()
  const [items, setItems] = useState<PlanItem[]>([])
  const [components, setComponents] = useState<Component[]>([])
  const [loading, setLoading] = useState(false)
  const [showAdd, setShowAdd] = useState<PlanStatus | null>(null)
  const [selected, setSelected] = useState<PlanItem | null>(null)

  const load = useCallback(async () => {
    if (!projectPath) return
    setLoading(true)
    try {
      const [its, comps] = await Promise.all([
        listPlanItems(projectPath),
        listComponents(projectPath),
      ])
      setItems(its)
      setComponents(comps)
    } catch (e: any) { toast('error', e.message) }
    finally { setLoading(false) }
  }, [projectPath])

  useEffect(() => { load() }, [load])

  // Live updates via SSE — fall back to 5s polling if EventSource unavailable
  useEffect(() => {
    if (!projectPath) return

    const refresh = async () => {
      try {
        const its = await listPlanItems(projectPath)
        setItems(prev => {
          const openId = selected?.id
          return its.map(s => s.id === openId ? (prev.find(p => p.id === openId) ?? s) : s)
        })
      } catch { /* silent */ }
    }

    let es: EventSource | null = null
    let fallback: ReturnType<typeof setInterval> | null = null

    if (typeof EventSource !== 'undefined') {
      es = new EventSource('/api/events')
      es.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data)
          if (msg.event === 'plan_changed') refresh()
        } catch { /* ignore */ }
      }
      es.onerror = () => {
        // SSE dropped — switch to polling until next mount
        es?.close()
        es = null
        fallback = setInterval(refresh, 5000)
      }
    } else {
      fallback = setInterval(refresh, 5000)
    }

    return () => {
      es?.close()
      if (fallback) clearInterval(fallback)
    }
  }, [projectPath, selected?.id])

  const moveItem = async (item: PlanItem, newStatus: PlanStatus) => {
    try {
      await updatePlanItem(projectPath, item.id, { status: newStatus })
      setItems(its => its.map(i => i.id === item.id ? { ...i, status: newStatus } : i))
    } catch (e: any) { toast('error', e.message) }
  }

  const handleDelete = async (item: PlanItem) => {
    try {
      await deletePlanItem(projectPath, item.id)
      setItems(its => its.filter(i => i.id !== item.id))
      if (selected?.id === item.id) setSelected(null)
      toast('success', 'Task deleted')
    } catch (e: any) { toast('error', e.message) }
  }

  const compName = (id: string | null) => components.find(c => c.id === id)?.name ?? null

  if (!projectPath) return <EmptyState />

  const todoCount = items.filter(i => i.status === 'todo').length
  const inProgCount = items.filter(i => i.status === 'in_progress').length
  const doneCount = items.filter(i => i.status === 'done').length

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      {/* Toolbar */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 12,
        padding: '16px 24px', borderBottom: '1px solid var(--border)',
        background: 'var(--bg-surface)', flexShrink: 0,
      }}>
        <h2 style={{ fontSize: 16, fontWeight: 700, flex: 1 }}>Plan Board</h2>
        <div style={{ display: 'flex', gap: 10, fontSize: 12, color: 'var(--text-muted)' }}>
          <span>{items.length} total</span>
          <span style={{ color: '#4f7cff' }}>{inProgCount} active</span>
          <span style={{ color: '#22c55e' }}>{doneCount} done</span>
        </div>
        <button className="btn btn-primary btn-sm" onClick={() => setShowAdd('todo')}>
          <Plus size={13} /> Add Task
        </button>
      </div>

      {/* Kanban columns */}
      <div style={{
        flex: 1, display: 'flex', gap: 0, overflowX: 'auto', overflowY: 'hidden',
        padding: '20px 20px',
        background: 'var(--bg-base)',
      }}>
        {COLUMNS.map(col => {
          const colItems = items.filter(i => i.status === col.status)
          return (
            <div key={col.status} style={{
              width: 280, flexShrink: 0, display: 'flex', flexDirection: 'column',
              margin: '0 8px',
              background: 'var(--bg-surface)',
              borderRadius: 'var(--radius-lg)',
              border: '1px solid var(--border)',
              overflow: 'hidden',
              maxHeight: '100%',
            }}>
              {/* Column header */}
              <div style={{
                padding: '13px 16px',
                borderBottom: '1px solid var(--border)',
                display: 'flex', alignItems: 'center', gap: 8,
                background: col.color + '0a',
                flexShrink: 0,
              }}>
                <div style={{ width: 8, height: 8, borderRadius: '50%', background: col.color, boxShadow: `0 0 6px ${col.color}` }} />
                <span style={{ fontSize: 13, fontWeight: 700, flex: 1 }}>{col.label}</span>
                <span style={{ fontSize: 12, fontWeight: 700, color: col.color, background: col.color + '22', padding: '1px 8px', borderRadius: 10 }}>
                  {colItems.length}
                </span>
                <button
                  onClick={() => setShowAdd(col.status)}
                  style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', padding: 2 }}
                >
                  <Plus size={14} />
                </button>
              </div>

              {/* Cards */}
              <div style={{ flex: 1, overflowY: 'auto', padding: '10px 10px' }}>
                {loading && colItems.length === 0 && (
                  <div style={{ display: 'flex', justifyContent: 'center', padding: 20 }}>
                    <span className="spinner" />
                  </div>
                )}
                {colItems.map(item => (
                  <TaskCard
                    key={item.id}
                    item={item}
                    compName={compName(item.component_id)}
                    columns={COLUMNS}
                    onClick={() => setSelected(item)}
                    onMove={moveItem}
                    onDelete={handleDelete}
                    selected={selected?.id === item.id}
                  />
                ))}
                {colItems.length === 0 && !loading && (
                  <div style={{ textAlign: 'center', padding: '24px 8px', color: 'var(--text-muted)', fontSize: 12 }}>
                    Drop tasks here
                  </div>
                )}
              </div>
            </div>
          )
        })}
      </div>

      {/* Task detail panel */}
      {selected && (
        <TaskDetailModal
          item={selected}
          components={components}
          projectPath={projectPath}
          onClose={() => setSelected(null)}
          onUpdated={() => { load(); setSelected(null) }}
          onDelete={() => handleDelete(selected)}
          toast={toast}
        />
      )}

      {/* Add task modal */}
      {showAdd && (
        <AddTaskModal
          defaultStatus={showAdd}
          projectPath={projectPath}
          components={components}
          onClose={() => setShowAdd(null)}
          onAdded={load}
          toast={toast}
        />
      )}
    </div>
  )
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function isRecentlyAgentUpdated(item: PlanItem): boolean {
  if (item.status !== 'in_progress') return false
  const updatedMs = new Date(item.updated_at).getTime()
  return Date.now() - updatedMs < 30_000
}

// ── Task Card ──────────────────────────────────────────────────────────────────

function TaskCard({ item, compName, columns, onClick, onMove, onDelete, selected }: {
  item: PlanItem
  compName: string | null
  columns: typeof COLUMNS
  onClick: () => void
  onMove: (item: PlanItem, s: PlanStatus) => void
  onDelete: (item: PlanItem) => void
  selected: boolean
}) {
  const [showMenu, setShowMenu] = useState(false)
  const pc = PRIORITY_COLOR[item.priority] || '#64748b'

  return (
    <div
      onClick={onClick}
      style={{
        background: selected ? 'var(--bg-hover)' : 'var(--bg-card)',
        border: `1px solid ${selected ? 'var(--accent)' : 'var(--border)'}`,
        borderRadius: 'var(--radius)',
        padding: '11px 13px',
        marginBottom: 8,
        cursor: 'pointer',
        transition: 'all 0.12s ease',
        boxShadow: selected ? '0 0 0 2px rgba(79,124,255,0.2)' : 'none',
      }}
      onMouseEnter={e => { if (!selected) (e.currentTarget as HTMLDivElement).style.borderColor = 'var(--border-bright)' }}
      onMouseLeave={e => { if (!selected) (e.currentTarget as HTMLDivElement).style.borderColor = 'var(--border)' }}
    >
      {/* Priority + agent badge + component */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
        <span style={{
          fontSize: 10, fontWeight: 700, padding: '1px 7px', borderRadius: 10,
          background: pc + '22', color: pc, letterSpacing: '0.03em',
        }}>{item.priority}</span>
        {isRecentlyAgentUpdated(item) && (
          <span style={{
            fontSize: 10, fontWeight: 700, padding: '1px 7px', borderRadius: 10,
            background: '#4f7cff22', color: '#4f7cff',
            animation: 'pulse 1.5s ease-in-out infinite',
          }}>agent working</span>
        )}
        {compName && (
          <span style={{ fontSize: 10, color: 'var(--text-muted)', background: 'var(--bg-raised)', padding: '1px 6px', borderRadius: 4, marginLeft: 'auto' }}>
            {compName}
          </span>
        )}
      </div>

      {/* Title */}
      <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4, lineHeight: 1.4 }}>
        {item.title}
      </div>

      {item.description && (
        <div style={{ fontSize: 11, color: 'var(--text-muted)', lineHeight: 1.5, overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' as any }}>
          {item.description}
        </div>
      )}

      {/* Footer actions */}
      <div style={{ display: 'flex', gap: 4, marginTop: 8 }} onClick={e => e.stopPropagation()}>
        {columns.filter(c => c.status !== item.status).slice(0, 2).map(col => (
          <button
            key={col.status}
            className="btn btn-ghost btn-sm"
            onClick={() => onMove(item, col.status)}
            style={{ fontSize: 10, padding: '3px 8px', color: col.color, borderColor: col.color + '44' }}
          >
            {col.label}
          </button>
        ))}
        <button
          className="btn btn-danger btn-sm"
          onClick={() => onDelete(item)}
          style={{ marginLeft: 'auto', padding: '3px 7px' }}
        >
          <Trash2 size={10} />
        </button>
      </div>
    </div>
  )
}

// ── Detail modal ───────────────────────────────────────────────────────────────

function TaskDetailModal({ item, components, projectPath, onClose, onUpdated, onDelete, toast }: any) {
  const [form, setForm] = useState({
    title: item.title, description: item.description,
    status: item.status, priority: item.priority, component_id: item.component_id ?? '',
  })
  const [saving, setSaving] = useState(false)

  const save = async () => {
    setSaving(true)
    try {
      await updatePlanItem(projectPath, item.id, {
        ...form,
        component_id: form.component_id || null,
      })
      toast('success', 'Task updated')
      onUpdated()
    } catch (e: any) { toast('error', e.message) }
    finally { setSaving(false) }
  }

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 1000,
      background: 'rgba(8,12,20,0.8)', backdropFilter: 'blur(6px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }} onClick={onClose}>
      <div style={{
        background: 'var(--bg-surface)', border: '1px solid var(--border-bright)',
        borderRadius: 'var(--radius-lg)', padding: 24, width: 500,
        boxShadow: 'var(--shadow)', animation: 'slideUp 0.2s ease',
      }} onClick={e => e.stopPropagation()}>
        <div style={{ display: 'flex', alignItems: 'center', marginBottom: 20 }}>
          <span style={{ fontWeight: 700, fontSize: 15, flex: 1 }}>Edit Task</span>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}>
            <X size={16} />
          </button>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <Field label="Title *">
            <input type="text" value={form.title} onChange={e => setForm(f => ({...f, title: e.target.value}))} />
          </Field>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <Field label="Status">
              <select value={form.status} onChange={e => setForm(f => ({...f, status: e.target.value}))}>
                <option value="todo">Todo</option>
                <option value="in_progress">In Progress</option>
                <option value="blocked">Blocked</option>
                <option value="done">Done</option>
                <option value="cancelled">Cancelled</option>
              </select>
            </Field>
            <Field label="Priority">
              <select value={form.priority} onChange={e => setForm(f => ({...f, priority: e.target.value}))}>
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
                <option value="critical">Critical</option>
              </select>
            </Field>
          </div>
          <Field label="Component">
            <select value={form.component_id} onChange={e => setForm(f => ({...f, component_id: e.target.value}))}>
              <option value="">No component</option>
              {components.map((c: Component) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </Field>
          <Field label="Description">
            <textarea value={form.description} onChange={e => setForm(f => ({...f, description: e.target.value}))} style={{ minHeight: 80 }} />
          </Field>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'space-between' }}>
            <button className="btn btn-danger btn-sm" onClick={onDelete}><Trash2 size={12} /> Delete</button>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
              <button className="btn btn-primary" onClick={save} disabled={saving}>
                {saving ? <span className="spinner" /> : 'Save changes'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Add task modal ─────────────────────────────────────────────────────────────

function AddTaskModal({ defaultStatus, projectPath, components, onClose, onAdded, toast }: any) {
  const [form, setForm] = useState({
    title: '', description: '', status: defaultStatus as PlanStatus,
    priority: 'medium' as PlanPriority, component_id: '',
  })
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.title.trim()) return
    setLoading(true)
    try {
      await createPlanItem(projectPath, {
        title: form.title.trim(),
        description: form.description,
        status: form.status,
        priority: form.priority,
        component_id: form.component_id || null,
      })
      toast('success', 'Task created')
      onAdded()
      onClose()
    } catch (e: any) { toast('error', e.message) }
    finally { setLoading(false) }
  }

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 1000,
      background: 'rgba(8,12,20,0.8)', backdropFilter: 'blur(6px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }} onClick={onClose}>
      <div style={{
        background: 'var(--bg-surface)', border: '1px solid var(--border-bright)',
        borderRadius: 'var(--radius-lg)', padding: 24, width: 460,
        boxShadow: 'var(--shadow)', animation: 'slideUp 0.2s ease',
      }} onClick={e => e.stopPropagation()}>
        <div style={{ display: 'flex', alignItems: 'center', marginBottom: 20 }}>
          <span style={{ fontWeight: 700, fontSize: 15, flex: 1 }}>New Task</span>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}>
            <X size={16} />
          </button>
        </div>
        <form onSubmit={handleSubmit}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <Field label="Title *">
              <input type="text" value={form.title} onChange={e => setForm(f => ({...f, title: e.target.value}))} placeholder="What needs to be done?" autoFocus />
            </Field>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <Field label="Status">
                <select value={form.status} onChange={e => setForm(f => ({...f, status: e.target.value as PlanStatus}))}>
                  <option value="todo">Todo</option>
                  <option value="in_progress">In Progress</option>
                  <option value="blocked">Blocked</option>
                </select>
              </Field>
              <Field label="Priority">
                <select value={form.priority} onChange={e => setForm(f => ({...f, priority: e.target.value as PlanPriority}))}>
                  <option value="low">Low</option>
                  <option value="medium">Medium</option>
                  <option value="high">High</option>
                  <option value="critical">Critical</option>
                </select>
              </Field>
            </div>
            <Field label="Component">
              <select value={form.component_id} onChange={e => setForm(f => ({...f, component_id: e.target.value}))}>
                <option value="">No component</option>
                {components.map((c: Component) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </Field>
            <Field label="Description">
              <textarea value={form.description} onChange={e => setForm(f => ({...f, description: e.target.value}))} placeholder="Optional details..." style={{ minHeight: 70 }} />
            </Field>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button type="button" className="btn btn-ghost" onClick={onClose}>Cancel</button>
              <button type="submit" className="btn btn-primary" disabled={loading || !form.title.trim()}>
                {loading ? <span className="spinner" /> : <><Plus size={13} /> Create</>}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 6 }}>{label}</div>
      {children}
    </div>
  )
}

function EmptyState() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
      <div style={{ textAlign: 'center', color: 'var(--text-muted)' }}>
        <ClipboardList size={40} style={{ marginBottom: 12, opacity: 0.4 }} />
        <p style={{ fontSize: 14, color: 'var(--text-secondary)' }}>Load a project from the Dashboard first.</p>
      </div>
    </div>
  )
}
