import { NavLink } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { useAuthStore, ROLE_COLOR, type UserRole } from '@/store/auth'
import { tUi } from '@/i18n'
import {
  LayoutDashboard, Users, Upload, FileText, AlertTriangle,
  Settings, ShieldCheck, ShieldAlert, TrendingUp, BarChart3, Calendar,
  Lock, Unlock, Key, Activity, Globe, ChevronDown, ChevronRight,
  Building2, Zap, FileSearch, Bell, ClipboardList, MessageSquare, Handshake, Plug, KeyRound, GitMerge,
  FileStack, CheckSquare,
} from 'lucide-react'
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'

interface BadgeCounts {
  exceptions?: number
  elevations?: number
  onboarding?: number
  storage?: number
  pipeline?: number
  compliance?: number
  securityAlerts?: number
  anomalies?: number
  incidents?: number   // P1 open service incidents (PA only)
}

interface NavItem {
  label: string
  to: string
  icon: React.ReactNode
  badge?: { count: number; color: 'red' | 'amber' | 'sky' }
}

interface NavGroup {
  label?: string
  items: NavItem[]
  collapsible?: boolean
}

function navForRole(role: UserRole, base: string, counts: BadgeCounts = {}): NavGroup[] {
  switch (role) {
    case 'oa_operator':
      return [{
        items: [
          { label: tUi('NAV_DASHBOARD'),         to: `${base}/dashboard`,         icon: <LayoutDashboard size={16}/> },
          { label: tUi('NAV_EMPLOYEE_MASTER'),   to: `${base}/employees`,         icon: <Users size={16}/> },
          { label: tUi('NAV_UPLOAD_DOCUMENTS'),  to: `${base}/upload`,            icon: <Upload size={16}/> },
          { label: tUi('NAV_SETUP_CHECKLIST'),   to: `${base}/setup-checklist`,   icon: <CheckSquare size={16}/> },
          { label: tUi('NAV_STORAGE'),           to: `${base}/storage`,           icon: <Globe size={16}/> },
          { label: tUi('NAV_REQUEST_ELEVATION'), to: `${base}/elevation`,         icon: <ShieldCheck size={16}/> },
        ],
      }]

    case 'oa_admin':
      return [{
        items: [
          { label: tUi('NAV_DASHBOARD'),          to: `${base}/dashboard`,       icon: <LayoutDashboard size={16}/> },
          { label: tUi('NAV_EMPLOYEE_MASTER'),    to: `${base}/employees`,       icon: <Users size={16}/> },
          { label: tUi('NAV_UPLOAD_DOCUMENTS'),   to: `${base}/upload`,          icon: <Upload size={16}/> },
          { label: tUi('NAV_DOCUMENT_VIEWER'),    to: `${base}/documents`,       icon: <FileText size={16}/> },
          { label: tUi('NAV_EXCEPTION_QUEUE'),    to: `${base}/exceptions`,      icon: <AlertTriangle size={16}/>, ...(counts.exceptions ? { badge: { count: counts.exceptions, color: 'red' as const } } : {}) },
          { label: tUi('NAV_USER_MANAGEMENT'),    to: `${base}/users`,           icon: <Users size={16}/> },
          { label: tUi('NAV_ELEVATION_APPROVALS'),to: `${base}/elevations`,      icon: <ShieldCheck size={16}/>, ...(counts.elevations ? { badge: { count: counts.elevations, color: 'amber' as const } } : {}) },
          { label: tUi('NAV_ORG_SETTINGS'),       to: `${base}/settings`,        icon: <Settings size={16}/> },
          { label: tUi('NAV_DOCUMENT_FIELDS'),    to: `${base}/document-fields`, icon: <FileStack size={16}/> },
          { label: tUi('NAV_SETUP_CHECKLIST'),    to: `${base}/setup-checklist`, icon: <CheckSquare size={16}/> },
          { label: tUi('NAV_HRMS_INTEGRATION'),   to: `${base}/hrms`,            icon: <Plug size={16}/> },
          { label: tUi('NAV_RESET_TOTP'),         to: `${base}/reset-totp`,      icon: <Lock size={16}/> },
          { label: tUi('NAV_RESET_PASSWORD'),     to: `${base}/reset-password`,  icon: <KeyRound size={16}/> },
        ],
      }]

    case 'chro':
      return [{
        items: [
          { label: tUi('NAV_VAULT_HEALTH'),        to: `${base}/vault-health`,    icon: <BarChart3 size={16}/> },
          { label: tUi('NAV_COMPLIANCE_CALENDAR'), to: `${base}/compliance`,      icon: <Calendar size={16}/>, ...(counts.compliance ? { badge: { count: counts.compliance, color: 'amber' as const } } : {}) },
          { label: tUi('NAV_COMPLIANCE_EXPORT'),   to: `${base}/export`,          icon: <FileSearch size={16}/> },
          { label: tUi('NAV_WEEKLY_DIGEST'),       to: `${base}/weekly`,          icon: <Bell size={16}/> },
          { label: tUi('NAV_MONTHLY_SUMMARY'),     to: `${base}/monthly`,         icon: <ClipboardList size={16}/> },
          { label: tUi('NAV_QUARTERLY_REPORT'),    to: `${base}/quarterly`,       icon: <TrendingUp size={16}/> },
          { label: tUi('NAV_ALUMNI_NETWORK'),      to: '/org/alumni',             icon: <Handshake size={16}/> },
          { label: tUi('NAV_COMP_BENCHMARKING'),   to: '/org/comp-benchmarking',  icon: <TrendingUp size={16}/> },
          { label: tUi('NAV_ALERT_CONFIG'),        to: `${base}/alerts`,          icon: <Settings size={16}/> },
          { label: tUi('NAV_DIGEST_SETTINGS'),     to: `${base}/digest-settings`, icon: <Bell size={16}/> },
        ],
      }]

    case 'cfo':
      return [{
        items: [
          { label: tUi('NAV_DASHBOARD'),           to: `${base}/dashboard`,       icon: <LayoutDashboard size={16}/> },
          { label: tUi('NAV_PAYROLL_INTELLIGENCE'), to: `${base}/payroll`,        icon: <BarChart3 size={16}/> },
          { label: tUi('NAV_ATTRITION_COST'),      to: `${base}/attrition`,       icon: <TrendingUp size={16}/> },
          { label: tUi('NAV_COMPLIANCE_POSTURE'),  to: `${base}/compliance`,      icon: <ShieldCheck size={16}/> },
          { label: tUi('NAV_BENCHMARKING'),        to: `${base}/benchmarking`,    icon: <BarChart3 size={16}/> },
          { label: tUi('NAV_ANOMALY_ALERTS'),      to: `${base}/anomalies`,       icon: <AlertTriangle size={16}/>, ...(counts.anomalies ? { badge: { count: counts.anomalies, color: 'red' as const } } : {}) },
          { label: tUi('NAV_CONSENT_DASHBOARD'),   to: `${base}/consent`,         icon: <Lock size={16}/> },
          { label: tUi('NAV_CFO_DIGEST'),          to: `${base}/cfo-digest`,      icon: <ClipboardList size={16}/> },
          { label: tUi('NAV_DIGEST_SETTINGS'),     to: `${base}/digest-settings`, icon: <Settings size={16}/> },
        ],
      }]

    case 'ciso':
      return [{
        items: [
          { label: tUi('NAV_SECURITY_OVERVIEW'),  to: `${base}/overview`,        icon: <ShieldCheck size={16}/>, ...(counts.securityAlerts ? { badge: { count: counts.securityAlerts, color: 'red' as const } } : {}) },
          { label: tUi('NAV_OA_ACTIVITY_AUDIT'),  to: `${base}/oa-audit`,        icon: <Activity size={16}/> },
          { label: tUi('NAV_SHARE_ANALYTICS'),    to: `${base}/shares`,          icon: <FileText size={16}/> },
          { label: tUi('NAV_KEY_HEALTH'),         to: `${base}/keys`,            icon: <Key size={16}/> },
          { label: tUi('NAV_AUTH_ANOMALY_FEED'),  to: `${base}/auth-anomalies`,  icon: <AlertTriangle size={16}/> },
          { label: tUi('NAV_DATA_RESIDENCY'),     to: `${base}/residency`,       icon: <Globe size={16}/> },
          { label: tUi('NAV_INFOSEC_DIGEST'),     to: `${base}/ciso-digest`,     icon: <ClipboardList size={16}/> },
          { label: tUi('NAV_SECURITY_INCIDENTS'), to: `${base}/ciso-incidents`,  icon: <ShieldAlert size={16}/>, ...(counts.securityAlerts ? { badge: { count: counts.securityAlerts, color: 'red' as const } } : {}) },
          { label: tUi('NAV_NOTIFICATION_LOG'),   to: `${base}/ciso-notif-log`,  icon: <Bell size={16}/> },
          { label: tUi('NAV_DIGEST_SETTINGS'),    to: `${base}/digest-settings`, icon: <Settings size={16}/> },
        ],
      }]

    case 'portal_admin':
      return [
        {
          label: tUi('NAV_GROUP_OVERVIEW'),
          items: [
            { label: tUi('NAV_META_DASHBOARD'),  to: `${base}/dashboard`,       icon: <LayoutDashboard size={16}/> },
          ],
        },
        {
          label: tUi('NAV_GROUP_TENANT_MANAGEMENT'),
          collapsible: true,
          items: [
            { label: tUi('NAV_ONBOARDING_QUEUE'), to: `${base}/onboarding`,     icon: <Building2 size={16}/>, ...(counts.onboarding ? { badge: { count: counts.onboarding, color: 'amber' as const } } : {}) },
            { label: tUi('NAV_TENANT_DIRECTORY'), to: `${base}/tenants`,        icon: <Users size={16}/> },
            { label: tUi('NAV_OA_EMERGENCY'),     to: `${base}/oa-override`,    icon: <Zap size={16}/> },
            { label: tUi('NAV_PA_RESET_TOTP'),    to: `${base}/reset-totp`,     icon: <Lock size={16}/> },
            { label: tUi('NAV_PA_UNLOCK'),         to: `${base}/pa-unlock`,      icon: <Unlock size={16}/> },
            { label: tUi('NAV_PA_RESET_PASSWORD'), to: `${base}/reset-password`, icon: <KeyRound size={16}/> },
            { label: tUi('NAV_PA_EMPLOYEE_MERGE'), to: `${base}/employee-merge`, icon: <GitMerge size={16}/> },
            { label: tUi('NAV_SETUP_CHECKLIST'),  to: `${base}/setup-checklist`, icon: <CheckSquare size={16}/> },
            { label: tUi('NAV_STORAGE_REQUESTS'), to: `${base}/storage`,        icon: <Globe size={16}/>, ...(counts.storage ? { badge: { count: counts.storage, color: 'amber' as const } } : {}) },
            { label: tUi('NAV_ANNOUNCEMENTS'),    to: `${base}/announcements`,  icon: <Bell size={16}/> },
            { label: tUi('NAV_INQUIRIES'),        to: `${base}/inquiries`,      icon: <MessageSquare size={16}/> },
          ],
        },
        {
          label: tUi('NAV_GROUP_PLATFORM_OPS'),
          collapsible: true,
          items: [
            { label: tUi('NAV_PIPELINE_HEALTH'),    to: `${base}/pipeline`,     icon: <Activity size={16}/>, ...(counts.pipeline ? { badge: { count: counts.pipeline, color: 'red' as const } } : {}) },
            { label: tUi('NAV_EXCEPTION_OVERVIEW'), to: `${base}/exceptions`,   icon: <AlertTriangle size={16}/>, ...(counts.exceptions ? { badge: { count: counts.exceptions, color: 'red' as const } } : {}) },
            { label: tUi('NAV_API_KEYS'),           to: `${base}/api-keys`,     icon: <Key size={16}/> },
            { label: tUi('NAV_HRMS_CONNECTORS'),    to: `${base}/hrms`,         icon: <Plug size={16}/> },
            { label: tUi('NAV_RATE_LIMITS'),        to: `${base}/rate-limits`,  icon: <BarChart3 size={16}/> },
          ],
        },
        {
          label: tUi('NAV_GROUP_SECURITY_COMPLIANCE'),
          collapsible: true,
          items: [
            { label: tUi('NAV_SECOPS_DASHBOARD'),    to: `${base}/secops`,              icon: <ShieldCheck size={16}/> },
            { label: tUi('NAV_ANOMALY_DETECTION'),   to: `${base}/anomalies`,           icon: <AlertTriangle size={16}/>, ...(counts.anomalies ? { badge: { count: counts.anomalies, color: 'amber' as const } } : {}) },
            { label: tUi('NAV_INCIDENT_REGISTER'),   to: `${base}/incidents`,           icon: <ClipboardList size={16}/>, ...(counts.incidents ? { badge: { count: counts.incidents, color: 'red' as const } } : {}) },
            { label: tUi('NAV_SECURITY_INCIDENTS'),  to: `${base}/security-incidents`,  icon: <ShieldAlert size={16}/> },
            { label: tUi('NAV_INCIDENT_POLICY'),     to: `${base}/incident-policy`,     icon: <Settings size={16}/> },
            { label: tUi('NAV_DOCUMENT_FIELDS'),     to: `${base}/document-fields`,     icon: <FileStack size={16}/> },
            { label: tUi('NAV_NOTIFICATION_LOG'),    to: `${base}/notifications`,       icon: <Bell size={16}/> },
            { label: tUi('NAV_CRYPTOGRAPHIC_HEALTH'),to: `${base}/crypto`,              icon: <Key size={16}/> },
            { label: tUi('NAV_AUDIT_TRAIL'),         to: `${base}/audit`,               icon: <FileSearch size={16}/> },
          ],
        },
      ]

    default:
      return []
  }
}

function BadgePill({ count, color }: { count: number; color: 'red' | 'amber' | 'sky' }) {
  const cls = { red: 'bg-red-500', amber: 'bg-amber-500', sky: 'bg-sky-500' }[color]
  return (
    <span className={`ml-auto px-1.5 py-0.5 rounded-full text-[10px] font-mono text-white font-bold ${cls}`}>
      {count}
    </span>
  )
}

function NavGroup({ group, accentColor }: { group: NavGroup; accentColor: string }) {
  const [open, setOpen] = useState(true)

  return (
    <div className="mb-1">
      {group.label && (
        <button
          onClick={() => group.collapsible && setOpen(o => !o)}
          className="flex items-center w-full px-4 py-1.5 text-[9px] font-mono font-semibold
                     text-amber-500 uppercase tracking-widest gap-1"
        >
          {group.label}
          {group.collapsible && (
            open ? <ChevronDown size={10}/> : <ChevronRight size={10}/>
          )}
        </button>
      )}
      {(!group.collapsible || open) && (
        <div className="space-y-0.5">
          {group.items.map(item => (
            <NavLink key={item.to} to={item.to} end>
              {({ isActive }) => (
                <div
                  className={cn(
                    'nav-item',
                    isActive && 'active'
                  )}
                  style={isActive ? { borderLeftColor: accentColor } : undefined}
                >
                  <span style={{ color: isActive ? accentColor : undefined }}>{item.icon}</span>
                  <span className="flex-1 text-sm">{item.label}</span>
                  {item.badge && <BadgePill {...item.badge} />}
                </div>
              )}
            </NavLink>
          ))}
        </div>
      )}
    </div>
  )
}

export function Sidebar() {
  const { user } = useAuthStore()

  const { data: badgeData, isLoading: badgesLoading } = useQuery({
    queryKey: ['sidebar-badges', user?.role],
    queryFn: async () => {
      if (!user) return {}
      if (user.role === 'portal_admin') {
        const [meta, inc] = await Promise.all([
          api.get('/admin/meta-dashboard').then(r => r.data).catch(() => ({})),
          api.get('/admin/incidents').then(r => r.data).catch(() => ({ p1_open: 0 })),
        ])
        return {
          exceptions: meta.open_exceptions || 0,
          onboarding: 0,
          storage: 0,
          pipeline: Object.values(meta.pipeline_counts ?? {}).reduce((a: number, v: any) => a + Number(v), 0),
          incidents: inc.p1_open || 0,
        } as BadgeCounts
      }
      if (user.role === 'oa_admin') {
        const [exc, elev] = await Promise.all([
          api.get('/v1/org/exceptions/count').then(r => r.data.count).catch(() => 0),
          api.get('/v1/org/elevations/pending-count').then(r => r.data.count).catch(() => 0),
        ])
        return { exceptions: exc, elevations: elev } as BadgeCounts
      }
      return {} as BadgeCounts
    },
    enabled: !!user,
    refetchInterval: 60_000,
    staleTime: 30_000,
  })

  if (!user) return null

  const role = user.role as UserRole
  const isPA = role === 'portal_admin'
  const base = isPA ? '/admin' : '/org'
  const groups = navForRole(role, base, badgesLoading ? {} : (badgeData ?? {}))
  const accentColor = ROLE_COLOR[role]

  return (
    <aside className="fixed top-[52px] left-0 bottom-0 w-[220px] bg-shell
                      border-r border-white/10 overflow-y-auto z-40 py-4">
      {/* Tenant name */}
      {user.tenantName && (
        <div className="px-4 mb-4">
          <p className="text-[10px] font-mono text-slate-500 uppercase tracking-widest">{tUi('SIDEBAR_ORG_LABEL')}</p>
          <p className="text-sm text-white font-medium mt-0.5 truncate">{user.tenantName}</p>
        </div>
      )}

      {groups.map((group, i) => (
        <NavGroup key={i} group={group} accentColor={accentColor} />
      ))}
    </aside>
  )
}
