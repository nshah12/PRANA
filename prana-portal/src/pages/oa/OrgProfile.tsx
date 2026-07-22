import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Building2, MapPin, Users, Shield, Briefcase, Settings,
  Save, Lock, AlertTriangle, Check, ChevronDown, ChevronUp,
} from 'lucide-react'
import { api } from '@/lib/api'
import { tUi } from '@/i18n'

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

  if (isLoading) return <p className="text-sm text-slate-400 p-6">{tUi('OA_ORG_PROFILE_LOADING')}</p>

  const p = profile ?? {}

  return (
    <div className="space-y-4 max-w-3xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-800">{tUi('OA_ORG_PROFILE_TITLE')}</h1>
          <p className="text-xs text-slate-400 mt-0.5">
            {tUi('OA_ORG_PROFILE_SUB')}
            <span className="inline-flex items-center gap-1 ml-2 text-slate-300">
              <Lock size={10}/> {tUi('OA_ORG_PROFILE_LOCKED_NOTE')}
            </span>
          </p>
        </div>
        <button
          onClick={() => saveMutation.mutate()}
          disabled={saveMutation.isPending}
          className="flex items-center gap-2 px-5 py-2 bg-violet-600 text-white text-sm
                     font-medium rounded-lg hover:bg-violet-700 disabled:opacity-50">
          <Save size={13}/>
          {saved ? <><Check size={13}/>{tUi('OA_ORG_PROFILE_SAVED')}</> : saveMutation.isPending ? tUi('OA_ORG_PROFILE_SAVING') : tUi('OA_ORG_PROFILE_SAVE_CHANGES')}
        </button>
      </div>

      {/* ── Locked: Legal & Platform ─────────────────────────────────────── */}
      <Section icon={Building2} title={tUi('OA_ORG_PROFILE_LEGAL_IDENTITY_TITLE')} subtitle={tUi('OA_ORG_PROFILE_MANAGED_BY_PA')} defaultOpen={true}>
        <div className="grid grid-cols-2 gap-x-8 gap-y-4 mt-2">
          <ReadOnly label={tUi('OA_ORG_PROFILE_LEGAL_NAME')} value={p.tenant_name} />
          <Field label={tUi('OA_ORG_PROFILE_BRAND_NAME_LABEL')}>
            <input className={inp} value={form.brand_name ?? ''} onChange={sf('brand_name')}
              placeholder={tUi('ORG_PROFILE_BRAND_NAME_PLACEHOLDER')} />
          </Field>
          <ReadOnly label={tUi('OA_ORG_PROFILE_CIN')} value={p.cin} />
          <ReadOnly label={tUi('OA_ORG_PROFILE_GSTIN')} value={p.gstin} />
          <ReadOnly label={tUi('OA_ORG_PROFILE_ENTITY_TYPE')} value={p.entity_type} />
          <ReadOnly label={tUi('OA_ORG_PROFILE_INCORPORATION_DATE')} value={p.incorporation_date} />
          <ReadOnly label={tUi('OA_ORG_PROFILE_ROC')} value={p.roc_jurisdiction} />
          <ReadOnly label={tUi('OA_ORG_PROFILE_COMPANY_PAN')} value={p.pan_entity} />
          <ReadOnly label={tUi('OA_ORG_PROFILE_TAN')} value={p.tan} />
          <ReadOnly label={tUi('OA_ORG_PROFILE_STATUS')} value={p.status} />
          <ReadOnly label={tUi('OA_ORG_PROFILE_DATA_REGION')} value={p.home_region} />
          <ReadOnly label={tUi('OA_ORG_PROFILE_DOMAIN')} value={p.domain} />
        </div>
      </Section>

      {/* ── Addresses ────────────────────────────────────────────────────── */}
      <Section icon={MapPin} title={tUi('OA_ORG_PROFILE_ADDRESSES_TITLE')} subtitle={tUi('OA_ORG_PROFILE_ADDRESSES_SUB')}>
        <div className="space-y-6 mt-2">
          <div>
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">
              {tUi('OA_ORG_PROFILE_REG_OFFICE')}
            </p>
            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2">
                <Field label={tUi('OA_ORG_PROFILE_ADDR_LINE1')}>
                  <input className={inp} value={form.reg_address?.line1 ?? ''}
                    onChange={nested('reg_address','line1')} placeholder="Building / Flat, Street" />
                </Field>
              </div>
              <Field label={tUi('OA_ORG_PROFILE_ADDR_LINE2')}>
                <input className={inp} value={form.reg_address?.line2 ?? ''}
                  onChange={nested('reg_address','line2')} placeholder="Area / Locality" />
              </Field>
              <Field label={tUi('OA_ORG_PROFILE_CITY')}>
                <input className={inp} value={form.reg_address?.city ?? ''}
                  onChange={nested('reg_address','city')} placeholder="Mumbai" />
              </Field>
              <Field label={tUi('OA_ORG_PROFILE_STATE')}>
                <select className={sel} value={form.reg_address?.state ?? ''}
                  onChange={nested('reg_address','state')}>
                  <option value="">{tUi('OA_ORG_PROFILE_SELECT_STATE')}</option>
                  {STATES.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </Field>
              <Field label={tUi('OA_ORG_PROFILE_PINCODE')}>
                <input className={inp} value={form.reg_address?.pincode ?? ''}
                  onChange={nested('reg_address','pincode')} placeholder="400001" maxLength={6} />
              </Field>
            </div>
          </div>

          <div>
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">
              {tUi('OA_ORG_PROFILE_CORP_OFFICE')} <span className="font-normal normal-case">{tUi('OA_ORG_PROFILE_IF_DIFFERENT')}</span>
            </p>
            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2">
                <Field label={tUi('OA_ORG_PROFILE_ADDR_LINE1')}>
                  <input className={inp} value={form.corp_address?.line1 ?? ''}
                    onChange={nested('corp_address','line1')} placeholder="Building / Flat, Street" />
                </Field>
              </div>
              <Field label={tUi('OA_ORG_PROFILE_CITY')}>
                <input className={inp} value={form.corp_address?.city ?? ''}
                  onChange={nested('corp_address','city')} placeholder="Bangalore" />
              </Field>
              <Field label={tUi('OA_ORG_PROFILE_STATE')}>
                <select className={sel} value={form.corp_address?.state ?? ''}
                  onChange={nested('corp_address','state')}>
                  <option value="">{tUi('OA_ORG_PROFILE_SELECT_STATE')}</option>
                  {STATES.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </Field>
              <Field label={tUi('OA_ORG_PROFILE_PINCODE')}>
                <input className={inp} value={form.corp_address?.pincode ?? ''}
                  onChange={nested('corp_address','pincode')} placeholder="560001" maxLength={6} />
              </Field>
            </div>
          </div>
        </div>
      </Section>

      {/* ── Primary Contact ───────────────────────────────────────────────── */}
      <Section icon={Users} title={tUi('OA_ORG_PROFILE_PRIMARY_CONTACT_TITLE')} subtitle={tUi('OA_ORG_PROFILE_PRIMARY_CONTACT_SUB')}>
        <div className="grid grid-cols-2 gap-4 mt-2">
          <Field label={tUi('OA_ORG_PROFILE_FULL_NAME')}>
            <input className={inp} value={form.primary_contact?.name ?? ''}
              onChange={nested('primary_contact','name')} placeholder="Priya Sharma" />
          </Field>
          <Field label={tUi('OA_ORG_PROFILE_DESIGNATION')}>
            <input className={inp} value={form.primary_contact?.designation ?? ''}
              onChange={nested('primary_contact','designation')} placeholder="CHRO / HR Head" />
          </Field>
          <Field label={tUi('OA_ORG_PROFILE_WORK_EMAIL')}>
            <input type="email" className={inp} value={form.primary_contact?.email ?? ''}
              onChange={nested('primary_contact','email')} placeholder="priya@company.in" />
          </Field>
          <Field label={tUi('OA_ORG_PROFILE_MOBILE')}>
            <input className={inp} value={form.primary_contact?.mobile ?? ''}
              onChange={nested('primary_contact','mobile')} placeholder="+91 98765 43210" />
          </Field>
        </div>
      </Section>

      {/* ── DPDP Officers ─────────────────────────────────────────────────── */}
      <Section icon={Shield} title={tUi('OA_ORG_PROFILE_DPO_TITLE')}
        subtitle={tUi('OA_ORG_PROFILE_DPO_SUB')}>
        <div className="grid grid-cols-2 gap-4 mt-2">
          <Field label={tUi('OA_ORG_PROFILE_DPO_NAME')}>
            <input className={inp} value={form.dpo_name ?? ''} onChange={sf('dpo_name')}
              placeholder={tUi('OA_ORG_PROFILE_FULL_NAME_PLACEHOLDER')} />
          </Field>
          <Field label={tUi('OA_ORG_PROFILE_DPO_EMAIL')}>
            <input type="email" className={inp} value={form.dpo_email ?? ''} onChange={sf('dpo_email')}
              placeholder="dpo@company.in" />
          </Field>
          <Field label={tUi('OA_ORG_PROFILE_GRIEVANCE_NAME')}>
            <input className={inp} value={form.grievance_officer_name ?? ''}
              onChange={sf('grievance_officer_name')} placeholder={tUi('OA_ORG_PROFILE_FULL_NAME_PLACEHOLDER')} />
          </Field>
          <Field label={tUi('OA_ORG_PROFILE_GRIEVANCE_EMAIL')}>
            <input type="email" className={inp} value={form.grievance_officer_email ?? ''}
              onChange={sf('grievance_officer_email')} placeholder="grievance@company.in" />
          </Field>
        </div>
        {profile?.dpa_accepted_at && (
          <div className="mt-4 flex items-center gap-2 text-xs text-emerald-700 bg-emerald-50 rounded-lg px-3 py-2">
            <Check size={12}/> {tUi('OA_ORG_PROFILE_DPA_ACCEPTED', { version: profile.dpa_version, date: new Date(profile.dpa_accepted_at).toLocaleDateString('en-IN', { day:'2-digit', month:'long', year:'numeric' }) })}
          </div>
        )}
      </Section>

      {/* ── Workforce Profile ─────────────────────────────────────────────── */}
      <Section icon={Briefcase} title={tUi('OA_ORG_PROFILE_WORKFORCE_TITLE')}
        subtitle={tUi('OA_ORG_PROFILE_WORKFORCE_SUB')}>
        <div className="grid grid-cols-2 gap-4 mt-2">
          <Field label={tUi('OA_ORG_PROFILE_INDUSTRY_LABEL')}>
            <select className={sel} value={form.industry ?? ''} onChange={sf('industry')}>
              <option value="">{tUi('OA_ORG_PROFILE_SELECT_INDUSTRY')}</option>
              {INDUSTRIES.map(i => <option key={i} value={i}>{i}</option>)}
            </select>
          </Field>
          <Field label={tUi('OA_ORG_PROFILE_HEADCOUNT_LABEL')}>
            <select className={sel} value={form.employee_headcount_band ?? ''}
              onChange={sf('employee_headcount_band')}>
              <option value="">{tUi('OA_ORG_PROFILE_SELECT_BAND')}</option>
              {['1-50','51-200','201-500','501-2000','2001-10000','10000+'].map(b =>
                <option key={b} value={b}>{b} {tUi('OA_ORG_PROFILE_EMPLOYEES_SUFFIX')}</option>
              )}
            </select>
          </Field>
          <Field label={tUi('OA_ORG_PROFILE_PAYROLL_FREQ_LABEL')}>
            <select className={sel} value={form.payroll_frequency ?? 'MONTHLY'}
              onChange={sf('payroll_frequency')}>
              <option value="MONTHLY">{tUi('OA_ORG_PROFILE_MONTHLY')}</option>
              <option value="BI_MONTHLY">{tUi('OA_ORG_PROFILE_BI_MONTHLY')}</option>
              <option value="WEEKLY">{tUi('OA_ORG_PROFILE_WEEKLY')}</option>
            </select>
          </Field>
          <Field label={tUi('OA_ORG_PROFILE_FISCAL_YEAR_LABEL')}>
            <select className={sel} value={form.fiscal_year_start ?? 'APRIL'}
              onChange={sf('fiscal_year_start')}>
              <option value="APRIL">{tUi('OA_ORG_PROFILE_APRIL_STANDARD')}</option>
              <option value="JANUARY">{tUi('OA_ORG_PROFILE_JANUARY_MNC')}</option>
              <option value="OTHER">{tUi('OA_ORG_PROFILE_OTHER')}</option>
            </select>
          </Field>
          <Field label={tUi('OA_ORG_PROFILE_HRMS_PLATFORM_LABEL')}>
            <select className={sel} value={form.hrms_system ?? ''} onChange={sf('hrms_system')}>
              <option value="">{tUi('OA_ORG_PROFILE_SELECT_PLATFORM')}</option>
              {HRMS_OPTIONS.map(h => <option key={h} value={h}>{h}</option>)}
            </select>
          </Field>
          <Field label={tUi('OA_ORG_PROFILE_INGESTION_METHOD_LABEL')}>
            <select className={sel} value={form.document_ingestion_method ?? 'PORTAL_UPLOAD'}
              onChange={sf('document_ingestion_method')}>
              <option value="PORTAL_UPLOAD">{tUi('OA_ORG_PROFILE_PORTAL_UPLOAD')}</option>
              <option value="HRMS_API">{tUi('OA_ORG_PROFILE_HRMS_API_PUSH')}</option>
              <option value="BOTH">{tUi('OA_ORG_PROFILE_BOTH_PORTAL_API')}</option>
            </select>
          </Field>
          <Field label={tUi('OA_ORG_PROFILE_PUSH_WINDOW_LABEL')}
            hint={tUi('OA_ORG_PROFILE_PUSH_WINDOW_HINT')}>
            <select className={sel} value={String(form.push_window_months ?? 6)}
              onChange={e => setForm(f => ({ ...f, push_window_months: Number(e.target.value) }))}>
              <option value="3">{tUi('OA_ORG_PROFILE_MONTHS_3')}</option>
              <option value="6">{tUi('OA_ORG_PROFILE_MONTHS_6_DEFAULT')}</option>
              <option value="9">{tUi('OA_ORG_PROFILE_MONTHS_9')}</option>
              <option value="12">{tUi('OA_ORG_PROFILE_MONTHS_12')}</option>
            </select>
          </Field>
          <Field label={tUi('OA_ORG_PROFILE_DEFAULT_LANG_LABEL')}>
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
      <Section icon={Shield} title={tUi('OA_ORG_PROFILE_STATUTORY_TITLE')}
        subtitle={tUi('OA_ORG_PROFILE_STATUTORY_SUB')}>
        <div className="grid grid-cols-2 gap-4 mt-2">
          <Field label={tUi('OA_ORG_PROFILE_PF_REG_LABEL')}
            hint={tUi('OA_ORG_PROFILE_PF_REG_HINT')}>
            <input className={inp} value={form.pf_registration ?? ''} onChange={sf('pf_registration')}
              placeholder="MH/MUM/0012345" />
          </Field>
          <Field label={tUi('OA_ORG_PROFILE_ESIC_REG_LABEL')}
            hint={tUi('OA_ORG_PROFILE_ESIC_REG_HINT')}>
            <input className={inp} value={form.esic_registration ?? ''} onChange={sf('esic_registration')}
              placeholder="31-00-123456-000-0000" />
          </Field>
        </div>
      </Section>

      {/* ── Branding ─────────────────────────────────────────────────────── */}
      <Section icon={Settings} title={tUi('OA_ORG_PROFILE_BRANDING_TITLE')}
        subtitle={tUi('OA_ORG_PROFILE_BRANDING_SUB')}>
        <div className="grid grid-cols-2 gap-4 mt-2">
          <div className="col-span-2">
            <Field label={tUi('OA_ORG_PROFILE_LOGO_LABEL')}
              hint={tUi('OA_ORG_PROFILE_LOGO_HINT')}>
              <input className={inp} value={form.logo_url ?? ''} onChange={sf('logo_url')}
                placeholder="https://cdn.company.in/logo.png" />
            </Field>
          </div>
          <Field label={tUi('OA_ORG_PROFILE_BRAND_COLOUR_LABEL')} hint={tUi('OA_ORG_PROFILE_BRAND_COLOUR_HINT')}>
            <div className="flex gap-2 items-center">
              <input type="color" value={form.brand_colour || '#6366f1'}
                onChange={sf('brand_colour')}
                className="w-10 h-10 rounded-lg border border-slate-200 cursor-pointer p-0.5" />
              <input className={`${inp} flex-1`} value={form.brand_colour ?? ''}
                onChange={sf('brand_colour')} placeholder="#6366f1" maxLength={7} />
            </div>
          </Field>
          <Field label={tUi('OA_ORG_PROFILE_SUPPORT_EMAIL_LABEL')}
            hint={tUi('OA_ORG_PROFILE_SUPPORT_EMAIL_HINT')}>
            <input type="email" className={inp} value={form.support_email ?? ''}
              onChange={sf('support_email')} placeholder="hr-support@company.in" />
          </Field>
        </div>
      </Section>

      {/* ── Platform-locked ──────────────────────────────────────────────── */}
      <Section icon={Lock} title={tUi('OA_ORG_PROFILE_PLATFORM_CONFIG_TITLE')}
        subtitle={tUi('OA_ORG_PROFILE_PLATFORM_CONFIG_SUB')}>
        <div className="grid grid-cols-2 gap-x-8 gap-y-4 mt-2 opacity-70">
          <ReadOnly label={tUi('OA_ORG_PROFILE_SLA_TIER')} value={p.sla_tier} />
          <ReadOnly label={tUi('OA_ORG_PROFILE_STORAGE_QUOTA')} value={p.storage_quota_gb ? `${p.storage_quota_gb} GB` : undefined} />
          <ReadOnly label={tUi('OA_ORG_PROFILE_CONTRACT_TYPE')} value={p.contract_type} />
          <ReadOnly label={tUi('OA_ORG_PROFILE_ONBOARDING_TIER')} value={p.onboarding_tier} />
          <ReadOnly label={tUi('OA_ORG_PROFILE_NIK_TYPE')} value={p.nik_type} />
          <ReadOnly label={tUi('OA_ORG_PROFILE_SELF_UPLOAD_POLICY')} value={p.self_upload_policy} />
          <ReadOnly label={tUi('OA_ORG_PROFILE_ACCOUNT_MANAGER')} value={p.account_manager} />
          <ReadOnly label={tUi('OA_ORG_PROFILE_MEMBER_SINCE')} value={p.created_at ? new Date(p.created_at).toLocaleDateString('en-IN', { day:'2-digit', month:'long', year:'numeric' }) : undefined} />
        </div>
        <p className="text-xs text-slate-400 mt-4 flex items-center gap-1">
          <AlertTriangle size={11}/> {tUi('OA_ORG_PROFILE_LOCKED_FIELDS_NOTE')}
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
          {saved ? <><Check size={13}/>{tUi('OA_ORG_PROFILE_SAVED')}</> : saveMutation.isPending ? tUi('OA_ORG_PROFILE_SAVING') : tUi('OA_ORG_PROFILE_SAVE_ALL_CHANGES')}
        </button>
      </div>
    </div>
  )
}
