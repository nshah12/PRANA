/**
 * Data hooks for the vault — documents, employers, timeline, health, shares.
 * Each hook follows the { data, loading, error, refetch } pattern.
 * Mocks are still importable as fallback for Expo Go / offline dev.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';

type IconType = 'salary' | 'form16' | 'invest' | 'letter' | 'tax' | 'bank';

export type DocSourceType =
  | 'EMPLOYER_PUSH'
  | 'EMPLOYEE_SELF_UPLOAD'
  | 'EMAIL_FETCH'
  | 'THIRD_PARTY_VERIFIED';

export interface VaultDocument {
  id: string;             // document_id UUID
  doc_type: string;
  title: string;
  source_type: DocSourceType;
  issuer: string;         // tenant_name, "Self", or email domain
  employer_id: string | null;
  received_at: string;
  icon_type: IconType;
  icon_emoji: string;
}

export interface DocumentDetail extends VaultDocument {
  file_hash: string;
  // Insights from AI pipeline — non-sensitive fields only (no ₹ salary amounts)
  insights: Record<string, { value: string; confidence: number }>;
}

export interface Employer {
  id: string;
  name: string;
  role: string;
  from: string;
  to: string | null;
}

export interface VaultHealth {
  score: number;
  label: string;
  missing_types: string[];
}

export interface ShareLink {
  token_id: string;
  label: string;
  status: string;
  expires_at: string | null;
  usage_count: number;
  usage_limit: number | null;
  created_at: string;
}

// ── Generic fetch hook ────────────────────────────────────────────────────────

function useFetch<T>(path: string, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const mounted = useRef(true);

  const fetch_ = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.get<T>(path);
      if (mounted.current) setData(result);
    } catch (e: unknown) {
      if (mounted.current) setError((e as Error).message);
    } finally {
      if (mounted.current) setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, ...deps]);

  useEffect(() => {
    mounted.current = true;
    fetch_();
    return () => { mounted.current = false; };
  }, [fetch_]);

  return { data, loading, error, refetch: fetch_ };
}

// ── Vault document list ───────────────────────────────────────────────────────

export function useDocuments(params?: { employer_id?: string; doc_type?: string }) {
  const qs = new URLSearchParams();
  if (params?.employer_id) qs.set('employer_id', params.employer_id);
  if (params?.doc_type)    qs.set('doc_type',    params.doc_type);
  const query = qs.toString() ? `?${qs}` : '';
  return useFetch<{ documents: VaultDocument[] }>(`/vault/documents${query}`);
}

// ── Employers list ────────────────────────────────────────────────────────────

export function useEmployers() {
  return useFetch<{ employers: Employer[] }>('/vault/employers');
}

// ── Vault health score ────────────────────────────────────────────────────────

export function useVaultHealth() {
  return useFetch<VaultHealth>('/vault/health');
}

// ── Share links ───────────────────────────────────────────────────────────────

export function useShares() {
  return useFetch<{ shares: ShareLink[] }>('/vault/share');
}

// ── Activity: document access log ─────────────────────────────────────────────

export interface AccessEntry {
  access_id: string;
  document_id: string;
  doc_title: string;
  access_type: string;
  channel: string;
  accessed_at: string;
  ip_address: string | null;
}

export function useAccessLog(limit = 30) {
  return useFetch<{ events: AccessEntry[] }>(`/vault/activity?limit=${limit}`);
}

// ── Career timeline ───────────────────────────────────────────────────────────

export interface TimelineEvent {
  event_id: string;
  event_type: string;
  event_date: string;
  employer_name: string;
  title: string | null;
  notes: string | null;
}

export function useTimeline() {
  return useFetch<{ events: TimelineEvent[] }>('/vault/timeline');
}

// ── Single document detail ────────────────────────────────────────────────────

export function useDocument(id: string) {
  return useFetch<{ document: DocumentDetail }>(`/vault/documents/${id}`, [id]);
}

// ── Download presigned URL ────────────────────────────────────────────────────

export async function getDownloadUrl(id: string): Promise<string> {
  const res = await api.get<{ presigned_url: string }>(`/vault/documents/${id}/download`);
  return res.presigned_url;
}

// ── Create share link ─────────────────────────────────────────────────────────

export interface CreateShareParams {
  document_ids: string[];
  label?: string;
  expires_hours: number;     // 24 | 168 | 720
  usage_limit?: number;
}

export interface CreatedShare {
  token_id: string;
  share_url: string;
  expires_at: string;
}

export async function createShare(params: CreateShareParams): Promise<CreatedShare> {
  return api.post<CreatedShare>('/vault/shares', params);
}

// ── Career Passport credential card ──────────────────────────────────────────

export interface CredentialCard {
  verification_code: string;
  verify_url:        string;
  qr_url:            string;
  doc_type:          string;
  doc_period:        string | null;
  pushed_by:         string;
  pushed_at:         string | null;
  routed_at:         string | null;
  file_hash_sha256:  string | null;
}

export async function getCredential(docId: string): Promise<CredentialCard> {
  return api.get<CredentialCard>(`/vault/documents/${docId}/credential`);
}

// ── Bulk ZIP download ─────────────────────────────────────────────────────────

export async function requestZipDownload(document_ids: string[]): Promise<{ job_id: string; download_url?: string }> {
  return api.post('/vault/documents/bulk-download', { document_ids });
}
