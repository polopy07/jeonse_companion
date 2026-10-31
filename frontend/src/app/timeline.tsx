import { useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { Icon } from '@/components/Icon';
import { Disclaimer, Screen } from '@/components/layout';
import { Colors, Radius } from '@/constants/theme';
import { house, timeline as demoTimeline, type TimelineEvent, type TimelineKind } from '@/data/demo';
import { apiEnabled, getTimeline, type ApiContract, type ApiTimelineEvent } from '@/lib/api';
import { useLatestCheck, type CheckView } from '@/lib/check';
import { useVirtualToday } from '@/lib/clock';
import { contractToken, useLatestContract } from '@/lib/contract';

const kinds: Record<TimelineKind, { label: string; color: string }> = {
  contract: { label: '계약·점검', color: Colors.primary },
  todo: { label: '할 일 완료', color: Colors.ok },
  alert: { label: '경보·특약', color: Colors.cautionStrong },
  end: { label: '만기·이사', color: Colors.danger },
};

/** 서버 기록 종류 → 화면 색 묶음 */
const kindOf: Record<ApiTimelineEvent['kind'], TimelineKind> = {
  check: 'contract',
  contract: 'contract',
  registry: 'contract',
  document: 'contract',
  special_term: 'alert',
  alert: 'alert',
  todo: 'todo',
  return: 'end',
  // 갈아타기는 계획한 일이라 경고(빨강)가 아니라 계약 묶음으로
  move: 'contract',
  cancel: 'end',
};

const dotted = (iso: string) => iso.replaceAll('-', '.');

/** "2026-10-14" 또는 "2026.10.14" → 연도와 "10.14" */
function at(date: string) {
  const [year, m, d] = date.split(/[-.]/);
  return { year, md: `${m}.${d}` };
}

/**
 * 계약 응답으로 그리는 기록 (FR-032, 서버 타임라인을 받기 전·받지 못했을 때): 계약 전 확인, 계약 당일 특약 결과,
 * 끝낸 할 일(끝낸 날·증빙). 같은 날은 계약 → 특약 → 할 일 순서
 */
function eventsFromContract(contract: ApiContract, check: CheckView | null): TimelineEvent[] {
  const events: (TimelineEvent & { day: string })[] = [];
  const add = (day: string, kind: TimelineKind, title: string, sub: string, photo = false) =>
    events.push({ day: day.replaceAll('.', '-'), ...at(day), kind, title, sub, photo });

  if (check) {
    const ratio = check.deposit_ratio === null ? '' : ` · 비율 ${Math.round(check.deposit_ratio * 100)}%`;
    add(check.checkedAt, 'contract', '계약 전 확인', `${check.label}${ratio}`);
  }
  add(contract.contract_date, 'contract', '계약 당일 체크', '계약 날짜 입력 · 2년 할 일 만듦');
  for (const e of contract.special_term_effects) {
    if (e.result === 'rejected') {
      const top = e.moves_to_top.map((t) => t.title).join(', ');
      add(contract.contract_date, 'alert', '특약 거절당함', top ? `${e.label} → ${top} 맨 위로` : e.label);
    } else {
      add(contract.contract_date, 'contract', '특약 넣음', e.label);
    }
  }
  for (const t of contract.todos) {
    if (t.status === 'todo' || !t.done_date) continue;
    const sub = t.evidence_uploaded ? (t.evidence ?? '증빙 1장') : t.status === 'skipped' ? '증빙은 나중에' : '완료';
    add(t.done_date, 'todo', t.title, sub, t.evidence_uploaded);
  }
  // 날짜순 (같은 날은 넣은 순서 그대로)
  return events.map((e, i) => ({ e, i })).sort((a, b) => a.e.day.localeCompare(b.e.day) || a.i - b.i).map(({ e }) => e);
}

/** 서버 타임라인 → 화면 값. 제목·설명은 서버 문구 그대로, 증빙을 올린 할 일과 첫 계약 서류는 사진 표시 */
const eventsFromApi = (events: ApiTimelineEvent[]): TimelineEvent[] =>
  events.map((e) => ({
    ...at(e.date),
    kind: kindOf[e.kind],
    title: e.title,
    sub: e.detail ?? '',
    photo: e.kind === 'document' || !!e.evidence_uploaded,
  }));

type RemoteTimeline = { contractId: number; events: TimelineEvent[] | null };

/**
 * 계약 타임라인을 서버에서 받는다 (GET /api/contracts/{id}/timeline). 화면을 열 때·가상 날짜를 바꿀 때·계약이 바뀔 때
 * 다시 받는다. 받기 전이나 실패하면 null (화면은 계약 응답으로 그린 기록을 보여 준다)
 */
function useTimeline(contract: ApiContract | null): TimelineEvent[] | null {
  const [remote, setRemote] = useState<RemoteTimeline | null>(null);
  const day = useVirtualToday();
  const id = contract?.id ?? null;
  useFocusEffect(
    useCallback(() => {
      if (!apiEnabled || id === null) return;
      let alive = true;
      getTimeline(id, contractToken(id))
        .then((r) => alive && setRemote({ contractId: id, events: eventsFromApi(r.events) }))
        .catch(() => alive && setRemote({ contractId: id, events: null }));
      return () => {
        alive = false;
      };
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [id, day, contract]),
  );
  return remote?.contractId === id ? remote.events : null;
}

/**
 * UI-06 계약 타임라인. 계약이 있으면 서버 타임라인(등기부 재비교·첫 계약 서류·경보 재계산·반환 대응·갈아타기 포함,
 * 오늘(가상 날짜)까지)으로, 서버에서 받기 전이나 받지 못하면 계약 응답으로 그린 기록으로, 계약이 없으면 시연 계약의 2년으로
 */
export default function TimelineScreen() {
  const contract = useLatestContract();
  const latestCheck = useLatestCheck();
  const check = contract && latestCheck?.id === contract.check_id ? latestCheck : null;
  const remote = useTimeline(contract);
  const timeline = contract ? (remote ?? eventsFromContract(contract, check)) : demoTimeline;
  const header = contract
    ? `${check?.houseLabel ?? '내 계약'} · ${dotted(contract.contract_date)} ~ ${dotted(contract.end_date)}`
    : `${house.name} · ${house.contractDate} ~ ${house.endDate}`;
  return (
    <Screen title="계약 타임라인">
      <AppText size={13} color={Colors.textSub} style={{ marginTop: 4 }}>
        {header}
      </AppText>

      <View style={styles.legend}>
        {Object.values(kinds).map((k) => (
          <View key={k.label} style={styles.chip}>
            <View style={[styles.chipDot, { backgroundColor: k.color }]} />
            <AppText size={12} color={Colors.textSub}>
              {k.label}
            </AppText>
          </View>
        ))}
      </View>

      <View style={styles.list}>
        <View style={styles.rail} />
        {timeline.map((e, i) => (
          <View key={i} style={styles.row}>
            <View style={styles.date}>
              <AppText size={10} color={Colors.textHint}>
                {e.year}
              </AppText>
              <AppText size={12} weight="semibold">
                {e.md}
              </AppText>
            </View>
            <View style={[styles.dot, { backgroundColor: kinds[e.kind].color }]} />
            <View style={styles.event}>
              <View style={{ flex: 1, minWidth: 0 }}>
                <AppText size={14} weight="semibold">
                  {e.title}
                </AppText>
                {e.sub ? (
                  <AppText size={12} color={Colors.textSub} leading={1.5} style={{ marginTop: 2 }}>
                    {e.sub}
                  </AppText>
                ) : null}
              </View>
              {e.photo ? (
                <View style={styles.photo} accessibilityLabel="증빙 사진 있음">
                  <Icon name="camera" size={16} color="#9C968A" />
                </View>
              ) : null}
            </View>
          </View>
        ))}
      </View>

      <View style={{ flex: 1 }} />
      <Disclaimer>이 기록은 반환 확인 후 3개월 동안 보관돼요.</Disclaimer>
    </Screen>
  );
}

const styles = StyleSheet.create({
  legend: { marginTop: 14, flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingVertical: 4,
    paddingHorizontal: 10,
    borderRadius: 999,
    backgroundColor: Colors.card,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  chipDot: { width: 8, height: 8, borderRadius: 4 },
  list: { marginTop: 16, gap: 4 },
  rail: { position: 'absolute', left: 57, top: 8, bottom: 8, width: 2, backgroundColor: Colors.timelineLine },
  row: { flexDirection: 'row', alignItems: 'flex-start', gap: 12 },
  date: { width: 40, alignItems: 'flex-end', paddingTop: 12 },
  dot: { width: 12, height: 12, borderRadius: 6, marginTop: 18, borderWidth: 2, borderColor: Colors.bg },
  event: {
    flex: 1,
    minWidth: 0,
    paddingVertical: 10,
    paddingHorizontal: 12,
    backgroundColor: Colors.card,
    borderRadius: Radius.item,
    borderWidth: 1,
    borderColor: Colors.border,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  photo: { width: 36, height: 36, borderRadius: 6, backgroundColor: Colors.photo, alignItems: 'center', justifyContent: 'center' },
});
