import { router } from 'expo-router';
import * as WebBrowser from 'expo-web-browser';
import { Pressable, StyleSheet, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { Icon } from '@/components/Icon';
import { Card, Disclaimer, Screen, SectionLabel } from '@/components/layout';
import { Colors, Radius } from '@/constants/theme';
import { helpDesks, house, returnSteps as demoSteps } from '@/data/demo';
import type { ApiContract } from '@/lib/api';
import { useLatestContract } from '@/lib/contract';

type ReturnStep = { title: string; body: string; state: 'done' | 'current' | 'todo' };

/** 보증기관별 청구 창구 (rules/guarantors.yaml claim_channel). 기관 이름은 제도 안내로만 쓴다 */
const claimChannels = {
  HUG: { label: '주택도시보증공사', channel: 'HUG 보증 이행 청구 창구' },
  HF: { label: '한국주택금융공사', channel: 'HF 보증 이행 청구 창구' },
  SGI: { label: '서울보증보험', channel: 'SGI 보험금 청구 창구' },
} as const;

/**
 * 내 계약의 반환 대응 순서. 반환 확인 → 반환 대응 흐름(#52)이 서버에 생기기 전이라 진행 상태는 첫 단계부터 시작하고,
 * 만기일과 보증기관(미가입이면 공공 상담 창구)만 계약 값으로 바꾼다
 */
function stepsFor(contract: ApiContract): ReturnStep[] {
  const claim = contract.guarantor === 'none' ? null : claimChannels[contract.guarantor];
  return [
    { title: '반환 요청 기록', body: '보증금 반환을 요청한 문자·통화 기록을 캡처해 기록함에 남겨요.', state: 'current' },
    ...demoSteps.slice(1, 3).map((s) => ({ ...s, state: 'todo' as const })),
    claim
      ? {
          title: '반환보증 청구',
          body: `${claim.label} 반환보증 가입자예요. ${claim.channel}에서 절차를 안내받으세요.`,
          state: 'todo',
        }
      : {
          title: '공공 상담 받기',
          body: '반환보증에 가입하지 않았어요. 대한법률구조공단 등 공공 상담 창구에서 다음 절차를 안내받으세요.',
          state: 'todo',
        },
  ];
}

/** UI-08 반환 대응 안내 (정적). 일반 절차 안내이며 개별 법률 판단이 아니다. 계약이 있으면 그 만기일·보증기관으로 */
export default function ReturnScreen() {
  const contract = useLatestContract();
  const returnSteps: ReturnStep[] = contract ? stepsFor(contract) : demoSteps;
  const endDate = contract ? contract.end_date.replaceAll('-', '.') : house.endDate;
  return (
    <Screen title="반환 대응 안내">
      <View style={styles.hero}>
        <AppText size={12} weight="semibold" color={Colors.dangerDeep}>
          {endDate} 만기 · 보증금 못 받음
        </AppText>
        <AppText size={19} weight="bold" color={Colors.dangerText} leading={1.4} style={{ marginTop: 6 }}>
          아직 이사 가지 마세요. 순서대로 함께 챙길게요.
        </AppText>
      </View>

      <View style={{ marginTop: 18, gap: 8 }}>
        {returnSteps.map((s, i) => {
          const current = s.state === 'current';
          const done = s.state === 'done';
          return (
            <View key={s.title} style={[styles.step, current && styles.stepCurrent, done && { opacity: 0.7 }]}>
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
                    {i + 1}
                  </AppText>
                )}
              </View>
              <View style={{ flex: 1 }}>
                <AppText size={15} weight={current ? 'bold' : 'semibold'}>
                  {s.title}
                </AppText>
                <AppText
                  size={done ? 12 : 13}
                  color={Colors.textSub}
                  leading={done ? undefined : 1.6}
                  style={{ marginTop: done ? 2 : 4 }}>
                  {s.body}
                </AppText>
                {current ? (
                  <Pressable style={styles.smallButton} onPress={() => router.push('/records')}>
                    <AppText size={13} weight="semibold" color="#FFFFFF">
                      보낸 뒤 사본 올리기
                    </AppText>
                  </Pressable>
                ) : null}
              </View>
            </View>
          );
        })}
      </View>

      <Card style={{ marginTop: 18 }}>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
          <AppText size={14} weight="bold">
            청구 서류 대조
          </AppText>
          <AppText size={13} weight="bold" color={Colors.danger}>
            6개 중 1개 빠짐
          </AppText>
        </View>
        <View style={styles.progress}>
          <View style={{ width: '83%', height: 8, backgroundColor: Colors.ok }} />
        </View>
        <AppText size={13} color={Colors.textSub} style={{ marginTop: 10 }}>
          빠진 서류:{' '}
          <AppText size={13} weight="bold" color={Colors.danger}>
            내용증명 사본
          </AppText>
        </AppText>
        <Pressable onPress={() => router.push('/records')} style={{ minHeight: 44, justifyContent: 'center' }}>
          <AppText size={13} weight="semibold" color={Colors.primary}>
            비상 서류함 열기 →
          </AppText>
        </Pressable>
      </Card>

      <SectionLabel>상담 창구</SectionLabel>
      <View style={styles.links}>
        {helpDesks.map((h, i) => (
          <Pressable
            key={h.url}
            accessibilityRole="link"
            onPress={() => WebBrowser.openBrowserAsync(h.url)}
            style={[styles.link, i < helpDesks.length - 1 && styles.divider]}>
            <AppText size={14}>{h.label}</AppText>
            <AppText size={14} color={Colors.textHint}>
              ↗
            </AppText>
          </Pressable>
        ))}
      </View>

      <View style={{ flex: 1 }} />
      <Disclaimer>일반 절차 안내이며 개별 법률 판단이 아닙니다.</Disclaimer>
    </Screen>
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
