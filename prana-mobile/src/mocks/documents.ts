export type SourceType = 'EMPLOYER_PUSH' | 'EMPLOYEE_SELF_UPLOAD' | 'EMAIL_FETCH' | 'THIRD_PARTY_VERIFIED';
export type IconType = 'salary' | 'form16' | 'invest' | 'letter' | 'tax' | 'bank';
// must match keys of docIconGradients in tokens.ts

export interface Document {
  id: string;
  doc_type: string;
  title: string;
  source_type: SourceType;
  issuer: string;
  employer_id: string | null; // links to mockCareer employer id
  received_at: string;
  icon_type: IconType;
  icon_emoji: string;
}

export const mockDocuments: Document[] = [
  // ── NPCI Salary Slips ──────────────────────────────────────────
  { id: 'n_sal_01', doc_type: 'SALARY_SLIP', title: 'Salary Slip — May 2026', source_type: 'EMPLOYER_PUSH', issuer: 'NPCI', employer_id: 'e1', received_at: '2026-06-02', icon_type: 'salary', icon_emoji: '💰' },
  { id: 'n_sal_02', doc_type: 'SALARY_SLIP', title: 'Salary Slip — Apr 2026', source_type: 'EMPLOYER_PUSH', issuer: 'NPCI', employer_id: 'e1', received_at: '2026-05-03', icon_type: 'salary', icon_emoji: '💰' },
  { id: 'n_sal_03', doc_type: 'SALARY_SLIP', title: 'Salary Slip — Mar 2026', source_type: 'EMPLOYER_PUSH', issuer: 'NPCI', employer_id: 'e1', received_at: '2026-04-02', icon_type: 'salary', icon_emoji: '💰' },
  { id: 'n_sal_04', doc_type: 'SALARY_SLIP', title: 'Salary Slip — Feb 2026', source_type: 'EMPLOYER_PUSH', issuer: 'NPCI', employer_id: 'e1', received_at: '2026-03-03', icon_type: 'salary', icon_emoji: '💰' },
  { id: 'n_sal_05', doc_type: 'SALARY_SLIP', title: 'Salary Slip — Jan 2026', source_type: 'EMPLOYER_PUSH', issuer: 'NPCI', employer_id: 'e1', received_at: '2026-02-03', icon_type: 'salary', icon_emoji: '💰' },
  { id: 'n_sal_06', doc_type: 'SALARY_SLIP', title: 'Salary Slip — Dec 2025', source_type: 'EMPLOYER_PUSH', issuer: 'NPCI', employer_id: 'e1', received_at: '2026-01-02', icon_type: 'salary', icon_emoji: '💰' },
  { id: 'n_sal_07', doc_type: 'SALARY_SLIP', title: 'Salary Slip — Nov 2025', source_type: 'EMPLOYER_PUSH', issuer: 'NPCI', employer_id: 'e1', received_at: '2025-12-03', icon_type: 'salary', icon_emoji: '💰' },
  { id: 'n_sal_08', doc_type: 'SALARY_SLIP', title: 'Salary Slip — Oct 2025', source_type: 'EMPLOYER_PUSH', issuer: 'NPCI', employer_id: 'e1', received_at: '2025-11-03', icon_type: 'salary', icon_emoji: '💰' },
  { id: 'n_sal_09', doc_type: 'SALARY_SLIP', title: 'Salary Slip — Sep 2025', source_type: 'EMPLOYER_PUSH', issuer: 'NPCI', employer_id: 'e1', received_at: '2025-10-02', icon_type: 'salary', icon_emoji: '💰' },
  { id: 'n_sal_10', doc_type: 'SALARY_SLIP', title: 'Salary Slip — Aug 2025', source_type: 'EMPLOYER_PUSH', issuer: 'NPCI', employer_id: 'e1', received_at: '2025-09-02', icon_type: 'salary', icon_emoji: '💰' },
  { id: 'n_sal_11', doc_type: 'SALARY_SLIP', title: 'Salary Slip — Jul 2025', source_type: 'EMPLOYER_PUSH', issuer: 'NPCI', employer_id: 'e1', received_at: '2025-08-02', icon_type: 'salary', icon_emoji: '💰' },
  { id: 'n_sal_12', doc_type: 'SALARY_SLIP', title: 'Salary Slip — Jun 2025', source_type: 'EMPLOYER_PUSH', issuer: 'NPCI', employer_id: 'e1', received_at: '2025-07-02', icon_type: 'salary', icon_emoji: '💰' },

  // ── NPCI Form 16 ───────────────────────────────────────────────
  { id: 'n_f16_01', doc_type: 'FORM_16', title: 'Form 16 — FY 2025-26', source_type: 'EMPLOYER_PUSH', issuer: 'NPCI', employer_id: 'e1', received_at: '2026-05-28', icon_type: 'form16', icon_emoji: '🧾' },
  { id: 'n_f16_02', doc_type: 'FORM_16', title: 'Form 16 — FY 2024-25', source_type: 'EMPLOYER_PUSH', issuer: 'NPCI', employer_id: 'e1', received_at: '2025-05-30', icon_type: 'form16', icon_emoji: '🧾' },
  { id: 'n_f16_03', doc_type: 'FORM_16', title: 'Form 16 — FY 2023-24', source_type: 'EMPLOYER_PUSH', issuer: 'NPCI', employer_id: 'e1', received_at: '2024-06-01', icon_type: 'form16', icon_emoji: '🧾' },
  { id: 'n_f16_04', doc_type: 'FORM_16', title: 'Form 16 — FY 2022-23', source_type: 'EMPLOYER_PUSH', issuer: 'NPCI', employer_id: 'e1', received_at: '2023-05-29', icon_type: 'form16', icon_emoji: '🧾' },

  // ── NPCI Letters ───────────────────────────────────────────────
  { id: 'n_off_01', doc_type: 'OFFER_LETTER', title: 'Offer Letter — NPCI', source_type: 'EMPLOYER_PUSH', issuer: 'NPCI', employer_id: 'e1', received_at: '2022-03-10', icon_type: 'letter', icon_emoji: '📩' },
  { id: 'n_jn_01',  doc_type: 'JOINING_LETTER', title: 'Joining Letter — NPCI', source_type: 'EMPLOYER_PUSH', issuer: 'NPCI', employer_id: 'e1', received_at: '2022-04-01', icon_type: 'letter', icon_emoji: '📋' },
  { id: 'n_apl_01', doc_type: 'APPRAISAL_LETTER', title: 'Appraisal Letter — FY 2024-25', source_type: 'EMPLOYER_PUSH', issuer: 'NPCI', employer_id: 'e1', received_at: '2025-04-01', icon_type: 'letter', icon_emoji: '📈' },
  { id: 'n_apl_02', doc_type: 'APPRAISAL_LETTER', title: 'Appraisal Letter — FY 2023-24', source_type: 'EMPLOYER_PUSH', issuer: 'NPCI', employer_id: 'e1', received_at: '2024-04-01', icon_type: 'letter', icon_emoji: '📈' },
  { id: 'n_apl_03', doc_type: 'APPRAISAL_LETTER', title: 'Appraisal Letter — FY 2022-23', source_type: 'EMPLOYER_PUSH', issuer: 'NPCI', employer_id: 'e1', received_at: '2023-04-01', icon_type: 'letter', icon_emoji: '📈' },
  { id: 'n_prm_01', doc_type: 'PROMOTION_LETTER', title: 'Promotion Letter — Senior Engineer', source_type: 'EMPLOYER_PUSH', issuer: 'NPCI', employer_id: 'e1', received_at: '2024-01-15', icon_type: 'letter', icon_emoji: '🎖' },
  { id: 'n_bon_01', doc_type: 'BONUS_LETTER', title: 'Performance Bonus — FY 2024-25', source_type: 'EMPLOYER_PUSH', issuer: 'NPCI', employer_id: 'e1', received_at: '2025-04-10', icon_type: 'letter', icon_emoji: '🎁' },
  { id: 'n_bon_02', doc_type: 'BONUS_LETTER', title: 'Performance Bonus — FY 2023-24', source_type: 'EMPLOYER_PUSH', issuer: 'NPCI', employer_id: 'e1', received_at: '2024-04-08', icon_type: 'letter', icon_emoji: '🎁' },
  { id: 'n_bon_03', doc_type: 'BONUS_LETTER', title: 'Performance Bonus — FY 2022-23', source_type: 'EMPLOYER_PUSH', issuer: 'NPCI', employer_id: 'e1', received_at: '2023-04-12', icon_type: 'letter', icon_emoji: '🎁' },

  // ── Infosys Salary Slips ───────────────────────────────────────
  { id: 'i_sal_01', doc_type: 'SALARY_SLIP', title: 'Salary Slip — Mar 2022', source_type: 'EMPLOYER_PUSH', issuer: 'Infosys', employer_id: 'e2', received_at: '2022-04-01', icon_type: 'salary', icon_emoji: '💰' },
  { id: 'i_sal_02', doc_type: 'SALARY_SLIP', title: 'Salary Slip — Feb 2022', source_type: 'EMPLOYER_PUSH', issuer: 'Infosys', employer_id: 'e2', received_at: '2022-03-03', icon_type: 'salary', icon_emoji: '💰' },
  { id: 'i_sal_03', doc_type: 'SALARY_SLIP', title: 'Salary Slip — Jan 2022', source_type: 'EMPLOYER_PUSH', issuer: 'Infosys', employer_id: 'e2', received_at: '2022-02-03', icon_type: 'salary', icon_emoji: '💰' },
  { id: 'i_sal_04', doc_type: 'SALARY_SLIP', title: 'Salary Slip — Dec 2021', source_type: 'EMPLOYER_PUSH', issuer: 'Infosys', employer_id: 'e2', received_at: '2022-01-03', icon_type: 'salary', icon_emoji: '💰' },
  { id: 'i_sal_05', doc_type: 'SALARY_SLIP', title: 'Salary Slip — Nov 2021', source_type: 'EMPLOYER_PUSH', issuer: 'Infosys', employer_id: 'e2', received_at: '2021-12-03', icon_type: 'salary', icon_emoji: '💰' },
  { id: 'i_sal_06', doc_type: 'SALARY_SLIP', title: 'Salary Slip — Oct 2021', source_type: 'EMPLOYER_PUSH', issuer: 'Infosys', employer_id: 'e2', received_at: '2021-11-02', icon_type: 'salary', icon_emoji: '💰' },
  { id: 'i_sal_07', doc_type: 'SALARY_SLIP', title: 'Salary Slip — Sep 2021', source_type: 'EMPLOYER_PUSH', issuer: 'Infosys', employer_id: 'e2', received_at: '2021-10-02', icon_type: 'salary', icon_emoji: '💰' },
  { id: 'i_sal_08', doc_type: 'SALARY_SLIP', title: 'Salary Slip — Aug 2021', source_type: 'EMPLOYER_PUSH', issuer: 'Infosys', employer_id: 'e2', received_at: '2021-09-02', icon_type: 'salary', icon_emoji: '💰' },
  { id: 'i_sal_09', doc_type: 'SALARY_SLIP', title: 'Salary Slip — Jul 2021', source_type: 'EMPLOYER_PUSH', issuer: 'Infosys', employer_id: 'e2', received_at: '2021-08-02', icon_type: 'salary', icon_emoji: '💰' },
  { id: 'i_sal_10', doc_type: 'SALARY_SLIP', title: 'Salary Slip — Jun 2021', source_type: 'EMPLOYER_PUSH', issuer: 'Infosys', employer_id: 'e2', received_at: '2021-07-02', icon_type: 'salary', icon_emoji: '💰' },
  { id: 'i_sal_11', doc_type: 'SALARY_SLIP', title: 'Salary Slip — Mar 2020', source_type: 'EMPLOYER_PUSH', issuer: 'Infosys', employer_id: 'e2', received_at: '2020-04-02', icon_type: 'salary', icon_emoji: '💰' },
  { id: 'i_sal_12', doc_type: 'SALARY_SLIP', title: 'Salary Slip — Mar 2019', source_type: 'EMPLOYER_PUSH', issuer: 'Infosys', employer_id: 'e2', received_at: '2019-04-02', icon_type: 'salary', icon_emoji: '💰' },

  // ── Infosys Form 16 ────────────────────────────────────────────
  { id: 'i_f16_01', doc_type: 'FORM_16', title: 'Form 16 — FY 2021-22', source_type: 'EMPLOYER_PUSH', issuer: 'Infosys', employer_id: 'e2', received_at: '2022-05-28', icon_type: 'form16', icon_emoji: '🧾' },
  { id: 'i_f16_02', doc_type: 'FORM_16', title: 'Form 16 — FY 2020-21', source_type: 'EMPLOYER_PUSH', issuer: 'Infosys', employer_id: 'e2', received_at: '2021-06-02', icon_type: 'form16', icon_emoji: '🧾' },
  { id: 'i_f16_03', doc_type: 'FORM_16', title: 'Form 16 — FY 2019-20', source_type: 'EMPLOYER_PUSH', issuer: 'Infosys', employer_id: 'e2', received_at: '2020-06-01', icon_type: 'form16', icon_emoji: '🧾' },

  // ── Infosys Letters ────────────────────────────────────────────
  { id: 'i_off_01', doc_type: 'OFFER_LETTER', title: 'Offer Letter — Infosys', source_type: 'EMPLOYER_PUSH', issuer: 'Infosys', employer_id: 'e2', received_at: '2019-02-10', icon_type: 'letter', icon_emoji: '📩' },
  { id: 'i_jn_01',  doc_type: 'JOINING_LETTER', title: 'Joining Letter — Infosys', source_type: 'EMPLOYER_PUSH', issuer: 'Infosys', employer_id: 'e2', received_at: '2019-03-01', icon_type: 'letter', icon_emoji: '📋' },
  { id: 'i_apl_01', doc_type: 'APPRAISAL_LETTER', title: 'Appraisal Letter — FY 2021-22', source_type: 'EMPLOYER_PUSH', issuer: 'Infosys', employer_id: 'e2', received_at: '2022-03-28', icon_type: 'letter', icon_emoji: '📈' },
  { id: 'i_apl_02', doc_type: 'APPRAISAL_LETTER', title: 'Appraisal Letter — FY 2020-21', source_type: 'EMPLOYER_PUSH', issuer: 'Infosys', employer_id: 'e2', received_at: '2021-03-30', icon_type: 'letter', icon_emoji: '📈' },
  { id: 'i_rel_01', doc_type: 'RELIEVING_LETTER', title: 'Relieving Letter — Infosys', source_type: 'EMPLOYER_PUSH', issuer: 'Infosys', employer_id: 'e2', received_at: '2022-03-31', icon_type: 'letter', icon_emoji: '🚪' },
  { id: 'i_exp_01', doc_type: 'EXPERIENCE_LETTER', title: 'Experience Letter — Infosys (3 yrs)', source_type: 'EMPLOYER_PUSH', issuer: 'Infosys', employer_id: 'e2', received_at: '2022-03-31', icon_type: 'letter', icon_emoji: '📜' },
  { id: 'i_bon_01', doc_type: 'BONUS_LETTER', title: 'Performance Bonus — FY 2021-22', source_type: 'EMPLOYER_PUSH', issuer: 'Infosys', employer_id: 'e2', received_at: '2022-03-01', icon_type: 'letter', icon_emoji: '🎁' },
  { id: 'i_bon_02', doc_type: 'BONUS_LETTER', title: 'Performance Bonus — FY 2020-21', source_type: 'EMPLOYER_PUSH', issuer: 'Infosys', employer_id: 'e2', received_at: '2021-03-15', icon_type: 'letter', icon_emoji: '🎁' },

  // ── Self-uploaded documents ────────────────────────────────────
  { id: 's_inv_01', doc_type: 'INVESTMENT_PROOF', title: 'Investment Proof — LIC FY 2025-26', source_type: 'EMPLOYEE_SELF_UPLOAD', issuer: 'Self', employer_id: null, received_at: '2026-01-15', icon_type: 'invest', icon_emoji: '📊' },
  { id: 's_inv_02', doc_type: 'INVESTMENT_PROOF', title: 'Investment Proof — PPF FY 2024-25', source_type: 'EMPLOYEE_SELF_UPLOAD', issuer: 'Self', employer_id: null, received_at: '2025-01-20', icon_type: 'invest', icon_emoji: '📊' },
  { id: 's_inv_03', doc_type: 'INVESTMENT_PROOF', title: 'Investment Proof — ELSS FY 2023-24', source_type: 'EMPLOYEE_SELF_UPLOAD', issuer: 'Self', employer_id: null, received_at: '2024-01-18', icon_type: 'invest', icon_emoji: '📊' },
  { id: 's_itr_01', doc_type: 'IT_RETURN', title: 'ITR — AY 2025-26', source_type: 'EMPLOYEE_SELF_UPLOAD', issuer: 'Self', employer_id: null, received_at: '2025-08-01', icon_type: 'tax', icon_emoji: '🏛' },
  { id: 's_itr_02', doc_type: 'IT_RETURN', title: 'ITR — AY 2024-25', source_type: 'EMPLOYEE_SELF_UPLOAD', issuer: 'Self', employer_id: null, received_at: '2024-07-28', icon_type: 'tax', icon_emoji: '🏛' },
  { id: 's_itr_03', doc_type: 'IT_RETURN', title: 'ITR — AY 2023-24', source_type: 'EMPLOYEE_SELF_UPLOAD', issuer: 'Self', employer_id: null, received_at: '2023-07-30', icon_type: 'tax', icon_emoji: '🏛' },
  { id: 's_bnk_01', doc_type: 'BANK_STATEMENT', title: 'Bank Statement — HDFC Jan–Jun 2026', source_type: 'EMPLOYEE_SELF_UPLOAD', issuer: 'Self', employer_id: null, received_at: '2026-06-12', icon_type: 'bank', icon_emoji: '🏦' },
  { id: 's_bnk_02', doc_type: 'BANK_STATEMENT', title: 'Bank Statement — HDFC Jul–Dec 2025', source_type: 'EMPLOYEE_SELF_UPLOAD', issuer: 'Self', employer_id: null, received_at: '2026-01-05', icon_type: 'bank', icon_emoji: '🏦' },
  { id: 's_bnk_03', doc_type: 'BANK_STATEMENT', title: 'Bank Statement — HDFC Jan–Jun 2025', source_type: 'EMPLOYEE_SELF_UPLOAD', issuer: 'Self', employer_id: null, received_at: '2025-07-03', icon_type: 'bank', icon_emoji: '🏦' },

  // ── Email-fetched documents ────────────────────────────────────
  { id: 'em_sal_01', doc_type: 'SALARY_SLIP',   title: 'Salary Slip — Apr 2022',     source_type: 'EMAIL_FETCH', issuer: 'Wipro', employer_id: 'e3', received_at: '2022-05-04', icon_type: 'salary', icon_emoji: '💰' },
  { id: 'em_sal_02', doc_type: 'SALARY_SLIP',   title: 'Salary Slip — Mar 2022',     source_type: 'EMAIL_FETCH', issuer: 'Wipro', employer_id: 'e3', received_at: '2022-04-04', icon_type: 'salary', icon_emoji: '💰' },
  { id: 'em_off_01', doc_type: 'OFFER_LETTER',  title: 'Offer Letter — Wipro',       source_type: 'EMAIL_FETCH', issuer: 'Wipro', employer_id: 'e3', received_at: '2019-01-15', icon_type: 'letter', icon_emoji: '📩' },
  { id: 'em_f16_01', doc_type: 'FORM_16',       title: 'Form 16 — FY 2021-22',       source_type: 'EMAIL_FETCH', issuer: 'Wipro', employer_id: 'e3', received_at: '2022-05-30', icon_type: 'form16', icon_emoji: '🧾' },
];
