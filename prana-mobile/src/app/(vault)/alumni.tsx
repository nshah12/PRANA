import React, { useState } from 'react';
import {
  View, Text, Pressable, StyleSheet, ScrollView,
  ActivityIndicator, Switch, FlatList, TextInput,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { colors, fonts } from '@/prana-theme/tokens';
import { api } from '@/lib/api';

type PastEmployer = {
  tenant_id:    string;
  employee_uuid: string;
  company_name: string;
  designation:  string;
  department:   string;
  doj:          string;
  dol:          string;
  tenure_band:  string;
  granted:      boolean;
  share_mobile: boolean;
  share_email:  boolean;
};

type OutreachMsg = {
  outreach_id:  string;
  company_name: string;
  subject:      string;
  body_text:    string;
  status:       string;
  sent_at:      string;
  read_at:      string | null;
  reply_body:   string | null;
  replied_at:   string | null;
};

const STATUS_COLOR: Record<string, string> = {
  SENT:      '#0EA5E9',
  READ:      '#10B981',
  REPLIED:   '#7C3AED',
  IGNORED:   '#94A3B8',
  OPTED_OUT: '#EF4444',
};

export default function AlumniScreen() {
  const qc = useQueryClient();
  const [tab, setTab] = useState<'consent' | 'inbox'>('consent');
  const [expanded, setExpanded] = useState<string | null>(null);
  const [replyText, setReplyText] = useState<Record<string, string>>({});

  const { data: employersData, isLoading: empLoading } = useQuery({
    queryKey: ['alumni-employers'],
    queryFn:  () => api.get('/v1/alumni/employers').then(r => r.data),
  });

  const { data: outreachData, isLoading: inboxLoading } = useQuery({
    queryKey: ['alumni-outreach'],
    queryFn:  () => api.get('/v1/alumni/outreach').then(r => r.data),
    enabled:  tab === 'inbox',
  });

  const consentMutation = useMutation({
    mutationFn: (body: { tenant_id: string; granted: boolean; share_mobile: boolean; share_email: boolean }) =>
      api.post('/v1/alumni/consent', body).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alumni-employers'] }),
  });

  const readMutation = useMutation({
    mutationFn: (outreach_id: string) =>
      api.post(`/v1/alumni/outreach/${outreach_id}/read`).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alumni-outreach'] }),
  });

  const replyMutation = useMutation({
    mutationFn: ({ outreach_id, body }: { outreach_id: string; body: string }) =>
      api.post(`/v1/alumni/outreach/${outreach_id}/reply`, { body }).then(r => r.data),
    onSuccess: (_data, vars) => {
      setReplyText(prev => { const next = { ...prev }; delete next[vars.outreach_id]; return next; });
      qc.invalidateQueries({ queryKey: ['alumni-outreach'] });
    },
  });

  const employers: PastEmployer[] = employersData?.items ?? [];
  const messages:  OutreachMsg[]  = outreachData?.items ?? [];
  const unreadCount = messages.filter(m => m.status === 'SENT').length;

  function toggleConsent(emp: PastEmployer, granted: boolean) {
    consentMutation.mutate({
      tenant_id:    emp.tenant_id,
      granted,
      share_mobile: emp.share_mobile,
      share_email:  emp.share_email,
    });
  }

  function toggleShareField(emp: PastEmployer, field: 'share_mobile' | 'share_email', val: boolean) {
    consentMutation.mutate({
      tenant_id:    emp.tenant_id,
      granted:      emp.granted,
      share_mobile: field === 'share_mobile' ? val : emp.share_mobile,
      share_email:  field === 'share_email'  ? val : emp.share_email,
    });
  }

  function handleMessageTap(msg: OutreachMsg) {
    const isExpanded = expanded === msg.outreach_id;
    setExpanded(isExpanded ? null : msg.outreach_id);
    if (!isExpanded && msg.status === 'SENT') {
      readMutation.mutate(msg.outreach_id);
    }
  }

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} style={styles.back}>
          <Text style={styles.backText}>‹</Text>
        </Pressable>
        <Text style={styles.title}>Alumni Connect</Text>
      </View>

      {/* Tabs */}
      <View style={styles.tabs}>
        <Pressable
          style={[styles.tab, tab === 'consent' && styles.tabActive]}
          onPress={() => setTab('consent')}
        >
          <Text style={[styles.tabText, tab === 'consent' && styles.tabTextActive]}>
            Past Employers
          </Text>
        </Pressable>
        <Pressable
          style={[styles.tab, tab === 'inbox' && styles.tabActive]}
          onPress={() => setTab('inbox')}
        >
          <Text style={[styles.tabText, tab === 'inbox' && styles.tabTextActive]}>
            Inbox {unreadCount > 0 ? `(${unreadCount})` : ''}
          </Text>
          {unreadCount > 0 && <View style={styles.badge}><Text style={styles.badgeText}>{unreadCount}</Text></View>}
        </Pressable>
      </View>

      {/* Past Employers tab */}
      {tab === 'consent' && (
        <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
          {/* Explanation */}
          <View style={styles.infoBox}>
            <Text style={styles.infoTitle}>You control who can find you</Text>
            <Text style={styles.infoText}>
              Toggle on for each past employer whose CHRO you're happy to hear from.
              They'll see your name, designation and tenure. Mobile/email only if you allow it.
            </Text>
          </View>

          {empLoading && (
            <ActivityIndicator size="large" color={colors.sky ?? '#0EA5E9'} style={{ marginTop: 40 }} />
          )}

          {!empLoading && employers.length === 0 && (
            <View style={styles.emptyBox}>
              <Text style={styles.emptyIcon}>🏢</Text>
              <Text style={styles.emptyTitle}>No past employers found</Text>
              <Text style={styles.emptySub}>
                Past employers appear here once your documents have been processed.
              </Text>
            </View>
          )}

          {employers.map(emp => (
            <View key={emp.tenant_id} style={styles.employerCard}>
              {/* Company + tenure */}
              <View style={styles.employerHeader}>
                <View style={styles.companyAvatar}>
                  <Text style={styles.companyInitial}>{emp.company_name.charAt(0)}</Text>
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.companyName}>{emp.company_name}</Text>
                  <Text style={styles.companyMeta}>
                    {emp.designation}{emp.department ? ` · ${emp.department}` : ''}
                  </Text>
                  <Text style={styles.tenureLine}>
                    {emp.doj} → {emp.dol} · {emp.tenure_band}
                  </Text>
                </View>
                {/* Master consent toggle */}
                <Switch
                  value={emp.granted}
                  onValueChange={v => toggleConsent(emp, v)}
                  trackColor={{ true: '#10B981', false: '#CBD5E1' }}
                  thumbColor="#FFFFFF"
                  disabled={consentMutation.isPending}
                />
              </View>

              {/* Sub-options — only visible when consented */}
              {emp.granted && (
                <View style={styles.shareOptions}>
                  <Text style={styles.shareOptionsLabel}>What to share with their CHRO:</Text>

                  <View style={styles.shareRow}>
                    <Text style={styles.shareRowLabel}>📱 Mobile number</Text>
                    <Switch
                      value={emp.share_mobile}
                      onValueChange={v => toggleShareField(emp, 'share_mobile', v)}
                      trackColor={{ true: '#0EA5E9', false: '#CBD5E1' }}
                      thumbColor="#FFFFFF"
                      disabled={consentMutation.isPending}
                    />
                  </View>

                  <View style={styles.shareRow}>
                    <Text style={styles.shareRowLabel}>✉️ Email address</Text>
                    <Switch
                      value={emp.share_email}
                      onValueChange={v => toggleShareField(emp, 'share_email', v)}
                      trackColor={{ true: '#0EA5E9', false: '#CBD5E1' }}
                      thumbColor="#FFFFFF"
                      disabled={consentMutation.isPending}
                    />
                  </View>

                  <Text style={styles.shareNote}>
                    Name, designation, city, and tenure dates are always shared when you're opted in.
                    Toggle off above to hide your contact details.
                  </Text>
                </View>
              )}
            </View>
          ))}
        </ScrollView>
      )}

      {/* Inbox tab */}
      {tab === 'inbox' && (
        <>
          {inboxLoading && (
            <ActivityIndicator size="large" color={colors.sky ?? '#0EA5E9'} style={{ marginTop: 40 }} />
          )}

          {!inboxLoading && messages.length === 0 && (
            <View style={[styles.emptyBox, { marginTop: 60 }]}>
              <Text style={styles.emptyIcon}>💬</Text>
              <Text style={styles.emptyTitle}>No messages yet</Text>
              <Text style={styles.emptySub}>
                When a past employer's CHRO sends you an in-app message, it appears here.
                They can also reach you directly via mobile/email if you've shared those.
              </Text>
            </View>
          )}

          <FlatList
            data={messages}
            keyExtractor={m => m.outreach_id}
            contentContainerStyle={styles.content}
            renderItem={({ item: msg }) => {
              const isExpanded = expanded === msg.outreach_id;
              const isUnread   = msg.status === 'SENT';
              return (
                <Pressable
                  onPress={() => handleMessageTap(msg)}
                  style={[styles.msgCard, isUnread && styles.msgCardUnread]}
                >
                  <View style={styles.msgHeader}>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.msgCompany}>{msg.company_name}</Text>
                      <Text style={[styles.msgSubject, isUnread && styles.msgSubjectUnread]}>
                        {msg.subject}
                      </Text>
                    </View>
                    <View style={{ alignItems: 'flex-end', gap: 4 }}>
                      <View style={[styles.statusDot, { backgroundColor: STATUS_COLOR[msg.status] ?? '#94A3B8' }]} />
                      <Text style={styles.msgDate}>
                        {new Date(msg.sent_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}
                      </Text>
                    </View>
                  </View>
                  {isExpanded && (
                    <View style={styles.expandedBody}>
                      <Text style={styles.msgBody}>{msg.body_text}</Text>

                      {msg.replied_at ? (
                        /* Already replied — show it */
                        <View style={styles.repliedBox}>
                          <Text style={styles.repliedLabel}>Your reply</Text>
                          <Text style={styles.repliedText}>{msg.reply_body}</Text>
                          <Text style={styles.repliedDate}>
                            Sent {new Date(msg.replied_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}
                          </Text>
                        </View>
                      ) : (
                        /* Reply composer */
                        <View style={styles.replyBox}>
                          <TextInput
                            style={styles.replyInput}
                            placeholder="Write a reply…"
                            placeholderTextColor="#94A3B8"
                            multiline
                            value={replyText[msg.outreach_id] ?? ''}
                            onChangeText={t => setReplyText(prev => ({ ...prev, [msg.outreach_id]: t }))}
                          />
                          <Pressable
                            style={[
                              styles.replyBtn,
                              (!replyText[msg.outreach_id]?.trim() || replyMutation.isPending)
                                && styles.replyBtnDim,
                            ]}
                            onPress={() => {
                              const body = replyText[msg.outreach_id]?.trim();
                              if (body) replyMutation.mutate({ outreach_id: msg.outreach_id, body });
                            }}
                            disabled={!replyText[msg.outreach_id]?.trim() || replyMutation.isPending}
                          >
                            <Text style={styles.replyBtnText}>
                              {replyMutation.isPending ? 'Sending…' : 'Send reply'}
                            </Text>
                          </Pressable>
                        </View>
                      )}
                    </View>
                  )}
                </Pressable>
              );
            }}
          />
        </>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe:   { flex: 1, backgroundColor: '#F8FAFC' },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 12, gap: 8, borderBottomWidth: 1, borderBottomColor: '#E2E8F0' },
  back:   { padding: 4 },
  backText: { fontSize: 24, color: '#475569', lineHeight: 28 },
  title:  { fontSize: 17, fontFamily: fonts.displayBold, color: '#0F172A' },

  tabs:        { flexDirection: 'row', borderBottomWidth: 1, borderBottomColor: '#E2E8F0', backgroundColor: '#FFFFFF' },
  tab:         { flex: 1, alignItems: 'center', paddingVertical: 12, flexDirection: 'row', justifyContent: 'center', gap: 6 },
  tabActive:   { borderBottomWidth: 2, borderBottomColor: '#0EA5E9' },
  tabText:     { fontSize: 14, color: '#94A3B8', fontFamily: fonts.bodySemiBold },
  tabTextActive: { color: '#0EA5E9' },
  badge:       { backgroundColor: '#EF4444', borderRadius: 8, minWidth: 16, height: 16, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 4 },
  badgeText:   { fontSize: 10, color: '#FFFFFF', fontFamily: fonts.bodySemiBold },

  content: { padding: 16, paddingBottom: 40, gap: 12 },

  infoBox:   { backgroundColor: '#EFF6FF', borderRadius: 12, padding: 14, borderWidth: 1, borderColor: '#BFDBFE' },
  infoTitle: { fontSize: 13, fontFamily: fonts.bodySemiBold, color: '#1D4ED8', marginBottom: 4 },
  infoText:  { fontSize: 12, color: '#3B82F6', lineHeight: 17 },

  emptyBox:  { alignItems: 'center', paddingVertical: 40, paddingHorizontal: 24 },
  emptyIcon: { fontSize: 36, marginBottom: 12 },
  emptyTitle:{ fontSize: 15, fontFamily: fonts.bodySemiBold, color: '#334155', marginBottom: 6 },
  emptySub:  { fontSize: 13, color: '#64748B', textAlign: 'center', lineHeight: 19 },

  employerCard: {
    backgroundColor: '#FFFFFF', borderRadius: 16, padding: 16,
    shadowColor: '#000', shadowOpacity: 0.04, shadowRadius: 8, elevation: 2,
  },
  employerHeader: { flexDirection: 'row', alignItems: 'flex-start', gap: 12 },
  companyAvatar:  { width: 40, height: 40, borderRadius: 12, backgroundColor: '#E0F2FE', alignItems: 'center', justifyContent: 'center' },
  companyInitial: { fontSize: 16, fontFamily: fonts.displayBold, color: '#0369A1' },
  companyName:    { fontSize: 14, fontFamily: fonts.bodySemiBold, color: '#0F172A' },
  companyMeta:    { fontSize: 12, color: '#64748B', marginTop: 1 },
  tenureLine:     { fontSize: 11, color: '#94A3B8', marginTop: 2, fontFamily: fonts.mono },

  shareOptions:      { marginTop: 12, paddingTop: 12, borderTopWidth: 1, borderTopColor: '#F1F5F9', gap: 8 },
  shareOptionsLabel: { fontSize: 11, color: '#94A3B8', fontFamily: fonts.mono, letterSpacing: 0.5, marginBottom: 2 },
  shareRow:          { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  shareRowLabel:     { fontSize: 13, color: '#475569' },
  shareNote:         { fontSize: 11, color: '#94A3B8', lineHeight: 16, marginTop: 4 },

  msgCard:        { backgroundColor: '#FFFFFF', borderRadius: 14, padding: 14, shadowColor: '#000', shadowOpacity: 0.03, shadowRadius: 6, elevation: 1 },
  msgCardUnread:  { borderLeftWidth: 3, borderLeftColor: '#0EA5E9' },
  msgHeader:      { flexDirection: 'row', alignItems: 'flex-start', gap: 10 },
  msgCompany:     { fontSize: 11, color: '#94A3B8', fontFamily: fonts.mono, marginBottom: 2 },
  msgSubject:     { fontSize: 14, color: '#475569' },
  msgSubjectUnread: { color: '#0F172A', fontFamily: fonts.bodySemiBold },
  statusDot:      { width: 8, height: 8, borderRadius: 4 },
  msgDate:        { fontSize: 11, color: '#CBD5E1' },
  msgBody:        { marginTop: 10, fontSize: 13, color: '#334155', lineHeight: 20, paddingTop: 10, borderTopWidth: 1, borderTopColor: '#F1F5F9' },

  expandedBody: { gap: 12 },

  // Already replied
  repliedBox:   { backgroundColor: '#F0FDF4', borderRadius: 10, padding: 12, borderWidth: 1, borderColor: '#BBF7D0' },
  repliedLabel: { fontSize: 10, color: '#16A34A', fontFamily: fonts.mono, letterSpacing: 0.5, marginBottom: 4 },
  repliedText:  { fontSize: 13, color: '#166534', lineHeight: 18 },
  repliedDate:  { fontSize: 11, color: '#4ADE80', marginTop: 4 },

  // Reply composer
  replyBox:     { gap: 8 },
  replyInput:   {
    borderWidth: 1, borderColor: '#E2E8F0', borderRadius: 10,
    padding: 10, fontSize: 13, color: '#0F172A', minHeight: 72,
    textAlignVertical: 'top', backgroundColor: '#F8FAFC',
  },
  replyBtn:     { alignSelf: 'flex-end', backgroundColor: '#0EA5E9', borderRadius: 10, paddingHorizontal: 16, paddingVertical: 8 },
  replyBtnDim:  { backgroundColor: '#CBD5E1' },
  replyBtnText: { fontSize: 13, fontFamily: fonts.bodySemiBold, color: '#FFFFFF' },
});
