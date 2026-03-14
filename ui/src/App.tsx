import React, { useState } from 'react'
import { Routes, Route, NavLink } from 'react-router-dom'
import DashboardPage from './pages/DashboardPage'
import ComponentsPage from './pages/ComponentsPage'
import PlanPage from './pages/PlanPage'

const NAV_STYLE: React.CSSProperties = {
  display: 'flex', gap: 8, padding: '12px 20px',
  borderBottom: '1px solid #1e293b', background: '#0d1117',
  alignItems: 'center',
}

const LOGO_STYLE: React.CSSProperties = {
  fontWeight: 700, fontSize: 16, color: '#6366f1',
  marginRight: 24, letterSpacing: '-0.5px',
}

export default function App() {
  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <nav style={NAV_STYLE}>
        <span style={LOGO_STYLE}>ArchMap</span>
        {(['/', '/components', '/plan'] as const).map((path, i) => (
          <NavLink
            key={path}
            to={path}
            end={path === '/'}
            style={({ isActive }) => ({
              padding: '6px 14px', borderRadius: 6, fontSize: 13,
              textDecoration: 'none', fontWeight: 500,
              background: isActive ? '#1e293b' : 'transparent',
              color: isActive ? '#e2e8f0' : '#64748b',
            })}
          >
            {['Dashboard', 'Architecture', 'Plan'][i]}
          </NavLink>
        ))}
      </nav>
      <main style={{ flex: 1, padding: 24 }}>
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/components" element={<ComponentsPage />} />
          <Route path="/plan" element={<PlanPage />} />
        </Routes>
      </main>
    </div>
  )
}
