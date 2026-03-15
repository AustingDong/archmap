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
  Activity, Zap, AlertTriangle, FileCode, Cpu, RefreshCw, FolderPlus, Link, Search, Map,
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
  describeArchitecture, findRelated, tracePath,
} from '../api/archMapApi'
import type { Component, Dependency, FileMapping, Layer, ComponentMetrics, ComponentImpact, FileContent, SymbolExtract, RelatedSearchResult, PathTrace } from '../types'

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

// ── Markdown renderer ──────────────────────────────────────────────────────────
// Lightweight line-by-line renderer: h1/h2/h3, bold, inline code, bullets, hr.

function renderInline(text: string): React.ReactNode[] {
  // Parse **bold** and `code` inline spans
  const parts: React.ReactNode[] = []
  const rx = /(\*\*(.+?)\*\*|`([^`]+)`)/g
  let last = 0, m: RegExpExecArray | null
  while ((m = rx.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index))
    if (m[2] != null) parts.push(<strong key={m.index} style={{ color: '#e2e8f0', fontWeight: 700 }}>{m[2]}</strong>)
    else parts.push(<code key={m.index} style={{ fontFamily: 'monospace', fontSize: '0.9em', padding: '1px 5px', borderRadius: 4, background: 'rgba(96,165,250,0.12)', color: '#93c5fd' }}>{m[3]}</code>)
    last = m.index + m[0].length
  }
  if (last < text.length) parts.push(text.slice(last))
  return parts
}

function MarkdownView({ text }: { text: string }) {
  const lines = text.split('\n')
  const nodes: React.ReactNode[] = []
  let bulletBuf: string[] = []

  const flushBullets = () => {
    if (!bulletBuf.length) return
    nodes.push(
      <ul key={`ul-${nodes.length}`} style={{ margin: '4px 0 10px 0', paddingLeft: 18, listStyle: 'none' }}>
        {bulletBuf.map((b, i) => (
          <li key={i} style={{ fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.65, marginBottom: 2, display: 'flex', gap: 7, alignItems: 'flex-start' }}>
            <span style={{ color: '#60a5fa', marginTop: 1, flexShrink: 0 }}>›</span>
            <span>{renderInline(b)}</span>
          </li>
        ))}
      </ul>
    )
    bulletBuf = []
  }

  lines.forEach((raw, idx) => {
    const line = raw.trimEnd()

    if (line.startsWith('# ')) {
      flushBullets()
      nodes.push(
        <div key={idx} style={{
          fontSize: 15, fontWeight: 800, color: '#f1f5f9', marginTop: nodes.length ? 18 : 0, marginBottom: 6,
          paddingBottom: 6, borderBottom: '1px solid rgba(96,165,250,0.2)',
          letterSpacing: '-0.01em',
        }}>{renderInline(line.slice(2))}</div>
      )
    } else if (line.startsWith('## ')) {
      flushBullets()
      nodes.push(
        <div key={idx} style={{
          fontSize: 12, fontWeight: 700, color: '#94c8ff', marginTop: 16, marginBottom: 5,
          display: 'flex', alignItems: 'center', gap: 7,
        }}>
          <span style={{ display: 'inline-block', width: 3, height: 12, borderRadius: 2, background: '#60a5fa', flexShrink: 0 }} />
          {renderInline(line.slice(3))}
        </div>
      )
    } else if (line.startsWith('### ')) {
      flushBullets()
      nodes.push(
        <div key={idx} style={{ fontSize: 10.5, fontWeight: 700, color: '#7dd3fc', marginTop: 10, marginBottom: 3, textTransform: 'uppercase', letterSpacing: '0.07em' }}>
          {renderInline(line.slice(4))}
        </div>
      )
    } else if (/^-{3,}$/.test(line)) {
      flushBullets()
      nodes.push(<hr key={idx} style={{ border: 'none', borderTop: '1px solid rgba(255,255,255,0.07)', margin: '10px 0' }} />)
    } else if (line.startsWith('- ') || line.startsWith('* ')) {
      bulletBuf.push(line.slice(2))
    } else if (line.trim() === '') {
      flushBullets()
      nodes.push(<div key={idx} style={{ height: 4 }} />)
    } else {
      flushBullets()
      nodes.push(
        <p key={idx} style={{ fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.75, margin: '0 0 4px 0' }}>
          {renderInline(line)}
        </p>
      )
    }
  })
  flushBullets()

  return <div>{nodes}</div>
}

// ── Intelligence Panel ─────────────────────────────────────────────────────────
// Searchable graph explorer for humans and agents. Provides find_related,
// describe_architecture, and trace_path without leaving the graph view.

function IntelligencePanel({ projectPath, components, onClose }: {
  projectPath: string
  components: Component[]
  onClose: () => void
}) {
  const [panelWidth, resizeHandle] = usePanelResize(380)
  const [tab, setTab] = React.useState<'search' | 'describe' | 'trace'>('search')
  const [query, setQuery] = React.useState('')
  const [searchResult, setSearchResult] = React.useState<RelatedSearchResult | null>(null)
  const [searching, setSearching] = React.useState(false)
  const [descText, setDescText] = React.useState<string | null>(null)
  const [descLoading, setDescLoading] = React.useState(false)
  const [traceFrom, setTraceFrom] = React.useState('')
  const [traceTo, setTraceTo] = React.useState('')
  const [traceResult, setTraceResult] = React.useState<PathTrace | null>(null)
  const [tracing, setTracing] = React.useState(false)

  const handleSearch = async () => {
    if (!query.trim()) return
    setSearching(true)
    try { setSearchResult(await findRelated(projectPath, query)) }
    catch { /* silent */ }
    finally { setSearching(false) }
  }

  const handleDescribe = async () => {
    if (descText) return  // already loaded
    setDescLoading(true)
    try { const r = await describeArchitecture(projectPath); setDescText(r.text) }
    catch { /* silent */ }
    finally { setDescLoading(false) }
  }

  React.useEffect(() => { if (tab === 'describe') handleDescribe() }, [tab])

  const handleTrace = async () => {
    if (!traceFrom || !traceTo) return
    setTracing(true)
    try { setTraceResult(await tracePath(projectPath, traceFrom, traceTo)) }
    catch { /* silent */ }
    finally { setTracing(false) }
  }

  const TAB_STYLE = (active: boolean) => ({
    flex: 1, padding: '6px 0', fontSize: 10.5, fontWeight: active ? 700 : 500,
    background: active ? 'rgba(96,165,250,0.12)' : 'none',
    border: 'none', borderBottom: `2px solid ${active ? '#60a5fa' : 'transparent'}`,
    cursor: 'pointer', color: active ? '#60a5fa' : 'var(--text-muted)', transition: 'all 0.15s',
  })

  return (
    <div style={{
      width: panelWidth, flexShrink: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden',
      position: 'relative',
      background: 'rgba(8,13,24,0.98)', borderLeft: '1px solid rgba(255,255,255,0.07)',
      backdropFilter: 'blur(20px)',
    }}>
      {resizeHandle}
      <div style={{ height: 2, background: 'linear-gradient(90deg, #60a5facc, #34d39944)' }} />

      {/* Header */}
      <div style={{ padding: '12px 16px', borderBottom: '1px solid rgba(255,255,255,0.07)', display: 'flex', alignItems: 'center', gap: 9 }}>
        <Map size={14} color="#60a5fa" style={{ flexShrink: 0 }} />
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 700, fontSize: 13 }}>Graph Intelligence</div>
          <div style={{ fontSize: 9, color: 'var(--text-muted)', marginTop: 1 }}>Explore the architecture without reading source files</div>
        </div>
        <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', padding: 4 }}><X size={13} /></button>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', borderBottom: '1px solid rgba(255,255,255,0.07)' }}>
        <button style={TAB_STYLE(tab === 'search')} onClick={() => setTab('search')}>Search</button>
        <button style={TAB_STYLE(tab === 'describe')} onClick={() => setTab('describe')}>Overview</button>
        <button style={TAB_STYLE(tab === 'trace')} onClick={() => setTab('trace')}>Trace Path</button>
      </div>

      <div style={{ flex: 1, overflowY: 'auto' }}>

        {/* ── Search tab ── */}
        {tab === 'search' && (
          <div style={{ padding: 16 }}>
            <div style={{ display: 'flex', gap: 6, marginBottom: 14 }}>
              <input
                type="text" placeholder="e.g. authentication, database, validate..."
                value={query} onChange={e => setQuery(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleSearch()}
                style={{ flex: 1, fontSize: 11.5 }} autoFocus
              />
              <button className="btn btn-primary btn-sm" onClick={handleSearch} disabled={searching || !query.trim()}>
                {searching ? <span className="spinner" style={{ width: 10, height: 10 }} /> : <Search size={11} />}
              </button>
            </div>

            {searchResult && (
              <>
                <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 10, padding: '5px 9px', background: 'rgba(96,165,250,0.06)', borderRadius: 7, border: '1px solid rgba(96,165,250,0.12)' }}>
                  {searchResult.summary}
                </div>

                {searchResult.components.length > 0 && (
                  <div style={{ marginBottom: 12 }}>
                    <div style={{ fontSize: 9, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 6 }}>Components</div>
                    {searchResult.components.map(c => (
                      <div key={c.id} style={{ marginBottom: 5, padding: '6px 9px', background: 'rgba(255,255,255,0.03)', borderRadius: 7, border: '1px solid rgba(255,255,255,0.07)' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 3 }}>
                          <div style={{ width: 7, height: 7, borderRadius: '50%', background: LAYER_COLOR[c.layer] ?? '#94a3b8', flexShrink: 0 }} />
                          <span style={{ fontSize: 11.5, fontWeight: 700 }}>{c.name}</span>
                          <span style={{ fontSize: 9, color: 'var(--text-muted)', marginLeft: 'auto' }}>{c.layer}</span>
                        </div>
                        {c.description && <p style={{ fontSize: 10.5, color: 'var(--text-muted)', lineHeight: 1.5, margin: 0 }}>{c.description}</p>}
                      </div>
                    ))}
                  </div>
                )}

                {searchResult.files.length > 0 && (
                  <div style={{ marginBottom: 12 }}>
                    <div style={{ fontSize: 9, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 6 }}>Files</div>
                    {searchResult.files.slice(0, 8).map(f => (
                      <div key={f.file_path} style={{ marginBottom: 4, padding: '5px 9px', background: 'rgba(255,255,255,0.02)', borderRadius: 6, border: '1px solid rgba(255,255,255,0.06)' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                          <FileCode size={9} color="var(--text-muted)" style={{ flexShrink: 0 }} />
                          <span style={{ fontSize: 10, fontFamily: 'monospace', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.file_path}</span>
                          {f.language && <span style={{ fontSize: 8, color: 'var(--text-muted)' }}>{f.language}</span>}
                        </div>
                        {f.component_name && <div style={{ fontSize: 9, color: 'var(--text-muted)', marginTop: 1, paddingLeft: 14 }}>→ {f.component_name}</div>}
                      </div>
                    ))}
                  </div>
                )}

                {searchResult.symbols.length > 0 && (
                  <div>
                    <div style={{ fontSize: 9, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 6 }}>Symbols</div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                      {searchResult.symbols.slice(0, 20).map((s, i) => {
                        const isCls = !s.symbol.endsWith('()')
                        return (
                          <div key={i} style={{ padding: '3px 8px', borderRadius: 5, fontSize: 9.5, fontFamily: 'monospace', background: isCls ? 'rgba(168,85,247,0.1)' : 'rgba(96,165,250,0.08)', color: isCls ? '#a855f7' : '#60a5fa', border: `1px solid ${isCls ? 'rgba(168,85,247,0.2)' : 'rgba(96,165,250,0.15)'}` }} title={`${s.file_path} → ${s.component_name}`}>
                            {s.symbol}
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )}
              </>
            )}

            {!searchResult && (
              <p style={{ fontSize: 11, color: 'var(--text-muted)', lineHeight: 1.7 }}>
                Search across component names, descriptions, file paths, and symbol names.<br />
                <span style={{ opacity: 0.6 }}>Try: "auth", "api", "store", "validate"</span>
              </p>
            )}
          </div>
        )}

        {/* ── Describe tab ── */}
        {tab === 'describe' && (
          <div style={{ padding: 16 }}>
            {descLoading && <div style={{ display: 'flex', justifyContent: 'center', padding: 24 }}><span className="spinner spinner-lg" /></div>}
            {descText && <MarkdownView text={descText} />}
            {descText && (
              <button
                className="btn btn-ghost btn-sm"
                style={{ marginTop: 12, width: '100%', justifyContent: 'center' }}
                onClick={() => { navigator.clipboard.writeText(descText) }}
              >
                Copy for Agent
              </button>
            )}
          </div>
        )}

        {/* ── Trace tab ── */}
        {tab === 'trace' && (
          <div style={{ padding: 16 }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 14 }}>
              <div>
                <label style={{ fontSize: 9.5, color: 'var(--text-muted)', marginBottom: 3, display: 'block' }}>From component</label>
                <select value={traceFrom} onChange={e => setTraceFrom(e.target.value)} style={{ width: '100%', fontSize: 11 }}>
                  <option value="">— select —</option>
                  {components.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
              </div>
              <div>
                <label style={{ fontSize: 9.5, color: 'var(--text-muted)', marginBottom: 3, display: 'block' }}>To component</label>
                <select value={traceTo} onChange={e => setTraceTo(e.target.value)} style={{ width: '100%', fontSize: 11 }}>
                  <option value="">— select —</option>
                  {components.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
              </div>
              <button className="btn btn-primary btn-sm" onClick={handleTrace} disabled={tracing || !traceFrom || !traceTo}>
                {tracing ? <span className="spinner" style={{ width: 10, height: 10 }} /> : 'Trace Path'}
              </button>
            </div>

            {traceResult && (
              traceResult.found ? (
                <div>
                  <div style={{ padding: '7px 10px', marginBottom: 10, borderRadius: 8, background: 'rgba(52,211,153,0.08)', border: '1px solid rgba(52,211,153,0.2)', fontSize: 10.5, color: '#34d399', fontWeight: 600 }}>
                    Path found — {traceResult.length} hop{traceResult.length !== 1 ? 's' : ''}
                  </div>
                  <div style={{ fontSize: 10, fontFamily: 'monospace', color: 'var(--text-muted)', marginBottom: 12, padding: '6px 9px', background: 'rgba(255,255,255,0.03)', borderRadius: 6 }}>
                    {traceResult.text}
                  </div>
                  {traceResult.path.map((node, i) => (
                    <div key={node.component_id} style={{ marginBottom: 6 }}>
                      {i > 0 && node.via_dependency && (
                        <div style={{ fontSize: 9, color: 'var(--text-muted)', paddingLeft: 12, marginBottom: 2 }}>
                          ↓ {node.via_dependency.label} ({node.via_dependency.confidence})
                        </div>
                      )}
                      <div style={{ padding: '6px 9px', borderRadius: 7, background: 'rgba(255,255,255,0.03)', border: `1px solid ${LAYER_COLOR[node.layer] ?? '#94a3b8'}22` }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                          <div style={{ width: 6, height: 6, borderRadius: '50%', background: LAYER_COLOR[node.layer] ?? '#94a3b8', flexShrink: 0 }} />
                          <span style={{ fontSize: 11.5, fontWeight: 700 }}>{node.component_name}</span>
                          <span style={{ fontSize: 9, color: 'var(--text-muted)', marginLeft: 'auto' }}>{node.layer}</span>
                        </div>
                        {node.files.length > 0 && (
                          <div style={{ marginTop: 4, paddingLeft: 12 }}>
                            {node.files.map(f => (
                              <span key={f} style={{ fontSize: 8.5, fontFamily: 'monospace', color: 'var(--text-muted)', display: 'block' }}>{f}</span>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div style={{ padding: '7px 10px', borderRadius: 8, background: 'rgba(248,113,113,0.08)', border: '1px solid rgba(248,113,113,0.2)', fontSize: 10.5, color: '#f87171' }}>
                  {traceResult.text ?? traceResult.error ?? 'No path found'}
                </div>
              )
            )}

            {!traceResult && (
              <p style={{ fontSize: 11, color: 'var(--text-muted)', lineHeight: 1.7 }}>
                Find the shortest dependency path between two components.<br />
                <span style={{ opacity: 0.6 }}>Useful for understanding data flow and blast radius.</span>
              </p>
            )}
          </div>
        )}
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
  const [showIntel, setShowIntel] = useState(false)
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

  // ── File node CRUD actions ──────────────────────────────────────────────────

  const [syncingFiles, setSyncingFiles] = useState<Set<string>>(new Set())

  // Rebuild symbol nodes for a file node using the provided updated file data (avoids stale closure)
  const refreshSymbolNodes = useCallback((fileNodeId: string, updatedFile: FileMapping) => {
    const symbols: string[] = updatedFile.metadata?.functions ?? []
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
              <div style={{ width: 1, background: 'rgba(255,255,255,0.08)', margin: '0 2px' }} />
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => setShowIntel(v => !v)}
                title="Graph intelligence — search, overview, trace paths"
                style={{ color: showIntel ? '#60a5fa' : undefined, background: showIntel ? 'rgba(96,165,250,0.1)' : undefined }}
              >
                <Map size={12} /> Intelligence
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
      {showIntel && (
        <IntelligencePanel
          projectPath={projectPath}
          components={components}
          onClose={() => setShowIntel(false)}
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

function ComponentPanel({ comp, projectPath, deps, components, onClose, onDelete, onUpdated, toast, onFileUnmapped }: any) {
  const [panelWidth, resizeHandle] = usePanelResize(300)
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState({ name: comp.name, description: comp.description, layer: comp.layer })
  const [metrics, setMetrics] = useState<ComponentMetrics | null>(null)
  const [impact, setImpact] = useState<ComponentImpact | null>(null)
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
    setCompFiles([])
    // Fetch metrics, impact and file list in parallel
    getComponentMetrics(projectPath, comp.id).then(setMetrics).catch(() => {})
    getComponentImpact(projectPath, comp.id).then(setImpact).catch(() => {})
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
