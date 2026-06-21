/**
 * Thin fetch wrapper over the PRANA REST API.
 * All requests attach the Bearer token stored in authStore.
 * On 401, tries a silent cookie-based refresh; on second failure, signs out.
 */

import { authStore } from './auth-store';

const BASE_URL = process.env.EXPO_PUBLIC_API_URL ?? 'https://api.prana.in';

type Method = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';

async function request<T>(
  method: Method,
  path: string,
  body?: unknown,
  headers?: Record<string, string>,
  retry = true,
): Promise<T> {
  const token = authStore.getToken();

  const res = await fetch(`${BASE_URL}${path}`, {
    method,
    credentials: 'include',       // httpOnly refresh cookie
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...headers,
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (res.status === 401 && retry) {
    // Attempt silent refresh using httpOnly cookie
    const refreshRes = await fetch(`${BASE_URL}/auth/employee/refresh`, {
      method: 'POST',
      credentials: 'include',
    });
    if (refreshRes.ok) {
      const data = await refreshRes.json() as { access_token: string };
      authStore.setToken(data.access_token);
      return request<T>(method, path, body, headers, false);
    } else {
      authStore.clearToken();
      authStore.onSignOut?.();
      throw new Error('SESSION_EXPIRED');
    }
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: 'UNKNOWN' }));
    throw Object.assign(new Error((err as { error?: string }).error ?? 'API_ERROR'), {
      status: res.status,
      body: err,
    });
  }

  // 204 No Content
  if (res.status === 204) return undefined as unknown as T;
  return res.json() as Promise<T>;
}

async function uploadMultipart<T>(
  path: string,
  formData: FormData,
  onProgress?: (pct: number) => void,
): Promise<T> {
  const token = authStore.getToken();
  return new Promise<T>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${BASE_URL}${path}`);
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`);
    // Do NOT set Content-Type — browser/RN sets it automatically with boundary
    if (onProgress) {
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) onProgress(e.loaded / e.total);
      };
    }
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try { resolve(JSON.parse(xhr.responseText) as T); } catch { resolve(undefined as unknown as T); }
      } else {
        reject(Object.assign(new Error('UPLOAD_FAILED'), { status: xhr.status }));
      }
    };
    xhr.onerror = () => reject(new Error('NETWORK_ERROR'));
    xhr.send(formData);
  });
}

export const api = {
  get:    <T>(path: string, headers?: Record<string, string>) =>
            request<T>('GET', path, undefined, headers),
  post:   <T>(path: string, body?: unknown, headers?: Record<string, string>) =>
            request<T>('POST', path, body, headers),
  patch:  <T>(path: string, body?: unknown) => request<T>('PATCH', path, body),
  delete: <T>(path: string) => request<T>('DELETE', path),
  upload: <T>(path: string, formData: FormData, onProgress?: (pct: number) => void) =>
            uploadMultipart<T>(path, formData, onProgress),
};
