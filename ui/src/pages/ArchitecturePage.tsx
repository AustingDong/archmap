import React, { useCallback, useEffect, useState } from 'react'
import {
  ReactFlow,
  Background, Controls, MiniMap,
  addEdge, useNodesState, useEdgesState,
  Handle, Position,
  getBezierPath, useInternalNode,
  type Node, type Edge, type Connection, type EdgeProps,
  type InternalNode, type ConnectionLineComponentProps,
  MarkerType, Panel, BackgroundVariant,
} from '@xyflow/react'
import dagre from '@dagrejs/dagre'
import '@xyflow/react/dist/style.css'
import {
  Plus, Trash2, Edit2, X, Check,
  ChevronRight, ChevronDown, Layers, GitBranch, Tag, Info,
  Monitor, Server, Database, Cloud, Share2, FlaskConical, Box,
  Activity, Zap, AlertTriangle, FileCode, Cpu,
  type LucideIcon,
} from 'lucide-react'
import { useStore } from '../store'
import {
  getArchitecture, addComponent, updateComponent, deleteComponent,
  addDependency, removeDependency, listComponentFiles,
  inferDependencies, confirmDependency,
  getComponentMetrics, getComponentImpact,
  getFileContent, getFileSymbol,
} from '../api/archMapApi'
import type { Component, Dependency, FileMapping, Layer, ComponentMetrics, ComponentImpact, FileContent, SymbolExtract } from '../types'

// ── Constants ──────────────────────────────────────────────────────────────────

const LAYER_COLOR: Record<string, string> = {
  frontend: '#34d399', backend: '#60a5fa', database: '#fbbf24',
  infra: '#c084fc', shared: '#22d3ee', testing: '#f472b6', other: '#94a3b8',
}

const LAYER_ICON: Record<string, LucideIcon> = {
  frontend: Monitor, backend: Server, database: Database,
  infra: Cloud, shared: Share2, testing: FlaskConical, other: Box,
}

const LAYERS: Layer[] = ['frontend', 'backend', 'database', 'infra', 'shared', 'testing', 'other']
const NODE_W = 200
const NODE_H = 72

// ── Floating edge utilities ────────────────────────────────────────────────────
// Calculates the nearest border intersection point so edges connect from any side.

function getNodeCenter(node: InternalNode) {
  const w = node.measured?.width ?? NODE_W
  const h = node.measured?.height ?? NODE_H
  const p = node.internals.positionAbsolute
  return { x: p.x + w / 2, y: p.y + h / 2 }
}

function getNodeIntersection(node: InternalNode, target: InternalNode): { x: number; y: number } {
  const w = (node.measured?.width ?? NODE_W) / 2
  const h = (node.measured?.height ?? NODE_H) / 2
  const { x: cx, y: cy } = getNodeCenter(node)
  const { x: tx, y: ty } = getNodeCenter(target)

  const dx = (tx - cx) / (2 * w) - (ty - cy) / (2 * h)
  const dy = (tx - cx) / (2 * w) + (ty - cy) / (2 * h)
  const a = 1 / (Math.abs(dx) + Math.abs(dy) || 0.001)
  return { x: w * (a * dx + a * dy) + cx, y: h * (-(a * dx) + a * dy) + cy }
}

function getSideFromPoint(node: InternalNode, pt: { x: number; y: number }): Position {
  const nx = node.internals.positionAbsolute.x
  const ny = node.internals.positionAbsolute.y
  const nw = node.measured?.width ?? NODE_W
  const nh = node.measured?.height ?? NODE_H
  const px = Math.round(pt.x), py = Math.round(pt.y)
  if (px <= Math.round(nx) + 1) return Position.Left
  if (px >= Math.round(nx + nw) - 1) return Position.Right
  if (py <= Math.round(ny) + 1) return Position.Top
  return Position.Bottom
}

function getFloatingParams(source: InternalNode, target: InternalNode) {
  const sp = getNodeIntersection(source, target)
  const tp = getNodeIntersection(target, source)
  return { sx: sp.x, sy: sp.y, tx: tp.x, ty: tp.y, srcPos: getSideFromPoint(source, sp), tgtPos: getSideFromPoint(target, tp) }
}

// ── Custom Edge (floating + glow + animateMotion for auto deps) ─────────────

function FlowEdge({ id, source, target, data, markerEnd }: EdgeProps) {
  const srcNode = useInternalNode(source)
  const tgtNode = useInternalNode(target)
  if (!srcNode || !tgtNode) return null

  const { sx, sy, tx, ty, srcPos, tgtPos } = getFloatingParams(srcNode, tgtNode)
  const [path] = getBezierPath({ sourceX: sx, sourceY: sy, sourcePosition: srcPos, targetX: tx, targetY: ty, targetPosition: tgtPos })

  const isAuto = (data as any)?.confidence === 'auto'
  const color = isAuto ? '#64748b' : '#60a5fa'
  const filterId = `glow-${id}`

  return (
    <g>
      <defs>
        <filter id={filterId} x="-60%" y="-60%" width="220%" height="220%">
          <feGaussianBlur stdDeviation={isAuto ? 2 : 3} result="blur" />
          <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
      </defs>

      {/* Wide glow halo behind the line */}
      <path
        d={path} fill="none"
        stroke={color} strokeWidth={isAuto ? 5 : 8} strokeOpacity={0.12}
        filter={`url(#${filterId})`}
      />

      {/* Main edge line */}
      <path
        id={id}
        className="react-flow__edge-path rf-edge-main"
        d={path}
        fill="none"
        stroke={color}
        strokeWidth={isAuto ? 1.2 : 1.8}
        strokeDasharray={isAuto ? '6 4' : undefined}
        strokeOpacity={isAuto ? 0.6 : 0.9}
        markerEnd={markerEnd as string}
        style={{ color }}
      />

      {/* Animated travelling dot for auto/inferred edges */}
      {isAuto && (
        <circle r={3} fill={color} fillOpacity={0.85}>
          <animateMotion dur="2.4s" repeatCount="indefinite" path={path} />
        </circle>
      )}

      {/* Subtle pulse dot for confirmed edges */}
      {!isAuto && (
        <circle r={2.5} fill={color} fillOpacity={0.7}>
          <animateMotion dur="3s" repeatCount="indefinite" path={path} />
        </circle>
      )}
    </g>
  )
}

// ── Custom connection line (while dragging a new edge) ─────────────────────────

function ConnectionLine({ fromX, fromY, fromPosition, toX, toY, toPosition }: ConnectionLineComponentProps) {
  const [path] = getBezierPath({ sourceX: fromX, sourceY: fromY, sourcePosition: fromPosition, targetX: toX, targetY: toY, targetPosition: toPosition })
  return (
    <g>
      <path d={path} fill="none" stroke="#60a5fa" strokeWidth={1.5} strokeDasharray="5 3" strokeOpacity={0.7} />
      <circle cx={toX} cy={toY} r={4} fill="#60a5fa" fillOpacity={0.9}>
        <animate attributeName="r" values="3;5;3" dur="1s" repeatCount="indefinite" />
      </circle>
    </g>
  )
}

// ── Custom component node ──────────────────────────────────────────────────────

function ComponentNode({ data }: { data: any }) {
  const c = LAYER_COLOR[data.layer] || '#94a3b8'
  const Icon = LAYER_ICON[data.layer] ?? Box
  const isSelected: boolean = data.selected ?? false
  const expanded: boolean = data.expanded ?? false
  const loading: boolean = data.loading ?? false

  return (
    <div
      style={{
        position: 'relative',
        background: 'linear-gradient(145deg, rgba(20,30,50,0.92) 0%, rgba(10,16,30,0.95) 100%)',
        backdropFilter: 'blur(16px)',
        WebkitBackdropFilter: 'blur(16px)',
        border: `1px solid ${isSelected ? c + 'cc' : 'rgba(255,255,255,0.08)'}`,
        borderRadius: 16,
        minWidth: NODE_W,
        overflow: 'hidden',
        boxShadow: isSelected
          ? `0 0 0 1px ${c}55, 0 0 32px ${c}44, 0 8px 40px rgba(0,0,0,0.6)`
          : '0 4px 24px rgba(0,0,0,0.5), 0 0 0 1px rgba(255,255,255,0.05)',
        transition: 'box-shadow 0.25s ease, border-color 0.25s ease',
        animation: 'node-appear 0.22s ease both',
      }}
    >
      {/* Invisible handles on all 4 sides so any edge direction works */}
      <Handle type="target" position={Position.Top}    id="t" style={{ top: '50%', left: '50%' }} />
      <Handle type="target" position={Position.Left}   id="l" style={{ top: '50%', left: 0 }} />
      <Handle type="target" position={Position.Bottom} id="b" style={{ bottom: 0, left: '50%' }} />
      <Handle type="target" position={Position.Right}  id="r" style={{ top: '50%', right: 0 }} />
      <Handle type="source" position={Position.Top}    id="st" style={{ top: 0, left: '50%' }} />
      <Handle type="source" position={Position.Left}   id="sl" style={{ top: '50%', left: 0 }} />
      <Handle type="source" position={Position.Bottom} id="sb" style={{ bottom: 0, left: '50%' }} />
      <Handle type="source" position={Position.Right}  id="sr" style={{ top: '50%', right: 0 }} />

      {/* Colored gradient top stripe */}
      <div style={{ height: 3, background: `linear-gradient(90deg, ${c}ee 0%, ${c}44 80%, transparent 100%)` }} />

      {/* Shimmer sweep on selection */}
      {isSelected && (
        <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none', overflow: 'hidden', borderRadius: 'inherit' }}>
          <div style={{
            position: 'absolute', top: 0, left: '-100%', width: '60%', height: '100%',
            background: `linear-gradient(90deg, transparent, ${c}18, transparent)`,
            animation: 'shine 2s ease-in-out infinite',
          }} />
        </div>
      )}

      {/* Main header */}
      <div style={{ padding: '10px 14px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
          {/* Layer icon badge */}
          <div style={{
            width: 30, height: 30, borderRadius: 9, flexShrink: 0,
            background: `linear-gradient(135deg, ${c}28 0%, ${c}12 100%)`,
            border: `1px solid ${c}44`, display: 'flex', alignItems: 'center', justifyContent: 'center',
            boxShadow: isSelected ? `0 0 12px ${c}44` : 'none', transition: 'box-shadow 0.25s',
          }}>
            <Icon size={14} color={c} />
          </div>

          {/* Name */}
          <span style={{
            flex: 1, fontWeight: 700, fontSize: 12.5, lineHeight: 1.25,
            color: isSelected ? '#f0f7ff' : 'var(--text-primary)', letterSpacing: '-0.01em',
          }}>{data.label}</span>

          {/* Expand files as graph nodes */}
          <button
            onMouseDown={e => e.stopPropagation()}
            onClick={e => { e.stopPropagation(); data.onToggle?.() }}
            style={{
              background: expanded ? c + '22' : 'none',
              border: `1px solid ${expanded ? c + '55' : 'rgba(255,255,255,0.08)'}`,
              borderRadius: 6, cursor: 'pointer',
              color: expanded ? c : 'var(--text-muted)',
              padding: '2px 5px', display: 'flex', alignItems: 'center', gap: 3,
              transition: 'all 0.15s', fontSize: 8.5, fontWeight: 600,
            }}
            title={expanded ? 'Collapse file nodes' : 'Expand file nodes in graph'}
          >
            {loading
              ? <span className="spinner" style={{ width: 10, height: 10, borderWidth: 1.5 }} />
              : <><FileCode size={9} /><ChevronDown size={9} style={{ transform: expanded ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }} /></>
            }
          </button>
        </div>

        {/* Layer + confidence pills */}
        <div style={{ display: 'flex', gap: 5, marginTop: 8 }}>
          <span style={{
            display: 'inline-flex', alignItems: 'center',
            padding: '1px 8px', borderRadius: 99, fontSize: 9.5, fontWeight: 600,
            letterSpacing: '0.04em', textTransform: 'capitalize',
            background: c + '18', color: c, border: `1px solid ${c}33`,
          }}>{data.layer}</span>
          {data.confidence === 'auto' && (
            <span style={{
              display: 'inline-flex', alignItems: 'center',
              padding: '1px 8px', borderRadius: 99, fontSize: 9.5, fontWeight: 500,
              background: 'rgba(255,255,255,0.04)', color: 'var(--text-muted)',
              border: '1px solid rgba(255,255,255,0.08)', fontStyle: 'italic',
            }}>auto-detected</span>
          )}
        </div>
      </div>
    </div>
  )
}

// ── File node (expands from component; click opens FilePanel) ──────────────────

function FileNode({ data }: { data: any }) {
  const { file, parentColor } = data as { file: FileMapping; parentColor: string }
  const { description, functions, language } = file?.metadata ?? {}
  const basename = file?.file_path?.split(/[/\\]/).pop() ?? file?.file_path ?? ''
  const c = parentColor ?? '#64748b'
  const isSelected: boolean = data.selected ?? false
  const expanded: boolean = data.expanded ?? false
  const loading: boolean = data.loading ?? false
  const hasSymbols = Array.isArray(functions) && functions.length > 0

  return (
    <div style={{
      background: isSelected
        ? `linear-gradient(145deg, rgba(20,28,46,0.97), rgba(12,18,34,0.98))`
        : 'rgba(12,18,32,0.95)',
      backdropFilter: 'blur(12px)',
      border: `1px solid ${isSelected ? c + '88' : c + '33'}`,
      borderRadius: 10,
      width: 158,
      overflow: 'hidden',
      boxShadow: isSelected
        ? `0 0 0 1px ${c}44, 0 0 20px ${c}30, 0 4px 16px rgba(0,0,0,0.5)`
        : `0 2px 12px rgba(0,0,0,0.5), 0 0 0 1px rgba(255,255,255,0.04)`,
      animation: 'node-appear 0.18s ease both',
      transition: 'border-color 0.2s, box-shadow 0.2s',
      cursor: 'pointer',
    }}>
      <Handle type="target" position={Position.Top} id="t" style={{ opacity: 0 }} />
      <Handle type="source" position={Position.Bottom} id="b" style={{ opacity: 0 }} />

      {/* Micro top stripe */}
      <div style={{ height: 2, background: `linear-gradient(90deg, ${c}cc, transparent)` }} />

      <div style={{ padding: '6px 8px 7px' }}>
        {/* Filename row */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <FileCode size={9} color={c} style={{ flexShrink: 0, opacity: 0.8 }} />
          {language && (
            <span style={{
              fontSize: 7, fontWeight: 700, padding: '0 4px', borderRadius: 3,
              background: c + '22', color: c, fontFamily: 'monospace', flexShrink: 0,
            }}>{language}</span>
          )}
          <span style={{
            flex: 1, fontSize: 10, fontFamily: 'monospace', color: isSelected ? '#e8f4ff' : 'var(--text-primary)',
            fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          }}>{basename}</span>

          {/* Expand symbols button */}
          {hasSymbols && (
            <button
              onMouseDown={e => e.stopPropagation()}
              onClick={e => { e.stopPropagation(); data.onToggle?.() }}
              title={expanded ? 'Collapse symbols' : 'Expand functions/classes'}
              style={{
                background: expanded ? c + '22' : 'none',
                border: `1px solid ${expanded ? c + '55' : 'rgba(255,255,255,0.08)'}`,
                borderRadius: 4, cursor: 'pointer', padding: '1px 3px',
                color: expanded ? c : 'var(--text-muted)', display: 'flex', alignItems: 'center',
                flexShrink: 0, transition: 'all 0.15s',
              }}
            >
              {loading
                ? <span className="spinner" style={{ width: 8, height: 8, borderWidth: 1.5 }} />
                : <ChevronDown size={8} style={{ transform: expanded ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }} />
              }
            </button>
          )}
        </div>

        {/* Description — 2-line clamp; full text visible in FilePanel on click */}
        {description && (
          <div style={{
            fontSize: 8.5, color: 'var(--text-muted)', lineHeight: 1.45, marginTop: 4,
            display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden',
          } as React.CSSProperties}>{description}</div>
        )}

        {/* Click hint if selected */}
        {isSelected && (
          <div style={{ fontSize: 7.5, color: c, marginTop: 3, opacity: 0.7 }}>Click to view details →</div>
        )}
      </div>
    </div>
  )
}

// ── Symbol (function / class) leaf node ────────────────────────────────────────

function SymbolNode({ data }: { data: any }) {
  const { symbol, parentColor } = data as { symbol: string; parentColor: string }
  const c = parentColor ?? '#64748b'
  const isCls = !symbol.endsWith('()')
  const name = symbol.replace(/\(\)$/, '')
  return (
    <div style={{
      background: 'rgba(6,10,20,0.97)',
      border: `1px solid ${c}30`,
      borderRadius: 7,
      width: 136,
      overflow: 'hidden',
      boxShadow: `0 1px 8px rgba(0,0,0,0.5), 0 0 0 1px rgba(255,255,255,0.03)`,
      cursor: 'pointer',
      animation: 'node-appear 0.14s ease both',
      transition: 'border-color 0.15s',
    }}>
      <Handle type="target" position={Position.Top} id="t" style={{ opacity: 0 }} />
      <div style={{ height: 1.5, background: `linear-gradient(90deg, ${c}88, transparent)` }} />
      <div style={{ padding: '5px 9px', display: 'flex', alignItems: 'center', gap: 5 }}>
        <span style={{
          fontSize: 7, fontWeight: 800, padding: '1px 4px', borderRadius: 3, flexShrink: 0,
          background: isCls ? 'rgba(168,85,247,0.18)' : `${c}20`,
          color: isCls ? '#a855f7' : c, fontFamily: 'monospace', letterSpacing: '0.04em',
        }}>{isCls ? 'cls' : 'fn'}</span>
        <span style={{
          fontSize: 9.5, fontFamily: 'monospace', color: 'var(--text-secondary)',
          fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }} title={name}>{name}</span>
      </div>
    </div>
  )
}

// Register types outside component to avoid stale closures
const nodeTypes = { component: ComponentNode, file: FileNode, symbol: SymbolNode }
const edgeTypes = { floating: FlowEdge }

// ── Layout ─────────────────────────────────────────────────────────────────────

function layoutWithDagre(nodes: Node[], edges: Edge[]): Node[] {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: 'TB', nodesep: 80, ranksep: 120, marginx: 50, marginy: 50 })
  nodes.forEach(n => g.setNode(n.id, { width: NODE_W + 20, height: NODE_H + 20 }))
  edges.forEach(e => { try { g.setEdge(e.source, e.target) } catch { /* ignore duplicate */ } })
  dagre.layout(g)
  return nodes.map(n => {
    const gn = g.node(n.id)
    if (!gn) return n
    return { ...n, position: { x: gn.x - NODE_W / 2, y: gn.y - NODE_H / 2 } }
  })
}

// ── Main page ──────────────────────────────────────────────────────────────────

export default function ArchitecturePage() {
  const { projectPath, toast } = useStore()
  const [components, setComponents] = useState<Component[]>([])
  const [dependencies, setDependencies] = useState<Dependency[]>([])
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([])
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([])
  const [selected, setSelected] = useState<Component | null>(null)
  const [loading, setLoading] = useState(false)
  const [inferring, setInferring] = useState(false)
  const [showAdd, setShowAdd] = useState(false)
  const [expandedComponents, setExpandedComponents] = useState<Set<string>>(new Set())
  const [loadingComponents, setLoadingComponents] = useState<Set<string>>(new Set())
  const [expandedFiles, setExpandedFiles] = useState<Set<string>>(new Set())
  const [loadingFiles, setLoadingFiles] = useState<Set<string>>(new Set())
  const [filePanel, setFilePanel] = useState<{ file: FileMapping; nodeId: string } | null>(null)
  const [symbolPanel, setSymbolPanel] = useState<{ symbol: string; filePath: string } | null>(null)

  const graphKey = projectPath ? `archmap-graph::${btoa(projectPath)}` : null

  const load = useCallback(async () => {
    if (!projectPath) return

    // Read saved state SYNCHRONOUSLY before the first await — concurrent effects
    // (e.g. the expansion persistence useEffect) can overwrite localStorage while we await,
    // so capture the values now into local variables that won't be affected.
    const saved = graphKey ? JSON.parse(localStorage.getItem(graphKey) ?? '{}') : {}
    const savedPositions: Record<string, { x: number; y: number }> = saved.positions ?? {}
    const savedExpandedComponents: string[] = saved.expandedComponents ?? []
    const savedExpandedFiles: string[] = saved.expandedFiles ?? []

    setLoading(true)
    setFilePanel(null)
    setSymbolPanel(null)
    try {
      const arch = await getArchitecture(projectPath)
      setComponents(arch.components)
      setDependencies(arch.dependencies)
      const rawEdges = buildEdges(arch.dependencies)
      const rawNodes = buildNodes(arch.components)
      const laid = layoutWithDagre(rawNodes, rawEdges)

      // Restore component node positions
      const compNodes = laid.map(n =>
        savedPositions[n.id] ? { ...n, position: savedPositions[n.id] } : n
      )

      // Re-expand previously expanded components (fetch files from server)
      const allFileNodes: Node[] = []
      const allFileEdges: Edge[] = []
      const validExpandedComponents: string[] = []
      const validExpandedFiles = new Set<string>()

      for (const compId of savedExpandedComponents) {
        const parentNode = compNodes.find(n => n.id === compId)
        if (!parentNode) continue
        try {
          const files = await listComponentFiles(projectPath, compId)
          const parentColor = LAYER_COLOR[parentNode.data.layer as string] ?? '#94a3b8'
          const cols = 3
          const fw = 160, fh = 100, gap = 12
          const px = parentNode.position.x
          const py = parentNode.position.y
          const totalW = Math.min(files.length, cols) * (fw + gap) - gap
          const startX = px + (NODE_W - totalW) / 2

          const fileNodes: Node[] = files.map((f, i) => {
            const fileNodeId = `file::${compId}::${i}`
            const defaultPos = {
              x: startX + (i % cols) * (fw + gap),
              y: py + NODE_H + 60 + Math.floor(i / cols) * (fh + gap),
            }
            return {
              id: fileNodeId,
              type: 'file',
              position: savedPositions[fileNodeId] ?? defaultPos,
              data: { file: f, componentId: compId, parentColor },
              draggable: true,
              selectable: true,
            }
          })

          const fileEdges: Edge[] = files.map((_, i) => ({
            id: `fileedge::${compId}::${i}`,
            source: compId,
            target: `file::${compId}::${i}`,
            type: 'straight',
            style: { stroke: 'rgba(255,255,255,0.1)', strokeWidth: 1, strokeDasharray: '3 3' },
            selectable: false,
            focusable: false,
          }))

          allFileNodes.push(...fileNodes)
          allFileEdges.push(...fileEdges)
          validExpandedComponents.push(compId)

          // Re-expand previously expanded file nodes (symbols are built from metadata, no API needed)
          for (const fileNodeId of savedExpandedFiles) {
            if (!fileNodeId.startsWith(`file::${compId}::`)) continue
            const fileNode = fileNodes.find(n => n.id === fileNodeId)
            if (!fileNode) continue
            const file = fileNode.data?.file as FileMapping | undefined
            const symbols: string[] = file?.metadata?.functions ?? []
            if (symbols.length === 0) continue
            const { x: fpx, y: fpy } = fileNode.position
            const fParentColor = (fileNode.data?.parentColor as string) ?? '#64748b'
            const fFilePath = file?.file_path ?? ''
            const cols2 = 2, sw = 136, sh = 46, sgap = 6
            const totalW2 = Math.min(symbols.length, cols2) * (sw + sgap) - sgap
            const startX2 = fpx + (158 - totalW2) / 2

            const symNodes: Node[] = symbols.map((sym, i) => {
              const symNodeId = `sym::${fileNodeId}::${i}`
              return {
                id: symNodeId,
                type: 'symbol',
                position: savedPositions[symNodeId] ?? {
                  x: startX2 + (i % cols2) * (sw + sgap),
                  y: fpy + 108 + Math.floor(i / cols2) * (sh + sgap),
                },
                data: { symbol: sym, filePath: fFilePath, parentColor: fParentColor, fileNodeId },
                draggable: true, selectable: true,
              }
            })

            const symEdges: Edge[] = symbols.map((_, i) => ({
              id: `symedge::${fileNodeId}::${i}`,
              source: fileNodeId,
              target: `sym::${fileNodeId}::${i}`,
              type: 'straight',
              style: { stroke: `${fParentColor}28`, strokeWidth: 0.75, strokeDasharray: '2 3' },
              selectable: false, focusable: false,
            }))

            allFileNodes.push(...symNodes)
            allFileEdges.push(...symEdges)
            validExpandedFiles.add(fileNodeId)
          }
        } catch { /* skip this component's expansion if fetch fails */ }
      }

      setNodes([...compNodes, ...allFileNodes])
      setEdges([...rawEdges, ...allFileEdges])
      setExpandedComponents(new Set(validExpandedComponents))
      setExpandedFiles(validExpandedFiles)
    } catch (e: any) { toast('error', e.message) }
    finally { setLoading(false) }
  }, [projectPath, graphKey])

  useEffect(() => { load() }, [load])

  const toggleNode = useCallback(async (nodeId: string) => {
    // Collapse: remove file nodes + their symbol children
    if (expandedComponents.has(nodeId)) {
      setExpandedComponents(prev => { const s = new Set(prev); s.delete(nodeId); return s })
      setNodes(prev => {
        // Find file node IDs belonging to this component to also remove their symbols
        const fileNodeIds = prev.filter(n => n.id.startsWith(`file::${nodeId}::`)).map(n => n.id)
        return prev.filter(n =>
          !n.id.startsWith(`file::${nodeId}::`) &&
          !fileNodeIds.some(fid => n.id.startsWith(`sym::${fid}::`))
        )
      })
      setEdges(prev => {
        const filePrefix = `file::${nodeId}::`
        return prev.filter(e => !e.id.startsWith(`fileedge::${nodeId}::`) && !e.id.startsWith(`symedge::${filePrefix}`))
      })
      setExpandedFiles(prev => {
        const s = new Set(prev)
        // Remove any expanded file node IDs for this component
        for (const id of [...s]) { if (id.startsWith(`file::${nodeId}::`)) s.delete(id) }
        return s
      })
      return
    }

    setLoadingComponents(prev => new Set(prev).add(nodeId))
    try {
      const files = await listComponentFiles(projectPath, nodeId)

      setNodes(prev => {
        const parentNode = prev.find(n => n.id === nodeId)
        if (!parentNode) return prev
        const px = parentNode.position.x
        const py = parentNode.position.y
        const parentColor = LAYER_COLOR[parentNode.data.layer as string] ?? '#94a3b8'
        const cols = 3
        const fw = 160, fh = 100, gap = 12
        const totalW = Math.min(files.length, cols) * (fw + gap) - gap
        const startX = px + (NODE_W - totalW) / 2

        const fileNodes: Node[] = files.map((f, i) => ({
          id: `file::${nodeId}::${i}`,
          type: 'file',
          position: {
            x: startX + (i % cols) * (fw + gap),
            y: py + NODE_H + 60 + Math.floor(i / cols) * (fh + gap),
          },
          data: { file: f, componentId: nodeId, parentColor },
          draggable: true,
          selectable: true,
        }))
        return [...prev, ...fileNodes]
      })

      setEdges(prev => {
        const fileEdges: Edge[] = files.map((_, i) => ({
          id: `fileedge::${nodeId}::${i}`,
          source: nodeId,
          target: `file::${nodeId}::${i}`,
          type: 'straight',
          style: { stroke: 'rgba(255,255,255,0.1)', strokeWidth: 1, strokeDasharray: '3 3' },
          selectable: false,
          focusable: false,
        }))
        return [...prev, ...fileEdges]
      })

      setExpandedComponents(prev => new Set(prev).add(nodeId))
    } catch { /* silent */ }
    finally { setLoadingComponents(prev => { const s = new Set(prev); s.delete(nodeId); return s }) }
  }, [projectPath, expandedComponents])

  // Persist expansion state whenever it changes
  useEffect(() => {
    if (!graphKey) return
    const saved = JSON.parse(localStorage.getItem(graphKey) ?? '{}')
    saved.expandedComponents = [...expandedComponents]
    saved.expandedFiles = [...expandedFiles]
    localStorage.setItem(graphKey, JSON.stringify(saved))
  }, [expandedComponents, expandedFiles, graphKey])

  // Save all node positions to localStorage on drag stop
  const handleNodeDragStop = useCallback((_: React.MouseEvent, __: Node, allNodes: Node[]) => {
    if (!graphKey) return
    const saved = JSON.parse(localStorage.getItem(graphKey) ?? '{}')
    saved.positions = saved.positions ?? {}
    allNodes.forEach(n => { saved.positions[n.id] = n.position })
    localStorage.setItem(graphKey, JSON.stringify(saved))
  }, [graphKey])

  // Expand/collapse file → symbol nodes in graph
  const toggleFileNode = useCallback((fileNodeId: string) => {
    if (expandedFiles.has(fileNodeId)) {
      setExpandedFiles(prev => { const s = new Set(prev); s.delete(fileNodeId); return s })
      setNodes(prev => prev.filter(n => !n.id.startsWith(`sym::${fileNodeId}::`)))
      setEdges(prev => prev.filter(e => !e.id.startsWith(`symedge::${fileNodeId}::`)))
      return
    }
    setNodes(prev => {
      const fileNode = prev.find(n => n.id === fileNodeId)
      if (!fileNode) return prev
      const file = fileNode.data?.file as FileMapping | undefined
      const symbols: string[] = file?.metadata?.functions ?? []
      if (symbols.length === 0) return prev
      const { x: px, y: py } = fileNode.position
      const parentColor = (fileNode.data?.parentColor as string) ?? '#64748b'
      const filePath = file?.file_path ?? ''
      const cols = 2
      const sw = 136, sh = 46, gap = 6
      const totalW = Math.min(symbols.length, cols) * (sw + gap) - gap
      const startX = px + (158 - totalW) / 2
      const symNodes: Node[] = symbols.map((sym, i) => ({
        id: `sym::${fileNodeId}::${i}`,
        type: 'symbol',
        position: {
          x: startX + (i % cols) * (sw + gap),
          y: py + 108 + Math.floor(i / cols) * (sh + gap),
        },
        data: { symbol: sym, filePath, parentColor, fileNodeId },
        draggable: true, selectable: true,
      }))
      return [...prev, ...symNodes]
    })
    setEdges(prev => {
      // Get symbol count from current nodes to build edges
      const file = nodes.find(n => n.id === fileNodeId)?.data?.file as FileMapping | undefined
      const count = file?.metadata?.functions?.length ?? 0
      const parentColor = (nodes.find(n => n.id === fileNodeId)?.data?.parentColor as string) ?? '#64748b'
      const symEdges: Edge[] = Array.from({ length: count }, (_, i) => ({
        id: `symedge::${fileNodeId}::${i}`,
        source: fileNodeId,
        target: `sym::${fileNodeId}::${i}`,
        type: 'straight',
        style: { stroke: `${parentColor}28`, strokeWidth: 0.75, strokeDasharray: '2 3' },
        selectable: false, focusable: false,
      }))
      return [...prev, ...symEdges]
    })
    setExpandedFiles(prev => new Set(prev).add(fileNodeId))
  }, [expandedFiles, nodes])

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
    if (node.type === 'component') {
      setSelected(components.find(c => c.id === node.id) ?? null)
      setFilePanel(null)
      setSymbolPanel(null)
    } else if (node.type === 'file') {
      setSelected(null)
      setSymbolPanel(null)
      setFilePanel({ file: node.data.file as FileMapping, nodeId: node.id })
    } else if (node.type === 'symbol') {
      setSelected(null)
      setFilePanel(null)
      setSymbolPanel({ symbol: node.data.symbol as string, filePath: node.data.filePath as string })
    }
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

  const handleEdgeClick = useCallback(async (_e: React.MouseEvent, edge: Edge) => {
    if (!projectPath || !edge.id) return
    if (edge.id.startsWith('fileedge::')) return  // ignore file-to-node edges
    if ((edge.data as any)?.confidence === 'auto') {
      try {
        const confirmed = await confirmDependency(projectPath, edge.id)
        setDependencies(deps => deps.map(d => d.id === edge.id ? { ...d, confidence: 'confirmed' as const } : d))
        setEdges(eds => eds.map(e => e.id === edge.id ? depToEdge({ ...confirmed, confidence: 'confirmed' }) : e))
        toast('success', 'Dependency confirmed')
      } catch (e: any) { toast('error', e.message) }
    } else {
      try {
        await removeDependency(projectPath, edge.id)
        setEdges(eds => eds.filter(e => e.id !== edge.id))
        toast('success', 'Dependency removed')
      } catch (e: any) { toast('error', e.message) }
    }
  }, [projectPath])

  const handleInfer = useCallback(async () => {
    if (!projectPath) return
    setInferring(true)
    try {
      const result = await inferDependencies(projectPath)
      if (result.added > 0) {
        setDependencies(prev => [...prev, ...result.dependencies])
        setEdges(prev => [...prev, ...result.dependencies.map(depToEdge)])
        toast('success', `${result.added} dep${result.added !== 1 ? 's' : ''} inferred — click dashed edges to confirm`)
      } else {
        toast('success', 'No new dependencies found')
      }
      if (result.unmapped.length > 0) {
        toast('info' as any, `${result.unmapped.length} file${result.unmapped.length !== 1 ? 's' : ''} not yet mapped`)
      }
    } catch (e: any) { toast('error', e.message) }
    finally { setInferring(false) }
  }, [projectPath])

  if (!projectPath) return <EmptyState />

  return (
    <div style={{ display: 'flex', height: '100%', overflow: 'hidden' }}>
      <div style={{ flex: 1, position: 'relative' }}>
        {loading && (
          <div style={{
            position: 'absolute', inset: 0, zIndex: 10,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: 'rgba(8,12,20,0.7)', backdropFilter: 'blur(6px)',
          }}>
            <span className="spinner spinner-lg" />
          </div>
        )}

        <ReactFlow
          nodes={nodes.map(n => {
            if (n.type === 'component') return {
              ...n,
              data: {
                ...n.data,
                selected: n.id === selected?.id,
                expanded: expandedComponents.has(n.id),
                loading: loadingComponents.has(n.id),
                onToggle: () => toggleNode(n.id),
              },
            }
            if (n.type === 'file') return {
              ...n,
              selectable: true,
              data: {
                ...n.data,
                selected: filePanel?.nodeId === n.id,
                expanded: expandedFiles.has(n.id),
                loading: loadingFiles.has(n.id),
                onToggle: () => toggleFileNode(n.id),
              },
            }
            return n  // symbol nodes — data already set at creation
          })}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onNodeClick={handleSelectNode}
          onNodeDragStop={handleNodeDragStop}
          onEdgeClick={handleEdgeClick}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          connectionLineComponent={ConnectionLine}
          fitView
          fitViewOptions={{ padding: 0.3 }}
          minZoom={0.2}
          maxZoom={2.5}
          style={{ background: 'transparent' }}
          deleteKeyCode={null}
          defaultEdgeOptions={{
            type: 'floating',
            markerEnd: { type: MarkerType.ArrowClosed, width: 10, height: 10 },
          }}
        >
          {/* Canvas background — radial gradient + dot pattern */}
          <Background
            variant={BackgroundVariant.Dots}
            gap={32}
            size={1.2}
            color="rgba(255,255,255,0.04)"
            style={{ background: 'radial-gradient(ellipse 80% 60% at 50% 40%, #0d1829 0%, #080c14 100%)' }}
          />

          <Controls
            showInteractive={false}
            style={{
              background: 'rgba(13,20,33,0.85)', backdropFilter: 'blur(10px)',
              border: '1px solid rgba(255,255,255,0.08)',
              borderRadius: 12, overflow: 'hidden',
              boxShadow: '0 4px 20px rgba(0,0,0,0.4)',
            }}
          />
          <MiniMap
            style={{
              background: 'rgba(13,20,33,0.85)', backdropFilter: 'blur(10px)',
              border: '1px solid rgba(255,255,255,0.08)',
              borderRadius: 12, overflow: 'hidden',
            }}
            nodeColor={n => LAYER_COLOR[(n as any).data?.layer] || '#64748b'}
            maskColor="rgba(8,12,20,0.8)"
            nodeStrokeWidth={0}
          />

          {/* Toolbar */}
          <Panel position="top-left">
            <div style={{
              display: 'flex', gap: 6, padding: '6px 8px',
              background: 'rgba(13,20,33,0.85)', backdropFilter: 'blur(12px)',
              border: '1px solid rgba(255,255,255,0.08)',
              borderRadius: 12, boxShadow: '0 4px 20px rgba(0,0,0,0.4)',
            }}>
              <button className="btn btn-primary btn-sm" onClick={() => setShowAdd(true)}>
                <Plus size={12} /> Component
              </button>
              <div style={{ width: 1, background: 'rgba(255,255,255,0.08)', margin: '0 2px' }} />
              <button className="btn btn-ghost btn-sm" onClick={load}>Refresh</button>
              <button
                className="btn btn-ghost btn-sm"
                onClick={handleInfer}
                disabled={inferring}
                title="Auto-detect imports between components"
              >
                {inferring ? <span className="spinner" /> : <><GitBranch size={12} /> Infer Deps</>}
              </button>
            </div>
          </Panel>

          {/* Legend */}
          <Panel position="top-right">
            <div style={{
              background: 'rgba(13,20,33,0.85)', backdropFilter: 'blur(12px)',
              border: '1px solid rgba(255,255,255,0.08)',
              borderRadius: 12, padding: '12px 16px', margin: 8,
              boxShadow: '0 4px 20px rgba(0,0,0,0.4)', minWidth: 168,
            }}>
              <p style={{ fontSize: 9, fontWeight: 700, color: 'rgba(255,255,255,0.3)', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 10 }}>Layers</p>
              {Object.entries(LAYER_COLOR).map(([layer, color]) => {
                const Icon = LAYER_ICON[layer] ?? Box
                return (
                  <div key={layer} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                    <div style={{ width: 18, height: 18, borderRadius: 5, background: color + '22', border: `1px solid ${color}44`, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                      <Icon size={10} color={color} />
                    </div>
                    <span style={{ fontSize: 11, color: 'rgba(255,255,255,0.55)', textTransform: 'capitalize' }}>{layer}</span>
                  </div>
                )
              })}

              <div style={{ height: 1, background: 'rgba(255,255,255,0.06)', margin: '10px 0' }} />
              <p style={{ fontSize: 9, fontWeight: 700, color: 'rgba(255,255,255,0.3)', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 8 }}>Edges</p>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                <svg width="24" height="8"><line x1="0" y1="4" x2="24" y2="4" stroke="#60a5fa" strokeWidth="2" /><circle cx="16" cy="4" r="2.5" fill="#60a5fa" /></svg>
                <span style={{ fontSize: 10.5, color: 'rgba(255,255,255,0.45)' }}>confirmed</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                <svg width="24" height="8"><line x1="0" y1="4" x2="24" y2="4" stroke="#64748b" strokeWidth="1.5" strokeDasharray="5 3" /></svg>
                <span style={{ fontSize: 10.5, color: 'rgba(255,255,255,0.45)' }}>inferred · click to confirm</span>
              </div>

              <div style={{ height: 1, background: 'rgba(255,255,255,0.06)', margin: '0 0 10px' }} />
              <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginBottom: 6 }}>
                <Cpu size={9} color="rgba(255,255,255,0.3)" />
                <p style={{ fontSize: 9, fontWeight: 700, color: 'rgba(255,255,255,0.3)', textTransform: 'uppercase', letterSpacing: '0.1em' }}>How Inference Works</p>
              </div>
              <p style={{ fontSize: 9.5, color: 'rgba(255,255,255,0.35)', lineHeight: 1.65 }}>
                Static import analysis — no AI.<br />
                Python: exact AST parsing.<br />
                TS/JS: relative import regex.<br />
                Misses: dynamic imports, aliases.<br />
                <span style={{ color: 'rgba(255,255,255,0.22)' }}>Click dashed edge → confirm or remove.</span>
              </p>

              <div style={{ height: 1, background: 'rgba(255,255,255,0.06)', margin: '10px 0' }} />
              <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginBottom: 6 }}>
                <FileCode size={9} color="rgba(255,255,255,0.3)" />
                <p style={{ fontSize: 9, fontWeight: 700, color: 'rgba(255,255,255,0.3)', textTransform: 'uppercase', letterSpacing: '0.1em' }}>File Nodes</p>
              </div>
              <p style={{ fontSize: 9.5, color: 'rgba(255,255,255,0.35)', lineHeight: 1.65 }}>
                Click <FileCode size={8} style={{ display: 'inline', verticalAlign: 'middle' }} /> on a component<br />
                to expand its files as graph nodes.<br />
                Annotate via <code style={{ fontSize: 8, opacity: 0.6 }}>annotate_file</code> MCP tool<br />
                or Scan to auto-detect.
              </p>
            </div>
          </Panel>
        </ReactFlow>
      </div>

      {/* Side panels — only one at a time */}
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
      {!selected && filePanel && (
        <FilePanel
          file={filePanel.file}
          projectPath={projectPath}
          onClose={() => setFilePanel(null)}
        />
      )}
      {!selected && !filePanel && symbolPanel && (
        <SymbolPanel
          symbol={symbolPanel.symbol}
          filePath={symbolPanel.filePath}
          projectPath={projectPath}
          onClose={() => setSymbolPanel(null)}
        />
      )}

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

// ── Side panel ─────────────────────────────────────────────────────────────────

function ComponentPanel({ comp, projectPath, deps, components, onClose, onDelete, onUpdated, toast }: any) {
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState({ name: comp.name, description: comp.description, layer: comp.layer })
  const [metrics, setMetrics] = useState<ComponentMetrics | null>(null)
  const [impact, setImpact] = useState<ComponentImpact | null>(null)
  const c = LAYER_COLOR[comp.layer] || '#94a3b8'
  const Icon = LAYER_ICON[comp.layer] ?? Box

  useEffect(() => {
    setForm({ name: comp.name, description: comp.description, layer: comp.layer })
    setEditing(false)
    setMetrics(null)
    setImpact(null)
    // Fetch metrics and impact in parallel
    getComponentMetrics(projectPath, comp.id).then(setMetrics).catch(() => {})
    getComponentImpact(projectPath, comp.id).then(setImpact).catch(() => {})
  }, [comp.id, projectPath])

  const nameMap: Record<string, string> = {}
  components.forEach((cc: Component) => { nameMap[cc.id] = cc.name })
  const connectedDeps = deps.filter((d: Dependency) => d.from_component === comp.id || d.to_component === comp.id)

  const handleSave = async () => {
    try {
      await updateComponent(projectPath, comp.id, form)
      toast('success', 'Updated')
      setEditing(false)
      onUpdated()
    } catch (e: any) { toast('error', e.message) }
  }

  return (
    <div style={{
      width: 300, flexShrink: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden',
      background: 'rgba(10,16,28,0.97)', borderLeft: '1px solid rgba(255,255,255,0.07)',
      backdropFilter: 'blur(20px)',
    }}>
      {/* Colored top bar */}
      <div style={{ height: 3, background: `linear-gradient(90deg, ${c}ee, ${c}33)` }} />

      <div style={{ padding: '14px 18px', borderBottom: '1px solid rgba(255,255,255,0.07)', display: 'flex', alignItems: 'center', gap: 9 }}>
        <div style={{ width: 32, height: 32, borderRadius: 9, background: c + '22', border: `1px solid ${c}44`, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, boxShadow: `0 0 12px ${c}33` }}>
          <Icon size={15} color={c} />
        </div>
        <span style={{ flex: 1, fontWeight: 700, fontSize: 13.5, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{comp.name}</span>
        <button onClick={() => setEditing(!editing)} style={{ background: editing ? c + '22' : 'none', border: `1px solid ${editing ? c + '55' : 'transparent'}`, borderRadius: 6, cursor: 'pointer', color: editing ? c : 'var(--text-muted)', padding: 5 }}>
          <Edit2 size={13} />
        </button>
        <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', padding: 5 }}>
          <X size={13} />
        </button>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: 18 }}>
        {editing ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <Field label="Name"><input type="text" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} /></Field>
            <Field label="Layer">
              <select value={form.layer} onChange={e => setForm(f => ({ ...f, layer: e.target.value }))}>
                {LAYERS.map(l => <option key={l} value={l}>{l}</option>)}
              </select>
            </Field>
            <Field label="Description">
              <textarea value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} style={{ minHeight: 70 }} />
            </Field>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="btn btn-primary btn-sm" onClick={handleSave}><Check size={12} /> Save</button>
              <button className="btn btn-ghost btn-sm" onClick={() => setEditing(false)}>Cancel</button>
            </div>
          </div>
        ) : (
          <>
            <Section icon={<Info size={11} />} label="Details">
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 10 }}>
                <span style={{ padding: '2px 9px', borderRadius: 99, fontSize: 10.5, fontWeight: 600, background: c + '1a', color: c, border: `1px solid ${c}44` }}>{comp.layer}</span>
                <span style={{ padding: '2px 9px', borderRadius: 99, fontSize: 10.5, background: 'rgba(255,255,255,0.05)', color: 'var(--text-muted)', border: '1px solid rgba(255,255,255,0.08)' }}>{comp.confidence}</span>
              </div>
              {comp.description && <p style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.65, marginBottom: 8 }}>{comp.description}</p>}
              {/* Expand hint */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '5px 9px', borderRadius: 7, background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.07)', marginBottom: 8 }}>
                <FileCode size={10} color={c} style={{ flexShrink: 0 }} />
                <span style={{ fontSize: 9.5, color: 'var(--text-muted)', lineHeight: 1.5 }}>
                  Click <strong style={{ color: 'var(--text-secondary)' }}>▾</strong> on the node to expand its mapped files as graph nodes.
                </span>
              </div>
              <p style={{ fontSize: 9, color: 'var(--text-muted)', fontFamily: 'monospace', opacity: 0.5 }}>{comp.id}</p>
            </Section>

            {comp.tags.length > 0 && (
              <Section icon={<Tag size={11} />} label="Tags">
                <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap' }}>
                  {comp.tags.map((t: string) => (
                    <span key={t} style={{ padding: '2px 8px', borderRadius: 4, fontSize: 10.5, background: 'rgba(255,255,255,0.05)', color: 'var(--text-secondary)', border: '1px solid rgba(255,255,255,0.08)' }}>{t}</span>
                  ))}
                </div>
              </Section>
            )}

            {/* ── Code Quality Metrics ─────────────────────────────── */}
            <Section icon={<Activity size={11} />} label="Code Quality">
              {metrics == null ? (
                <div style={{ display: 'flex', justifyContent: 'center', padding: '8px 0' }}><span className="spinner" /></div>
              ) : (
                <>
                  {metrics.hotspot && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '5px 9px', marginBottom: 10, borderRadius: 7, background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.25)', color: '#ef4444', fontSize: 10.5, fontWeight: 600 }}>
                      <AlertTriangle size={11} /> Hotspot — high churn &amp; complexity
                    </div>
                  )}
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, marginBottom: 8 }}>
                    {[
                      { label: 'Files', value: metrics.file_count },
                      { label: 'Lines', value: metrics.total_lines.toLocaleString() },
                      { label: 'Complexity', value: metrics.avg_complexity, title: 'avg keyword complexity' },
                      { label: 'Git churn', value: metrics.total_churn, title: 'total commits touching files' },
                    ].map(({ label, value, title }) => (
                      <div key={label} title={title} style={{ padding: '7px 10px', borderRadius: 8, background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)', textAlign: 'center' }}>
                        <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)', fontVariantNumeric: 'tabular-nums' }}>{value}</div>
                        <div style={{ fontSize: 9, color: 'var(--text-muted)', marginTop: 2, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{label}</div>
                      </div>
                    ))}
                  </div>
                  {metrics.files.filter(f => f.hotspot).length > 0 && (
                    <div>
                      {metrics.files.filter(f => f.hotspot).map(f => (
                        <div key={f.file_path} style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '3px 6px', borderRadius: 5, background: 'rgba(239,68,68,0.07)', marginBottom: 3 }}>
                          <AlertTriangle size={9} color="#ef4444" style={{ flexShrink: 0 }} />
                          <span style={{ fontSize: 9.5, fontFamily: 'monospace', color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {f.file_path.split(/[/\\]/).pop()}
                          </span>
                          <span style={{ fontSize: 8.5, color: 'var(--text-muted)', flexShrink: 0, marginLeft: 'auto' }}>{f.churn}c</span>
                        </div>
                      ))}
                    </div>
                  )}
                </>
              )}
            </Section>

            {/* ── Impact Analysis ──────────────────────────────────── */}
            <Section icon={<Zap size={11} />} label="Impact Analysis">
              {impact == null ? (
                <div style={{ display: 'flex', justifyContent: 'center', padding: '8px 0' }}><span className="spinner" /></div>
              ) : (
                <>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, marginBottom: 10 }}>
                    <div style={{ padding: '7px 10px', borderRadius: 8, background: 'rgba(239,68,68,0.07)', border: '1px solid rgba(239,68,68,0.15)', textAlign: 'center' }} title="Components that would be affected if this one changes">
                      <div style={{ fontSize: 14, fontWeight: 700, color: '#f87171', fontVariantNumeric: 'tabular-nums' }}>{impact.upstream.length}</div>
                      <div style={{ fontSize: 9, color: 'var(--text-muted)', marginTop: 2, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Dependents</div>
                    </div>
                    <div style={{ padding: '7px 10px', borderRadius: 8, background: 'rgba(96,165,250,0.07)', border: '1px solid rgba(96,165,250,0.15)', textAlign: 'center' }} title="Components this one depends on">
                      <div style={{ fontSize: 14, fontWeight: 700, color: '#60a5fa', fontVariantNumeric: 'tabular-nums' }}>{impact.downstream.length}</div>
                      <div style={{ fontSize: 9, color: 'var(--text-muted)', marginTop: 2, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Dependencies</div>
                    </div>
                  </div>
                  {impact.cycles.length > 0 && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '5px 9px', marginBottom: 8, borderRadius: 7, background: 'rgba(245,158,11,0.1)', border: '1px solid rgba(245,158,11,0.25)', color: '#f59e0b', fontSize: 10.5, fontWeight: 600 }}>
                      <AlertTriangle size={11} /> Circular dependency detected
                    </div>
                  )}
                  {impact.upstream.length > 0 && (
                    <div style={{ marginBottom: 8 }}>
                      <div style={{ fontSize: 9, fontWeight: 700, color: '#f87171', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 4 }}>Breaks if changed</div>
                      {impact.upstream.slice(0, 5).map(id => (
                        <div key={id} style={{ fontSize: 10.5, color: 'var(--text-secondary)', padding: '2px 6px', borderRadius: 4, background: 'rgba(248,113,113,0.06)', marginBottom: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {nameMap[id] ?? id}
                        </div>
                      ))}
                      {impact.upstream.length > 5 && <div style={{ fontSize: 9, color: 'var(--text-muted)', marginTop: 2 }}>+{impact.upstream.length - 5} more</div>}
                    </div>
                  )}
                  {impact.is_leaf && impact.is_root && (
                    <p style={{ fontSize: 10.5, color: 'var(--text-muted)' }}>Isolated — no dependencies.</p>
                  )}
                </>
              )}
            </Section>

            <Section icon={<GitBranch size={11} />} label={`Connections (${connectedDeps.length})`}>
              {connectedDeps.length === 0
                ? <p style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>No connections yet. Drag between nodes to connect.</p>
                : connectedDeps.map((d: Dependency) => {
                  const isOut = d.from_component === comp.id
                  const other = nameMap[isOut ? d.to_component : d.from_component] ?? '?'
                  const otherComp = components.find((cc: Component) => cc.id === (isOut ? d.to_component : d.from_component))
                  const dc = LAYER_COLOR[otherComp?.layer ?? 'other']
                  return (
                    <div key={d.id} style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 5, padding: '5px 8px', background: 'rgba(255,255,255,0.03)', borderRadius: 7, border: '1px solid rgba(255,255,255,0.06)' }}>
                      <ChevronRight size={10} color={isOut ? '#60a5fa' : 'var(--text-muted)'} style={{ transform: isOut ? 'none' : 'rotate(180deg)', flexShrink: 0 }} />
                      <div style={{ width: 6, height: 6, borderRadius: '50%', background: dc, flexShrink: 0, boxShadow: `0 0 5px ${dc}` }} />
                      <span style={{ fontSize: 11.5, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{other}</span>
                      <span style={{ fontSize: 9, color: 'var(--text-muted)', flexShrink: 0 }}>{d.label}</span>
                    </div>
                  )
                })
              }
            </Section>
          </>
        )}
      </div>

      <div style={{ padding: '12px 18px', borderTop: '1px solid rgba(255,255,255,0.07)' }}>
        <button className="btn btn-danger btn-sm" onClick={onDelete} style={{ width: '100%', justifyContent: 'center' }}>
          <Trash2 size={12} /> Delete Component
        </button>
      </div>
    </div>
  )
}

// ── File panel (shows on file node click) ──────────────────────────────────────

function FilePanel({ file, projectPath, onClose }: { file: FileMapping; projectPath: string; onClose: () => void }) {
  const [content, setContent] = useState<FileContent | null>(null)
  const [loadingContent, setLoadingContent] = useState(false)
  const { description, functions, language } = file.metadata ?? {}
  const basename = file.file_path.split(/[/\\]/).pop() ?? file.file_path
  const ext = file.file_path.split('.').pop() ?? ''
  const langColor = language === 'python' ? '#60a5fa'
    : language === 'typescript' ? '#34d399'
    : language === 'javascript' ? '#fbbf24'
    : language === 'html' ? '#f87171'
    : '#94a3b8'

  useEffect(() => {
    setContent(null)
    setLoadingContent(true)
    getFileContent(projectPath, file.file_path)
      .then(setContent)
      .catch(() => setContent(null))
      .finally(() => setLoadingContent(false))
  }, [file.file_path, projectPath])

  return (
    <div style={{
      width: 360, flexShrink: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden',
      background: 'rgba(8,13,24,0.98)', borderLeft: '1px solid rgba(255,255,255,0.07)',
      backdropFilter: 'blur(20px)',
    }}>
      <div style={{ height: 2, background: `linear-gradient(90deg, ${langColor}cc, transparent)` }} />

      {/* Header */}
      <div style={{ padding: '12px 16px', borderBottom: '1px solid rgba(255,255,255,0.07)', display: 'flex', alignItems: 'center', gap: 8 }}>
        <FileCode size={14} color={langColor} style={{ flexShrink: 0 }} />
        <div style={{ flex: 1, overflow: 'hidden' }}>
          <div style={{ fontWeight: 700, fontSize: 12.5, fontFamily: 'monospace', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{basename}</div>
          <div style={{ fontSize: 9, color: 'var(--text-muted)', fontFamily: 'monospace', marginTop: 1 }}>{file.file_path}</div>
        </div>
        <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', padding: 4 }}><X size={13} /></button>
      </div>

      <div style={{ flex: 1, overflowY: 'auto' }}>
        {/* Description — full, untruncated */}
        {description && (
          <div style={{ padding: '12px 16px', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
            <div style={{ fontSize: 9, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 6 }}>Description</div>
            <p style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.7 }}>{description}</p>
          </div>
        )}

        {/* Functions/classes */}
        {functions && functions.length > 0 && (
          <div style={{ padding: '10px 16px', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
            <div style={{ fontSize: 9, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8 }}>
              Functions & Classes ({functions.length}) — click node to view code
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
              {(functions as string[]).map((fn, i) => {
                const isCls = !fn.endsWith('()')
                return (
                  <span key={i} style={{
                    fontSize: 9.5, fontFamily: 'monospace', padding: '2px 7px', borderRadius: 5,
                    background: isCls ? 'rgba(168,85,247,0.12)' : `${langColor}14`,
                    color: isCls ? '#a855f7' : langColor,
                    border: `1px solid ${isCls ? 'rgba(168,85,247,0.25)' : langColor + '33'}`,
                  }}>{fn}</span>
                )
              })}
            </div>
          </div>
        )}

        {/* File meta */}
        <div style={{ padding: '10px 16px', borderBottom: '1px solid rgba(255,255,255,0.05)', display: 'flex', gap: 12 }}>
          {language && <span style={{ fontSize: 10, color: langColor, fontWeight: 600 }}>{language}</span>}
          {content && <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>{content.lines} lines</span>}
          <span style={{ fontSize: 10, color: 'var(--text-muted)', marginLeft: 'auto', opacity: 0.5 }}>{file.mapped_by}</span>
        </div>

        {/* File content */}
        <div style={{ padding: '10px 16px' }}>
          <div style={{ fontSize: 9, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8 }}>Source</div>
          {loadingContent ? (
            <div style={{ display: 'flex', justifyContent: 'center', padding: 16 }}><span className="spinner" /></div>
          ) : content ? (
            <pre style={{
              margin: 0, padding: '12px 14px', borderRadius: 8,
              background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)',
              fontSize: 10, fontFamily: 'monospace', color: 'var(--text-secondary)',
              lineHeight: 1.6, overflowX: 'auto', whiteSpace: 'pre', maxHeight: 480,
              overflowY: 'auto',
            }}>{content.content}</pre>
          ) : (
            <p style={{ fontSize: 10.5, color: 'var(--text-muted)' }}>Could not load file.</p>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Symbol panel (shows on function/class node click) ──────────────────────────

function SymbolPanel({ symbol, filePath, projectPath, onClose }: { symbol: string; filePath: string; projectPath: string; onClose: () => void }) {
  const [data, setData] = useState<SymbolExtract | null>(null)
  const [loading, setLoading] = useState(false)
  const isCls = !symbol.endsWith('()')
  const name = symbol.replace(/\(\)$/, '')
  const ext = filePath.split('.').pop() ?? ''
  const langColor = ext === 'py' ? '#60a5fa' : ext === 'ts' || ext === 'tsx' ? '#34d399' : '#fbbf24'

  useEffect(() => {
    setData(null)
    setLoading(true)
    getFileSymbol(projectPath, filePath, symbol)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [symbol, filePath, projectPath])

  return (
    <div style={{
      width: 400, flexShrink: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden',
      background: 'rgba(8,13,24,0.98)', borderLeft: '1px solid rgba(255,255,255,0.07)',
      backdropFilter: 'blur(20px)',
    }}>
      <div style={{ height: 2, background: `linear-gradient(90deg, ${isCls ? '#a855f7' : langColor}cc, transparent)` }} />

      {/* Header */}
      <div style={{ padding: '12px 16px', borderBottom: '1px solid rgba(255,255,255,0.07)', display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{
          fontSize: 8, fontWeight: 800, padding: '2px 6px', borderRadius: 4,
          background: isCls ? 'rgba(168,85,247,0.18)' : `${langColor}20`,
          color: isCls ? '#a855f7' : langColor, fontFamily: 'monospace', flexShrink: 0,
        }}>{isCls ? 'class' : 'function'}</span>
        <div style={{ flex: 1, overflow: 'hidden' }}>
          <div style={{ fontWeight: 700, fontSize: 13, fontFamily: 'monospace', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{name}</div>
          <div style={{ fontSize: 9, color: 'var(--text-muted)', fontFamily: 'monospace', marginTop: 1 }}>{filePath}</div>
        </div>
        <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', padding: 4 }}><X size={13} /></button>
      </div>

      {/* Line range */}
      {data && (data.start_line > 0) && (
        <div style={{ padding: '6px 16px', borderBottom: '1px solid rgba(255,255,255,0.05)', fontSize: 9.5, color: 'var(--text-muted)' }}>
          Lines {data.start_line}–{data.end_line} · {data.language}
          {data.fallback && <span style={{ color: '#f59e0b', marginLeft: 8 }}>⚠ approximate match</span>}
        </div>
      )}

      {/* Code */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '12px 16px' }}>
        {loading ? (
          <div style={{ display: 'flex', justifyContent: 'center', padding: 24 }}><span className="spinner spinner-lg" /></div>
        ) : data?.code ? (
          <pre style={{
            margin: 0, padding: '14px 16px', borderRadius: 10,
            background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.07)',
            fontSize: 11, fontFamily: 'monospace', color: '#c9d9f0',
            lineHeight: 1.65, overflowX: 'auto', whiteSpace: 'pre',
          }}>{data.code}</pre>
        ) : (
          <p style={{ fontSize: 11, color: 'var(--text-muted)' }}>Could not extract source code.</p>
        )}
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
        name: form.name.trim(), layer: form.layer,
        description: form.description,
        tags: form.tags.split(',').map(t => t.trim()).filter(Boolean),
      })
      toast('success', `"${form.name}" added`)
      onAdded()
      onClose()
    } catch (e: any) { toast('error', e.message) }
    finally { setLoading(false) }
  }

  return (
    <Modal title="Add Component" onClose={onClose}>
      <form onSubmit={handleSubmit}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <Field label="Name *"><input type="text" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} placeholder="e.g. Auth Service" autoFocus /></Field>
          <Field label="Layer">
            <select value={form.layer} onChange={e => setForm(f => ({ ...f, layer: e.target.value as Layer }))}>
              {LAYERS.map(l => <option key={l} value={l}>{l}</option>)}
            </select>
          </Field>
          <Field label="Description"><textarea value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} placeholder="What does this component do?" /></Field>
          <Field label="Tags (comma-separated)"><input type="text" value={form.tags} onChange={e => setForm(f => ({ ...f, tags: e.target.value }))} placeholder="api, auth, jwt" /></Field>
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

// ── Data helpers ───────────────────────────────────────────────────────────────

function buildNodes(components: Component[]): Node[] {
  return components.map(c => ({
    id: c.id, type: 'component',
    data: { label: c.name, layer: c.layer, confidence: c.confidence },
    position: { x: 0, y: 0 },
  }))
}

function depToEdge(d: Dependency): Edge {
  const isAuto = d.confidence === 'auto'
  return {
    id: d.id,
    source: d.from_component,
    target: d.to_component,
    type: 'floating',
    label: d.label,
    markerEnd: { type: MarkerType.ArrowClosed, width: 10, height: 10, color: isAuto ? '#64748b' : '#60a5fa' },
    labelStyle: { fill: isAuto ? '#475569' : '#64748b', fontSize: 9.5 },
    labelBgStyle: { fill: 'rgba(8,12,20,0.85)', fillOpacity: 1 },
    labelBgPadding: [4, 3] as [number, number],
    labelBgBorderRadius: 4,
    data: { confidence: d.confidence },
  }
}

function buildEdges(deps: Dependency[]): Edge[] {
  return deps.map(depToEdge)
}

// ── UI primitives ──────────────────────────────────────────────────────────────

function Section({ icon, label, children }: { icon: React.ReactNode; label: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 20 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginBottom: 8 }}>
        <span style={{ color: 'var(--text-muted)' }}>{icon}</span>
        <span style={{ fontSize: 9.5, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.09em' }}>{label}</span>
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
    <div style={{ position: 'fixed', inset: 0, zIndex: 1000, background: 'rgba(8,12,20,0.8)', backdropFilter: 'blur(8px)', display: 'flex', alignItems: 'center', justifyContent: 'center' }} onClick={onClose}>
      <div
        style={{ background: 'rgba(13,20,33,0.97)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 18, padding: 24, width: 440, boxShadow: '0 24px 64px rgba(0,0,0,0.6)', animation: 'slideUp 0.2s ease' }}
        onClick={e => e.stopPropagation()}
      >
        <div style={{ display: 'flex', alignItems: 'center', marginBottom: 20 }}>
          <span style={{ fontWeight: 700, fontSize: 14.5, flex: 1 }}>{title}</span>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', padding: 4 }}><X size={16} /></button>
        </div>
        {children}
      </div>
    </div>
  )
}

function EmptyState() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', background: 'radial-gradient(ellipse 80% 60% at 50% 40%, #0d1829 0%, #080c14 100%)' }}>
      <div style={{ textAlign: 'center', color: 'var(--text-muted)' }}>
        <Layers size={44} style={{ marginBottom: 14, opacity: 0.2 }} />
        <p style={{ fontSize: 13.5, color: 'var(--text-secondary)' }}>Load a project from the Dashboard first.</p>
      </div>
    </div>
  )
}
