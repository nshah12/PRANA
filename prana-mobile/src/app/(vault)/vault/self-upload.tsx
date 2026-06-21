/**
 * Self-upload screen — employee uploads their own document to the vault.
 *
 * Emotional job: "Your document. Your choice. Your vault."
 *
 * Flow:
 *  1. Pick file (PDF / image) via expo-document-picker
 *  2. Choose doc type + optional label
 *  3. Upload via POST /vault/documents/upload (multipart)
 *  4. Show animated progress → success → navigate to vault
 *
 * Privacy: password-protected PDFs handled server-side in-memory, nothing persisted.
 */
import React, { useState } from 'react';
import {
  View, Text, Pressable, StyleSheet, ScrollView,
  TextInput, ActivityIndicator,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import * as DocumentPicker from 'expo-document-picker';
import { colors, fonts, gradJourney } from '@/prana-theme/tokens';
import { api } from '@/lib/api';

// ── Doc type options ──────────────────────────────────────────────────────────

const DOC_TYPES = [
  { value: 'SALARY_SLIP',       label: 'Salary Slip',        emoji: '💰' },
  { value: 'FORM_16',           label: 'Form 16',            emoji: '🏛' },
  { value: 'INVESTMENT_PROOF',  label: 'Investment Proof',   emoji: '📊' },
  { value: 'IT_RETURN',         label: 'ITR',                emoji: '🇮🇳' },
  { value: 'BANK_STATEMENT',    label: 'Bank Statement',     emoji: '🏦' },
  { value: 'OFFER_LETTER',      label: 'Offer Letter',       emoji: '📄' },
  { value: 'JOINING_LETTER',    label: 'Joining Letter',     emoji: '🤝' },
  { value: 'APPRAISAL_LETTER',  label: 'Appraisal Letter',   emoji: '⭐' },
  { value: 'BONUS_LETTER',      label: 'Bonus Letter',       emoji: '🎁' },
  { value: 'PROMOTION_LETTER',  label: 'Promotion Letter',   emoji: '🚀' },
  { value: 'RELIEVING_LETTER',  label: 'Relieving Letter',   emoji: '👋' },
  { value: 'EXPERIENCE_LETTER', label: 'Experience Letter',  emoji: '📋' },
  { value: 'OTHER',             label: 'Other',              emoji: '📎' },
];

// ── File picker area ──────────────────────────────────────────────────────────

function FilePickerArea({
  file, onPick,
}: { file: DocumentPicker.DocumentPickerAsset | null; onPick: () => void }) {
  if (file) {
    const sizeKb = file.size ? Math.round(file.size / 1024) : null;
    const ext = (file.name ?? '').split('.').pop()?.toUpperCase() ?? 'DOC';
    return (
      <Pressable style={fp.filePicked} onPress={onPick}>
        <LinearGradient colors={['rgba(99,102,241,0.12)', 'rgba(99,102,241,0.06)']} style={fp.fileGrad}>
          <View style={fp.fileLeft}>
            <View style={fp.extChip}><Text style={fp.extText}>{ext}</Text></View>
            <View style={{ flex: 1 }}>
              <Text style={fp.fileName} numberOfLines={1}>{file.name}</Text>
              {sizeKb != null && (
                <Text style={fp.fileSize}>{sizeKb < 1024 ? `${sizeKb} KB` : `${(sizeKb / 1024).toFixed(1)} MB`}</Text>
              )}
            </View>
          </View>
          <Text style={fp.changeText}>Change</Text>
        </LinearGradient>
      </Pressable>
    );
  }
  return (
    <Pressable style={fp.dropzone} onPress={onPick}>
      <Text style={fp.dropIcon}>📎</Text>
      <Text style={fp.dropTitle}>Tap to pick a document</Text>
      <Text style={fp.dropSub}>PDF, JPG, PNG, HEIC — up to 20 MB</Text>
      <View style={fp.dropButton}>
        <Text style={fp.dropButtonText}>Browse files →</Text>
      </View>
    </Pressable>
  );
}
const fp = StyleSheet.create({
  dropzone: { borderWidth: 2, borderStyle: 'dashed', borderColor: 'rgba(99,102,241,0.3)', borderRadius: 18, padding: 28, alignItems: 'center', gap: 8, backgroundColor: 'rgba(99,102,241,0.04)' },
  dropIcon: { fontSize: 36, marginBottom: 4 },
  dropTitle: { fontFamily: fonts.bodySemiBold, fontSize: 14, color: colors.ink },
  dropSub: { fontFamily: fonts.mono, fontSize: 10, color: colors.ink3 },
  dropButton: { marginTop: 8, backgroundColor: 'rgba(99,102,241,0.12)', borderRadius: 10, paddingHorizontal: 16, paddingVertical: 8 },
  dropButtonText: { fontFamily: fonts.bodySemiBold, fontSize: 12, color: colors.indigo },
  filePicked: { borderRadius: 16, overflow: 'hidden', borderWidth: 1.5, borderColor: 'rgba(99,102,241,0.3)' },
  fileGrad: { flexDirection: 'row', alignItems: 'center', padding: 14, gap: 12 },
  fileLeft: { flexDirection: 'row', alignItems: 'center', gap: 10, flex: 1 },
  extChip: { backgroundColor: colors.indigo, borderRadius: 8, paddingHorizontal: 7, paddingVertical: 4, flexShrink: 0 },
  extText: { fontFamily: fonts.mono, fontSize: 10, fontWeight: '700', color: '#FFFFFF', letterSpacing: 1 },
  fileName: { fontFamily: fonts.bodySemiBold, fontSize: 13, color: colors.ink },
  fileSize: { fontFamily: fonts.mono, fontSize: 10, color: colors.ink3, marginTop: 2 },
  changeText: { fontFamily: fonts.bodySemiBold, fontSize: 12, color: colors.indigo, flexShrink: 0 },
});

// ── Upload progress bar ───────────────────────────────────────────────────────

function UploadProgress({ progress, done }: { progress: number; done: boolean }) {
  return (
    <View style={up.wrap}>
      <View style={up.header}>
        <Text style={up.label}>{done ? '✓  Uploaded to your vault' : 'Uploading…'}</Text>
        <Text style={up.pct}>{Math.round(progress * 100)}%</Text>
      </View>
      <View style={up.bar}>
        <LinearGradient
          colors={done ? (['#34D399', '#22D3EE'] as [string, string]) : ([...gradJourney.colors] as [string, string, ...string[]])}
          locations={done ? [0, 1] : gradJourney.locations}
          start={{ x: 0, y: 0 }}
          end={{ x: 1, y: 0 }}
          style={[up.fill, { width: `${Math.round(progress * 100)}%` as `${number}%` }]}
        />
      </View>
    </View>
  );
}
const up = StyleSheet.create({
  wrap: { gap: 8 },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  label: { fontFamily: fonts.bodySemiBold, fontSize: 13, color: colors.ink },
  pct: { fontFamily: fonts.mono, fontSize: 12, color: colors.indigo },
  bar: { height: 6, borderRadius: 3, backgroundColor: colors.surface3, overflow: 'hidden' },
  fill: { height: '100%', borderRadius: 3 },
});

// ── Screen ────────────────────────────────────────────────────────────────────

type UploadState = 'idle' | 'uploading' | 'done' | 'error';

export default function SelfUploadScreen() {
  const [file, setFile] = useState<DocumentPicker.DocumentPickerAsset | null>(null);
  const [docType, setDocType] = useState('');
  const [label, setLabel] = useState('');
  const [issuer, setIssuer] = useState('');
  const [isPasswordProtected, setIsPasswordProtected] = useState(false);
  const [docPassword, setDocPassword] = useState('');
  const [uploadState, setUploadState] = useState<UploadState>('idle');
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState('');

  async function pickFile() {
    try {
      const result = await DocumentPicker.getDocumentAsync({
        type: ['application/pdf', 'image/*'],
        copyToCacheDirectory: true,
        multiple: false,
      });
      if (!result.canceled && result.assets.length > 0) {
        setFile(result.assets[0]);
        setError('');
      }
    } catch {
      setError('Couldn\'t open file picker. Please try again.');
    }
  }

  async function handleUpload() {
    if (!file || !docType || uploadState === 'uploading') return;
    setError('');
    setUploadState('uploading');
    setProgress(0);

    try {
      const formData = new FormData();
      formData.append('file', {
        uri: file.uri,
        name: file.name ?? 'document.pdf',
        type: file.mimeType ?? 'application/octet-stream',
      } as unknown as Blob);
      formData.append('doc_type', docType);
      if (label.trim()) formData.append('label', label.trim());
      if (issuer.trim()) formData.append('issuer', issuer.trim());
      if (isPasswordProtected && docPassword) formData.append('doc_password', docPassword);

      // Simulate smooth progress ticks while multipart upload runs
      const interval = setInterval(() => {
        setProgress(p => Math.min(p + 0.06, 0.88));
      }, 280);

      await api.upload('/vault/documents/upload', formData, (pct) => {
        clearInterval(interval);
        setProgress(pct);
      });
      clearInterval(interval);
      setProgress(1);
      setUploadState('done');

      setTimeout(() => router.replace('/(vault)/vault'), 1400);
    } catch (e: unknown) {
      setUploadState('error');
      const msg = (e as { message?: string })?.message ?? '';
      setError(msg || 'Upload failed. Check your connection and try again.');
      setProgress(0);
    }
  }

  const canUpload = !!file && !!docType && uploadState !== 'uploading';

  return (
    <View style={s.screen}>
      {/* Header */}
      <LinearGradient colors={['#0B0F1E', '#131B33']} style={s.header}>
        <SafeAreaView edges={['top']}>
          <View style={s.headerRow}>
            <Pressable style={s.backBtn} onPress={() => router.back()}>
              <Text style={s.backIcon}>←</Text>
            </Pressable>
            <View style={{ flex: 1, marginLeft: 12 }}>
              <Text style={s.headerTitle}>Add to your vault</Text>
              <Text style={s.headerSub}>⬆  Your upload — your chain of custody</Text>
            </View>
          </View>
        </SafeAreaView>
      </LinearGradient>

      <ScrollView
        style={s.body}
        contentContainerStyle={s.bodyContent}
        showsVerticalScrollIndicator={false}
        keyboardShouldPersistTaps="handled"
      >
        {/* File pick */}
        <Text style={s.sectionLabel}>DOCUMENT FILE</Text>
        <FilePickerArea file={file} onPick={pickFile} />

        {/* Upload progress */}
        {(uploadState === 'uploading' || uploadState === 'done') && (
          <View style={{ marginTop: 12 }}>
            <UploadProgress progress={progress} done={uploadState === 'done'} />
          </View>
        )}

        {/* Doc type */}
        <Text style={[s.sectionLabel, { marginTop: 20 }]}>DOCUMENT TYPE  <Text style={s.required}>*</Text></Text>
        <View style={s.typeGrid}>
          {DOC_TYPES.map(dt => (
            <Pressable
              key={dt.value}
              style={[s.typeChip, docType === dt.value && s.typeChipActive]}
              onPress={() => setDocType(dt.value)}
            >
              <Text style={s.typeEmoji}>{dt.emoji}</Text>
              <Text style={[s.typeLabel, docType === dt.value && s.typeLabelActive]} numberOfLines={2}>{dt.label}</Text>
            </Pressable>
          ))}
        </View>

        {/* Issuer */}
        <Text style={[s.sectionLabel, { marginTop: 20 }]}>COMPANY / ISSUER  <Text style={s.optional}>(optional)</Text></Text>
        <TextInput
          value={issuer}
          onChangeText={setIssuer}
          placeholder="e.g. Infosys, SBI, HDFC Bank…"
          placeholderTextColor={colors.ink3}
          style={s.textInput}
        />

        {/* Label */}
        <Text style={[s.sectionLabel, { marginTop: 14 }]}>LABEL  <Text style={s.optional}>(optional)</Text></Text>
        <TextInput
          value={label}
          onChangeText={setLabel}
          placeholder="e.g. FY 2024–25, July salary…"
          placeholderTextColor={colors.ink3}
          style={s.textInput}
          maxLength={60}
        />

        {/* Password-protected PDF */}
        <Pressable
          style={[s.pwToggle, isPasswordProtected && s.pwToggleActive]}
          onPress={() => setIsPasswordProtected(v => !v)}
        >
          <View style={[s.pwCheckbox, isPasswordProtected && s.pwCheckboxOn]}>
            {isPasswordProtected && <Text style={s.pwCheck}>✓</Text>}
          </View>
          <View>
            <Text style={s.pwLabel}>This PDF is password-protected</Text>
            <Text style={s.pwSub}>Password used in-memory only — never stored</Text>
          </View>
        </Pressable>
        {isPasswordProtected && (
          <TextInput
            value={docPassword}
            onChangeText={setDocPassword}
            placeholder="PDF password…"
            placeholderTextColor={colors.ink3}
            secureTextEntry
            style={[s.textInput, { marginTop: 8 }]}
          />
        )}

        {/* Privacy note */}
        <View style={s.privacyNote}>
          <Text style={s.privacyText}>🔒  PRANA's AI pipeline extracts insights only — no salary figures are stored. Your document is encrypted with your personal key and stays in your vault.</Text>
        </View>

        {error ? <Text style={s.error}>{error}</Text> : null}

        {/* CTA */}
        <Pressable onPress={handleUpload} disabled={!canUpload}>
          <LinearGradient
            colors={gradJourney.colors}
            locations={gradJourney.locations}
            start={gradJourney.start}
            end={gradJourney.end}
            style={[s.uploadBtn, !canUpload && { opacity: 0.4 }]}
          >
            {uploadState === 'uploading'
              ? <ActivityIndicator size="small" color="#04261C" />
              : <Text style={s.uploadBtnText}>
                  {!file ? 'Pick a document first'
                    : !docType ? 'Choose document type'
                    : 'Add to vault →'}
                </Text>
            }
          </LinearGradient>
        </Pressable>
      </ScrollView>
    </View>
  );
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.surface },
  header: { paddingHorizontal: 16, paddingBottom: 14 },
  headerRow: { flexDirection: 'row', alignItems: 'center', paddingTop: 10 },
  backBtn: { width: 36, height: 36, borderRadius: 10, backgroundColor: 'rgba(255,255,255,0.08)', alignItems: 'center', justifyContent: 'center' },
  backIcon: { fontSize: 16, color: '#FFFFFF' },
  headerTitle: { fontFamily: fonts.displayBold, fontSize: 17, color: '#FFFFFF', letterSpacing: -0.2 },
  headerSub: { fontFamily: fonts.mono, fontSize: 10, color: '#9CA8C9', marginTop: 2 },
  body: { flex: 1 },
  bodyContent: { padding: 16, paddingBottom: 48 },
  sectionLabel: { fontFamily: fonts.mono, fontSize: 10, fontWeight: '700', color: colors.ink3, letterSpacing: 1.2, marginBottom: 10 },
  required: { color: colors.rose },
  optional: { fontWeight: '400', color: colors.ink3 },
  typeGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  typeChip: { width: '30%', borderWidth: 1.5, borderColor: colors.surface3, borderRadius: 14, padding: 10, alignItems: 'center', backgroundColor: colors.surface3, gap: 4 },
  typeChipActive: { borderColor: colors.indigo, backgroundColor: 'rgba(99,102,241,0.08)' },
  typeEmoji: { fontSize: 20 },
  typeLabel: { fontFamily: fonts.bodyRegular, fontSize: 10, color: colors.ink2, textAlign: 'center' },
  typeLabelActive: { color: colors.indigo, fontFamily: fonts.bodySemiBold },
  textInput: { borderWidth: 1.5, borderColor: colors.surface3, borderRadius: 12, padding: 13, fontFamily: fonts.bodyRegular, fontSize: 13, color: colors.ink, backgroundColor: colors.surface3 },
  pwToggle: { flexDirection: 'row', alignItems: 'center', gap: 12, padding: 12, borderRadius: 14, borderWidth: 1.5, borderColor: colors.surface3, backgroundColor: colors.surface3, marginTop: 14 },
  pwToggleActive: { borderColor: 'rgba(99,102,241,0.4)', backgroundColor: 'rgba(99,102,241,0.05)' },
  pwCheckbox: { width: 22, height: 22, borderRadius: 6, borderWidth: 2, borderColor: colors.ink3, alignItems: 'center', justifyContent: 'center', flexShrink: 0 },
  pwCheckboxOn: { backgroundColor: colors.indigo, borderColor: colors.indigo },
  pwCheck: { fontSize: 12, color: '#FFFFFF', fontWeight: '700' },
  pwLabel: { fontFamily: fonts.bodySemiBold, fontSize: 13, color: colors.ink, marginBottom: 2 },
  pwSub: { fontFamily: fonts.mono, fontSize: 9, color: colors.ink3 },
  privacyNote: { backgroundColor: 'rgba(52,211,153,0.07)', borderWidth: 1, borderColor: 'rgba(52,211,153,0.16)', borderRadius: 12, padding: 12, marginVertical: 16 },
  privacyText: { fontFamily: fonts.mono, fontSize: 10, color: '#047857', lineHeight: 17 },
  error: { fontFamily: fonts.bodyMedium, fontSize: 12, color: colors.rose, textAlign: 'center', marginBottom: 12 },
  uploadBtn: { borderRadius: 16, height: 56, alignItems: 'center', justifyContent: 'center' },
  uploadBtnText: { fontFamily: fonts.displayBold, fontSize: 15, color: '#04261C' },
});
