import { Stack } from 'expo-router';

export default function AuthLayout() {
  return (
    <Stack screenOptions={{ headerShown: false, animation: 'slide_from_right' }}>
      <Stack.Screen name="splash" />
      <Stack.Screen name="sign-in" />
      <Stack.Screen name="totp-setup" />
      <Stack.Screen name="totp-verify" />
      <Stack.Screen name="register-device" />
      <Stack.Screen name="enable-face-id" />
      <Stack.Screen name="biometric-unlock" />
      <Stack.Screen name="push-approval" />
      <Stack.Screen name="consent" />
    </Stack>
  );
}
