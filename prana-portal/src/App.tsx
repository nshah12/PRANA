import { useState, useEffect } from 'react'
import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuthStore } from '@/store/auth'
import { Topbar } from '@/components/shell/Topbar'
import { Sidebar } from '@/components/shell/Sidebar'
import { ElevationBanner } from '@/components/shell/ElevationBanner'
import { SetupChecklistBanner } from '@/components/shell/SetupChecklistBanner'
import { api } from '@/lib/api'

// Public pages
import { Landing }     from '@/pages/Landing'
import { OrgRegister } from '@/pages/OrgRegister'

// Legal pages
import { PrivacyPolicy } from '@/pages/legal/PrivacyPolicy'
import { TermsOfUse }    from '@/pages/legal/TermsOfUse'
import { DPA }           from '@/pages/legal/DPA'
import { CookiePolicy }  from '@/pages/legal/CookiePolicy'
import { Grievance }     from '@/pages/legal/Grievance'
import { ApiTerms }      from '@/pages/legal/ApiTerms'

// Auth pages
import { OrgLogin }    from '@/pages/auth/OrgLogin'
import { OrgTotp }     from '@/pages/auth/OrgTotp'
import { ResetPassword } from '@/pages/auth/ResetPassword'
import { AdminLogin }  from '@/pages/auth/AdminLogin'
import { AdminTotp }   from '@/pages/auth/AdminTotp'

// OA-Operator / OA-Admin pages
import { Dashboard }       from '@/pages/oa/Dashboard'
import { EmployeeMaster }  from '@/pages/oa/EmployeeMaster'
import { UploadDocuments } from '@/pages/oa/UploadDocuments'
import { DocumentViewer }  from '@/pages/oa/DocumentViewer'
import { ExceptionQueue }  from '@/pages/oa/ExceptionQueue'
import { UserManagement }  from '@/pages/oa/UserManagement'
import { ElevationPage }   from '@/pages/oa/ElevationPage'
import { OrgSettings }     from '@/pages/oa/OrgSettings'
import { DocumentFields }  from '@/pages/oa/DocumentFields'
import { SetupChecklist }  from '@/pages/oa/SetupChecklist'
import { OrgProfile }      from '@/pages/oa/OrgProfile'
import { ResetTotp }       from '@/pages/oa/ResetTotp'
import { EmployeePasswordReset as OaEmployeePasswordReset } from '@/pages/oa/EmployeePasswordReset'

// CHRO pages
import { VaultHealthChro }      from '@/pages/chro/VaultHealthChro'
import { ComplianceCalendar }   from '@/pages/chro/ComplianceCalendar'
import { ComplianceExport }     from '@/pages/chro/ComplianceExport'
import { WeeklyDigest }         from '@/pages/chro/WeeklyDigest'
import { MonthlySummary }       from '@/pages/chro/MonthlySummary'
import { QuarterlyReport }      from '@/pages/chro/QuarterlyReport'
import { AlertConfig }          from '@/pages/chro/AlertConfig'
import { StatutoryCompliance }  from '@/pages/chro/StatutoryCompliance'
import { AlumniNetwork }        from '@/pages/chro/AlumniNetwork'
import { CompBenchmarking }     from '@/pages/chro/CompBenchmarking'

// CFO pages
import { PayrollIntelligence } from '@/pages/cfo/PayrollIntelligence'
import { AnomalyAlerts }       from '@/pages/cfo/AnomalyAlerts'
import { AttritionCost }     from '@/pages/cfo/AttritionCost'
import { Benchmarking }      from '@/pages/cfo/Benchmarking'
import { ConsentDashboard }  from '@/pages/cfo/ConsentDashboard'
import { CfoDigest }         from '@/pages/cfo/CfoDigest'
import { CompliancePosture } from '@/pages/chro/CompliancePosture'

// CISO pages
import { ShareAnalytics }    from '@/pages/ciso/ShareAnalytics'
import { KeyHealth }         from '@/pages/ciso/KeyHealth'
import { DataResidency }     from '@/pages/ciso/DataResidency'
import { AccessFlags }       from '@/pages/ciso/AccessFlags'
import { AccountLocks }      from '@/pages/ciso/AccountLocks'
import { AnomalyQueue }      from '@/pages/ciso/AnomalyQueue'
import { ElevationHistory }  from '@/pages/ciso/ElevationHistory'
import { CisoDigest }        from '@/pages/ciso/CisoDigest'
import { SecurityIncidents } from '@/pages/ciso/SecurityIncidents'
import { NotificationLog }   from '@/pages/ciso/NotificationLog'

// Shared pages
import { DigestSettings }    from '@/pages/DigestSettings'

// Portal Admin screens (formerly stubs)
import { ExceptionOverview } from '@/pages/pa/ExceptionOverview'
import { SecOpsDashboard }   from '@/pages/pa/SecOpsDashboard'
import { AnomalyDetection }  from '@/pages/pa/AnomalyDetection'
import { IncidentRegister }         from '@/pages/pa/IncidentRegister'
import { SecurityIncidentRegister } from '@/pages/pa/SecurityIncidentRegister'
import { IncidentPolicyConfig }     from '@/pages/pa/IncidentPolicyConfig'
import { CommunicationSettings as PaCommunicationSettings } from '@/pages/pa/CommunicationSettings'
import { PlatformCredentials }      from '@/pages/pa/PlatformCredentials'
import { PlatformDocumentFields }   from '@/pages/pa/PlatformDocumentFields'
import { SetupChecklistTemplate }   from '@/pages/pa/SetupChecklistTemplate'
import { PaNotificationLog }        from '@/pages/pa/PaNotificationLog'
import { CryptoHealth }             from '@/pages/pa/CryptoHealth'
import { ApiKeys }           from '@/pages/pa/ApiKeys'

// CISO pages
import { SecurityOverview }  from '@/pages/ciso/SecurityOverview'
import { OaActivityAudit }   from '@/pages/ciso/OaActivityAudit'
import { AuthAnomalyFeed }   from '@/pages/ciso/AuthAnomalyFeed'

// Portal Admin pages
// Employee self-service portal
import { EmpLogin }        from '@/pages/emp/EmpLogin'
import { EmpLayout }       from '@/pages/emp/EmpLayout'
import { EmpVault }        from '@/pages/emp/EmpVault'
import { EmpShares }       from '@/pages/emp/EmpShares'
import { EmpAsk }          from '@/pages/emp/EmpAsk'
import { EmpDataRights }   from '@/pages/emp/EmpDataRights'
import { EmpCareer }       from '@/pages/emp/EmpCareer'
import { EmpVaultHealth }  from '@/pages/emp/EmpVaultHealth'
import { EmpActivity }     from '@/pages/emp/EmpActivity'
import { EmpPrivacy }      from '@/pages/emp/EmpPrivacy'
import { EmpDocRequest }   from '@/pages/emp/EmpDocRequest'
import { EmpSettings }     from '@/pages/emp/EmpSettings'
import { useEmpAuthStore } from '@/store/empAuth'

import { MetaDashboard }     from '@/pages/pa/MetaDashboard'
import { OnboardingQueue }   from '@/pages/pa/OnboardingQueue'
import { TenantDirectory }      from '@/pages/pa/TenantDirectory'
import { TenantDetail }         from '@/pages/pa/TenantDetail'
import { CreateTenantWizard }  from '@/pages/pa/CreateTenantWizard'
import { OaEmergency }       from '@/pages/pa/OaEmergency'
import { EmployeeTotpReset } from '@/pages/pa/EmployeeTotpReset'
import { PaUnlock }          from '@/pages/pa/PaUnlock'
import { EmployeePasswordReset as PaEmployeePasswordReset } from '@/pages/pa/EmployeePasswordReset'
import { EmployeeMerge } from '@/pages/pa/EmployeeMerge'
import { StorageRequests }   from '@/pages/pa/StorageRequests'
import { PipelineHealth }    from '@/pages/pa/PipelineHealth'
import { AuditTrail }        from '@/pages/pa/AuditTrail'
import { RateLimits }        from '@/pages/pa/RateLimits'
import { Announcements }     from '@/pages/pa/Announcements'
import { ContactInquiries }  from '@/pages/pa/ContactInquiries'
import { HRMSCatalogue }    from '@/pages/pa/HRMSCatalogue'
import { HRMSSettings }     from '@/pages/oa/HRMSSettings'
import { CommunicationSettings as OaCommunicationSettings } from '@/pages/oa/CommunicationSettings'

// Zustand's `persist` middleware rehydrates from localStorage asynchronously —
// on first render after a page reload, `user` is still null even for an
// already-logged-in session. Without waiting for hydration, these guards would
// redirect to login on every single refresh before the persisted session had
// a chance to load. `store.persist.hasHydrated()` / `onFinishHydration()` let
// us hold the redirect until rehydration actually completes.
function useHasHydrated(store: { persist: { hasHydrated: () => boolean; onFinishHydration: (cb: () => void) => () => void } }) {
  const [hydrated, setHydrated] = useState(store.persist.hasHydrated())
  useEffect(() => {
    if (store.persist.hasHydrated()) { setHydrated(true); return }
    return store.persist.onFinishHydration(() => setHydrated(true))
  }, [store])
  return hydrated
}

function AuthBootstrapSpinner() {
  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="w-8 h-8 border-2 border-slate-200 border-t-sky-500 rounded-full animate-spin" />
    </div>
  )
}

export function RequireEmpAuth({ children }: { children: React.ReactNode }) {
  const user           = useEmpAuthStore(s => s.user)
  const accessToken    = useEmpAuthStore(s => s.accessToken)
  const setAccessToken = useEmpAuthStore(s => s.setAccessToken)
  const logout         = useEmpAuthStore(s => s.logout)
  const hydrated       = useHasHydrated(useEmpAuthStore)
  const location       = useLocation()

  // Access token lives in memory only (never persisted — CLAUDE.md), so it's
  // null on every fresh tab/reload even when `user` is a valid persisted
  // session. Resolve it proactively via the httpOnly refresh cookie BEFORE
  // rendering children, instead of letting every child query fire, 401, and
  // retry after a reactive refresh — same outcome, half the network calls,
  // and no false 401s in the browser console/network tab.
  const [bootstrapping, setBootstrapping] = useState(!accessToken && !!user)
  useEffect(() => {
    if (user && !accessToken) {
      api.post('/auth/employee/refresh', {}, { withCredentials: true })
        .then(({ data }) => setAccessToken(data.access_token))
        .catch(() => logout())
        .finally(() => setBootstrapping(false))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Must wait for the persisted `user` to rehydrate before deciding to
  // redirect — otherwise every refresh briefly sees user=null and bounces
  // to login before localStorage has a chance to load.
  if (!hydrated) return null
  if (!user && !accessToken) return <Navigate to="/emp/login" state={{ from: location }} replace />
  if (bootstrapping) return <AuthBootstrapSpinner />
  return <>{children}</>
}

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const user           = useAuthStore(s => s.user)
  const accessToken    = useAuthStore(s => s.accessToken)
  const setAccessToken = useAuthStore(s => s.setAccessToken)
  const logout         = useAuthStore(s => s.logout)
  const hydrated       = useHasHydrated(useAuthStore)
  const location       = useLocation()

  // Same proactive-bootstrap rationale as RequireEmpAuth above.
  const [bootstrapping, setBootstrapping] = useState(!accessToken && !!user)
  useEffect(() => {
    if (user && !accessToken) {
      const refreshPath = user.role === 'portal_admin' ? '/auth/admin/refresh' : '/auth/org/refresh'
      api.post(refreshPath, {}, { withCredentials: true })
        .then(({ data }) => setAccessToken(data.access_token))
        .catch(() => logout())
        .finally(() => setBootstrapping(false))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  if (!hydrated) return null
  if (!user) {
    const loginPage = location.pathname.startsWith('/admin') ? '/admin/login' : '/org/login'
    return <Navigate to={loginPage} replace />
  }
  if (bootstrapping) return <AuthBootstrapSpinner />
  return <>{children}</>
}

function PortalLayout({ children }: { children: React.ReactNode }) {
  const { user } = useAuthStore()
  const qc = useQueryClient()

  // Poll for active elevation — only for oa_operator (not admin, not other roles)
  // Errors caught in queryFn (returns null) — no blocking loading/error state needed for layout shell
  const { data: activeElevation, isLoading: elevationLoading } = useQuery<{ elevation_id: string; ends_at: string } | null>({
    queryKey: ['elevation-active'],
    queryFn:  () => api.get('/v1/org/elevations/active').then(r => r.data).catch(() => null),
    refetchInterval: 60_000,
    enabled: user?.role === 'oa_operator',
  })

  const endEarlyMutation = useMutation({
    mutationFn: (id: string) => api.post(`/v1/org/elevations/${id}/end-early`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['elevation-active'] }),
  })

  const hasElevation = !elevationLoading && !!activeElevation?.ends_at && new Date(activeElevation.ends_at) > new Date()

  // Go-Live Checklist gate — only relevant to the roles that actually upload
  // documents. Errors caught in queryFn (returns null) — same non-blocking
  // pattern as the elevation query above.
  const checklistEnabled = user?.role === 'oa_operator' || user?.role === 'oa_admin'
  const { data: checklistData } = useQuery({
    queryKey: ['setup-checklist-gate'],
    queryFn: () => api.get('/v1/org/setup-checklist').then(r => r.data).catch(() => null),
    refetchInterval: 60_000,
    enabled: checklistEnabled,
  })
  const missingRequiredCount = (checklistData?.items ?? []).filter(
    (i: any) => i.is_required && !i.completed,
  ).length
  const hasIncompleteChecklist = checklistEnabled && missingRequiredCount > 0

  const bannerCount = (hasElevation ? 1 : 0) + (hasIncompleteChecklist ? 1 : 0)

  return (
    <div className="min-h-screen bg-canvas">
      <Topbar />
      <Sidebar />
      {hasElevation && (
        <ElevationBanner
          endsAt={activeElevation!.ends_at}
          onEndEarly={() => endEarlyMutation.mutate(activeElevation!.elevation_id)}
        />
      )}
      {hasIncompleteChecklist && (
        <SetupChecklistBanner
          missingCount={missingRequiredCount}
          top={hasElevation ? 92 : 52}
        />
      )}
      <main className="ml-[220px] min-h-screen" style={{ paddingTop: 52 + bannerCount * 40 }}>
        <div className="p-6">{children}</div>
      </main>
    </div>
  )
}

export default function App() {
  return (
    <Routes>
      {/* Landing & public pages */}
      <Route path="/"           element={<Landing />} />
      <Route path="/register"   element={<OrgRegister />} />

      {/* Legal pages */}
      <Route path="/legal/privacy"   element={<PrivacyPolicy />} />
      <Route path="/legal/terms"     element={<TermsOfUse />} />
      <Route path="/legal/dpa"       element={<DPA />} />
      <Route path="/legal/cookies"   element={<CookiePolicy />} />
      <Route path="/legal/grievance" element={<Grievance />} />
      <Route path="/legal/api-terms" element={<ApiTerms />} />

      {/* Public auth routes */}
      <Route path="/org/login"        element={<OrgLogin />} />
      <Route path="/org/totp"         element={<OrgTotp />} />
      <Route path="/org/reset"        element={<ResetPassword />} />
      <Route path="/admin/login"      element={<AdminLogin />} />
      <Route path="/admin/totp"       element={<AdminTotp />} />

      {/* OA routes (oa_operator + oa_admin) */}
      <Route path="/org" element={<RequireAuth><PortalLayout><></></PortalLayout></RequireAuth>}>
        <Route index element={<Navigate to="/org/dashboard" replace />} />
      </Route>
      <Route path="/org/dashboard"  element={<RequireAuth><PortalLayout><Dashboard /></PortalLayout></RequireAuth>} />
      <Route path="/org/employees"  element={<RequireAuth><PortalLayout><EmployeeMaster /></PortalLayout></RequireAuth>} />
      <Route path="/org/upload"     element={<RequireAuth><PortalLayout><UploadDocuments /></PortalLayout></RequireAuth>} />
      <Route path="/org/documents"  element={<RequireAuth><PortalLayout><DocumentViewer /></PortalLayout></RequireAuth>} />
      <Route path="/org/exceptions" element={<RequireAuth><PortalLayout><ExceptionQueue /></PortalLayout></RequireAuth>} />
      <Route path="/org/users"      element={<RequireAuth><PortalLayout><UserManagement /></PortalLayout></RequireAuth>} />
      <Route path="/org/elevations" element={<RequireAuth><PortalLayout><ElevationPage /></PortalLayout></RequireAuth>} />
      <Route path="/org/elevation"  element={<RequireAuth><PortalLayout><ElevationPage /></PortalLayout></RequireAuth>} />
      <Route path="/org/settings"   element={<RequireAuth><PortalLayout><OrgSettings /></PortalLayout></RequireAuth>} />
      <Route path="/org/document-fields" element={<RequireAuth><PortalLayout><DocumentFields /></PortalLayout></RequireAuth>} />
      <Route path="/org/setup-checklist" element={<RequireAuth><PortalLayout><SetupChecklist /></PortalLayout></RequireAuth>} />
      <Route path="/org/reset-totp" element={<RequireAuth><PortalLayout><ResetTotp /></PortalLayout></RequireAuth>} />
      <Route path="/org/reset-password" element={<RequireAuth><PortalLayout><OaEmployeePasswordReset /></PortalLayout></RequireAuth>} />
      <Route path="/org/hrms"       element={<RequireAuth><PortalLayout><HRMSSettings /></PortalLayout></RequireAuth>} />
      <Route path="/org/communications" element={<RequireAuth><PortalLayout><OaCommunicationSettings /></PortalLayout></RequireAuth>} />
      <Route path="/org/profile"    element={<RequireAuth><PortalLayout><OrgProfile /></PortalLayout></RequireAuth>} />

      {/* CHRO routes */}
      <Route path="/org/vault-health" element={<RequireAuth><PortalLayout><VaultHealthChro /></PortalLayout></RequireAuth>} />
      <Route path="/org/compliance"   element={<RequireAuth><PortalLayout><ComplianceCalendar /></PortalLayout></RequireAuth>} />
      <Route path="/org/export"       element={<RequireAuth><PortalLayout><ComplianceExport /></PortalLayout></RequireAuth>} />
      <Route path="/org/weekly"       element={<RequireAuth><PortalLayout><WeeklyDigest /></PortalLayout></RequireAuth>} />
      <Route path="/org/monthly"      element={<RequireAuth><PortalLayout><MonthlySummary /></PortalLayout></RequireAuth>} />
      <Route path="/org/quarterly"    element={<RequireAuth><PortalLayout><QuarterlyReport /></PortalLayout></RequireAuth>} />
      <Route path="/org/alerts"           element={<RequireAuth><PortalLayout><AlertConfig /></PortalLayout></RequireAuth>} />
      <Route path="/org/statutory"         element={<RequireAuth><PortalLayout><StatutoryCompliance /></PortalLayout></RequireAuth>} />
      <Route path="/org/compliance-posture" element={<RequireAuth><PortalLayout><CompliancePosture /></PortalLayout></RequireAuth>} />
      <Route path="/org/alumni"            element={<RequireAuth><PortalLayout><AlumniNetwork /></PortalLayout></RequireAuth>} />
      <Route path="/org/comp-benchmarking" element={<RequireAuth><PortalLayout><CompBenchmarking /></PortalLayout></RequireAuth>} />

      {/* CFO routes */}
      <Route path="/org/payroll"      element={<RequireAuth><PortalLayout><PayrollIntelligence /></PortalLayout></RequireAuth>} />
      <Route path="/org/attrition"    element={<RequireAuth><PortalLayout><AttritionCost /></PortalLayout></RequireAuth>} />
      <Route path="/org/benchmarking" element={<RequireAuth><PortalLayout><Benchmarking /></PortalLayout></RequireAuth>} />
      <Route path="/org/anomalies"    element={<RequireAuth><PortalLayout><AnomalyAlerts /></PortalLayout></RequireAuth>} />
      <Route path="/org/consent"      element={<RequireAuth><PortalLayout><ConsentDashboard /></PortalLayout></RequireAuth>} />
      <Route path="/org/cfo-digest"   element={<RequireAuth><PortalLayout><CfoDigest /></PortalLayout></RequireAuth>} />

      {/* CISO routes */}
      <Route path="/org/overview"       element={<RequireAuth><PortalLayout><SecurityOverview /></PortalLayout></RequireAuth>} />
      <Route path="/org/oa-audit"       element={<RequireAuth><PortalLayout><OaActivityAudit /></PortalLayout></RequireAuth>} />
      <Route path="/org/shares"         element={<RequireAuth><PortalLayout><ShareAnalytics /></PortalLayout></RequireAuth>} />
      <Route path="/org/keys"           element={<RequireAuth><PortalLayout><KeyHealth /></PortalLayout></RequireAuth>} />
      <Route path="/org/auth-anomalies" element={<RequireAuth><PortalLayout><AuthAnomalyFeed /></PortalLayout></RequireAuth>} />
      <Route path="/org/residency"         element={<RequireAuth><PortalLayout><DataResidency /></PortalLayout></RequireAuth>} />
      <Route path="/org/access-flags"       element={<RequireAuth><PortalLayout><AccessFlags /></PortalLayout></RequireAuth>} />
      <Route path="/org/account-locks"      element={<RequireAuth><PortalLayout><AccountLocks /></PortalLayout></RequireAuth>} />
      <Route path="/org/anomaly-queue"      element={<RequireAuth><PortalLayout><AnomalyQueue /></PortalLayout></RequireAuth>} />
      <Route path="/org/elevation-history"  element={<RequireAuth><PortalLayout><ElevationHistory /></PortalLayout></RequireAuth>} />
      <Route path="/org/ciso-digest"        element={<RequireAuth><PortalLayout><CisoDigest /></PortalLayout></RequireAuth>} />
      <Route path="/org/ciso-incidents"    element={<RequireAuth><PortalLayout><SecurityIncidents /></PortalLayout></RequireAuth>} />
      <Route path="/org/ciso-notif-log"   element={<RequireAuth><PortalLayout><NotificationLog /></PortalLayout></RequireAuth>} />

      {/* Shared — digest settings (role-aware, works for CHRO / CFO / CISO) */}
      <Route path="/org/digest-settings" element={<RequireAuth><PortalLayout><DigestSettings /></PortalLayout></RequireAuth>} />

      {/* Portal Admin routes */}
      <Route path="/admin/dashboard"  element={<RequireAuth><PortalLayout><MetaDashboard /></PortalLayout></RequireAuth>} />
      <Route path="/admin/onboarding" element={<RequireAuth><PortalLayout><OnboardingQueue /></PortalLayout></RequireAuth>} />
      <Route path="/admin/tenants"     element={<RequireAuth><PortalLayout><TenantDirectory /></PortalLayout></RequireAuth>} />
      <Route path="/admin/tenants/new" element={<RequireAuth><PortalLayout><CreateTenantWizard /></PortalLayout></RequireAuth>} />
      <Route path="/admin/tenants/:id" element={<RequireAuth><PortalLayout><TenantDetail /></PortalLayout></RequireAuth>} />
      <Route path="/admin/oa-override"element={<RequireAuth><PortalLayout><OaEmergency /></PortalLayout></RequireAuth>} />
      <Route path="/admin/reset-totp" element={<RequireAuth><PortalLayout><EmployeeTotpReset /></PortalLayout></RequireAuth>} />
      <Route path="/admin/pa-unlock"  element={<RequireAuth><PortalLayout><PaUnlock /></PortalLayout></RequireAuth>} />
      <Route path="/admin/reset-password" element={<RequireAuth><PortalLayout><PaEmployeePasswordReset /></PortalLayout></RequireAuth>} />
      <Route path="/admin/employee-merge" element={<RequireAuth><PortalLayout><EmployeeMerge /></PortalLayout></RequireAuth>} />
      <Route path="/admin/storage"    element={<RequireAuth><PortalLayout><StorageRequests /></PortalLayout></RequireAuth>} />
      <Route path="/admin/pipeline"   element={<RequireAuth><PortalLayout><PipelineHealth /></PortalLayout></RequireAuth>} />
      <Route path="/admin/exceptions" element={<RequireAuth><PortalLayout><ExceptionOverview /></PortalLayout></RequireAuth>} />
      <Route path="/admin/secops"     element={<RequireAuth><PortalLayout><SecOpsDashboard /></PortalLayout></RequireAuth>} />
      <Route path="/admin/anomalies"  element={<RequireAuth><PortalLayout><AnomalyDetection /></PortalLayout></RequireAuth>} />
      <Route path="/admin/incidents"           element={<RequireAuth><PortalLayout><IncidentRegister /></PortalLayout></RequireAuth>} />
      <Route path="/admin/security-incidents" element={<RequireAuth><PortalLayout><SecurityIncidentRegister /></PortalLayout></RequireAuth>} />
      <Route path="/admin/incident-policy"    element={<RequireAuth><PortalLayout><IncidentPolicyConfig /></PortalLayout></RequireAuth>} />
      <Route path="/admin/communications"     element={<RequireAuth><PortalLayout><PaCommunicationSettings /></PortalLayout></RequireAuth>} />
      <Route path="/admin/platform-credentials" element={<RequireAuth><PortalLayout><PlatformCredentials /></PortalLayout></RequireAuth>} />
      <Route path="/admin/document-fields"    element={<RequireAuth><PortalLayout><PlatformDocumentFields /></PortalLayout></RequireAuth>} />
      <Route path="/admin/setup-checklist"    element={<RequireAuth><PortalLayout><SetupChecklistTemplate /></PortalLayout></RequireAuth>} />
      <Route path="/admin/notifications"      element={<RequireAuth><PortalLayout><PaNotificationLog /></PortalLayout></RequireAuth>} />
      <Route path="/admin/crypto"     element={<RequireAuth><PortalLayout><CryptoHealth /></PortalLayout></RequireAuth>} />
      <Route path="/admin/audit"      element={<RequireAuth><PortalLayout><AuditTrail /></PortalLayout></RequireAuth>} />
      <Route path="/admin/api-keys"   element={<RequireAuth><PortalLayout><ApiKeys /></PortalLayout></RequireAuth>} />
      <Route path="/admin/rate-limits"      element={<RequireAuth><PortalLayout><RateLimits /></PortalLayout></RequireAuth>} />
      <Route path="/admin/announcements"   element={<RequireAuth><PortalLayout><Announcements /></PortalLayout></RequireAuth>} />
      <Route path="/admin/inquiries"      element={<RequireAuth><PortalLayout><ContactInquiries /></PortalLayout></RequireAuth>} />
      <Route path="/admin/hrms"          element={<RequireAuth><PortalLayout><HRMSCatalogue /></PortalLayout></RequireAuth>} />

      {/* Employee self-service portal */}
      <Route path="/emp/login" element={<EmpLogin />} />
      <Route path="/emp" element={<RequireEmpAuth><EmpLayout /></RequireEmpAuth>}>
        <Route index element={<Navigate to="/emp/vault" replace />} />
        <Route path="vault"        element={<EmpVault />} />
        <Route path="career"       element={<EmpCareer />} />
        <Route path="vault-health" element={<EmpVaultHealth />} />
        <Route path="shares"       element={<EmpShares />} />
        <Route path="activity"     element={<EmpActivity />} />
        <Route path="data-rights"  element={<EmpDataRights />} />
        <Route path="privacy"      element={<EmpPrivacy />} />
        <Route path="doc-request"  element={<EmpDocRequest />} />
        <Route path="settings"     element={<EmpSettings />} />
        <Route path="ask"          element={<EmpAsk />} />
      </Route>

      {/* Fallback */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
