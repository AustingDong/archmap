import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  FolderOpen, Layers, GitBranch, FileCode2, ClipboardList,
  ArrowRight, Scan, Plus, CheckCircle2, AlertTriangle, Zap,
} from 'lucide-react'
import { useStore } from '../store'
import { projectStatus, initProject, scanProject } from '../api/archMapApi'
import type { ProjectStatus } from '../types'

const LAYER_GRADIENT: Record<string, string> = {
  frontend: 'linear-gradient(135deg,#22c55e,#16a34a)',
  backend:  'linear-gradient(135deg,#3b82f6,#1d4ed8)',
  database: 'linear-gradient(135deg,#f59e0b,#d97706)',
  infra:    'linear-gradient(135deg,#a855f7,#7c3aed)',
  shared:   'linear-gradient(135deg,#4f7cff,#3b5bdb)',
  testing:  'linear-gradient(135deg,#ec4899,#be185d)',
  other:    'linear-gradient(135deg,#64748b,#475569)',
}

export default function DashboardPage() {
  const navigate = useNavigate()
  const { projectPath, setProjectPath, setProjectStatus, toast } = useStore()
  const [input, setInput] = useState(projectPath)
  const [status, setStatus] = useState<ProjectStatus | null>(null)
  const [loading, setLoading] = useState(false)
  const [scanning, setScanning] = useState(false)
  const [initing, setIniting] = useState(false)

  const load = async (path: string) => {
    if (!path.trim()) return
    setLoading(true)
    try {
      const s = await projectStatus(path.trim())
      setStatus(s)
      setProjectStatus(s)
      setProjectPath(path.trim())
      toast('success', `Loaded: ${s.name}`)
    } catch (e: any) {
      setStatus(null)
      toast('error', e.message)
    } finally { setLoading(false) }
  }

  const handleInit = async () => {
    if (!input.trim()) return
    setIniting(true)
    try {
      await initProject(input.trim())
      toast('success', 'Project initialized!')
      await load(input.trim())
    } catch (e: any) { toast('error', e.message) }
    finally { setIniting(false) }
  }

  const handleScan = async () => {
    if (!projectPath) return
    setScanning(true)
    try {
      const r = await scanProject(projectPath, false, 2)
      toast('success', r.message)
      const s = await projectStatus(projectPath)
      setStatus(s); setProjectStatus(s)
    } catch (e: any) { toast('error', e.message) }
    finally { setScanning(false) }
  }

  const pct = status
    ? Math.min(100, Math.round((status.plan_items > 0 ? (status.plan_items - status.plan_open) / status.plan_items : 0) * 100))
    : 0

  return (
    <div style={{ height: '100%', overflowY: 'auto', padding: '32px 36px' }}>
      {/* Header */}
      <div style={{ marginBottom: 28 }}>
        <h1 style={{ fontSize: 24, fontWeight: 800, letterSpacing: '-0.5px', color: 'var(--text-primary)' }}>
          {status ? status.name : 'Dashboard'}
        </h1>
        <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 4 }}>
          {status ? 'Architecture overview & quick actions' : 'Load a project to get started'}
        </p>
      </div>

      {/* Project loader */}
      <div style={{
        background: 'var(--bg-card)', borderRadius: 'var(--radius-lg)',
        border: '1px solid var(--border)', padding: 20, marginBottom: 24,
      }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10 }}>
          Project Path
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <div style={{ position: 'relative', flex: 1 }}>
            <FolderOpen size={14} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
            <input
              type="text"
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && load(input)}
              placeholder="C:/Users/you/my-project"
              style={{ paddingLeft: 32 }}
            />
          </div>
          <button className="btn btn-primary" onClick={() => load(input)} disabled={loading}>
            {loading ? <span className="spinner" /> : <><ArrowRight size={14} /> Load</>}
          </button>
          <button className="btn btn-ghost" onClick={handleInit} disabled={initing}>
            {initing ? <span className="spinner" /> : <><Plus size={14} /> Init</>}
          </button>
        </div>
      </div>

      {/* Stats grid */}
      {status && (
        <div className="fade-in">
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, marginBottom: 24 }}>
            <StatCard
              icon={<Layers size={18} />}
              label="Components"
              value={status.components}
              color="#4f7cff"
              onClick={() => navigate('/architecture')}
            />
            <StatCard
              icon={<GitBranch size={18} />}
              label="Dependencies"
              value={status.dependencies}
              color="#a855f7"
              onClick={() => navigate('/architecture')}
            />
            <StatCard
              icon={<FileCode2 size={18} />}
              label="Mapped Files"
              value={status.mapped_files}
              color="#06b6d4"
              onClick={() => navigate('/mappings')}
            />
            <StatCard
              icon={<ClipboardList size={18} />}
              label="Open Tasks"
              value={status.plan_open}
              color="#f59e0b"
              onClick={() => navigate('/plan')}
            />
          </div>

          {/* Progress + Actions row */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 24 }}>
            {/* Progress */}
            <div style={{
              background: 'var(--bg-card)', borderRadius: 'var(--radius-lg)',
              border: '1px solid var(--border)', padding: 20,
            }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 14 }}>
                Plan Progress
              </div>
              <div style={{ fontSize: 32, fontWeight: 800, color: 'var(--text-primary)', marginBottom: 12 }}>
                {pct}%
              </div>
              <div style={{ background: 'var(--border)', borderRadius: 4, height: 6, marginBottom: 10, overflow: 'hidden' }}>
                <div style={{
                  height: '100%', borderRadius: 4,
                  width: `${pct}%`,
                  background: pct >= 80 ? 'var(--green)' : pct >= 40 ? 'var(--accent)' : 'var(--yellow)',
                  transition: 'width 0.6s ease',
                }} />
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                {status.plan_items - status.plan_open} of {status.plan_items} tasks done
              </div>
            </div>

            {/* Quick actions */}
            <div style={{
              background: 'var(--bg-card)', borderRadius: 'var(--radius-lg)',
              border: '1px solid var(--border)', padding: 20,
            }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 14 }}>
                Quick Actions
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <ActionBtn
                  icon={<Scan size={14} />}
                  label={scanning ? 'Scanning…' : 'Auto-scan Components'}
                  onClick={handleScan}
                  disabled={scanning}
                  loading={scanning}
                />
                <ActionBtn
                  icon={<Layers size={14} />}
                  label="View Architecture"
                  onClick={() => navigate('/architecture')}
                />
                <ActionBtn
                  icon={<ClipboardList size={14} />}
                  label="Open Plan Board"
                  onClick={() => navigate('/plan')}
                />
              </div>
            </div>
          </div>

          {/* Health indicators */}
          <div style={{
            background: 'var(--bg-card)', borderRadius: 'var(--radius-lg)',
            border: '1px solid var(--border)', padding: 20,
          }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 14 }}>
              Health Checks
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <HealthRow
                ok={status.components > 0}
                label="Architecture defined"
                sub={status.components > 0 ? `${status.components} components` : 'No components yet — run a scan'}
              />
              <HealthRow
                ok={status.mapped_files > 0}
                label="Files mapped"
                sub={status.mapped_files > 0 ? `${status.mapped_files} files assigned to components` : 'No files mapped — run a scan'}
              />
              <HealthRow
                ok={status.plan_items > 0}
                label="Plan populated"
                sub={status.plan_items > 0 ? `${status.plan_items} tasks total` : 'No tasks yet — create via Plan or MCP'}
              />
            </div>
          </div>
        </div>
      )}

      {!status && !loading && (
        <div style={{ textAlign: 'center', padding: '60px 20px', color: 'var(--text-muted)' }}>
          <div style={{
            width: 64, height: 64, borderRadius: 20,
            background: 'var(--bg-card)', border: '1px solid var(--border)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            margin: '0 auto 16px',
          }}>
            <Zap size={28} color="var(--accent)" />
          </div>
          <p style={{ fontSize: 15, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 6 }}>
            No project loaded
          </p>
          <p style={{ fontSize: 13 }}>
            Enter a project path and click Load, or Init to create a new ArchMap project.
          </p>
        </div>
      )}
    </div>
  )
}

function StatCard({ icon, label, value, color, onClick }: {
  icon: React.ReactNode; label: string; value: number; color: string; onClick?: () => void
}) {
  return (
    <div
      onClick={onClick}
      style={{
        background: 'var(--bg-card)', borderRadius: 'var(--radius-lg)',
        border: '1px solid var(--border)', padding: '18px 20px',
        cursor: onClick ? 'pointer' : 'default',
        transition: 'all 0.15s ease',
      }}
      onMouseEnter={e => onClick && ((e.currentTarget as HTMLDivElement).style.borderColor = color + '66')}
      onMouseLeave={e => ((e.currentTarget as HTMLDivElement).style.borderColor = 'var(--border)')}
    >
      <div style={{
        width: 34, height: 34, borderRadius: 8,
        background: color + '22', color, display: 'flex', alignItems: 'center', justifyContent: 'center',
        marginBottom: 12,
      }}>
        {icon}
      </div>
      <div style={{ fontSize: 28, fontWeight: 800, color: 'var(--text-primary)', lineHeight: 1 }}>{value}</div>
      <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 5 }}>{label}</div>
    </div>
  )
}

function ActionBtn({ icon, label, onClick, disabled, loading }: {
  icon: React.ReactNode; label: string; onClick: () => void; disabled?: boolean; loading?: boolean
}) {
  return (
    <button
      onClick={onClick} disabled={disabled}
      style={{
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '8px 12px', borderRadius: 'var(--radius-sm)',
        background: 'var(--bg-raised)', border: '1px solid var(--border)',
        color: 'var(--text-secondary)', fontSize: 13, cursor: 'pointer',
        textAlign: 'left', transition: 'all 0.12s', width: '100%',
        opacity: disabled ? 0.5 : 1,
      }}
      onMouseEnter={e => !disabled && ((e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--accent)')}
      onMouseLeave={e => ((e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--border)')}
    >
      {loading ? <span className="spinner" /> : icon}
      {label}
    </button>
  )
}

function HealthRow({ ok, label, sub }: { ok: boolean; label: string; sub: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
      {ok
        ? <CheckCircle2 size={16} color="var(--green)" style={{ flexShrink: 0 }} />
        : <AlertTriangle size={16} color="var(--yellow)" style={{ flexShrink: 0 }} />
      }
      <div>
        <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)' }}>{label}</div>
        <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{sub}</div>
      </div>
    </div>
  )
}
