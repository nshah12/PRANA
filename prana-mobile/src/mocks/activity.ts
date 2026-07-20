// ── Pipeline push events ──────────────────────────────────────────
// Each push from an employer goes through the 6-stage pipeline.
// The mobile surfaces the result of each stage to the employee.

export type PipelineStatus = 'routed' | 'pending_password' | 'exception' | 'processing';

export interface PipelineDoc {
  id: string;
  doc_title: string;
  doc_type: string;
  employer: string;
  employer_id: string;
  pushed_at: string;
  status: PipelineStatus;
  resolution_method?: 'PAN_TOKEN_EXACT' | 'EMP_ID' | 'FUZZY' | 'EMBEDDING';
  routed_at?: string;
  privacy_note: string;
}

export interface PipelinePush {
  id: string;
  employer: string;
  employer_id: string;
  pushed_at: string;
  doc_count: number;
  docs: PipelineDoc[];
  // unread = user hasn't tapped "acknowledge" yet
  unread: boolean;
}

export const mockPipelinePushes: PipelinePush[] = [
  {
    id: 'push_001',
    employer: 'NPCI',
    employer_id: 'e1',
    pushed_at: '2026-06-10T09:32:00Z',
    doc_count: 3,
    unread: false,
    docs: [
      {
        id: 'pd_001',
        doc_title: 'Salary Slip — May 2026',
        doc_type: 'SALARY_SLIP',
        employer: 'NPCI',
        employer_id: 'e1',
        pushed_at: '2026-06-10T09:32:00Z',
        status: 'routed',
        resolution_method: 'PAN_TOKEN_EXACT',
        routed_at: '2026-06-10T09:32:03Z',
        privacy_note: 'Processed in-memory · Raw salary discarded · Insights only stored',
      },
      {
        id: 'pd_002',
        doc_title: 'Form 16 — FY 2025-26',
        doc_type: 'FORM_16',
        employer: 'NPCI',
        employer_id: 'e1',
        pushed_at: '2026-06-10T09:32:00Z',
        status: 'routed',
        resolution_method: 'PAN_TOKEN_EXACT',
        routed_at: '2026-06-10T09:32:04Z',
        privacy_note: 'TDS data processed in-memory · Not stored · Form 16 cross-reference complete',
      },
      {
        id: 'pd_003',
        doc_title: 'Appraisal Letter — FY 2025-26',
        doc_type: 'APPRAISAL_LETTER',
        employer: 'NPCI',
        employer_id: 'e1',
        pushed_at: '2026-06-10T09:32:00Z',
        status: 'routed',
        resolution_method: 'EMP_ID',
        routed_at: '2026-06-10T09:32:05Z',
        privacy_note: 'Letter processed in-memory · Increment % stored as index · Raw CTC discarded',
      },
    ],
  },
  {
    id: 'push_002',
    employer: 'NPCI',
    employer_id: 'e1',
    pushed_at: '2026-06-01T08:15:00Z',
    doc_count: 1,
    unread: true,
    docs: [
      {
        id: 'pd_004',
        doc_title: 'Salary Slip — May 2026 (Protected)',
        doc_type: 'SALARY_SLIP',
        employer: 'NPCI',
        employer_id: 'e1',
        pushed_at: '2026-06-01T08:15:00Z',
        status: 'pending_password',
        privacy_note: 'Password-protected · Awaiting your password to process in a secure session',
      },
    ],
  },
  {
    id: 'push_003',
    employer: 'NPCI',
    employer_id: 'e1',
    pushed_at: '2026-05-02T09:00:00Z',
    doc_count: 1,
    unread: false,
    docs: [
      {
        id: 'pd_005',
        doc_title: 'Salary Slip — Apr 2026',
        doc_type: 'SALARY_SLIP',
        employer: 'NPCI',
        employer_id: 'e1',
        pushed_at: '2026-05-02T09:00:00Z',
        status: 'routed',
        resolution_method: 'PAN_TOKEN_EXACT',
        routed_at: '2026-05-02T09:00:02Z',
        privacy_note: 'Processed in-memory · Raw salary discarded · Insights only stored',
      },
    ],
  },
];

// ── Document access & login (unchanged) ──────────────────────────
export const mockActivity = {
  document_access: [
    { id: 'a1', doc_title: 'Salary Slip — May 2026', action: 'Viewed', actor: 'You', at: '2026-06-14T10:22:00Z' },
    { id: 'a2', doc_title: 'Form 16 — FY 2024-25', action: 'Shared with HDFC Bank', actor: 'You', at: '2026-06-10T14:05:00Z' },
    { id: 'a3', doc_title: 'Salary Slip — Apr 2026', action: 'Received', actor: 'NPCI', at: '2026-05-02T09:00:00Z' },
  ],
  login_history: [
    { id: 'l1', device: 'Pixel 8 Pro', location: 'Mumbai, IN', at: '2026-06-15T08:12:00Z', method: 'Biometric' },
    { id: 'l2', device: 'Pixel 8 Pro', location: 'Mumbai, IN', at: '2026-06-14T09:01:00Z', method: 'Push approval' },
  ],
};
