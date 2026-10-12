import { router } from 'expo-router';
import { useState } from 'react';
import { Pressable, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { Button, Disclaimer, Screen, SectionLabel } from '@/components/layout';
import { MatchedItem, RatioGauge, UncheckedBox, VerdictCard } from '@/components/verdict';
import { Colors } from '@/constants/theme';
import { checkResult, house } from '@/data/demo';

/** UI-01 계약 전 확인 결과 (무료) */
export default function CheckScreen() {
  const r = checkResult;
  const [showFormula, setShowFormula] = useState(false);

  return (
    <Screen
      title="계약 전 확인 결과"
      footer={
        <>
          <Disclaimer style={{ paddingTop: 0, marginBottom: 12 }}>{r.disclaimer}</Disclaimer>
          <Button label="전동기 패키지로 계약 당일 준비 · 9,900원" href="/contract-day" />
        </>
      }>
      <AppText size={13} color={Colors.textSub} style={{ marginTop: 10 }}>
        {house.name} · {house.type}
      </AppText>

      <View style={{ marginTop: 12 }}>
        <VerdictCard level={r.level} title={r.next_step} summary={r.summary} />
      </View>

      <View style={{ marginTop: 12 }}>
        <RatioGauge ratio={r.deposit_ratio}>
          <View style={{ marginTop: 14, borderTopWidth: 1, borderTopColor: Colors.divider, paddingTop: 4 }}>
            <Pressable
              accessibilityRole="button"
              accessibilityState={{ expanded: showFormula }}
              onPress={() => setShowFormula((v) => !v)}
              style={{ minHeight: 44, justifyContent: 'center' }}>
              <AppText size={13} weight="semibold" color={Colors.primary}>
                {showFormula ? '계산 방법 접기' : '계산 방법 보기'}
              </AppText>
            </Pressable>
            {showFormula ? (
              <AppText size={13} color={Colors.textSub} leading={1.8}>
                (보증금 1억 4,000만 + 근저당 3,600만) ÷ 추정 집값 2억 1,000만{'\n'}
                추정 집값 = 공시가격 1억 5,000만 × 140%{'\n'}
                실거래가: 같은 단지·비슷한 면적 표본 부족
              </AppText>
            ) : null}
          </View>
        </RatioGauge>
      </View>

      <SectionLabel>걸린 항목 {r.matched.length}개</SectionLabel>
      <View style={{ gap: 8 }}>
        {r.matched.map((m) => (
          <MatchedItem key={m.key} item={m} onPress={() => router.push('/detail')} />
        ))}
      </View>

      <SectionLabel>확인 못 한 항목</SectionLabel>
      <View style={{ gap: 8 }}>
        {r.unchecked.map((u) => (
          <UncheckedBox key={u.label} item={u} />
        ))}
      </View>
    </Screen>
  );
}
