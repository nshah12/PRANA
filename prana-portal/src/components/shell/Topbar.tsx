import { useState, useRef, useEffect } from 'react'
import { Bell, Settings, User, LogOut, ChevronDown, Building2 } from 'lucide-react'
import { useAuthStore, ROLE_COLOR, ROLE_LABEL, type UserRole } from '@/store/auth'
import { api } from '@/lib/api'
import { useNavigate } from 'react-router-dom'

// Role-specific profile menu items
const ROLE_MENU: Record<string, { icon: React.ReactNode; label: string; path: string }[]> = {
  oa_operator: [
    { icon: <User size={13} />,     label: 'My profile',     path: '/org/profile' },
    { icon: <Settings size={13} />, label: 'Org settings',   path: '/org/settings' },
  ],
  oa_admin: [
    { icon: <User size={13} />,     label: 'Org profile',    path: '/org/profile' },
    { icon: <Settings size={13} />, label: 'Org settings',   path: '/org/settings' },
    { icon: <Building2 size={13} />,label: 'User management',path: '/org/users' },
  ],
  chro: [
    { icon: <User size={13} />,     label: 'My profile',     path: '/org/profile' },
    { icon: <Settings size={13} />, label: 'Alert config',   path: '/org/alerts' },
  ],
  cfo: [
    { icon: <User size={13} />,     label: 'My profile',     path: '/org/profile' },
    { icon: <Settings size={13} />, label: 'Org settings',   path: '/org/settings' },
  ],
  ciso: [
    { icon: <User size={13} />,     label: 'My profile',     path: '/org/profile' },
    { icon: <Settings size={13} />, label: 'Security config',path: '/org/settings' },
  ],
  portal_admin: [
    { icon: <Settings size={13} />, label: 'Platform config',path: '/admin/platform' },
    { icon: <Building2 size={13} />,label: 'Tenant directory',path: '/admin/tenants' },
  ],
}

export function Topbar() {
  const { user, logout } = useAuthStore()
  const navigate = useNavigate()
  const [menuOpen, setMenuOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handler(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  async function handleLogout() {
    const isPA = user?.role === 'portal_admin'
    try {
      await api.post(isPA ? '/auth/admin/logout' : '/auth/org/logout')
    } catch { /* ignore */ }
    logout()
    navigate(isPA ? '/admin/login' : '/org/login')
    setMenuOpen(false)
  }

  if (!user) return null
  const color  = ROLE_COLOR[user.role as UserRole]
  const label  = ROLE_LABEL[user.role as UserRole]
  const menuItems = ROLE_MENU[user.role] ?? []
  const initials = user.displayName
    ? user.displayName.split(' ').map((w: string) => w[0]).slice(0, 2).join('').toUpperCase()
    : '?'

  return (
    <header className="fixed top-0 left-0 right-0 h-[52px] bg-shell border-b border-white/10 z-50
                       flex items-center justify-between px-5">
      {/* Brand */}
      <span className="font-mono text-lg font-semibold text-white tracking-tight">
        prana.<span className="text-sky-400">in</span>
      </span>

      {/* Right side */}
      <div className="flex items-center gap-3">

        {/* Notification bell */}
        <button className="text-slate-400 hover:text-white transition-colors relative p-1.5 rounded-lg hover:bg-white/5">
          <Bell size={16} />
        </button>

        {/* Profile chip + dropdown */}
        <div className="relative" ref={menuRef}>
          <button
            onClick={() => setMenuOpen(o => !o)}
            className="flex items-center gap-2 rounded-xl px-2.5 py-1.5 hover:bg-white/5 transition-colors">
            {/* Avatar */}
            <div className="w-7 h-7 rounded-lg flex items-center justify-center text-white text-[10px] font-bold flex-shrink-0"
              style={{ backgroundColor: color }}>
              {initials}
            </div>
            {/* Name + role — visible on medium+ */}
            <div className="hidden md:block text-left">
              <p className="text-white text-xs font-medium leading-tight truncate max-w-[120px]">{user.displayName}</p>
              <p className="text-slate-400 text-[10px] leading-tight">{label}</p>
            </div>
            <ChevronDown size={12}
              className={`text-slate-400 transition-transform hidden md:block ${menuOpen ? 'rotate-180' : ''}`} />
          </button>

          {menuOpen && (
            <div className="absolute right-0 mt-2 w-64 bg-white border border-slate-200 rounded-2xl
                            shadow-2xl py-2 overflow-hidden z-50">

              {/* User info header */}
              <div className="px-4 py-3 border-b border-slate-100">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl flex items-center justify-center text-white text-sm font-bold flex-shrink-0"
                    style={{ backgroundColor: color }}>
                    {initials}
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-slate-800 truncate">{user.displayName}</p>
                    <p className="text-xs text-slate-400 truncate">{user.email || user.tenantName}</p>
                    <span className="inline-flex items-center mt-0.5 px-2 py-0.5 rounded-full text-[10px] font-bold text-white"
                      style={{ backgroundColor: color }}>
                      {label}
                    </span>
                  </div>
                </div>
              </div>

              {/* Role-specific menu items */}
              {menuItems.length > 0 && (
                <div className="py-1 border-b border-slate-100">
                  {menuItems.map(item => (
                    <button
                      key={item.path}
                      onClick={() => { navigate(item.path); setMenuOpen(false) }}
                      className="w-full flex items-center gap-3 px-4 py-2.5 text-left
                                 hover:bg-slate-50 transition-colors">
                      <span className="text-slate-400">{item.icon}</span>
                      <span className="text-sm text-slate-700">{item.label}</span>
                    </button>
                  ))}
                </div>
              )}

              {/* Tenant info if available */}
              {user.tenantName && (
                <div className="px-4 py-2.5 border-b border-slate-100">
                  <p className="text-[10px] text-slate-400 uppercase tracking-wider font-semibold mb-0.5">Organisation</p>
                  <p className="text-xs text-slate-600 font-medium truncate">{user.tenantName}</p>
                </div>
              )}

              {/* Logout */}
              <div className="py-1">
                <button
                  onClick={handleLogout}
                  className="w-full flex items-center gap-3 px-4 py-2.5 text-left
                             hover:bg-red-50 transition-colors group">
                  <LogOut size={13} className="text-slate-400 group-hover:text-red-500 transition-colors" />
                  <span className="text-sm text-slate-700 group-hover:text-red-600 font-medium transition-colors">
                    Sign out
                  </span>
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </header>
  )
}
