import React, { useState, useEffect } from 'react';
import { View, Text, Switch, Pressable, StyleSheet } from 'react-native';
import { router } from 'expo-router';
import { useAuth } from '@/context/AuthContext';
import { PageScreen, SectionLabel } from '@/components/PageScreen';
import { api } from '@/lib/api';
import { colors, fonts, radius } from '@/prana-theme/tokens';

type Device = {
  id: string;
  name: string;
  platform: 'android' | 'ios' | 'web';
  is_current: boolean;
  trusted_at: string;
};

function SettingRow({ icon, iconBg, title, sub, right }: { icon: string; iconBg: string; title: string; sub?: string; right: React.ReactNode }) {
  return (
    <View style={styles.row}>
      <View style={[styles.rowIcon, { backgroundColor: iconBg }]}>
        <Text style={{ fontSize: 15 }}>{icon}</Text>
      </View>
      <View style={{ flex: 1 }}>
        <Text style={styles.rowTitle}>{title}</Text>
        {sub ? <Text style={styles.rowSub}>{sub}</Text> : null}
      </View>
      {right}
    </View>
  );
}

export default function SettingsScreen() {
  const { signOut } = useAuth();
  const [biometric, setBiometric] = useState(true);
  const [pushNotif, setPushNotif] = useState(true);
  const [docNotif, setDocNotif] = useState(true);
  const [devices, setDevices] = useState<Device[]>([]);

  useEffect(() => {
    api.get<{ devices: Device[] }>('/auth/sessions/devices').then(d => {
      setDevices(d.devices ?? []);
    }).catch(() => {});
  }, []);

  function removeDevice(id: string) {
    api.delete(`/auth/sessions/devices/${id}`).then(() => {
      setDevices(prev => prev.filter(d => d.id !== id));
    }).catch(() => {});
  }

  return (
    <PageScreen title="Settings" sub="Account & preferences" icon="⚙">
      <SectionLabel label="Security" />
      <View style={styles.group}>
        <SettingRow icon="👤" iconBg="rgba(99,102,241,0.15)" title="Biometric unlock" sub="Face ID / fingerprint" right={<Switch value={biometric} onValueChange={setBiometric} trackColor={{ true: colors.indigo }} />} />
        <SettingRow icon="📱" iconBg="rgba(52,211,153,0.15)" title="Push approval" sub="Login on new devices" right={<Switch value={pushNotif} onValueChange={setPushNotif} trackColor={{ true: colors.indigo }} />} />
      </View>

      <SectionLabel label="Notifications" />
      <View style={styles.group}>
        <SettingRow icon="🔔" iconBg="rgba(251,191,36,0.15)" title="New documents" sub="When employer pushes a doc" right={<Switch value={docNotif} onValueChange={setDocNotif} trackColor={{ true: colors.indigo }} />} />
      </View>

      <SectionLabel label="Trusted devices" />
      <View style={styles.group}>
        {devices.length === 0 ? (
          <Text style={[styles.rowSub, { padding: 12 }]}>No trusted devices yet</Text>
        ) : devices.map((d) => (
          <SettingRow
            key={d.id}
            icon={d.platform === 'android' ? '📱' : d.platform === 'ios' ? '📱' : '💻'}
            iconBg={colors.surface3}
            title={d.name}
            sub={d.is_current ? 'This device' : `Trusted ${new Date(d.trusted_at).toLocaleDateString('en-IN', { month: 'short', year: 'numeric' })}`}
            right={
              !d.is_current ? (
                <Pressable style={styles.removeBtn} onPress={() => removeDevice(d.id)}>
                  <Text style={styles.removeText}>Remove</Text>
                </Pressable>
              ) : (
                <View style={styles.currentBadge}><Text style={styles.currentText}>Current</Text></View>
              )
            }
          />
        ))}
      </View>

      <SectionLabel label="Privacy & data" />
      <View style={styles.group}>
        <Pressable style={styles.row} onPress={() => router.push('/(vault)/data-rights')}>
          <View style={[styles.rowIcon, { backgroundColor: 'rgba(99,102,241,0.12)' }]}>
            <Text style={{ fontSize: 15 }}>⚖️</Text>
          </View>
          <View style={{ flex: 1 }}>
            <Text style={styles.rowTitle}>My Data Rights</Text>
            <Text style={styles.rowSub}>DPDP Act 2023 · Access, correct, erase</Text>
          </View>
          <Text style={{ fontSize: 18, color: colors.ink3 }}>›</Text>
        </Pressable>
      </View>

      <SectionLabel label="Account" />
      <View style={styles.group}>
        <Pressable style={[styles.row, styles.dangerRow]} onPress={() => { signOut(); router.replace('/(auth)/sign-in'); }}>
          <View style={[styles.rowIcon, { backgroundColor: 'rgba(251,113,133,0.15)' }]}>
            <Text style={{ fontSize: 15 }}>🚪</Text>
          </View>
          <Text style={styles.dangerText}>Sign out</Text>
        </Pressable>
      </View>
    </PageScreen>
  );
}

const styles = StyleSheet.create({
  group: { backgroundColor: colors.surface3, borderRadius: 18, paddingHorizontal: 14, marginBottom: 4 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: 'rgba(0,0,0,0.04)' },
  rowIcon: { width: 34, height: 34, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
  rowTitle: { fontSize: 13, fontFamily: fonts.bodySemiBold, color: colors.ink },
  rowSub: { fontFamily: fonts.mono, fontSize: 10, color: colors.ink3, marginTop: 1 },
  removeBtn: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8, borderWidth: 1, borderColor: 'rgba(251,113,133,0.3)' },
  removeText: { fontSize: 11, color: '#FB7185', fontFamily: fonts.bodySemiBold },
  currentBadge: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8, backgroundColor: 'rgba(52,211,153,0.15)' },
  currentText: { fontSize: 11, color: '#047857', fontFamily: fonts.mono },
  dangerRow: { borderBottomWidth: 0 },
  dangerText: { fontSize: 14, fontFamily: fonts.bodySemiBold, color: '#FB7185' },
});
