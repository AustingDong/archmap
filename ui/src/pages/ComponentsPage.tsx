import React, { useEffect, useState } from 'react'
import { listComponents, getDependencyGraph } from '../api/archMapApi'
import type { Component, DependencyGraph } from '../types'

const LAYER_COLORS: Record<string, string> = {
  frontend: '#10b981', backend: '#3b82f6', database: '#f59e0b',
  infra: '#8b5cf6', shared: '#6366f1', testing: '#ec4899', other: '#64748b',
}

export default function ComponentsPage() {
  const projectPath = localStorage.getItem('archmap_project_path') || ''
  const [components, setComponents] = useState<Component[]>([])
  const [graph, setGraph] = useState<DependencyGraph | null>(null)
  const [selected, setSelected] = useState<Component | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!projectPath) return
    Promise.all([
      listComponents(projectPath),
      getDependencyGraph(projectPath),
    ]).then(([comps, g]) => {
      setComponents(comps)
      setGraph(g)
    }).catch(e => setError(e.message))
  }, [projectPath])

  if (!projectPath) return (
    <p style={{ color: '#64748b' }}>Load a project from the Dashboard first.</p>
  )

  return (
    <div style={{ display: 'flex', gap: 24, height: 'calc(100vh - 100px)' }}>
      {/* Component list */}
      <div style={{ width: 280, overflowY: 'auto' }}>
        <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>
          Components ({components.length})
        </h2>
        {error && <p style={{ color: '#f87171', fontSize: 12 }}>{error}</p>}
        {components.map(c => (
          <div
            key={c.id}
            onClick={() => setSelected(c)}
            style={{
              padding: '10px 14px', borderRadius: 8, marginBottom: 6, cursor: 'pointer',
              background: selected?.id === c.id ? '#1e3a5f' : '#1e293b',
              border: `1px solid ${selected?.id === c.id ? '#3b82f6' : '#334155'}`,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{
                width: 8, height: 8, borderRadius: '50%',
                background: LAYER_COLORS[c.layer] || '#64748b',
                flexShrink: 0,
              }} />
              <span style={{ fontSize: 13, fontWeight: 600 }}>{c.name}</span>
              {c.confidence === 'auto' && (
                <span style={{ fontSize: 10, color: '#64748b', marginLeft: 'auto' }}>auto</span>
              )}
            </div>
            <div style={{ fontSize: 11, color: '#64748b', marginTop: 3, marginLeft: 16 }}>
              {c.layer}
            </div>
          </div>
        ))}
      </div>

      {/* Detail panel */}
      <div style={{ flex: 1, background: '#1e293b', borderRadius: 12, padding: 24, border: '1px solid #334155', overflowY: 'auto' }}>
        {selected ? (
          <>
            <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 4 }}>{selected.name}</h2>
            <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
              <span style={{
                padding: '2px 10px', borderRadius: 20, fontSize: 11, fontWeight: 600,
                background: LAYER_COLORS[selected.layer] + '33',
                color: LAYER_COLORS[selected.layer],
              }}>{selected.layer}</span>
              <span style={{
                padding: '2px 10px', borderRadius: 20, fontSize: 11,
                background: '#0f172a', color: '#64748b',
              }}>{selected.confidence}</span>
            </div>
            {selected.description && (
              <p style={{ fontSize: 13, color: '#94a3b8', marginBottom: 16 }}>{selected.description}</p>
            )}
            {selected.tags.length > 0 && (
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 16 }}>
                {selected.tags.map(t => (
                  <span key={t} style={{
                    padding: '2px 8px', borderRadius: 4, fontSize: 11,
                    background: '#0f172a', color: '#94a3b8', border: '1px solid #334155',
                  }}>{t}</span>
                ))}
              </div>
            )}
            {graph && (
              <div>
                <h3 style={{ fontSize: 13, fontWeight: 700, color: '#64748b', marginBottom: 8 }}>
                  DEPENDENCIES
                </h3>
                {graph.edges.filter(e => e.source === selected.id || e.target === selected.id).length === 0
                  ? <p style={{ fontSize: 12, color: '#475569' }}>No dependencies</p>
                  : graph.edges
                      .filter(e => e.source === selected.id || e.target === selected.id)
                      .map(e => {
                        const other = e.source === selected.id
                          ? graph.nodes.find(n => n.id === e.target)
                          : graph.nodes.find(n => n.id === e.source)
                        const dir = e.source === selected.id ? '→' : '←'
                        return (
                          <div key={e.id} style={{ fontSize: 12, color: '#94a3b8', marginBottom: 4 }}>
                            {dir} <strong>{other?.label}</strong> <span style={{ color: '#475569' }}>({e.label})</span>
                          </div>
                        )
                      })
                }
              </div>
            )}
            <p style={{ fontSize: 11, color: '#334155', marginTop: 24 }}>ID: {selected.id}</p>
          </>
        ) : (
          <p style={{ color: '#475569', fontSize: 14 }}>Select a component to view details.</p>
        )}
      </div>
    </div>
  )
}
