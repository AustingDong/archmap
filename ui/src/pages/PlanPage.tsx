import React, { useEffect, useState } from 'react'
import { listPlanItems, updatePlanItem } from '../api/archMapApi'
import type { PlanItem } from '../types'

const STATUS_COLORS: Record<string, string> = {
  todo: '#64748b', in_progress: '#3b82f6', done: '#10b981',
  blocked: '#f59e0b', cancelled: '#475569',
}

const PRIORITY_COLORS: Record<string, string> = {
  low: '#64748b', medium: '#6366f1', high: '#f59e0b', critical: '#ef4444',
}

export default function PlanPage() {
  const projectPath = localStorage.getItem('archmap_project_path') || ''
  const [items, setItems] = useState<PlanItem[]>([])
  const [filter, setFilter] = useState('')
  const [error, setError] = useState('')

  const load = () => {
    if (!projectPath) return
    listPlanItems(projectPath, undefined, filter || undefined)
      .then(setItems)
      .catch(e => setError(e.message))
  }

  useEffect(() => { load() }, [projectPath, filter])

  const setStatus = async (item: PlanItem, status: PlanItem['status']) => {
    try {
      await updatePlanItem(projectPath, item.id, { status })
      load()
    } catch (e: any) { setError(e.message) }
  }

  if (!projectPath) return (
    <p style={{ color: '#64748b' }}>Load a project from the Dashboard first.</p>
  )

  return (
    <div style={{ maxWidth: 900 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <h2 style={{ fontSize: 18, fontWeight: 700 }}>Plan ({items.length} items)</h2>
        <select
          value={filter}
          onChange={e => setFilter(e.target.value)}
          style={{
            padding: '6px 12px', borderRadius: 6, background: '#1e293b',
            border: '1px solid #334155', color: '#e2e8f0', fontSize: 13,
          }}
        >
          <option value="">All statuses</option>
          <option value="todo">Todo</option>
          <option value="in_progress">In Progress</option>
          <option value="blocked">Blocked</option>
          <option value="done">Done</option>
          <option value="cancelled">Cancelled</option>
        </select>
      </div>

      {error && <p style={{ color: '#f87171', marginBottom: 12, fontSize: 12 }}>{error}</p>}

      {items.length === 0 && (
        <p style={{ color: '#475569', fontSize: 14 }}>No plan items. Create them via MCP or CLI.</p>
      )}

      {items.map(item => (
        <div key={item.id} style={{
          background: '#1e293b', borderRadius: 10, padding: '14px 18px',
          marginBottom: 10, border: '1px solid #334155',
          display: 'flex', gap: 16, alignItems: 'flex-start',
        }}>
          <div style={{ flex: 1 }}>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 4 }}>
              <span style={{
                padding: '2px 8px', borderRadius: 20, fontSize: 11, fontWeight: 600,
                background: STATUS_COLORS[item.status] + '33',
                color: STATUS_COLORS[item.status],
              }}>{item.status.replace('_', ' ')}</span>
              <span style={{
                padding: '2px 8px', borderRadius: 20, fontSize: 11,
                background: PRIORITY_COLORS[item.priority] + '22',
                color: PRIORITY_COLORS[item.priority],
              }}>{item.priority}</span>
            </div>
            <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>{item.title}</div>
            {item.description && (
              <div style={{ fontSize: 12, color: '#64748b' }}>{item.description}</div>
            )}
          </div>
          <div style={{ display: 'flex', gap: 6 }}>
            {item.status !== 'done' && (
              <button
                onClick={() => setStatus(item, 'done')}
                style={{
                  padding: '4px 10px', borderRadius: 6, fontSize: 11, cursor: 'pointer',
                  background: '#10b98122', color: '#10b981', border: '1px solid #10b98144',
                }}
              >Done</button>
            )}
            {item.status === 'todo' && (
              <button
                onClick={() => setStatus(item, 'in_progress')}
                style={{
                  padding: '4px 10px', borderRadius: 6, fontSize: 11, cursor: 'pointer',
                  background: '#3b82f622', color: '#3b82f6', border: '1px solid #3b82f644',
                }}
              >Start</button>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}
