import { StyleSheet, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { Card, DashedBox, DemoTag, Disclaimer, Screen, SectionLabel } from '@/components/layout';
import { SpecialTermRow, verdictStyle } from '@/components/verdict';
import { Colors, Radius } from '@/constants/theme';
import { checkResult } from '@/data/demo';
import { detailRowsFor, useLatestCheck } from '@/lib/check';
import { formatWon } from '@/lib/format';
import { termsFor } from '@/lib/special-terms';

/** UI-02 판정 상세: 마지막 판정 결과(없으면 시연 집 결과)를 항목별로 */
export default function DetailScreen() {
  const view = useLatestCheck() ?? checkResult;
  const rows = detailRowsFor(view);
  const mortgageAmount = view.input.registry?.mortgage ? view.input.registry.mortgage_amount : 0;
  const mortgageLine = view.sourceLines?.find((line) => line.includes('근저당'));
  const terms = termsFor(view.matched);

  return (
    <Screen title="판정 상세">
      <SectionLabel style={{ marginTop: 10 }}>항목별 결과</SectionLabel>
      <View style={styles.table}>
        {rows.map((row, i) => {
          const hit = row.level !== 'ok';
          // 등기부에서 걸린 항목만 줄 전체를 칠한다 (목업: 근저당 줄)
          const marked = hit && row.value.startsWith('있음');
          return (
            <View
              key={row.label}
              style={[styles.row, i < rows.length - 1 && styles.divider, marked && { backgroundColor: Colors.cautionRow }]}>
              <AppText size={14} weight={marked ? 'semibold' : 'regular'}>
                {row.label}
              </AppText>
              <AppText size={12} weight={hit ? 'bold' : 'semibold'} color={verdictStyle[row.level].fg}>
                {row.value}
              </AppText>
            </View>
          );
        })}
      </View>

      {mortgageAmount > 0 ? (
        <>
          <SectionLabel>근저당, 쉬운 말로</SectionLabel>
          <Card>
            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
              <AppText size={11} color={Colors.textHint}>
                등기부 요약 · 을구
              </AppText>
              {view.virtualMortgage ? <DemoTag label="시연용 가상 근저당" /> : null}
            </View>
            {mortgageLine ? (
              <View style={styles.source}>
                <AppText size={12} color={Colors.textCode} leading={1.7}>
                  {mortgageLine}
                </AppText>
              </View>
            ) : null}
            <AppText size={14} leading={1.7} style={{ marginTop: 12 }}>
              집주인이 이 집을 담보로 돈을 빌렸어요. 집이 경매로 넘어가면 근저당권자가{' '}
              <AppText size={14} weight="bold">
                최대 {formatWon(mortgageAmount)} 원
              </AppText>
              을 내 보증금보다 먼저 가져가요.
            </AppText>
            <AppText size={12} color={Colors.textHint} style={{ marginTop: 8 }}>
              자동 설명은 참고용이에요. 원문과 다르면 원문이 기준이에요.
            </AppText>
          </Card>
        </>
      ) : null}

      {terms.length ? (
        <>
          <SectionLabel>이 판정에 맞는 특약 예시</SectionLabel>
          <View style={{ gap: 8 }}>
            {terms.map((t) => (
              <SpecialTermRow key={t.id} term={t} />
            ))}
          </View>
        </>
      ) : null}

      {view.unchecked.map((u) => (
        <DashedBox key={u.label} style={{ marginTop: 20 }}>
          <AppText size={14} weight="semibold">
            확인 못 한 항목 · {u.label}
          </AppText>
          <AppText size={13} color={Colors.textSub} leading={1.6} style={{ marginTop: 6 }}>
            {u.guide}
          </AppText>
        </DashedBox>
      ))}

      <View style={{ flex: 1 }} />
      <Disclaimer>
        조회 {view.checkedAt} · 정보 제공이며 보증하지 않습니다. 개별 법률 판단이 필요하면 공공 상담 창구를 이용하세요.
      </Disclaimer>
    </Screen>
  );
}

const styles = StyleSheet.create({
  table: {
    backgroundColor: Colors.card,
    borderRadius: Radius.card,
    borderWidth: 1,
    borderColor: Colors.border,
    overflow: 'hidden',
  },
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 14, paddingHorizontal: 16 },
  divider: { borderBottomWidth: 1, borderBottomColor: Colors.divider },
  source: { marginTop: 6, paddingVertical: 10, paddingHorizontal: 12, backgroundColor: Colors.bg, borderRadius: 8 },
});
