import React, { useEffect, useState } from 'react'
import { projectStatus } from '../api/archMapApi'
import type { ProjectStatus } from '../types'

const CARD = {
  background: '#1e293b', borderRadius: 10, padding: '20px 24px',
  border: '1px solid #334155', minWidth: 160,
}

export default function DashboardPage() {
  const [status, setStatus] = useState<ProjectStatus | null>(null)
  const [error, setError] = useState('')
  const [projectPath, setProjectPath] = useState(
    localStorage.getItem('archmap_project_path') || ''
  )
  const [input, setInput] = useState(projectPath)

  const load = async (path: string) => {
    try {
      const s = await projectStatus(path)
      setStatus(s)
      setError('')
      localStorage.setItem('archmap_project_path', path)
    } catch (e: any) {
      setError(e.message)
    }
  }

  useEffect(() => { if (projectPath) load(projectPath) }, [projectPath])

  const stats = status ? [
    { label: 'Components', value: status.components },
    { label: 'Dependencies', value: status.dependencies },
    { label: 'Mapped Files', value: status.mapped_files },
    { label: 'Open Tasks', value: status.plan_open },
  ] : []

  return (
    <div style={{ maxWidth: 800 }}>
      <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 20 }}>
        {status ? status.name : 'ArchMap Dashboard'}
      </h1>

      <div style={{ display: 'flex', gap: 10, marginBottom: 24 }}>
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          placeholder="Project path (e.g. C:/Users/you/my-project)"
          style={{
            flex: 1, padding: '8px 12px', borderRadius: 6, border: '1px solid #334155',
            background: '#1e293b', color: '#e2e8f0', fontSize: 13,
          }}
          onKeyDown={e => e.key === 'Enter' && setProjectPath(input)}
        />
        <button
          onClick={() => setProjectPath(input)}
          style={{
            padding: '8px 16px', borderRadius: 6, background: '#6366f1',
            color: '#fff', border: 'none', cursor: 'pointer', fontSize: 13, fontWeight: 600,
          }}
        >
          Load
        </button>
      </div>

      {error && <p style={{ color: '#f87171', marginBottom: 16, fontSize: 13 }}>{error}</p>}

      {stats.length > 0 && (
        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
          {stats.map(s => (
            <div key={s.label} style={CARD}>
              <div style={{ fontSize: 32, fontWeight: 700, color: '#6366f1' }}>{s.value}</div>
              <div style={{ fontSize: 13, color: '#94a3b8', marginTop: 4 }}>{s.label}</div>
            </div>
          ))}
        </div>
      )}

      {!status && !error && (
        <p style={{ color: '#64748b', fontSize: 14 }}>
          Enter a project path above to load its architecture map.
        </p>
      )}
    </div>
  )
}
