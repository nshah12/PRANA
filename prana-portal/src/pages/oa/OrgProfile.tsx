import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Building2, MapPin, Users, Shield, Briefcase, Settings,
  Save, Lock, AlertTriangle, Check, ChevronDown, ChevronUp,
} from 'lucide-react'
import { api } from '@/lib/api'

// ── Helpers ───────────────────────────────────────────────────────────────────

function Section({
  icon: Icon, title, subtitle, children, defaultOpen = false,
}: {
  icon: React.ElementType; title: string; subtitle?: string
  children: React.ReactNode; defaultOpen?: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="bg-white rounded-xl border border-slate-100 shadow-sm overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full px-6 py-4 flex items-center gap-3 hover:bg-slate-50/50 transition-colors">
        <div className="w-8 h-8 rounded-lg bg-violet-100 flex items-center justify-center flex-shrink-0">
          <Icon size={15} className="text-violet-600" />
        </div>
        <div className="flex-1 text-left">
          <p className="font-semibold text-slate-800 text-sm">{title}</p>
          {subtitle && <p className="text-xs text-slate-400 mt-0.5">{subtitle}</p>}
        </div>
        {open ? <ChevronUp size={14} className="text-slate-400" /> : <ChevronDown size={14} className="text-slate-400" />}
      </button>
      {open && <div className="px-6 pb-6 pt-2 border-t border-slate-100">{children}</div>}
    </div>
  )
}

const inp = "w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-violet-400 bg-white disabled:bg-slate-50 disabled:text-slate-400"
const sel = `${inp} cursor-pointer`

function ReadOnly({ label, value }: { label: string; value?: string | null }) {
  return (
    <div>
      <p className="text-xs font-medium text-slate-500 mb-1">{label}</p>
      <div className="flex items-center gap-1.5">
        <Lock size={11} className="text-slate-300 flex-shrink-0" />
        <p className="text-sm text-slate-600">{value || '—'}</p>
      </div>
    </div>
  )
}

function Field({ label, required, hint, children }: {
  label: string; required?: boolean; hint?: string; children: React.ReactNode
}) {
  return (
    <div className="space-y-1">
      <label className="block text-xs font-medium text-slate-700">
        {label}{required && <span className="text-red-500 ml-0.5">*</span>}
      </label>
      {children}
      {hint && <p className="text-xs text-slate-400">{hint}</p>}
    </div>
  )
}

const STATES = [
  'Andhra Pradesh','Arunachal Pradesh','Assam','Bihar','Chhattisgarh','Goa','Gujarat',
  'Haryana','Himachal Pradesh','Jharkhand','Karnataka','Kerala','Madhya Pradesh',
  'Maharashtra','Manipur','Meghalaya','Mizoram','Nagaland','Odisha','Punjab','Rajasthan',
  'Sikkim','Tamil Nadu','Telangana','Tripura','Uttar Pradesh','Uttarakhand','West Bengal',
  'Delhi','Chandigarh','Puducherry',
]

const INDUSTRIES = [
  'Banking & Financial Services (BFSI)','IT & Software','Manufacturing',
  'Healthcare & Pharma','Retail & FMCG','Telecom','Education & EdTech',
  'Real Estate & Construction','Logistics & Supply Chain','Government / PSU',
  'Media & Entertainment','Automobile & Auto-ancillary','Other',
]

const HRMS_OPTIONS = [
  'SAP HCM','Darwinbox','GreytHR','Keka','Zoho People','BambooHR',
  'Workday','Oracle HCM','ADP','Freshteam','sumHR','HRMantra',
  'Manual / None','Custom / In-house',
]

// ── Main Component ────────────────────────────────────────────────────────────

export function OrgProfile() {
  const qc = useQueryClient()
  const { data: profile, isLoading } = useQuery({
    queryKey: ['org-profile'],
    queryFn: () => api.get('/v1/org/profile').then(r => r.data),
  })

  const [form, setForm] = useState<Record<string, any>>({})
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    if (profile) {
      setForm({
        brand_name: profile.brand_name ?? '',
        primary_contact: profile.primary_contact ?? {},
        reg_address: profile.reg_address ?? {},
        corp_address: profile.corp_address ?? {},
        dpo_name: profile.dpo_name ?? '',
        dpo_email: profile.dpo_email ?? '',
        grievance_officer_name: profile.grievance_officer_name ?? '',
        grievance_officer_email: profile.grievance_officer_email ?? '',
        industry: profile.industry ?? '',
        employee_headcount_band: profile.employee_headcount_band ?? '',
        payroll_frequency: profile.payroll_frequency ?? 'MONTHLY',
        fiscal_year_start: profile.fiscal_year_start ?? 'APRIL',
        hrms_system: profile.hrms_system ?? '',
        document_ingestion_method: profile.document_ingestion_method ?? 'PORTAL_UPLOAD',
        pf_registration: profile.pf_registration ?? '',
        esic_registration: profile.esic_registration ?? '',
        logo_url: profile.logo_url ?? '',
        brand_colour: profile.brand_colour ?? '',
        support_email: profile.support_email ?? '',
        default_language: profile.default_language ?? 'en',
        push_window_months: profile.push_window_months ?? 6,
      })
    }
  }, [profile])

  const saveMutation = useMutation({
    mutationFn: () => {
      const payload: Record<string, any> = {}
      const strings = [
        'brand_name','dpo_name','dpo_email','grievance_officer_name','grievance_officer_email',
        'industry','employee_headcount_band','payroll_frequency','fiscal_year_start',
        'hrms_system','document_ingestion_method','pf_registration','esic_registration',
        'logo_url','brand_colour','support_email','default_language',
      ]
      for (const k of strings) {
        if (form[k] !== undefined && form[k] !== '') payload[k] = form[k]
      }
      if (form.push_window_months) payload.push_window_months = Number(form.push_window_months)
      if (form.primary_contact && Object.keys(form.primary_contact).length)
        payload.primary_contact = form.primary_contact
      if (form.reg_address && form.reg_address.line1)
        payload.reg_address = form.reg_address
      if (form.corp_address && form.corp_address.line1)
        payload.corp_address = form.corp_address
      return api.patch('/v1/org/profile', payload).then(r => r.data)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['org-profile'] })
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    },
  })

  const sf = (key: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm(f => ({ ...f, [key]: e.target.value }))

  const nested = (obj: string, field: string) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
      setForm(f => ({ ...f, [obj]: { ...(f[obj] ?? {}), [field]: e.target.value } }))

  if (isLoading) return <p className="text-sm text-slate-400 p-6">Loading profile…</p>

  const p = profile ?? {}

  return (
    <div className="space-y-4 max-w-3xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-800">Org Profile</h1>
          <p className="text-xs text-slate-400 mt-0.5">
            View and update your organisation's profile.
            <span className="inline-flex items-center gap-1 ml-2 text-slate-300">
              <Lock size={10}/> fields are managed by PRANA Platform Admin.
            </span>
          </p>
        </div>
        <button
          onClick={() => saveMutation.mutate()}
          disabled={saveMutation.isPending}
          className="flex items-center gap-2 px-5 py-2 bg-violet-600 text-white text-sm
                     font-medium rounded-lg hover:bg-violet-700 disabled:opacity-50">
          <Save size={13}/>
          {saved ? <><Check size={13}/>Saved</> : saveMutation.isPending ? 'Saving…' : 'Save changes'}
        </button>
      </div>

      {/* ── Locked: Legal & Platform ─────────────────────────────────────── */}
      <Section icon={Building2} title="Legal Identity" subtitle="Managed by Platform Admin" defaultOpen={true}>
        <div className="grid grid-cols-2 gap-x-8 gap-y-4 mt-2">
          <ReadOnly label="Organisation Legal Name" value={p.tenant_name} />
          <Field label="Brand / Trade Name">
            <input className={inp} value={form.brand_name ?? ''} onChange={sf('brand_name')}
              placeholder="Common operating name" />
          </Field>
          <ReadOnly label="CIN" value={p.cin} />
          <ReadOnly label="GSTIN" value={p.gstin} />
          <ReadOnly label="Entity Type" value={p.entity_type} />
          <ReadOnly label="Date of Incorporation" value={p.incorporation_date} />
          <ReadOnly label="ROC Jurisdiction" value={p.roc_jurisdiction} />
          <ReadOnly label="Company PAN" value={p.pan_entity} />
          <ReadOnly label="TAN" value={p.tan} />
          <ReadOnly label="Status" value={p.status} />
          <ReadOnly label="Data Region (IMMUTABLE)" value={p.home_region} />
          <ReadOnly label="Domain" value={p.domain} />
        </div>
      </Section>

      {/* ── Addresses ────────────────────────────────────────────────────── */}
      <Section icon={MapPin} title="Addresses" subtitle="Registered office and corporate head office">
        <div className="space-y-6 mt-2">
          <div>
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">
              Registered Office Address
            </p>
            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2">
                <Field label="Address Line 1">
                  <input className={inp} value={form.reg_address?.line1 ?? ''}
                    onChange={nested('reg_address','line1')} placeholder="Building / Flat, Street" />
                </Field>
              </div>
              <Field label="Address Line 2">
                <input className={inp} value={form.reg_address?.line2 ?? ''}
                  onChange={nested('reg_address','line2')} placeholder="Area / Locality" />
              </Field>
              <Field label="City">
                <input className={inp} value={form.reg_address?.city ?? ''}
                  onChange={nested('reg_address','city')} placeholder="Mumbai" />
              </Field>
              <Field label="State">
                <select className={sel} value={form.reg_address?.state ?? ''}
                  onChange={nested('reg_address','state')}>
                  <option value="">Select state</option>
                  {STATES.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </Field>
              <Field label="PIN Code">
                <input className={inp} value={form.reg_address?.pincode ?? ''}
                  onChange={nested('reg_address','pincode')} placeholder="400001" maxLength={6} />
              </Field>
            </div>
          </div>

          <div>
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">
              Corporate / Head Office Address <span className="font-normal normal-case">(if different)</span>
            </p>
            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2">
                <Field label="Address Line 1">
                  <input className={inp} value={form.corp_address?.line1 ?? ''}
                    onChange={nested('corp_address','line1')} placeholder="Building / Flat, Street" />
                </Field>
              </div>
              <Field label="City">
                <input className={inp} value={form.corp_address?.city ?? ''}
                  onChange={nested('corp_address','city')} placeholder="Bangalore" />
              </Field>
              <Field label="State">
                <select className={sel} value={form.corp_address?.state ?? ''}
                  onChange={nested('corp_address','state')}>
                  <option value="">Select state</option>
                  {STATES.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </Field>
              <Field label="PIN Code">
                <input className={inp} value={form.corp_address?.pincode ?? ''}
                  onChange={nested('corp_address','pincode')} placeholder="560001" maxLength={6} />
              </Field>
            </div>
          </div>
        </div>
      </Section>

      {/* ── Primary Contact ───────────────────────────────────────────────── */}
      <Section icon={Users} title="Primary Contact" subtitle="Authorised SPOC for PRANA communications">
        <div className="grid grid-cols-2 gap-4 mt-2">
          <Field label="Full Name">
            <input className={inp} value={form.primary_contact?.name ?? ''}
              onChange={nested('primary_contact','name')} placeholder="Priya Sharma" />
          </Field>
          <Field label="Designation">
            <input className={inp} value={form.primary_contact?.designation ?? ''}
              onChange={nested('primary_contact','designation')} placeholder="CHRO / HR Head" />
          </Field>
          <Field label="Work Email">
            <input type="email" className={inp} value={form.primary_contact?.email ?? ''}
              onChange={nested('primary_contact','email')} placeholder="priya@company.in" />
          </Field>
          <Field label="Mobile">
            <input className={inp} value={form.primary_contact?.mobile ?? ''}
              onChange={nested('primary_contact','mobile')} placeholder="+91 98765 43210" />
          </Field>
        </div>
      </Section>

      {/* ── DPDP Officers ─────────────────────────────────────────────────── */}
      <Section icon={Shield} title="Data Protection Officers (DPDP Act 2023)"
        subtitle="DPO and Grievance Officer are displayed to employees in the PRANA app">
        <div className="grid grid-cols-2 gap-4 mt-2">
          <Field label="DPO Name">
            <input className={inp} value={form.dpo_name ?? ''} onChange={sf('dpo_name')}
              placeholder="Full name" />
          </Field>
          <Field label="DPO Email">
            <input type="email" className={inp} value={form.dpo_email ?? ''} onChange={sf('dpo_email')}
              placeholder="dpo@company.in" />
          </Field>
          <Field label="Grievance Officer Name">
            <input className={inp} value={form.grievance_officer_name ?? ''}
              onChange={sf('grievance_officer_name')} placeholder="Full name" />
          </Field>
          <Field label="Grievance Officer Email">
            <input type="email" className={inp} value={form.grievance_officer_email ?? ''}
              onChange={sf('grievance_officer_email')} placeholder="grievance@company.in" />
          </Field>
        </div>
        {profile?.dpa_accepted_at && (
          <div className="mt-4 flex items-center gap-2 text-xs text-emerald-700 bg-emerald-50 rounded-lg px-3 py-2">
            <Check size={12}/> DPA v{profile.dpa_version} accepted on {new Date(profile.dpa_accepted_at).toLocaleDateString('en-IN', { day:'2-digit', month:'long', year:'numeric' })}
          </div>
        )}
      </Section>

      {/* ── Workforce Profile ─────────────────────────────────────────────── */}
      <Section icon={Briefcase} title="Workforce Profile"
        subtitle="HR configuration used for analytics and PRANA AI pipeline tuning">
        <div className="grid grid-cols-2 gap-4 mt-2">
          <Field label="Industry / Sector">
            <select className={sel} value={form.industry ?? ''} onChange={sf('industry')}>
              <option value="">Select industry</option>
              {INDUSTRIES.map(i => <option key={i} value={i}>{i}</option>)}
            </select>
          </Field>
          <Field label="Employee Headcount Band">
            <select className={sel} value={form.employee_headcount_band ?? ''}
              onChange={sf('employee_headcount_band')}>
              <option value="">Select band</option>
              {['1-50','51-200','201-500','501-2000','2001-10000','10000+'].map(b =>
                <option key={b} value={b}>{b} employees</option>
              )}
            </select>
          </Field>
          <Field label="Payroll Frequency">
            <select className={sel} value={form.payroll_frequency ?? 'MONTHLY'}
              onChange={sf('payroll_frequency')}>
              <option value="MONTHLY">Monthly</option>
              <option value="BI_MONTHLY">Bi-monthly</option>
              <option value="WEEKLY">Weekly</option>
            </select>
          </Field>
          <Field label="Fiscal Year Start">
            <select className={sel} value={form.fiscal_year_start ?? 'APRIL'}
              onChange={sf('fiscal_year_start')}>
              <option value="APRIL">April (India standard)</option>
              <option value="JANUARY">January (MNC / foreign subsidiary)</option>
              <option value="OTHER">Other</option>
            </select>
          </Field>
          <Field label="HRMS / Payroll Platform">
            <select className={sel} value={form.hrms_system ?? ''} onChange={sf('hrms_system')}>
              <option value="">Select platform</option>
              {HRMS_OPTIONS.map(h => <option key={h} value={h}>{h}</option>)}
            </select>
          </Field>
          <Field label="Document Ingestion Method">
            <select className={sel} value={form.document_ingestion_method ?? 'PORTAL_UPLOAD'}
              onChange={sf('document_ingestion_method')}>
              <option value="PORTAL_UPLOAD">Portal Upload</option>
              <option value="HRMS_API">HRMS API Push</option>
              <option value="BOTH">Both (portal + API)</option>
            </select>
          </Field>
          <Field label="Push Window (months)"
            hint="How many months back employer can push historical documents">
            <select className={sel} value={String(form.push_window_months ?? 6)}
              onChange={e => setForm(f => ({ ...f, push_window_months: Number(e.target.value) }))}>
              <option value="3">3 months</option>
              <option value="6">6 months (default)</option>
              <option value="9">9 months</option>
              <option value="12">12 months</option>
            </select>
          </Field>
          <Field label="Default Language">
            <select className={sel} value={form.default_language ?? 'en'}
              onChange={sf('default_language')}>
              {[['en','English'],['hi','Hindi'],['mr','Marathi'],['ta','Tamil'],
                ['te','Telugu'],['kn','Kannada'],['bn','Bengali'],['gu','Gujarati']
              ].map(([v,l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </Field>
        </div>
      </Section>

      {/* ── Statutory Registrations ───────────────────────────────────────── */}
      <Section icon={Shield} title="Statutory Registrations"
        subtitle="PF, ESIC, and other statutory details used for document validation">
        <div className="grid grid-cols-2 gap-4 mt-2">
          <Field label="PF Registration Number"
            hint="Provident Fund establishment code (format: XX/XXX/XXXXXXX)">
            <input className={inp} value={form.pf_registration ?? ''} onChange={sf('pf_registration')}
              placeholder="MH/MUM/0012345" />
          </Field>
          <Field label="ESIC Registration Number"
            hint="Employees' State Insurance Corporation code (if applicable)">
            <input className={inp} value={form.esic_registration ?? ''} onChange={sf('esic_registration')}
              placeholder="31-00-123456-000-0000" />
          </Field>
        </div>
      </Section>

      {/* ── Branding ─────────────────────────────────────────────────────── */}
      <Section icon={Settings} title="Branding & Employee Support"
        subtitle="Shown on employee-facing employer card in the PRANA mobile app">
        <div className="grid grid-cols-2 gap-4 mt-2">
          <div className="col-span-2">
            <Field label="Organisation Logo URL"
              hint="HTTPS URL to logo image (PNG/SVG, minimum 200×200px)">
              <input className={inp} value={form.logo_url ?? ''} onChange={sf('logo_url')}
                placeholder="https://cdn.company.in/logo.png" />
            </Field>
          </div>
          <Field label="Brand Colour (Hex)" hint="Primary brand colour for employer card">
            <div className="flex gap-2 items-center">
              <input type="color" value={form.brand_colour || '#6366f1'}
                onChange={sf('brand_colour')}
                className="w-10 h-10 rounded-lg border border-slate-200 cursor-pointer p-0.5" />
              <input className={`${inp} flex-1`} value={form.brand_colour ?? ''}
                onChange={sf('brand_colour')} placeholder="#6366f1" maxLength={7} />
            </div>
          </Field>
          <Field label="Employee Support Email"
            hint="Where employees write for HR queries — shown in PRANA app">
            <input type="email" className={inp} value={form.support_email ?? ''}
              onChange={sf('support_email')} placeholder="hr-support@company.in" />
          </Field>
        </div>
      </Section>

      {/* ── Platform-locked ──────────────────────────────────────────────── */}
      <Section icon={Lock} title="Platform Configuration"
        subtitle="Managed by PRANA Platform Admin — contact support to change">
        <div className="grid grid-cols-2 gap-x-8 gap-y-4 mt-2 opacity-70">
          <ReadOnly label="SLA Tier" value={p.sla_tier} />
          <ReadOnly label="Storage Quota" value={p.storage_quota_gb ? `${p.storage_quota_gb} GB` : undefined} />
          <ReadOnly label="Contract Type" value={p.contract_type} />
          <ReadOnly label="Onboarding Tier" value={p.onboarding_tier} />
          <ReadOnly label="NIK (Employee Identifier Type)" value={p.nik_type} />
          <ReadOnly label="Self-Upload Policy" value={p.self_upload_policy} />
          <ReadOnly label="Account Manager" value={p.account_manager} />
          <ReadOnly label="Member Since" value={p.created_at ? new Date(p.created_at).toLocaleDateString('en-IN', { day:'2-digit', month:'long', year:'numeric' }) : undefined} />
        </div>
        <p className="text-xs text-slate-400 mt-4 flex items-center gap-1">
          <AlertTriangle size={11}/> To request changes to locked fields, raise a support ticket with PRANA.
        </p>
      </Section>

      {/* Save footer */}
      <div className="flex justify-end pb-4">
        <button
          onClick={() => saveMutation.mutate()}
          disabled={saveMutation.isPending}
          className="flex items-center gap-2 px-6 py-2.5 bg-violet-600 text-white text-sm
                     font-semibold rounded-lg hover:bg-violet-700 disabled:opacity-50">
          <Save size={13}/>
          {saved ? <><Check size={13}/>Saved</> : saveMutation.isPending ? 'Saving…' : 'Save all changes'}
        </button>
      </div>
    </div>
  )
}
