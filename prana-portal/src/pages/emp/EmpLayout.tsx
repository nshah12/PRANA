/**
 * Employee portal shell — sidebar nav + topbar.
 * Separate from the employer PortalLayout in App.tsx.
 * Nav matches PRANA_Portal_v52.html employee role spec.
 */
import { NavLink, useNavigate, Outlet } from 'react-router-dom'
import { FolderOpen, TrendingUp, Heart, Share2, ClipboardList, Scale, Eye, FileQuestion, Settings, LogOut, ShieldCheck } from 'lucide-react'
import { useState } from 'react'
import { api } from '@/lib/api'
import { useEmpAuthStore } from '@/store/empAuth'

const NAV = [
  { to: '/emp/vault',        icon: FolderOpen,    label: 'My Vault',            color: '#0EA5E9', bg: 'rgba(14,165,233,0.15)' },
  { to: '/emp/career',       icon: TrendingUp,    label: 'Career Timeline',     color: '#10B981', bg: 'rgba(16,185,129,0.15)' },
  { to: '/emp/vault-health', icon: Heart,         label: 'Vault Health',        color: '#EF4444', bg: 'rgba(239,68,68,0.15)'  },
  { to: '/emp/shares',       icon: Share2,        label: 'Shared Documents',    color: '#8B5CF6', bg: 'rgba(139,92,246,0.15)' },
  { to: '/emp/activity',     icon: ClipboardList, label: 'Activity Log',        color: '#F59E0B', bg: 'rgba(245,158,11,0.15)' },
  { to: '/emp/data-rights',  icon: Scale,         label: 'DPDP Rights',         color: '#06B6D4', bg: 'rgba(6,182,212,0.15)'  },
  { to: '/emp/privacy',      icon: Eye,           label: 'Privacy Cockpit',     color: '#EC4899', bg: 'rgba(236,72,153,0.15)' },
  { to: '/emp/doc-request',  icon: FileQuestion,  label: 'Request Documents',   color: '#F97316', bg: 'rgba(249,115,22,0.15)' },
  { to: '/emp/settings',     icon: Settings,      label: 'Settings',            color: '#94A3B8', bg: 'rgba(148,163,184,0.15)'},
]

export function EmpLayout() {
  const navigate = useNavigate()
  const { user, logout } = useEmpAuthStore()
  const [signingOut, setSigningOut] = useState(false)

  async function handleLogout() {
    setSigningOut(true)
    try { await api.post('/auth/employee/logout') } catch { /* ignore */ }
    logout()
    navigate('/emp/login')
  }

  return (
    <div className="min-h-screen bg-slate-50 flex">
      {/* Sidebar */}
      <aside className="w-[220px] min-h-screen bg-slate-950 flex flex-col fixed left-0 top-0 z-40">
        {/* Brand */}
        <div className="flex items-center gap-2.5 px-5 pt-5 pb-4 border-b border-white/5">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-emerald-400 to-cyan-400 flex items-center justify-center flex-shrink-0">
            <ShieldCheck size={16} className="text-emerald-950" />
          </div>
          <div>
            <p className="text-white font-bold text-sm leading-none">PRANA</p>
            <p className="text-slate-500 text-[10px] mt-0.5">Employee vault</p>
          </div>
        </div>

        {/* Nav */}
        <nav className="flex-1 py-4 px-3 space-y-1">
          {NAV.map(({ to, icon: Icon, label, color, bg }) => (
            <NavLink key={to} to={to}>
              {({ isActive }) => (
                <div className={`flex items-center gap-2.5 px-2 py-2 rounded-lg text-sm transition-colors cursor-pointer ${
                  isActive ? 'bg-white/8' : 'hover:bg-white/5'
                }`}>
                  <div className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 transition-colors"
                    style={{ background: isActive ? bg : 'rgba(255,255,255,0.05)' }}>
                    <Icon size={14} style={{ color: isActive ? color : '#64748b' }} />
                  </div>
                  <span style={{ color: isActive ? '#f1f5f9' : '#94a3b8' }}
                    className={isActive ? 'font-medium' : ''}>
                    {label}
                  </span>
                </div>
              )}
            </NavLink>
          ))}
        </nav>

        {/* User + logout */}
        <div className="px-3 pb-5 border-t border-white/5 pt-4">
          <div className="flex items-center gap-2.5 px-3 py-2 rounded-lg bg-white/5">
            <div className="w-7 h-7 rounded-full bg-gradient-to-br from-emerald-400 to-cyan-400 flex items-center justify-center flex-shrink-0">
              <span className="text-emerald-950 text-xs font-bold">{user?.name?.charAt(0) ?? 'E'}</span>
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-white text-xs font-medium truncate">{user?.name ?? 'Employee'}</p>
              <p className="text-slate-500 text-[10px] truncate">{user?.mobile}</p>
            </div>
          </div>
          <button onClick={handleLogout} disabled={signingOut}
            className="mt-2 w-full flex items-center gap-2 px-3 py-2 rounded-lg text-slate-400 hover:text-red-400 hover:bg-red-500/5 text-xs transition-colors">
            <LogOut size={13} />
            Sign out
          </button>
        </div>
      </aside>

      {/* Main */}
      <main className="ml-[220px] flex-1 min-h-screen">
        <Outlet />
      </main>
    </div>
  )
}
