import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import {
  Building2, MapPin, Users, Shield, Briefcase,
  ChevronRight, ChevronLeft, Check, AlertCircle, Info,
} from 'lucide-react'
import { api } from '@/lib/api'
import { tUi } from '@/i18n'

// ── Types ────────────────────────────────────────────────────────────────────

interface Address {
  line1: string; line2: string; city: string
  district: string; state: string; pincode: string
}

interface Contact {
  name: string; designation: string; email: string; mobile: string
}

interface WizardData {
  // Step 1 — Legal Identity
  tenant_name: string; brand_name: string; entity_type: string
  cin: string; gstin: string; pan_entity: string; tan: string
  incorporation_date: string; roc_jurisdiction: string

  // Step 2 — Addresses & Contacts
  reg_address: Address; corp_address_same: boolean; corp_address: Address
  primary_contact: Contact; first_oa_admin_email: string

  // Step 3 — DPDP & Data Protection
  dpo_name: string; dpo_email: string
  grievance_officer_name: string; grievance_officer_email: string
  dpa_accepted: boolean; purpose_limitation_accepted: boolean

  // Step 4 — Technical Configuration
  domain: string; additional_domains: string
  nik_type: string; home_region: string; hrms_system: string
  document_ingestion_method: string; self_upload_policy: string
  office_ip_ranges: string; primary_state: string

  // Step 5 — Workforce & Contract
  industry: string; employee_headcount_band: string
  payroll_frequency: string; fiscal_year_start: string
  push_window_months: number; default_language: string
  storage_quota_gb: number; sla_tier: string
  onboarding_tier: string; contract_type: string; account_manager: string
}

const EMPTY: WizardData = {
  tenant_name: '', brand_name: '', entity_type: '', cin: '', gstin: '',
  pan_entity: '', tan: '', incorporation_date: '', roc_jurisdiction: '',

  reg_address: { line1: '', line2: '', city: '', district: '', state: '', pincode: '' },
  corp_address_same: true,
  corp_address: { line1: '', line2: '', city: '', district: '', state: '', pincode: '' },
  primary_contact: { name: '', designation: '', email: '', mobile: '' },
  first_oa_admin_email: '',

  dpo_name: '', dpo_email: '',
  grievance_officer_name: '', grievance_officer_email: '',
  dpa_accepted: false, purpose_limitation_accepted: false,

  domain: '', additional_domains: '', nik_type: 'PAN', home_region: 'ap-south-1',
  hrms_system: '', document_ingestion_method: 'PORTAL_UPLOAD',
  self_upload_policy: 'ALLOWED_WITH_WARNING', office_ip_ranges: '', primary_state: '',

  industry: '', employee_headcount_band: '', payroll_frequency: 'MONTHLY',
  fiscal_year_start: 'APRIL', push_window_months: 6, default_language: 'en',
  storage_quota_gb: 50, sla_tier: 'STANDARD', onboarding_tier: 'ASSISTED',
  contract_type: 'ANNUAL', account_manager: '',
}

// ── Helper components ─────────────────────────────────────────────────────────

function Field({
  label, required, children, hint,
}: {
  label: string; required?: boolean; children: React.ReactNode; hint?: string
}) {
  return (
    <div className="space-y-1">
      <label className="block text-xs font-medium text-slate-700">
        {label}
        {required && <span className="text-red-500 ml-0.5">*</span>}
      </label>
      {children}
      {hint && <p className="text-xs text-slate-400">{hint}</p>}
    </div>
  )
}

const inp = "w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400 bg-white placeholder:text-slate-300"
const sel = `${inp} cursor-pointer`

function AddressBlock({
  label, value, onChange,
}: {
  label: string; value: Address; onChange: (v: Address) => void
}) {
  const s = (field: keyof Address) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    onChange({ ...value, [field]: e.target.value })

  return (
    <div className="space-y-3">
      <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide">{label}</p>
      <Field label={tUi('OA_ORG_PROFILE_ADDR_LINE1')} required>
        <input className={inp} value={value.line1} onChange={s('line1')} placeholder={tUi('PA_WIZARD_ADDR_LINE1_PLACEHOLDER')} />
      </Field>
      <Field label={tUi('OA_ORG_PROFILE_ADDR_LINE2')}>
        <input className={inp} value={value.line2} onChange={s('line2')} placeholder={tUi('PA_WIZARD_ADDR_LINE2_PLACEHOLDER')} />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label={tUi('OA_ORG_PROFILE_CITY')} required>
          <input className={inp} value={value.city} onChange={s('city')} placeholder="Mumbai" />
        </Field>
        <Field label={tUi('PA_WIZARD_DISTRICT_LABEL')}>
          <input className={inp} value={value.district} onChange={s('district')} placeholder={tUi('PA_WIZARD_DISTRICT_PLACEHOLDER')} />
        </Field>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Field label={tUi('OA_ORG_PROFILE_STATE')} required>
          <select className={sel} value={value.state} onChange={s('state')}>
            <option value="">{tUi('OA_ORG_PROFILE_SELECT_STATE')}</option>
            {STATES.map(st => <option key={st} value={st}>{st}</option>)}
          </select>
        </Field>
        <Field label={tUi('OA_ORG_PROFILE_PINCODE')} required>
          <input className={inp} value={value.pincode} onChange={s('pincode')} placeholder="400001" maxLength={6} />
        </Field>
      </div>
    </div>
  )
}

// ── Constants ─────────────────────────────────────────────────────────────────

const STATES = [
  'Andhra Pradesh','Arunachal Pradesh','Assam','Bihar','Chhattisgarh','Goa','Gujarat',
  'Haryana','Himachal Pradesh','Jharkhand','Karnataka','Kerala','Madhya Pradesh',
  'Maharashtra','Manipur','Meghalaya','Mizoram','Nagaland','Odisha','Punjab','Rajasthan',
  'Sikkim','Tamil Nadu','Telangana','Tripura','Uttar Pradesh','Uttarakhand','West Bengal',
  'Andaman & Nicobar Islands','Chandigarh','Dadra & Nagar Haveli','Daman & Diu',
  'Delhi','Jammu & Kashmir','Ladakh','Lakshadweep','Puducherry',
]

const ENTITY_TYPES = [
  ['PRIVATE_LIMITED','Private Limited (Pvt Ltd)'],
  ['PUBLIC_LIMITED','Public Limited'],
  ['LLP','Limited Liability Partnership (LLP)'],
  ['PARTNERSHIP','Partnership Firm'],
  ['PROPRIETORSHIP','Sole Proprietorship'],
  ['GOVERNMENT_PSU','Government / Public Sector (PSU)'],
  ['SECTION_8_NGO','Section 8 / NGO / Non-Profit'],
  ['FOREIGN_SUBSIDIARY','Foreign Subsidiary'],
  ['OTHER','Other'],
]

const ROC_OPTIONS = [
  'RoC-Ahmedabad','RoC-Bangalore','RoC-Chandigarh','RoC-Chennai','RoC-Cuttack',
  'RoC-Delhi','RoC-Ernakulam','RoC-Gwalior','RoC-Hyderabad','RoC-Jaipur',
  'RoC-Jammu','RoC-Kanpur','RoC-Kolkata','RoC-Mumbai','RoC-Patna','RoC-Pune',
  'RoC-Shillong','RoC-Vijayawada',
]

const INDUSTRIES = [
  'Banking & Financial Services (BFSI)','IT & Software','Manufacturing','Healthcare & Pharma',
  'Retail & FMCG','Telecom','Education & EdTech','Real Estate & Construction',
  'Logistics & Supply Chain','Government / PSU','Media & Entertainment',
  'Automobile & Auto-ancillary','Energy & Utilities','Hospitality & Travel','Other',
]

const HRMS_OPTIONS = [
  'SAP HCM','Darwinbox','GreytHR','Keka','Zoho People','BambooHR',
  'Workday','Oracle HCM','ADP','Freshteam','sumHR','HRMantra',
  'Manual / None','Custom / In-house',
]

function getSteps() {
  return [
    { icon: Building2, label: tUi('OA_ORG_PROFILE_LEGAL_IDENTITY_TITLE') },
    { icon: MapPin,    label: tUi('PA_WIZARD_STEP_ADDRESS') },
    { icon: Shield,    label: tUi('PA_WIZARD_STEP_DPDP') },
    { icon: Users,     label: tUi('PA_WIZARD_STEP_TECH') },
    { icon: Briefcase, label: tUi('PA_WIZARD_STEP_WORKFORCE') },
  ]
}

// ── Main component ────────────────────────────────────────────────────────────

export function CreateTenantWizard() {
  const navigate = useNavigate()
  const [step, setStep] = useState(0)
  const [data, setData] = useState<WizardData>(EMPTY)
  const [errors, setErrors] = useState<string[]>([])
  const STEPS = getSteps()

  const set = (key: keyof WizardData) => (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>
  ) => setData(d => ({ ...d, [key]: e.target.value }))

  const setNum = (key: keyof WizardData) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setData(d => ({ ...d, [key]: Number(e.target.value) }))

  const toggle = (key: keyof WizardData) => () =>
    setData(d => ({ ...d, [key]: !d[key] }))

  const createMutation = useMutation({
    mutationFn: (payload: object) => api.post('/admin/tenants', payload).then(r => r.data),
    onSuccess: () => navigate('/admin/tenants'),
  })

  function validate(s: number): string[] {
    const errs: string[] = []
    if (s === 0) {
      if (!data.tenant_name.trim()) errs.push(tUi('PA_WIZARD_ERR_LEGAL_NAME'))
      if (!data.entity_type)        errs.push(tUi('PA_WIZARD_ERR_ENTITY_TYPE'))
    }
    if (s === 1) {
      if (!data.reg_address.line1.trim())  errs.push(tUi('PA_WIZARD_ERR_ADDR_LINE1'))
      if (!data.reg_address.city.trim())   errs.push(tUi('PA_WIZARD_ERR_ADDR_CITY'))
      if (!data.reg_address.state)         errs.push(tUi('PA_WIZARD_ERR_ADDR_STATE'))
      if (!data.reg_address.pincode.trim()) errs.push(tUi('PA_WIZARD_ERR_ADDR_PINCODE'))
      if (!data.primary_contact.name.trim())  errs.push(tUi('PA_WIZARD_ERR_CONTACT_NAME'))
      if (!data.primary_contact.email.trim()) errs.push(tUi('PA_WIZARD_ERR_CONTACT_EMAIL'))
      if (!data.primary_contact.mobile.trim()) errs.push(tUi('PA_WIZARD_ERR_CONTACT_MOBILE'))
      if (!data.first_oa_admin_email.trim()) errs.push(tUi('PA_WIZARD_ERR_ADMIN_EMAIL'))
    }
    if (s === 2) {
      if (!data.dpo_name.trim())                  errs.push(tUi('PA_WIZARD_ERR_DPO_NAME'))
      if (!data.dpo_email.trim())                 errs.push(tUi('PA_WIZARD_ERR_DPO_EMAIL'))
      if (!data.grievance_officer_name.trim())    errs.push(tUi('PA_WIZARD_ERR_GRIEVANCE_NAME'))
      if (!data.grievance_officer_email.trim())   errs.push(tUi('PA_WIZARD_ERR_GRIEVANCE_EMAIL'))
      if (!data.dpa_accepted)                     errs.push(tUi('PA_WIZARD_ERR_DPA_ACCEPT'))
      if (!data.purpose_limitation_accepted)      errs.push(tUi('PA_WIZARD_ERR_PURPOSE_ACCEPT'))
    }
    if (s === 3) {
      if (!data.domain.trim())        errs.push(tUi('PA_WIZARD_ERR_DOMAIN'))
      if (!data.primary_state)        errs.push(tUi('PA_WIZARD_ERR_PRIMARY_STATE'))
      if (!data.nik_type)             errs.push(tUi('PA_WIZARD_ERR_NIK_TYPE'))
      if (!data.home_region)          errs.push(tUi('PA_WIZARD_ERR_HOME_REGION'))
    }
    if (s === 4) {
      if (!data.employee_headcount_band) errs.push(tUi('PA_WIZARD_ERR_HEADCOUNT'))
      if (!data.storage_quota_gb || data.storage_quota_gb < 1) errs.push(tUi('PA_WIZARD_ERR_STORAGE_QUOTA'))
    }
    return errs
  }

  function next() {
    const errs = validate(step)
    setErrors(errs)
    if (errs.length === 0) setStep(s => s + 1)
  }

  function submit() {
    const allErrs = [0,1,2,3,4].flatMap(validate)
    if (allErrs.length > 0) { setErrors(allErrs); return }

    const payload = {
      tenant_name: data.tenant_name,
      brand_name: data.brand_name || undefined,
      entity_type: data.entity_type || undefined,
      cin: data.cin || undefined,
      gstin: data.gstin || undefined,
      pan_entity: data.pan_entity || undefined,
      tan: data.tan || undefined,
      incorporation_date: data.incorporation_date || undefined,
      roc_jurisdiction: data.roc_jurisdiction || undefined,
      primary_state: data.primary_state,
      reg_address: data.reg_address,
      corp_address: data.corp_address_same ? undefined : data.corp_address,
      primary_contact: data.primary_contact,
      first_oa_admin_email: data.first_oa_admin_email,
      dpo_name: data.dpo_name,
      dpo_email: data.dpo_email,
      grievance_officer_name: data.grievance_officer_name,
      grievance_officer_email: data.grievance_officer_email,
      dpa_accepted: data.dpa_accepted,
      dpa_version: '1.0',
      domain: data.domain,
      additional_domains: data.additional_domains
        ? data.additional_domains.split(',').map((d: string) => d.trim()).filter(Boolean)
        : undefined,
      nik_type: data.nik_type,
      home_region: data.home_region,
      self_upload_policy: data.self_upload_policy,
      document_ingestion_method: data.document_ingestion_method,
      hrms_system: data.hrms_system || undefined,
      industry: data.industry || undefined,
      employee_headcount_band: data.employee_headcount_band,
      payroll_frequency: data.payroll_frequency,
      fiscal_year_start: data.fiscal_year_start,
      push_window_months: data.push_window_months,
      default_language: data.default_language,
      storage_quota_gb: data.storage_quota_gb,
      sla_tier: data.sla_tier,
      onboarding_tier: data.onboarding_tier,
      contract_type: data.contract_type,
      account_manager: data.account_manager || undefined,
    }
    createMutation.mutate(payload)
  }

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <button onClick={() => navigate('/admin/tenants')}
                className="text-xs text-slate-400 hover:text-slate-600 mb-2 flex items-center gap-1">
          {tUi('PA_WIZARD_BACK_TO_DIRECTORY')}
        </button>
        <h1 className="text-xl font-semibold text-slate-800">{tUi('PA_WIZARD_TITLE')}</h1>
        <p className="text-sm text-slate-500 mt-1">
          {tUi('PA_WIZARD_SUB_PREFIX')} <span className="text-red-500 font-medium">*</span>{tUi('PA_WIZARD_SUB_SUFFIX')}
        </p>
      </div>

      {/* Step progress */}
      <div className="flex items-center gap-0">
        {STEPS.map((s, i) => {
          const Icon = s.icon
          const done = i < step; const active = i === step
          return (
            <div key={i} className="flex items-center flex-1 last:flex-none">
              <button
                onClick={() => { if (i < step) { setErrors([]); setStep(i) } }}
                className={`flex flex-col items-center gap-1 min-w-[64px] cursor-default
                  ${active ? 'cursor-default' : i < step ? 'cursor-pointer' : 'cursor-not-allowed'}`}>
                <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-semibold
                  transition-colors ${done ? 'bg-emerald-500 text-white' : active
                    ? 'bg-amber-500 text-white' : 'bg-slate-200 text-slate-400'}`}>
                  {done ? <Check size={14}/> : <Icon size={14}/>}
                </div>
                <span className={`text-[10px] font-medium text-center leading-tight
                  ${active ? 'text-amber-600' : done ? 'text-emerald-600' : 'text-slate-400'}`}>
                  {s.label}
                </span>
              </button>
              {i < STEPS.length - 1 && (
                <div className={`flex-1 h-0.5 mb-5 mx-1 ${i < step ? 'bg-emerald-300' : 'bg-slate-200'}`} />
              )}
            </div>
          )
        })}
      </div>

      {/* Error banner */}
      {errors.length > 0 && (
        <div className="bg-red-50 border border-red-200 rounded-xl px-4 py-3 flex gap-2">
          <AlertCircle size={14} className="text-red-500 flex-shrink-0 mt-0.5" />
          <ul className="text-xs text-red-700 space-y-0.5 list-disc list-inside">
            {errors.map((e, i) => <li key={i}>{e}</li>)}
          </ul>
        </div>
      )}

      {/* Step panels */}
      <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-6 space-y-6">

        {/* ── STEP 0: Legal Identity ──────────────────────────────────────── */}
        {step === 0 && (
          <>
            <StepHeading icon={Building2} title={tUi('OA_ORG_PROFILE_LEGAL_IDENTITY_TITLE')}
              subtitle={tUi('PA_WIZARD_STEP0_SUB')} />

            <div className="grid grid-cols-2 gap-4">
              <div className="col-span-2">
                <Field label={tUi('PA_WIZARD_LEGAL_NAME_LABEL')} required>
                  <input className={inp} value={data.tenant_name} onChange={set('tenant_name')}
                    placeholder={tUi('PA_WIZARD_LEGAL_NAME_PLACEHOLDER')} />
                </Field>
              </div>
              <Field label={tUi('OA_ORG_PROFILE_BRAND_NAME_LABEL')} hint={tUi('PA_WIZARD_BRAND_NAME_HINT')}>
                <input className={inp} value={data.brand_name} onChange={set('brand_name')}
                  placeholder={tUi('PA_WIZARD_BRAND_NAME_PLACEHOLDER')} />
              </Field>
              <Field label={tUi('OA_ORG_PROFILE_ENTITY_TYPE')} required>
                <select className={sel} value={data.entity_type} onChange={set('entity_type')}>
                  <option value="">{tUi('PA_WIZARD_SELECT_ENTITY_TYPE')}</option>
                  {ENTITY_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select>
              </Field>
              <Field label={tUi('OA_ORG_PROFILE_CIN')} hint={tUi('PA_WIZARD_CIN_HINT')}>
                <input className={inp} value={data.cin} onChange={set('cin')}
                  placeholder="U72900MH2010PTC123456" maxLength={21} />
              </Field>
              <Field label={tUi('OA_ORG_PROFILE_GSTIN')} hint={tUi('PA_WIZARD_GSTIN_HINT')}>
                <input className={inp} value={data.gstin} onChange={set('gstin')}
                  placeholder="27AABCT1234A1ZA" maxLength={15} />
              </Field>
              <Field label={tUi('OA_ORG_PROFILE_COMPANY_PAN')} hint={tUi('PA_WIZARD_PAN_HINT')}>
                <input className={inp} value={data.pan_entity} onChange={set('pan_entity')}
                  placeholder="AABCT1234A" maxLength={10} />
              </Field>
              <Field label={tUi('OA_ORG_PROFILE_TAN')} hint={tUi('PA_WIZARD_TAN_HINT')}>
                <input className={inp} value={data.tan} onChange={set('tan')}
                  placeholder="MUMТ12345A" maxLength={10} />
              </Field>
              <Field label={tUi('OA_ORG_PROFILE_INCORPORATION_DATE')}>
                <input type="date" className={inp} value={data.incorporation_date}
                  onChange={set('incorporation_date')} />
              </Field>
              <Field label={tUi('OA_ORG_PROFILE_ROC')} hint={tUi('PA_WIZARD_ROC_HINT')}>
                <select className={sel} value={data.roc_jurisdiction} onChange={set('roc_jurisdiction')}>
                  <option value="">{tUi('PA_WIZARD_SELECT_ROC')}</option>
                  {ROC_OPTIONS.map(r => <option key={r} value={r}>{r}</option>)}
                </select>
              </Field>
            </div>
          </>
        )}

        {/* ── STEP 1: Addresses & Contacts ───────────────────────────────── */}
        {step === 1 && (
          <>
            <StepHeading icon={MapPin} title={tUi('PA_WIZARD_STEP_ADDRESS')}
              subtitle={tUi('PA_WIZARD_STEP1_SUB')} />

            <AddressBlock
              label={tUi('OA_ORG_PROFILE_REG_OFFICE')}
              value={data.reg_address}
              onChange={v => setData(d => ({ ...d, reg_address: v }))}
            />

            <div>
              <label className="flex items-center gap-2 cursor-pointer text-sm">
                <input type="checkbox" checked={data.corp_address_same}
                  onChange={toggle('corp_address_same')}
                  className="rounded border-slate-300 text-amber-500 focus:ring-amber-400" />
                <span className="text-slate-700">{tUi('PA_WIZARD_CORP_SAME_LABEL')}</span>
              </label>
            </div>

            {!data.corp_address_same && (
              <AddressBlock
                label={tUi('OA_ORG_PROFILE_CORP_OFFICE')}
                value={data.corp_address}
                onChange={v => setData(d => ({ ...d, corp_address: v }))}
              />
            )}

            <div className="border-t border-slate-100 pt-4 space-y-3">
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
                {tUi('PA_WIZARD_PRIMARY_CONTACT_LABEL')}
              </p>
              <div className="grid grid-cols-2 gap-4">
                <Field label={tUi('OA_ORG_PROFILE_FULL_NAME')} required>
                  <input className={inp} value={data.primary_contact.name}
                    onChange={e => setData(d => ({ ...d, primary_contact: { ...d.primary_contact, name: e.target.value } }))}
                    placeholder="Priya Sharma" />
                </Field>
                <Field label={tUi('OA_ORG_PROFILE_DESIGNATION')} required>
                  <input className={inp} value={data.primary_contact.designation}
                    onChange={e => setData(d => ({ ...d, primary_contact: { ...d.primary_contact, designation: e.target.value } }))}
                    placeholder={tUi('PA_WIZARD_DESIGNATION_PLACEHOLDER')} />
                </Field>
                <Field label={tUi('OA_ORG_PROFILE_WORK_EMAIL')} required>
                  <input type="email" className={inp} value={data.primary_contact.email}
                    onChange={e => setData(d => ({ ...d, primary_contact: { ...d.primary_contact, email: e.target.value } }))}
                    placeholder="priya@company.in" />
                </Field>
                <Field label={tUi('OA_ORG_PROFILE_MOBILE')} required>
                  <input className={inp} value={data.primary_contact.mobile}
                    onChange={e => setData(d => ({ ...d, primary_contact: { ...d.primary_contact, mobile: e.target.value } }))}
                    placeholder="+91 98765 43210" />
                </Field>
              </div>
            </div>

            <div className="border-t border-slate-100 pt-4">
              <Field label={tUi('PA_WIZARD_ADMIN_EMAIL_LABEL')} required
                hint={tUi('PA_WIZARD_ADMIN_EMAIL_HINT')}>
                <input type="email" className={inp} value={data.first_oa_admin_email}
                  onChange={set('first_oa_admin_email')}
                  placeholder="admin@company.in" />
              </Field>
            </div>
          </>
        )}

        {/* ── STEP 2: Data Protection (DPDP) ─────────────────────────────── */}
        {step === 2 && (
          <>
            <StepHeading icon={Shield} title={tUi('PA_WIZARD_STEP2_TITLE')}
              subtitle={tUi('PA_WIZARD_STEP2_SUB')} />

            <div className="bg-sky-50 border border-sky-200 rounded-xl px-4 py-3 flex gap-2">
              <Info size={14} className="text-sky-600 flex-shrink-0 mt-0.5" />
              <p className="text-xs text-sky-700">
                {tUi('PA_WIZARD_DPDP_INFO')}
              </p>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <Field label={tUi('PA_WIZARD_DPO_NAME_LABEL')} required>
                <input className={inp} value={data.dpo_name} onChange={set('dpo_name')}
                  placeholder={tUi('OA_ORG_PROFILE_FULL_NAME_PLACEHOLDER')} />
              </Field>
              <Field label={tUi('OA_ORG_PROFILE_DPO_EMAIL')} required>
                <input type="email" className={inp} value={data.dpo_email} onChange={set('dpo_email')}
                  placeholder="dpo@company.in" />
              </Field>
              <Field label={tUi('OA_ORG_PROFILE_GRIEVANCE_NAME')} required
                hint={tUi('PA_WIZARD_GRIEVANCE_NAME_HINT')}>
                <input className={inp} value={data.grievance_officer_name}
                  onChange={set('grievance_officer_name')} placeholder={tUi('OA_ORG_PROFILE_FULL_NAME_PLACEHOLDER')} />
              </Field>
              <Field label={tUi('OA_ORG_PROFILE_GRIEVANCE_EMAIL')} required>
                <input type="email" className={inp} value={data.grievance_officer_email}
                  onChange={set('grievance_officer_email')} placeholder="grievance@company.in" />
              </Field>
            </div>

            <div className="border-t border-slate-100 pt-4 space-y-3">
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
                {tUi('PA_WIZARD_AGREEMENTS_LABEL')}
              </p>

              <label className={`flex items-start gap-3 p-4 border rounded-xl cursor-pointer transition-colors
                ${data.dpa_accepted ? 'border-emerald-400 bg-emerald-50' : 'border-slate-200 hover:border-slate-300'}`}>
                <input type="checkbox" checked={data.dpa_accepted} onChange={toggle('dpa_accepted')}
                  className="mt-0.5 rounded border-slate-300 text-emerald-500 focus:ring-emerald-400" />
                <div>
                  <p className="text-sm font-medium text-slate-800">
                    {tUi('PA_WIZARD_DPA_TITLE')} <span className="text-red-500">*</span>
                  </p>
                  <p className="text-xs text-slate-500 mt-0.5">
                    {tUi('PA_WIZARD_DPA_BODY')}
                  </p>
                </div>
              </label>

              <label className={`flex items-start gap-3 p-4 border rounded-xl cursor-pointer transition-colors
                ${data.purpose_limitation_accepted ? 'border-emerald-400 bg-emerald-50' : 'border-slate-200 hover:border-slate-300'}`}>
                <input type="checkbox" checked={data.purpose_limitation_accepted}
                  onChange={toggle('purpose_limitation_accepted')}
                  className="mt-0.5 rounded border-slate-300 text-emerald-500 focus:ring-emerald-400" />
                <div>
                  <p className="text-sm font-medium text-slate-800">
                    {tUi('PA_WIZARD_PURPOSE_TITLE')} <span className="text-red-500">*</span>
                  </p>
                  <p className="text-xs text-slate-500 mt-0.5">
                    {tUi('PA_WIZARD_PURPOSE_BODY')}
                  </p>
                </div>
              </label>
            </div>
          </>
        )}

        {/* ── STEP 3: Technical Configuration ─────────────────────────────── */}
        {step === 3 && (
          <>
            <StepHeading icon={Users} title={tUi('PA_WIZARD_STEP_TECH')}
              subtitle={tUi('PA_WIZARD_STEP3_SUB')} />

            <div className="grid grid-cols-2 gap-4">
              <Field label={tUi('PA_WIZARD_DOMAIN_LABEL')} required hint={tUi('PA_WIZARD_DOMAIN_HINT')}>
                <input className={inp} value={data.domain} onChange={set('domain')}
                  placeholder="company.in" />
              </Field>
              <Field label={tUi('PA_WIZARD_ADDL_DOMAINS_LABEL')}
                hint={tUi('PA_WIZARD_ADDL_DOMAINS_HINT')}>
                <input className={inp} value={data.additional_domains}
                  onChange={set('additional_domains')}
                  placeholder="subsidiary.in, group.com" />
              </Field>
              <Field label={tUi('PA_WIZARD_PRIMARY_STATE_LABEL')} required hint={tUi('PA_WIZARD_PRIMARY_STATE_HINT')}>
                <select className={sel} value={data.primary_state} onChange={set('primary_state')}>
                  <option value="">{tUi('OA_ORG_PROFILE_SELECT_STATE')}</option>
                  {STATES.map(st => <option key={st} value={st}>{st}</option>)}
                </select>
              </Field>
              <Field label={tUi('PA_WIZARD_NIK_LABEL')} required
                hint={tUi('PA_WIZARD_NIK_HINT')}>
                <select className={sel} value={data.nik_type} onChange={set('nik_type')}>
                  <option value="PAN">{tUi('PA_WIZARD_NIK_PAN_OPTION')}</option>
                  <option value="PASSPORT">{tUi('PA_WIZARD_NIK_PASSPORT_OPTION')}</option>
                </select>
              </Field>
              <Field label={tUi('PA_WIZARD_REGION_LABEL')} required
                hint={tUi('PA_WIZARD_REGION_HINT')}>
                <select className={sel} value={data.home_region} onChange={set('home_region')}>
                  <option value="ap-south-1">{tUi('PA_WIZARD_REGION_MUMBAI_OPTION')}</option>
                  <option value="ap-south-2">{tUi('PA_WIZARD_REGION_HYDERABAD_OPTION')}</option>
                </select>
              </Field>
              <Field label={tUi('OA_ORG_PROFILE_HRMS_PLATFORM_LABEL')}>
                <select className={sel} value={data.hrms_system} onChange={set('hrms_system')}>
                  <option value="">{tUi('PA_WIZARD_HRMS_NOT_INTEGRATED')}</option>
                  {HRMS_OPTIONS.map(h => <option key={h} value={h}>{h}</option>)}
                </select>
              </Field>
              <Field label={tUi('OA_ORG_PROFILE_INGESTION_METHOD_LABEL')} required>
                <select className={sel} value={data.document_ingestion_method}
                  onChange={set('document_ingestion_method')}>
                  <option value="PORTAL_UPLOAD">{tUi('PA_WIZARD_PORTAL_UPLOAD_OPTION')}</option>
                  <option value="HRMS_API">{tUi('PA_WIZARD_HRMS_API_OPTION')}</option>
                  <option value="BOTH">{tUi('PA_WIZARD_BOTH_OPTION')}</option>
                </select>
              </Field>
              <Field label={tUi('PA_WIZARD_SELF_UPLOAD_LABEL')} required
                hint={tUi('PA_WIZARD_SELF_UPLOAD_HINT')}>
                <select className={sel} value={data.self_upload_policy}
                  onChange={set('self_upload_policy')}>
                  <option value="ALLOWED">{tUi('PA_WIZARD_SELF_UPLOAD_ALLOWED')}</option>
                  <option value="ALLOWED_WITH_WARNING">{tUi('PA_WIZARD_SELF_UPLOAD_WARNING')}</option>
                  <option value="BLOCKED_ON_OFFICE_NETWORK">{tUi('PA_WIZARD_SELF_UPLOAD_BLOCKED_OFFICE')}</option>
                  <option value="BLOCKED_ENTIRELY">{tUi('PA_WIZARD_SELF_UPLOAD_BLOCKED_ALL')}</option>
                </select>
              </Field>
              <div className="col-span-2">
                <Field label={tUi('PA_WIZARD_IP_RANGES_LABEL')}
                  hint={tUi('PA_WIZARD_IP_RANGES_HINT')}>
                  <input className={inp} value={data.office_ip_ranges}
                    onChange={set('office_ip_ranges')}
                    placeholder="203.0.113.0/24, 198.51.100.0/24" />
                </Field>
              </div>
            </div>
          </>
        )}

        {/* ── STEP 4: Workforce & Contract ─────────────────────────────────── */}
        {step === 4 && (
          <>
            <StepHeading icon={Briefcase} title={tUi('PA_WIZARD_STEP_WORKFORCE')}
              subtitle={tUi('PA_WIZARD_STEP4_SUB')} />

            <div className="grid grid-cols-2 gap-4">
              <Field label={tUi('OA_ORG_PROFILE_INDUSTRY_LABEL')}>
                <select className={sel} value={data.industry} onChange={set('industry')}>
                  <option value="">{tUi('OA_ORG_PROFILE_SELECT_INDUSTRY')}</option>
                  {INDUSTRIES.map(i => <option key={i} value={i}>{i}</option>)}
                </select>
              </Field>
              <Field label={tUi('OA_ORG_PROFILE_HEADCOUNT_LABEL')} required>
                <select className={sel} value={data.employee_headcount_band}
                  onChange={set('employee_headcount_band')}>
                  <option value="">{tUi('OA_ORG_PROFILE_SELECT_BAND')}</option>
                  {['1-50','51-200','201-500','501-2000','2001-10000','10000+'].map(b =>
                    <option key={b} value={b}>{b} {tUi('OA_ORG_PROFILE_EMPLOYEES_SUFFIX')}</option>
                  )}
                </select>
              </Field>
              <Field label={tUi('OA_ORG_PROFILE_PAYROLL_FREQ_LABEL')}>
                <select className={sel} value={data.payroll_frequency}
                  onChange={set('payroll_frequency')}>
                  <option value="MONTHLY">{tUi('PA_WIZARD_PAYROLL_MONTHLY_STD')}</option>
                  <option value="BI_MONTHLY">{tUi('OA_ORG_PROFILE_BI_MONTHLY')}</option>
                  <option value="WEEKLY">{tUi('OA_ORG_PROFILE_WEEKLY')}</option>
                </select>
              </Field>
              <Field label={tUi('OA_ORG_PROFILE_FISCAL_YEAR_LABEL')}>
                <select className={sel} value={data.fiscal_year_start}
                  onChange={set('fiscal_year_start')}>
                  <option value="APRIL">{tUi('OA_ORG_PROFILE_APRIL_STANDARD')}</option>
                  <option value="JANUARY">{tUi('PA_WIZARD_FISCAL_JAN_FOREIGN')}</option>
                  <option value="OTHER">{tUi('OA_ORG_PROFILE_OTHER')}</option>
                </select>
              </Field>
              <Field label={tUi('PA_WIZARD_PUSH_WINDOW_LABEL')}
                hint={tUi('PA_WIZARD_PUSH_WINDOW_HINT')}>
                <select className={sel} value={String(data.push_window_months)}
                  onChange={e => setData(d => ({ ...d, push_window_months: Number(e.target.value) }))}>
                  <option value="3">{tUi('OA_ORG_PROFILE_MONTHS_3')}</option>
                  <option value="6">{tUi('OA_ORG_PROFILE_MONTHS_6_DEFAULT')}</option>
                  <option value="9">{tUi('OA_ORG_PROFILE_MONTHS_9')}</option>
                  <option value="12">{tUi('OA_ORG_PROFILE_MONTHS_12')}</option>
                </select>
              </Field>
              <Field label={tUi('OA_ORG_PROFILE_DEFAULT_LANG_LABEL')}>
                <select className={sel} value={data.default_language}
                  onChange={set('default_language')}>
                  {[['en','English'],['hi','Hindi'],['mr','Marathi'],['ta','Tamil'],
                    ['te','Telugu'],['kn','Kannada'],['bn','Bengali'],['gu','Gujarati']
                  ].map(([v,l]) => <option key={v} value={v}>{l}</option>)}
                </select>
              </Field>
            </div>

            <div className="border-t border-slate-100 pt-4 space-y-4">
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
                {tUi('PA_WIZARD_STORAGE_SLA_LABEL')}
              </p>
              <div className="grid grid-cols-2 gap-4">
                <Field label={tUi('OA_ORG_PROFILE_STORAGE_QUOTA')} required>
                  <input type="number" className={inp} value={data.storage_quota_gb}
                    onChange={setNum('storage_quota_gb')} min={10} max={10000} step={10} />
                </Field>
                <Field label={tUi('OA_ORG_PROFILE_SLA_TIER')} required hint={tUi('PA_WIZARD_SLA_TIER_HINT')}>
                  <select className={sel} value={data.sla_tier} onChange={set('sla_tier')}>
                    <option value="STANDARD">{tUi('PA_WIZARD_SLA_STANDARD')}</option>
                    <option value="PRIORITY">{tUi('PA_WIZARD_SLA_PRIORITY')}</option>
                    <option value="ENTERPRISE">{tUi('PA_WIZARD_SLA_ENTERPRISE')}</option>
                  </select>
                </Field>
                <Field label={tUi('OA_ORG_PROFILE_ONBOARDING_TIER')}>
                  <select className={sel} value={data.onboarding_tier}
                    onChange={set('onboarding_tier')}>
                    <option value="SELF_SERVICE">{tUi('PA_WIZARD_ONBOARD_SELF_SERVICE')}</option>
                    <option value="ASSISTED">{tUi('PA_WIZARD_ONBOARD_ASSISTED')}</option>
                    <option value="ENTERPRISE">{tUi('PA_WIZARD_ONBOARD_ENTERPRISE')}</option>
                  </select>
                </Field>
                <Field label={tUi('OA_ORG_PROFILE_CONTRACT_TYPE')}>
                  <select className={sel} value={data.contract_type}
                    onChange={set('contract_type')}>
                    <option value="MONTHLY">{tUi('OA_ORG_PROFILE_MONTHLY')}</option>
                    <option value="ANNUAL">{tUi('PA_WIZARD_CONTRACT_ANNUAL')}</option>
                    <option value="MULTI_YEAR">{tUi('PA_WIZARD_CONTRACT_MULTI_YEAR')}</option>
                  </select>
                </Field>
                <div className="col-span-2">
                  <Field label={tUi('OA_ORG_PROFILE_ACCOUNT_MANAGER')}
                    hint={tUi('PA_WIZARD_ACCOUNT_MANAGER_HINT')}>
                    <input className={inp} value={data.account_manager}
                      onChange={set('account_manager')} placeholder={tUi('PA_WIZARD_ACCOUNT_MANAGER_PLACEHOLDER')} />
                  </Field>
                </div>
              </div>
            </div>

            {/* Review summary */}
            <div className="border-t border-slate-100 pt-4 space-y-2">
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide">{tUi('PA_WIZARD_REVIEW_SUMMARY_TITLE')}</p>
              <div className="bg-slate-50 rounded-xl p-4 text-xs text-slate-600 space-y-1">
                <p><span className="font-medium text-slate-800">{tUi('PA_WIZARD_REVIEW_ORG_LABEL')}</span> {data.tenant_name || '—'} ({data.entity_type || '—'})</p>
                <p><span className="font-medium text-slate-800">{tUi('PA_WIZARD_REVIEW_DOMAIN_LABEL')}</span> {data.domain || '—'} · {tUi('PA_WIZARD_REVIEW_REGION_LABEL')} {data.home_region}</p>
                <p><span className="font-medium text-slate-800">{tUi('PA_WIZARD_REVIEW_STATE_LABEL')}</span> {data.primary_state || '—'} · {tUi('PA_WIZARD_REVIEW_NIK_LABEL')} {data.nik_type}</p>
                <p><span className="font-medium text-slate-800">{tUi('PA_WIZARD_REVIEW_ADMIN_LABEL')}</span> {data.first_oa_admin_email || '—'}</p>
                <p><span className="font-medium text-slate-800">{tUi('PA_WIZARD_REVIEW_DPO_LABEL')}</span> {data.dpo_name || '—'} · {tUi('PA_WIZARD_REVIEW_DPA_LABEL')} {data.dpa_accepted ? tUi('PA_WIZARD_DPA_ACCEPTED_MARK') : tUi('PA_WIZARD_DPA_PENDING_MARK')}</p>
                <p><span className="font-medium text-slate-800">{tUi('PA_WIZARD_REVIEW_STORAGE_LABEL')}</span> {data.storage_quota_gb} GB · {tUi('PA_WIZARD_REVIEW_SLA_LABEL')} {data.sla_tier}</p>
              </div>
            </div>
          </>
        )}
      </div>

      {/* Navigation */}
      <div className="flex items-center justify-between">
        <button
          onClick={() => { setErrors([]); setStep(s => Math.max(0, s - 1)) }}
          disabled={step === 0}
          className="flex items-center gap-1 px-4 py-2 text-sm font-medium text-slate-600
                     border border-slate-200 rounded-lg hover:bg-slate-50 disabled:opacity-40">
          <ChevronLeft size={14}/> {tUi('PA_WIZARD_BACK_BTN')}
        </button>

        {step < 4 ? (
          <button onClick={next}
            className="flex items-center gap-1 px-5 py-2 text-sm font-semibold text-white
                       bg-amber-500 rounded-lg hover:bg-amber-600">
            {tUi('PA_WIZARD_NEXT_BTN')} <ChevronRight size={14}/>
          </button>
        ) : (
          <button onClick={submit}
            disabled={createMutation.isPending}
            className="flex items-center gap-2 px-6 py-2 text-sm font-semibold text-white
                       bg-emerald-600 rounded-lg hover:bg-emerald-700 disabled:opacity-50">
            <Check size={14}/>
            {createMutation.isPending ? tUi('PA_WIZARD_CREATING') : tUi('PA_WIZARD_CREATE_BTN')}
          </button>
        )}
      </div>

      {createMutation.isError && (
        <p className="text-xs text-red-600 text-center">
          {tUi('PA_WIZARD_CREATE_FAILED')}
        </p>
      )}
    </div>
  )
}

function StepHeading({ icon: Icon, title, subtitle }: {
  icon: React.ElementType; title: string; subtitle: string
}) {
  return (
    <div className="flex items-start gap-3 pb-2 border-b border-slate-100">
      <div className="w-9 h-9 rounded-xl bg-amber-100 flex items-center justify-center flex-shrink-0">
        <Icon size={16} className="text-amber-600" />
      </div>
      <div>
        <h2 className="font-semibold text-slate-800">{title}</h2>
        <p className="text-xs text-slate-500 mt-0.5">{subtitle}</p>
      </div>
    </div>
  )
}
