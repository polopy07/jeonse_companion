import { router, useFocusEffect } from 'expo-router';
import * as WebBrowser from 'expo-web-browser';
import { useCallback, useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { Icon } from '@/components/Icon';
import { Button, Card, Disclaimer, Screen, SectionLabel } from '@/components/layout';
import { Colors, Radius } from '@/constants/theme';
import { helpDesks as demoHelpDesks, house, returnSteps as demoSteps } from '@/data/demo';
import {
  ApiError,
  apiEnabled,
  getReturnGuide,
  patchTodo,
  startReturnResponse,
  undoReturnResponse,
  uploadEvidence,
  type ApiContract,
  type ApiLink,
  type ApiReturnGuide,
} from '@/lib/api';
import { useVirtualToday } from '@/lib/clock';
import { contractToken, setLatestContract, useLatestContract } from '@/lib/contract';
import { pickEvidence, type EvidenceSource } from '@/lib/evidence';

type StepView = {
  key: string;
  title: string;
  body: string;
  state: 'done' | 'current' | 'todo';
  /** 신청·청구 창구 */
  link?: ApiLink | null;
  /** 이 단계에 필요한데 기록함에 없는 서류 */
  missing?: string[];
  /** 반환 대응 중인 계약의 이 단계 할 일 (끝내기·증빙) */
  todoId?: number | null;
  evidence?: string | null;
};

type GuideView = {
  heroLabel: string;
  heroTitle: string;
  steps: StepView[];
  docTotal: number;
  missingNames: string[];
  helpDesks: ApiLink[];
  disclaimer: string;
};

/** "2026-11-24" → "2026.11.24" */
const dotDate = (s: string) => s.replaceAll('-', '.');

/** 계약이 없을 때 보여 주는 시연 안내 (정적) */
const demoView: GuideView = {
  heroLabel: `${house.endDate} 만기 · 보증금 못 받음`,
  heroTitle: '아직 이사 가지 마세요. 순서대로 함께 챙길게요.',
  steps: demoSteps.map((s) => ({ key: s.title, ...s })),
  docTotal: 6,
  missingNames: ['내용증명 사본'],
  helpDesks: demoHelpDesks,
  disclaimer: '일반 절차 안내이며 개별 법률 판단이 아닙니다.',
};

function heroOf(g: ApiReturnGuide) {
  const end = dotDate(g.end_date);
  if (g.status === 'in_progress') {
    return { heroLabel: `${end} 만기 · 보증금 못 받음`, heroTitle: '아직 이사 가지 마세요. 순서대로 함께 챙길게요.' };
  }
  if (g.status === 'ended') {
    return { heroLabel: `${end} 만기 · 반환 확인`, heroTitle: '보증금을 돌려받았어요. 반환 대응 기록은 기록함에 남아요.' };
  }
  return {
    heroLabel: `${end} 만기 · 미리 점검`,
    heroTitle:
      g.today >= g.end_date
        ? '만기일이 지났어요. 보증금을 못 받았으면 반환 대응을 시작하세요.'
        : '못 돌려받을 때를 대비해 청구 서류를 미리 채워 두세요.',
  };
}

/** 서버 반환 대응 안내 → 화면 값. 단계 제목·안내·창구는 보증기관에 맞춘 서버 값 그대로 */
function viewOf(g: ApiReturnGuide): GuideView {
  return {
    ...heroOf(g),
    steps: g.steps.map((s) => ({
      key: s.rule_id,
      title: s.title,
      body:
        s.state === 'done'
          ? `${s.done_date ? `${dotDate(s.done_date)} ` : ''}완료${s.evidence_uploaded ? ' · 증빙 1장' : s.evidence ? ' · 증빙은 나중에' : ''}`
          : s.detail,
      state: s.state,
      link: s.link,
      missing: s.missing_documents,
      todoId: s.todo_id,
      evidence: s.evidence,
    })),
    docTotal: g.documents.length,
    missingNames: g.documents.filter((d) => !d.uploaded).map((d) => d.name),
    helpDesks: g.help_desks,
    disclaimer: g.disclaimer,
  };
}

type RemoteGuide = { contractId: number; guide: ApiReturnGuide | null; error: string | null };

const messageOf = (e: unknown, fallback: string) =>
  (e instanceof ApiError ? [e.message, e.hint].filter(Boolean).join('. ') : e instanceof Error ? e.message : '') ||
  fallback;

/**
 * 계약의 반환 대응 안내를 서버에서 받는다 (GET /api/contracts/{id}/return-guide). 화면을 열 때·가상 날짜를 바꿀 때·
 * 계약이 바뀔 때(단계를 끝내거나 "못 받음"을 고름) 다시 받는다. 서버 주소가 없거나 계약이 없으면 null
 */
function useReturnGuide(contract: ApiContract | null): RemoteGuide | null {
  const [remote, setRemote] = useState<RemoteGuide | null>(null);
  const day = useVirtualToday();
  const id = contract?.id ?? null;
  useFocusEffect(
    useCallback(() => {
      if (!apiEnabled || id === null) return;
      let alive = true;
      getReturnGuide(id, contractToken(id))
        .then((guide) => alive && setRemote({ contractId: id, guide, error: null }))
        .catch((e) => alive && setRemote({ contractId: id, guide: null, error: messageOf(e, '반환 대응 안내를 받지 못했어요') }));
      return () => {
        alive = false;
      };
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [id, day, contract]),
  );
  return remote?.contractId === id ? remote : null;
}

/**
 * UI-08 반환 대응 안내 (FR-024·034·035). 일반 절차 안내이며 개별 법률 판단이 아니다.
 * 계약이 있으면 서버의 단계·진행·청구 서류 대조로 그리고, 만기일이 지나면 "못 받음"으로 반환 대응을 시작한다
 * (단계 할 일이 할 일 맨 위에 붙음). 단계는 이 화면이나 할 일 탭에서 증빙 1장으로 끝낸다. 계약이 없으면 시연 안내
 */
export default function ReturnScreen() {
  const contract = useLatestContract();
  const remote = useReturnGuide(contract);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const guide = remote?.guide ?? null;
  const view = guide ? viewOf(guide) : contract && apiEnabled ? null : demoView;
  const active = !!contract && contract.status === 'active';

  // 서버에서 바꾸고 돌아온 계약으로 다시 그린다 (계약이 바뀌면 안내도 다시 받는다)
  const run = async (call: (token: string | null) => Promise<ApiContract | null>, fallback: string) => {
    if (!contract || busy) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await call(contractToken(contract.id));
      if (updated) setLatestContract(updated);
    } catch (e) {
      setError(messageOf(e, fallback));
    } finally {
      setBusy(false);
    }
  };

  const start = () => run((token) => startReturnResponse(contract!.id, token), '반환 대응을 시작하지 못했어요');
  const undo = () => run((token) => undoReturnResponse(contract!.id, token), '되돌리지 못했어요');
  const complete = (s: StepView, source: EvidenceSource) =>
    run(async (token) => {
      if (!s.todoId) return null;
      if (!s.evidence) return patchTodo(s.todoId, token, 'done');
      const file = await pickEvidence(source);
      return file ? uploadEvidence(s.todoId, token, file) : null;
    }, '단계를 끝내지 못했어요');
  const skip = (s: StepView) =>
    run((token) => (s.todoId ? patchTodo(s.todoId, token, 'skipped') : Promise.resolve(null)), '단계를 끝내지 못했어요');

  const canStart = active && guide?.status === 'preview' && guide.today >= guide.end_date;
  const canUndo = active && guide?.status === 'in_progress' && !guide.steps.some((s) => s.state === 'done');
  const stepActions = active && guide?.status === 'in_progress';

  return (
    <Screen title="반환 대응 안내">
      {view ? (
        <View style={styles.hero}>
          <AppText size={12} weight="semibold" color={Colors.dangerDeep}>
            {view.heroLabel}
          </AppText>
          <AppText size={19} weight="bold" color={Colors.dangerText} leading={1.4} style={{ marginTop: 6 }}>
            {view.heroTitle}
          </AppText>
          {canStart ? (
            // FR-024: 9번(반환 확인)에서 "못 받음" → 반환 대응 단계를 할 일 맨 위에
            <Button
              label={busy ? '시작하는 중…' : '보증금을 못 받았어요 · 반환 대응 시작'}
              height={46}
              onPress={start}
              style={{ marginTop: 14, backgroundColor: Colors.danger, opacity: busy ? 0.6 : 1 }}
            />
          ) : null}
          {guide?.status === 'preview' && !canStart ? (
            <AppText size={12} color={Colors.dangerText} style={{ marginTop: 8 }}>
              만기일({dotDate(guide.end_date)})이 지나도 못 받으면 여기서 반환 대응을 시작해요
            </AppText>
          ) : null}
        </View>
      ) : (
        <AppText size={13} color={remote?.error ? Colors.caution : Colors.textSub} style={{ marginTop: 12 }}>
          {remote?.error ?? '반환 대응 안내를 불러오는 중…'}
        </AppText>
      )}

      {error ? (
        <AppText size={12} color={Colors.caution} leading={1.5} style={{ marginTop: 8 }}>
          {error}
        </AppText>
      ) : null}

      {view ? (
        <>
          <View style={{ marginTop: 18, gap: 8 }}>
            {view.steps.map((s, i) => (
              <StepCard
                key={s.key}
                step={s}
                index={i}
                busy={busy}
                onComplete={stepActions && s.state === 'current' && s.todoId ? (source) => complete(s, source) : undefined}
                onSkip={stepActions && s.state === 'current' && s.todoId && s.evidence ? () => skip(s) : undefined}
              />
            ))}
          </View>
          {canUndo ? (
            <Pressable onPress={undo} hitSlop={8} style={{ minHeight: 44, justifyContent: 'center', alignSelf: 'flex-start' }}>
              <AppText size={13} weight="semibold" color={Colors.textSub}>
                잘못 골랐어요 · &quot;못 받음&quot; 되돌리기
              </AppText>
            </Pressable>
          ) : null}

          <Card style={{ marginTop: 18 }}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
              <AppText size={14} weight="bold">
                청구 서류 대조
              </AppText>
              <AppText size={13} weight="bold" color={view.missingNames.length ? Colors.danger : Colors.ok}>
                {view.missingNames.length ? `${view.docTotal}개 중 ${view.missingNames.length}개 빠짐` : `${view.docTotal}개 모두 있음`}
              </AppText>
            </View>
            <View style={styles.progress}>
              <View
                style={{
                  width: `${view.docTotal ? Math.round(((view.docTotal - view.missingNames.length) / view.docTotal) * 100) : 0}%`,
                  height: 8,
                  backgroundColor: Colors.ok,
                }}
              />
            </View>
            {view.missingNames.length ? (
              <AppText size={13} color={Colors.textSub} leading={1.6} style={{ marginTop: 10 }}>
                빠진 서류:{' '}
                <AppText size={13} weight="bold" color={Colors.danger}>
                  {view.missingNames.join(', ')}
                </AppText>
              </AppText>
            ) : null}
            {guide?.status === 'preview' ? (
              <AppText size={12} color={Colors.textSub} style={{ marginTop: 4 }}>
                지금 준비할 수 있는 서류만 대조했어요. 단계별 서류는 반환 대응을 시작하면 더해져요
              </AppText>
            ) : null}
            <Pressable onPress={() => router.push('/records')} style={{ minHeight: 44, justifyContent: 'center' }}>
              <AppText size={13} weight="semibold" color={Colors.primary}>
                비상 서류함 열기 →
              </AppText>
            </Pressable>
          </Card>

          <SectionLabel>상담 창구</SectionLabel>
          <View style={styles.links}>
            {view.helpDesks.map((h, i) => (
              <Pressable
                key={h.url}
                accessibilityRole="link"
                onPress={() => WebBrowser.openBrowserAsync(h.url)}
                style={[styles.link, i < view.helpDesks.length - 1 && styles.divider]}>
                <AppText size={14}>{h.label}</AppText>
                <AppText size={14} color={Colors.textHint}>
                  ↗
                </AppText>
              </Pressable>
            ))}
          </View>
        </>
      ) : null}

      <View style={{ flex: 1 }} />
      <Disclaimer>{view?.disclaimer ?? demoView.disclaimer}</Disclaimer>
    </Screen>
  );
}

function StepCard({
  step: s,
  index,
  busy,
  onComplete,
  onSkip,
}: {
  step: StepView;
  index: number;
  busy: boolean;
  onComplete?: (source: EvidenceSource) => void;
  onSkip?: () => void;
}) {
  const current = s.state === 'current';
  const done = s.state === 'done';
  return (
    <View style={[styles.step, current && styles.stepCurrent, done && { opacity: 0.7 }]}>
      <View
        style={[
          styles.num,
          done && { backgroundColor: Colors.ok },
          current && { backgroundColor: Colors.primary },
          !done && !current && styles.numTodo,
        ]}>
        {done ? (
          <Icon name="check" size={14} color="#FFFFFF" strokeWidth={2.5} />
        ) : (
          <AppText size={13} weight="bold" color={current ? '#FFFFFF' : Colors.textSub}>
            {index + 1}
          </AppText>
        )}
      </View>
      <View style={{ flex: 1 }}>
        <AppText size={15} weight={current ? 'bold' : 'semibold'}>
          {s.title}
        </AppText>
        <AppText size={done ? 12 : 13} color={Colors.textSub} leading={done ? undefined : 1.6} style={{ marginTop: done ? 2 : 4 }}>
          {s.body}
        </AppText>
        {current && s.missing?.length ? (
          // FR-035: 지금 할 단계에 필요한데 기록함에 없는 서류 (전체 대조는 아래 카드)
          <AppText size={12} color={Colors.danger} leading={1.5} style={{ marginTop: 4 }}>
            빠진 서류: {s.missing.join(', ')}
          </AppText>
        ) : null}
        {!done && s.link ? (
          <Pressable
            accessibilityRole="link"
            onPress={() => WebBrowser.openBrowserAsync(s.link!.url)}
            hitSlop={8}
            style={{ minHeight: 32, justifyContent: 'center', alignSelf: 'flex-start' }}>
            <AppText size={13} weight="semibold" color={Colors.primary}>
              {s.link.label} ↗
            </AppText>
          </Pressable>
        ) : null}
        {onComplete ? (
          <>
            <Pressable
              style={[styles.smallButton, busy && { opacity: 0.6 }]}
              onPress={() => onComplete('camera')}
              accessibilityRole="button">
              <AppText size={13} weight="semibold" color="#FFFFFF">
                {busy ? '올리는 중…' : s.evidence ? '증빙 1장 남기고 완료' : '완료'}
              </AppText>
            </Pressable>
            {s.evidence ? (
              <View style={styles.subActions}>
                <TextAction label="앨범에서 고르기" onPress={() => onComplete('library')} />
                {onSkip ? <TextAction label="나중에 올리기" onPress={onSkip} /> : null}
              </View>
            ) : null}
            {s.evidence ? (
              <AppText size={12} color={Colors.textSub} style={{ marginTop: 2 }}>
                증빙: {s.evidence}
              </AppText>
            ) : null}
          </>
        ) : current && !s.todoId ? (
          // 시연 안내·미리 점검: 올리기는 기록함에서
          <Pressable style={styles.smallButton} onPress={() => router.push('/records')}>
            <AppText size={13} weight="semibold" color="#FFFFFF">
              기록함 열기
            </AppText>
          </Pressable>
        ) : null}
      </View>
    </View>
  );
}

function TextAction({ label, onPress }: { label: string; onPress: () => void }) {
  return (
    <Pressable accessibilityRole="button" onPress={onPress} hitSlop={8} style={{ minHeight: 32, justifyContent: 'center' }}>
      <AppText size={13} weight="semibold" color={Colors.primary}>
        {label}
      </AppText>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  hero: { marginTop: 8, padding: 18, backgroundColor: Colors.dangerBg, borderRadius: Radius.card },
  step: {
    flexDirection: 'row',
    gap: 12,
    paddingVertical: 14,
    paddingHorizontal: 16,
    backgroundColor: Colors.card,
    borderRadius: Radius.sm,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  stepCurrent: { padding: 16, borderWidth: 2, borderColor: Colors.primary },
  num: { width: 28, height: 28, borderRadius: 14, alignItems: 'center', justifyContent: 'center' },
  numTodo: { borderWidth: 2, borderColor: Colors.inputBorder },
  smallButton: {
    alignSelf: 'flex-start',
    marginTop: 10,
    height: 44,
    paddingHorizontal: 14,
    borderRadius: Radius.input,
    backgroundColor: Colors.primary,
    justifyContent: 'center',
  },
  subActions: { flexDirection: 'row', gap: 16, marginTop: 6 },
  progress: { height: 8, borderRadius: 4, backgroundColor: Colors.track, marginTop: 10, overflow: 'hidden' },
  links: {
    backgroundColor: Colors.card,
    borderRadius: Radius.sm,
    borderWidth: 1,
    borderColor: Colors.border,
    overflow: 'hidden',
  },
  link: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', minHeight: 48, paddingHorizontal: 16 },
  divider: { borderBottomWidth: 1, borderBottomColor: Colors.divider },
});
