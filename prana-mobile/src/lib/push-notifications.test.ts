import { Platform } from 'react-native';
import * as Notifications from 'expo-notifications';
import { getExpoPushTokenOrNull, refreshPushToken } from './push-notifications';
import { api } from '@/lib/api';
import { authStore } from '@/lib/auth-store';

jest.mock('expo-notifications', () => ({
  getPermissionsAsync: jest.fn(),
  requestPermissionsAsync: jest.fn(),
  getExpoPushTokenAsync: jest.fn(),
}));

jest.mock('expo-constants', () => ({
  expoConfig: { extra: { eas: { projectId: 'test-project-id' } } },
}));

jest.mock('@/lib/api', () => ({ api: { post: jest.fn() } }));
jest.mock('@/lib/auth-store', () => ({ authStore: { getPublicKey: jest.fn() } }));

const mockGetPerms = Notifications.getPermissionsAsync as jest.Mock;
const mockRequestPerms = Notifications.requestPermissionsAsync as jest.Mock;
const mockGetToken = Notifications.getExpoPushTokenAsync as jest.Mock;
const mockPost = api.post as jest.Mock;
const mockGetPublicKey = authStore.getPublicKey as jest.Mock;

beforeEach(() => {
  jest.clearAllMocks();
  (Platform as any).OS = 'android';
});

test('returns the token when permission is already granted', async () => {
  mockGetPerms.mockResolvedValue({ status: 'granted' });
  mockGetToken.mockResolvedValue({ data: 'ExponentPushToken[abc]' });

  const token = await getExpoPushTokenOrNull();

  expect(token).toBe('ExponentPushToken[abc]');
  expect(mockRequestPerms).not.toHaveBeenCalled();
});

test('requests permission when not already granted, then fetches token', async () => {
  mockGetPerms.mockResolvedValue({ status: 'undetermined' });
  mockRequestPerms.mockResolvedValue({ status: 'granted' });
  mockGetToken.mockResolvedValue({ data: 'ExponentPushToken[xyz]' });

  const token = await getExpoPushTokenOrNull();

  expect(mockRequestPerms).toHaveBeenCalled();
  expect(token).toBe('ExponentPushToken[xyz]');
});

test('returns null without throwing when permission is denied', async () => {
  mockGetPerms.mockResolvedValue({ status: 'undetermined' });
  mockRequestPerms.mockResolvedValue({ status: 'denied' });

  const token = await getExpoPushTokenOrNull();

  expect(token).toBeNull();
  expect(mockGetToken).not.toHaveBeenCalled();
});

test('returns null without throwing when getExpoPushTokenAsync rejects', async () => {
  mockGetPerms.mockResolvedValue({ status: 'granted' });
  mockGetToken.mockRejectedValue(new Error('no native module'));

  const token = await getExpoPushTokenOrNull();

  expect(token).toBeNull();
});

test('returns null on web without calling any native API', async () => {
  (Platform as any).OS = 'web';

  const token = await getExpoPushTokenOrNull();

  expect(token).toBeNull();
  expect(mockGetPerms).not.toHaveBeenCalled();
});

test('passes the EAS projectId from app config to getExpoPushTokenAsync', async () => {
  mockGetPerms.mockResolvedValue({ status: 'granted' });
  mockGetToken.mockResolvedValue({ data: 'tok' });

  await getExpoPushTokenOrNull();

  expect(mockGetToken).toHaveBeenCalledWith({ projectId: 'test-project-id' });
});

describe('refreshPushToken', () => {
  test('no-ops when this device was never registered (no persisted public key)', async () => {
    mockGetPublicKey.mockResolvedValue(null);
    await refreshPushToken();
    expect(mockGetToken).not.toHaveBeenCalled();
    expect(mockPost).not.toHaveBeenCalled();
  });

  test('re-posts with the SAME persisted public_key and a fresh push token', async () => {
    mockGetPublicKey.mockResolvedValue('pubkey-persisted');
    mockGetPerms.mockResolvedValue({ status: 'granted' });
    mockGetToken.mockResolvedValue({ data: 'ExponentPushToken[rotated]' });

    await refreshPushToken();

    expect(mockPost).toHaveBeenCalledWith('/auth/employee/device/register', expect.objectContaining({
      public_key: 'pubkey-persisted',
      push_token: 'ExponentPushToken[rotated]',
    }));
  });

  test('no-ops without posting when permission is not granted', async () => {
    mockGetPublicKey.mockResolvedValue('pubkey-persisted');
    mockGetPerms.mockResolvedValue({ status: 'denied' });
    mockRequestPerms.mockResolvedValue({ status: 'denied' });

    await refreshPushToken();

    expect(mockPost).not.toHaveBeenCalled();
  });

  test('never throws — a POST failure is swallowed', async () => {
    mockGetPublicKey.mockResolvedValue('pubkey-persisted');
    mockGetPerms.mockResolvedValue({ status: 'granted' });
    mockGetToken.mockResolvedValue({ data: 'tok' });
    mockPost.mockRejectedValue(new Error('network down'));

    await expect(refreshPushToken()).resolves.toBeUndefined();
  });
});
