import React, { useEffect } from 'react'
import { Routes, Route, NavLink, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard, Layers, ClipboardList, FolderSearch,
  X, CheckCircle2, AlertCircle, Info, Map,
} from 'lucide-react'
import DashboardPage from './pages/DashboardPage'
import ArchitecturePage from './pages/ArchitecturePage'
import PlanPage from './pages/PlanPage'
import MappingsPage from './pages/MappingsPage'
import { useStore } from './store'
import { projectStatus } from './api/archMapApi'

const NAV_ITEMS = [
  { to: '/',             label: 'Dashboard',    icon: LayoutDashboard, end: true },
  { to: '/architecture', label: 'Architecture', icon: Layers },
  { to: '/plan',         label: 'Plan',         icon: ClipboardList },
  { to: '/mappings',     label: 'Mappings',     icon: FolderSearch },
]

export default function App() {
  const { projectPath, projectStatus: status, setProjectStatus, toasts, dismissToast } = useStore()

  // Refresh project status whenever path changes
  useEffect(() => {
    if (!projectPath) return
    projectStatus(projectPath)
      .then(setProjectStatus)
      .catch(() => setProjectStatus(null))
  }, [projectPath])

  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
      {/* Sidebar */}
      <aside style={{
        width: 220, flexShrink: 0, display: 'flex', flexDirection: 'column',
        background: 'var(--bg-surface)',
        borderRight: '1px solid var(--border)',
      }}>
        {/* Logo */}
        <div style={{
          padding: '20px 20px 16px',
          borderBottom: '1px solid var(--border)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{
              width: 32, height: 32, borderRadius: 8,
              background: 'linear-gradient(135deg, #4f7cff 0%, #a855f7 100%)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              boxShadow: '0 2px 12px rgba(79,124,255,0.4)',
            }}>
              <Map size={16} color="#fff" />
            </div>
            <div>
              <div style={{ fontWeight: 700, fontSize: 15, letterSpacing: '-0.3px', color: 'var(--text-primary)' }}>ArchMap</div>
              <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 1 }}>v0.1.0</div>
            </div>
          </div>
        </div>

        {/* Project indicator */}
        {status && (
          <div style={{
            margin: '12px 12px 0',
            padding: '10px 12px',
            background: 'var(--bg-card)',
            borderRadius: 'var(--radius)',
            border: '1px solid var(--border)',
          }}>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 3, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Project</div>
            <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{status.name}</div>
            <div style={{ display: 'flex', gap: 10, marginTop: 6 }}>
              <Chip label={`${status.components} comp`} color="var(--accent)" />
              <Chip label={`${status.plan_open} open`} color="var(--yellow)" />
            </div>
          </div>
        )}

        {/* Nav */}
        <nav style={{ flex: 1, padding: '12px 8px', overflowY: 'auto' }}>
          {NAV_ITEMS.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to} to={to} end={end}
              style={({ isActive }) => ({
                display: 'flex', alignItems: 'center', gap: 10,
                padding: '9px 12px', borderRadius: 'var(--radius-sm)',
                marginBottom: 2, textDecoration: 'none',
                fontSize: 13, fontWeight: 500,
                background: isActive ? 'var(--accent-dim)' : 'transparent',
                color: isActive ? 'var(--accent)' : 'var(--text-secondary)',
                borderLeft: isActive ? '2px solid var(--accent)' : '2px solid transparent',
                transition: 'all 0.12s ease',
              })}
            >
              <Icon size={15} />
              {label}
            </NavLink>
          ))}
        </nav>

        {/* Status dot */}
        <div style={{
          padding: '12px 20px',
          borderTop: '1px solid var(--border)',
          display: 'flex', alignItems: 'center', gap: 8,
        }}>
          <div style={{
            width: 7, height: 7, borderRadius: '50%',
            background: projectPath ? 'var(--green)' : 'var(--text-muted)',
            boxShadow: projectPath ? '0 0 8px rgba(34,197,94,0.6)' : 'none',
          }} />
          <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
            {projectPath ? 'Connected' : 'No project'}
          </span>
        </div>
      </aside>

      {/* Main content */}
      <main style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column', background: 'var(--bg-base)' }}>
        <Routes>
          <Route path="/"             element={<DashboardPage />} />
          <Route path="/architecture" element={<ArchitecturePage />} />
          <Route path="/plan"         element={<PlanPage />} />
          <Route path="/mappings"     element={<MappingsPage />} />
        </Routes>
      </main>

      {/* Toast stack */}
      <div style={{
        position: 'fixed', bottom: 24, right: 24,
        display: 'flex', flexDirection: 'column', gap: 8,
        zIndex: 9999,
      }}>
        {toasts.map(t => (
          <div key={t.id} style={{
            display: 'flex', alignItems: 'center', gap: 10,
            padding: '12px 16px', borderRadius: 'var(--radius)',
            background: 'var(--bg-raised)', border: `1px solid ${t.type === 'error' ? '#ef444433' : t.type === 'success' ? '#22c55e33' : 'var(--border)'}`,
            boxShadow: 'var(--shadow)', animation: 'slideUp 0.2s ease',
            maxWidth: 360, minWidth: 260,
          }}>
            {t.type === 'success' && <CheckCircle2 size={15} color="var(--green)" />}
            {t.type === 'error'   && <AlertCircle  size={15} color="var(--red)" />}
            {t.type === 'info'    && <Info          size={15} color="var(--accent)" />}
            <span style={{ flex: 1, fontSize: 13, color: 'var(--text-primary)' }}>{t.message}</span>
            <button onClick={() => dismissToast(t.id)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', padding: 2 }}>
              <X size={13} />
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}

function Chip({ label, color }: { label: string; color: string }) {
  return (
    <span style={{ fontSize: 10, color, background: color + '22', padding: '2px 7px', borderRadius: 10, fontWeight: 600 }}>
      {label}
    </span>
  )
}
