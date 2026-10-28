import { Link, router } from 'expo-router';
import { Pressable, StyleSheet, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { Icon } from '@/components/Icon';
import { Card, Disclaimer, Screen, SectionLabel } from '@/components/layout';
import { ratioBand } from '@/components/verdict';
import { Colors, Radius, Touch } from '@/constants/theme';
import { checkResult, house, recordDocs, today } from '@/data/demo';
import type { ApiContract } from '@/lib/api';
import { useLatestCheck } from '@/lib/check';
import { dottedDate, parseDateKey, useVirtualToday } from '@/lib/clock';
import { todoViews, useLatestContract } from '@/lib/contract';
import { formatWon } from '@/lib/format';

const stages = ['계약 전', '계약 당일', '입주 준비', '거주', '만기'];

type HomeView = {
  houseLine: string;
  /** "잔금일까지" + "D-15" */
  headline: string;
  dday: string;
  stage: number;
  period: string;
  now: { when: string; title: string; detail: string } | null;
  ratio: number | null;
  ratioAt: string;
  checkedAt: string;
};

const DAY = 86_400_000;
const dotted = (s: string) => s.split('-').join('.');
/** "2026.10.13" → "10/13" */
const shortDate = (s: string) => {
  const [, m, d] = s.split('.');
  return `${Number(m)}/${Number(d)}`;
};
const ddayText = (days: number) => (days === 0 ? 'D-DAY' : days > 0 ? `D-${days}` : `D+${-days}`);

/** 시연 집 (계약을 아직 만들지 않았을 때) */
const demoHome: HomeView = {
  houseLine: `${house.name} · 보증금 1억 4,000만 원`,
  headline: '잔금일까지',
  dday: 'D-15',
  stage: 2,
  period: `${house.contractDate} 계약 → ${house.endDate} 만기`,
  now: {
    when: '11월 25일(수) · 잔금 보낸 직후',
    title: '전입신고',
    detail: '잔금을 보낸 날 바로 전입신고를 해야 다음 날부터 대항력이 생겨요. 주민센터나 정부24에서 할 수 있어요.',
  },
  ratio: checkResult.deposit_ratio,
  ratioAt: '10/13 기준',
  checkedAt: today.full,
};

/** 패키지를 시작해 만든 계약(POST /api/contracts)으로 홈을 그린다. 오늘은 서버가 계산한 날(가상 날짜면 그날) */
function homeFromContract(contract: ApiContract, houseLabel: string | null, ratio: number | null, ratioAt: string): HomeView {
  const now = parseDateKey(contract.today);
  const days = (s: string) => Math.round((parseDateKey(s).getTime() - now.getTime()) / DAY);
  const toBalance = days(contract.balance_date);
  const toEnd = days(contract.end_date);
  // 계약일 전 → 계약 당일, 잔금일 전 → 입주 준비, 만기 2개월 전부터 → 만기
  const stage = days(contract.contract_date) >= 0 ? 1 : toBalance >= 0 ? 2 : toEnd > 61 ? 3 : 4;
  const views = todoViews(contract.todos, now);
  const current = views.find((v) => v.status === 'current');
  const api = current ? contract.todos.find((t) => `${t.rule_id}-${t.id}` === current.id) : undefined;
  return {
    houseLine: `${houseLabel ?? '내 계약'} · 보증금 ${formatWon(contract.deposit)} 원`,
    headline: toBalance >= 0 ? '잔금일까지' : '만기일까지',
    dday: ddayText(toBalance >= 0 ? toBalance : toEnd),
    stage,
    period: `${dotted(contract.contract_date)} 계약 → ${dotted(contract.end_date)} 만기`,
    now: current
      ? { when: [current.when, current.dday].filter(Boolean).join(' · '), title: current.title, detail: api?.detail ?? '' }
      : null,
    ratio,
    ratioAt,
    checkedAt: dottedDate(now),
  };
}

/** 홈: "지금 할 일" 1개만 크게, 보증금 비율과 기록함 현황은 작은 카드로 */
export default function HomeScreen() {
  const contract = useLatestContract();
  const virtualDay = useVirtualToday();
  const check = useLatestCheck();
  // 계약은 판정 1건으로 만든다. 저장한 판정이 이 계약의 판정이 아니면 집 이름·비율은 쓰지 않는다
  const sameCheck = check && contract && check.id === contract.check_id ? check : null;
  const h = contract
    ? homeFromContract(
        contract,
        sameCheck?.houseLabel ?? null,
        sameCheck?.deposit_ratio ?? null,
        sameCheck ? `${shortDate(sameCheck.checkedAt)} 기준` : '',
      )
    : demoHome;
  const ratio = h.ratio ?? 0;
  const band = ratioBand(ratio);
  // 비율이 80% 미만이어도 주변 전세가 내 보증금보다 낮으면 경보는 주의 (alert.yaml)
  const lowNearby = ratio < 0.8 && sameCheck?.nearbyJeonse?.below_deposit === true;
  const filled = recordDocs.filter((d) => d.filled).length;
  const currentStage = h.stage;

  return (
    <Screen inTabs>
      <View style={styles.top}>
        <AppText size={20} weight="bold">
          전동기
        </AppText>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
          {/* FR-044: 시연용 가상 날짜. 가상 날짜면 그 날짜를 보여 준다 */}
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="시연 날짜 바꾸기"
            onPress={() => router.push('/virtual-date')}
            style={[styles.dateChip, virtualDay ? styles.dateChipOn : null]}>
            <Icon name="calendar" size={14} color={virtualDay ? '#FFFFFF' : Colors.textSub} strokeWidth={2} />
            <AppText size={12} weight="semibold" color={virtualDay ? '#FFFFFF' : Colors.textSub}>
              {virtualDay ? dottedDate(parseDateKey(virtualDay)) : '시연 날짜'}
            </AppText>
          </Pressable>
          <Pressable accessibilityRole="button" accessibilityLabel="알림" style={styles.iconButton}>
            <Icon name="bell" />
          </Pressable>
        </View>
      </View>

      <AppText size={13} color={Colors.textSub} style={{ marginTop: 8 }}>
        {h.houseLine}
      </AppText>
      <View style={{ flexDirection: 'row', alignItems: 'baseline', gap: 10, marginTop: 6 }}>
        <AppText size={26} weight="bold">
          {h.headline}
        </AppText>
        <AppText size={26} weight="bold" color={Colors.primary}>
          {h.dday}
        </AppText>
      </View>

      <Pressable accessibilityRole="button" accessibilityLabel="계약 타임라인 보기" onPress={() => router.push('/timeline')}>
        <Card style={{ marginTop: 18, paddingBottom: 14 }}>
          <View style={styles.rowBetween}>
            {stages.map((s, i) => (
              <AppText
                key={s}
                size={12}
                weight={i === currentStage ? 'semibold' : 'regular'}
                color={i === currentStage ? Colors.primary : Colors.textSub}>
                {s}
              </AppText>
            ))}
          </View>
          <View style={styles.stageTrack}>
            <View style={styles.stageLine} />
            <View style={[styles.stageLine, { backgroundColor: Colors.primary, right: undefined, width: `${(currentStage / (stages.length - 1)) * 92}%` }]} />
            <View style={[styles.rowBetween, { alignItems: 'center' }]}>
              {stages.map((s, i) =>
                i === currentStage ? (
                  <View key={s} style={styles.stageNow} />
                ) : (
                  <View
                    key={s}
                    style={[styles.stageDot, { backgroundColor: i < currentStage ? Colors.primary : Colors.inactiveDot }]}
                  />
                ),
              )}
            </View>
          </View>
          <AppText size={12} color={Colors.textSub} style={{ marginTop: 6 }}>
            {h.period}
          </AppText>
        </Card>
      </Pressable>

      <SectionLabel>지금 할 일</SectionLabel>
      <View style={styles.nowCard}>
        <AppText size={12} color="rgba(255,255,255,0.85)">
          {h.now?.when ?? '남은 할 일이 없어요'}
        </AppText>
        <AppText size={21} weight="bold" color="#FFFFFF" style={{ marginTop: 6 }}>
          {h.now?.title ?? '모든 할 일을 마쳤어요'}
        </AppText>
        {h.now?.detail ? (
          <AppText size={14} color="rgba(255,255,255,0.92)" leading={1.55} style={{ marginTop: 8 }}>
            {h.now.detail}
          </AppText>
        ) : null}
        <View style={{ flexDirection: 'row', gap: 8, marginTop: 16 }}>
          <Pressable style={[styles.nowButton, { flex: 1, backgroundColor: '#FFFFFF' }]} onPress={() => router.push('/todos')}>
            <AppText size={15} weight="semibold" color={Colors.primary}>
              증빙 남기기
            </AppText>
          </Pressable>
          <Pressable style={[styles.nowButton, styles.nowButtonGhost]} onPress={() => router.push('/todos')}>
            <AppText size={15} color="#FFFFFF">
              전체 할 일
            </AppText>
          </Pressable>
        </View>
      </View>

      <View style={{ flexDirection: 'row', gap: 10, marginTop: 14 }}>
        <Pressable style={{ flex: 1 }} onPress={() => router.push('/alert')}>
          <Card>
            <AppText size={12} color={Colors.textSub}>
              내 보증금 비율
            </AppText>
            <AppText size={26} weight="bold" color={band.color} style={{ marginTop: 4 }}>
              {h.ratio === null ? '—' : `${Math.round(ratio * 100)}%`}
            </AppText>
            <View style={styles.bar}>
              <View style={[styles.barFill, { width: `${Math.min(ratio, 1) * 100}%`, backgroundColor: band.color }]} />
            </View>
            <AppText size={12} color={Colors.textSub} style={{ marginTop: 8 }}>
              {h.ratio === null ? '계산한 판정 없음' : `${band.label}${lowNearby ? ' · 주변 전세 낮음' : ''} · ${h.ratioAt}`}
            </AppText>
          </Card>
        </Pressable>
        <Pressable style={{ flex: 1 }} onPress={() => router.push('/records')}>
          <Card>
            <AppText size={12} color={Colors.textSub}>
              기록함
            </AppText>
            <AppText size={26} weight="bold" style={{ marginTop: 4 }}>
              {filled}
              <AppText size={15} weight="medium" color={Colors.textSub}>
                {' '}
                / {recordDocs.length}장
              </AppText>
            </AppText>
            <View style={{ flexDirection: 'row', gap: 4, marginTop: 8 }}>
              {recordDocs.map((d) => (
                <View key={d.name} style={[styles.segment, { backgroundColor: d.filled ? Colors.primary : Colors.track }]} />
              ))}
            </View>
            <AppText size={12} color={Colors.textSub} style={{ marginTop: 8 }}>
              빈 서류 {recordDocs.length - filled}개
            </AppText>
          </Card>
        </Pressable>
      </View>

      <View style={{ flexDirection: 'row', gap: 16, marginTop: 8 }}>
        <Link href="/precheck" style={styles.textLink}>
          <AppText size={13} weight="semibold" color={Colors.primary}>
            새 집 계약 전 확인 →
          </AppText>
        </Link>
        <Link href="/check" style={styles.textLink}>
          <AppText size={13} weight="semibold" color={Colors.textSub}>
            지난 확인 결과
          </AppText>
        </Link>
      </View>

      <View style={{ flex: 1 }} />
      <Disclaimer>정보 제공이며 보증하지 않습니다 · 조회 {h.checkedAt}</Disclaimer>
    </Screen>
  );
}

const styles = StyleSheet.create({
  dateChip: {
    height: 32,
    paddingHorizontal: 10,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: Colors.inputBorder,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  dateChipOn: { backgroundColor: Colors.primary, borderColor: Colors.primary },
  top: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingTop: 20 },
  iconButton: { width: Touch.min, height: Touch.min, alignItems: 'center', justifyContent: 'center', marginRight: -12 },
  rowBetween: { flexDirection: 'row', justifyContent: 'space-between' },
  stageTrack: { height: 22, marginTop: 8, justifyContent: 'center' },
  stageLine: { position: 'absolute', left: 8, right: 8, top: 10, height: 2, backgroundColor: Colors.border },
  stageDot: { width: 12, height: 12, borderRadius: 6 },
  stageNow: {
    width: 20,
    height: 20,
    borderRadius: 10,
    backgroundColor: '#FFFFFF',
    borderWidth: 3,
    borderColor: Colors.primary,
  },
  nowCard: { padding: 20, backgroundColor: Colors.primary, borderRadius: Radius.lg },
  nowButton: { height: 48, borderRadius: Radius.button, alignItems: 'center', justifyContent: 'center' },
  nowButtonGhost: { paddingHorizontal: 16, borderWidth: 1, borderColor: 'rgba(255,255,255,0.45)' },
  bar: { height: 6, borderRadius: 3, backgroundColor: Colors.track, marginTop: 8, overflow: 'hidden' },
  barFill: { height: 6, borderRadius: 3 },
  segment: { flex: 1, height: 6, borderRadius: 3 },
  textLink: { paddingVertical: 12 },
});
