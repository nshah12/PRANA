/**
 * useVault hook tests — the shared useFetch<T> plumbing (loading/error/data/
 * refetch) backs every one of these hooks, so useDocuments doubles as the
 * contract test for that plumbing. getDownloadUrl/createShare/
 * requestZipDownload are deliberately NOT tested here — they're already
 * flagged with TODO(backend) comments in useVault.ts for calling endpoints
 * that don't exist or have the wrong shape; testing them would just lock in
 * the known-wrong contract.
 */
import { renderHook, waitFor, cleanup } from '@testing-library/react-native';
import {
  useDocuments, useEmployers, useVaultHealth, useShares, useAccessLog,
  useTimeline, useDocument, getCredential,
} from './useVault';
import { api } from '@/lib/api';

jest.mock('@/lib/api', () => ({ api: { get: jest.fn(), post: jest.fn() } }));

const mockGet = api.get as jest.Mock;
afterEach(async () => { await cleanup(); });
beforeEach(() => { jest.clearAllMocks(); });

describe('useFetch-backed hooks', () => {
  it('useDocuments resolves with data and clears the loading flag', async () => {
    mockGet.mockResolvedValue({ documents: [{ id: 'd1' }] });
    const { result } = await renderHook(() => useDocuments());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.data).toEqual({ documents: [{ id: 'd1' }] });
    expect(result.current.error).toBeNull();
    expect(mockGet).toHaveBeenCalledWith('/v1/vault/documents');
  });

  it('useDocuments appends employer_id and doc_type as query params', async () => {
    mockGet.mockResolvedValue({ documents: [] });
    await renderHook(() => useDocuments({ employer_id: 'emp-1', doc_type: 'FORM16' }));
    expect(mockGet).toHaveBeenCalledWith('/v1/vault/documents?employer_id=emp-1&doc_type=FORM16');
  });

  it('exposes an error message and stops loading when the request fails', async () => {
    mockGet.mockRejectedValue(new Error('SERVER_DOWN'));
    const { result } = await renderHook(() => useDocuments());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBe('SERVER_DOWN');
    expect(result.current.data).toBeNull();
  });

  it('refetch re-runs the request and clears a prior error', async () => {
    mockGet.mockRejectedValueOnce(new Error('boom'));
    const { result } = await renderHook(() => useDocuments());
    await waitFor(() => expect(result.current.error).toBe('boom'));

    mockGet.mockResolvedValueOnce({ documents: [{ id: 'd2' }] });
    await result.current.refetch();
    await waitFor(() => expect(result.current.error).toBeNull());
    expect(result.current.data).toEqual({ documents: [{ id: 'd2' }] });
  });

  it('useEmployers calls the employers endpoint', async () => {
    mockGet.mockResolvedValue({ employers: [] });
    const { result } = await renderHook(() => useEmployers());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(mockGet).toHaveBeenCalledWith('/v1/vault/employers');
  });

  it('useVaultHealth calls the health endpoint', async () => {
    mockGet.mockResolvedValue({ score: 80, label: 'Good', missing_types: [] });
    const { result } = await renderHook(() => useVaultHealth());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(mockGet).toHaveBeenCalledWith('/v1/vault/health');
    expect(result.current.data?.score).toBe(80);
  });

  it('useShares calls the share endpoint', async () => {
    mockGet.mockResolvedValue({ shares: [] });
    await renderHook(() => useShares());
    expect(mockGet).toHaveBeenCalledWith('/v1/vault/share');
  });

  it('useAccessLog defaults to a limit of 30 and accepts an override', async () => {
    mockGet.mockResolvedValue({ events: [] });
    await renderHook(() => useAccessLog());
    expect(mockGet).toHaveBeenCalledWith('/v1/vault/activity?limit=30');

    jest.clearAllMocks();
    mockGet.mockResolvedValue({ events: [] });
    await renderHook(() => useAccessLog(10));
    expect(mockGet).toHaveBeenCalledWith('/v1/vault/activity?limit=10');
  });

  it('useTimeline calls the timeline endpoint', async () => {
    mockGet.mockResolvedValue({ events: [] });
    await renderHook(() => useTimeline());
    expect(mockGet).toHaveBeenCalledWith('/v1/vault/timeline');
  });

  it('useDocument fetches a single document by id and refetches when the id changes', async () => {
    mockGet.mockResolvedValue({ document: { id: 'doc-1' } });
    const { result, rerender } = await renderHook(({ id }: { id: string }) => useDocument(id), { initialProps: { id: 'doc-1' } });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(mockGet).toHaveBeenCalledWith('/v1/vault/documents/doc-1');

    mockGet.mockResolvedValue({ document: { id: 'doc-2' } });
    await rerender({ id: 'doc-2' });
    await waitFor(() => expect(mockGet).toHaveBeenCalledWith('/v1/vault/documents/doc-2'));
  });
});

describe('getCredential', () => {
  it('fetches the credential card for a document', async () => {
    mockGet.mockResolvedValue({ verification_code: 'ABC123' });
    const cred = await getCredential('doc-1');
    expect(mockGet).toHaveBeenCalledWith('/v1/vault/documents/doc-1/credential');
    expect(cred.verification_code).toBe('ABC123');
  });
});
