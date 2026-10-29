import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { Image, Modal, Platform, Pressable, StyleSheet, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { Icon } from '@/components/Icon';
import { Button, Disclaimer, Screen } from '@/components/layout';
import { Colors, Gutter, MaxAppWidth, Radius } from '@/constants/theme';
import { recordDocs, siteCheckDemo, type RecordDoc } from '@/data/demo';
import {
  ApiError,
  apiEnabled,
  deleteEvidence,
  evidenceSource,
  uploadEvidence,
  type ApiContract,
  type ApiTodo,
} from '@/lib/api';
import { contractToken, setLatestContract, useLatestContract } from '@/lib/contract';
import { pickEvidence, type EvidenceSource } from '@/lib/evidence';
import { siteCheckItems, useSiteCheck } from '@/lib/site-check';
import { specialTermRules, useSpecialTermResults, type SpecialTermResult } from '@/lib/special-terms';

/** 기록함 칸 하나. todo가 있으면 그 할 일의 증빙(서버)이라 눌러서 보고·올리고·지운다 */
type Slot = RecordDoc & { key: string; todo?: ApiTodo };

/**
 * 반환보증 청구·임차권등기명령에 필요한 서류를 남기는 할 일. 반환 대응 단계별 서류(todos.yaml return_response
 * documents, #52)와 같게: 확정일자 받은 계약서(T4)·임대차 신고필증(T1)·보증서(T5)와 반환 대응 단계의 증빙
 */
const CLAIM_TODOS = new Set(['T1', 'T4', 'T5', 'R1', 'R2', 'R3']);

/**
 * 할 일별 증빙 사진 버전. 다시 올리거나 지울 때마다 올려 사진 주소(?v=)를 바꾼다. 창 밖에 두어 창을 닫았다 다시 열어도
 * 앞 사진 주소로 돌아가지 않게, 앞에 앱 실행마다 다른 값을 붙여 앱을 다시 켠 뒤에도 휴대폰 캐시와 겹치지 않게 (#122 리뷰 1번)
 */
const LAUNCH = Date.now().toString(36);
const evidenceVersions = new Map<number, number>();
const bumpVersion = (todoId: number) => {
  const v = (evidenceVersions.get(todoId) ?? 0) + 1;
  evidenceVersions.set(todoId, v);
  return v;
};

/** "2026-10-20" → "10.20" */
const md = (s: string) => `${Number(s.slice(5, 7))}.${s.slice(8, 10)}`;

/** T1~T9 먼저 번호순, 그 뒤 반환 대응(R1~) */
const ruleOrder = (id: string) => (id.startsWith('T') ? 0 : 100) + Number(id.slice(1));

function slotMeta(t: ApiTodo): string {
  const which = t.rule_id.startsWith('T') ? `${t.rule_id.slice(1)}번 할 일` : '반환 대응';
  if (t.evidence_uploaded) return t.done_date ? `${md(t.done_date)} · ${which}` : which;
  if (t.status === 'skipped') return '나중에 올리기';
  if (t.due_date) return `${md(t.due_date)}까지 · ${which}`;
  return which;
}

/** 계약의 할 일 중 증빙이 있는 것 → 기록함 칸 (FR-031). 할 일을 끝낼 때 올린 사진이 여기 쌓인다 */
function slotsFromContract(contract: ApiContract): Slot[] {
  return contract.todos
    .filter((t): t is ApiTodo & { evidence: string } => t.evidence !== null)
    .sort((a, b) => ruleOrder(a.rule_id) - ruleOrder(b.rule_id))
    .map((t) => ({
      key: `todo-${t.id}`,
      name: t.evidence,
      meta: slotMeta(t),
      filled: t.evidence_uploaded,
      needForClaim: CLAIM_TODOS.has(t.rule_id),
      todo: t,
    }));
}

/**
 * 계약 당일 "넣음"으로 고른 특약이 요구하는 서류 (special_terms.yaml on_inserted require_document).
 * 올릴 서버 칸이 아직 없어(첫 계약 서류 #46) 빈칸으로만 보여 준다
 */
function termSlots(results: Partial<Record<string, SpecialTermResult>>): Slot[] {
  const names = specialTermRules
    .filter((t) => results[t.id] === 'inserted')
    .flatMap((t) => t.ifInserted.documents);
  return [...new Set(names)].map((name) => ({ key: `term-${name}`, name, meta: '계약 당일', filled: false, needForClaim: true }));
}

/**
 * UI-05 전세 기록함: 평소엔 계약 기록, 비상 모드에선 청구에 빠진 서류만 빨간 칸으로.
 * 계약이 있으면 할 일 증빙(GET·POST·DELETE /api/todos/{id}/evidence)으로 칸을 채우고, 없으면 시연 데이터
 */
export default function RecordsScreen() {
  const [emergency, setEmergency] = useState(false);
  const latest = useLatestContract();
  const contract = apiEnabled ? latest : null;
  const localTerms = useSpecialTermResults();
  const termDocs = termSlots(contract ? contract.special_term_result : localTerms);
  const docs: Slot[] = contract
    ? [...slotsFromContract(contract), ...termDocs]
    : [...recordDocs.map((d) => ({ ...d, key: d.name })), ...termDocs];
  const missing = docs.filter((d) => d.needForClaim && !d.filled).length;
  // 열어 본 칸 (할 일 id). 올리거나 지워 계약이 바뀌어도 같은 할 일을 다시 찾아 그린다
  const [openId, setOpenId] = useState<number | null>(null);
  const opened = docs.find((d) => d.todo?.id === openId) ?? null;

  return (
    <Screen inTabs>
      <AppText size={22} weight="bold" style={{ marginTop: 20 }}>
        전세 기록함
      </AppText>
      <AppText size={13} color={Colors.textSub} style={{ marginTop: 4 }}>
        할 일을 완료할 때 남긴 증빙이 여기 쌓여요
      </AppText>

      <View style={styles.segment} accessibilityRole="tablist">
        <SegmentButton label="평소 · 계약 기록" on={!emergency} onPress={() => setEmergency(false)} />
        <SegmentButton label="비상 · 못 돌려받을 때" on={emergency} danger onPress={() => setEmergency(true)} />
      </View>

      {emergency ? (
        <Pressable onPress={() => router.push('/return')} style={styles.alert}>
          <AppText size={14} weight="bold" color={Colors.dangerDeep}>
            반환보증 청구에 빠진 서류 {missing}개
          </AppText>
          <AppText size={13} color={Colors.dangerText} leading={1.6} style={{ marginTop: 4 }}>
            빨간 칸부터 채우세요. 반환 대응 안내에서 다음 단계를 볼 수 있어요.
          </AppText>
        </Pressable>
      ) : null}

      {!emergency ? <SiteCheckRecord /> : null}

      <View style={styles.grid}>
        {docs.map((d) => {
          const todoId = d.todo?.id;
          return (
            <DocSlot
              key={d.key}
              doc={d}
              emergency={emergency}
              onPress={todoId !== undefined ? () => setOpenId(todoId) : undefined}
            />
          );
        })}
      </View>

      <View style={{ flex: 1 }} />
      <Disclaimer>반환 확인 후 3개월 동안 보관해요. 주민등록번호는 가리고 올려 주세요.</Disclaimer>

      {contract && opened?.todo ? (
        <EvidenceSheet contract={contract} slot={opened} todo={opened.todo} onClose={() => setOpenId(null)} />
      ) : null}
    </Screen>
  );
}

/** 계약 당일 현장 확인 기록 (FR-047). 체크하지 않은 항목은 "확인 안 함"으로 남긴다 */
function SiteCheckRecord() {
  const items = siteCheckItems(useSiteCheck() ?? siteCheckDemo);
  const missed = items.filter((i) => !i.checked);
  return (
    <View style={styles.siteCheck}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
        <AppText size={13} weight="semibold">
          계약 당일 현장 확인
        </AppText>
        <AppText size={12} weight="semibold" color={missed.length ? Colors.caution : Colors.ok}>
          {items.length}개 중 {items.length - missed.length}개 확인
        </AppText>
      </View>
      {missed.map((m) => (
        <AppText key={m.label} size={12} color={Colors.caution} style={{ marginTop: 4 }}>
          확인 안 함 · {m.label}
        </AppText>
      ))}
    </View>
  );
}

/**
 * 기록함 칸을 눌렀을 때: 올린 증빙 보기·다시 올리기·지우기, 빈칸이면 올리기.
 * 올리면 그 할 일을 끝낸다 (할 일 탭과 같은 POST /api/todos/{id}/evidence, 끝낼 수 있는 조건도 같음).
 * 지우면 완료는 그대로 두고 "나중에 올리기"로 바뀐다 (FR-033). 무산된 계약은 보기·지우기만
 */
function EvidenceSheet({
  contract,
  slot,
  todo,
  onClose,
}: {
  contract: ApiContract;
  slot: Slot;
  todo: ApiTodo;
  onClose: () => void;
}) {
  const token = contractToken(contract.id);
  const active = contract.status !== 'cancelled';
  const [busy, setBusy] = useState(false);
  // 사진을 고르는 중 / 서버에 보내는 중 (버튼 문구를 나눠 보여 준다, #122 리뷰 3번)
  const [phase, setPhase] = useState<'picking' | 'uploading' | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [version, setVersion] = useState(() => evidenceVersions.get(todo.id) ?? 0);

  const run = async (call: () => Promise<ApiContract | null>) => {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await call();
      if (updated) {
        setLatestContract(updated);
        setVersion(bumpVersion(todo.id));
      }
    } catch (e) {
      const message =
        e instanceof ApiError ? [e.message, e.hint].filter(Boolean).join('. ') : e instanceof Error ? e.message : '';
      setError(message || '증빙을 바꾸지 못했어요');
    } finally {
      setBusy(false);
      setPhase(null);
      setConfirmDelete(false);
    }
  };
  const upload = (source: EvidenceSource) =>
    run(async () => {
      setPhase('picking');
      const file = await pickEvidence(source);
      if (!file) return null;
      setPhase('uploading');
      return uploadEvidence(todo.id, token, file);
    });
  // 기록함에서 올려도 할 일이 끝난다는 것을 미리 알린다 (#122 리뷰 2번)
  const which = todo.rule_id.startsWith('T') ? `${todo.rule_id.slice(1)}번 할 일` : '이 반환 대응 단계';
  const uploadNote = todo.evidence_uploaded
    ? '다시 올리면 앞 사진을 바꿔요.'
    : todo.status === 'skipped'
      ? `올리면 나중에 올리기로 끝낸 ${which}의 기록함이 채워져요.`
      : `올리면 ${which}${todo.rule_id.startsWith('T') ? '이' : '가'} 끝나요. 할 일 탭에서 끝내는 것과 같아요.`;
  // 확인 창(Alert)은 웹에서 동작하지 않아 한 번 더 누르게 한다
  const remove = () => {
    if (!confirmDelete) {
      setConfirmDelete(true);
      return;
    }
    run(() => deleteEvidence(todo.id, token));
  };
  const close = () => {
    if (!busy) onClose();
  };

  return (
    <Modal visible transparent animationType="slide" onRequestClose={close}>
      <Pressable accessibilityLabel="닫기" style={styles.backdrop} onPress={close} />
      <View style={styles.sheet}>
        <View style={styles.grabber} />
        <AppText size={18} weight="bold">
          {slot.name}
        </AppText>
        <AppText size={13} color={Colors.textSub} style={{ marginTop: 4 }}>
          {todo.title} · {slot.meta}
        </AppText>

        {todo.evidence_uploaded ? (
          <EvidenceImage todoId={todo.id} token={token} version={`${LAUNCH}-${todo.done_date ?? ''}-${version}`} />
        ) : (
          <View style={[styles.preview, styles.previewEmpty]}>
            <AppText size={13} color={Colors.textSub}>
              {todo.status === 'skipped' ? '나중에 올리기로 끝낸 할 일이에요' : '아직 올린 증빙이 없어요'}
            </AppText>
          </View>
        )}

        {error ? (
          <AppText size={13} color={Colors.danger} leading={1.6} style={{ marginTop: 12 }}>
            {error}
          </AppText>
        ) : null}

        {active ? (
          <AppText size={12} color={Colors.textSub} leading={1.6} style={{ marginTop: 14 }}>
            {uploadNote}
          </AppText>
        ) : null}
        {active ? (
          <View style={{ flexDirection: 'row', gap: 8, marginTop: 10 }}>
            <Button
              label={
                phase === 'picking'
                  ? '사진 고르는 중…'
                  : phase === 'uploading'
                    ? '올리는 중…'
                    : todo.evidence_uploaded
                      ? '다시 찍기'
                      : '사진 찍기'
              }
              onPress={() => upload('camera')}
              style={{ flex: 1, opacity: busy ? 0.6 : 1 }}
            />
            <Button label="앨범에서 고르기" variant="outline" onPress={() => upload('library')} style={{ flex: 1 }} />
          </View>
        ) : (
          <AppText size={13} color={Colors.textSub} style={{ marginTop: 16 }}>
            무산된 계약이라 증빙을 새로 올릴 수 없어요. 지우기는 할 수 있어요.
          </AppText>
        )}
        {todo.evidence_uploaded ? (
          <Pressable accessibilityRole="button" onPress={remove} style={styles.textButton}>
            <AppText size={14} weight="semibold" color={Colors.danger}>
              {confirmDelete ? '한 번 더 누르면 지워요 (할 일은 완료로 남아요)' : '증빙 지우기'}
            </AppText>
          </Pressable>
        ) : null}
        <Pressable accessibilityRole="button" onPress={close} style={styles.textButton}>
          <AppText size={14} weight="semibold" color={Colors.textSub}>
            닫기
          </AppText>
        </Pressable>
      </View>
    </Modal>
  );
}

/**
 * 올린 증빙 사진. 휴대폰은 Image source에 계약 토큰 헤더를 붙이고, 웹(개발 편의용)은 Image에 헤더를 붙일 수 없어
 * fetch로 받아 blob 주소로 보여 준다. 사진이 아닌 파일(PDF 등)은 미리 보지 못한다고 안내
 */
function EvidenceImage({ todoId, token, version }: { todoId: number; token: string | null; version: string }) {
  const source = evidenceSource(todoId, token, version);
  const key = `${todoId}-${version}`;
  const [web, setWeb] = useState<{ key: string; uri: string } | null>(null);
  const [failedKey, setFailedKey] = useState<string | null>(null);

  useEffect(() => {
    if (Platform.OS !== 'web') return;
    const src = evidenceSource(todoId, token, version);
    if (!src) return;
    const k = `${todoId}-${version}`;
    let alive = true;
    let url: string | null = null;
    fetch(src.uri, { headers: src.headers })
      .then((r) => (r.ok && r.headers.get('content-type')?.startsWith('image/') ? r.blob() : Promise.reject(new Error())))
      .then((blob) => {
        if (!alive) return;
        url = URL.createObjectURL(blob);
        setWeb({ key: k, uri: url });
      })
      .catch(() => {
        if (alive) setFailedKey(k);
      });
    return () => {
      alive = false;
      if (url) URL.revokeObjectURL(url);
    };
  }, [todoId, token, version]);

  if (!source || failedKey === key) {
    return (
      <View style={[styles.preview, styles.previewEmpty]}>
        <AppText size={13} color={Colors.textSub} leading={1.6} style={{ textAlign: 'center', paddingHorizontal: 16 }}>
          올린 증빙이 있지만 앱에서 미리 볼 수 없는 파일이에요
        </AppText>
      </View>
    );
  }
  const webUri = web?.key === key ? web.uri : null;
  return (
    <View style={styles.preview}>
      {Platform.OS !== 'web' || webUri ? (
        <Image
          accessibilityLabel="올린 증빙 사진"
          source={Platform.OS === 'web' && webUri ? { uri: webUri } : source}
          resizeMode="contain"
          onError={() => setFailedKey(key)}
          style={StyleSheet.absoluteFill}
        />
      ) : null}
    </View>
  );
}

function SegmentButton({ label, on, danger, onPress }: { label: string; on: boolean; danger?: boolean; onPress: () => void }) {
  return (
    <Pressable
      accessibilityRole="tab"
      accessibilityState={{ selected: on }}
      onPress={onPress}
      style={[styles.segmentButton, on && { backgroundColor: Colors.card }]}>
      <AppText size={13} weight={on ? 'bold' : 'medium'} color={on ? (danger ? Colors.dangerDeep : Colors.text) : Colors.textSub}>
        {label}
      </AppText>
    </Pressable>
  );
}

function DocSlot({ doc, emergency, onPress }: { doc: RecordDoc; emergency: boolean; onPress?: () => void }) {
  const missing = emergency && doc.needForClaim && !doc.filled;
  const dim = emergency && !doc.needForClaim;
  return (
    <Pressable
      accessibilityRole={onPress ? 'button' : undefined}
      accessibilityLabel={onPress ? `${doc.name} ${doc.filled ? '보기' : '올리기'}` : undefined}
      disabled={!onPress}
      onPress={onPress}
      style={({ pressed }) => [styles.slotBox, dim && { opacity: 0.4 }, pressed && { opacity: 0.7 }]}>
      {doc.filled ? (
        <View style={styles.photo}>
          <Icon name="doc" size={22} color="#9C968A" />
        </View>
      ) : (
        <View style={[styles.empty, missing && styles.emptyMissing]}>
          <Icon name="plus" size={20} color={missing ? Colors.danger : '#9C968A'} />
        </View>
      )}
      <AppText size={12} weight="semibold" leading={1.35} style={{ marginTop: 8 }}>
        {doc.name}
      </AppText>
      <AppText
        size={11}
        weight={missing ? 'bold' : 'regular'}
        color={missing ? Colors.danger : Colors.textHint}
        style={{ marginTop: 2 }}>
        {missing ? '청구에 필요' : doc.meta}
      </AppText>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  segment: {
    marginTop: 16,
    padding: 4,
    backgroundColor: Colors.muted,
    borderRadius: Radius.button,
    flexDirection: 'row',
    gap: 4,
  },
  segmentButton: { flex: 1, height: 44, borderRadius: 9, alignItems: 'center', justifyContent: 'center' },
  alert: { marginTop: 12, paddingVertical: 14, paddingHorizontal: 16, backgroundColor: Colors.dangerBg, borderRadius: Radius.sm },
  siteCheck: {
    marginTop: 12,
    paddingVertical: 12,
    paddingHorizontal: 14,
    backgroundColor: Colors.card,
    borderRadius: Radius.item,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  grid: { marginTop: 14, flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  slotBox: {
    // 3열 격자: (100% - 간격 2개) / 3
    width: '31%',
    flexGrow: 1,
    padding: 8,
    borderRadius: Radius.item,
    backgroundColor: Colors.card,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  photo: { height: 72, borderRadius: 8, backgroundColor: Colors.photo, alignItems: 'center', justifyContent: 'center' },
  empty: {
    height: 72,
    borderRadius: 8,
    borderWidth: 1.5,
    borderStyle: 'dashed',
    borderColor: Colors.inputBorder,
    alignItems: 'center',
    justifyContent: 'center',
  },
  emptyMissing: { borderWidth: 2, borderColor: Colors.danger, backgroundColor: Colors.dangerSlot },
  backdrop: { flex: 1, backgroundColor: 'rgba(23, 32, 42, 0.4)' },
  // 웹에서 넓은 화면으로 열어도 앱 폭에 맞춘다 (PaymentSheet와 같음)
  sheet: {
    width: '100%',
    maxWidth: MaxAppWidth,
    alignSelf: 'center',
    backgroundColor: Colors.card,
    borderTopLeftRadius: Radius.lg,
    borderTopRightRadius: Radius.lg,
    paddingHorizontal: Gutter,
    paddingTop: 10,
    paddingBottom: 28,
  },
  grabber: { alignSelf: 'center', width: 40, height: 4, borderRadius: 2, backgroundColor: Colors.inactiveDot, marginBottom: 16 },
  preview: {
    marginTop: 14,
    height: 260,
    borderRadius: Radius.item,
    backgroundColor: Colors.photo,
    overflow: 'hidden',
    alignItems: 'center',
    justifyContent: 'center',
  },
  previewEmpty: { backgroundColor: Colors.bg },
  textButton: { minHeight: 44, alignItems: 'center', justifyContent: 'center', marginTop: 4 },
});
