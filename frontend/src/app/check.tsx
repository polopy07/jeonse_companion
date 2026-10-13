import { router } from 'expo-router';
import { useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { Button, DemoTag, Disclaimer, Screen, SectionLabel } from '@/components/layout';
import { MatchedItem, RatioGauge, UncheckedBox, VerdictCard } from '@/components/verdict';
import { Colors, Radius } from '@/constants/theme';
import { checkResult } from '@/data/demo';
import { useLatestCheck } from '@/lib/check';

/** UI-01 계약 전 확인 결과 (무료). 입력 화면에서 넘어오면 그 결과를, 아니면 시연 집 결과를 보여 준다 */
export default function CheckScreen() {
  const latest = useLatestCheck();
  const r = latest ?? checkResult;
  const [showFormula, setShowFormula] = useState(false);

  const footer = (
    <>
      <Disclaimer style={{ paddingTop: 0, marginBottom: 12 }}>{r.disclaimer}</Disclaimer>
      {r.level === 'problem' ? (
        // FR-011: 문제 항목이면 결제를 막고 계약 재검토·공공 상담 창구를 안내한다
        <Button label="공공 상담 창구 보기" href="/return" />
      ) : r.level === 'na' ? (
        <Button label="할 일 관리로 시작 · 4,900원" href="/site-check" />
      ) : (
        <Button label="전동기 패키지로 계약 당일 준비 · 9,900원" href="/site-check" />
      )}
    </>
  );

  return (
    <Screen title="계약 전 확인 결과" footer={footer}>
      <AppText size={13} color={Colors.textSub} style={{ marginTop: 10 }}>
        {r.houseLabel}
      </AppText>
      {r.virtualMortgage ? <DemoTag label="시연용 가상 근저당" style={{ marginTop: 6 }} /> : null}
      {r.notice ? (
        <AppText size={12} color={Colors.textHint} style={{ marginTop: 6 }}>
          {r.notice}
        </AppText>
      ) : null}

      <View style={{ marginTop: 12 }}>
        <VerdictCard level={r.level} title={r.next_step} summary={r.summary} />
      </View>

      {r.block_payment ? (
        <View style={styles.block}>
          <AppText size={14} weight="bold" color={Colors.dangerDeep}>
            패키지 결제를 막아 두었어요
          </AppText>
          <AppText size={13} color={Colors.dangerText} leading={1.6} style={{ marginTop: 4 }}>
            문제 항목이 해결되기 전에는 계약금을 보내지 마세요. 계약을 다시 검토하고 상담 창구에 물어보세요.
          </AppText>
        </View>
      ) : null}

      {r.deposit_ratio !== null ? (
        <View style={{ marginTop: 12 }}>
          <RatioGauge ratio={r.deposit_ratio} isMinimum={r.ratio_is_minimum}>
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
                  {r.formula.join('\n')}
                </AppText>
              ) : null}
            </View>
          </RatioGauge>
        </View>
      ) : null}

      {r.matched.length ? (
        <>
          <SectionLabel>걸린 항목 {r.matched.length}개</SectionLabel>
          <View style={{ gap: 8 }}>
            {r.matched.map((m) => (
              <MatchedItem key={m.key} item={m} onPress={() => router.push('/detail')} />
            ))}
          </View>
        </>
      ) : null}

      <SectionLabel>확인 못 한 항목</SectionLabel>
      <View style={{ gap: 8 }}>
        {r.unchecked.map((u) => (
          <UncheckedBox key={u.label} item={u} />
        ))}
      </View>

      {latest ? (
        <Pressable onPress={() => router.back()} style={{ minHeight: 44, justifyContent: 'center', marginTop: 12 }}>
          <AppText size={13} weight="semibold" color={Colors.primary}>
            입력 다시 하기 →
          </AppText>
        </Pressable>
      ) : null}
    </Screen>
  );
}

const styles = StyleSheet.create({
  block: { marginTop: 12, paddingVertical: 14, paddingHorizontal: 16, backgroundColor: Colors.dangerBg, borderRadius: Radius.sm },
});
