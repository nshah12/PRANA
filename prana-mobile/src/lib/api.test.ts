/**
 * Tests for the fetch-based API client: token attachment, JSON handling,
 * error mapping, and the 401 → silent-refresh → retry flow.
 * global.fetch is mocked; the real authStore holds the token.
 */
import { api } from './api';
import { authStore } from './auth-store';

function jsonResponse(status: number, body: unknown) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

const fetchMock = jest.fn();

beforeEach(() => {
  global.fetch = fetchMock as unknown as typeof fetch;
  fetchMock.mockReset();
  authStore.clearToken();
  authStore.onSignOut = undefined;
});

describe('api client — requests', () => {
  it('attaches the Bearer token when one is set', async () => {
    authStore.setToken('tok-1');
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { ok: true }));

    await api.get('/v1/vault/profile');

    const [, init] = fetchMock.mock.calls[0];
    expect(init.headers.Authorization).toBe('Bearer tok-1');
    expect(init.method).toBe('GET');
  });

  it('omits the Authorization header when no token is set', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, {}));
    await api.get('/v1/public/thing');
    const [, init] = fetchMock.mock.calls[0];
    expect(init.headers.Authorization).toBeUndefined();
  });

  it('returns the parsed JSON body', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { documents: [1, 2] }));
    const body = await api.get<{ documents: number[] }>('/v1/vault/documents');
    expect(body).toEqual({ documents: [1, 2] });
  });

  it('serializes the request body on POST', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(201, { id: 'x' }));
    await api.post('/v1/vault/requests', { doc_type: 'FORM_16' });
    const [, init] = fetchMock.mock.calls[0];
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({ doc_type: 'FORM_16' });
  });

  it('returns undefined for a 204 No Content', async () => {
    fetchMock.mockResolvedValueOnce({ ok: true, status: 204, json: async () => { throw new Error('no body'); } } as Response);
    const res = await api.delete('/v1/vault/share/abc');
    expect(res).toBeUndefined();
  });

  it('throws an Error carrying the server error code on non-2xx', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(400, { error: 'INVALID_TOTP' }));
    await expect(api.get('/v1/vault/documents')).rejects.toMatchObject({
      message: 'INVALID_TOTP',
      status: 400,
    });
  });
});

describe('api client — 401 silent refresh', () => {
  it('refreshes on 401, stores the new token, and retries the original request', async () => {
    authStore.setToken('old-tok');
    fetchMock
      .mockResolvedValueOnce(jsonResponse(401, { error: 'TOKEN_EXPIRED' }))          // original → 401
      .mockResolvedValueOnce(jsonResponse(200, { access_token: 'new-tok' }))         // refresh → ok
      .mockResolvedValueOnce(jsonResponse(200, { documents: [] }));                  // retry → ok

    const body = await api.get<{ documents: unknown[] }>('/v1/vault/documents');

    expect(body).toEqual({ documents: [] });
    expect(authStore.getToken()).toBe('new-tok');
    // 2nd call is the refresh endpoint
    expect(fetchMock.mock.calls[1][0]).toContain('/auth/employee/refresh');
    // 3rd call (retry) carries the new token
    expect(fetchMock.mock.calls[2][1].headers.Authorization).toBe('Bearer new-tok');
  });

  it('signs out and throws SESSION_EXPIRED when the refresh also fails', async () => {
    authStore.setToken('old-tok');
    const onSignOut = jest.fn();
    authStore.onSignOut = onSignOut;
    fetchMock
      .mockResolvedValueOnce(jsonResponse(401, { error: 'TOKEN_EXPIRED' }))  // original → 401
      .mockResolvedValueOnce(jsonResponse(401, { error: 'REFRESH_INVALID' })); // refresh → 401

    await expect(api.get('/v1/vault/documents')).rejects.toThrow('SESSION_EXPIRED');
    expect(authStore.getToken()).toBeNull();
    expect(onSignOut).toHaveBeenCalled();
  });

  it('does not attempt a second refresh on a retried request (no infinite loop)', async () => {
    authStore.setToken('old-tok');
    fetchMock
      .mockResolvedValueOnce(jsonResponse(401, { error: 'TOKEN_EXPIRED' }))   // original → 401
      .mockResolvedValueOnce(jsonResponse(200, { access_token: 'new-tok' }))  // refresh → ok
      .mockResolvedValueOnce(jsonResponse(401, { error: 'TOKEN_EXPIRED' }));  // retry → 401 again

    // Retried request has retry=false, so a second 401 surfaces as an error (no 4th call).
    await expect(api.get('/v1/vault/documents')).rejects.toBeDefined();
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });
});
