import React, { useState } from 'react';
import {
  View, Text, Pressable, StyleSheet, ScrollView, TextInput, ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { colors, fonts } from '@/prana-theme/tokens';
import { api } from '@/lib/api';

type Nominee = {
  nominee_id: string;
  name: string;
  relationship: string;
  mobile: string;
  email?: string;
  is_active: boolean;
  created_at: string;
};

const RELATIONSHIPS = ['Spouse', 'Parent', 'Sibling', 'Child', 'Guardian', 'Other'];

export default function NominationScreen() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [name, setName]         = useState('');
  const [rel, setRel]           = useState('Spouse');
  const [mobile, setMobile]     = useState('');
  const [email, setEmail]       = useState('');
  const [done, setDone]         = useState(false);

  const { data, isLoading } = useQuery<{ items: Nominee[] }>({
    queryKey: ['nominations'],
    queryFn:  () => api.get('/vault/compliance/nominees').then(r => r.data),
  });

  const addMutation = useMutation({
    mutationFn: () => api.post('/vault/compliance/nominees', { name, relationship: rel, mobile, email: email || undefined }),
    onSuccess:  () => {
      queryClient.invalidateQueries({ queryKey: ['nominations'] });
      setShowForm(false); setDone(true);
      setName(''); setMobile(''); setEmail('');
    },
  });

  const removeMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/vault/compliance/nominees/${id}`),
    onSuccess:  () => queryClient.invalidateQueries({ queryKey: ['nominations'] }),
  });

  const nominees = data?.items ?? [];

  return (
    <View style={s.screen}>
      <SafeAreaView edges={['top']} style={s.safe}>
        <View style={s.header}>
          <Pressable onPress={() => router.back()} style={s.backBtn}>
            <Text style={s.backText}>‹</Text>
          </Pressable>
          <View style={{ flex: 1 }}>
            <Text style={s.headerTitle}>Nominations</Text>
            <Text style={s.headerSub}>DPDP §15 · Trusted guardian for your vault</Text>
          </View>
          <Pressable style={s.newBtn} onPress={() => setShowForm(true)}>
            <Text style={s.newBtnText}>＋ Add</Text>
          </Pressable>
        </View>
      </SafeAreaView>

      <ScrollView style={s.body} contentContainerStyle={s.bodyContent} showsVerticalScrollIndicator={false}>

        <View style={s.infoCard}>
          <Text style={s.infoTitle}>👨‍👩‍👧 What is a nominee?</Text>
          <Text style={s.infoText}>
            A nominee can manage your PRANA vault on your behalf — useful for minors, or to designate a trusted person in case of incapacitation. They cannot access your documents without your explicit approval.
          </Text>
        </View>

        {done && (
          <View style={s.successBanner}>
            <Text style={s.successText}>✓ Nominee added successfully.</Text>
          </View>
        )}

        {isLoading ? (
          <View style={s.center}><ActivityIndicator color={colors.indigo} /></View>
        ) : nominees.length === 0 ? (
          <View style={s.emptyCard}>
            <Text style={s.emptyIcon}>👤</Text>
            <Text style={s.emptyTitle}>No nominees yet</Text>
            <Text style={s.emptySub}>Add a trusted person to manage your vault.</Text>
          </View>
        ) : (
          nominees.map(n => (
            <View key={n.nominee_id} style={s.nomineeCard}>
              <View style={s.nomineeAvatar}>
                <Text style={s.nomineeInitial}>{n.name.charAt(0)}</Text>
              </View>
              <View style={{ flex: 1 }}>
                <Text style={s.nomineeName}>{n.name}</Text>
                <Text style={s.nomineeRel}>{n.relationship} · {n.mobile}</Text>
                <Text style={s.nomineeDate}>Added {new Date(n.created_at).toLocaleDateString('en-IN', { day:'2-digit', month:'short', year:'numeric' })}</Text>
              </View>
              <Pressable
                style={s.removeBtn}
                onPress={() => removeMutation.mutate(n.nominee_id)}
                disabled={removeMutation.isPending}
              >
                <Text style={s.removeText}>Remove</Text>
              </Pressable>
            </View>
          ))
        )}

        {showForm && (
          <View style={s.formCard}>
            <Text style={s.formTitle}>Add nominee</Text>

            <Text style={s.label}>Full name</Text>
            <TextInput style={s.input} value={name} onChangeText={setName} placeholder="Nominee's legal name" placeholderTextColor={colors.ink3} />

            <Text style={s.label}>Relationship</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 14 }}>
              <View style={{ flexDirection: 'row', gap: 8 }}>
                {RELATIONSHIPS.map(r => (
                  <Pressable key={r} style={[s.chip, rel === r && s.chipActive]} onPress={() => setRel(r)}>
                    <Text style={[s.chipText, rel === r && s.chipTextActive]}>{r}</Text>
                  </Pressable>
                ))}
              </View>
            </ScrollView>

            <Text style={s.label}>Mobile number</Text>
            <TextInput style={s.input} value={mobile} onChangeText={setMobile} placeholder="+91 9000000000" placeholderTextColor={colors.ink3} keyboardType="phone-pad" />

            <Text style={s.label}>Email (optional)</Text>
            <TextInput style={s.input} value={email} onChangeText={setEmail} placeholder="nominee@email.com" placeholderTextColor={colors.ink3} keyboardType="email-address" autoCapitalize="none" />

            <View style={{ flexDirection: 'row', gap: 10 }}>
              <Pressable style={[s.btn, s.btnCancel]} onPress={() => setShowForm(false)}>
                <Text style={s.btnCancelText}>Cancel</Text>
              </Pressable>
              <Pressable
                style={[s.btn, s.btnSubmit, (addMutation.isPending || !name || !mobile) && { opacity: 0.5 }]}
                onPress={() => addMutation.mutate()}
                disabled={addMutation.isPending || !name || !mobile}
              >
                {addMutation.isPending
                  ? <ActivityIndicator size="small" color="#FFF" />
                  : <Text style={s.btnSubmitText}>Add nominee</Text>
                }
              </Pressable>
            </View>
          </View>
        )}
      </ScrollView>
    </View>
  );
}

const s = StyleSheet.create({
  screen:        { flex: 1, backgroundColor: colors.surface },
  safe:          { backgroundColor: colors.surface },
  header:        { flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 16, paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: colors.surface3 },
  backBtn:       { padding: 4, marginRight: 2 },
  backText:      { fontSize: 28, color: colors.ink2, lineHeight: 32 },
  headerTitle:   { fontFamily: fonts.displayBold, fontSize: 17, color: colors.ink },
  headerSub:     { fontFamily: fonts.mono, fontSize: 10, color: colors.ink3, marginTop: 2 },
  newBtn:        { backgroundColor: 'rgba(99,102,241,0.12)', borderRadius: 12, paddingHorizontal: 12, paddingVertical: 8 },
  newBtnText:    { fontFamily: fonts.bodySemiBold, fontSize: 13, color: colors.indigo },
  body:          { flex: 1 },
  bodyContent:   { padding: 16, paddingBottom: 60, gap: 12 },
  infoCard:      { backgroundColor: 'rgba(99,102,241,0.07)', borderRadius: 18, padding: 16, gap: 8 },
  infoTitle:     { fontFamily: fonts.bodySemiBold, fontSize: 13, color: colors.ink },
  infoText:      { fontSize: 12, color: colors.ink2, lineHeight: 19 },
  center:        { padding: 24, alignItems: 'center' },
  emptyCard:     { backgroundColor: colors.surface3, borderRadius: 18, padding: 32, alignItems: 'center', gap: 8 },
  emptyIcon:     { fontSize: 36 },
  emptyTitle:    { fontFamily: fonts.displayBold, fontSize: 16, color: colors.ink },
  emptySub:      { fontSize: 12, color: colors.ink3, textAlign: 'center' },
  successBanner: { backgroundColor: 'rgba(52,211,153,0.10)', borderRadius: 12, padding: 12 },
  successText:   { fontSize: 12, color: colors.emerald },
  nomineeCard:   { backgroundColor: colors.surface3, borderRadius: 16, padding: 14, flexDirection: 'row', alignItems: 'center', gap: 12 },
  nomineeAvatar: { width: 40, height: 40, borderRadius: 12, backgroundColor: 'rgba(99,102,241,0.15)', alignItems: 'center', justifyContent: 'center' },
  nomineeInitial:{ fontFamily: fonts.displayBold, fontSize: 16, color: colors.indigo },
  nomineeName:   { fontFamily: fonts.bodySemiBold, fontSize: 13, color: colors.ink },
  nomineeRel:    { fontFamily: fonts.mono, fontSize: 10, color: colors.ink3, marginTop: 2 },
  nomineeDate:   { fontFamily: fonts.mono, fontSize: 10, color: colors.ink3 },
  removeBtn:     { borderWidth: 1, borderColor: 'rgba(251,113,133,0.3)', borderRadius: 10, paddingHorizontal: 10, paddingVertical: 6 },
  removeText:    { fontFamily: fonts.bodySemiBold, fontSize: 11, color: colors.rose },
  formCard:      { backgroundColor: colors.surface3, borderRadius: 18, padding: 16, gap: 0 },
  formTitle:     { fontFamily: fonts.displayBold, fontSize: 15, color: colors.ink, marginBottom: 14 },
  label:         { fontFamily: fonts.mono, fontSize: 10, color: colors.ink3, letterSpacing: 0.8, marginBottom: 6 },
  input:         { backgroundColor: colors.surface, borderRadius: 12, paddingHorizontal: 14, paddingVertical: 11, fontSize: 14, color: colors.ink, marginBottom: 14 },
  chip:          { borderWidth: 1, borderColor: colors.surface, borderRadius: 20, paddingHorizontal: 12, paddingVertical: 7, backgroundColor: colors.surface },
  chipActive:    { backgroundColor: colors.indigo, borderColor: colors.indigo },
  chipText:      { fontFamily: fonts.bodySemiBold, fontSize: 12, color: colors.ink2 },
  chipTextActive:{ color: '#FFF' },
  btn:           { flex: 1, borderRadius: 14, paddingVertical: 13, alignItems: 'center' },
  btnCancel:     { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.surface3 },
  btnCancelText: { fontFamily: fonts.bodySemiBold, fontSize: 13, color: colors.ink2 },
  btnSubmit:     { backgroundColor: colors.indigo },
  btnSubmitText: { fontFamily: fonts.displayBold, fontSize: 13, color: '#FFF' },
});
