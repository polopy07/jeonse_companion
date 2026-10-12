import { Link, router } from 'expo-router';
import { Pressable, StyleSheet, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { Icon } from '@/components/Icon';
import { Card, Disclaimer, Screen, SectionLabel } from '@/components/layout';
import { ratioBand } from '@/components/verdict';
import { Colors, Radius, Touch } from '@/constants/theme';
import { checkResult, house, recordDocs, today } from '@/data/demo';

const stages = ['계약 전', '계약 당일', '입주 준비', '거주', '만기'];
const currentStage = 2;

/** 홈: "지금 할 일" 1개만 크게, 보증금 비율과 기록함 현황은 작은 카드로 */
export default function HomeScreen() {
  const ratio = checkResult.deposit_ratio;
  const band = ratioBand(ratio);
  const filled = recordDocs.filter((d) => d.filled).length;

  return (
    <Screen inTabs>
      <View style={styles.top}>
        <AppText size={20} weight="bold">
          전동기
        </AppText>
        <Pressable accessibilityRole="button" accessibilityLabel="알림" style={styles.iconButton}>
          <Icon name="bell" />
        </Pressable>
      </View>

      <AppText size={13} color={Colors.textSub} style={{ marginTop: 8 }}>
        {house.name} · 보증금 1억 4,000만 원
      </AppText>
      <View style={{ flexDirection: 'row', alignItems: 'baseline', gap: 10, marginTop: 6 }}>
        <AppText size={26} weight="bold">
          잔금일까지
        </AppText>
        <AppText size={26} weight="bold" color={Colors.primary}>
          D-10
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
            <View style={[styles.stageLine, { backgroundColor: Colors.primary, right: undefined, width: '46%' }]} />
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
            {house.contractDate} 계약 → {house.endDate} 만기
          </AppText>
        </Card>
      </Pressable>

      <SectionLabel>지금 할 일</SectionLabel>
      <View style={styles.nowCard}>
        <AppText size={12} color="rgba(255,255,255,0.85)">
          11월 20일(금) 아침 · 잔금 보내기 전
        </AppText>
        <AppText size={21} weight="bold" color="#FFFFFF" style={{ marginTop: 6 }}>
          잔금일 아침 등기부 재비교
        </AppText>
        <AppText size={14} color="rgba(255,255,255,0.92)" leading={1.55} style={{ marginTop: 8 }}>
          계약 당일 등기부와 비교해 새 근저당·압류가 생겼는지 확인해요. 담보 설정 금지 특약이 거절돼서 이 확인이 더
          중요해요.
        </AppText>
        <View style={{ flexDirection: 'row', gap: 8, marginTop: 16 }}>
          <Pressable style={[styles.nowButton, { flex: 1, backgroundColor: '#FFFFFF' }]} onPress={() => router.push('/todos')}>
            <AppText size={15} weight="semibold" color={Colors.primary}>
              등기부 올리기
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
              {Math.round(ratio * 100)}%
            </AppText>
            <View style={styles.bar}>
              <View style={[styles.barFill, { width: `${ratio * 100}%`, backgroundColor: band.color }]} />
            </View>
            <AppText size={12} color={Colors.textSub} style={{ marginTop: 8 }}>
              {band.label} · 10/9 기준
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

      <Link href="/check" style={styles.textLink}>
        <AppText size={13} weight="semibold" color={Colors.primary}>
          계약 전 확인 결과 다시 보기 →
        </AppText>
      </Link>

      <View style={{ flex: 1 }} />
      <Disclaimer>정보 제공이며 보증하지 않습니다 · 조회 {today.full}</Disclaimer>
    </Screen>
  );
}

const styles = StyleSheet.create({
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
  textLink: { marginTop: 16, paddingVertical: 12 },
});
