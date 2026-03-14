import React, { useCallback, useEffect, useMemo, useState } from 'react'
import {
  ReactFlow,
  Background, Controls, MiniMap,
  addEdge, useNodesState, useEdgesState,
  type Node, type Edge, type Connection,
  MarkerType, Panel,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import {
  Plus, Trash2, Edit2, X, Check, ChevronRight, Layers,
  GitBranch, Tag, Info,
} from 'lucide-react'
import { useStore } from '../store'
import {
  getArchitecture, addComponent, updateComponent, deleteComponent,
  addDependency, removeDependency,
} from '../api/archMapApi'
import type { Component, Dependency, Layer } from '../types'

const LAYER_COLOR: Record<string, string> = {
  frontend: '#22c55e', backend:  '#4f7cff', database: '#f59e0b',
  infra:    '#a855f7', shared:   '#06b6d4', testing:  '#ec4899', other: '#64748b',
}

const LAYERS: Layer[] = ['frontend', 'backend', 'database', 'infra', 'shared', 'testing', 'other']

// ── Custom node ────────────────────────────────────────────────────────────────

function ComponentNode({ data }: { data: any }) {
  const c = LAYER_COLOR[data.layer] || '#64748b'
  return (
    <div style={{
      background: 'var(--bg-card)',
      border: `1.5px solid ${data.selected ? c : 'var(--border)'}`,
      borderRadius: 10,
      padding: '10px 14px',
      minWidth: 140,
      boxShadow: data.selected ? `0 0 0 2px ${c}44, 0 4px 20px ${c}22` : '0 2px 12px rgba(0,0,0,0.4)',
      transition: 'all 0.15s',
      cursor: 'pointer',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 4 }}>
        <div style={{ width: 8, height: 8, borderRadius: '50%', background: c, flexShrink: 0, boxShadow: `0 0 6px ${c}` }} />
        <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-primary)', lineHeight: 1.2 }}>{data.label}</span>
      </div>
      <div style={{
        display: 'inline-flex', alignItems: 'center',
        padding: '1px 7px', borderRadius: 10, fontSize: 10, fontWeight: 600,
        background: c + '22', color: c, letterSpacing: '0.03em',
      }}>
        {data.layer}
      </div>
      {data.confidence === 'auto' && (
        <div style={{ fontSize: 9, color: 'var(--text-muted)', marginTop: 4 }}>auto-detected</div>
      )}
    </div>
  )
}

const nodeTypes = { component: ComponentNode }

// ── Main page ──────────────────────────────────────────────────────────────────

export default function ArchitecturePage() {
  const { projectPath, toast } = useStore()
  const [components, setComponents] = useState<Component[]>([])
  const [dependencies, setDependencies] = useState<Dependency[]>([])
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([])
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([])
  const [selected, setSelected] = useState<Component | null>(null)
  const [loading, setLoading] = useState(false)
  const [showAdd, setShowAdd] = useState(false)

  const load = useCallback(async () => {
    if (!projectPath) return
    setLoading(true)
    try {
      const arch = await getArchitecture(projectPath)
      setComponents(arch.components)
      setDependencies(arch.dependencies)
      setNodes(buildNodes(arch.components))
      setEdges(buildEdges(arch.dependencies))
    } catch (e: any) { toast('error', e.message) }
    finally { setLoading(false) }
  }, [projectPath])

  useEffect(() => { load() }, [load])

  const onConnect = useCallback(async (conn: Connection) => {
    if (!projectPath || !conn.source || !conn.target) return
    try {
      const dep = await addDependency(projectPath, conn.source, conn.target)
      setDependencies(d => [...d, dep])
      setEdges(e => addEdge(depToEdge(dep), e))
      toast('success', 'Dependency added')
    } catch (e: any) { toast('error', e.message) }
  }, [projectPath])

  const handleSelectNode = useCallback((_e: React.MouseEvent, node: Node) => {
    const comp = components.find(c => c.id === node.id) ?? null
    setSelected(comp)
  }, [components])

  const handleDeleteComp = async (id: string) => {
    if (!projectPath) return
    try {
      await deleteComponent(projectPath, id)
      toast('success', 'Component deleted')
      setSelected(null)
      load()
    } catch (e: any) { toast('error', e.message) }
  }

  const handleDeleteEdge = useCallback(async (edge: Edge) => {
    if (!projectPath || !edge.id) return
    try {
      await removeDependency(projectPath, edge.id)
      setEdges(eds => eds.filter(e => e.id !== edge.id))
      toast('success', 'Dependency removed')
    } catch (e: any) { toast('error', e.message) }
  }, [projectPath])

  if (!projectPath) return <EmptyState />

  return (
    <div style={{ display: 'flex', height: '100%', overflow: 'hidden' }}>
      {/* Canvas */}
      <div style={{ flex: 1, position: 'relative' }}>
        {loading && (
          <div style={{
            position: 'absolute', inset: 0, zIndex: 10,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: 'rgba(8,12,20,0.6)', backdropFilter: 'blur(4px)',
          }}>
            <span className="spinner spinner-lg" />
          </div>
        )}
        <ReactFlow
          nodes={nodes.map(n => ({ ...n, data: { ...n.data, selected: n.id === selected?.id } }))}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onNodeClick={handleSelectNode}
          onEdgeClick={(_, edge) => handleDeleteEdge(edge)}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{ padding: 0.2 }}
          style={{ background: 'var(--bg-base)' }}
          deleteKeyCode={null}
        >
          <Background color="var(--border)" gap={24} size={1} />
          <Controls style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 8 }} />
          <MiniMap
            style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
            nodeColor={n => LAYER_COLOR[(n as any).data?.layer] || '#64748b'}
            maskColor="rgba(8,12,20,0.7)"
          />
          <Panel position="top-left">
            <div style={{ display: 'flex', gap: 8, padding: 8 }}>
              <button className="btn btn-primary btn-sm" onClick={() => setShowAdd(true)}>
                <Plus size={13} /> Component
              </button>
              <button className="btn btn-ghost btn-sm" onClick={load}>
                Refresh
              </button>
            </div>
          </Panel>
          <Panel position="top-right">
            <LayerLegend />
          </Panel>
        </ReactFlow>
      </div>

      {/* Side panel */}
      {selected && (
        <ComponentPanel
          comp={selected}
          projectPath={projectPath}
          deps={dependencies}
          components={components}
          onClose={() => setSelected(null)}
          onDelete={() => handleDeleteComp(selected.id)}
          onUpdated={load}
          toast={toast}
        />
      )}

      {/* Add modal */}
      {showAdd && (
        <AddComponentModal
          projectPath={projectPath}
          onClose={() => setShowAdd(false)}
          onAdded={load}
          toast={toast}
        />
      )}
    </div>
  )
}

// ── Panel ──────────────────────────────────────────────────────────────────────

function ComponentPanel({ comp, projectPath, deps, components, onClose, onDelete, onUpdated, toast }: any) {
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState({ name: comp.name, description: comp.description, layer: comp.layer })

  useEffect(() => {
    setForm({ name: comp.name, description: comp.description, layer: comp.layer })
    setEditing(false)
  }, [comp.id])

  const connectedDeps = deps.filter((d: Dependency) => d.from_component === comp.id || d.to_component === comp.id)
  const nameMap: Record<string, string> = {}
  components.forEach((c: Component) => { nameMap[c.id] = c.name })

  const handleSave = async () => {
    try {
      await updateComponent(projectPath, comp.id, form)
      toast('success', 'Updated')
      setEditing(false)
      onUpdated()
    } catch (e: any) { toast('error', e.message) }
  }

  const c = LAYER_COLOR[comp.layer] || '#64748b'

  return (
    <div style={{
      width: 300, flexShrink: 0,
      borderLeft: '1px solid var(--border)',
      background: 'var(--bg-surface)',
      display: 'flex', flexDirection: 'column',
      overflow: 'hidden',
    }}>
      {/* Header */}
      <div style={{
        padding: '16px 18px', borderBottom: '1px solid var(--border)',
        display: 'flex', alignItems: 'center', gap: 8,
      }}>
        <div style={{ width: 10, height: 10, borderRadius: '50%', background: c, boxShadow: `0 0 8px ${c}` }} />
        <span style={{ flex: 1, fontWeight: 700, fontSize: 14, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {comp.name}
        </span>
        <button onClick={() => setEditing(!editing)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', padding: 4 }}>
          <Edit2 size={14} />
        </button>
        <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', padding: 4 }}>
          <X size={14} />
        </button>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: 18 }}>
        {editing ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <Field label="Name">
              <input type="text" value={form.name} onChange={e => setForm(f => ({...f, name: e.target.value}))} />
            </Field>
            <Field label="Layer">
              <select value={form.layer} onChange={e => setForm(f => ({...f, layer: e.target.value}))}>
                {LAYERS.map(l => <option key={l} value={l}>{l}</option>)}
              </select>
            </Field>
            <Field label="Description">
              <textarea value={form.description} onChange={e => setForm(f => ({...f, description: e.target.value}))} style={{ minHeight: 70 }} />
            </Field>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="btn btn-primary btn-sm" onClick={handleSave}><Check size={12} /> Save</button>
              <button className="btn btn-ghost btn-sm" onClick={() => setEditing(false)}>Cancel</button>
            </div>
          </div>
        ) : (
          <>
            <Section icon={<Info size={12} />} label="Details">
              <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
                <span className="badge" style={{ background: c + '22', color: c }}>{comp.layer}</span>
                <span className="badge" style={{ background: 'var(--bg-raised)', color: 'var(--text-muted)' }}>{comp.confidence}</span>
              </div>
              {comp.description && (
                <p style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.6 }}>{comp.description}</p>
              )}
              <p style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 8, fontFamily: 'monospace' }}>{comp.id}</p>
            </Section>

            {comp.tags.length > 0 && (
              <Section icon={<Tag size={12} />} label="Tags">
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                  {comp.tags.map((t: string) => (
                    <span key={t} style={{ padding: '2px 8px', borderRadius: 4, fontSize: 11, background: 'var(--bg-raised)', color: 'var(--text-secondary)', border: '1px solid var(--border)' }}>{t}</span>
                  ))}
                </div>
              </Section>
            )}

            <Section icon={<GitBranch size={12} />} label={`Dependencies (${connectedDeps.length})`}>
              {connectedDeps.length === 0
                ? <p style={{ fontSize: 12, color: 'var(--text-muted)' }}>No dependencies. Connect nodes on the canvas.</p>
                : connectedDeps.map((d: Dependency) => {
                    const isOut = d.from_component === comp.id
                    const other = nameMap[isOut ? d.to_component : d.from_component] ?? '?'
                    const dc = LAYER_COLOR[components.find((c: Component) => c.id === (isOut ? d.to_component : d.from_component))?.layer ?? 'other']
                    return (
                      <div key={d.id} style={{
                        display: 'flex', alignItems: 'center', gap: 6, marginBottom: 5,
                        padding: '5px 8px', background: 'var(--bg-raised)', borderRadius: 6,
                      }}>
                        <ChevronRight size={11} color={isOut ? 'var(--accent)' : 'var(--text-muted)'} style={{ transform: isOut ? 'none' : 'rotate(180deg)' }} />
                        <span style={{ width: 7, height: 7, borderRadius: '50%', background: dc, flexShrink: 0 }} />
                        <span style={{ fontSize: 12, flex: 1 }}>{other}</span>
                        <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>{d.label}</span>
                      </div>
                    )
                  })
              }
            </Section>
          </>
        )}
      </div>

      <div style={{ padding: '12px 18px', borderTop: '1px solid var(--border)' }}>
        <button className="btn btn-danger btn-sm" onClick={onDelete} style={{ width: '100%', justifyContent: 'center' }}>
          <Trash2 size={12} /> Delete Component
        </button>
      </div>
    </div>
  )
}

// ── Add modal ──────────────────────────────────────────────────────────────────

function AddComponentModal({ projectPath, onClose, onAdded, toast }: any) {
  const [form, setForm] = useState({ name: '', layer: 'backend' as Layer, description: '', tags: '' })
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.name.trim()) return
    setLoading(true)
    try {
      await addComponent(projectPath, {
        name: form.name.trim(),
        layer: form.layer,
        description: form.description,
        tags: form.tags.split(',').map(t => t.trim()).filter(Boolean),
      })
      toast('success', `Component "${form.name}" added`)
      onAdded()
      onClose()
    } catch (e: any) { toast('error', e.message) }
    finally { setLoading(false) }
  }

  return (
    <Modal title="Add Component" onClose={onClose}>
      <form onSubmit={handleSubmit}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <Field label="Name *">
            <input type="text" value={form.name} onChange={e => setForm(f => ({...f, name: e.target.value}))} placeholder="e.g. Auth Service" autoFocus />
          </Field>
          <Field label="Layer">
            <select value={form.layer} onChange={e => setForm(f => ({...f, layer: e.target.value as Layer}))}>
              {LAYERS.map(l => <option key={l} value={l}>{l}</option>)}
            </select>
          </Field>
          <Field label="Description">
            <textarea value={form.description} onChange={e => setForm(f => ({...f, description: e.target.value}))} placeholder="What does this component do?" />
          </Field>
          <Field label="Tags (comma-separated)">
            <input type="text" value={form.tags} onChange={e => setForm(f => ({...f, tags: e.target.value}))} placeholder="api, auth, jwt" />
          </Field>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button type="button" className="btn btn-ghost" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn btn-primary" disabled={loading || !form.name.trim()}>
              {loading ? <span className="spinner" /> : <><Plus size={13} /> Add</>}
            </button>
          </div>
        </div>
      </form>
    </Modal>
  )
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function buildNodes(components: Component[]): Node[] {
  const cols = Math.ceil(Math.sqrt(components.length)) || 1
  return components.map((c, i) => ({
    id: c.id,
    type: 'component',
    data: { label: c.name, layer: c.layer, confidence: c.confidence },
    position: { x: (i % cols) * 220, y: Math.floor(i / cols) * 120 },
  }))
}

function depToEdge(d: Dependency): Edge {
  return {
    id: d.id,
    source: d.from_component,
    target: d.to_component,
    label: d.label,
    type: 'smoothstep',
    markerEnd: { type: MarkerType.ArrowClosed, width: 12, height: 12, color: '#4f7cff' },
    style: { stroke: '#4f7cff', strokeWidth: 1.5 },
    labelStyle: { fill: '#8ba0b8', fontSize: 10 },
    labelBgStyle: { fill: 'var(--bg-card)' },
  }
}

function buildEdges(deps: Dependency[]): Edge[] {
  return deps.map(depToEdge)
}

function LayerLegend() {
  return (
    <div style={{
      background: 'var(--bg-card)', border: '1px solid var(--border)',
      borderRadius: 'var(--radius)', padding: '10px 14px', margin: 8,
    }}>
      <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>
        Layers
      </div>
      {Object.entries(LAYER_COLOR).map(([layer, color]) => (
        <div key={layer} style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 4 }}>
          <div style={{ width: 7, height: 7, borderRadius: '50%', background: color, boxShadow: `0 0 5px ${color}` }} />
          <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{layer}</span>
        </div>
      ))}
    </div>
  )
}

function Section({ icon, label, children }: { icon: React.ReactNode; label: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 20 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginBottom: 8 }}>
        <span style={{ color: 'var(--text-muted)' }}>{icon}</span>
        <span style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.07em' }}>{label}</span>
      </div>
      {children}
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

function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 1000,
      background: 'rgba(8,12,20,0.75)', backdropFilter: 'blur(6px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }} onClick={onClose}>
      <div
        style={{
          background: 'var(--bg-surface)', border: '1px solid var(--border-bright)',
          borderRadius: 'var(--radius-lg)', padding: 24, width: 440,
          boxShadow: 'var(--shadow)', animation: 'slideUp 0.2s ease',
        }}
        onClick={e => e.stopPropagation()}
      >
        <div style={{ display: 'flex', alignItems: 'center', marginBottom: 20 }}>
          <span style={{ fontWeight: 700, fontSize: 15, flex: 1 }}>{title}</span>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}>
            <X size={16} />
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}

function EmptyState() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
      <div style={{ textAlign: 'center', color: 'var(--text-muted)' }}>
        <Layers size={40} style={{ marginBottom: 12, opacity: 0.4 }} />
        <p style={{ fontSize: 14, color: 'var(--text-secondary)' }}>Load a project from the Dashboard first.</p>
      </div>
    </div>
  )
}
