/**
 * Employee portal shell — sidebar nav + mobile top bar.
 * Separate from the employer PortalLayout in App.tsx.
 * Nav matches PRANA_Portal_v52.html employee role spec.
 *
 * Responsive strategy:
 *   mobile (<lg): fixed top bar (56px) + slide-over drawer + backdrop
 *   desktop (lg+): persistent fixed sidebar, no top bar
 */
import { NavLink, useNavigate, useLocation, Outlet } from 'react-router-dom'
import { FolderOpen, TrendingUp, Heart, Share2, ClipboardList, Scale, Eye, FileQuestion, Settings, LogOut, ShieldCheck, Menu, X } from 'lucide-react'
import { useState, useEffect } from 'react'
import { api } from '@/lib/api'
import { useEmpAuthStore } from '@/store/empAuth'

const NAV = [
  { to: '/emp/vault',        icon: FolderOpen,    label: 'My Vault',          color: '#0EA5E9', bg: 'rgba(14,165,233,0.15)' },
  { to: '/emp/career',       icon: TrendingUp,    label: 'Career Timeline',   color: '#10B981', bg: 'rgba(16,185,129,0.15)' },
  { to: '/emp/vault-health', icon: Heart,         label: 'Vault Health',      color: '#EF4444', bg: 'rgba(239,68,68,0.15)'  },
  { to: '/emp/shares',       icon: Share2,        label: 'Shared Documents',  color: '#8B5CF6', bg: 'rgba(139,92,246,0.15)' },
  { to: '/emp/activity',     icon: ClipboardList, label: 'Activity Log',      color: '#F59E0B', bg: 'rgba(245,158,11,0.15)' },
  { to: '/emp/data-rights',  icon: Scale,         label: 'DPDP Rights',       color: '#06B6D4', bg: 'rgba(6,182,212,0.15)'  },
  { to: '/emp/privacy',      icon: Eye,           label: 'Privacy Cockpit',   color: '#EC4899', bg: 'rgba(236,72,153,0.15)' },
  { to: '/emp/doc-request',  icon: FileQuestion,  label: 'Request Documents', color: '#F97316', bg: 'rgba(249,115,22,0.15)' },
  { to: '/emp/settings',     icon: Settings,      label: 'Settings',          color: '#94A3B8', bg: 'rgba(148,163,184,0.15)'},
]

export function EmpLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const { user, logout } = useEmpAuthStore()
  const [signingOut, setSigningOut] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)

  // Close drawer on route change (nav tap resolved)
  useEffect(() => {
    setDrawerOpen(false)
  }, [location.pathname])

  // Prevent body scroll while drawer is open on mobile
  useEffect(() => {
    document.body.style.overflow = drawerOpen ? 'hidden' : ''
    return () => { document.body.style.overflow = '' }
  }, [drawerOpen])

  async function handleLogout() {
    setSigningOut(true)
    try { await api.post('/auth/employee/logout') } catch { /* ignore */ }
    logout()
    navigate('/emp/login')
  }

  return (
    <div className="min-h-screen bg-slate-50 flex">

      {/* ── Mobile top bar (hidden on lg+) ──────────────────────────────── */}
      <header className="lg:hidden fixed top-0 left-0 right-0 z-50 h-14 bg-slate-950 flex items-center justify-between px-4 border-b border-white/5">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-emerald-400 to-cyan-400 flex items-center justify-center flex-shrink-0">
            <ShieldCheck size={13} className="text-emerald-950" />
          </div>
          <span className="text-white font-bold text-sm leading-none">
            PRANA <span className="text-slate-500 font-normal text-[10px]">vault</span>
          </span>
        </div>
        <button
          onClick={() => setDrawerOpen(o => !o)}
          aria-label={drawerOpen ? 'Close navigation' : 'Open navigation'}
          aria-expanded={drawerOpen}
          aria-controls="emp-sidebar"
          className="w-10 h-10 flex items-center justify-center rounded-lg text-slate-400 hover:text-white hover:bg-white/10 active:bg-white/15 transition-colors"
        >
          {drawerOpen ? <X size={18} /> : <Menu size={18} />}
        </button>
      </header>

      {/* ── Drawer backdrop (mobile only) ───────────────────────────────── */}
      <div
        aria-hidden="true"
        onClick={() => setDrawerOpen(false)}
        className={[
          'lg:hidden fixed inset-0 z-30 bg-slate-950/60 backdrop-blur-sm',
          'transition-opacity duration-200 motion-reduce:transition-none',
          drawerOpen ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none',
        ].join(' ')}
      />

      {/* ── Sidebar ──────────────────────────────────────────────────────── */}
      <aside
        id="emp-sidebar"
        className={[
          'w-[220px] min-h-screen bg-slate-950 flex flex-col fixed left-0 top-0 z-40',
          'transition-transform duration-200 ease-out motion-reduce:transition-none',
          drawerOpen ? 'translate-x-0' : '-translate-x-full',
          'lg:translate-x-0',
        ].join(' ')}
      >
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
        <nav className="flex-1 py-3 px-3 space-y-0.5 overflow-y-auto" aria-label="Employee navigation">
          {NAV.map(({ to, icon: Icon, label, color, bg }) => (
            <NavLink key={to} to={to}>
              {({ isActive }) => (
                <div className={`flex items-center gap-2.5 px-2 min-h-[44px] rounded-lg text-sm transition-colors cursor-pointer ${
                  isActive ? 'bg-white/8' : 'hover:bg-white/5'
                }`}>
                  <div
                    className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 transition-colors"
                    style={{ background: isActive ? bg : 'rgba(255,255,255,0.05)' }}
                  >
                    <Icon size={14} style={{ color: isActive ? color : '#64748b' }} />
                  </div>
                  <span
                    style={{ color: isActive ? '#f1f5f9' : '#94a3b8' }}
                    className={isActive ? 'font-medium' : ''}
                  >
                    {label}
                  </span>
                </div>
              )}
            </NavLink>
          ))}
        </nav>

        {/* User chip + logout */}
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
          <button
            onClick={handleLogout}
            disabled={signingOut}
            className="mt-2 w-full flex items-center gap-2 px-3 min-h-[40px] rounded-lg text-slate-400 hover:text-red-400 hover:bg-red-500/5 text-xs transition-colors disabled:opacity-50"
          >
            <LogOut size={13} />
            Sign out
          </button>
        </div>
      </aside>

      {/* ── Page content ─────────────────────────────────────────────────── */}
      <main className="flex-1 min-h-screen lg:ml-[220px] pt-14 lg:pt-0">
        <Outlet />
      </main>

    </div>
  )
}
