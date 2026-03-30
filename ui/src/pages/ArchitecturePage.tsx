import React, { useCallback, useEffect, useMemo, useState } from 'react'
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
  Activity, Zap, AlertTriangle, FileCode, Cpu, RefreshCw, FolderPlus, Link, Heart,
  type LucideIcon,
} from 'lucide-react'
import { useStore } from '../store'
import {
  getArchitecture, addComponent, updateComponent, deleteComponent,
  addDependency, removeDependency, listComponentFiles,
  inferDependencies, confirmDependency,
  getComponentMetrics, getComponentImpact,
  getFileContent, getFileSymbol,
  mapFile, unmapFile, annotateFile, syncFileSymbols,
  getContract, migrateMultilevel, resetGraph,
  getCycles, getValidate, getCodeQuality, getCompleteness,
} from '../api/archMapApi'
import type {
  Component, Dependency, FileMapping, Layer,
  ComponentMetrics, ComponentImpact, FileContent, SymbolExtract,
  Contract, NodeLevel,
} from '../types'
import { EDGE_TYPE_COLOR, LEVEL_LABELS } from '../types'

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

  const isAuto   = (data as any)?.confidence === 'auto'
  const edgeType = (data as any)?.edge_type as string | undefined
  const isAsync  = (data as any)?.async_flag === true
  const isCrossBoundary = (data as any)?.crosses_boundary === true
  const stability = (data as any)?.stability as string | undefined

  // Color: edge_type takes priority, then auto/confirmed fallback
  const color = edgeType && EDGE_TYPE_COLOR[edgeType]
    ? EDGE_TYPE_COLOR[edgeType]
    : (isAuto ? '#64748b' : '#60a5fa')

  // Thicker for cross-boundary edges; thinner for deprecated/internal
  const strokeW = isCrossBoundary ? 2.4 : isAuto ? 1.2 : 1.8
  const opacity  = stability === 'deprecated' ? 0.35 : isAuto ? 0.6 : 0.9

  // Dash: async = long dash, auto = short dash, deprecated = dot-dash
  const dash = isAsync ? '10 5' : stability === 'deprecated' ? '4 6' : isAuto ? '6 4' : undefined

  const filterId = `glow-${id}`

  return (
    <g>
      <defs>
        <filter id={filterId} x="-60%" y="-60%" width="220%" height="220%">
          <feGaussianBlur stdDeviation={isCrossBoundary ? 4 : isAuto ? 2 : 3} result="blur" />
          <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
      </defs>

      {/* Wide glow halo */}
      <path
        d={path} fill="none"
        stroke={color} strokeWidth={strokeW * 4} strokeOpacity={isCrossBoundary ? 0.18 : 0.12}
        filter={`url(#${filterId})`}
      />

      {/* Main edge line */}
      <path
        id={id}
        className="react-flow__edge-path rf-edge-main"
        d={path}
        fill="none"
        stroke={color}
        strokeWidth={strokeW}
        strokeDasharray={dash}
        strokeOpacity={opacity}
        markerEnd={markerEnd as string}
        style={{ color }}
      />

      {/* Travelling dot — async edges get larger dot */}
      <circle r={isAsync ? 4 : isAuto ? 3 : 2.5} fill={color} fillOpacity={0.85}>
        <animateMotion dur={isAsync ? '1.8s' : isAuto ? '2.4s' : '3s'} repeatCount="indefinite" path={path} />
      </circle>
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

// ── C4 Breadcrumb navigation bar ──────────────────────────────────────────────

function BreadcrumbNav({
  navStack, onNavigate,
}: {
  navStack: Array<{ id: string; name: string; layer: string }>
  onNavigate: (index: number) => void
}) {
  const crumbStyle: React.CSSProperties = {
    fontSize: 11, fontWeight: 600, cursor: 'pointer', padding: '3px 8px', borderRadius: 6,
    transition: 'background 0.15s, color 0.15s',
    color: 'rgba(255,255,255,0.55)',
    background: 'none', border: 'none',
  }
  const activeCrumbStyle: React.CSSProperties = {
    ...crumbStyle,
    color: '#f0f7ff', cursor: 'default',
    background: 'rgba(255,255,255,0.07)',
  }
  const sepStyle: React.CSSProperties = {
    fontSize: 10, color: 'rgba(255,255,255,0.2)', margin: '0 1px', userSelect: 'none',
  }

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 2,
      background: 'rgba(13,20,33,0.88)', backdropFilter: 'blur(12px)',
      border: '1px solid rgba(255,255,255,0.08)', borderRadius: 10,
      padding: '4px 10px', boxShadow: '0 4px 20px rgba(0,0,0,0.4)',
      maxWidth: 600, overflow: 'hidden',
    }}>
      <button style={navStack.length === 0 ? activeCrumbStyle : crumbStyle} onClick={() => onNavigate(-1)}>
        <Layers size={10} style={{ marginRight: 4, verticalAlign: 'middle', opacity: 0.7 }} />
        Domains
      </button>
      {navStack.map((crumb, i) => {
        const c = LAYER_COLOR[crumb.layer] || '#94a3b8'
        const isLast = i === navStack.length - 1
        return (
          <React.Fragment key={crumb.id}>
            <span style={sepStyle}>›</span>
            <button
              style={isLast ? { ...activeCrumbStyle, color: c } : crumbStyle}
              onClick={() => !isLast && onNavigate(i)}
            >
              {crumb.name}
            </button>
          </React.Fragment>
        )
      })}
    </div>
  )
}

// ── Custom component node ──────────────────────────────────────────────────────

function ComponentNode({ data }: { data: any }) {
  const c = LAYER_COLOR[data.layer] || '#94a3b8'
  const Icon = LAYER_ICON[data.layer] ?? Box
  const isSelected: boolean = data.selected ?? false
  const isDimmed: boolean = data.dimmed ?? false
  const expandedFiles: boolean = data.expanded ?? false
  const hasChildren: boolean = data.hasChildren ?? false
  const childCount: number = data.childCount ?? 0
  const loading: boolean = data.loading ?? false
  // Health badge data (injected from parent)
  const qualityScore: number | undefined = data.qualityScore
  const inCycle: boolean = data.inCycle ?? false
  const couplingCount: number = data.couplingCount ?? 0
  const showHealthMode: boolean = data.showHealthMode ?? false
  const completenessScore: number | undefined = data.completenessScore
  const showCompletenessMode: boolean = data.showCompletenessMode ?? false

  // Completeness-mode background: red/yellow/green based on score
  const completenessBg = showCompletenessMode && completenessScore != null
    ? (completenessScore >= 80 ? 'linear-gradient(145deg, rgba(10,40,25,0.95) 0%, rgba(8,28,18,0.97) 100%)'
      : completenessScore >= 60 ? 'linear-gradient(145deg, rgba(50,38,8,0.95) 0%, rgba(35,26,5,0.97) 100%)'
      : 'linear-gradient(145deg, rgba(60,15,15,0.95) 0%, rgba(40,10,10,0.97) 100%)')
    : null

  // Health-mode background: red/yellow/green based on available signals
  const healthBg = showHealthMode
    ? (inCycle ? 'linear-gradient(145deg, rgba(60,15,15,0.95) 0%, rgba(40,10,10,0.97) 100%)'
      : couplingCount > 4 ? 'linear-gradient(145deg, rgba(50,30,10,0.95) 0%, rgba(35,20,5,0.97) 100%)'
      : qualityScore != null && qualityScore < 60 ? 'linear-gradient(145deg, rgba(55,15,15,0.95) 0%, rgba(38,10,10,0.97) 100%)'
      : qualityScore != null && qualityScore >= 80 ? 'linear-gradient(145deg, rgba(10,40,25,0.95) 0%, rgba(8,28,18,0.97) 100%)'
      : 'linear-gradient(145deg, rgba(20,30,50,0.92) 0%, rgba(10,16,30,0.95) 100%)')
    : null

  const nodeBg = completenessBg ?? healthBg ?? 'linear-gradient(145deg, rgba(20,30,50,0.92) 0%, rgba(10,16,30,0.95) 100%)'

  return (
    <div
      style={{
        position: 'relative',
        background: nodeBg,
        backdropFilter: 'blur(16px)',
        WebkitBackdropFilter: 'blur(16px)',
        border: `1px solid ${isSelected ? c + 'cc' : 'rgba(255,255,255,0.08)'}`,
        borderRadius: 16,
        minWidth: NODE_W,
        overflow: 'hidden',
        boxShadow: isSelected
          ? `0 0 0 1px ${c}55, 0 0 32px ${c}44, 0 8px 40px rgba(0,0,0,0.6)`
          : '0 4px 24px rgba(0,0,0,0.5), 0 0 0 1px rgba(255,255,255,0.05)',
        opacity: isDimmed ? 0.25 : 1,
        transition: 'opacity 0.2s ease, box-shadow 0.25s ease, border-color 0.25s ease',
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

          {/* Drill-in button — only for nodes with children */}
          {hasChildren ? (
            <button
              onMouseDown={e => e.stopPropagation()}
              onClick={e => { e.stopPropagation(); data.onDrillIn?.() }}
              style={{
                background: `${c}18`,
                border: `1px solid ${c}44`,
                borderRadius: 6, cursor: 'pointer', color: c,
                padding: '2px 6px', display: 'flex', alignItems: 'center', gap: 3,
                transition: 'all 0.15s', fontSize: 8.5, fontWeight: 700,
              }}
              title={`Drill in — view ${childCount} child${childCount !== 1 ? 'ren' : ''}`}
            >
              <ChevronRight size={9} />
              {childCount > 0 && <span>{childCount}</span>}
            </button>
          ) : (
            /* File expand — only on leaf nodes (no hierarchy children) */
            <button
              onMouseDown={e => e.stopPropagation()}
              onClick={e => { e.stopPropagation(); data.onToggle?.() }}
              style={{
                background: expandedFiles ? c + '22' : 'none',
                border: `1px solid ${expandedFiles ? c + '55' : 'rgba(255,255,255,0.08)'}`,
                borderRadius: 6, cursor: 'pointer',
                color: expandedFiles ? c : 'var(--text-muted)',
                padding: '2px 5px', display: 'flex', alignItems: 'center', gap: 3,
                transition: 'all 0.15s', fontSize: 8.5, fontWeight: 600,
              }}
              title={expandedFiles ? 'Collapse file nodes' : 'Expand file nodes in graph'}
            >
              {loading
                ? <span className="spinner" style={{ width: 10, height: 10, borderWidth: 1.5 }} />
                : <><FileCode size={9} /><ChevronDown size={9} style={{ transform: expandedFiles ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }} /></>
              }
            </button>
          )}
        </div>

        {/* Layer + level + confidence pills */}
        <div style={{ display: 'flex', gap: 5, marginTop: 8, flexWrap: 'wrap' }}>
          <span style={{
            display: 'inline-flex', alignItems: 'center',
            padding: '1px 8px', borderRadius: 99, fontSize: 9.5, fontWeight: 600,
            letterSpacing: '0.04em', textTransform: 'capitalize',
            background: c + '18', color: c, border: `1px solid ${c}33`,
          }}>{data.layer}</span>
          <span style={{
            display: 'inline-flex', alignItems: 'center',
            padding: '1px 7px', borderRadius: 99, fontSize: 9, fontWeight: 700,
            background: 'rgba(139,92,246,0.15)', color: '#a78bfa', border: '1px solid rgba(139,92,246,0.3)',
            letterSpacing: '0.02em',
          }}>L{data.level ?? 4} {LEVEL_LABELS[(data.level ?? 4) as NodeLevel] ?? ''}</span>
          {data.public_api?.length > 0 && (
            <span style={{
              display: 'inline-flex', alignItems: 'center',
              padding: '1px 7px', borderRadius: 99, fontSize: 9, fontWeight: 600,
              background: 'rgba(34,197,94,0.12)', color: '#4ade80', border: '1px solid rgba(34,197,94,0.25)',
            }}>{data.public_api.length} API</span>
          )}
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

      {/* Completeness badge — top-left overlay, only in completeness mode */}
      {showCompletenessMode && completenessScore != null && (
        <div style={{
          position: 'absolute', top: 6, left: 6,
          display: 'flex', alignItems: 'center', pointerEvents: 'none',
        }}>
          <span style={{
            fontSize: 8, padding: '1px 4px', borderRadius: 3, fontWeight: 700,
            background: completenessScore >= 80 ? 'rgba(52,211,153,0.15)' : completenessScore >= 60 ? 'rgba(245,158,11,0.15)' : 'rgba(248,113,113,0.15)',
            color: completenessScore >= 80 ? '#34d399' : completenessScore >= 60 ? '#f59e0b' : '#f87171',
            border: `1px solid ${completenessScore >= 80 ? 'rgba(52,211,153,0.3)' : completenessScore >= 60 ? 'rgba(245,158,11,0.3)' : 'rgba(248,113,113,0.3)'}`,
          }} title={`Knowledge completeness: ${completenessScore}%`}>{completenessScore}%</span>
        </div>
      )}

      {/* Health badges — top-right overlay */}
      {(inCycle || couplingCount > 0 || qualityScore != null) && (
        <div style={{
          position: 'absolute', top: 6, right: 6,
          display: 'flex', gap: 3, alignItems: 'center', pointerEvents: 'none',
        }}>
          {inCycle && (
            <span style={{
              fontSize: 8, padding: '1px 4px', borderRadius: 3, fontWeight: 700,
              background: 'rgba(248,113,113,0.2)', color: '#fca5a5',
              border: '1px solid rgba(248,113,113,0.35)',
            }} title="In a dependency cycle">⟳</span>
          )}
          {couplingCount > 0 && (
            <span style={{
              fontSize: 8, padding: '1px 4px', borderRadius: 3, fontWeight: 700,
              background: couplingCount > 4 ? 'rgba(251,146,60,0.2)' : 'rgba(148,163,184,0.12)',
              color: couplingCount > 4 ? '#fdba74' : '#94a3b8',
              border: `1px solid ${couplingCount > 4 ? 'rgba(251,146,60,0.35)' : 'rgba(148,163,184,0.2)'}`,
            }} title={`${couplingCount} upstream dependents`}>↑{couplingCount}</span>
          )}
          {qualityScore != null && (
            <span style={{
              fontSize: 8, padding: '1px 4px', borderRadius: 3, fontWeight: 700,
              background: qualityScore >= 80 ? 'rgba(52,211,153,0.15)' : qualityScore >= 60 ? 'rgba(245,158,11,0.15)' : 'rgba(248,113,113,0.15)',
              color: qualityScore >= 80 ? '#34d399' : qualityScore >= 60 ? '#f59e0b' : '#f87171',
              border: `1px solid ${qualityScore >= 80 ? 'rgba(52,211,153,0.3)' : qualityScore >= 60 ? 'rgba(245,158,11,0.3)' : 'rgba(248,113,113,0.3)'}`,
            }} title={`Quality score: ${qualityScore}/100`}>{qualityScore}</span>
          )}
        </div>
      )}
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
  const syncing: boolean = data.syncing ?? false
  const hasSymbols = Array.isArray(functions) && functions.length > 0
  const [hovered, setHovered] = React.useState(false)

  return (
    <div
      style={{
        background: isSelected
          ? `linear-gradient(145deg, rgba(20,28,46,0.97), rgba(12,18,34,0.98))`
          : 'rgba(12,18,32,0.95)',
        backdropFilter: 'blur(12px)',
        border: `1px solid ${isSelected ? c + '88' : c + '33'}`,
        borderRadius: 10,
        width: 158,
        overflow: 'visible',
        boxShadow: isSelected
          ? `0 0 0 1px ${c}44, 0 0 20px ${c}30, 0 4px 16px rgba(0,0,0,0.5)`
          : `0 2px 12px rgba(0,0,0,0.5), 0 0 0 1px rgba(255,255,255,0.04)`,
        animation: 'node-appear 0.18s ease both',
        transition: 'border-color 0.2s, box-shadow 0.2s',
        cursor: 'pointer',
        position: 'relative',
      }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <Handle type="target" position={Position.Top} id="t" style={{ opacity: 0 }} />
      <Handle type="source" position={Position.Bottom} id="b" style={{ opacity: 0 }} />

      {/* Hover action buttons */}
      {hovered && (
        <div style={{
          position: 'absolute', top: -10, right: -6, display: 'flex', gap: 3, zIndex: 10,
        }}>
          <button
            onMouseDown={e => e.stopPropagation()}
            onClick={e => { e.stopPropagation(); data.onSync?.() }}
            title="Sync symbols from actual file"
            style={{
              background: 'rgba(13,20,33,0.95)', border: '1px solid rgba(255,255,255,0.12)',
              borderRadius: 5, cursor: 'pointer', padding: '2px 4px',
              color: c, display: 'flex', alignItems: 'center',
            }}
          >
            {syncing
              ? <span className="spinner" style={{ width: 8, height: 8, borderWidth: 1.5 }} />
              : <RefreshCw size={8} />
            }
          </button>
          <button
            onMouseDown={e => e.stopPropagation()}
            onClick={e => { e.stopPropagation(); data.onUnmap?.() }}
            title="Unmap file from component"
            style={{
              background: 'rgba(13,20,33,0.95)', border: '1px solid rgba(255,100,100,0.2)',
              borderRadius: 5, cursor: 'pointer', padding: '2px 4px',
              color: '#f87171', display: 'flex', alignItems: 'center',
            }}
          >
            <X size={8} />
          </button>
        </div>
      )}

      {/* Micro top stripe */}
      <div style={{ height: 2, background: `linear-gradient(90deg, ${c}cc, transparent)`, borderRadius: '10px 10px 0 0' }} />

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
  const [hovered, setHovered] = React.useState(false)

  return (
    <div
      style={{
        background: 'rgba(6,10,20,0.97)',
        border: `1px solid ${c}30`,
        borderRadius: 7,
        width: 136,
        overflow: 'visible',
        boxShadow: `0 1px 8px rgba(0,0,0,0.5), 0 0 0 1px rgba(255,255,255,0.03)`,
        cursor: 'pointer',
        animation: 'node-appear 0.14s ease both',
        transition: 'border-color 0.15s',
        position: 'relative',
      }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <Handle type="target" position={Position.Top} id="t" style={{ opacity: 0 }} />
      <div style={{ height: 1.5, background: `linear-gradient(90deg, ${c}88, transparent)`, borderRadius: '7px 7px 0 0' }} />
      <div style={{ padding: '5px 9px', display: 'flex', alignItems: 'center', gap: 5 }}>
        <span style={{
          fontSize: 7, fontWeight: 800, padding: '1px 4px', borderRadius: 3, flexShrink: 0,
          background: isCls ? 'rgba(168,85,247,0.18)' : `${c}20`,
          color: isCls ? '#a855f7' : c, fontFamily: 'monospace', letterSpacing: '0.04em',
        }}>{isCls ? 'cls' : 'fn'}</span>
        <span style={{
          flex: 1, fontSize: 9.5, fontFamily: 'monospace', color: 'var(--text-secondary)',
          fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }} title={name}>{name}</span>
        {hovered && (
          <button
            onMouseDown={e => e.stopPropagation()}
            onClick={e => { e.stopPropagation(); data.onRemove?.() }}
            title="Remove symbol from registry"
            style={{
              background: 'none', border: 'none', cursor: 'pointer', padding: '0 1px',
              color: '#f87171', display: 'flex', alignItems: 'center', flexShrink: 0,
            }}
          >
            <X size={8} />
          </button>
        )}
      </div>
    </div>
  )
}

// ── Resizable panel hook ───────────────────────────────────────────────────────
// Returns [width, dragHandleProps]. Drag the left edge to resize.

function usePanelResize(defaultWidth: number, min = 220, max = 700) {
  const [width, setWidth] = React.useState(defaultWidth)
  const dragging = React.useRef(false)
  const startX = React.useRef(0)
  const startW = React.useRef(0)

  const onMouseDown = React.useCallback((e: React.MouseEvent) => {
    dragging.current = true
    startX.current = e.clientX
    startW.current = width
    e.preventDefault()

    const onMove = (ev: MouseEvent) => {
      if (!dragging.current) return
      const delta = startX.current - ev.clientX   // drag left = wider
      setWidth(Math.min(max, Math.max(min, startW.current + delta)))
    }
    const onUp = () => {
      dragging.current = false
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }, [width, min, max])

  const handle = (
    <div
      onMouseDown={onMouseDown}
      style={{
        position: 'absolute', left: 0, top: 0, bottom: 0, width: 5,
        cursor: 'col-resize', zIndex: 10,
        background: 'transparent',
        transition: 'background 0.15s',
      }}
      onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'rgba(96,165,250,0.25)' }}
      onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'transparent' }}
    />
  )

  return [width, handle] as const
}

// ── Health Panel ───────────────────────────────────────────────────────────────
// Shows project health: dependency cycles, rule violations, and hot zones ranked
// by "messiness" (coupling + cycles + quality). Helps users prioritize refactoring.

interface HealthData {
  cycles: Array<{
    component_id: string
    component_name: string
    layer: string
    cycles_with: Array<{ component_id: string; component_name: string; layer: string }>
  }>
  violations: Array<{
    rule_id: string
    rule_type: string
    message: string
    from_component: string
    from_name: string
    to_component: string
    to_name: string
  }>
  couplingMap: Record<string, number>  // component_id → upstream count
}

function HealthPanel({
  components,
  healthData,
  qualityScores,
  completenessMap,
  onClose,
  onSelectComponent,
}: {
  components: Component[]
  healthData: HealthData | null
  qualityScores: Record<string, number>
  completenessMap: Record<string, number>
  onClose: () => void
  onSelectComponent: (id: string) => void
}) {
  const [panelWidth, resizeHandle] = usePanelResize(360)

  if (!healthData) {
    return (
      <div style={{ width: 360, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'rgba(8,13,24,0.98)', borderLeft: '1px solid rgba(255,255,255,0.07)' }}>
        <span className="spinner spinner-lg" />
      </div>
    )
  }

  const cycleIds = new Set(healthData.cycles.flatMap(c => [c.component_id, ...c.cycles_with.map(x => x.component_id)]))
  const violatingIds = new Set(healthData.violations.flatMap(v => [v.from_component, v.to_component]))

  // Composite messiness score for ranking (not shown to user)
  const messiness = (comp: Component): number => {
    const coupling = healthData.couplingMap[comp.id] ?? 0
    const couplingPenalty = coupling > 4 ? (coupling - 4) * 8 : coupling * 2
    const cyclePenalty = cycleIds.has(comp.id) ? 30 : 0
    const violationPenalty = violatingIds.has(comp.id) ? 20 : 0
    const quality = qualityScores[comp.id]
    const qualityPenalty = quality != null ? Math.max(0, (80 - quality) * 0.5) : 0
    return couplingPenalty + cyclePenalty + violationPenalty + qualityPenalty
  }

  const rankedComponents = [...components]
    .filter(c => messiness(c) > 0)
    .sort((a, b) => messiness(b) - messiness(a))

  const totalIssues = healthData.cycles.length + healthData.violations.length
  const healthyCount = components.length - rankedComponents.length

  return (
    <div style={{
      width: panelWidth, flexShrink: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden',
      position: 'relative',
      background: 'rgba(8,13,24,0.98)', borderLeft: '1px solid rgba(255,255,255,0.07)',
      backdropFilter: 'blur(20px)',
    }}>
      {resizeHandle}
      <div style={{ height: 2, background: 'linear-gradient(90deg, #f87171cc, #f59e0b44)' }} />

      {/* Header */}
      <div style={{ padding: '12px 16px', borderBottom: '1px solid rgba(255,255,255,0.07)', display: 'flex', alignItems: 'center', gap: 9 }}>
        <Heart size={14} color="#f87171" style={{ flexShrink: 0 }} />
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 700, fontSize: 13 }}>Project Health</div>
          <div style={{ fontSize: 9, color: 'var(--text-muted)', marginTop: 1 }}>
            {components.length} component{components.length !== 1 ? 's' : ''} — {healthyCount} healthy, {rankedComponents.length} with issues
          </div>
        </div>
        <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', padding: 4 }}><X size={13} /></button>
      </div>

      <div style={{ flex: 1, overflowY: 'auto' }}>

        {/* Cycles */}
        {healthData.cycles.length > 0 && (
          <div style={{ padding: '12px 16px', borderBottom: '1px solid rgba(255,255,255,0.07)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8, padding: '5px 9px', borderRadius: 7, background: 'rgba(248,113,113,0.1)', border: '1px solid rgba(248,113,113,0.25)' }}>
              <AlertTriangle size={11} color="#f87171" />
              <span style={{ fontSize: 10.5, fontWeight: 700, color: '#f87171' }}>{healthData.cycles.length} circular dependenc{healthData.cycles.length !== 1 ? 'ies' : 'y'}</span>
            </div>
            {healthData.cycles.map((cycle, i) => (
              <div key={i} style={{ marginBottom: 5, fontSize: 10.5, display: 'flex', alignItems: 'center', gap: 5, flexWrap: 'wrap' }}>
                {cycle.cycles_with.map((partner, j) => (
                  <React.Fragment key={partner.component_id}>
                    <button
                      onClick={() => onSelectComponent(cycle.component_id)}
                      style={{ border: 'none', cursor: 'pointer', padding: '1px 6px', borderRadius: 4, background: 'rgba(248,113,113,0.08)', color: '#fca5a5', fontSize: 10.5, fontWeight: 600 }}
                    >{cycle.component_name}</button>
                    <span style={{ color: 'var(--text-muted)', fontSize: 9 }}>⟳</span>
                    <button
                      onClick={() => onSelectComponent(partner.component_id)}
                      style={{ border: 'none', cursor: 'pointer', padding: '1px 6px', borderRadius: 4, background: 'rgba(248,113,113,0.08)', color: '#fca5a5', fontSize: 10.5, fontWeight: 600 }}
                    >{partner.component_name}</button>
                    {j < cycle.cycles_with.length - 1 && <span style={{ color: 'var(--text-muted)' }}>,</span>}
                  </React.Fragment>
                ))}
              </div>
            ))}
          </div>
        )}

        {/* Rule violations */}
        {healthData.violations.length > 0 && (
          <div style={{ padding: '12px 16px', borderBottom: '1px solid rgba(255,255,255,0.07)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8, padding: '5px 9px', borderRadius: 7, background: 'rgba(245,158,11,0.1)', border: '1px solid rgba(245,158,11,0.25)' }}>
              <AlertTriangle size={11} color="#f59e0b" />
              <span style={{ fontSize: 10.5, fontWeight: 700, color: '#f59e0b' }}>{healthData.violations.length} rule violation{healthData.violations.length !== 1 ? 's' : ''}</span>
            </div>
            {healthData.violations.slice(0, 8).map((v, i) => (
              <div key={i} style={{ marginBottom: 4, padding: '5px 9px', borderRadius: 6, background: 'rgba(245,158,11,0.05)', border: '1px solid rgba(245,158,11,0.12)', fontSize: 10 }}>
                <span style={{ color: '#fcd34d', fontWeight: 600 }}>{v.from_name}</span>
                <span style={{ color: 'var(--text-muted)', margin: '0 4px' }}>→</span>
                <span style={{ color: '#fcd34d', fontWeight: 600 }}>{v.to_name}</span>
                {v.message && <div style={{ fontSize: 9, color: 'var(--text-muted)', marginTop: 1 }}>{v.message}</div>}
              </div>
            ))}
          </div>
        )}

        {/* Hot zones */}
        <div style={{ padding: '12px 16px' }}>
          <div style={{ fontSize: 9, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 10 }}>
            Hot Zones {rankedComponents.length > 0 ? `(${rankedComponents.length})` : ''}
          </div>

          {rankedComponents.length === 0 ? (
            <div style={{ padding: '16px 0', textAlign: 'center', color: '#34d399', fontSize: 11 }}>
              <span style={{ display: 'block', fontSize: 18, marginBottom: 4 }}>✓</span>
              All components look healthy
            </div>
          ) : (
            rankedComponents.map(comp => {
              const coupling = healthData.couplingMap[comp.id] ?? 0
              const inCycle = cycleIds.has(comp.id)
              const hasViolation = violatingIds.has(comp.id)
              const quality = qualityScores[comp.id]
              const c = LAYER_COLOR[comp.layer] ?? '#94a3b8'

              return (
                <div
                  key={comp.id}
                  onClick={() => onSelectComponent(comp.id)}
                  style={{
                    marginBottom: 6, padding: '8px 10px', borderRadius: 8, cursor: 'pointer',
                    background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.07)',
                    transition: 'background 0.15s, border-color 0.15s',
                  }}
                  onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'rgba(255,255,255,0.06)'; (e.currentTarget as HTMLElement).style.borderColor = 'rgba(255,255,255,0.13)' }}
                  onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'rgba(255,255,255,0.03)'; (e.currentTarget as HTMLElement).style.borderColor = 'rgba(255,255,255,0.07)' }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 5 }}>
                    <div style={{ width: 7, height: 7, borderRadius: '50%', background: c, flexShrink: 0 }} />
                    <span style={{ fontSize: 11.5, fontWeight: 700, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{comp.name}</span>
                    <span style={{ fontSize: 8.5, padding: '1px 5px', borderRadius: 4, background: c + '18', color: c, flexShrink: 0 }}>{comp.layer}</span>
                  </div>

                  {/* Quality bar + completeness bar + coupling */}
                  <div style={{ display: 'flex', gap: 6, marginBottom: 5, alignItems: 'center' }}>
                    {quality != null && (
                      <div style={{ flex: 1 }}>
                        <div style={{ fontSize: 8, color: 'var(--text-muted)', marginBottom: 2 }}>quality</div>
                        <div style={{ height: 4, borderRadius: 2, background: 'rgba(255,255,255,0.08)', overflow: 'hidden' }}>
                          <div style={{ height: '100%', width: `${quality}%`, borderRadius: 2, background: quality >= 80 ? '#34d399' : quality >= 60 ? '#f59e0b' : '#f87171', transition: 'width 0.3s' }} />
                        </div>
                      </div>
                    )}
                    {completenessMap[comp.id] != null && (
                      <div style={{ flex: 1 }}>
                        <div style={{ fontSize: 8, color: 'var(--text-muted)', marginBottom: 2 }}>complete</div>
                        <div style={{ height: 4, borderRadius: 2, background: 'rgba(255,255,255,0.08)', overflow: 'hidden' }}>
                          {(() => { const s = completenessMap[comp.id]; return <div style={{ height: '100%', width: `${s}%`, borderRadius: 2, background: s >= 80 ? '#34d399' : s >= 60 ? '#f59e0b' : '#f87171', transition: 'width 0.3s' }} /> })()}
                        </div>
                      </div>
                    )}
                    {coupling > 0 && (
                      <div style={{ flexShrink: 0, fontSize: 9, color: coupling > 4 ? '#fb923c' : 'var(--text-muted)', fontWeight: coupling > 4 ? 700 : 400 }}>
                        ↑{coupling}
                      </div>
                    )}
                  </div>

                  {/* Tags */}
                  <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                    {inCycle && <span style={{ fontSize: 8.5, padding: '1px 5px', borderRadius: 3, background: 'rgba(248,113,113,0.1)', color: '#fca5a5', border: '1px solid rgba(248,113,113,0.2)' }}>⟳ cycle</span>}
                    {coupling > 4 && <span style={{ fontSize: 8.5, padding: '1px 5px', borderRadius: 3, background: 'rgba(251,146,60,0.1)', color: '#fdba74', border: '1px solid rgba(251,146,60,0.2)' }}>↑{coupling} deps</span>}
                    {hasViolation && <span style={{ fontSize: 8.5, padding: '1px 5px', borderRadius: 3, background: 'rgba(245,158,11,0.1)', color: '#fcd34d', border: '1px solid rgba(245,158,11,0.2)' }}>rule violation</span>}
                    {quality != null && quality < 60 && <span style={{ fontSize: 8.5, padding: '1px 5px', borderRadius: 3, background: 'rgba(248,113,113,0.1)', color: '#fca5a5', border: '1px solid rgba(248,113,113,0.2)' }}>quality {quality}</span>}
                  </div>
                </div>
              )
            })
          )}
        </div>
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
  // Tighter spacing: fewer nodes visible at any time due to hierarchical fold
  g.setGraph({ rankdir: 'TB', nodesep: 60, ranksep: 100, marginx: 60, marginy: 60 })
  nodes.forEach(n => g.setNode(n.id, { width: NODE_W + 16, height: NODE_H + 16 }))
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
  const [showHealth, setShowHealth] = useState(false)
  const [showHealthMode, setShowHealthMode] = useState(false)
  const [showCompletenessMode, setShowCompletenessMode] = useState(false)
  const [showCycles, setShowCycles] = useState(false)
  const [healthData, setHealthData] = useState<HealthData | null>(null)
  const [qualityScores, setQualityScores] = useState<Record<string, number>>({})
  const [completenessMap, setCompletenessMap] = useState<Record<string, number>>({})
  const [expandedComponents, setExpandedComponents] = useState<Set<string>>(new Set())
  const [loadingComponents, setLoadingComponents] = useState<Set<string>>(new Set())
  const [expandedFiles, setExpandedFiles] = useState<Set<string>>(new Set())
  const [loadingFiles, setLoadingFiles] = useState<Set<string>>(new Set())
  const [filePanel, setFilePanel] = useState<{ file: FileMapping; nodeId: string } | null>(null)
  const [symbolPanel, setSymbolPanel] = useState<{ symbol: string; filePath: string } | null>(null)
  // C4 navigator — breadcrumb drill-down stack
  const [navStack, setNavStack] = useState<Array<{ id: string; name: string; layer: string }>>([])
  const rfRef = React.useRef<any>(null)
  // Saved positions before focus-radial repositioning so they can be restored on deselect
  const focusSavedPos = React.useRef<Record<string, { x: number; y: number }>>({})
  const [migrating, setMigrating] = useState(false)
  const [showEdgeLegend, setShowEdgeLegend] = useState(false)
  const [showResetDialog, setShowResetDialog] = useState(false)
  const [resetting, setResetting] = useState(false)

  const graphKey = projectPath ? `archmap-graph::${btoa(projectPath)}` : null

  // Map parent_id → [child_id] for all components
  const childrenMap = useMemo(() => {
    const map: Record<string, string[]> = {}
    for (const c of components) {
      if (c.parent_id) {
        map[c.parent_id] = map[c.parent_id] ?? []
        map[c.parent_id].push(c.id)
      }
    }
    return map
  }, [components])

  // IDs of the selected node + its direct neighbors (for dimming unrelated nodes)
  const neighborIds = useMemo(() => {
    if (!selected) return null
    const ids = new Set<string>()
    ids.add(selected.id)
    for (const d of dependencies) {
      if (d.from_component === selected.id) ids.add(d.to_component)
      if (d.to_component === selected.id) ids.add(d.from_component)
    }
    return ids
  }, [selected, dependencies])

  // Build the ReactFlow graph for the given navigation scope.
  // Takes explicit data params (not state) to avoid stale-closure issues.
  const buildScopedGraph = useCallback((
    allComponents: Component[],
    allDeps: Dependency[],
    cMap: Record<string, string[]>,
    scope: Array<{ id: string }>,
    savedPositions: Record<string, { x: number; y: number }> = {},
  ) => {
    const scopeId = scope[scope.length - 1]?.id ?? null
    let visibleComps: Component[]
    let visibleDeps: Dependency[]

    if (scopeId === null) {
      // Root: show only L2 domain nodes. L1 is the implicit system boundary.
      visibleComps = allComponents.filter(c => (c.level ?? 4) === 2)
      if (visibleComps.length === 0) visibleComps = allComponents.filter(c => (c.level ?? 4) <= 2)
      if (visibleComps.length === 0) visibleComps = allComponents

      const visibleSet = new Set(visibleComps.map(c => c.id))
      const byId = Object.fromEntries(allComponents.map(c => [c.id, c]))

      // Find the L2 ancestor of any component (walks parent_id chain up to level 2).
      const l2AncestorOf = (id: string): string | null => {
        let cur = byId[id]
        while (cur) {
          if ((cur.level ?? 4) === 2) return cur.id
          if (!cur.parent_id) return null
          cur = byId[cur.parent_id]
        }
        return null
      }

      // Roll up all deps to their L2 ancestors so domain-level connections are visible.
      const rollupEdges = new Map<string, Dependency>()
      for (const d of allDeps) {
        const fromL2 = visibleSet.has(d.from_component) ? d.from_component : l2AncestorOf(d.from_component)
        const toL2   = visibleSet.has(d.to_component)   ? d.to_component   : l2AncestorOf(d.to_component)
        if (fromL2 && toL2 && fromL2 !== toL2) {
          const key = `${fromL2}→${toL2}`
          if (!rollupEdges.has(key)) {
            rollupEdges.set(key, { ...d, id: `rollup_${key}`, from_component: fromL2, to_component: toL2, confidence: 'auto' as const })
          }
        }
      }
      visibleDeps = [...rollupEdges.values()]
    } else {
      const childIds = new Set(cMap[scopeId] ?? [])
      visibleComps = allComponents.filter(c => childIds.has(c.id))
      const visibleSet = new Set(visibleComps.map(c => c.id))
      visibleDeps = allDeps.filter(d => visibleSet.has(d.from_component) && visibleSet.has(d.to_component))
    }

    const laid = layoutWithDagre(buildNodes(visibleComps, cMap), buildEdges(visibleDeps))
    const withPositions = laid.map(n => savedPositions[n.id] ? { ...n, position: savedPositions[n.id] } : n)
    setNodes(withPositions)
    setEdges(buildEdges(visibleDeps))
  }, [])

  const load = useCallback(async () => {
    if (!projectPath) return
    const saved = graphKey ? JSON.parse(localStorage.getItem(graphKey) ?? '{}') : {}
    const savedPositions: Record<string, { x: number; y: number }> = saved.positions ?? {}

    setLoading(true)
    setFilePanel(null)
    setSymbolPanel(null)
    try {
      const arch = await getArchitecture(projectPath)
      setComponents(arch.components)
      setDependencies(arch.dependencies)
      const cMap: Record<string, string[]> = {}
      for (const c of arch.components) {
        if (c.parent_id) { cMap[c.parent_id] = cMap[c.parent_id] ?? []; cMap[c.parent_id].push(c.id) }
      }
      setNavStack([]) // always reset to root on full reload
      buildScopedGraph(arch.components, arch.dependencies, cMap, [], savedPositions)
      setExpandedComponents(new Set())
      setExpandedFiles(new Set())
      focusSavedPos.current = {}

      // Compute coupling map from loaded deps (upstream count per component)
      const couplingMap: Record<string, number> = {}
      for (const d of arch.dependencies) {
        couplingMap[d.to_component] = (couplingMap[d.to_component] ?? 0) + 1
      }

      // Fetch cycles, violations, and completeness in parallel (non-blocking, best-effort)
      const [cyclesResult, validateResult, completenessResult] = await Promise.allSettled([
        getCycles(projectPath),
        getValidate(projectPath),
        getCompleteness(projectPath),
      ])
      const cycles = cyclesResult.status === 'fulfilled' ? cyclesResult.value.cycles : []
      const violations = validateResult.status === 'fulfilled' ? validateResult.value.violations : []
      setHealthData({ cycles, violations, couplingMap })
      if (completenessResult.status === 'fulfilled') {
        const cMap: Record<string, number> = {}
        for (const s of completenessResult.value) cMap[s.component_id] = s.score
        setCompletenessMap(cMap)
      }
    } catch (e: any) { toast('error', e.message) }
    finally { setLoading(false) }
  }, [projectPath, graphKey, buildScopedGraph])

  useEffect(() => { load() }, [load])

  // Lazily fetch quality score when a component is selected (if not already cached)
  useEffect(() => {
    if (!selected || !projectPath || qualityScores[selected.id] !== undefined) return
    getCodeQuality(projectPath, selected.id)
      .then(r => setQualityScores(prev => ({ ...prev, [selected.id]: r.score })))
      .catch(() => { /* silent — quality is optional */ })
  }, [selected, projectPath])

  // Merge health badges + completeness into node data when data or mode changes
  useEffect(() => {
    if (!healthData) return
    const cycleIds = new Set(healthData.cycles.flatMap(c => [c.component_id, ...c.cycles_with.map(x => x.component_id)]))
    setNodes(prev => prev.map(n => {
      if (n.type !== 'component') return n
      return {
        ...n,
        data: {
          ...n.data,
          inCycle: cycleIds.has(n.id),
          couplingCount: healthData.couplingMap[n.id] ?? 0,
          qualityScore: qualityScores[n.id],
          showHealthMode,
          completenessScore: completenessMap[n.id],
          showCompletenessMode,
        },
      }
    }))
  }, [healthData, qualityScores, showHealthMode, completenessMap, showCompletenessMode])

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

  // ── C4 Navigator: drill-down and breadcrumb navigation ────────────────────────

  const drillInto = useCallback((comp: Component) => {
    if ((childrenMap[comp.id] ?? []).length === 0) return
    setNavStack(prev => [...prev, { id: comp.id, name: comp.name, layer: comp.layer }])
    setSelected(null)
    setFilePanel(null)
    setSymbolPanel(null)
    focusSavedPos.current = {}
  }, [childrenMap])

  // Navigate to a specific breadcrumb index (−1 = root)
  const navigateTo = useCallback((index: number) => {
    setNavStack(prev => index < 0 ? [] : prev.slice(0, index + 1))
    setSelected(null)
    setFilePanel(null)
    focusSavedPos.current = {}
  }, [])

  // Rebuild graph whenever the navigation stack changes
  const prevNavKey = React.useRef<string>('__init__')
  useEffect(() => {
    const key = navStack.map(n => n.id).join('/')
    if (prevNavKey.current === '__init__') { prevNavKey.current = key; return } // skip initial mount
    if (prevNavKey.current === key) return
    prevNavKey.current = key
    if (components.length === 0) return
    buildScopedGraph(components, dependencies, childrenMap, navStack)
    setExpandedComponents(new Set())
    setExpandedFiles(new Set())
    focusSavedPos.current = {}
  }, [navStack, components, dependencies, childrenMap, buildScopedGraph])

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
      const rawSyms: string[] = (file?.symbols ?? []).map((s: any) => s.display_name ?? s.name ?? '').filter(Boolean)
      const symbols: string[] = rawSyms.length > 0 ? rawSyms : (file?.metadata?.functions ?? [])
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
      const symArr = file?.symbols ?? []
      const count = symArr.length > 0 ? symArr.length : (file?.metadata?.functions?.length ?? 0)
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

  // ── File node CRUD actions ──────────────────────────────────────────────────

  const [syncingFiles, setSyncingFiles] = useState<Set<string>>(new Set())

  // Rebuild symbol nodes for a file node using the provided updated file data (avoids stale closure)
  const refreshSymbolNodes = useCallback((fileNodeId: string, updatedFile: FileMapping) => {
    const rawSyms2: string[] = (updatedFile.symbols ?? []).map((s: any) => s.display_name ?? s.name ?? '').filter(Boolean)
    const symbols: string[] = rawSyms2.length > 0 ? rawSyms2 : (updatedFile.metadata?.functions ?? [])
    // Remove old sym nodes + edges
    setNodes(prev => prev.filter(n => !n.id.startsWith(`sym::${fileNodeId}::`)))
    setEdges(prev => prev.filter(e => !e.id.startsWith(`symedge::${fileNodeId}::`)))
    if (symbols.length === 0) {
      setExpandedFiles(prev => { const s = new Set(prev); s.delete(fileNodeId); return s })
      return
    }
    // Re-build sym nodes using current position from DOM (via functional setNodes)
    setNodes(prev => {
      const fileNode = prev.find(n => n.id === fileNodeId)
      if (!fileNode) return prev
      const { x: px, y: py } = fileNode.position
      const parentColor = (fileNode.data?.parentColor as string) ?? '#64748b'
      const filePath = updatedFile.file_path
      const cols = 2, sw = 136, sh = 46, gap = 6
      const totalW = Math.min(symbols.length, cols) * (sw + gap) - gap
      const startX = px + (158 - totalW) / 2
      const symNodes: Node[] = symbols.map((sym, i) => ({
        id: `sym::${fileNodeId}::${i}`,
        type: 'symbol',
        position: { x: startX + (i % cols) * (sw + gap), y: py + 108 + Math.floor(i / cols) * (sh + gap) },
        data: { symbol: sym, filePath, parentColor, fileNodeId },
        draggable: true, selectable: true,
      }))
      return [...prev, ...symNodes]
    })
    setEdges(prev => {
      const symEdges: Edge[] = symbols.map((_, i) => ({
        id: `symedge::${fileNodeId}::${i}`,
        source: fileNodeId, target: `sym::${fileNodeId}::${i}`,
        type: 'straight',
        style: { stroke: 'rgba(100,116,139,0.28)', strokeWidth: 0.75, strokeDasharray: '2 3' },
        selectable: false, focusable: false,
      }))
      return [...prev, ...symEdges]
    })
    if (symbols.length > 0) {
      setExpandedFiles(prev => new Set(prev).add(fileNodeId))
    }
  }, [])

  const handleSyncFile = useCallback(async (fileNodeId: string, file: FileMapping) => {
    if (!projectPath) return
    setSyncingFiles(prev => new Set(prev).add(fileNodeId))
    try {
      const updated = await syncFileSymbols(projectPath, file.file_path)
      // Update the file node's data in-place
      setNodes(prev => prev.map(n =>
        n.id === fileNodeId ? { ...n, data: { ...n.data, file: updated } } : n
      ))
      // If symbols were expanded, refresh them with new data
      if (expandedFiles.has(fileNodeId)) {
        refreshSymbolNodes(fileNodeId, updated)
      }
      // Keep FilePanel in sync
      setFilePanel(prev => prev?.nodeId === fileNodeId ? { ...prev, file: updated } : prev)
      toast('success', `Synced ${updated.metadata?.functions?.length ?? 0} symbol(s)`)
    } catch (e: any) { toast('error', e.message) }
    finally { setSyncingFiles(prev => { const s = new Set(prev); s.delete(fileNodeId); return s }) }
  }, [projectPath, expandedFiles, refreshSymbolNodes])

  const handleUnmapFile = useCallback(async (fileNodeId: string, file: FileMapping) => {
    if (!projectPath) return
    try {
      await unmapFile(projectPath, file.file_path)
      // Collapse symbols first
      setNodes(prev => prev.filter(n =>
        n.id !== fileNodeId && !n.id.startsWith(`sym::${fileNodeId}::`)
      ))
      setEdges(prev => prev.filter(e =>
        e.target !== fileNodeId && e.source !== fileNodeId && !e.id.startsWith(`symedge::${fileNodeId}::`)
      ))
      setExpandedFiles(prev => { const s = new Set(prev); s.delete(fileNodeId); return s })
      if (filePanel?.nodeId === fileNodeId) setFilePanel(null)
      toast('success', 'File unmapped')
    } catch (e: any) { toast('error', e.message) }
  }, [projectPath, filePanel])

  const handleRemoveSymbol = useCallback(async (symNodeId: string, symbol: string, fileNodeId: string) => {
    if (!projectPath) return
    // Find parent file node and update its functions list
    setNodes(prev => {
      const fileNode = prev.find(n => n.id === fileNodeId)
      if (!fileNode) return prev
      const file = fileNode.data?.file as FileMapping | undefined
      if (!file) return prev
      const newFunctions = (file.metadata?.functions ?? []).filter(f => f !== symbol)
      const updatedFile = { ...file, metadata: { ...file.metadata, functions: newFunctions } }
      annotateFile(projectPath, file.file_path, { functions: newFunctions }).catch(() => {})
      // Update file node data + remove the symbol node
      return prev
        .filter(n => n.id !== symNodeId)
        .map(n => n.id === fileNodeId ? { ...n, data: { ...n.data, file: updatedFile } } : n)
    })
    setEdges(prev => prev.filter(e => e.target !== symNodeId))
    toast('success', 'Symbol removed')
  }, [projectPath])

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

      // ── Radial focus: reposition direct neighbors around the focal node ────────
      // Only rearrange component nodes (not file/symbol nodes)
      setNodes(prev => {
        const compEdges = edges.filter(e =>
          !e.id.startsWith('fileedge::') && !e.id.startsWith('symedge::') && !e.id.startsWith('hieredge::')
        )
        const nbrIds = Array.from(new Set([
          ...compEdges.filter(e => e.source === node.id).map(e => e.target),
          ...compEdges.filter(e => e.target === node.id).map(e => e.source),
        ])).filter(id => prev.some(n => n.id === id && n.type === 'component'))

        if (nbrIds.length === 0) {
          setTimeout(() => rfRef.current?.fitView({ nodes: [{ id: node.id }], duration: 500, padding: 1.8 }), 20)
          return prev
        }

        // Save original positions for restoration
        const saved: Record<string, { x: number; y: number }> = {}
        for (const n of prev) {
          if (nbrIds.includes(n.id)) saved[n.id] = { ...n.position }
        }
        focusSavedPos.current = saved

        // Place neighbors in a circle around the focal node
        const focalNode = prev.find(n => n.id === node.id)!
        const fx = focalNode.position.x + (NODE_W / 2)
        const fy = focalNode.position.y + (NODE_H / 2)
        const radius = Math.max(260, nbrIds.length * 55)
        const angleStep = (2 * Math.PI) / nbrIds.length

        const updated = prev.map(n => {
          const idx = nbrIds.indexOf(n.id)
          if (idx < 0) return n
          const angle = -Math.PI / 2 + idx * angleStep
          return {
            ...n,
            position: {
              x: fx + Math.cos(angle) * radius - NODE_W / 2,
              y: fy + Math.sin(angle) * radius - NODE_H / 2,
            },
          }
        })

        // Fit to focal + neighbors after React re-renders positions
        const fitIds = [{ id: node.id }, ...nbrIds.map(id => ({ id }))]
        setTimeout(() => rfRef.current?.fitView({ nodes: fitIds, duration: 520, padding: 0.6 }), 30)

        return updated
      })
    } else if (node.type === 'file') {
      setSelected(null)
      setSymbolPanel(null)
      setFilePanel({ file: node.data.file as FileMapping, nodeId: node.id })
      rfRef.current?.fitView({ nodes: [{ id: node.id }], duration: 400, padding: 2.0 })
    } else if (node.type === 'symbol') {
      setSelected(null)
      setFilePanel(null)
      setSymbolPanel({ symbol: node.data.symbol as string, filePath: node.data.filePath as string })
    }
  }, [components, edges])

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
        setEdges(prev => [...prev, ...result.dependencies.map(d => depToEdge(d, false))])
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
          onInit={inst => { rfRef.current = inst }}
          nodes={nodes.map(n => {
            if (n.type === 'component') return {
              ...n,
              data: {
                ...n.data,
                selected: n.id === selected?.id,
                dimmed: neighborIds !== null && !neighborIds.has(n.id),
                expanded: expandedComponents.has(n.id),
                loading: loadingComponents.has(n.id),
                hasChildren: (childrenMap[n.id] ?? []).length > 0,
                childCount: (childrenMap[n.id] ?? []).length,
                onToggle: () => toggleNode(n.id),
                onDrillIn: () => {
                  const comp = components.find(c => c.id === n.id)
                  if (comp) drillInto(comp)
                },
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
                syncing: syncingFiles.has(n.id),
                onToggle: () => toggleFileNode(n.id),
                onSync: () => handleSyncFile(n.id, n.data.file as FileMapping),
                onUnmap: () => handleUnmapFile(n.id, n.data.file as FileMapping),
              },
            }
            if (n.type === 'symbol') return {
              ...n,
              data: {
                ...n.data,
                onRemove: () => handleRemoveSymbol(n.id, n.data.symbol as string, n.data.fileNodeId as string),
              },
            }
            return n
          })}
          edges={showCycles ? (() => {
            const cycleIds = computeCycleEdgeIds(dependencies)
            return edges.map(e => cycleIds.has(e.id)
              ? { ...e, data: { ...e.data, isCycle: true }, markerEnd: { type: MarkerType.ArrowClosed, width: 10, height: 10, color: '#f87171' }, labelStyle: { fill: '#f87171', fontSize: 9.5 } }
              : e)
          })() : edges}
          onPaneClick={() => {
            setSelected(null); setFilePanel(null); setSymbolPanel(null)
            // Restore neighbor positions that were rearranged during focus
            if (Object.keys(focusSavedPos.current).length > 0) {
              const restore = focusSavedPos.current
              focusSavedPos.current = {}
              setNodes(prev => prev.map(n => restore[n.id] ? { ...n, position: restore[n.id] } : n))
            }
          }}
          onNodeDoubleClick={(_e, node) => {
            if (node.type !== 'component') return
            const comp = components.find(c => c.id === node.id)
            if (comp) drillInto(comp)
          }}
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

          {/* C4 Breadcrumb navigation */}
          <Panel position="top-center">
            <div style={{ marginTop: 8 }}>
              <BreadcrumbNav navStack={navStack} onNavigate={navigateTo} />
            </div>
          </Panel>

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
              <div style={{ width: 1, background: 'rgba(255,255,255,0.08)', margin: '0 2px' }} />
              {navStack.length > 0 && (
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={() => navigateTo(-1)}
                  title="Back to domain overview"
                  style={{ fontSize: 10, padding: '3px 7px', color: '#a78bfa' }}
                >
                  <Layers size={11} /> Root
                </button>
              )}
              <div style={{ width: 1, background: 'rgba(255,255,255,0.08)', margin: '0 2px' }} />
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => setShowHealth(v => !v)}
                title="Project health — cycles, violations, hot zones"
                style={{ color: showHealth ? '#f87171' : undefined, background: showHealth ? 'rgba(248,113,113,0.1)' : undefined }}
              >
                <Heart size={12} /> Health
              </button>
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => setShowHealthMode(v => !v)}
                title="Heat-map: color nodes by health state"
                style={{ color: showHealthMode ? '#f59e0b' : undefined, background: showHealthMode ? 'rgba(245,158,11,0.1)' : undefined }}
              >
                <Activity size={12} /> Show Health
              </button>
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => setShowCompletenessMode(v => !v)}
                title="Heat-map: color nodes by knowledge completeness score"
                style={{ color: showCompletenessMode ? '#34d399' : undefined, background: showCompletenessMode ? 'rgba(52,211,153,0.1)' : undefined }}
              >
                <Cpu size={12} /> Completeness
              </button>
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => setShowCycles(v => !v)}
                title="Highlight dependency cycles in red"
                style={{ color: showCycles ? '#f87171' : undefined, background: showCycles ? 'rgba(248,113,113,0.1)' : undefined }}
              >
                <AlertTriangle size={12} /> Cycles
              </button>
              <div style={{ width: 1, background: 'rgba(255,255,255,0.08)', margin: '0 2px' }} />
              <button
                className="btn btn-ghost btn-sm"
                onClick={async () => {
                  if (!projectPath) return
                  setMigrating(true)
                  try {
                    const r = await migrateMultilevel(projectPath)
                    toast('success', r.summary)
                    await load()
                  } catch (e: any) { toast('error', e.message) }
                  finally { setMigrating(false) }
                }}
                disabled={migrating}
                title="Bootstrap 5-level hierarchy: create domains, annotate edges, declare contracts"
                style={{ color: '#f59e0b', fontSize: 10 }}
              >
                {migrating ? <span className="spinner" /> : <><Layers size={11} /> Migrate Graph</>}
              </button>
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => setShowResetDialog(true)}
                title="Reset graph and rebuild with AI agent (/bootstrap-arch)"
                style={{ color: '#f87171', fontSize: 10 }}
              >
                <RefreshCw size={11} /> Rebuild
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
              <p style={{ fontSize: 9, fontWeight: 700, color: 'rgba(255,255,255,0.3)', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 8 }}>Edge Types</p>
              {(Object.entries(EDGE_TYPE_COLOR) as [string, string][]).map(([et, ec]) => (
                <div key={et} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                  <svg width="24" height="8"><line x1="0" y1="4" x2="24" y2="4" stroke={ec} strokeWidth="2" /><circle cx="18" cy="4" r="2.5" fill={ec} /></svg>
                  <span style={{ fontSize: 9.5, color: 'rgba(255,255,255,0.45)', textTransform: 'capitalize' }}>{et.replace('_', ' ')}</span>
                </div>
              ))}
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 4, marginBottom: 6 }}>
                <svg width="24" height="8"><line x1="0" y1="4" x2="24" y2="4" stroke="#94a3b8" strokeWidth="1.5" strokeDasharray="10 5" /></svg>
                <span style={{ fontSize: 9.5, color: 'rgba(255,255,255,0.35)' }}>async (dashed)</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                <svg width="24" height="8"><line x1="0" y1="4" x2="24" y2="4" stroke="#64748b" strokeWidth="1.5" strokeDasharray="5 3" /></svg>
                <span style={{ fontSize: 9.5, color: 'rgba(255,255,255,0.45)' }}>inferred · click to confirm</span>
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
          onFileUnmapped={(filePath: string) => {
            // Surgically remove the file node + its symbols from the graph
            const fileNodeId = nodes.find(n => n.type === 'file' && (n.data?.file as FileMapping)?.file_path === filePath)?.id
            if (fileNodeId) {
              setNodes(prev => prev.filter(n => n.id !== fileNodeId && !n.id.startsWith(`sym::${fileNodeId}::`)))
              setEdges(prev => prev.filter(e => e.target !== fileNodeId && e.source !== fileNodeId && !e.id.startsWith(`symedge::${fileNodeId}::`)))
              setExpandedFiles(prev => { const s = new Set(prev); s.delete(fileNodeId); return s })
            }
          }}
        />
      )}
      {!selected && filePanel && (
        <FilePanel
          file={filePanel.file}
          projectPath={projectPath}
          onClose={() => setFilePanel(null)}
          onSync={(updated) => {
            setFilePanel(prev => prev ? { ...prev, file: updated } : null)
            const nodeId = filePanel.nodeId
            setNodes(prev => prev.map(n =>
              n.id === nodeId ? { ...n, data: { ...n.data, file: updated } } : n
            ))
            if (expandedFiles.has(nodeId)) refreshSymbolNodes(nodeId, updated)
          }}
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
      {showHealth && (
        <HealthPanel
          components={components}
          healthData={healthData}
          qualityScores={qualityScores}
          completenessMap={completenessMap}
          onClose={() => setShowHealth(false)}
          onSelectComponent={(id) => {
            const comp = components.find(c => c.id === id)
            if (comp) {
              setSelected(comp)
              setShowHealth(false)
              // Center on the node
              const node = nodes.find(n => n.id === id)
              if (node && rfRef.current) {
                rfRef.current.setCenter(node.position.x + NODE_W / 2, node.position.y + NODE_H / 2, { zoom: 1.2, duration: 500 })
              }
            }
          }}
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

      {showResetDialog && (
        <Modal title="Rebuild Architecture Graph" onClose={() => !resetting && setShowResetDialog(false)}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <p style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
              This will <strong style={{ color: '#f87171' }}>erase all components, dependencies, file mappings,
              and contracts</strong> for this project. Plan items and ADRs are preserved.
            </p>
            <p style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
              After resetting, use the <strong style={{ color: '#a78bfa' }}>/bootstrap-arch</strong> skill
              in Claude Code to rebuild the graph with AI-driven analysis — it reads your project
              structure and populates the graph with proper domains, services, components, and contracts.
            </p>
            <div style={{ padding: '10px 14px', borderRadius: 8, background: 'rgba(167,139,250,0.08)', border: '1px solid rgba(167,139,250,0.2)' }}>
              <p style={{ fontSize: 11, fontFamily: 'monospace', color: '#c4b5fd', margin: 0, lineHeight: 1.7 }}>
                # In Claude Code terminal:<br />
                /bootstrap-arch
              </p>
            </div>
            <p style={{ fontSize: 10.5, color: 'var(--text-muted)', lineHeight: 1.6 }}>
              The skill guides Claude through 9 phases: orient → L1 system → L2 domains →
              L3 services → L4 components → file mapping → dependencies → contracts → verify.
            </p>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button
                className="btn btn-ghost"
                onClick={() => setShowResetDialog(false)}
                disabled={resetting}
              >
                Cancel
              </button>
              <button
                className="btn btn-danger"
                disabled={resetting}
                onClick={async () => {
                  if (!projectPath) return
                  setResetting(true)
                  try {
                    const r = await resetGraph(projectPath)
                    toast('success', `Graph cleared — ${r.cleared_components} components, ${r.cleared_file_mappings} files removed`)
                    setShowResetDialog(false)
                    await load()
                  } catch (e: any) { toast('error', e.message) }
                  finally { setResetting(false) }
                }}
              >
                {resetting ? <span className="spinner" /> : <><Trash2 size={13} /> Reset Graph</>}
              </button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}

// ── Side panel ─────────────────────────────────────────────────────────────────

function ComponentPanel({ comp, projectPath, deps, components, onClose, onDelete, onUpdated, toast, onFileUnmapped }: any) {
  const [panelWidth, resizeHandle] = usePanelResize(300)
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState({ name: comp.name, description: comp.description, layer: comp.layer })
  const [metrics, setMetrics] = useState<ComponentMetrics | null>(null)
  const [impact, setImpact] = useState<ComponentImpact | null>(null)
  const [contract, setContract] = useState<Contract | null>(null)
  const [compFiles, setCompFiles] = useState<FileMapping[]>([])
  const [mapInput, setMapInput] = useState('')
  const [mapping, setMapping] = useState(false)
  const c = LAYER_COLOR[comp.layer] || '#94a3b8'
  const Icon = LAYER_ICON[comp.layer] ?? Box

  useEffect(() => {
    setForm({ name: comp.name, description: comp.description, layer: comp.layer })
    setEditing(false)
    setMetrics(null)
    setImpact(null)
    setContract(null)
    setCompFiles([])
    // Fetch metrics, impact, contract and file list in parallel
    getComponentMetrics(projectPath, comp.id).then(setMetrics).catch(() => {})
    getComponentImpact(projectPath, comp.id).then(setImpact).catch(() => {})
    getContract(projectPath, comp.id).then(setContract).catch(() => {})
    listComponentFiles(projectPath, comp.id).then(setCompFiles).catch(() => {})
  }, [comp.id, projectPath])

  const handleMapFile = async () => {
    const fp = mapInput.trim()
    if (!fp) return
    setMapping(true)
    try {
      const added = await mapFile(projectPath, fp, comp.id)
      setCompFiles(prev => [...prev, added])
      setMapInput('')
      onUpdated()
    } catch (e: any) { toast('error', e.message) }
    finally { setMapping(false) }
  }

  const handleUnmapCompFile = async (file: FileMapping) => {
    try {
      await unmapFile(projectPath, file.file_path)
      setCompFiles(prev => prev.filter(f => f.file_path !== file.file_path))
      onFileUnmapped?.(file.file_path)
    } catch (e: any) { toast('error', e.message) }
  }

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
      width: panelWidth, flexShrink: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden',
      position: 'relative',
      background: 'rgba(10,16,28,0.97)', borderLeft: '1px solid rgba(255,255,255,0.07)',
      backdropFilter: 'blur(20px)',
    }}>
      {resizeHandle}
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

            {/* ── Interface Contract ───────────────────────────────── */}
            {contract && (
              <Section icon={<Zap size={11} />} label={`Interface Contract${contract.declared ? ' ✓' : ' (undeclared)'}`}>
                {!contract.declared ? (
                  <p style={{ fontSize: 10.5, color: 'var(--text-muted)' }}>No contract declared yet. Use <code style={{ fontSize: 9, opacity: 0.7 }}>declare_contract</code> MCP tool to define the public interface.</p>
                ) : (
                  <>
                    {/* Node hierarchy metadata */}
                    <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap', marginBottom: 10 }}>
                      {comp.level && (
                        <span style={{ padding: '2px 8px', borderRadius: 99, fontSize: 9.5, background: 'rgba(167,139,250,0.12)', color: '#a78bfa', border: '1px solid rgba(167,139,250,0.25)' }}>
                          L{comp.level} · {LEVEL_LABELS[comp.level as NodeLevel] ?? ''}
                        </span>
                      )}
                      {comp.stability && comp.stability !== 'stable' && (
                        <span style={{ padding: '2px 8px', borderRadius: 99, fontSize: 9.5, background: comp.stability === 'deprecated' ? 'rgba(239,68,68,0.12)' : 'rgba(245,158,11,0.12)', color: comp.stability === 'deprecated' ? '#f87171' : '#f59e0b', border: `1px solid ${comp.stability === 'deprecated' ? 'rgba(239,68,68,0.25)' : 'rgba(245,158,11,0.25)'}` }}>
                          {comp.stability}
                        </span>
                      )}
                    </div>
                    {contract.sla && (
                      <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 8, padding: '4px 8px', background: 'rgba(255,255,255,0.03)', borderRadius: 5, border: '1px solid rgba(255,255,255,0.07)' }}>
                        SLA: <span style={{ color: 'var(--text-secondary)' }}>{contract.sla}</span>
                      </div>
                    )}
                    {contract.commands.length > 0 && (
                      <div style={{ marginBottom: 8 }}>
                        <div style={{ fontSize: 9, fontWeight: 700, color: '#f97316', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 4 }}>Commands</div>
                        {contract.commands.map((op: any) => (
                          <div key={op.name} style={{ fontSize: 10, padding: '3px 7px', marginBottom: 2, borderRadius: 5, background: 'rgba(249,115,22,0.06)', border: '1px solid rgba(249,115,22,0.15)', fontFamily: 'monospace', color: '#fed7aa' }}>
                            {op.name}
                            {op.input_type && <span style={{ color: 'var(--text-muted)', marginLeft: 5 }}>({op.input_type})</span>}
                            {op.output_type && <span style={{ color: 'var(--text-muted)' }}> → {op.output_type}</span>}
                          </div>
                        ))}
                      </div>
                    )}
                    {contract.queries.length > 0 && (
                      <div style={{ marginBottom: 8 }}>
                        <div style={{ fontSize: 9, fontWeight: 700, color: '#3b82f6', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 4 }}>Queries</div>
                        {contract.queries.map((op: any) => (
                          <div key={op.name} style={{ fontSize: 10, padding: '3px 7px', marginBottom: 2, borderRadius: 5, background: 'rgba(59,130,246,0.06)', border: '1px solid rgba(59,130,246,0.15)', fontFamily: 'monospace', color: '#bfdbfe' }}>
                            {op.name}
                            {op.output_type && <span style={{ color: 'var(--text-muted)' }}> → {op.output_type}</span>}
                          </div>
                        ))}
                      </div>
                    )}
                    {contract.events_emitted.length > 0 && (
                      <div style={{ marginBottom: 8 }}>
                        <div style={{ fontSize: 9, fontWeight: 700, color: '#22c55e', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 4 }}>Events Emitted</div>
                        {contract.events_emitted.map((ev: any) => (
                          <div key={ev.name} style={{ fontSize: 10, padding: '3px 7px', marginBottom: 2, borderRadius: 5, background: 'rgba(34,197,94,0.06)', border: '1px solid rgba(34,197,94,0.15)', fontFamily: 'monospace', color: '#bbf7d0' }}>
                            {ev.name}
                            {ev.payload_type && <span style={{ color: 'var(--text-muted)', marginLeft: 5 }}>[{ev.payload_type}]</span>}
                          </div>
                        ))}
                      </div>
                    )}
                    {contract.data_owned.length > 0 && (
                      <div style={{ marginBottom: 4 }}>
                        <div style={{ fontSize: 9, fontWeight: 700, color: '#fbbf24', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 4 }}>Data Owned</div>
                        {contract.data_owned.map((dt: any) => (
                          <div key={dt.type_name} style={{ fontSize: 10, padding: '3px 7px', marginBottom: 2, borderRadius: 5, background: 'rgba(251,191,36,0.06)', border: '1px solid rgba(251,191,36,0.15)', fontFamily: 'monospace', color: '#fde68a' }}>
                            {dt.type_name}
                            {dt.authoritative && <span style={{ fontSize: 8, marginLeft: 5, color: '#fbbf24' }}>authoritative</span>}
                          </div>
                        ))}
                      </div>
                    )}
                  </>
                )}
              </Section>
            )}

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

            {/* ── Files ─────────────────────────────────────────────── */}
            <Section icon={<FolderPlus size={11} />} label={`Files (${compFiles.length})`}>
              {compFiles.map((f: FileMapping) => (
                <div key={f.file_path} style={{ display: 'flex', alignItems: 'center', gap: 5, marginBottom: 4, padding: '4px 7px', background: 'rgba(255,255,255,0.03)', borderRadius: 6, border: '1px solid rgba(255,255,255,0.06)', minWidth: 0 }}>
                  <FileCode size={9} color={c} style={{ flexShrink: 0 }} />
                  <span style={{ flex: 1, fontSize: 10, fontFamily: 'monospace', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: 'var(--text-secondary)' }} title={f.file_path}>
                    {f.file_path.split(/[/\\]/).pop()}
                  </span>
                  {f.metadata?.language && (
                    <span style={{ fontSize: 7.5, padding: '1px 4px', borderRadius: 3, background: c + '18', color: c, fontFamily: 'monospace', flexShrink: 0 }}>{f.metadata.language}</span>
                  )}
                  <button
                    onClick={() => handleUnmapCompFile(f)}
                    title="Unmap file"
                    style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#f87171', padding: 2, display: 'flex', alignItems: 'center', flexShrink: 0, opacity: 0.6 }}
                    onMouseEnter={e => (e.currentTarget.style.opacity = '1')}
                    onMouseLeave={e => (e.currentTarget.style.opacity = '0.6')}
                  >
                    <X size={9} />
                  </button>
                </div>
              ))}
              {compFiles.length === 0 && (
                <p style={{ fontSize: 10.5, color: 'var(--text-muted)', marginBottom: 8 }}>No files mapped yet.</p>
              )}
              {/* Map file input */}
              <div style={{ display: 'flex', gap: 5, marginTop: 6 }}>
                <input
                  type="text"
                  placeholder="path/to/file.py"
                  value={mapInput}
                  onChange={e => setMapInput(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleMapFile()}
                  style={{ flex: 1, fontSize: 10.5, fontFamily: 'monospace' }}
                />
                <button
                  className="btn btn-primary btn-sm"
                  onClick={handleMapFile}
                  disabled={mapping || !mapInput.trim()}
                  style={{ flexShrink: 0 }}
                >
                  {mapping ? <span className="spinner" style={{ width: 10, height: 10 }} /> : <Link size={10} />}
                </button>
              </div>
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

function FilePanel({ file, projectPath, onClose, onSync }: {
  file: FileMapping
  projectPath: string
  onClose: () => void
  onSync?: (updated: FileMapping) => void
}) {
  const [panelWidth, resizeHandle] = usePanelResize(300)
  const [content, setContent] = useState<FileContent | null>(null)
  const [loadingContent, setLoadingContent] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [editingDesc, setEditingDesc] = useState(false)
  const [descDraft, setDescDraft] = useState(file.metadata?.description ?? '')
  const [savingDesc, setSavingDesc] = useState(false)
  const { description, functions, language } = file.metadata ?? {}
  const basename = file.file_path.split(/[/\\]/).pop() ?? file.file_path
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
    setDescDraft(file.metadata?.description ?? '')
    setEditingDesc(false)
  }, [file.file_path, projectPath, file.metadata?.description])

  const handleSync = async () => {
    setSyncing(true)
    try {
      const updated = await syncFileSymbols(projectPath, file.file_path)
      onSync?.(updated)
    } catch { /* silent */ }
    finally { setSyncing(false) }
  }

  const handleSaveDesc = async () => {
    setSavingDesc(true)
    try {
      const updated = await annotateFile(projectPath, file.file_path, { description: descDraft })
      onSync?.(updated)
      setEditingDesc(false)
    } catch { /* silent */ }
    finally { setSavingDesc(false) }
  }

  return (
    <div style={{
      width: panelWidth, flexShrink: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden',
      position: 'relative',
      background: 'rgba(8,13,24,0.98)', borderLeft: '1px solid rgba(255,255,255,0.07)',
      backdropFilter: 'blur(20px)',
    }}>
      {resizeHandle}
      <div style={{ height: 2, background: `linear-gradient(90deg, ${langColor}cc, transparent)` }} />

      {/* Header */}
      <div style={{ padding: '12px 16px', borderBottom: '1px solid rgba(255,255,255,0.07)', display: 'flex', alignItems: 'center', gap: 8 }}>
        <FileCode size={14} color={langColor} style={{ flexShrink: 0 }} />
        <div style={{ flex: 1, overflow: 'hidden' }}>
          <div style={{ fontWeight: 700, fontSize: 12.5, fontFamily: 'monospace', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{basename}</div>
          <div style={{ fontSize: 9, color: 'var(--text-muted)', fontFamily: 'monospace', marginTop: 1 }}>{file.file_path}</div>
        </div>
        <button
          onClick={handleSync}
          title="Sync symbols from actual file"
          disabled={syncing}
          style={{ background: 'none', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 6, cursor: 'pointer', color: langColor, padding: '3px 6px', display: 'flex', alignItems: 'center', gap: 4 }}
        >
          {syncing ? <span className="spinner" style={{ width: 10, height: 10 }} /> : <RefreshCw size={10} />}
        </button>
        <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', padding: 4 }}><X size={13} /></button>
      </div>

      <div style={{ flex: 1, overflowY: 'auto' }}>
        {/* Description — editable */}
        <div style={{ padding: '12px 16px', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
            <div style={{ fontSize: 9, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', flex: 1 }}>Description</div>
            {!editingDesc && (
              <button onClick={() => setEditingDesc(true)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', padding: 2 }}><Edit2 size={9} /></button>
            )}
          </div>
          {editingDesc ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <textarea
                value={descDraft}
                onChange={e => setDescDraft(e.target.value)}
                style={{ fontSize: 11, lineHeight: 1.6, minHeight: 70, resize: 'vertical' }}
                autoFocus
              />
              <div style={{ display: 'flex', gap: 6 }}>
                <button className="btn btn-primary btn-sm" onClick={handleSaveDesc} disabled={savingDesc}>
                  {savingDesc ? <span className="spinner" style={{ width: 10, height: 10 }} /> : <Check size={10} />} Save
                </button>
                <button className="btn btn-ghost btn-sm" onClick={() => { setEditingDesc(false); setDescDraft(description ?? '') }}>Cancel</button>
              </div>
            </div>
          ) : description ? (
            <p style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.7, cursor: 'text' }} onClick={() => setEditingDesc(true)}>{description}</p>
          ) : (
            <p style={{ fontSize: 11, color: 'var(--text-muted)', cursor: 'text', fontStyle: 'italic' }} onClick={() => setEditingDesc(true)}>Click to add description…</p>
          )}
        </div>

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
  const [panelWidth, resizeHandle] = usePanelResize(400)
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
      width: panelWidth, flexShrink: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden',
      position: 'relative',
      background: 'rgba(8,13,24,0.98)', borderLeft: '1px solid rgba(255,255,255,0.07)',
      backdropFilter: 'blur(20px)',
    }}>
      {resizeHandle}
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


function buildNodes(components: Component[], childrenMap: Record<string, string[]>): Node[] {
  return components.map(c => ({
    id: c.id, type: 'component',
    data: {
      label: c.name,
      layer: c.layer,
      confidence: c.confidence,
      level: c.level ?? 4,
      parent_id: c.parent_id ?? '',
      public_api: c.public_api ?? [],
      stability: c.stability ?? 'stable',
      protocol: c.protocol ?? '',
      hasChildren: (childrenMap[c.id] ?? []).length > 0,
    },
    position: { x: 0, y: 0 },
  }))
}

function depToEdge(d: Dependency, isCycle = false): Edge {
  const isAuto   = d.confidence === 'auto'
  const edgeType = d.edge_type ?? ''
  const edgeColor = EDGE_TYPE_COLOR[edgeType]
  const color = isCycle ? '#f87171' : edgeColor ?? (isAuto ? '#64748b' : '#60a5fa')
  // Show edge_type or label (whichever is more informative)
  const edgeLabel = edgeType && edgeType !== 'invoke' ? edgeType.replace('_', ' ') : d.label
  return {
    id: d.id,
    source: d.from_component,
    target: d.to_component,
    type: 'floating',
    label: edgeLabel,
    markerEnd: { type: MarkerType.ArrowClosed, width: 10, height: 10, color },
    labelStyle: { fill: isCycle ? '#f87171' : edgeColor ?? (isAuto ? '#475569' : '#64748b'), fontSize: 9.5 },
    labelBgStyle: { fill: 'rgba(8,12,20,0.85)', fillOpacity: 1 },
    labelBgPadding: [4, 3] as [number, number],
    labelBgBorderRadius: 4,
    data: {
      confidence: d.confidence,
      isCycle,
      edge_type: d.edge_type,
      async_flag: d.async_flag,
      crosses_boundary: d.crosses_boundary,
      stability: d.stability,
      interface_points: d.interface_points,
      payload_types: d.payload_types,
    },
  }
}

function buildEdges(deps: Dependency[]): Edge[] {
  return deps.map(d => depToEdge(d, false))
}

function computeCycleEdgeIds(deps: Dependency[]): Set<string> {
  // BFS to find which component IDs are in a cycle, then mark edges between them
  const outgoing: Record<string, string[]> = {}
  for (const d of deps) {
    if (!outgoing[d.from_component]) outgoing[d.from_component] = []
    outgoing[d.from_component].push(d.to_component)
  }
  const bfs = (start: string): Set<string> => {
    const visited = new Set<string>()
    const queue = [start]
    while (queue.length) {
      const cur = queue.shift()!
      for (const nxt of outgoing[cur] ?? []) {
        if (!visited.has(nxt) && nxt !== start) { visited.add(nxt); queue.push(nxt) }
      }
    }
    return visited
  }
  const cycleNodes = new Set<string>()
  for (const d of deps) {
    if (bfs(d.to_component).has(d.from_component)) {
      cycleNodes.add(d.from_component)
      cycleNodes.add(d.to_component)
    }
  }
  return new Set(deps.filter(d => cycleNodes.has(d.from_component) && cycleNodes.has(d.to_component)).map(d => d.id))
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
