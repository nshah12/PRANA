import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuthStore } from '@/store/auth'
import { Topbar } from '@/components/shell/Topbar'
import { Sidebar } from '@/components/shell/Sidebar'
import { ElevationBanner } from '@/components/shell/ElevationBanner'
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
import { OrgProfile }      from '@/pages/oa/OrgProfile'

// CHRO pages
import { VaultHealthChro }      from '@/pages/chro/VaultHealthChro'
import { ComplianceCalendar }   from '@/pages/chro/ComplianceCalendar'
import { ComplianceExport }     from '@/pages/chro/ComplianceExport'
import { WeeklyDigest }         from '@/pages/chro/WeeklyDigest'
import { MonthlySummary }       from '@/pages/chro/MonthlySummary'
import { QuarterlyReport }      from '@/pages/chro/QuarterlyReport'
import { AlertConfig }          from '@/pages/chro/AlertConfig'
import { StatutoryCompliance }  from '@/pages/chro/StatutoryCompliance'

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
import { CreateTenantWizard }  from '@/pages/pa/CreateTenantWizard'
import { OaEmergency }       from '@/pages/pa/OaEmergency'
import { StorageRequests }   from '@/pages/pa/StorageRequests'
import { PipelineHealth }    from '@/pages/pa/PipelineHealth'
import { AuditTrail }        from '@/pages/pa/AuditTrail'
import { RateLimits }        from '@/pages/pa/RateLimits'
import { Announcements }     from '@/pages/pa/Announcements'
import { ContactInquiries }  from '@/pages/pa/ContactInquiries'

function RequireEmpAuth({ children }: { children: React.ReactNode }) {
  const user = useEmpAuthStore(s => s.user)
  const location = useLocation()
  if (!user) return <Navigate to="/emp/login" state={{ from: location }} replace />
  return <>{children}</>
}

function RequireAuth({ children }: { children: React.ReactNode }) {
  const user = useAuthStore(s => s.user)
  const location = useLocation()
  if (!user) {
    const loginPage = location.pathname.startsWith('/admin') ? '/admin/login' : '/org/login'
    return <Navigate to={loginPage} replace />
  }
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
      <main className="ml-[220px] min-h-screen" style={{ paddingTop: hasElevation ? 92 : 52 }}>
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
      <Route path="/admin/oa-override"element={<RequireAuth><PortalLayout><OaEmergency /></PortalLayout></RequireAuth>} />
      <Route path="/admin/storage"    element={<RequireAuth><PortalLayout><StorageRequests /></PortalLayout></RequireAuth>} />
      <Route path="/admin/pipeline"   element={<RequireAuth><PortalLayout><PipelineHealth /></PortalLayout></RequireAuth>} />
      <Route path="/admin/exceptions" element={<RequireAuth><PortalLayout><ExceptionOverview /></PortalLayout></RequireAuth>} />
      <Route path="/admin/secops"     element={<RequireAuth><PortalLayout><SecOpsDashboard /></PortalLayout></RequireAuth>} />
      <Route path="/admin/anomalies"  element={<RequireAuth><PortalLayout><AnomalyDetection /></PortalLayout></RequireAuth>} />
      <Route path="/admin/incidents"           element={<RequireAuth><PortalLayout><IncidentRegister /></PortalLayout></RequireAuth>} />
      <Route path="/admin/security-incidents" element={<RequireAuth><PortalLayout><SecurityIncidentRegister /></PortalLayout></RequireAuth>} />
      <Route path="/admin/notifications"      element={<RequireAuth><PortalLayout><PaNotificationLog /></PortalLayout></RequireAuth>} />
      <Route path="/admin/crypto"     element={<RequireAuth><PortalLayout><CryptoHealth /></PortalLayout></RequireAuth>} />
      <Route path="/admin/audit"      element={<RequireAuth><PortalLayout><AuditTrail /></PortalLayout></RequireAuth>} />
      <Route path="/admin/api-keys"   element={<RequireAuth><PortalLayout><ApiKeys /></PortalLayout></RequireAuth>} />
      <Route path="/admin/rate-limits"      element={<RequireAuth><PortalLayout><RateLimits /></PortalLayout></RequireAuth>} />
      <Route path="/admin/announcements"   element={<RequireAuth><PortalLayout><Announcements /></PortalLayout></RequireAuth>} />
      <Route path="/admin/inquiries"      element={<RequireAuth><PortalLayout><ContactInquiries /></PortalLayout></RequireAuth>} />

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
