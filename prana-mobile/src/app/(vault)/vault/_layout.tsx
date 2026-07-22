import { Stack } from 'expo-router';

export default function VaultStack() {
  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Screen name="index" />
      <Stack.Screen name="document-viewer" />
      <Stack.Screen name="self-upload" />
      <Stack.Screen name="create-share" />
      <Stack.Screen name="unlock-document" options={{ animation: 'slide_from_bottom', presentation: 'modal' }} />
    </Stack>
  );
}
