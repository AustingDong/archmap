import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Search, FileCode2, Folder, X, Trash2 } from 'lucide-react'
import { useStore } from '../store'
import { listAllMappings, listComponents, unmapFile } from '../api/archMapApi'
import type { FileMapping, Component } from '../types'

const LAYER_COLOR: Record<string, string> = {
  frontend: '#22c55e', backend: '#4f7cff', database: '#f59e0b',
  infra: '#a855f7', shared: '#06b6d4', testing: '#ec4899', other: '#64748b',
}

export default function MappingsPage() {
  const { projectPath, toast } = useStore()
  const [mappings, setMappings] = useState<FileMapping[]>([])
  const [components, setComponents] = useState<Component[]>([])
  const [loading, setLoading] = useState(false)
  const [search, setSearch] = useState('')
  const [filterComp, setFilterComp] = useState('')

  const load = useCallback(async () => {
    if (!projectPath) return
    setLoading(true)
    try {
      const [maps, comps] = await Promise.all([
        listAllMappings(projectPath),
        listComponents(projectPath),
      ])
      setMappings(maps)
      setComponents(comps)
    } catch (e: any) { toast('error', e.message) }
    finally { setLoading(false) }
  }, [projectPath])

  useEffect(() => { load() }, [load])

  const compMap = useMemo(() => {
    const m: Record<string, Component> = {}
    components.forEach(c => { m[c.id] = c })
    return m
  }, [components])

  const filtered = useMemo(() => {
    let ms = mappings
    if (search) ms = ms.filter(m => m.file_path.toLowerCase().includes(search.toLowerCase()))
    if (filterComp) ms = ms.filter(m => m.component_id === filterComp)
    return ms
  }, [mappings, search, filterComp])

  const handleUnmap = async (fp: string) => {
    try {
      await unmapFile(projectPath, fp)
      setMappings(m => m.filter(x => x.file_path !== fp))
      toast('success', 'File unmapped')
    } catch (e: any) { toast('error', e.message) }
  }

  // Group by directory
  const grouped = useMemo(() => {
    const g: Record<string, FileMapping[]> = {}
    filtered.forEach(m => {
      const parts = m.file_path.split('/')
      const dir = parts.length > 1 ? parts.slice(0, -1).join('/') : '(root)'
      ;(g[dir] = g[dir] ?? []).push(m)
    })
    return Object.entries(g).sort(([a], [b]) => a.localeCompare(b))
  }, [filtered])

  if (!projectPath) return <EmptyState />

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      {/* Toolbar */}
      <div style={{
        padding: '16px 24px', borderBottom: '1px solid var(--border)',
        background: 'var(--bg-surface)', flexShrink: 0,
        display: 'flex', gap: 12, alignItems: 'center',
      }}>
        <h2 style={{ fontSize: 16, fontWeight: 700 }}>Mappings</h2>
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{mappings.length} files</span>

        <div style={{ flex: 1 }} />

        {/* Search */}
        <div style={{ position: 'relative', width: 260 }}>
          <Search size={13} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
          <input
            type="search" value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Search files…"
            style={{ paddingLeft: 32, width: '100%' }}
          />
          {search && (
            <button onClick={() => setSearch('')} style={{ position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}>
              <X size={12} />
            </button>
          )}
        </div>

        {/* Component filter */}
        <select value={filterComp} onChange={e => setFilterComp(e.target.value)} style={{ width: 180 }}>
          <option value="">All components</option>
          {components.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
      </div>

      {/* Two-column layout */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        {/* Component sidebar */}
        <div style={{
          width: 220, flexShrink: 0,
          borderRight: '1px solid var(--border)',
          background: 'var(--bg-surface)',
          overflowY: 'auto',
          padding: '12px 8px',
        }}>
          <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', padding: '0 8px', marginBottom: 8 }}>
            Components
          </div>
          <div
            onClick={() => setFilterComp('')}
            style={{
              padding: '7px 10px', borderRadius: 6, cursor: 'pointer', marginBottom: 2, fontSize: 12,
              background: !filterComp ? 'var(--accent-dim)' : 'transparent',
              color: !filterComp ? 'var(--accent)' : 'var(--text-secondary)',
              borderLeft: !filterComp ? '2px solid var(--accent)' : '2px solid transparent',
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            }}
          >
            <span>All files</span>
            <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>{mappings.length}</span>
          </div>
          {components.map(c => {
            const cnt = mappings.filter(m => m.component_id === c.id).length
            const color = LAYER_COLOR[c.layer] || '#64748b'
            const active = filterComp === c.id
            return (
              <div
                key={c.id}
                onClick={() => setFilterComp(active ? '' : c.id)}
                style={{
                  padding: '7px 10px', borderRadius: 6, cursor: 'pointer', marginBottom: 2,
                  background: active ? color + '15' : 'transparent',
                  borderLeft: active ? `2px solid ${color}` : '2px solid transparent',
                  display: 'flex', gap: 7, alignItems: 'center',
                }}
              >
                <div style={{ width: 7, height: 7, borderRadius: '50%', background: color, flexShrink: 0 }} />
                <span style={{ fontSize: 12, flex: 1, color: active ? 'var(--text-primary)' : 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {c.name}
                </span>
                <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>{cnt}</span>
              </div>
            )
          })}
        </div>

        {/* File list */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '0 0 20px' }}>
          {loading ? (
            <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}>
              <span className="spinner spinner-lg" />
            </div>
          ) : grouped.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '40px 20px', color: 'var(--text-muted)' }}>
              <FileCode2 size={32} style={{ marginBottom: 10, opacity: 0.3 }} />
              <p style={{ fontSize: 13 }}>No files match your filters.</p>
            </div>
          ) : (
            grouped.map(([dir, files]) => (
              <div key={dir}>
                {/* Dir header */}
                <div style={{
                  display: 'flex', alignItems: 'center', gap: 7,
                  padding: '10px 20px 6px',
                  position: 'sticky', top: 0,
                  background: 'var(--bg-base)',
                  borderBottom: '1px solid var(--border)',
                  zIndex: 1,
                }}>
                  <Folder size={12} color="var(--text-muted)" />
                  <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-secondary)', fontFamily: 'monospace' }}>{dir}</span>
                  <span style={{ fontSize: 10, color: 'var(--text-muted)', marginLeft: 4 }}>({files.length})</span>
                </div>

                {/* Files */}
                {files.map(m => {
                  const comp = compMap[m.component_id]
                  const color = comp ? (LAYER_COLOR[comp.layer] || '#64748b') : '#475569'
                  const fname = m.file_path.split('/').pop() ?? m.file_path
                  const ext = fname.includes('.') ? fname.split('.').pop() ?? '' : ''

                  return (
                    <div key={m.file_path} style={{
                      display: 'flex', alignItems: 'center', gap: 10,
                      padding: '7px 20px',
                      borderBottom: '1px solid var(--border)',
                      transition: 'background 0.1s',
                    }}
                    onMouseEnter={e => (e.currentTarget as HTMLDivElement).style.background = 'var(--bg-hover)'}
                    onMouseLeave={e => (e.currentTarget as HTMLDivElement).style.background = 'transparent'}
                    >
                      <FileIcon ext={ext} />
                      <span style={{
                        fontSize: 12, flex: 1, color: 'var(--text-primary)',
                        fontFamily: 'monospace', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                      }}>
                        {fname}
                      </span>

                      {comp && (
                        <span style={{ fontSize: 10, padding: '1px 7px', borderRadius: 10, background: color + '22', color, fontWeight: 600, flexShrink: 0 }}>
                          {comp.name}
                        </span>
                      )}
                      <span style={{ fontSize: 10, color: 'var(--text-muted)', flexShrink: 0 }}>
                        {m.mapped_by}
                      </span>

                      <button
                        onClick={() => handleUnmap(m.file_path)}
                        title="Unmap file"
                        style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', padding: 2, opacity: 0.5, flexShrink: 0 }}
                        onMouseEnter={e => (e.currentTarget as HTMLButtonElement).style.opacity = '1'}
                        onMouseLeave={e => (e.currentTarget as HTMLButtonElement).style.opacity = '0.5'}
                      >
                        <Trash2 size={11} />
                      </button>
                    </div>
                  )
                })}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}

const EXT_COLOR: Record<string, string> = {
  ts: '#3b82f6', tsx: '#06b6d4', js: '#f59e0b', jsx: '#f59e0b',
  py: '#22c55e', md: '#8ba0b8', json: '#f59e0b', css: '#ec4899',
  html: '#f97316', go: '#06b6d4', rs: '#f59e0b', sh: '#22c55e',
}

function FileIcon({ ext }: { ext: string }) {
  const color = EXT_COLOR[ext.toLowerCase()] || '#64748b'
  return (
    <div style={{
      width: 20, height: 20, borderRadius: 4,
      background: color + '22', color,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      fontSize: 8, fontWeight: 800, flexShrink: 0, fontFamily: 'monospace',
    }}>
      {ext ? ext.slice(0, 2).toUpperCase() : <FileCode2 size={10} />}
    </div>
  )
}

function EmptyState() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
      <div style={{ textAlign: 'center', color: 'var(--text-muted)' }}>
        <FileCode2 size={40} style={{ marginBottom: 12, opacity: 0.4 }} />
        <p style={{ fontSize: 14, color: 'var(--text-secondary)' }}>Load a project from the Dashboard first.</p>
      </div>
    </div>
  )
}
